#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if REPO_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, REPO_ROOT.as_posix())

from app.services.trend_enhancement_service import run_trend_enhancement


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the status-analysis-driven trend enhancement subchain.",
    )
    parser.add_argument("report_md", help="Path to the cleaned status analysis markdown report.")
    parser.add_argument(
        "--docx",
        dest="base_docx",
        help="Optional base docx report for appendix augmentation.",
    )
    args = parser.parse_args()

    artifacts = run_trend_enhancement(
        Path(args.report_md).expanduser().resolve(),
        base_report_docx_path=(Path(args.base_docx).expanduser().resolve() if args.base_docx else None),
    )
    print(json.dumps(artifacts.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
