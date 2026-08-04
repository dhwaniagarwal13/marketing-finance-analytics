"""
Loading and slicing.

`load_from_paths()` reads the four **raw** CSVs and cleans them in-process, so
`data/raw/campaigns_clean.csv` and `transactions_clean.csv` are no longer
inputs to anything. They were written as a side effect of running notebook 01
while `generate_report.py` depended on them — a fresh clone would crash.

`DatasetBundle.as_of()` is the whole simulation: slice every table to a cursor
date and recompute. On this dataset that mask costs ~5 ms, which is why the
live view needs no caching or incremental aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .config import DEFAULTS, AnalysisParams
from .quality import QualityReport, audit

# Raw filenames and their date columns. `*_clean.csv` deliberately absent.
SOURCES: dict[str, tuple[str, list[str]]] = {
    "campaigns": ("campaigns.csv", ["date"]),
    "customers": ("customers.csv", ["acquisition_date"]),
    "transactions": ("transactions.csv", ["transaction_date"]),
    "ab_test": ("ab_test_campaigns.csv", ["date"]),
}

DATE_COLUMN: dict[str, str] = {
    "campaigns": "date",
    "customers": "acquisition_date",
    "transactions": "transaction_date",
    "ab_test": "date",
}


@dataclass(frozen=True)
class Capabilities:
    """Which analysis modules the loaded tables can support."""

    overview: bool = False
    marketing: bool = False
    forecast: bool = False
    acquisition_cost: bool = False
    customer_value: bool = False
    rfm: bool = False
    cohorts: bool = False
    profitability: bool = False
    reallocation: bool = False
    experiments: bool = False
    churn_ml: bool = False

    def as_dict(self) -> dict:
        return {k: bool(v) for k, v in self.__dict__.items()}


@dataclass
class Provenance:
    source: str
    loaded_at: str
    rows_raw: dict[str, int] = field(default_factory=dict)
    rows_clean: dict[str, int] = field(default_factory=dict)


@dataclass
class DatasetBundle:
    campaigns: pd.DataFrame | None
    customers: pd.DataFrame | None
    transactions: pd.DataFrame | None
    ab_test: pd.DataFrame | None
    quality: QualityReport
    provenance: Provenance
    params: AnalysisParams = DEFAULTS

    # -- access ------------------------------------------------------------
    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            name: df
            for name, df in (
                ("campaigns", self.campaigns), ("customers", self.customers),
                ("transactions", self.transactions), ("ab_test", self.ab_test),
            )
            if df is not None
        }

    def has(self, *names: str) -> bool:
        present = self.tables
        return all(n in present and len(present[n]) for n in names)

    @property
    def capabilities(self) -> Capabilities:
        months = self.months_of_history
        p = self.params
        return Capabilities(
            overview=self.has("campaigns"),
            marketing=self.has("campaigns"),
            forecast=self.has("campaigns") and months >= p.holdout_months + 3,
            acquisition_cost=self.has("campaigns", "customers"),
            customer_value=self.has("customers", "transactions"),
            rfm=self.has("transactions"),
            cohorts=self.has("customers", "transactions"),
            profitability=self.has("campaigns", "customers", "transactions"),
            reallocation=(
                self.has("campaigns", "customers", "transactions")
                and self.campaigns.loc[self.campaigns["spend"] > 0, "channel"].nunique()
                >= p.n_donors + p.n_recipients
            ),
            experiments=self.has("ab_test"),
            churn_ml=(
                self.has("customers", "transactions")
                and len(self.customers) >= p.churn_min_customers
                and months >= p.churn_min_months
            ),
        )

    @property
    def months_of_history(self) -> int:
        spans = []
        for name, df in self.tables.items():
            col = DATE_COLUMN[name]
            if col in df.columns and len(df):
                lo, hi = df[col].min(), df[col].max()
                spans.append((hi.year - lo.year) * 12 + (hi.month - lo.month) + 1)
        return max(spans) if spans else 0

    @property
    def max_date(self) -> pd.Timestamp | None:
        highs = [
            df[DATE_COLUMN[name]].max()
            for name, df in self.tables.items()
            if DATE_COLUMN[name] in df.columns and len(df)
        ]
        return max(highs) if highs else None

    # -- slicing -----------------------------------------------------------
    def as_of(self, cursor: date | pd.Timestamp) -> "DatasetBundle":
        """
        Everything visible on or before `cursor`.

        Cheap boolean masks, no copy of the underlying blocks. The returned
        bundle carries the *original* quality report — the audit describes the
        source data, not the slice.
        """
        ts = pd.Timestamp(cursor)

        def cut(df: pd.DataFrame | None, col: str) -> pd.DataFrame | None:
            if df is None:
                return None
            return df.loc[df[col] <= ts]

        return DatasetBundle(
            campaigns=cut(self.campaigns, "date"),
            customers=cut(self.customers, "acquisition_date"),
            transactions=cut(self.transactions, "transaction_date"),
            ab_test=cut(self.ab_test, "date"),
            quality=self.quality,
            provenance=self.provenance,
            params=self.params,
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_from_paths(data_dir: str | Path,
                    params: AnalysisParams = DEFAULTS) -> DatasetBundle:
    """Read the four raw CSVs, audit and clean them in-process."""
    data_dir = Path(data_dir)
    raw: dict[str, pd.DataFrame] = {}

    for name, (filename, date_cols) in SOURCES.items():
        path = data_dir / filename
        if path.exists():
            raw[name] = pd.read_csv(path, parse_dates=date_cols)

    if not raw:
        raise FileNotFoundError(
            f"No source CSVs found in {data_dir}. Run `python src/generate_data.py` first."
        )

    return build_bundle(raw, params=params, source=str(data_dir))


def build_bundle(raw: dict[str, pd.DataFrame],
                 params: AnalysisParams = DEFAULTS,
                 source: str = "memory") -> DatasetBundle:
    """Audit, clean and wrap already-parsed tables. Shared by file and upload paths."""
    rows_raw = {name: len(df) for name, df in raw.items()}
    clean, report = audit(raw, params)

    return DatasetBundle(
        campaigns=clean.get("campaigns"),
        customers=clean.get("customers"),
        transactions=clean.get("transactions"),
        ab_test=clean.get("ab_test"),
        quality=report,
        provenance=Provenance(
            source=source,
            loaded_at=pd.Timestamp.now().isoformat(timespec="seconds"),
            rows_raw=rows_raw,
            rows_clean={name: len(df) for name, df in clean.items()},
        ),
        params=params,
    )
