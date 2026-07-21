from __future__ import annotations

import unittest
import time
from pathlib import Path

from src.collectors.http import extract_page_metadata
from src.models import Candidate, SourceHealth
from src.pipeline import collect_from_sources


ROOT = Path(__file__).resolve().parents[1]


class CollectorTests(unittest.TestCase):
    def test_html_fixture_metadata(self) -> None:
        html = (ROOT / "tests/fixtures/html/product_page.html").read_text(encoding="utf-8")
        meta = extract_page_metadata("https://example.com/products/carbon", html)
        self.assertEqual(meta["title"], "Elite carbon plated running shoes")
        self.assertTrue(meta["image_url"].endswith("/images/carbon-runner.jpg"))

    def test_single_source_failure_does_not_block(self) -> None:
        class FailingCollector:
            def safe_collect(self, category, days):
                return [], SourceHealth("bad", "media", "failed", category=category["id"], message="boom")

        class GoodCollector:
            def safe_collect(self, category, days):
                return [
                    Candidate(
                        category=category["id"],
                        title="carbon plated running shoes",
                        source_url="https://example.com/a",
                        source_domain="example.com",
                        source_type="media",
                        image_url="https://example.com/a.jpg",
                    )
                ], SourceHealth("good", "media", "ok", category=category["id"], candidates=1)

        candidates, health = collect_from_sources({"id": "professional-running"}, [FailingCollector(), GoodCollector()], 365)
        self.assertEqual(len(candidates), 1)
        self.assertEqual([item.status for item in health], ["failed", "ok"])

    def test_source_timeout_does_not_block_following_sources(self) -> None:
        class HangingCollector:
            source_id = "slow"
            source_type = "media"
            source_config = {}

            def safe_collect(self, category, days):
                time.sleep(5)
                return [], SourceHealth("slow", "media", "ok", category=category["id"])

        class GoodCollector:
            source_id = "good"
            source_type = "media"
            source_config = {}

            def safe_collect(self, category, days):
                return [
                    Candidate(
                        category=category["id"],
                        title="carbon plated running shoes",
                        source_url="https://example.com/a",
                        source_domain="example.com",
                        source_type="media",
                        image_url="https://example.com/a.jpg",
                    )
                ], SourceHealth("good", "media", "ok", category=category["id"], candidates=1)

        started = time.monotonic()
        candidates, health = collect_from_sources(
            {"id": "professional-running"},
            [HangingCollector(), GoodCollector()],
            365,
            deadline=time.monotonic() + 5,
            max_source_seconds=1,
        )
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(len(candidates), 1)
        self.assertEqual([item.status for item in health], ["failed", "ok"])
        self.assertIn("exceeded runtime budget", health[0].message)


if __name__ == "__main__":
    unittest.main()
