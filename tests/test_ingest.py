"""
Proves the `*_clean.csv` files are no longer needed.

`analytics.ingest.load_from_paths()` reads the raw CSVs and cleans them in
memory. These tests assert the result is frame-for-frame identical to the
`_clean.csv` files that notebook 01 used to write — which is what lets every
downstream number stay unchanged while the fresh-clone crash goes away.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.ingest import load_from_paths


@pytest.fixture(scope="module")
def bundle(project_root):
    return load_from_paths(project_root / "data" / "raw")


@pytest.fixture(scope="module")
def clean_csvs(project_root):
    """
    The files notebook 01 used to emit.

    This is a migration check: it proves the in-process clean is identical to
    what downstream code used to read. The files are now gitignored outputs, so
    once they are gone the comparison is moot and the test skips rather than
    erroring — the parity suite is what guards the numbers from then on.
    """
    raw = project_root / "data" / "raw"
    paths = {
        "campaigns": (raw / "campaigns_clean.csv", "date"),
        "transactions": (raw / "transactions_clean.csv", "transaction_date"),
    }
    missing = [p.name for p, _ in paths.values() if not p.exists()]
    if missing:
        pytest.skip(f"legacy clean CSVs absent ({', '.join(missing)}); superseded by test_parity")

    return {
        name: pd.read_csv(path, parse_dates=[date_col])
        for name, (path, date_col) in paths.items()
    }


def test_clean_shapes(bundle):
    assert bundle.campaigns.shape == (3481, 13)
    assert bundle.customers.shape == (6000, 9)
    assert bundle.transactions.shape == (40690, 8)
    assert bundle.ab_test.shape == (60, 7)


@pytest.mark.parametrize("table", ["campaigns", "transactions"])
def test_matches_the_clean_csv_exactly(bundle, clean_csvs, table):
    """The in-process clean must equal the file notebook 01 used to emit."""
    actual = getattr(bundle, table).reset_index(drop=True)
    expected = clean_csvs[table].reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_issue_counts_match_notebook_01(bundle, golden):
    """The audit must reproduce notebook 01's counts, check for check."""
    expected = {
        item["check"]: item["issue_count"]
        for item in golden["01_Data_Overview"]["dq_issues"]
    }
    actual = {i.check: i.issue_count for i in bundle.quality.issues}

    assert actual == expected


def test_dedup_runs_before_the_other_campaign_checks(bundle):
    """
    Ordering is load-bearing: notebook 01 de-duplicates immediately (cell 7)
    but defers the negative-spend drop to cell 16, so the rate checks in
    between see 3,486 rows. The golden capture pins this via len(ctr_check).
    """
    by_key = {i.key: i for i in bundle.quality.issues}
    assert by_key["duplicate_rows"].issue_count == 8
    assert by_key["negative_spend"].issue_count == 5
    assert by_key["conversions_exceed_clicks"].issue_count == 4
    # 3494 raw - 8 dupes - 5 negative-spend = 3481
    assert bundle.provenance.rows_raw["campaigns"] == 3494
    assert bundle.provenance.rows_clean["campaigns"] == 3481


def test_flagged_issues_carry_examples(bundle):
    for issue in bundle.quality.flagged:
        assert issue.examples, f"{issue.key} flagged {issue.issue_count} rows but gave no examples"
        assert len(issue.examples) <= 20


def test_age_group_nulls_are_reported_but_retained(bundle):
    """Documented decision: keep the row, exclude it from age-based cuts."""
    by_key = {i.key: i for i in bundle.quality.issues}
    assert by_key["missing_age_group"].issue_count == 10
    assert bundle.customers["age_group"].isna().sum() == 10
    assert len(bundle.customers) == 6000


def test_as_of_slices_every_table(bundle):
    cut = bundle.as_of("2024-12-31")
    assert cut.campaigns["date"].max() <= pd.Timestamp("2024-12-31")
    assert cut.transactions["transaction_date"].max() <= pd.Timestamp("2024-12-31")
    assert cut.customers["acquisition_date"].max() <= pd.Timestamp("2024-12-31")
    assert len(cut.campaigns) < len(bundle.campaigns)


def test_as_of_at_end_of_data_is_the_whole_dataset(bundle):
    """The replay cursor must converge exactly on the static analysis."""
    cut = bundle.as_of("2025-12-31")
    assert cut.campaigns.shape == bundle.campaigns.shape
    assert cut.transactions.shape == bundle.transactions.shape
    assert cut.customers.shape == bundle.customers.shape


def test_capabilities_on_the_full_demo_dataset(bundle):
    caps = bundle.capabilities
    assert caps.overview and caps.marketing and caps.forecast
    assert caps.profitability and caps.reallocation
    assert caps.rfm and caps.cohorts and caps.experiments
    assert caps.churn_ml


def test_works_from_a_directory_containing_only_the_generated_csvs(project_root, tmp_path):
    """
    The fresh-clone case, proven rather than asserted.

    Copies in only what `python src/generate_data.py` produces — no
    `campaigns_clean.csv`, no `transactions_clean.csv` — and loads from there.
    Before this module existed, `generate_report.py` raised FileNotFoundError
    on exactly this input.
    """
    import shutil

    raw = project_root / "data" / "raw"
    generated = ["campaigns.csv", "customers.csv", "transactions.csv",
                 "ab_test_campaigns.csv"]
    for name in generated:
        shutil.copy2(raw / name, tmp_path / name)

    assert not list(tmp_path.glob("*_clean.csv"))

    fresh = load_from_paths(tmp_path)
    assert fresh.campaigns.shape == (3481, 13)
    assert fresh.transactions.shape == (40690, 8)

    # Seven checks flag, but only six distinct defects were seeded:
    # `conversions_exceed_clicks` and `impossible_cvr` catch the same 4 rows.
    flagged = {i.key for i in fresh.quality.flagged}
    assert flagged == {
        "missing_customer_id", "missing_age_group", "duplicate_rows",
        "negative_spend", "orphan_transactions",
        "conversions_exceed_clicks", "impossible_cvr",
    }


def test_partial_upload_degrades_to_capabilities_not_errors(project_root):
    """Campaigns-only must still work — it just unlocks fewer modules."""
    from analytics.ingest import build_bundle

    raw = project_root / "data" / "raw"
    campaigns_only = {"campaigns": pd.read_csv(raw / "campaigns.csv", parse_dates=["date"])}
    b = build_bundle(campaigns_only, source="test")

    caps = b.capabilities
    assert caps.overview and caps.marketing and caps.forecast
    assert not caps.profitability
    assert not caps.cohorts
    assert not caps.experiments
    assert b.customers is None
