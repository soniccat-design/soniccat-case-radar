#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.publishing.site import build_site
from src.utils.config import load_tasks


def main() -> int:
    config = load_tasks(ROOT / "config/tasks.yml")
    output_dir = build_site(config)
    print("site_built=%s" % output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
