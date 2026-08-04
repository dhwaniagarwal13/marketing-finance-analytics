"""
Purity — why one user's upload cannot corrupt another's data.

Every engine function takes DataFrames and returns values. None of them writes
back. Isolation between the demo dataset and uploaded ones therefore comes from
the shape of the code, not from defensive copying at the API layer.

That is a strong claim, so it is checked rather than asserted: hash every input
frame before and after each call and require the hashes to match.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics import customers, experiments, finance, forecast, marketing
from analytics.config import DEFAULTS
from analytics.errors import AnalysisError
from analytics.ingest import load_from_paths
from analytics.snapshot import MODULES, build_snapshot


def fingerprint(bundle) -> dict[str, str]:
    return {
        name: pd.util.hash_pandas_object(df, index=True).sum()
        for name, df in bundle.tables.items()
    }


@pytest.fixture(scope="function")
def bundle(project_root):
    return load_from_paths(project_root / "data" / "raw")


@pytest.mark.parametrize("module", sorted(MODULES))
def test_module_does_not_mutate_its_inputs(bundle, module):
    before = fingerprint(bundle)
    try:
        MODULES[module](bundle, DEFAULTS)
    except AnalysisError:
        pass
    assert fingerprint(bundle) == before


def test_full_snapshot_does_not_mutate_its_inputs(bundle):
    before = fingerprint(bundle)
    build_snapshot(bundle, DEFAULTS)
    assert fingerprint(bundle) == before


def test_repeated_calls_are_identical(bundle):
    """No hidden state: the same inputs must give the same answer every time."""
    first = finance.profitability(bundle, DEFAULTS)
    second = finance.profitability(bundle, DEFAULTS)
    pd.testing.assert_frame_equal(first, second)


def test_slicing_does_not_mutate_the_parent(bundle):
    before = fingerprint(bundle)
    sliced = bundle.as_of("2024-09-30")
    build_snapshot(sliced, DEFAULTS)
    assert fingerprint(bundle) == before
    assert len(sliced.campaigns) < len(bundle.campaigns)


def test_two_bundles_are_independent(project_root):
    """
    The isolation guarantee, end to end.

    Analysing one dataset — including a mutating operation on a slice of it —
    must leave a second, separately loaded dataset bit-identical.
    """
    a = load_from_paths(project_root / "data" / "raw")
    b = load_from_paths(project_root / "data" / "raw")
    before_b = fingerprint(b)

    build_snapshot(a.as_of("2025-06-30"), DEFAULTS)
    a.campaigns.loc[a.campaigns.index[:10], "spend"] = -999

    assert fingerprint(b) == before_b


def test_params_are_immutable():
    """`AnalysisParams` doubles as a cache key, so it must not be editable."""
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        DEFAULTS.shift_pct = 0.5  # type: ignore[misc]


def test_params_fingerprint_tracks_changes():
    from dataclasses import replace

    assert DEFAULTS.fingerprint() == DEFAULTS.fingerprint()
    assert replace(DEFAULTS, shift_pct=0.25).fingerprint() != DEFAULTS.fingerprint()
