from __future__ import annotations

from typing import Any, Dict, List

from src.collectors.generic import GenericWebCollector
from src.models import Candidate


class WorldAthleticsCollector(GenericWebCollector):
    adapter_name = "world_athletics"

    def collect(self, category: Dict[str, Any], days: int) -> List[Candidate]:
        candidates = super().collect(category, days)
        for candidate in candidates:
            candidate.metadata["certification_hint"] = True
            candidate.source_type = "certification"
            candidate.source_priority = int(self.source_config.get("priority", 100))
        return candidates
