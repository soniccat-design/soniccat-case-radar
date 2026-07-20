from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from src.models import Candidate, SourceHealth


class BaseCollector(ABC):
    adapter_name = "base"

    def __init__(self, source_config: Dict[str, Any], global_config: Dict[str, Any]) -> None:
        self.source_config = source_config
        self.global_config = global_config
        self.source_id = source_config.get("id", self.adapter_name)
        self.source_type = source_config.get("type", self.adapter_name)

    def safe_collect(self, category: Dict[str, Any], days: int) -> Tuple[List[Candidate], SourceHealth]:
        if category.get("id") not in self.source_config.get("use_for", [category.get("id")]):
            return [], SourceHealth(self.source_id, self.source_type, "skipped", category=category.get("id", ""))
        try:
            candidates = self.collect(category, days)
            return candidates, SourceHealth(
                self.source_id,
                self.source_type,
                "ok",
                category=category.get("id", ""),
                candidates=len(candidates),
            )
        except Exception as exc:
            return [], SourceHealth(
                self.source_id,
                self.source_type,
                "failed",
                category=category.get("id", ""),
                message=str(exc)[:400],
            )

    @abstractmethod
    def collect(self, category: Dict[str, Any], days: int) -> List[Candidate]:
        raise NotImplementedError
