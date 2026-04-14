import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def _default_platform_tests_to_local_analyzer(monkeypatch):
    monkeypatch.setenv("ANALYZER_MODE", "local")
