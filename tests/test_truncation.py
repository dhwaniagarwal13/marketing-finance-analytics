"""
Truncation safety — the test that makes the replay cursor viable.

Every module runs against `bundle.as_of(cursor)`, which early in the replay
means three days of data, one campaign, and no A/B test at all. The contract:

    every module returns a valid result or a typed AnalysisError —
    never an unhandled exception, and never a NaN in a headline KPI.

Sweeping ~40 cursor positions turns what would otherwise be a week of
whack-a-mole (found one crash at a time as the cursor advances in front of a
viewer) into a single parametrized run.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from analytics.config import DEFAULTS
from analytics.errors import AnalysisError
from analytics.ingest import load_from_paths
from analytics.snapshot import MODULES, build_snapshot

# Dense early (where things break), sparse later (where they don't).
CURSORS = (
    [f"2024-02-{d:02d}" for d in (25, 26, 27, 28, 29)]
    + [f"2024-03-{d:02d}" for d in (1, 3, 5, 10, 20, 31)]
    + [f"2024-{m:02d}-15" for m in range(4, 13)]
    + [f"2025-{m:02d}-15" for m in range(1, 13)]
    + ["2025-12-30", "2025-12-31", "2026-06-30"]
)


@pytest.fixture(scope="module")
def bundle(project_root):
    return load_from_paths(project_root / "data" / "raw")


@pytest.mark.parametrize("cursor", CURSORS)
@pytest.mark.parametrize("module", sorted(MODULES))
def test_module_never_raises_an_untyped_error(bundle, cursor, module):
    sliced = bundle.as_of(cursor)
    try:
        MODULES[module](sliced, DEFAULTS)
    except AnalysisError:
        pass  # the contract: typed and reportable
    except Exception as exc:  # noqa: BLE001 — that is the thing under test
        pytest.fail(f"{module} at {cursor} raised {type(exc).__name__}: {exc}")


@pytest.mark.parametrize("cursor", CURSORS)
def test_snapshot_always_builds(bundle, cursor):
    """The SSE frame must be produced at every cursor position, degraded or not."""
    snap = build_snapshot(bundle.as_of(cursor), DEFAULTS, as_of=cursor)

    assert snap["as_of"]
    assert set(snap["modules"]) == set(MODULES)
    for name, env in snap["modules"].items():
        assert env["status"] in {"ok", "unavailable", "insufficient_data", "degraded"}, name
        if env["status"] != "ok":
            assert env["reason"], f"{name} failed without a reason"


@pytest.mark.parametrize("cursor", CURSORS)
def test_no_nan_in_headline_kpis(bundle, cursor):
    """
    A NaN reaching a KPI tile renders as the literal text 'NaN' on screen.

    Undefined is a legitimate state — ROAS before any paid spend, LTV:CAC when
    CAC is zero — so `None` is allowed and the client renders "n/a". What must
    never survive is a NaN float, because JSON cannot carry one.
    """
    snap = build_snapshot(bundle.as_of(cursor), DEFAULTS, as_of=cursor)
    env = snap["modules"]["finance"]
    if env["status"] != "ok":
        return

    for key, kpi in env["data"]["kpis"].items():
        value = kpi["value"]
        assert not (isinstance(value, float) and math.isnan(value)), f"{key} is NaN at {cursor}"


@pytest.mark.parametrize("cursor", ["2024-02-27", "2024-03-05", "2024-04-15"])
def test_early_cursor_degrades_rather_than_lying(bundle, cursor):
    """With days of history, forecasting must decline rather than extrapolate."""
    snap = build_snapshot(bundle.as_of(cursor), DEFAULTS, as_of=cursor)
    assert snap["modules"]["forecast"]["status"] == "insufficient_data"


def test_reallocation_guards_the_donor_recipient_overlap(bundle):
    """
    Before 2024-07-01 TikTok does not exist, so fewer elastic channels are
    present. `head(2)`/`tail(2)` would overlap on a short table and double-count
    a channel's spend; the guard must either widen the basis or decline.
    """
    from analytics import finance

    for cursor in ("2024-03-31", "2024-04-30", "2024-05-31", "2024-06-30"):
        sliced = bundle.as_of(cursor)
        try:
            table = finance.profitability(sliced, DEFAULTS)
            result = finance.reallocation(table, DEFAULTS)
        except AnalysisError:
            continue
        donors, recipients = set(result["from_channels"]), set(result["to_channels"])
        assert not donors & recipients, f"overlap at {cursor}: {donors & recipients}"


def test_converges_exactly_on_the_static_analysis(bundle, golden):
    """
    The claim the whole replay design rests on: when the cursor reaches the end
    of the data, the live app reproduces the notebooks and the PDF exactly.
    """
    from analytics import finance

    sliced = bundle.as_of("2025-12-31")
    kpis = finance.headline_kpis(sliced, DEFAULTS)
    expected = golden["generate_report"]["compute_kpis"]

    for key in ("total_revenue", "total_spend", "total_net_profit",
                "blended_cac", "blended_roas", "blended_roi", "blended_cvr"):
        assert kpis[key]["value"] == pytest.approx(expected[key], rel=1e-9), key


def test_cursor_past_the_end_is_stable(bundle):
    """Holding at the end of the replay must not change the numbers."""
    at_end = build_snapshot(bundle.as_of("2025-12-31"), DEFAULTS, as_of="2025-12-31")
    beyond = build_snapshot(bundle.as_of("2026-06-30"), DEFAULTS, as_of="2026-06-30")

    a = at_end["modules"]["finance"]["data"]["kpis"]["total_revenue"]["value"]
    b = beyond["modules"]["finance"]["data"]["kpis"]["total_revenue"]["value"]
    assert a == b


@pytest.mark.parametrize("cursor", ["2025-06-15", "2025-09-15", "2025-12-31"])
def test_snapshot_is_json_serializable(bundle, cursor):
    """
    NaN and Infinity are not valid JSON. `allow_nan=False` is what the SSE
    encoder will use, so anything non-finite must be caught here rather than
    breaking the stream in production.
    """
    import json

    snap = build_snapshot(bundle.as_of(cursor), DEFAULTS, as_of=cursor)
    try:
        json.dumps(snap, allow_nan=False, default=str)
    except ValueError as exc:
        pytest.fail(f"snapshot at {cursor} is not JSON-safe: {exc}")
