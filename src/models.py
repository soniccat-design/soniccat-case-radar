from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Candidate:
    category: str
    title: str
    source_url: str
    source_domain: str
    source_type: str
    image_url: str = ""
    model_name: str = ""
    summary: str = ""
    published_at: str = ""
    captured_at: str = ""
    source_id: str = ""
    source_priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)
    image_bytes: Optional[bytes] = None
    image_width: int = 0
    image_height: int = 0
    image_hash: str = ""
    content_hash: str = ""
    normalized_model_name: str = ""
    score: float = 0.0
    reason: str = ""

    def to_case_record(self, case_id: str, image_path: str, published_at: str) -> Dict[str, Any]:
        return {
            "id": case_id,
            "category": self.category,
            "image_path": image_path,
            "reason": self.reason,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "model_name": self.model_name or self.title,
            "normalized_model_name": self.normalized_model_name,
            "title": self.title,
            "image_hash": self.image_hash,
            "content_hash": self.content_hash,
            "score": round(float(self.score), 2),
            "captured_at": self.captured_at,
            "published_at": published_at,
            "visible": True,
        }


@dataclass
class SourceHealth:
    source_id: str
    source_type: str
    status: str
    category: str = ""
    domain: str = ""
    candidates: int = 0
    filtered_remaining: int = 0
    filtered_out: int = 0
    selected: int = 0
    window_days: int = 0
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "status": self.status,
            "category": self.category,
            "domain": self.domain,
            "candidates": self.candidates,
            "filtered_remaining": self.filtered_remaining,
            "filtered_out": self.filtered_out,
            "selected": self.selected,
            "window_days": self.window_days,
            "message": self.message,
        }


def public_case(case: Dict[str, Any], category_name: str = "") -> Dict[str, Any]:
    """Return only fields allowed to reach the frontend."""
    return {
        "id": case.get("id", ""),
        "category": case.get("category", ""),
        "category_name": category_name or case.get("category_name", ""),
        "image_path": case.get("image_path", ""),
        "reason": case.get("reason", ""),
    }


def category_map(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in config.get("categories", []) if item.get("enabled", True)}


def enabled_categories(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in config.get("categories", []) if item.get("enabled", True)]
