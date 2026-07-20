from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Sequence, Set

from src.models import Candidate
from src.utils.dates import CN_TZ, parse_datetime
from src.utils.text import normalize_model_name, normalize_title


def dedupe_urls(candidates: Sequence[Candidate]) -> List[Candidate]:
    seen: Set[str] = set()
    result: List[Candidate] = []
    for candidate in candidates:
        key = (candidate.source_url or "").split("#", 1)[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def hamming_distance_hex(left: str, right: str) -> int:
    if not left or not right:
        return 999
    try:
        width = max(len(left), len(right)) * 4
        return bin(int(left, 16) ^ int(right, 16)).count("1") if width else 999
    except ValueError:
        return 999


def dedupe_image_hashes(candidates: Sequence[Candidate], max_distance: int = 6) -> List[Candidate]:
    result: List[Candidate] = []
    hashes: List[str] = []
    for candidate in candidates:
        image_hash = candidate.image_hash
        if image_hash and any(hamming_distance_hex(image_hash, old) <= max_distance for old in hashes):
            continue
        if image_hash:
            hashes.append(image_hash)
        result.append(candidate)
    return result


def dedupe_titles(candidates: Sequence[Candidate]) -> List[Candidate]:
    seen: Set[str] = set()
    result: List[Candidate] = []
    for candidate in candidates:
        key = normalize_title(candidate.title)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def dedupe_recent_models(
    candidates: Sequence[Candidate],
    existing_cases: Sequence[Dict],
    category: str,
    window_days: int,
    now: datetime,
) -> List[Candidate]:
    cutoff = now - timedelta(days=window_days)
    recent_models: Set[str] = set()
    for case in existing_cases:
        if case.get("category") != category or not case.get("visible", True):
            continue
        published = parse_datetime(case.get("published_at", ""))
        if published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=CN_TZ)
        if published >= cutoff:
            model = case.get("normalized_model_name") or normalize_model_name(case.get("model_name", "") or case.get("title", ""))
            if model:
                recent_models.add(model)
    result: List[Candidate] = []
    for candidate in candidates:
        model = candidate.normalized_model_name or normalize_model_name(candidate.model_name or candidate.title)
        candidate.normalized_model_name = model
        if model and model in recent_models:
            continue
        result.append(candidate)
    return result


def apply_blocked_cases(candidates: Sequence[Candidate], blocked: Dict) -> List[Candidate]:
    blocked_urls = set(blocked.get("blocked_source_urls") or [])
    blocked_content = set(blocked.get("blocked_content_hashes") or [])
    blocked_images = set(blocked.get("blocked_image_hashes") or [])
    blocked_models = set()
    for row in blocked.get("blocked_normalized_model_names_by_category") or []:
        if isinstance(row, dict):
            blocked_models.add((row.get("category"), row.get("normalized_model_name")))
    result: List[Candidate] = []
    for candidate in candidates:
        key = (candidate.category, candidate.normalized_model_name)
        if candidate.source_url in blocked_urls:
            continue
        if candidate.content_hash in blocked_content:
            continue
        if candidate.image_hash in blocked_images:
            continue
        if key in blocked_models:
            continue
        result.append(candidate)
    return result
