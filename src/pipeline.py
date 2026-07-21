from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import signal
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.ai.reasoner import ReasonGenerator
from src.collectors.base import BaseCollector
from src.collectors.registry import build_collectors
from src.dedupe.dedupe import (
    apply_blocked_cases,
    dedupe_image_hashes,
    dedupe_recent_models,
    dedupe_titles,
    dedupe_urls,
)
from src.filters.rules import filter_candidates
from src.images.processor import download_image_bytes, inspect_image_bytes, save_webp
from src.models import Candidate, SourceHealth, enabled_categories, public_case
from src.publishing.site import build_site
from src.scoring.scorer import score_and_sort
from src.utils.config import load_yaml
from src.utils.dates import iso_now, now_cn
from src.utils.json_store import load_json, write_json
from src.utils.text import content_hash, normalize_model_name, stable_hash


def run_daily(
    config: Dict[str, Any],
    root: Path,
    collectors: Optional[List[BaseCollector]] = None,
    build: bool = True,
) -> Dict[str, Any]:
    project = config.get("project", {})
    data_dir = root / project.get("backend_data_dir", "data")
    asset_state_dir = root / project.get("asset_state_dir", "case_assets")
    blocked_cases = load_yaml(root / "config/blocked_cases.yml")
    blocked_sources = load_yaml(root / "config/blocked_sources.yml")
    existing_cases = load_json(data_dir / "cases.json", [])
    categories = enabled_categories(config)
    global_config = config.get("global", {})
    time_windows = global_config.get("time_windows", {})
    primary_days = int(time_windows.get("primary_days", 365))
    fallback_days = int(time_windows.get("fallback_days", 1095))
    daily_new_cases: List[Dict[str, Any]] = []
    source_health: List[Dict[str, Any]] = []
    category_summary: Dict[str, Dict[str, Any]] = {}
    reasoner = ReasonGenerator(config)
    active_collectors = collectors if collectors is not None else build_collectors(config, blocked_sources)
    run_config = global_config.get("run", {})
    started_at = time.monotonic()
    max_total_seconds = int(run_config.get("max_total_seconds", 0) or 0)
    max_category_seconds = int(run_config.get("max_seconds_per_category", 0) or 0)
    max_source_seconds = int(run_config.get("max_seconds_per_source", 0) or 0)

    for category in categories:
        if max_total_seconds and time.monotonic() - started_at >= max_total_seconds:
            category_summary[category["id"]] = {
                "name": category["name"],
                "selected": 0,
                "daily_limit": int(category.get("daily_limit", 3)),
                "used_fallback_days": False,
                "raw_candidates": 0,
                "filtered_candidates": 0,
                "filtered_out": 0,
                "skipped_reason": "daily runtime budget reached",
            }
            continue
        deadline = None
        if max_total_seconds:
            deadline = started_at + max_total_seconds
        if max_category_seconds:
            category_deadline = time.monotonic() + max_category_seconds
            deadline = min(deadline, category_deadline) if deadline else category_deadline
        selected, health, used_fallback, stats = run_category(
            category=category,
            config=config,
            collectors=active_collectors,
            existing_cases=existing_cases + daily_new_cases,
            blocked_cases=blocked_cases,
            asset_state_dir=asset_state_dir,
            reasoner=reasoner,
            primary_days=primary_days,
            fallback_days=fallback_days,
            deadline=deadline,
            max_source_seconds=max_source_seconds,
        )
        daily_new_cases.extend(selected)
        source_health.extend([item.to_dict() for item in health])
        category_summary[category["id"]] = {
            "name": category["name"],
            "selected": len(selected),
            "daily_limit": int(category.get("daily_limit", 3)),
            "used_fallback_days": used_fallback,
            "raw_candidates": stats["raw_candidates"],
            "filtered_candidates": stats["filtered_candidates"],
            "filtered_out": max(0, stats["raw_candidates"] - stats["filtered_candidates"]),
        }

    publish_allowed = True
    if global_config.get("publish_guard", {}).get("block_when_all_categories_empty", True):
        publish_allowed = len(daily_new_cases) > 0

    generated_at = iso_now()
    if daily_new_cases:
        merged = merge_cases(existing_cases, daily_new_cases)
        write_json(data_dir / "cases.json", merged)
        write_json(data_dir / "latest.json", [public_case(case) for case in daily_new_cases])
    else:
        write_json(data_dir / "latest.json", [])

    source_health_doc = build_source_health(generated_at, source_health)
    write_json(data_dir / "source_health.json", source_health_doc)

    summary = {
        "generated_at": generated_at,
        "publish_allowed": publish_allowed,
        "selected_total": len(daily_new_cases),
        "categories": category_summary,
        "source_health_summary": source_health_doc["summary"],
        "source_health": source_health_doc["sources"],
    }
    write_json(data_dir / "run_summary.json", summary)

    if build and publish_allowed:
        build_site(config)
    return summary


def run_category(
    category: Dict[str, Any],
    config: Dict[str, Any],
    collectors: List[BaseCollector],
    existing_cases: List[Dict[str, Any]],
    blocked_cases: Dict[str, Any],
    asset_state_dir: Path,
    reasoner: ReasonGenerator,
    primary_days: int,
    fallback_days: int,
    deadline: Optional[float] = None,
    max_source_seconds: int = 0,
) -> Tuple[List[Dict[str, Any]], List[SourceHealth], bool, Dict[str, int]]:
    daily_limit = int(category.get("daily_limit", 3))
    primary_candidates, health = collect_from_sources(category, collectors, primary_days, deadline=deadline, max_source_seconds=max_source_seconds)
    prepared = prepare_candidates(primary_candidates, category, config, existing_cases, blocked_cases, primary_days)
    used_fallback = False
    if len(prepared) < daily_limit and not _deadline_reached(deadline):
        fallback_candidates, fallback_health = collect_from_sources(category, collectors, fallback_days, deadline=deadline, max_source_seconds=max_source_seconds)
        health.extend(fallback_health)
        prepared = prepare_candidates(primary_candidates + fallback_candidates, category, config, existing_cases, blocked_cases, fallback_days)
        used_fallback = True

    weights = config.get("global", {}).get("scoring", {})
    sorted_candidates = score_and_sort(prepared, category, weights, primary_days)
    selected: List[Dict[str, Any]] = []
    selected_source_counts: Dict[Tuple[str, int], int] = {}
    now_iso = iso_now()
    image_config = config.get("global", {}).get("image", {})
    for candidate in sorted_candidates:
        if len(selected) >= daily_limit:
            break
        candidate.reason = reasoner.generate(candidate, category)
        case_id = make_case_id(category["id"], candidate)
        final_path = asset_state_dir / "cases" / ("%s.webp" % case_id)
        if candidate.image_bytes is None:
            try:
                candidate.image_bytes = download_image_bytes(candidate.image_url, timeout=int(image_config.get("request_timeout_seconds", 20)))
            except Exception as exc:
                candidate.metadata["final_download_error"] = str(exc)[:200]
                continue
        saved = save_webp(
            candidate.image_bytes,
            final_path,
            max_long_edge=int(image_config.get("max_long_edge", 1400)),
            target_max_kb=int(image_config.get("target_max_kb", 250)),
        )
        if saved is None:
            candidate.metadata["final_image_error"] = "webp conversion failed"
            continue
        source_key = (candidate.source_id or "unknown", int(candidate.metadata.get("collection_window_days", 0) or 0))
        selected_source_counts[source_key] = selected_source_counts.get(source_key, 0) + 1
        selected.append(candidate.to_case_record(case_id, "assets/cases/%s.webp" % case_id, now_iso))

    _annotate_source_health(health, prepared, selected_source_counts)
    stats = {
        "raw_candidates": sum(item.candidates for item in health),
        "filtered_candidates": len(prepared),
    }
    return selected, health, used_fallback, stats


def collect_from_sources(
    category: Dict[str, Any],
    collectors: List[BaseCollector],
    days: int,
    deadline: Optional[float] = None,
    max_source_seconds: int = 0,
) -> Tuple[List[Candidate], List[SourceHealth]]:
    all_candidates: List[Candidate] = []
    health: List[SourceHealth] = []
    for collector in collectors:
        source_id = getattr(collector, "source_id", "unknown")
        source_type = getattr(collector, "source_type", "unknown")
        if _deadline_reached(deadline):
            health.append(
                SourceHealth(
                    source_id,
                    source_type,
                    "skipped",
                    category=category.get("id", ""),
                    window_days=days,
                    message="runtime budget reached",
                )
            )
            continue
        source_config = getattr(collector, "source_config", {})
        original_deadline = source_config.get("deadline_seconds") if isinstance(source_config, dict) else None
        source_deadline = 0
        if deadline:
            remaining = max(1, int(deadline - time.monotonic()))
            source_deadline = _source_runtime_budget(source_config, remaining, max_source_seconds)
            if isinstance(source_config, dict):
                source_config["deadline_seconds"] = source_deadline
        elif isinstance(source_config, dict):
            source_deadline = _source_runtime_budget(source_config, None, max_source_seconds)
        try:
            with _collector_timeout(source_deadline, source_id):
                candidates, source_health = collector.safe_collect(category, days)
        except TimeoutError as exc:
            candidates = []
            source_health = SourceHealth(
                source_id,
                source_type,
                "failed",
                category=category.get("id", ""),
                window_days=days,
                message=str(exc)[:400],
            )
        if isinstance(source_config, dict):
            if original_deadline is None:
                source_config.pop("deadline_seconds", None)
            else:
                source_config["deadline_seconds"] = original_deadline
        for candidate in candidates:
            if not candidate.source_id:
                candidate.source_id = source_id
            candidate.metadata["collection_window_days"] = days
        source_health.category = source_health.category or category.get("id", "")
        source_health.window_days = source_health.window_days or days
        all_candidates.extend(candidates)
        health.append(source_health)
    return all_candidates, health


def _deadline_reached(deadline: Optional[float]) -> bool:
    return bool(deadline and time.monotonic() >= deadline)


def _annotate_source_health(
    health: List[SourceHealth],
    prepared: List[Candidate],
    selected_source_counts: Dict[Tuple[str, int], int],
) -> None:
    prepared_counts: Dict[Tuple[str, int], int] = {}
    for candidate in prepared:
        key = (candidate.source_id or "unknown", int(candidate.metadata.get("collection_window_days", 0) or 0))
        prepared_counts[key] = prepared_counts.get(key, 0) + 1
    for item in health:
        key = (item.source_id, int(item.window_days or 0))
        item.filtered_remaining = prepared_counts.get(key, 0)
        item.filtered_out = max(0, int(item.candidates or 0) - item.filtered_remaining)
        item.selected = selected_source_counts.get(key, 0)


def _source_runtime_budget(source_config: Any, remaining_seconds: Optional[int], max_source_seconds: int) -> int:
    budgets: List[int] = []
    if remaining_seconds:
        budgets.append(max(1, int(remaining_seconds)))
    if max_source_seconds:
        budgets.append(max(1, int(max_source_seconds)))
    if isinstance(source_config, dict) and source_config.get("hard_timeout_seconds"):
        budgets.append(max(1, int(source_config["hard_timeout_seconds"])))
    return min(budgets) if budgets else 0


@contextmanager
def _collector_timeout(seconds: Any, source_id: str):
    timeout_seconds = int(seconds or 0)
    if timeout_seconds <= 0 or not hasattr(signal, "setitimer"):
        yield
        return

    def _raise_timeout(signum, frame):
        raise TimeoutError("collector %s exceeded runtime budget of %ss" % (source_id, timeout_seconds))

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def prepare_candidates(
    candidates: List[Candidate],
    category: Dict[str, Any],
    config: Dict[str, Any],
    existing_cases: List[Dict[str, Any]],
    blocked_cases: Dict[str, Any],
    days: int,
) -> List[Candidate]:
    global_config = config.get("global", {})
    image_config = global_config.get("image", {})
    candidate_limits = global_config.get("candidate_limits", {})
    max_candidates = int(candidate_limits.get("max_per_category", 50))
    candidates = dedupe_urls(candidates)[:max_candidates]
    normalized: List[Candidate] = []
    for candidate in candidates:
        candidate.normalized_model_name = candidate.normalized_model_name or normalize_model_name(candidate.model_name or candidate.title)
        candidate.content_hash = candidate.content_hash or content_hash(candidate.title, candidate.source_url, candidate.image_url)
        if not candidate.captured_at:
            candidate.captured_at = iso_now()
        if candidate.image_bytes is None:
            try:
                candidate.image_bytes = download_image_bytes(candidate.image_url, timeout=int(image_config.get("request_timeout_seconds", 20)))
            except Exception as exc:
                candidate.metadata["image_download_error"] = str(exc)[:200]
                continue
        inspected = inspect_image_bytes(candidate.image_bytes)
        if not inspected.get("ok"):
            candidate.metadata["image_error"] = inspected.get("reason", "invalid image")
            continue
        candidate.image_width = int(inspected.get("width", 0) or 0)
        candidate.image_height = int(inspected.get("height", 0) or 0)
        candidate.image_hash = str(inspected.get("image_hash", ""))
        candidate.metadata["clarity"] = inspected.get("clarity", 0.0)
        normalized.append(candidate)

    filtered = filter_candidates(normalized, category, image_config)
    filtered = apply_blocked_cases(filtered, blocked_cases)
    filtered = dedupe_titles(filtered)
    filtered = dedupe_image_hashes(filtered, int(global_config.get("dedupe", {}).get("perceptual_hash_max_distance", 6)))
    filtered = dedupe_recent_models(
        filtered,
        existing_cases,
        category["id"],
        int(global_config.get("dedupe", {}).get("category_model_window_days", 30)),
        now_cn(),
    )
    return filtered


def make_case_id(category_id: str, candidate: Candidate) -> str:
    seed = stable_hash(category_id, candidate.source_url, candidate.image_hash, candidate.content_hash, length=12)
    return "%s-%s" % (category_id, seed)


def merge_cases(existing_cases: List[Dict[str, Any]], new_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for case in new_cases + existing_cases:
        if case.get("id") in seen:
            continue
        seen.add(case.get("id"))
        merged.append(case)
    merged.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    return merged


def build_source_health(generated_at: str, health_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {"ok": 0, "failed": 0, "partial": 0, "skipped": 0}
    for row in health_rows:
        status = row.get("status", "failed")
        summary[status] = summary.get(status, 0) + 1
    return {"generated_at": generated_at, "sources": health_rows, "summary": summary}


def summary_markdown(summary: Dict[str, Any]) -> str:
    lines = ["# SONIC CAT 专业鞋案例雷达", ""]
    lines.append("- 是否允许发布：`%s`" % ("是" if summary.get("publish_allowed") else "否"))
    lines.append("- 本轮新增案例：`%s`" % summary.get("selected_total", 0))
    if not summary.get("publish_allowed"):
        lines.append("- 发布保护：`本轮新增为 0，已跳过 Pages 覆盖，上一版网页保持不变`")
    lines.append("")
    lines.append("| 分类 | 原始候选 | 筛选后 | 筛除 | 新增 | 每日目标 | 是否扩展近三年 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in summary.get("categories", {}).values():
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                row.get("name", ""),
                row.get("raw_candidates", 0),
                row.get("filtered_candidates", 0),
                row.get("filtered_out", 0),
                row.get("selected", 0),
                row.get("daily_limit", 0),
                "是" if row.get("used_fallback_days") else "否",
            )
        )
    lines.append("")
    lines.append("## 来源健康")
    for key, value in summary.get("source_health_summary", {}).items():
        lines.append("- %s: `%s`" % (key, value))
    lines.append("")
    lines.append("| 分类 | 来源 | 时间范围 | 状态 | 原始候选 | 筛选后 | 筛除 | 入选 | 失败原因 |")
    lines.append("| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |")
    for row in summary.get("source_health", []):
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                row.get("category", ""),
                row.get("source_id", ""),
                row.get("window_days", 0),
                row.get("status", ""),
                row.get("candidates", 0),
                row.get("filtered_remaining", 0),
                row.get("filtered_out", 0),
                row.get("selected", 0),
                _summary_cell(row.get("message", "")),
            )
        )
    return "\n".join(lines) + "\n"


def _summary_cell(value: Any) -> str:
    text = str(value or "").replace("|", "/").replace("\n", " ").strip()
    return text[:180]
