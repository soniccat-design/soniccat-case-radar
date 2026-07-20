from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from src.models import category_map, enabled_categories, public_case
from src.utils.json_store import load_json, write_json


PAGE_COPY = {
    "index": {
        "eyebrow": "今日新增",
        "heading": "专业鞋案例每日精选",
        "lead": "每天自动沉淀专业跑鞋、跑鞋底片和专业钉鞋参考案例。页面只展示图片、分类和一句设计参考理由。",
    },
    "category": {
        "eyebrow": "历史沉淀",
        "lead": "按最新顺序沉淀同类案例，便于长期做系列化设计、结构拆解和竞品参考。",
    },
}


def build_site(config: Dict[str, Any]) -> Path:
    project = config.get("project", {})
    output_dir = Path(project.get("site_output_dir", "site"))
    data_dir = Path(project.get("backend_data_dir", "data"))
    static_dir = Path(project.get("static_dir", "static"))
    asset_state_dir = Path(project.get("asset_state_dir", "case_assets"))

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = load_json(data_dir / "cases.json", [])
    latest = load_json(data_dir / "latest.json", [])
    categories = enabled_categories(config)
    category_lookup = category_map(config)
    visible_cases = [case for case in cases if case.get("visible", True)]
    visible_cases.sort(key=lambda item: item.get("published_at", ""), reverse=True)

    public_latest = _public_cases(latest, category_lookup)
    if not public_latest:
        public_latest = _public_cases(visible_cases[: sum(int(c.get("daily_limit", 3)) for c in categories)], category_lookup)
    public_all = _public_cases(visible_cases, category_lookup)

    _copy_static(static_dir, output_dir / "static")
    _copy_case_images(public_all, output_dir, asset_state_dir)
    _write_public_data(output_dir, public_latest, public_all, categories)

    nav = _nav_items(categories, active="index")
    _render_page(
        output_dir / "index.html",
        config,
        title="SONIC CAT 专业鞋案例雷达",
        description="专业鞋案例每日精选静态案例库",
        eyebrow=PAGE_COPY["index"]["eyebrow"],
        heading=PAGE_COPY["index"]["heading"],
        lead=PAGE_COPY["index"]["lead"],
        cases=public_latest,
        categories=categories,
        nav=nav,
        base_path="",
    )

    for category in categories:
        route_dir = output_dir / category["route"].strip("/")
        category_cases = [case for case in public_all if case["category"] == category["id"]]
        _render_page(
            route_dir / "index.html",
            config,
            title="%s - SONIC CAT 专业鞋案例雷达" % category["name"],
            description="%s历史案例库" % category["name"],
            eyebrow=PAGE_COPY["category"]["eyebrow"],
            heading=category["name"],
            lead=PAGE_COPY["category"]["lead"],
            cases=category_cases,
            categories=categories,
            nav=_nav_items(categories, active=category["id"]),
            base_path="../",
        )

    _copy_404(config, output_dir)
    return output_dir


def _public_cases(cases: List[Dict[str, Any]], category_lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for case in cases:
        category = category_lookup.get(case.get("category", ""), {})
        rows.append(public_case(case, category_name=category.get("name", case.get("category", ""))))
    return rows


def _write_public_data(output_dir: Path, latest: List[Dict[str, Any]], all_cases: List[Dict[str, Any]], categories: List[Dict[str, Any]]) -> None:
    public_data = output_dir / "data"
    write_json(public_data / "latest.json", latest)
    write_json(public_data / "cases.json", all_cases)
    for category in categories:
        write_json(public_data / ("%s.json" % category["id"]), [case for case in all_cases if case["category"] == category["id"]])


def _copy_static(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target)


def _copy_case_images(cases: List[Dict[str, Any]], output_dir: Path, asset_state_dir: Path) -> None:
    for case in cases:
        image_path = case.get("image_path", "")
        if not image_path:
            continue
        source = _resolve_image_source(image_path, asset_state_dir)
        if not source.exists():
            continue
        target = output_dir / image_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _resolve_image_source(image_path: str, asset_state_dir: Path) -> Path:
    if image_path.startswith("assets/cases/"):
        return asset_state_dir / "cases" / Path(image_path).name
    return Path(image_path)


def _render_page(
    path: Path,
    config: Dict[str, Any],
    title: str,
    description: str,
    eyebrow: str,
    heading: str,
    lead: str,
    cases: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    nav: List[Dict[str, Any]],
    base_path: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    template_dir = Path(config.get("project", {}).get("templates_dir", "templates"))
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore

        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape(["html", "xml"]))
        template = env.get_template("base.html")
        html = template.render(
            title=title,
            description=description,
            eyebrow=eyebrow,
            heading=heading,
            lead=lead,
            cases=cases,
            categories=categories,
            nav=nav,
            base_path=base_path,
        )
    except Exception:
        html = _render_fallback(title, description, eyebrow, heading, lead, cases, categories, nav, base_path)
    path.write_text(html, encoding="utf-8")


def _render_fallback(
    title: str,
    description: str,
    eyebrow: str,
    heading: str,
    lead: str,
    cases: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    nav: List[Dict[str, Any]],
    base_path: str,
) -> str:
    nav_html = "".join(
        '<a href="%s%s"%s>%s</a>'
        % (base_path, item["href"], ' aria-current="page"' if item.get("active") else "", item["label"])
        for item in nav
    )
    filters = "".join('<button class="filter-button" data-filter="%s" aria-pressed="false">%s</button>' % (c["id"], c["name"]) for c in categories)
    cards = "".join(
        '<article class="case-card" data-category="{category}"><img class="case-image" src="{base}{image_path}" alt="{category_name}案例图片" loading="lazy" data-fallback="true"><div class="case-body"><span class="case-category">{category_name}</span><p class="case-reason">{reason}</p></div></article>'.format(
            base=base_path,
            **case,
        )
        for case in cases
    )
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><meta name="description" content="{description}"><link rel="stylesheet" href="{base}static/styles.css"></head><body data-placeholder="{base}static/placeholder.svg"><header class="site-header"><div class="header-inner"><a class="brand" href="{base}index.html"><span class="brand-mark">SONIC CAT 专业鞋案例雷达</span><span class="brand-sub">专业跑鞋 / 底片 / 钉鞋案例库</span></a><nav class="nav">{nav}</nav></div></header><main class="page-shell"><section class="hero"><p class="eyebrow">{eyebrow}</p><h1>{heading}</h1><p class="lead">{lead}</p></section><section class="toolbar"><div class="filters"><button class="filter-button is-active" data-filter="all" aria-pressed="true">全部</button>{filters}</div><div class="result-count" data-result-count>{count} 个案例</div></section><section class="case-grid">{cards}</section></main><footer class="site-footer"><div class="page-shell">仅展示设计参考信息；来源、评分和抓取过程保存在后台用于核验与下架。</div></footer><script src="{base}static/app.js"></script></body></html>""".format(
        title=title,
        description=description,
        base=base_path,
        nav=nav_html,
        eyebrow=eyebrow,
        heading=heading,
        lead=lead,
        filters=filters,
        count=len(cases),
        cards=cards,
    )


def _nav_items(categories: List[Dict[str, Any]], active: str) -> List[Dict[str, Any]]:
    rows = [{"href": "index.html", "label": "首页", "active": active == "index"}]
    for category in categories:
        rows.append(
            {
                "href": category["route"].strip("/") + "/index.html",
                "label": category["name"],
                "active": active == category["id"],
            }
        )
    return rows


def _copy_404(config: Dict[str, Any], output_dir: Path) -> None:
    template = Path(config.get("project", {}).get("templates_dir", "templates")) / "404.html"
    if template.exists():
        shutil.copy2(template, output_dir / "404.html")
