"""Shared request dependencies: dataset lookup, cursor parsing, param overrides."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, HTTPException, Query, Request

from analytics.config import DEFAULTS, AnalysisParams
from analytics.ingest import DatasetBundle

from .store import DatasetNotFound, DatasetStore


def get_store(request: Request) -> DatasetStore:
    return request.app.state.store


def get_bundle(
    request: Request,
    dataset: Annotated[str, Query(description="Dataset id; 'demo' is the built-in one")] = "demo",
    as_of: Annotated[date | None, Query(description="Cursor date; defaults to all data")] = None,
) -> DatasetBundle:
    """Resolve `?dataset=` and apply `?as_of=`, so every analysis route is one line."""
    try:
        bundle = get_store(request).get(dataset)
    except DatasetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown dataset '{dataset}'. It may have expired — uploads are kept "
                   f"for 30 minutes of inactivity.",
        ) from None

    return bundle.as_of(pd.Timestamp(as_of)) if as_of is not None else bundle


def get_params(
    # temporal
    reference_date: date | None = None,
    # rfm / customers
    rfm_bins: Annotated[int, Query(ge=2, le=10)] = DEFAULTS.rfm_bins,
    include_refunds_in_rfm: bool = DEFAULTS.include_refunds_in_rfm,
    include_refunds_in_cohorts: bool = DEFAULTS.include_refunds_in_cohorts,
    cohort_min_size: Annotated[int, Query(ge=0)] = DEFAULTS.cohort_min_size,
    # finance
    shift_pct: Annotated[float, Query(ge=0.0, le=1.0)] = DEFAULTS.shift_pct,
    n_donors: Annotated[int, Query(ge=1, le=6)] = DEFAULTS.n_donors,
    n_recipients: Annotated[int, Query(ge=1, le=6)] = DEFAULTS.n_recipients,
    elastic: Annotated[str | None, Query(description="Comma-separated channel names")] = None,
    ltv_denominator: Literal["all_customers", "transacting_customers"] = DEFAULTS.ltv_denominator,
    ltv_cac_benchmark: Annotated[float, Query(gt=0)] = DEFAULTS.ltv_cac_benchmark,
    # experiments
    alpha: Annotated[float, Query(gt=0, lt=1)] = DEFAULTS.alpha,
    # forecast
    holdout_months: Annotated[int, Query(ge=1, le=12)] = DEFAULTS.holdout_months,
    forecast_horizon: Annotated[int, Query(ge=1, le=24)] = DEFAULTS.forecast_horizon,
    drop_partial_trailing_month: bool = DEFAULTS.drop_partial_trailing_month,
) -> AnalysisParams:
    """
    Build `AnalysisParams` from the query string.

    Bounds live in the annotations so FastAPI rejects nonsense with a 422 before
    any pandas runs — `rfm_bins=10000` should not become a slow qcut.
    """
    overrides: dict = dict(
        reference_date=reference_date,
        rfm_bins=rfm_bins,
        include_refunds_in_rfm=include_refunds_in_rfm,
        include_refunds_in_cohorts=include_refunds_in_cohorts,
        cohort_min_size=cohort_min_size,
        shift_pct=shift_pct,
        n_donors=n_donors,
        n_recipients=n_recipients,
        ltv_denominator=ltv_denominator,
        ltv_cac_benchmark=ltv_cac_benchmark,
        alpha=alpha,
        holdout_months=holdout_months,
        forecast_horizon=forecast_horizon,
        drop_partial_trailing_month=drop_partial_trailing_month,
    )
    if elastic:
        channels = tuple(c.strip() for c in elastic.split(",") if c.strip())
        if channels:
            overrides["elastic_paid_channels"] = channels

    return replace(DEFAULTS, **overrides)


BundleDep = Annotated[DatasetBundle, Depends(get_bundle)]
ParamsDep = Annotated[AnalysisParams, Depends(get_params)]
StoreDep = Annotated[DatasetStore, Depends(get_store)]
