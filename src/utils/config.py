from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from . import simple_yaml


REQUIRED_CASE_FIELDS = {
    "id",
    "category",
    "image_path",
    "reason",
    "source_url",
    "source_domain",
    "source_type",
    "model_name",
    "normalized_model_name",
    "title",
    "image_hash",
    "content_hash",
    "score",
    "captured_at",
    "published_at",
    "visible",
}


def load_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text) or {}
    except Exception:
        loaded = simple_yaml.load(text) or {}
    if not isinstance(loaded, dict):
        raise ValueError("%s must contain a YAML mapping" % path)
    return loaded


def load_tasks(path: Path = Path("config/tasks.yml")) -> Dict[str, Any]:
    config = load_yaml(path)
    validate_tasks(config)
    return config


def validate_tasks(config: Dict[str, Any]) -> None:
    if "project" not in config:
        raise ValueError("tasks.yml missing project section")
    categories = config.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("tasks.yml must define at least one category")
    category_ids = set()
    for category in categories:
        for field in ("id", "name", "daily_limit", "route"):
            if field not in category:
                raise ValueError("category missing %s" % field)
        if category["id"] in category_ids:
            raise ValueError("duplicate category id: %s" % category["id"])
        category_ids.add(category["id"])
        if not category.get("keywords_zh") and not category.get("keywords_en"):
            raise ValueError("category %s must define keywords" % category["id"])
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("tasks.yml must define sources")
    for source in sources:
        for field in ("id", "type", "adapter", "enabled", "domains"):
            if field not in source:
                raise ValueError("source missing %s" % field)
        if not isinstance(source.get("domains"), list) or not source["domains"]:
            raise ValueError("source %s must define domains" % source["id"])
        for category_id in source.get("use_for", []):
            if category_id not in category_ids:
                raise ValueError("source %s references unknown category %s" % (source["id"], category_id))

    weights = config.get("global", {}).get("scoring", {})
    if weights:
        total = sum(int(weights.get(key, 0)) for key in ("relevance", "image_quality", "freshness", "source_trust"))
        if total != 100:
            raise ValueError("scoring weights must total 100, got %s" % total)


def enabled_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [item for item in items if item.get("enabled", True)]
