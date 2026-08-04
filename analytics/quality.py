"""
The data-quality audit, lifted out of notebook 01 as a declarative rule table.

This module is why `campaigns_clean.csv` and `transactions_clean.csv` can stop
existing. Those files were a *side effect* of running notebook 01, but
`generate_report.py` read them — so a fresh clone that ran only
`generate_data.py` crashed with FileNotFoundError. The cleaning now happens
in-process, from the raw CSVs, every time.

Faithfulness note — the notebook's ordering is load-bearing and preserved here:

  * de-duplication is applied *immediately* (NB01 cell 7), so every later
    campaign check sees 3,486 rows;
  * the negative-spend drop and the conversions cap are deferred to the
    remediation step (NB01 cell 16), so the checks in between still count
    against the de-duplicated-but-otherwise-raw table.

Getting that backwards changes the reported issue counts, which is exactly the
kind of silent drift the golden baseline exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import pandas as pd

from .config import DEFAULTS, AnalysisParams
from .formulas import ctr, cvr

Severity = Literal["error", "warning", "info"]
Stage = Literal["immediate", "deferred"]
Remedy = Literal["none", "drop_rows", "cap_column", "drop_duplicates"]


@dataclass(frozen=True)
class Rule:
    key: str
    check: str                      # display label; matches NB01's log_issue text
    table: str
    severity: Severity
    predicate: Callable[[dict, "Context"], pd.Series]
    why: str
    production_handling: str
    remedy: Remedy = "none"
    remedy_args: dict = field(default_factory=dict)
    stage: Stage = "deferred"


@dataclass
class Context:
    """Cross-table state a predicate may need (e.g. the anti-join key set)."""

    customer_ids: set
    expected_range: tuple[pd.Timestamp, pd.Timestamp] | None


@dataclass
class Issue:
    key: str
    check: str
    table: str
    severity: Severity
    issue_count: int
    pct_of_rows: float
    why_it_matters: str
    production_handling: str
    examples: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "key": self.key, "check": self.check, "table": self.table,
            "severity": self.severity, "issue_count": self.issue_count,
            "pct_of_rows": self.pct_of_rows,
            "why_it_matters": self.why_it_matters,
            "production_handling": self.production_handling,
            "examples": self.examples,
        }


@dataclass
class QualityReport:
    issues: list[Issue]
    rows_before: dict[str, int]
    rows_after: dict[str, int]

    @property
    def flagged(self) -> list[Issue]:
        return [i for i in self.issues if i.issue_count > 0]

    def as_dict(self) -> dict:
        return {
            "issues": [i.as_dict() for i in self.issues],
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "total_flagged": len(self.flagged),
            "total_rows_removed": {
                t: self.rows_before[t] - self.rows_after[t]
                for t in self.rows_before
                if self.rows_before[t] != self.rows_after.get(t, self.rows_before[t])
            },
        }


MAX_EXAMPLES = 20


# ---------------------------------------------------------------------------
# The rules. Order matters — it is NB01's check order.
# ---------------------------------------------------------------------------
RULES: tuple[Rule, ...] = (
    Rule(
        key="missing_customer_id", check="Missing customer_id",
        table="transactions", severity="warning",
        predicate=lambda t, c: t["transactions"]["customer_id"].isna(),
        why="A transaction without a customer_id cannot be joined to acquisition channel or demographics.",
        production_handling="Quarantine the row; alert the checkout/event-tracking pipeline owner.",
        remedy="drop_rows",
    ),
    Rule(
        key="missing_age_group", check="Missing age_group",
        table="customers", severity="info",
        predicate=lambda t, c: t["customers"]["age_group"].isna(),
        why="Breaks demographic segmentation for the affected rows only.",
        production_handling="Keep the row; exclude from age-based cuts; backfill via profile-completion nudge.",
        remedy="none",  # deliberately retained — see docs/Business_Assumptions.md
    ),
    Rule(
        key="duplicate_rows", check="Duplicate rows",
        table="campaigns", severity="error",
        predicate=lambda t, c: t["campaigns"].duplicated(),
        why="Double-loaded rows double-count spend and revenue, distorting every downstream KPI.",
        production_handling="De-duplicate on (campaign_id, date); alert ETL owner if it recurs.",
        remedy="drop_duplicates",
        stage="immediate",  # NB01 cell 7 — every later campaign check sees the deduped table
    ),
    Rule(
        key="out_of_range_dates", check="Invalid/out-of-range dates",
        table="campaigns", severity="warning",
        predicate=lambda t, c: _out_of_range(t["campaigns"]["date"], c.expected_range),
        why="Out-of-range dates corrupt time-series trends and seasonality analysis.",
        production_handling="Reject at ingestion; quarantine for source investigation.",
    ),
    Rule(
        key="negative_spend", check="Negative spend",
        table="campaigns", severity="error",
        predicate=lambda t, c: t["campaigns"]["spend"] < 0,
        why="Silently deflates total spend and inflates ROAS/ROI if left in.",
        production_handling="Route to finance for classification; exclude from KPI calcs until resolved.",
        remedy="drop_rows",
    ),
    Rule(
        key="negative_revenue", check="Negative revenue",
        table="campaigns", severity="error",
        predicate=lambda t, c: t["campaigns"]["revenue"] < 0,
        why="Revenue should never be negative at the campaign-day grain.",
        production_handling="Quarantine and investigate at source; exclude from KPI calcs until resolved.",
        remedy="drop_rows",
    ),
    Rule(
        key="profit_exceeds_amount", check="Profit > transaction amount",
        table="transactions", severity="error",
        predicate=lambda t, c: t["transactions"]["profit"] > t["transactions"]["amount"],
        why="Profit should never exceed gross order amount; signals a broken margin calculation.",
        production_handling="Halt the margin-calc job; re-run after fixing the formula before finance reporting.",
    ),
    Rule(
        key="orphan_transactions", check="Orphan transactions",
        table="transactions", severity="error",
        predicate=lambda t, c: (
            t["transactions"]["customer_id"].notna()
            & ~t["transactions"]["customer_id"].isin(c.customer_ids)
        ),
        why="A transaction not tied to a valid customer is invisible to all customer-level analysis.",
        production_handling="Quarantine; check for a late-arriving customer dimension load.",
        remedy="drop_rows",
    ),
    Rule(
        key="conversions_exceed_clicks", check="Conversions > clicks",
        table="campaigns", severity="error",
        predicate=lambda t, c: t["campaigns"]["conversions"] > t["campaigns"]["clicks"],
        why="Logically impossible; signals a tracking/attribution double-count.",
        production_handling="Flag to tracking team; cap conversions at clicks for reporting until fixed at source.",
        remedy="cap_column",
        remedy_args={"column": "conversions", "cap_at": "clicks"},
    ),
    Rule(
        key="impossible_ctr", check="Impossible CTR (outside 0-100%)",
        table="campaigns", severity="error",
        predicate=lambda t, c: _outside_unit_interval(
            ctr(t["campaigns"]["clicks"], t["campaigns"]["impressions"])
        ),
        why="CTR is a bounded rate; an out-of-range value signals a logging/units bug.",
        production_handling="Quarantine; audit impression/click logging for scale mismatches.",
    ),
    Rule(
        key="impossible_cvr", check="Impossible CVR (outside 0-100%)",
        table="campaigns", severity="error",
        predicate=lambda t, c: _outside_unit_interval(
            cvr(t["campaigns"]["conversions"], t["campaigns"]["clicks"])
        ),
        why="Same rationale as CTR — CVR must be a valid rate.",
        production_handling="Quarantine; audit the conversion-tracking pipeline.",
    ),
)


def _outside_unit_interval(rate: pd.Series) -> pd.Series:
    """NaN (zero denominator) is not an error — it means 'no traffic', not 'bad rate'."""
    return ((rate < 0) | (rate > 1)).fillna(False)


def _out_of_range(dates: pd.Series, window) -> pd.Series:
    if window is None:
        # No declared window: only genuinely impossible dates are errors.
        return dates.isna() | (dates < pd.Timestamp("1990-01-01")) | (dates > pd.Timestamp.today())
    lo, hi = window
    return (dates < lo) | (dates > hi)


# ---------------------------------------------------------------------------
# Audit + remediate
# ---------------------------------------------------------------------------
def _example_rows(df: pd.DataFrame, mask: pd.Series) -> list[dict]:
    sample = df.loc[mask].head(MAX_EXAMPLES)
    return [
        {k: (None if pd.isna(v) else (str(v) if isinstance(v, pd.Timestamp) else v))
         for k, v in row.items()}
        for row in sample.to_dict(orient="records")
    ]


def audit(tables: dict[str, pd.DataFrame],
          params: AnalysisParams = DEFAULTS) -> tuple[dict[str, pd.DataFrame], QualityReport]:
    """
    Run every applicable rule, then apply its remedy.

    Returns the cleaned tables and the report. Rules whose table is absent are
    skipped silently, so this works on partial (uploaded) datasets.
    """
    working = {name: df.copy() for name, df in tables.items() if df is not None}
    rows_before = {name: len(df) for name, df in working.items()}

    ctx = Context(
        customer_ids=set(working["customers"]["customer_id"]) if "customers" in working else set(),
        expected_range=_resolve_range(working, params),
    )

    issues: list[Issue] = []
    deferred: list[tuple[Rule, pd.Series]] = []

    for rule in RULES:
        if rule.table not in working:
            continue

        df = working[rule.table]
        mask = rule.predicate(working, ctx).fillna(False)
        count = int(mask.sum())

        issues.append(Issue(
            key=rule.key, check=rule.check, table=rule.table, severity=rule.severity,
            issue_count=count,
            pct_of_rows=round(count / len(df) * 100, 4) if len(df) else 0.0,
            why_it_matters=rule.why, production_handling=rule.production_handling,
            examples=_example_rows(df, mask) if count else [],
        ))

        if rule.stage == "immediate":
            working[rule.table] = _apply(df, mask, rule)
        elif rule.remedy != "none" and count:
            deferred.append((rule, mask))

    for rule, mask in deferred:
        working[rule.table] = _apply(working[rule.table], mask, rule)

    return working, QualityReport(
        issues=issues,
        rows_before=rows_before,
        rows_after={name: len(df) for name, df in working.items()},
    )


def _apply(df: pd.DataFrame, mask: pd.Series, rule: Rule) -> pd.DataFrame:
    if rule.remedy == "drop_duplicates":
        return df.drop_duplicates().copy()
    if rule.remedy == "drop_rows":
        return df.loc[~mask.reindex(df.index, fill_value=False)].copy()
    if rule.remedy == "cap_column":
        col, cap_at = rule.remedy_args["column"], rule.remedy_args["cap_at"]
        out = df.copy()
        rows = mask.reindex(out.index, fill_value=False)
        out.loc[rows, col] = out.loc[rows, cap_at]
        return out
    return df


def _resolve_range(working: dict[str, pd.DataFrame],
                   params: AnalysisParams) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if params.expected_date_range is None:
        return None
    lo, hi = params.expected_date_range
    return pd.Timestamp(lo), pd.Timestamp(hi)
