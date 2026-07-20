from __future__ import annotations

from typing import Any, Dict, List, Type

from src.collectors.base import BaseCollector
from src.collectors.generic import BrandSiteCollector, MediaSiteCollector
from src.collectors.world_athletics import WorldAthleticsCollector


def get_collector_class(adapter: str) -> Type[BaseCollector]:
    if adapter == "world_athletics":
        return WorldAthleticsCollector
    if adapter == "brand_site":
        return BrandSiteCollector
    if adapter == "media_site":
        return MediaSiteCollector
    if adapter == "xiaohongshu":
        from src.collectors.xiaohongshu import XiaohongshuCollector

        return XiaohongshuCollector
    raise ValueError("unknown collector adapter: %s" % adapter)


def build_collectors(config: Dict[str, Any], blocked_sources: Dict[str, Any]) -> List[BaseCollector]:
    blocked_ids = set(blocked_sources.get("blocked_source_ids") or [])
    blocked_domains = set(blocked_sources.get("blocked_domains") or [])
    collectors: List[BaseCollector] = []
    global_config = config.get("global", {})
    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
        if source.get("id") in blocked_ids:
            continue
        if any(domain in blocked_domains for domain in source.get("domains", [])):
            continue
        cls = get_collector_class(source.get("adapter", ""))
        collectors.append(cls(source, global_config))
    return collectors
