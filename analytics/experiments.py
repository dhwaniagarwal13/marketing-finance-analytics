"""
A/B test analysis — notebook 05.

Two independent tests on the same experiment, which is the point: a
two-proportion z-test on pooled conversions, and Welch's t-test on the 30 daily
conversion rates. Agreement between a pooled test and a daily-variance test is
much stronger evidence than either alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from .config import DEFAULTS, AnalysisParams
from .errors import InsufficientData, require
from .formulas import safe_divide

CONTROL, TREATMENT = "A", "B"


def ab_test(ab: pd.DataFrame, params: AnalysisParams = DEFAULTS) -> dict:
    """
    Compare the two creative variants.

    Returns `status="insufficient_data"` rather than NaN statistics when a
    variant has no traffic yet — which is the normal state early in the replay,
    since the experiment does not start until 2025-09-01.
    """
    summary = ab.groupby("variant").agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        conversions=("conversions", "sum"),
        revenue=("revenue", "sum"),
        spend=("spend", "sum"),
    )

    missing = [v for v in (CONTROL, TREATMENT) if v not in summary.index]
    if missing:
        raise InsufficientData(
            "ab_test", need=f"both variants {CONTROL} and {TREATMENT}",
            have=f"only {', '.join(summary.index) or 'none'}",
        )

    if (summary["clicks"] <= 0).any():
        raise InsufficientData(
            "ab_test", need="clicks in both variants",
            have=f"A={int(summary.loc[CONTROL, 'clicks'])}, "
                 f"B={int(summary.loc[TREATMENT, 'clicks'])}",
        )

    summary["cvr"] = safe_divide(summary["conversions"], summary["clicks"])
    summary["roas"] = safe_divide(summary["revenue"], summary["spend"])

    cvr_a = float(summary.loc[CONTROL, "cvr"])
    cvr_b = float(summary.loc[TREATMENT, "cvr"])

    # Treatment first: the one-sided alternative asks whether B beats A.
    count = np.array([summary.loc[TREATMENT, "conversions"], summary.loc[CONTROL, "conversions"]])
    nobs = np.array([summary.loc[TREATMENT, "clicks"], summary.loc[CONTROL, "clicks"]])

    z_stat, p_value_z = proportions_ztest(count, nobs, alternative="larger")
    ci_low, ci_high = confint_proportions_2indep(
        count[0], nobs[0], count[1], nobs[1], method="wald")

    daily = ab.assign(cvr=safe_divide(ab["conversions"], ab["clicks"]))
    daily_a = daily.loc[daily["variant"] == CONTROL, "cvr"].dropna()
    daily_b = daily.loc[daily["variant"] == TREATMENT, "cvr"].dropna()

    if len(daily_a) < 2 or len(daily_b) < 2:
        t_stat = p_value_t = float("nan")
    else:
        t_stat, p_value_t = stats.ttest_ind(
            daily_b, daily_a, equal_var=False, alternative="greater")

    significant = bool(p_value_t < params.alpha) if not np.isnan(p_value_t) else False

    return {
        "status": "ok",
        "cvr_a": cvr_a,
        "cvr_b": cvr_b,
        "lift_pct": safe_divide(cvr_b - cvr_a, cvr_a),
        "z_stat": float(z_stat),
        "p_value_z": float(p_value_z),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "ci_excludes_zero": bool(ci_low > 0),
        "t_stat": float(t_stat),
        "p_value_t": float(p_value_t),
        "alpha": params.alpha,
        "significant": significant,
        "n_days": int(min(len(daily_a), len(daily_b))),
        "summary": summary.reset_index().to_dict("records"),
        "projection": _business_projection(summary),
    }


def _business_projection(summary: pd.DataFrame) -> dict:
    """
    What rolling B out to A's spend would be worth over the same 30-day window.

    Holds A's cost-per-click constant and re-prices its traffic at B's
    conversion rate — a spend-neutral rollout, not an increase.
    """
    spend_a = float(summary.loc[CONTROL, "spend"])
    clicks_a = float(summary.loc[CONTROL, "clicks"])
    conversions_a = float(summary.loc[CONTROL, "conversions"])
    cpc_a = safe_divide(spend_a, clicks_a)

    if not cpc_a or np.isnan(cpc_a):
        return {"available": False, "reason": "variant A has no cost-per-click"}

    projected = safe_divide(spend_a, cpc_a) * float(summary.loc[TREATMENT, "cvr"])
    incremental = projected - conversions_a
    revenue_per_conversion = safe_divide(
        summary.loc[TREATMENT, "revenue"], summary.loc[TREATMENT, "conversions"])

    return {
        "available": True,
        "basis": "variant A's spend, held constant, converting at variant B's rate",
        "current_conversions": conversions_a,
        "projected_conversions": float(projected),
        "incremental_conversions": float(incremental),
        "incremental_revenue": float(incremental * revenue_per_conversion),
        "period_days": 30,
    }


def build(bundle, params: AnalysisParams = DEFAULTS) -> dict:
    require(bundle, "experiments", "ab_test")
    return ab_test(bundle.ab_test, params)
