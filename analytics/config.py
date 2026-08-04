"""
Every tunable in the analysis, in one frozen object.

These values were hardcoded across the six notebooks (`SHIFT_PCT = 0.15` in
NB04, `REFERENCE_DATE = "2025-12-31"` in NB03, `ALPHA`/`HOLDOUT` in NB05, the
RFM segment cutoffs as an if-chain). Hoisting them here does three things:

  * the same engine can serve the notebooks, the PDF and the API;
  * each one becomes a UI control, since every engine function is pure;
  * the object is frozen and hashable, so it doubles as a cache key and can be
    fingerprinted onto the wire as `params_hash`.

Defaults reproduce the notebooks exactly, with two deliberate exceptions that
are called out in `AnalysisParams` — both are documented inconsistencies in the
original analysis, not behaviour worth preserving.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class SegmentRule:
    """
    One RFM segment, as data rather than a branch of an if-chain.

    Bounds are inclusive. Rules are evaluated in order and the first match
    wins, which mirrors NB03's `segment_customer` exactly.
    """

    name: str
    r_min: int = 1
    r_max: int = 5
    f_min: int = 1
    f_max: int = 5


DEFAULT_SEGMENT_RULES: tuple[SegmentRule, ...] = (
    SegmentRule("Champions", r_min=4, f_min=4),
    SegmentRule("Loyal Customers", r_min=3, f_min=3),
    SegmentRule("Potential Loyalists", r_min=4, f_max=2),
    SegmentRule("At Risk", r_max=2, f_min=3),
    SegmentRule("Lost Customers", r_max=2, f_max=2),
)
FALLTHROUGH_SEGMENT = "Needs Attention"


@dataclass(frozen=True)
class AnalysisParams:
    # --- temporal -----------------------------------------------------------
    # None -> use the `as_of` cursor, falling back to max(transaction_date).
    # NB03 froze this to 2025-12-31, which silently breaks under a moving cursor.
    reference_date: date | None = None
    # None -> infer from the data. NB01 hardcoded 2024-01-01/2025-12-31, which
    # would flag 100% of rows in any uploaded dataset.
    expected_date_range: tuple[date, date] | None = None

    # --- RFM / customers ----------------------------------------------------
    rfm_bins: int = 5
    segment_rules: tuple[SegmentRule, ...] = DEFAULT_SEGMENT_RULES
    include_refunds_in_rfm: bool = False
    # DELIBERATE DIVERGENCE: NB03's cohort analysis counted refunded purchases
    # as activity while its RFM excluded them — two definitions of "a purchase"
    # in one notebook. False unifies them on the RFM definition.
    include_refunds_in_cohorts: bool = False
    cohort_max_months: int = 11
    cohort_min_size: int = 20
    channel_retention_max_months: int = 6

    # --- finance ------------------------------------------------------------
    elastic_paid_channels: tuple[str, ...] = (
        "Google Ads", "Facebook", "Instagram", "Affiliate", "TikTok",
    )
    shift_pct: float = 0.15
    n_donors: int = 2
    n_recipients: int = 2
    # DELIBERATE DIVERGENCE: blended LTV averaged over transacting customers
    # only, while blended CAC divided by all customers — so the headline
    # LTV:CAC mixed bases (6.657 vs 6.625 on a consistent basis).
    ltv_denominator: Literal["all_customers", "transacting_customers"] = "all_customers"
    ltv_cac_benchmark: float = 3.0

    # --- experiments --------------------------------------------------------
    alpha: float = 0.05
    ab_alternative: Literal["larger", "two-sided"] = "larger"

    # --- forecast -----------------------------------------------------------
    holdout_months: int = 3
    forecast_horizon: int = 3
    forecast_methods: tuple[str, ...] = ("moving_average", "linear_trend", "arima")
    arima_order: tuple[int, int, int] = (1, 1, 1)
    ma_window: int = 3
    # Under a moving cursor the trailing month is partial, which reads as a
    # ~55%-low outlier and makes the fitted trend whipsaw every tick.
    drop_partial_trailing_month: bool = True

    # --- ml -----------------------------------------------------------------
    churn_window_days: int = 90
    churn_active_lookback_days: int = 180
    churn_min_customers: int = 500
    churn_min_months: int = 6

    def fingerprint(self) -> str:
        """Short stable hash, safe to expose to clients as `params_hash`."""
        blob = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


DEFAULTS = AnalysisParams()
