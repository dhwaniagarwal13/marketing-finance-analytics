"""
Analysis endpoints.

`/analysis` returns the full snapshot — the same payload the SSE stream pushes,
so the client has one shape to render whether it is following the live cursor
or looking at an uploaded dataset.

The per-module routes exist for parameter overrides: dragging the `shift_pct`
slider refetches only `/analysis/finance`, leaving the broadcast snapshot
untouched. That keeps server compute at one snapshot per tick no matter how
many clients are experimenting.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analytics import customers, experiments, finance, forecast, marketing
from analytics.marketing import GROUPABLE
from analytics.snapshot import build_snapshot, envelope, sanitize

from ..deps import BundleDep, ParamsDep

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _envelope(fn, bundle, params) -> dict:
    """Wrap a module the same way the snapshot does, plus the request context."""
    result = envelope(fn, bundle, params)
    result["as_of"] = str(bundle.max_date.date()) if bundle.max_date is not None else None
    result["params_hash"] = params.fingerprint()
    return sanitize(result)


@router.get("")
def analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    """Everything, in one call. Identical in shape to the SSE `snapshot` event."""
    return build_snapshot(bundle, params)


@router.get("/quality")
def quality(bundle: BundleDep) -> dict:
    """
    The data-quality audit for this dataset.

    On an upload this is the most useful page in the app: not "here is your
    ROAS" but "we dropped 11 of your transactions because they reference
    customer IDs that do not exist in your customer file, and here they are."
    """
    return sanitize({
        "status": "ok",
        "quality": bundle.quality.as_dict(),
        "provenance": {
            "source": bundle.provenance.source,
            "loaded_at": bundle.provenance.loaded_at,
            "rows_raw": bundle.provenance.rows_raw,
            "rows_clean": bundle.provenance.rows_clean,
        },
        "capabilities": bundle.capabilities.as_dict(),
    })


@router.get("/marketing")
def marketing_analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    return _envelope(marketing.build, bundle, params)


@router.get("/marketing/by")
def marketing_by_dimension(
    bundle: BundleDep,
    by: str = Query("channel", description=f"One of {', '.join(GROUPABLE)}"),
) -> dict:
    if by not in GROUPABLE:
        return sanitize({
            "status": "error",
            "reason": f"cannot group by {by!r}; expected one of {', '.join(GROUPABLE)}",
            "data": None,
        })
    table = marketing.groupby_kpis(bundle.campaigns, by)
    return sanitize({
        "status": "ok", "reason": None, "dimension": by,
        "data": table.reset_index().to_dict("records"),
    })


@router.get("/customers")
def customers_analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    return _envelope(customers.build, bundle, params)


@router.get("/finance")
def finance_analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    return _envelope(finance.build, bundle, params)


@router.get("/experiments")
def experiments_analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    return _envelope(experiments.build, bundle, params)


@router.get("/forecast")
def forecast_analysis(bundle: BundleDep, params: ParamsDep) -> dict:
    return _envelope(forecast.build, bundle, params)
