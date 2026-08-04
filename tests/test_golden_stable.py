"""
Guards the Phase 0 baseline itself.

These assert that the CSVs on disk still produce the numbers frozen in
`expected.json`. If `generate_data.py` is re-run with a different seed, or the
raw CSVs are edited, these fail loudly — which is what you want, because every
parity test downstream trusts this baseline.

They deliberately test `src/generate_report.py` (the pre-refactor code path), so
they stay meaningful as the `analytics/` package is built alongside it.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pytest

TOL = 1e-6


@pytest.fixture(scope="module")
def gr():
    import generate_report

    return generate_report


@pytest.fixture(scope="module")
def data(gr):
    return gr.load_data()


def test_source_row_counts(data):
    campaigns, customers, transactions, ab_test = data
    assert campaigns.shape == (3481, 13)
    assert customers.shape == (6000, 9)
    assert transactions.shape == (40690, 8)
    assert ab_test.shape == (60, 7)


def test_headline_kpis_match_golden(gr, data, golden):
    campaigns, customers, transactions, _ = data
    actual = gr.compute_kpis(campaigns, customers, transactions)
    expected = golden["generate_report"]["compute_kpis"]

    assert set(actual) == set(expected)
    for key, exp in expected.items():
        assert actual[key] == pytest.approx(exp, rel=TOL), key


def test_channel_profitability_matches_golden(gr, data, golden):
    campaigns, customers, transactions, _ = data
    actual = gr.compute_channel_profitability(campaigns, customers, transactions)
    expected = golden["generate_report"]["compute_channel_profitability"]

    assert list(actual.index) == expected["index"]
    assert list(actual.columns) == expected["columns"]
    for row, exp_row in zip(actual.to_dict("records"), expected["records"]):
        for col, exp in exp_row.items():
            assert row[col] == pytest.approx(exp, rel=TOL), col


def test_budget_reallocation_matches_golden(gr, data, golden):
    campaigns, customers, transactions, _ = data
    prof = gr.compute_channel_profitability(campaigns, customers, transactions)
    actual = gr.compute_budget_reallocation(prof)
    expected = golden["generate_report"]["compute_budget_reallocation"]

    assert actual["from_channels"] == expected["from_channels"]
    assert actual["to_channels"] == expected["to_channels"]
    for key in ("shift_amount", "net_profit_change", "net_revenue_change"):
        assert actual[key] == pytest.approx(expected[key], rel=TOL), key


def test_ab_test_matches_golden(gr, data, golden):
    *_, ab_test = data
    actual = gr.compute_ab_test(ab_test)
    expected = golden["generate_report"]["compute_ab_test"]
    for key, exp in expected.items():
        assert actual[key] == pytest.approx(exp, rel=TOL), key


def test_forecast_matches_golden(gr, data, golden):
    campaigns, *_ = data
    expected = golden["generate_report"]["compute_forecast"]
    assert gr.compute_forecast(campaigns) == pytest.approx(expected, rel=TOL)


def test_known_forecast_defect_is_still_present(gr, data, golden):
    """
    Documents a defect rather than a requirement (see task #2).

    `generate_campaign_daily` has no time-trend term, so monthly revenue only
    varies with how many of the 42 campaigns happen to overlap. The linear fit
    reads that noise as a trend and extrapolates to a next-quarter total well
    below the historical run rate — and to negative revenue within ~10 months.

    Phase 5 replaces this with an honest forecast. When that lands, this test
    should be deleted along with the defect.
    """
    import numpy as np
    import pandas as pd

    campaigns, *_ = data
    monthly = campaigns.groupby(pd.Grouper(key="date", freq="MS"))["revenue"].sum()
    slope, intercept = np.polyfit(np.arange(len(monthly)), monthly.values, 1)

    assert slope < 0, "defect changed shape — revisit the Phase 5 forecast fix"
    months_until_negative = -intercept / slope - len(monthly)
    assert months_until_negative < 12, (
        f"linear forecast goes negative in {months_until_negative:.1f} months"
    )
