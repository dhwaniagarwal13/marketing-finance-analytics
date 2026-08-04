"""
Funnel and dimensional performance — notebook 02.

`groupby_kpis` generalizes NB02's `channel_kpis`, which was already being
reused for other dimensions via a workaround:

    channel_kpis(campaigns.assign(channel=campaigns["device"]))

Passing the dimension as an argument does the same thing without the rename,
and extends to objective/audience for free.
"""

from __future__ import annotations

import pandas as pd

from .config import DEFAULTS, AnalysisParams
from .errors import InsufficientData, require
from .formulas import cpa, cpc, ctr, cvr, roas

KPI_COLUMNS = ["ctr", "cvr", "cpc", "cpa", "roas"]

# Dimensions the API will group by. Anything else is rejected rather than
# passed through to `groupby`, so a query string can't select arbitrary columns.
GROUPABLE = ("channel", "device", "country", "objective", "audience")


def funnel(campaigns: pd.DataFrame) -> dict:
    """
    Portfolio-level funnel volumes and blended efficiency.

    Spend is summed over paid rows only, mirroring NB02. On this dataset that
    is identical to the full sum (Organic carries zero spend), but it keeps the
    metric correct if an uploaded feed ever encodes unpaid rows differently.
    """
    paid = campaigns.loc[campaigns["spend"] > 0]

    impressions = int(campaigns["impressions"].sum())
    clicks = int(campaigns["clicks"].sum())
    conversions = int(campaigns["conversions"].sum())
    spend = float(paid["spend"].sum())
    revenue = float(campaigns["revenue"].sum())

    return {
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "spend": spend,
        "revenue": revenue,
        "ctr": ctr(clicks, impressions),
        "cvr": cvr(conversions, clicks),
        "cpc": cpc(spend, clicks),
        "cpa": cpa(spend, conversions),
        "roas": roas(revenue, spend),
        "stages": [
            {"stage": "Impressions", "value": impressions, "pct_of_initial": 1.0},
            {"stage": "Clicks", "value": clicks,
             "pct_of_initial": ctr(clicks, impressions)},
            {"stage": "Conversions", "value": conversions,
             "pct_of_initial": ctr(conversions, impressions)},
        ],
    }


def groupby_kpis(campaigns: pd.DataFrame, by: str = "channel") -> pd.DataFrame:
    """Aggregate to any campaign dimension and derive the five efficiency KPIs."""
    if by not in GROUPABLE:
        raise ValueError(f"cannot group by {by!r}; expected one of {GROUPABLE}")

    g = campaigns.groupby(by).agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        conversions=("conversions", "sum"),
        spend=("spend", "sum"),
        revenue=("revenue", "sum"),
    )
    g["ctr"] = ctr(g["clicks"], g["impressions"])
    g["cvr"] = cvr(g["conversions"], g["clicks"])
    g["cpc"] = cpc(g["spend"], g["clicks"])
    g["cpa"] = cpa(g["spend"], g["conversions"])
    g["roas"] = roas(g["revenue"], g["spend"])
    return g.sort_values("roas", ascending=False)


def campaign_leaderboard(campaigns: pd.DataFrame,
                         min_spend: float = 100, n: int = 5) -> dict:
    """
    Best and worst campaigns by ROAS.

    `min_spend` filters campaign-*days*, not campaign totals — that is what
    NB02 does, and it keeps a single big-spend day from dragging in a campaign
    that is otherwise noise.
    """
    df = campaigns.loc[campaigns["spend"] > min_spend]
    if df.empty:
        return {"top": [], "bottom": [], "min_spend": min_spend, "n_campaigns": 0}

    perf = (
        df.groupby(["campaign_id", "campaign_name", "channel"])
        .agg(spend=("spend", "sum"), revenue=("revenue", "sum"),
             conversions=("conversions", "sum"))
        .reset_index()
    )
    perf["roas"] = roas(perf["revenue"], perf["spend"])
    perf["cpa"] = cpa(perf["spend"], perf["conversions"])
    ranked = perf.sort_values("roas", ascending=False)

    return {
        "top": ranked.head(n).to_dict("records"),
        "bottom": ranked.tail(n).iloc[::-1].to_dict("records"),
        "min_spend": min_spend,
        "n_campaigns": len(perf),
    }


def monthly_revenue(campaigns: pd.DataFrame,
                    params: AnalysisParams = DEFAULTS) -> pd.Series:
    """
    Campaign-attributed revenue per calendar month.

    Drops a trailing *incomplete* month by default. Under the replay cursor the
    current month holds only part of its days, which reads as a large downward
    outlier at the end of the series — enough to flip the fitted trend and the
    backtest winner from tick to tick.
    """
    if campaigns.empty:
        raise InsufficientData("monthly_revenue", need="at least 1 campaign row", have="0")

    monthly = campaigns.groupby(pd.Grouper(key="date", freq="MS"))["revenue"].sum()

    if params.drop_partial_trailing_month and len(monthly):
        last_day = campaigns["date"].max()
        month_end = last_day + pd.offsets.MonthEnd(0)
        if last_day < month_end:
            monthly = monthly.iloc[:-1]

    return monthly


def seasonality(campaigns: pd.DataFrame,
                params: AnalysisParams = DEFAULTS) -> dict:
    """Monthly revenue plus the peak month, for the seasonality view."""
    monthly = monthly_revenue(campaigns, params)
    if monthly.empty:
        raise InsufficientData("seasonality", need="at least 1 complete month", have="0")

    peak = monthly.idxmax()
    return {
        "months": [
            {"month": str(idx.date()), "revenue": float(val)}
            for idx, val in monthly.items()
        ],
        "peak_month": str(peak.date()),
        "peak_revenue": float(monthly.max()),
        "mean_revenue": float(monthly.mean()),
        "months_used": int(len(monthly)),
    }


def build(bundle, params: AnalysisParams = DEFAULTS) -> dict:
    """Everything the Marketing page needs, from one bundle."""
    require(bundle, "marketing", "campaigns")
    campaigns = bundle.campaigns

    return {
        "funnel": funnel(campaigns),
        "by_dimension": {
            dim: groupby_kpis(campaigns, dim).reset_index().to_dict("records")
            for dim in GROUPABLE
        },
        "campaigns": campaign_leaderboard(campaigns),
        "seasonality": seasonality(campaigns, params),
    }
