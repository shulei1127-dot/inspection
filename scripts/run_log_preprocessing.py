#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if REPO_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, REPO_ROOT.as_posix())

from app.services.log_preprocessing_service import run_log_preprocessing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full-log preprocessing layer and generate status_analysis.md.",
    )
    parser.add_argument("analysis_dir", help="Path to the extracted full-log directory.")
    args = parser.parse_args()

    artifacts = run_log_preprocessing(Path(args.analysis_dir).expanduser().resolve())
    print(json.dumps(artifacts.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
