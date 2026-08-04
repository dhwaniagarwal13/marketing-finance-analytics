"""
Parity: the engine must reproduce the notebooks exactly.

This is the test that makes the whole refactor defensible. Every value here is
compared against `tests/golden/expected.json`, which was captured by executing
the notebooks' own cell source before any code moved.

Where the engine deliberately diverges from a notebook, the divergence is
asserted explicitly rather than tolerated — see the `ltv_denominator` and
cohort-refund cases in `analytics/config.py`.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics import customers, experiments, finance, forecast, marketing
from analytics.config import DEFAULTS
from analytics.ingest import load_from_paths

REL = 1e-9


@pytest.fixture(scope="module")
def bundle(project_root):
    return load_from_paths(project_root / "data" / "raw")


# ---------------------------------------------------------------------------
# Golden accessors
# ---------------------------------------------------------------------------
def g_frame(golden: dict, section: str, name: str) -> pd.DataFrame:
    node = golden[section][name]
    assert node["_type"] == "DataFrame", f"{section}.{name} is not a DataFrame"
    return pd.DataFrame(node["records"], index=node["index"])


def g_float(value) -> float:
    """
    Coerce a golden value to float.

    JSON cannot represent NaN or Infinity, so the capture stores them as the
    strings "nan" / "inf". `pd.isna("nan")` is False, so they have to be run
    through `float()` before any missingness check.
    """
    return float("nan") if value is None else float(value)


def g_summary(golden: dict, section: str, name: str) -> dict:
    """
    Column aggregates for frames too large to have been captured row by row.

    The capture stores full records only up to 200 rows; beyond that it keeps
    per-column sum/mean/min/max, which still pins the result exactly — a single
    changed score would move the sum.
    """
    node = golden[section][name]
    assert "summary" in node, f"{section}.{name} was captured verbatim, use g_frame"
    return node["summary"]


def g_series(golden: dict, section: str, name: str) -> pd.Series:
    node = golden[section][name]
    assert node["_type"] == "Series", f"{section}.{name} is not a Series"
    return pd.Series(node["values"])


def assert_frames_match(actual: pd.DataFrame, expected: pd.DataFrame,
                        columns: list[str], strict_index: bool = True):
    """Compare on shared columns, aligned by index rather than row order."""
    if strict_index:
        assert set(actual.index) == set(expected.index)
    else:
        assert set(actual.index) <= set(expected.index)
    for col in columns:
        a = actual[col].astype(float)
        e = expected.loc[a.index, col].astype(float)
        for key in a.index:
            if pd.isna(e[key]):
                assert pd.isna(a[key]), f"{col}[{key}]: expected NaN, got {a[key]}"
            else:
                assert a[key] == pytest.approx(e[key], rel=REL), f"{col}[{key}]"


# ---------------------------------------------------------------------------
# Notebook 02 — marketing
# ---------------------------------------------------------------------------
def test_funnel_matches_nb02(bundle, golden):
    actual = marketing.funnel(bundle.campaigns)
    overall = g_series(golden, "02_Marketing_Performance", "overall")
    kpis = g_series(golden, "02_Marketing_Performance", "kpis")

    assert actual["impressions"] == overall["Impressions"]
    assert actual["clicks"] == overall["Clicks"]
    assert actual["conversions"] == overall["Conversions"]
    assert actual["spend"] == pytest.approx(overall["Spend"], rel=REL)
    assert actual["revenue"] == pytest.approx(overall["Revenue"], rel=REL)

    for engine_key, nb_key in [("ctr", "CTR"), ("cvr", "CVR"), ("cpc", "CPC"),
                               ("cpa", "CPA"), ("roas", "ROAS")]:
        assert actual[engine_key] == pytest.approx(kpis[nb_key], rel=REL), engine_key


def test_channel_kpis_match_nb02(bundle, golden):
    actual = marketing.groupby_kpis(bundle.campaigns, "channel")
    expected = g_frame(golden, "02_Marketing_Performance", "channel_perf")

    assert_frames_match(actual, expected,
                        ["impressions", "clicks", "conversions", "spend", "revenue",
                         "ctr", "cvr", "cpc", "cpa", "roas"])
    # ROAS-descending order is what the chart and the table both rely on.
    assert list(actual.index) == list(expected.index)


def test_device_kpis_match_nb02(bundle, golden):
    actual = marketing.groupby_kpis(bundle.campaigns, "device")
    expected = g_frame(golden, "02_Marketing_Performance", "device_perf")
    assert_frames_match(actual, expected,
                        ["impressions", "clicks", "conversions", "spend",
                         "revenue", "ctr", "cvr", "cpa", "roas"])


def test_country_kpis_match_nb02(bundle, golden):
    actual = marketing.groupby_kpis(bundle.campaigns, "country")
    expected = g_frame(golden, "02_Marketing_Performance", "country_perf")
    assert_frames_match(actual, expected, ["spend", "revenue", "cpc", "cpa", "roas"])
    assert list(actual.index) == list(expected.index)


def test_monthly_revenue_matches_nb02(bundle, golden):
    actual = marketing.monthly_revenue(bundle.campaigns, DEFAULTS)
    expected = g_series(golden, "02_Marketing_Performance", "monthly")

    assert len(actual) == len(expected) == 23
    for ts, value in zip(actual.index, actual.values):
        assert value == pytest.approx(expected[str(ts)], rel=REL), str(ts)


def test_campaign_leaderboard_matches_nb02(bundle, golden):
    actual = marketing.campaign_leaderboard(bundle.campaigns, min_spend=100, n=5)
    expected = g_frame(golden, "02_Marketing_Performance", "camp_perf")

    assert actual["n_campaigns"] == len(expected)
    best = expected.sort_values("roas", ascending=False).iloc[0]
    assert actual["top"][0]["campaign_name"] == best["campaign_name"]
    assert actual["top"][0]["roas"] == pytest.approx(best["roas"], rel=REL)


# ---------------------------------------------------------------------------
# Notebook 03 — customers
# ---------------------------------------------------------------------------
def test_rfm_scores_match_nb03(bundle, golden):
    actual = customers.rfm_table(bundle, DEFAULTS)
    expected = g_summary(golden, "03_Customer_Analytics", "rfm")

    assert len(actual) == 5971
    # NB03 froze the reference date to the last day of data; the engine derives
    # the same value from the data itself.
    assert actual.attrs["reference_date"] == "2025-12-31"
    assert not actual.attrs["degraded"]

    for col in ("recency_days", "frequency", "monetary",
                "R_score", "F_score", "M_score", "rfm_score"):
        for stat in ("sum", "mean", "min", "max"):
            assert actual[col].agg(stat) == pytest.approx(
                expected[col][stat], rel=REL), f"{col}.{stat}"


def test_vectorized_segments_match_the_row_wise_apply(bundle, golden):
    """
    `np.select` must reproduce NB03's if-chain exactly.

    The per-customer frame was too large to capture row by row, but segment
    *counts* were: a single misrouted customer moves two of these six numbers.
    """
    rfm = customers.rfm_table(bundle, DEFAULTS)
    actual = rfm["segment"].value_counts()
    expected = g_frame(golden, "03_Customer_Analytics", "segment_summary")

    assert set(actual.index) == set(expected.index)
    for segment in expected.index:
        assert actual[segment] == int(expected.loc[segment, "customers"]), segment


def test_segment_summary_matches_nb03(bundle, golden):
    rfm = customers.rfm_table(bundle, DEFAULTS)
    actual = customers.segment_summary(rfm)
    expected = g_frame(golden, "03_Customer_Analytics", "segment_summary")

    assert list(actual.index) == list(expected.index)
    assert_frames_match(actual, expected,
                        ["customers", "avg_recency_days", "avg_frequency",
                         "avg_monetary", "pct_of_base"])


def test_cohorts_reproduce_nb03_when_refunds_are_included(bundle, golden):
    """
    NB03 counted refunded purchases as cohort activity. Setting the parameter
    back must recover its retention matrix exactly.
    """
    from dataclasses import replace

    params = replace(DEFAULTS, include_refunds_in_cohorts=True, cohort_min_size=0)
    actual = customers.cohort_retention(bundle, params)
    expected = g_frame(golden, "03_Customer_Analytics", "retention_pivot")

    assert actual["n_cohorts"] == len(expected)
    by_cohort = {c["cohort"]: c for c in actual["cohorts"]}

    for cohort in expected.index:
        cells = {c["month"]: c["retention_pct"] for c in by_cohort[cohort]["cells"]}
        for month_col in expected.columns:  # JSON keys, so strings
            want = g_float(expected.loc[cohort, month_col])
            got = cells[int(month_col)]
            if pd.isna(want):
                assert got is None, f"{cohort}[{month_col}]"
            else:
                assert got == pytest.approx(want, rel=REL), f"{cohort}[{month_col}]"


def test_default_cohorts_exclude_refunds_and_so_differ_from_nb03(bundle):
    """
    Deliberate divergence: NB03's RFM excluded refunds while its cohorts
    included them — two definitions of a purchase in one chapter.
    """
    from dataclasses import replace

    unified = customers.cohort_retention(bundle, DEFAULTS)
    original = customers.cohort_retention(
        bundle, replace(DEFAULTS, include_refunds_in_cohorts=True))

    assert unified["counts_include_refunds"] is False
    assert original["counts_include_refunds"] is True
    assert unified["mean_month_0"] < original["mean_month_0"]


def test_month_0_to_1_is_the_steepest_drop(bundle):
    """The report's central retention claim, recomputed rather than asserted."""
    result = customers.cohort_retention(bundle, DEFAULTS)
    assert result["month_0_to_1_drop"] > 0

    means = {}
    for cohort in result["cohorts"]:
        for cell in cohort["cells"]:
            if cell["retention_pct"] is not None:
                means.setdefault(cell["month"], []).append(cell["retention_pct"])
    avg = {m: sum(v) / len(v) for m, v in sorted(means.items())}
    drops = [avg[m] - avg[m + 1] for m in list(avg)[:-1] if m + 1 in avg]
    assert drops[0] == max(drops)


def test_retention_by_channel_matches_nb03(bundle, golden):
    from dataclasses import replace

    params = replace(DEFAULTS, include_refunds_in_cohorts=True)
    actual = customers.retention_by_channel(bundle, params)
    expected = g_frame(golden, "03_Customer_Analytics", "channel_retention")

    assert len(actual) == len(expected)
    key = ["acquisition_channel", "months_since_acquisition"]
    merged = actual.merge(expected, on=key, suffixes=("_a", "_e"))
    assert len(merged) == len(expected)
    for _, row in merged.iterrows():
        assert row["retention_pct_a"] == pytest.approx(
            float(row["retention_pct_e"]), rel=REL)


def test_value_by_plan_matches_nb03(bundle, golden):
    actual = customers.value_by_plan(bundle, DEFAULTS)
    expected = g_frame(golden, "03_Customer_Analytics", "plan_value")
    assert_frames_match(actual, expected,
                        ["customers", "avg_purchases", "avg_lifetime_profit"])


def test_unobservable_cohort_cells_are_labelled(bundle):
    """
    A blank cell must be distinguishable from a zero one. The most recent
    cohort has almost no observable future at the cursor.
    """
    # Slice the bundle rather than passing a bare date: the cursor has to move
    # the data as well as the label, or the mask describes a window the frame
    # does not actually respect.
    sliced = bundle.as_of("2025-06-30")
    result = customers.cohort_retention(sliced, DEFAULTS)

    newest = max(result["cohorts"], key=lambda c: c["cohort"])
    unobserved = [c for c in newest["cells"] if not c["observed"]]
    assert unobserved, "newest cohort should have months that have not happened yet"
    assert all(c["retention_pct"] is None for c in unobserved)

    # And the converse: an observed cell that is genuinely zero must not be
    # confused with one that simply has not happened.
    oldest = min(result["cohorts"], key=lambda c: c["cohort"])
    assert all(c["observed"] for c in oldest["cells"])


# ---------------------------------------------------------------------------
# Notebook 04 — finance
# ---------------------------------------------------------------------------
def test_profitability_matches_nb04(bundle, golden):
    actual = finance.profitability(bundle, DEFAULTS)
    expected = g_frame(golden, "04_Financial_Analysis", "profitability")

    assert_frames_match(actual, expected,
                        ["campaign_revenue", "marketing_spend", "customer_gross_profit",
                         "net_profit", "revenue_rank", "profit_rank", "rank_shift",
                         "contribution_margin", "profit_per_customer"])


def test_cac_ltv_matches_nb04(bundle, golden):
    actual = finance.cac_ltv_by_channel(bundle, DEFAULTS)
    expected = g_frame(golden, "04_Financial_Analysis", "ltv_cac")

    assert_frames_match(actual, expected, ["cac", "ltv"])

    # Every channel with real acquisition cost must match the notebook exactly.
    defined = actual.loc[~actual["ratio_undefined"]]
    assert_frames_match(defined, expected, ["ltv_cac_ratio"], strict_index=False)
    assert list(defined.index) == [c for c in expected.index if c != "Organic"]


def test_zero_cac_channel_is_flagged_rather_than_infinite(bundle, golden):
    """
    Deliberate divergence from NB04.

    Organic has no attributable spend, so NB04's `ltv / cac` produced `inf`.
    matplotlib then dropped the bar entirely — Organic is missing from
    reports/figures/04_ltv_cac_ratio.png while the notebook text discusses it.
    `inf` is also not representable in JSON, so the API could not serve it.
    """
    expected = g_frame(golden, "04_Financial_Analysis", "ltv_cac")
    assert float(expected.loc["Organic", "ltv_cac_ratio"]) == float("inf")

    actual = finance.cac_ltv_by_channel(bundle, DEFAULTS)
    organic = actual.loc["Organic"]

    assert organic["cac"] == 0
    assert organic["ratio_undefined"] is True or bool(organic["ratio_undefined"])
    assert pd.isna(organic["ltv_cac_ratio"])
    assert organic["clears_benchmark"] is None
    # Undefined ratio ranks first, not last.
    assert actual.index[0] == "Organic"


def test_reallocation_matches_nb04(bundle, golden):
    table = finance.profitability(bundle, DEFAULTS)
    actual = finance.reallocation(table, DEFAULTS)
    nb = golden["04_Financial_Analysis"]

    assert actual["from_channels"] == nb["bottom2"]["index"]
    assert actual["to_channels"] == nb["top2"]["index"]

    for engine_key, nb_key in [
        ("shift_amount", "shift_amount"),
        ("profit_lost", "profit_lost"),
        ("profit_gained", "profit_gained"),
        ("net_profit_change", "net_expected_profit_change"),
        ("revenue_lost", "revenue_lost"),
        ("revenue_gained", "revenue_gained"),
        ("net_revenue_change", "net_expected_revenue_change"),
    ]:
        assert actual[engine_key] == pytest.approx(nb[nb_key], rel=REL), engine_key

    assert actual["basis"] == "configured"


def test_reallocation_plan_matches_nb04(bundle, golden):
    table = finance.profitability(bundle, DEFAULTS)
    actual = {row["channel"]: row for row in finance.reallocation(table, DEFAULTS)["plan"]}
    expected = g_frame(golden, "04_Financial_Analysis", "reallocation")

    assert set(actual) == set(expected.index)
    for channel in expected.index:
        for col in ("current_spend", "recommended_spend", "change", "change_pct"):
            assert actual[channel][col] == pytest.approx(
                float(expected.loc[channel, col]), rel=REL), f"{channel}.{col}"


# ---------------------------------------------------------------------------
# Notebook 05 — experiments
# ---------------------------------------------------------------------------
def test_ab_test_matches_nb05(bundle, golden):
    actual = experiments.ab_test(bundle.ab_test, DEFAULTS)
    nb = golden["05_Advanced_Analytics"]

    for engine_key, nb_key in [
        ("lift_pct", "lift_pct"), ("z_stat", "z_stat"), ("p_value_z", "p_value_z"),
        ("ci_low", "ci_low"), ("ci_high", "ci_high"),
        ("t_stat", "t_stat"), ("p_value_t", "p_value_t"),
    ]:
        assert actual[engine_key] == pytest.approx(nb[nb_key], rel=1e-6), engine_key

    assert actual["significant"] is nb["significant"]
    assert actual["ci_excludes_zero"] is True


def test_ab_projection_matches_nb05(bundle, golden):
    actual = experiments.ab_test(bundle.ab_test, DEFAULTS)["projection"]
    nb = golden["05_Advanced_Analytics"]

    assert actual["incremental_conversions"] == pytest.approx(
        nb["incremental_conversions"], rel=1e-6)
    assert actual["incremental_revenue"] == pytest.approx(
        nb["incremental_revenue"], rel=1e-6)


def test_ab_test_before_the_experiment_started_is_typed(bundle):
    """The experiment starts 2025-09-01; before that the module must not guess."""
    from analytics.errors import InsufficientData

    early = bundle.as_of("2025-08-01")
    with pytest.raises(InsufficientData):
        experiments.ab_test(early.ab_test, DEFAULTS)


# ---------------------------------------------------------------------------
# Notebook 05 — forecast
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def monthly(bundle):
    series = marketing.monthly_revenue(bundle.campaigns, DEFAULTS)
    series.index = series.index.to_period("M")
    return series


def test_backtest_matches_nb05(monthly, golden):
    actual = forecast.backtest(monthly, DEFAULTS)
    expected = g_frame(golden, "05_Advanced_Analytics", "accuracy")

    assert actual["train_months"] == 20
    assert actual["test_months"] == 3
    assert not actual["methods_skipped"]

    for method, res in actual["results"].items():
        label = res["label"]
        assert res["rmse"] == pytest.approx(float(expected.loc[label, "RMSE"]), rel=1e-6), label
        assert res["mae"] == pytest.approx(float(expected.loc[label, "MAE"]), rel=1e-6), label

    # RMSE ranking, and therefore the selected method, must be identical.
    assert [actual["results"][m]["label"] for m in actual["ranked"]] == list(expected.index)
    assert actual["best_label"] == golden["05_Advanced_Analytics"]["best_method"]


def test_backtest_method_forecasts_match_nb05(monthly, golden):
    actual = forecast.backtest(monthly, DEFAULTS)["results"]
    nb = golden["05_Advanced_Analytics"]

    for method, nb_key in [("moving_average", "ma_forecast"),
                           ("linear_trend", "lt_forecast"),
                           ("arima", "arima_forecast")]:
        for got, want in zip(actual[method]["forecast"], nb[nb_key]):
            assert got == pytest.approx(want, rel=1e-6), method


def test_next_quarter_forecast_matches_nb05(monthly, golden):
    actual = forecast.select_and_forecast(monthly, DEFAULTS)
    nb = golden["05_Advanced_Analytics"]

    assert actual["label"] == nb["best_method"]
    for got, want in zip([m["forecast_revenue"] for m in actual["months"]],
                         nb["next_quarter_forecast"]):
        assert got == pytest.approx(want, rel=1e-6)

    # The PDF prints the unrounded total; NB05 rounds each month first.
    assert actual["total"] == pytest.approx(
        golden["generate_report"]["compute_forecast"], rel=1e-6)
    assert round(actual["total"]) == nb["next_quarter_total"]


def test_forecast_is_the_only_path_nb06_should_have_used(monthly, golden):
    """
    NB06 refit a linear trend directly instead of using NB05's backtest winner.

    They agree today only because Linear Trend wins. Asserting both the value
    and the reason keeps that coincidence from being mistaken for a guarantee.
    """
    actual = forecast.select_and_forecast(monthly, DEFAULTS)
    assert actual["method"] == "linear_trend"
    assert actual["total"] == pytest.approx(
        golden["06_Executive_Report"]["next_quarter_forecast_total"], rel=1e-6)


def test_trend_diagnostics_flag_the_noise_fit(monthly):
    """
    Phase 5 tracking: the generator has no time-trend term, so the fitted
    slope is an artefact of which campaigns happen to overlap each month.
    """
    d = forecast.trend_diagnostics(monthly)
    assert d["available"]
    assert d["slope_per_month"] < 0
    assert d["months_until_zero"] is not None and d["months_until_zero"] < 12


# ---------------------------------------------------------------------------
# generate_report.py — the PDF's numbers
# ---------------------------------------------------------------------------
def test_headline_kpis_match_the_pdf(bundle, golden):
    """
    All but one KPI must match the published report exactly.

    `blended_ltv` deliberately does not: the report averaged over transacting
    customers while dividing CAC by all customers, so its LTV:CAC mixed bases.
    The engine defaults to a consistent all-customer denominator.
    """
    actual = finance.headline_kpis(bundle, DEFAULTS)
    expected = golden["generate_report"]["compute_kpis"]

    for key in ("total_revenue", "total_spend", "total_net_profit", "blended_cac",
                "blended_roas", "blended_roi", "blended_cvr", "repeat_rate"):
        assert actual[key]["value"] == pytest.approx(expected[key], rel=REL), key

    assert actual["blended_ltv"]["value"] == pytest.approx(222.631727, rel=1e-6)
    assert expected["blended_ltv"] == pytest.approx(223.713006, rel=1e-6)
    assert actual["ltv_cac_ratio"]["value"] == pytest.approx(6.624837, rel=1e-6)


def test_transacting_denominator_reproduces_the_published_ltv(bundle, golden):
    """Flipping the parameter back must recover the report's number exactly."""
    from dataclasses import replace

    params = replace(DEFAULTS, ltv_denominator="transacting_customers")
    actual = finance.headline_kpis(bundle, params)
    expected = golden["generate_report"]["compute_kpis"]

    assert actual["blended_ltv"]["value"] == pytest.approx(expected["blended_ltv"], rel=REL)
    assert actual["ltv_cac_ratio"]["value"] == pytest.approx(expected["ltv_cac_ratio"], rel=REL)
