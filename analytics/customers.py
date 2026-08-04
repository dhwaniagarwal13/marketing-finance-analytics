"""
RFM segmentation and cohort retention — notebook 03.

This is the messiest extraction in the project. In the notebook, cells 4 and 6
share a mutated module-level `txn_with_cohort`, the pivot is fused with the
seaborn call that renders it, and the reference date is frozen to a literal.
Four things are fixed on the way out:

**One definition of "a purchase."** NB03's RFM excluded refunded transactions
while its cohort analysis included them, so the two halves of the chapter
disagreed about what activity means. `include_refunds_in_cohorts=False` unifies
them on the RFM definition; set it True to reproduce the notebook exactly.

**A live reference date.** `REFERENCE_DATE = "2025-12-31"` is correct only at
the end of the dataset. Under a moving cursor every recency score would be
computed against a future date.

**Cohorts that cannot be sized are dropped, not divided by NaN.** A cohort
month present in transactions but absent from customers produced NaN sizes and
therefore NaN retention.

**Unobservable cells are labelled.** For a cohort acquired in month *m*, months
beyond `as_of - m` have not happened yet. They are absent from the pivot, which
renders as blank — visually identical to 0% retention. The mask says which is
which.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FALLTHROUGH_SEGMENT, DEFAULTS, AnalysisParams
from .errors import InsufficientData, require
from .formulas import safe_divide

MIN_RFM_CUSTOMERS = 20


def _purchase_txns(transactions: pd.DataFrame, include_refunds: bool) -> pd.DataFrame:
    return transactions if include_refunds else transactions[~transactions["refund_flag"]]


def resolve_reference_date(transactions: pd.DataFrame,
                           params: AnalysisParams,
                           as_of: pd.Timestamp | None = None) -> pd.Timestamp:
    """Explicit param wins, then the cursor, then the last observed transaction."""
    if params.reference_date is not None:
        return pd.Timestamp(params.reference_date)
    if as_of is not None:
        return pd.Timestamp(as_of)
    return pd.Timestamp(transactions["transaction_date"].max())


def _score(values: pd.Series, bins: int, ascending: bool) -> tuple[pd.Series, int]:
    """
    Quantile score, degrading rather than raising when the data is thin.

    `qcut` raises on duplicate bin edges, which happens as soon as a value
    dominates the distribution — common early in the replay. `duplicates="drop"`
    keeps it working and the returned bin count says how much resolution was
    actually available.
    """
    labels_hi_first = list(range(bins, 0, -1))
    labels_lo_first = list(range(1, bins + 1))
    try:
        binned = pd.qcut(values, bins, labels=labels_hi_first if ascending else labels_lo_first)
        return binned.astype(int), bins
    except ValueError:
        binned = pd.qcut(values, bins, duplicates="drop")
        n = len(binned.cat.categories)
        order = list(range(n, 0, -1)) if ascending else list(range(1, n + 1))
        return binned.cat.rename_categories(order).astype(int), n


def assign_segments(rfm: pd.DataFrame, params: AnalysisParams = DEFAULTS) -> pd.Series:
    """
    Vectorized replacement for NB03's row-wise `.apply(segment_customer)`.

    `np.select` evaluates conditions in order and takes the first match, which
    is exactly the semantics of the original if-chain — and it turns the rules
    into data that the API can expose and a user can edit.
    """
    conditions = [
        rfm["R_score"].between(r.r_min, r.r_max) & rfm["F_score"].between(r.f_min, r.f_max)
        for r in params.segment_rules
    ]
    return pd.Series(
        np.select(conditions, [r.name for r in params.segment_rules],
                  default=FALLTHROUGH_SEGMENT),
        index=rfm.index, name="segment",
    )


def rfm_table(bundle, params: AnalysisParams = DEFAULTS,
              as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Recency/frequency/monetary scores and a segment per customer."""
    require(bundle, "rfm", "transactions")

    txns = _purchase_txns(bundle.transactions, params.include_refunds_in_rfm)
    if txns.empty:
        raise InsufficientData("rfm", need="at least 1 non-refunded purchase", have="0")

    reference = resolve_reference_date(bundle.transactions, params, as_of)

    rfm = txns.groupby("customer_id").agg(
        last_purchase=("transaction_date", "max"),
        frequency=("transaction_id", "count"),
        monetary=("amount", "sum"),
    ).reset_index()

    if len(rfm) < MIN_RFM_CUSTOMERS:
        raise InsufficientData("rfm", need=f"{MIN_RFM_CUSTOMERS} purchasing customers",
                               have=f"{len(rfm)}")

    rfm["recency_days"] = (reference - rfm["last_purchase"]).dt.days

    # Recency is scored directly; frequency and monetary are ranked first so
    # their heavy ties (many customers share a purchase count) still split into
    # distinct quantiles.
    rfm["R_score"], r_bins = _score(rfm["recency_days"], params.rfm_bins, ascending=True)
    rfm["F_score"], f_bins = _score(rfm["frequency"].rank(method="first"),
                                    params.rfm_bins, ascending=False)
    rfm["M_score"], m_bins = _score(rfm["monetary"].rank(method="first"),
                                    params.rfm_bins, ascending=False)
    rfm["rfm_score"] = rfm["R_score"] + rfm["F_score"] + rfm["M_score"]
    rfm["segment"] = assign_segments(rfm, params)

    if bundle.customers is not None:
        rfm = rfm.merge(
            bundle.customers[["customer_id", "acquisition_channel", "subscription_plan"]],
            on="customer_id", how="left",
        )

    rfm.attrs["reference_date"] = str(reference.date())
    rfm.attrs["bins_used"] = {"R": r_bins, "F": f_bins, "M": m_bins}
    rfm.attrs["degraded"] = min(r_bins, f_bins, m_bins) < params.rfm_bins
    return rfm


def segment_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    out = rfm.groupby("segment").agg(
        customers=("customer_id", "count"),
        avg_recency_days=("recency_days", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
    ).sort_values("customers", ascending=False)
    out["pct_of_base"] = out["customers"] / out["customers"].sum()
    return out


# ---------------------------------------------------------------------------
# Cohorts
# ---------------------------------------------------------------------------
def _cohort_activity(bundle, params: AnalysisParams, max_months: int) -> pd.DataFrame:
    """Transactions tagged with acquisition cohort and months-since-acquisition."""
    txns = _purchase_txns(bundle.transactions, params.include_refunds_in_cohorts)
    cohort_map = bundle.customers.set_index("customer_id")["acquisition_date"].dt.to_period("M")

    tagged = txns.dropna(subset=["customer_id"]).copy()
    tagged["cohort_month"] = tagged["customer_id"].map(cohort_map)
    tagged = tagged.dropna(subset=["cohort_month"])
    tagged["activity_month"] = tagged["transaction_date"].dt.to_period("M")
    tagged["months_since_acquisition"] = (
        tagged["activity_month"].astype("int64") - tagged["cohort_month"].astype("int64")
    )
    return tagged.loc[tagged["months_since_acquisition"].between(0, max_months)]


def cohort_retention(bundle, params: AnalysisParams = DEFAULTS,
                     as_of: pd.Timestamp | None = None,
                     _activity: pd.DataFrame | None = None) -> dict:
    """
    Monthly acquisition cohorts by months since acquisition.

    `_activity` lets `build()` share one tagged-transaction table with
    `retention_by_channel`, which halves the cost of the module. Tagging is the
    expensive step — mapping 39k transactions to cohorts and differencing two
    PeriodIndexes — and both views need exactly the same table.
    """
    require(bundle, "cohorts", "customers", "transactions")

    active = _activity if _activity is not None else _cohort_activity(
        bundle, params, params.cohort_max_months)
    active = active.loc[active["months_since_acquisition"] <= params.cohort_max_months]
    if active.empty:
        raise InsufficientData("cohorts", need="at least 1 attributable purchase", have="0")

    sizes = bundle.customers.groupby(
        bundle.customers["acquisition_date"].dt.to_period("M")).size()

    counts = (
        active.groupby(["cohort_month", "months_since_acquisition"])["customer_id"]
        .nunique().reset_index(name="active_customers")
    )
    counts["cohort_size"] = counts["cohort_month"].map(sizes)

    # A cohort month with transactions but no customers cannot be sized; NB03
    # divided by NaN and produced NaN retention instead of excluding it.
    unsized = counts["cohort_size"].isna().sum()
    counts = counts.dropna(subset=["cohort_size"])
    counts = counts.loc[counts["cohort_size"] >= params.cohort_min_size]

    if counts.empty:
        raise InsufficientData(
            "cohorts", need=f"a cohort of at least {params.cohort_min_size} customers",
            have=f"largest is {int(sizes.max()) if len(sizes) else 0}",
        )

    counts["retention_pct"] = safe_divide(counts["active_customers"], counts["cohort_size"])

    pivot = counts.pivot_table(index="cohort_month", columns="months_since_acquisition",
                               values="retention_pct", aggfunc="first")

    reference = resolve_reference_date(bundle.transactions, params, as_of)
    observable_through = pd.Period(reference, freq="M")

    matrix = []
    for cohort, row in pivot.iterrows():
        observable = observable_through.ordinal - cohort.ordinal
        matrix.append({
            "cohort": str(cohort),
            "cohort_size": int(counts.loc[counts["cohort_month"] == cohort,
                                          "cohort_size"].iloc[0]),
            "cells": [
                {
                    "month": int(m),
                    "retention_pct": None if pd.isna(row[m]) else float(row[m]),
                    # Distinguishes "nobody came back" from "not yet knowable".
                    "observed": bool(m <= observable),
                }
                for m in pivot.columns
            ],
        })

    month_1 = pivot[1].mean() if 1 in pivot.columns else float("nan")
    month_0 = pivot[0].mean() if 0 in pivot.columns else float("nan")

    return {
        "cohorts": matrix,
        "months": [int(m) for m in pivot.columns],
        "n_cohorts": int(len(pivot)),
        "cohorts_dropped_unsized": int(unsized),
        "mean_month_0": None if pd.isna(month_0) else float(month_0),
        "mean_month_1": None if pd.isna(month_1) else float(month_1),
        "month_0_to_1_drop": (
            None if pd.isna(month_0) or pd.isna(month_1) else float(month_0 - month_1)
        ),
        "counts_include_refunds": params.include_refunds_in_cohorts,
    }


def retention_by_channel(bundle, params: AnalysisParams = DEFAULTS,
                         _activity: pd.DataFrame | None = None) -> pd.DataFrame:
    """Retention curve per acquisition channel, denominated on all its customers."""
    require(bundle, "retention_by_channel", "customers", "transactions")

    active = _activity if _activity is not None else _cohort_activity(
        bundle, params, params.channel_retention_max_months)
    active = active.loc[
        active["months_since_acquisition"] <= params.channel_retention_max_months]
    tagged = active.merge(
        bundle.customers[["customer_id", "acquisition_channel"]],
        on="customer_id", how="left",
    )

    sizes = bundle.customers.groupby("acquisition_channel").size()
    out = (
        tagged.groupby(["acquisition_channel", "months_since_acquisition"])["customer_id"]
        .nunique().reset_index(name="active_customers")
    )
    out["cohort_size"] = out["acquisition_channel"].map(sizes)
    out["retention_pct"] = safe_divide(out["active_customers"], out["cohort_size"])
    return out


def value_by_plan(bundle, params: AnalysisParams = DEFAULTS) -> pd.DataFrame:
    """Lifetime profit and purchase frequency per subscription tier."""
    require(bundle, "value_by_plan", "customers", "transactions")

    txns = _purchase_txns(bundle.transactions, params.include_refunds_in_rfm)
    per_customer = txns.groupby("customer_id").agg(
        lifetime_profit=("profit", "sum"),
        purchases=("transaction_id", "count"),
        total_spend=("amount", "sum"),
    )
    joined = per_customer.join(
        bundle.customers.set_index("customer_id")[["subscription_plan", "acquisition_channel"]]
    )
    return joined.groupby("subscription_plan").agg(
        customers=("lifetime_profit", "size"),
        avg_purchases=("purchases", "mean"),
        avg_lifetime_profit=("lifetime_profit", "mean"),
    )


def build(bundle, params: AnalysisParams = DEFAULTS,
          as_of: pd.Timestamp | None = None) -> dict:
    """Everything the Customers page needs."""
    require(bundle, "customers", "customers", "transactions")
    rfm = rfm_table(bundle, params, as_of)

    # Tag once at the widest window both views need, then let each filter down.
    activity = _cohort_activity(
        bundle, params,
        max(params.cohort_max_months, params.channel_retention_max_months),
    )

    return {
        "rfm": {
            "reference_date": rfm.attrs["reference_date"],
            "bins_used": rfm.attrs["bins_used"],
            "degraded": rfm.attrs["degraded"],
            "n_customers": int(len(rfm)),
            "segments": segment_summary(rfm).reset_index().to_dict("records"),
        },
        "cohorts": cohort_retention(bundle, params, as_of, _activity=activity),
        "retention_by_channel": retention_by_channel(
            bundle, params, _activity=activity).to_dict("records"),
        "value_by_plan": value_by_plan(bundle, params).reset_index().to_dict("records"),
    }
