from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ai.reasoner import ReasonGenerator
from src.models import Candidate
from src.pipeline import prepare_candidates, run_category
from src.publishing.site import build_site
from src.utils.config import load_tasks


ROOT = Path(__file__).resolve().parents[1]
TARGET_SITE_URL = "https://soniccat-design.github.io/soniccat-case-radar/"
TARGET_BASE_PATH = "/soniccat-case-radar/"
OLD_REPO_MARKERS = (
    "liyulin040520" + "-hue",
    "sonic-cat" + "-anli",
    "liyulin040520" + "-hue.github.io",
    "/sonic-cat" + "-anli/",
)


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

        def prepared_side_effect(candidates, category, config, existing, blocked, days, **kwargs):
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
            selected, health, used_fallback, stats = run_category(
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
        self.assertEqual(stats["filtered_candidates"], 3)

    def test_prepare_candidates_limits_image_checks(self) -> None:
        category = {"id": "professional-running", "name": "专业跑鞋案例", "keywords_en": ["running shoes"], "keywords_zh": []}
        config = {
            "global": {
                "run": {"max_image_checks_per_category": 2, "max_seconds_per_image": 1},
                "image": {"request_timeout_seconds": 10, "min_width": 500, "min_height": 500},
                "dedupe": {"perceptual_hash_max_distance": 6, "category_model_window_days": 30},
                "candidate_limits": {"max_per_category": 50},
            }
        }
        candidates = [
            Candidate(
                category="professional-running",
                title="carbon running shoes %s" % index,
                source_url="https://example.com/%s" % index,
                source_domain="example.com",
                source_type="media",
                image_url="https://example.com/%s.jpg" % index,
                normalized_model_name="model %s" % index,
            )
            for index in range(5)
        ]
        with patch("src.pipeline.download_image_bytes", return_value=b"image") as mocked_download, patch(
            "src.pipeline.inspect_image_bytes",
            side_effect=[
                {"ok": True, "width": 900, "height": 900, "clarity": 120.0, "image_hash": "0000000000000001"},
                {"ok": True, "width": 900, "height": 900, "clarity": 120.0, "image_hash": "ffffffffffffffff"},
            ],
        ):
            prepared = prepare_candidates(candidates, category, config, [], {}, 365)

        self.assertEqual(mocked_download.call_count, 2)
        self.assertEqual(len(prepared), 2)

    def test_site_generation_and_no_source_url_leak(self) -> None:
        config = load_tasks(ROOT / "config/tasks.yml")
        output = build_site(config)
        self.assertTrue((output / "index.html").exists())
        self.assertTrue((output / "professional-running/index.html").exists())
        self.assertTrue((output / "running-outsole/index.html").exists())
        self.assertTrue((output / "professional-spikes/index.html").exists())
        self.assertTrue((output / "sitemap.xml").exists())
        self.assertTrue((output / "robots.txt").exists())
        public_data = json.loads((output / "data/cases.json").read_text(encoding="utf-8"))
        self.assertTrue(public_data)
        self.assertNotIn("source_url", public_data[0])
        combined_html = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*.html"))
        generated_text = combined_html
        generated_text += "\n" + (output / "sitemap.xml").read_text(encoding="utf-8")
        generated_text += "\n" + (output / "robots.txt").read_text(encoding="utf-8")
        self.assertIn('rel="canonical" href="%s"' % TARGET_SITE_URL, combined_html)
        self.assertIn('property="og:url" content="%s"' % TARGET_SITE_URL, combined_html)
        self.assertIn(TARGET_SITE_URL + "professional-running/", generated_text)
        self.assertIn("Allow: %s" % TARGET_BASE_PATH, generated_text)
        self.assertNotIn("example.invalid/internal", combined_html)
        self.assertNotIn("source_url", combined_html)
        for marker in OLD_REPO_MARKERS:
            self.assertNotIn(marker, generated_text)


if __name__ == "__main__":
    unittest.main()
