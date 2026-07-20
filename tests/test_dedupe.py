from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.dedupe.dedupe import dedupe_image_hashes, dedupe_recent_models, dedupe_urls
from src.models import Candidate
from src.utils.text import normalize_model_name


def candidate(url: str, image_hash: str = "", model: str = "Nike Vaporfly 4 Running Shoes") -> Candidate:
    return Candidate(
        category="professional-running",
        title=model,
        source_url=url,
        source_domain="example.com",
        source_type="media",
        image_url=url + ".jpg",
        image_hash=image_hash,
        normalized_model_name=normalize_model_name(model),
    )


class DedupeTests(unittest.TestCase):
    def test_url_dedupe(self) -> None:
        rows = dedupe_urls([candidate("https://example.com/a"), candidate("https://example.com/a#x"), candidate("https://example.com/b")])
        self.assertEqual(len(rows), 2)

    def test_image_hash_dedupe(self) -> None:
        rows = dedupe_image_hashes(
            [
                candidate("https://example.com/a", "ff00ff00ff00ff00"),
                candidate("https://example.com/b", "ff00ff00ff00ff01"),
                candidate("https://example.com/c", "0000000000000000"),
            ],
            max_distance=2,
        )
        self.assertEqual([row.source_url for row in rows], ["https://example.com/a", "https://example.com/c"])

    def test_model_normalization(self) -> None:
        self.assertEqual(normalize_model_name("Nike Vaporfly 4 Men's Running Shoes Review"), "nike vaporfly 4")

    def test_30_day_category_model_dedupe(self) -> None:
        existing = [
            {
                "category": "professional-running",
                "normalized_model_name": "nike vaporfly 4",
                "published_at": "2026-07-10T08:00:00+08:00",
                "visible": True,
            }
        ]
        rows = dedupe_recent_models(
            [candidate("https://example.com/new", model="Nike Vaporfly 4")],
            existing,
            "professional-running",
            30,
            datetime(2026, 7, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
