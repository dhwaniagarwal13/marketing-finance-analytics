"""
Unit economics and profitability — notebook 04.

Two things worth knowing about the numbers here.

**Revenue and profit come from different universes.** `campaign_revenue` is
campaign-attributed (from `campaigns.revenue`), while `customer_gross_profit`
is transaction profit attributed to the channel that *acquired* the customer.
They answer different questions and are not comparable line by line — Email's
net profit exceeds its campaign revenue for exactly this reason. Both are
labelled explicitly so the UI can say so.

**The reallocation model assumes constant marginal ROI.** It prices shifted
dollars at each channel's current *average* ROI. Real marginal returns
diminish as spend scales, so treat the output as an upper bound. The donors
here also carry negative ROI, which means the model books a gain on both sides
of the shift — that is arithmetically right but worth reading carefully.
"""

from __future__ import annotations

import pandas as pd

from .config import DEFAULTS, AnalysisParams
from .errors import InsufficientData, require
from .formulas import cac as cac_formula
from .formulas import contribution_margin, roas, roi, safe_divide


def _customer_lifetime_profit(transactions: pd.DataFrame,
                              params: AnalysisParams) -> pd.Series:
    txns = transactions if params.include_refunds_in_rfm else transactions[~transactions["refund_flag"]]
    return txns.groupby("customer_id")["profit"].sum().rename("lifetime_profit")


def _customers_with_profit(customers: pd.DataFrame, transactions: pd.DataFrame,
                           params: AnalysisParams) -> pd.DataFrame:
    """Customers joined to lifetime profit, zero-filled for non-purchasers."""
    profit = _customer_lifetime_profit(transactions, params)
    return customers.set_index("customer_id").join(profit).fillna({"lifetime_profit": 0})


def cac_ltv_by_channel(bundle, params: AnalysisParams = DEFAULTS,
                       _cust: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    CAC, LTV and their ratio per acquisition channel.

    `_cust` lets `build()` share the customer-to-lifetime-profit join with
    `profitability`, which otherwise groups 39k transactions twice per call.
    """
    require(bundle, "cac_ltv", "campaigns", "customers", "transactions")

    spend = bundle.campaigns.groupby("channel")["spend"].sum()
    new_customers = bundle.customers.groupby("acquisition_channel").size()
    cust = _cust if _cust is not None else _customers_with_profit(
        bundle.customers, bundle.transactions, params)

    cac = cac_formula(spend, new_customers).rename("cac")

    if params.ltv_denominator == "all_customers":
        ltv = cust.groupby("acquisition_channel")["lifetime_profit"].mean().rename("ltv")
    else:
        purchasers = cust.loc[cust["lifetime_profit"] != 0]
        ltv = purchasers.groupby("acquisition_channel")["lifetime_profit"].mean().rename("ltv")

    out = pd.DataFrame({"cac": cac, "ltv": ltv}).dropna()

    # Zero-CAC channels (Organic) have no attributable acquisition cost, so the
    # ratio is undefined rather than infinite. NB04 divided anyway and produced
    # `inf`, which matplotlib silently declined to draw — Organic is absent from
    # reports/figures/04_ltv_cac_ratio.png even though the surrounding text
    # discusses it. Flag it instead, so the UI can say why it has no bar.
    out["ratio_undefined"] = out["cac"] == 0
    out["ltv_cac_ratio"] = safe_divide(out["ltv"], out["cac"])
    out["clears_benchmark"] = [
        None if undefined else bool(ratio >= params.ltv_cac_benchmark)
        for undefined, ratio in zip(out["ratio_undefined"], out["ltv_cac_ratio"])
    ]

    # Undefined ratios sort to the top: no acquisition cost is the best possible
    # position, and burying them at the bottom next to the failing channels
    # would read as the opposite.
    return out.sort_values(["ratio_undefined", "ltv_cac_ratio"], ascending=[False, False])


def profitability(bundle, params: AnalysisParams = DEFAULTS,
                  _cust: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    True channel profitability, and where the revenue ranking misleads.

    `rank_shift` is the headline: positive means a channel ranks better on
    revenue than on profit, i.e. a revenue-only leaderboard would over-fund it.
    """
    require(bundle, "profitability", "campaigns", "customers", "transactions")

    spend = bundle.campaigns.groupby("channel")["spend"].sum()
    revenue = bundle.campaigns.groupby("channel")["revenue"].sum()
    new_customers = bundle.customers.groupby("acquisition_channel").size()
    cust = _cust if _cust is not None else _customers_with_profit(
        bundle.customers, bundle.transactions, params)
    gross_profit = cust.groupby("acquisition_channel")["lifetime_profit"].sum()

    df = pd.DataFrame({
        "campaign_revenue": revenue,
        "marketing_spend": spend,
        "customer_gross_profit": gross_profit,
        "net_profit": (gross_profit - spend),
    }).fillna(0)

    df["revenue_rank"] = df["campaign_revenue"].rank(ascending=False).astype(int)
    df["profit_rank"] = df["net_profit"].rank(ascending=False).astype(int)
    df["rank_shift"] = df["revenue_rank"] - df["profit_rank"]
    df["contribution_margin"] = contribution_margin(df["campaign_revenue"], df["marketing_spend"])
    df["profit_per_customer"] = safe_divide(df["customer_gross_profit"], new_customers)
    df["roi"] = roi(df["customer_gross_profit"], df["marketing_spend"])

    return df.sort_values("net_profit", ascending=False)


def reallocation(profit_table: pd.DataFrame,
                 params: AnalysisParams = DEFAULTS) -> dict:
    """
    Move `shift_pct` of spend from the weakest to the strongest elastic channels.

    Guards an overlap bug latent in the original: `head(2)` and `tail(2)` of a
    table with fewer than four rows return overlapping slices, so a channel
    becomes both donor and recipient and its spend is counted twice. That never
    fired on the full dataset (all five elastic channels are present) but does
    fire early in the replay — TikTok has no rows before 2024-07-01 — and on
    uploads with a different channel mix.
    """
    n_needed = params.n_donors + params.n_recipients

    elastic = [c for c in params.elastic_paid_channels if c in profit_table.index]
    basis = "configured"

    if len(elastic) < n_needed:
        elastic = list(profit_table.index[profit_table["marketing_spend"] > 0])
        basis = "inferred"

    if len(elastic) < n_needed:
        raise InsufficientData(
            "reallocation",
            need=f"{n_needed} channels with spend",
            have=f"{len(elastic)}",
        )

    paid = profit_table.loc[profit_table.index.isin(elastic)].copy()
    paid["roi"] = roi(paid["customer_gross_profit"], paid["marketing_spend"])
    paid = paid.sort_values("roi", ascending=False)

    recipients = paid.head(params.n_recipients)
    donors = paid.tail(params.n_donors)
    assert not set(recipients.index) & set(donors.index), "donor/recipient overlap"

    shift_amount = float((donors["marketing_spend"] * params.shift_pct).sum())
    weights = recipients["roi"] / recipients["roi"].sum()

    profit_lost = float((donors["marketing_spend"] * params.shift_pct * donors["roi"]).sum())
    profit_gained = float((weights * shift_amount * recipients["roi"]).sum())

    donor_roas = roas(donors["campaign_revenue"], donors["marketing_spend"])
    recipient_roas = roas(recipients["campaign_revenue"], recipients["marketing_spend"])
    revenue_lost = float((donors["marketing_spend"] * params.shift_pct * donor_roas).sum())
    revenue_gained = float((weights * shift_amount * recipient_roas).sum())

    current = paid["marketing_spend"].copy()
    recommended = current.copy()
    recommended.loc[donors.index] -= donors["marketing_spend"] * params.shift_pct
    recommended.loc[recipients.index] += weights * shift_amount

    plan = pd.DataFrame({"current_spend": current, "recommended_spend": recommended})
    plan["change"] = plan["recommended_spend"] - plan["current_spend"]
    plan["change_pct"] = safe_divide(plan["change"], plan["current_spend"])

    return {
        "shift_pct": params.shift_pct,
        "shift_amount": shift_amount,
        "from_channels": list(donors.index),
        "to_channels": list(recipients.index),
        "profit_lost": profit_lost,
        "profit_gained": profit_gained,
        "net_profit_change": profit_gained - profit_lost,
        "revenue_lost": revenue_lost,
        "revenue_gained": revenue_gained,
        "net_revenue_change": revenue_gained - revenue_lost,
        "plan": plan.reset_index().rename(columns={"index": "channel"}).to_dict("records"),
        "basis": basis,
        "channels_considered": elastic,
        "assumption": "marginal ROI held equal to current average ROI; treat as an upper bound",
    }


def headline_kpis(bundle, params: AnalysisParams = DEFAULTS) -> dict:
    """
    Portfolio scorecard.

    Every value carries its `basis`, because two of them are not what a reader
    would assume: ROAS is campaign-attributed revenue over spend, while ROI is
    transaction profit over spend — different revenue universes in adjacent
    tiles. LTV's denominator is configurable for the same reason.
    """
    require(bundle, "kpis", "campaigns", "customers", "transactions")

    campaigns, customers = bundle.campaigns, bundle.customers
    txns = bundle.transactions
    paid_txns = txns if params.include_refunds_in_rfm else txns[~txns["refund_flag"]]

    n_customers = len(customers)
    if n_customers == 0:
        raise InsufficientData("kpis", need="at least 1 customer", have="0")

    total_revenue = float(campaigns["revenue"].sum())
    total_spend = float(campaigns["spend"].sum())
    total_gross_profit = float(paid_txns["profit"].sum())

    per_customer = paid_txns.groupby("customer_id")["profit"].sum()
    if params.ltv_denominator == "all_customers":
        blended_ltv = total_gross_profit / n_customers
        ltv_basis = f"all {n_customers:,} customers, zero-filled"
    else:
        blended_ltv = float(per_customer.mean())
        ltv_basis = f"{len(per_customer):,} customers who transacted"

    blended_cac = total_spend / n_customers

    return {
        "total_revenue": {"value": total_revenue, "basis": "campaign-attributed"},
        "total_spend": {"value": total_spend, "basis": "campaign media spend"},
        "total_gross_profit": {"value": total_gross_profit,
                               "basis": "non-refunded transaction profit"},
        "total_net_profit": {"value": total_gross_profit - total_spend,
                             "basis": "transaction profit less marketing spend"},
        "blended_cac": {"value": blended_cac,
                        "basis": f"spend / all {n_customers:,} customers"},
        "blended_ltv": {"value": blended_ltv, "basis": ltv_basis},
        "ltv_cac_ratio": {"value": safe_divide(blended_ltv, blended_cac),
                          "basis": "same denominator on both sides"},
        "blended_roas": {"value": safe_divide(total_revenue, total_spend),
                         "basis": "campaign revenue / spend"},
        "blended_roi": {"value": safe_divide(total_gross_profit - total_spend, total_spend),
                        "basis": "transaction profit / spend"},
        "blended_cvr": {"value": safe_divide(campaigns["conversions"].sum(),
                                             campaigns["clicks"].sum()),
                        "basis": "conversions / clicks"},
        "repeat_rate": {"value": float((per_customer.index.map(
            paid_txns.groupby("customer_id").size()) > 1).mean()) if len(per_customer) else 0.0,
            "basis": "share of transacting customers with >1 purchase"},
    }


def build(bundle, params: AnalysisParams = DEFAULTS) -> dict:
    """Everything the Finance page needs."""
    require(bundle, "finance", "campaigns", "customers", "transactions")

    # One join, shared by both tables below.
    cust = _customers_with_profit(bundle.customers, bundle.transactions, params)
    table = profitability(bundle, params, _cust=cust)

    try:
        realloc = reallocation(table, params)
    except InsufficientData as exc:
        realloc = exc.as_dict()

    return {
        "kpis": headline_kpis(bundle, params),
        "profitability": table.reset_index().rename(
            columns={"index": "channel", "channel": "channel"}).to_dict("records"),
        "cac_ltv": cac_ltv_by_channel(bundle, params, _cust=cust).reset_index().rename(
            columns={"acquisition_channel": "channel", "index": "channel"}).to_dict("records"),
        "reallocation": realloc,
    }
