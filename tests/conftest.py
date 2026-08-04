"""Shared fixtures. Makes both `src/` and the repo root importable from tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "golden" / "expected.json"

for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def golden() -> dict:
    """The Phase 0 baseline: what the notebooks and PDF produced before any refactor."""
    if not GOLDEN_PATH.exists():
        pytest.skip("golden baseline missing — run tests/golden/capture_golden.py")
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
