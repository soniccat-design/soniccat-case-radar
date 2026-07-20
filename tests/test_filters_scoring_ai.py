from __future__ import annotations

import os
import unittest

from src.ai.reasoner import ReasonGenerator
from src.filters.rules import basic_candidate_filter
from src.models import Candidate
from src.scoring.scorer import score_and_sort


class FilterScoringAiTests(unittest.TestCase):
    def test_image_size_filter(self) -> None:
        candidate = Candidate(
            category="professional-running",
            title="carbon plated running shoes",
            source_url="https://example.com/a",
            source_domain="example.com",
            source_type="media",
            image_url="https://example.com/a.jpg",
            image_width=300,
            image_height=800,
        )
        ok, reason = basic_candidate_filter(candidate, {"id": "professional-running", "keywords_en": ["running shoes"]}, {"min_width": 500, "min_height": 500})
        self.assertFalse(ok)
        self.assertEqual(reason, "image width too small")

    def test_scoring_sort(self) -> None:
        category = {"id": "professional-running", "keywords_en": ["carbon plated running shoes"], "keywords_zh": []}
        high = Candidate(
            category="professional-running",
            title="carbon plated marathon racing running shoes",
            source_url="https://trusted.example/a",
            source_domain="trusted.example",
            source_type="brand",
            image_url="https://trusted.example/a.jpg",
            image_width=1400,
            image_height=1000,
            published_at="2026-07-01T00:00:00+08:00",
            source_priority=100,
        )
        low = Candidate(
            category="professional-running",
            title="daily running shoes",
            source_url="https://media.example/b",
            source_domain="media.example",
            source_type="media",
            image_url="https://media.example/b.jpg",
            image_width=600,
            image_height=600,
            published_at="2024-01-01T00:00:00+08:00",
            source_priority=50,
        )
        rows = score_and_sort([low, high], category, {"relevance": 40, "image_quality": 25, "freshness": 20, "source_trust": 15}, 365)
        self.assertIs(rows[0], high)
        self.assertGreater(rows[0].score, rows[1].score)

    def test_ai_failure_fallback(self) -> None:
        for key in ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL"):
            os.environ.pop(key, None)
        config = {"global": {"ai": {"enabled": True, "default_env_keys": {}}, "reason": {"min_cn_chars": 20, "max_cn_chars": 40}}}
        reasoner = ReasonGenerator(config)
        candidate = Candidate(
            category="running-outsole",
            title="carbon running shoe outsole",
            source_url="https://example.com/a",
            source_domain="example.com",
            source_type="media",
            image_url="https://example.com/a.jpg",
            content_hash="a1",
        )
        reason = reasoner.generate(candidate, {"id": "running-outsole", "keywords_zh": ["跑鞋底片"]})
        self.assertGreaterEqual(len([char for char in reason if "\u4e00" <= char <= "\u9fff"]), 20)


if __name__ == "__main__":
    unittest.main()
