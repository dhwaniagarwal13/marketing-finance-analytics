"""Health, theme tokens, and the parameter schema that drives the UI controls."""

from __future__ import annotations

import os
import time
from dataclasses import fields

from fastapi import APIRouter, Request

from analytics.config import DEFAULTS, AnalysisParams
from analytics.palette import as_theme_dict

from ..settings import get_settings

router = APIRouter(tags=["meta"])
STARTED = time.monotonic()


@router.get("/health")
def health(request: Request) -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.version,
        "git_sha": os.getenv("GIT_SHA", "dev"),
        "uptime_s": round(time.monotonic() - STARTED, 1),
        "datasets_loaded": request.app.state.store.size,
    }


@router.get("/theme")
def theme() -> dict:
    """
    Colour tokens, served from the same source the notebooks use.

    The frontend compiles these into `theme.generated.ts` at build time rather
    than fetching at runtime, so a chart never renders before its palette
    arrives. This endpoint is what that build step reads.
    """
    return as_theme_dict()


@router.get("/params/schema")
def params_schema() -> dict:
    """
    Field-by-field description of `AnalysisParams`.

    The UI builds its controls from this rather than hardcoding a form, so a
    new analysis parameter shows up in the interface without frontend work.
    """
    out = []
    for f in fields(AnalysisParams):
        default = getattr(DEFAULTS, f.name)
        out.append({
            "name": f.name,
            "type": str(f.type),
            "default": list(default) if isinstance(default, tuple) else default,
            "group": _group_for(f.name),
        })
    return {"fields": out, "params_hash": DEFAULTS.fingerprint()}


def _group_for(name: str) -> str:
    if name.startswith("churn"):
        return "ml"
    if name.startswith(("forecast", "holdout", "arima", "ma_", "drop_partial")):
        return "forecast"
    if name.startswith(("alpha", "ab_")):
        return "experiments"
    if name.startswith(("elastic", "shift", "n_donors", "n_recipients", "ltv")):
        return "finance"
    if name.startswith(("rfm", "segment", "cohort", "channel_retention", "include_refunds")):
        return "customers"
    return "temporal"
