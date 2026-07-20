#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import run_daily, summary_markdown
from src.utils.config import load_tasks


def main() -> int:
    config = load_tasks(ROOT / "config/tasks.yml")
    summary = run_daily(config, ROOT, build=True)
    markdown = summary_markdown(summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(markdown)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write("publish_allowed=%s\n" % ("true" if summary.get("publish_allowed") else "false"))
            handle.write("selected_total=%s\n" % summary.get("selected_total", 0))
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
