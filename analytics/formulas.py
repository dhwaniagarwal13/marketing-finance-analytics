"""
KPI formulas, lifted out of `src/utils.py`.

One behavioural change from the originals: these accept scalars, numpy arrays
and pandas Series alike. The `utils` versions called `.replace(0, np.nan)` on
the denominator, which only works on a Series — so notebook 02 had to wrap
scalars just to compute a blended CTR:

    u.ctr(pd.Series([overall["Clicks"]]), pd.Series([overall["Impressions"]]))[0]

Division by zero still yields NaN rather than raising or returning inf; that
behaviour is relied on throughout the analysis (Organic has zero spend, so its
CPC/CPA/ROAS must be NaN, not inf).

`utils.ltv_simple` and `utils.retention_rate` are deliberately not carried
over — neither had a single call site.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "ctr", "cvr", "cpc", "cpa", "roas", "roi", "cac",
    "contribution_margin", "safe_divide", "fmt_currency", "fmt_pct",
]


def safe_divide(numerator, denominator):
    """
    Divide, mapping a zero denominator to NaN.

    Preserves pandas types and index when either operand is a Series, so the
    result can be assigned straight back onto a DataFrame column.
    """
    if isinstance(denominator, (pd.Series, pd.DataFrame)):
        # .where() keeps values where the condition holds and inserts NaN
        # elsewhere, upcasting integer dtypes to float as needed.
        return numerator / denominator.where(denominator != 0)

    if isinstance(numerator, (pd.Series, pd.DataFrame)):
        den = np.asarray(denominator, dtype="float64")
        return numerator / np.where(den == 0, np.nan, den)

    num = np.asarray(numerator, dtype="float64")
    den = np.asarray(denominator, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.divide(num, np.where(den == 0, np.nan, den))
    return float(result) if result.ndim == 0 else result


# ---------------------------------------------------------------------------
# Funnel efficiency
# ---------------------------------------------------------------------------
def ctr(clicks, impressions):
    """Click-through rate: clicks / impressions."""
    return safe_divide(clicks, impressions)


def cvr(conversions, clicks):
    """Conversion rate: conversions / clicks."""
    return safe_divide(conversions, clicks)


def cpc(spend, clicks):
    """Cost per click: spend / clicks. NaN for unpaid channels (Organic)."""
    return safe_divide(spend, clicks)


def cpa(spend, conversions):
    """Cost per acquisition: spend / conversions. NaN for unpaid channels."""
    return safe_divide(spend, conversions)


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------
def roas(revenue, spend):
    """Return on ad spend: revenue / spend. NaN for unpaid channels."""
    return safe_divide(revenue, spend)


def roi(profit, spend):
    """Return on investment: (profit - spend) / spend."""
    return safe_divide(profit - spend, spend)


def cac(spend_by_channel, new_customers_by_channel):
    """Customer acquisition cost: marketing spend / new customers acquired."""
    return safe_divide(spend_by_channel, new_customers_by_channel)


def contribution_margin(revenue, variable_cost):
    """
    Margin ratio: (revenue - variable_cost) / revenue.

    Note on naming: notebook 04 calls this with *marketing spend* as the
    variable cost, which makes the result a marketing-cost margin
    (equivalently `1 - 1/ROAS`) rather than a COGS-based contribution margin.
    The formula is general; the interpretation depends on what you pass in.
    """
    return safe_divide(revenue - variable_cost, revenue)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def fmt_currency(x, decimals: int = 0) -> str:
    return f"${x:,.{decimals}f}"


def fmt_pct(x, decimals: int = 1) -> str:
    return f"{x * 100:.{decimals}f}%"
