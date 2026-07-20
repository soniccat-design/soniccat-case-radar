#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import load_tasks


def main() -> int:
    load_tasks(ROOT / "config/tasks.yml")
    print("config_ok=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
