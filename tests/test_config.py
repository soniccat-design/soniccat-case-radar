from __future__ import annotations

import unittest
from pathlib import Path

from src.models import enabled_categories
from src.utils.config import load_tasks


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_tasks_config_validates(self) -> None:
        config = load_tasks(ROOT / "config/tasks.yml")
        self.assertEqual(config["project"]["name"], "SONIC CAT 专业鞋案例雷达")
        self.assertEqual(len(enabled_categories(config)), 3)

    def test_three_categories_daily_limit(self) -> None:
        config = load_tasks(ROOT / "config/tasks.yml")
        limits = {category["id"]: category["daily_limit"] for category in enabled_categories(config)}
        self.assertEqual(limits["professional-running"], 3)
        self.assertEqual(limits["running-outsole"], 3)
        self.assertEqual(limits["professional-spikes"], 3)


if __name__ == "__main__":
    unittest.main()
