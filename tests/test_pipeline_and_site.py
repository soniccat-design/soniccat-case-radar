from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ai.reasoner import ReasonGenerator
from src.models import Candidate
from src.pipeline import run_category
from src.publishing.site import build_site
from src.utils.config import load_tasks


ROOT = Path(__file__).resolve().parents[1]


class PipelineAndSiteTests(unittest.TestCase):
    def test_near_year_shortage_extends_three_years(self) -> None:
        category = {"id": "professional-running", "name": "专业跑鞋案例", "daily_limit": 3, "keywords_en": ["running shoes"], "keywords_zh": []}
        config = {
            "global": {
                "image": {"request_timeout_seconds": 1, "max_long_edge": 1400, "target_max_kb": 250},
                "dedupe": {"perceptual_hash_max_distance": 6, "category_model_window_days": 30},
                "scoring": {"relevance": 40, "image_quality": 25, "freshness": 20, "source_trust": 15},
            }
        }
        collectors = []
        reasoner = Mock(spec=ReasonGenerator)
        reasoner.generate.return_value = "中底侧墙上扬与鞋面压线形成清楚推进节奏"

        def prepared_side_effect(candidates, category, config, existing, blocked, days):
            count = 2 if days == 365 else 3
            return [
                Candidate(
                    category="professional-running",
                    title="carbon running shoes %s" % index,
                    source_url="https://example.com/%s" % index,
                    source_domain="example.com",
                    source_type="media",
                    image_url="https://example.com/%s.jpg" % index,
                    image_width=1000,
                    image_height=1000,
                    image_hash="%016x" % index,
                    content_hash="%02x" % index,
                    normalized_model_name="model %s" % index,
                    image_bytes=b"fake",
                )
                for index in range(count)
            ]

        with patch("src.pipeline.collect_from_sources", side_effect=[([], []), ([], [])]), patch(
            "src.pipeline.prepare_candidates", side_effect=prepared_side_effect
        ), patch("src.pipeline.save_webp", return_value=ROOT / "case_assets/cases/fake.webp"):
            selected, health, used_fallback = run_category(
                category,
                config,
                collectors,
                [],
                {},
                ROOT / "case_assets",
                reasoner,
                365,
                1095,
            )
        self.assertTrue(used_fallback)
        self.assertEqual(len(selected), 3)

    def test_site_generation_and_no_source_url_leak(self) -> None:
        config = load_tasks(ROOT / "config/tasks.yml")
        output = build_site(config)
        self.assertTrue((output / "index.html").exists())
        self.assertTrue((output / "professional-running/index.html").exists())
        public_data = json.loads((output / "data/cases.json").read_text(encoding="utf-8"))
        self.assertTrue(public_data)
        self.assertNotIn("source_url", public_data[0])
        combined_html = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*.html"))
        self.assertNotIn("example.invalid/internal", combined_html)
        self.assertNotIn("source_url", combined_html)


if __name__ == "__main__":
    unittest.main()
