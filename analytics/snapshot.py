"""
One call, one payload: everything the dashboard renders at a point in time.

Each module is wrapped in a uniform envelope so the frontend has a single code
path for "worked", "this dataset can't support it", and "not enough history
yet". A module that raises is reported, never propagated — a missing
transactions file should grey out three cards, not 500 the request.

This is also the SSE frame. The tick loop calls `build_snapshot` on a sliced
bundle and broadcasts the result verbatim.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd

from . import customers, experiments, finance, forecast, marketing
from .config import DEFAULTS, AnalysisParams
from .errors import AnalysisError

MODULES = {
    "marketing": marketing.build,
    "customers": customers.build,
    "finance": finance.build,
    "experiments": experiments.build,
    "forecast": forecast.build,
}


def sanitize(value):
    """
    Make a payload JSON-safe by turning non-finite floats into null.

    Undefined metrics are real and common — ROAS for Organic (no spend),
    LTV:CAC before any paid acquisition — and pandas represents them as NaN.
    JSON has no NaN or Infinity literal, so `json.dumps(..., allow_nan=False)`
    would raise and `allow_nan=True` would emit bare `NaN` tokens that
    `JSON.parse` rejects. Either way the stream breaks.

    Converting at this boundary keeps NaN semantics inside the engine, where
    they are correct, and gives the client `null`, which it can render as "n/a".
    """
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if value is pd.NaT:
        return None
    return value


def envelope(fn, bundle, params: AnalysisParams) -> dict:
    """Run one module, capturing typed failures as status rather than exceptions."""
    started = time.perf_counter()
    try:
        data = fn(bundle, params)
        status, reason, extra = "ok", None, {}
    except AnalysisError as exc:
        data = None
        payload = exc.as_dict()
        status = payload.pop("status")
        reason = payload.pop("reason")
        extra = payload

    return {
        "status": status,
        "reason": reason,
        "computed_ms": round((time.perf_counter() - started) * 1000, 1),
        "data": data,
        **extra,
    }


def build_snapshot(bundle, params: AnalysisParams = DEFAULTS,
                   as_of: pd.Timestamp | None = None) -> dict:
    """Compute every module against `bundle` and return the full payload."""
    started = time.perf_counter()
    cursor = pd.Timestamp(as_of) if as_of is not None else bundle.max_date

    modules = {name: envelope(fn, bundle, params) for name, fn in MODULES.items()}

    return sanitize({
        "as_of": str(cursor.date()) if cursor is not None else None,
        "params_hash": params.fingerprint(),
        "capabilities": bundle.capabilities.as_dict(),
        "quality": bundle.quality.as_dict(),
        "provenance": {
            "source": bundle.provenance.source,
            "rows_raw": bundle.provenance.rows_raw,
            "rows_clean": bundle.provenance.rows_clean,
        },
        "coverage": {
            "months_of_history": bundle.months_of_history,
            "max_date": str(bundle.max_date.date()) if bundle.max_date is not None else None,
        },
        "modules": modules,
        "computed_ms": round((time.perf_counter() - started) * 1000, 1),
    })
