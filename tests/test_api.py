"""
API contract tests.

Runs against the real app with the real demo dataset — no mocks, because the
thing worth testing is that the engine's output survives serialization and
reaches a client intact.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["datasets_loaded"] >= 1


def test_theme_matches_the_palette_module(client):
    from analytics.palette import CATEGORICAL, CHANNEL_COLORS

    body = client.get("/api/theme").json()
    assert body["categorical"] == CATEGORICAL
    assert body["channel_colors"] == CHANNEL_COLORS
    # The accessibility constraint has to reach the frontend, not just the docstring.
    assert set(body["low_contrast_hues"]) == {"#1baf7a", "#eda100", "#e87ba4"}


def test_params_schema_covers_every_field(client):
    from dataclasses import fields

    from analytics.config import AnalysisParams

    body = client.get("/api/params/schema").json()
    assert {f["name"] for f in body["fields"]} == {f.name for f in fields(AnalysisParams)}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def test_full_snapshot(client):
    body = client.get("/api/analysis").json()

    assert body["as_of"] == "2025-12-31"
    assert set(body["modules"]) == {"marketing", "customers", "finance",
                                    "experiments", "forecast"}
    assert all(m["status"] == "ok" for m in body["modules"].values())
    assert body["capabilities"]["profitability"] is True


def test_snapshot_reproduces_the_published_kpis(client, golden):
    kpis = client.get("/api/analysis").json()["modules"]["finance"]["data"]["kpis"]
    expected = golden["generate_report"]["compute_kpis"]

    for key in ("total_revenue", "total_spend", "total_net_profit", "blended_cac"):
        assert kpis[key]["value"] == pytest.approx(expected[key], rel=1e-9), key


def test_response_contains_no_nan_tokens(client):
    """
    `NaN` is not valid JSON and `JSON.parse` rejects it.

    Checking the raw bytes rather than the parsed body, because Python's json
    module accepts the token that browsers refuse.
    """
    raw = client.get("/api/analysis").text
    assert "NaN" not in raw
    assert "Infinity" not in raw
    json.loads(raw)  # parses under strict rules


def test_as_of_slices_the_cursor(client):
    body = client.get("/api/analysis", params={"as_of": "2024-12-31"}).json()
    assert body["as_of"] == "2024-12-31"
    assert body["modules"]["marketing"]["status"] == "ok"


def test_early_cursor_degrades_gracefully(client):
    body = client.get("/api/analysis", params={"as_of": "2024-03-05"}).json()
    assert body["modules"]["forecast"]["status"] == "insufficient_data"
    assert body["modules"]["forecast"]["reason"]
    # A failing module must not take the others down with it.
    assert body["modules"]["marketing"]["status"] == "ok"


def test_unknown_dataset_is_404_with_a_useful_message(client):
    r = client.get("/api/analysis", params={"dataset": "nope"})
    assert r.status_code == 404
    assert "expired" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Parameter overrides
# ---------------------------------------------------------------------------
def test_shift_pct_override_changes_the_reallocation(client):
    base = client.get("/api/analysis/finance").json()
    doubled = client.get("/api/analysis/finance", params={"shift_pct": 0.30}).json()

    a = base["data"]["reallocation"]["shift_amount"]
    b = doubled["data"]["reallocation"]["shift_amount"]
    assert b == pytest.approx(a * 2, rel=1e-9)
    assert base["params_hash"] != doubled["params_hash"]


def test_out_of_range_params_are_rejected_before_pandas_runs(client):
    assert client.get("/api/analysis/customers", params={"rfm_bins": 9999}).status_code == 422
    assert client.get("/api/analysis/finance", params={"shift_pct": 5}).status_code == 422
    assert client.get("/api/analysis/experiments", params={"alpha": 2}).status_code == 422


def test_ltv_denominator_switch_recovers_the_published_number(client, golden):
    body = client.get("/api/analysis/finance",
                      params={"ltv_denominator": "transacting_customers"}).json()
    expected = golden["generate_report"]["compute_kpis"]["blended_ltv"]
    assert body["data"]["kpis"]["blended_ltv"]["value"] == pytest.approx(expected, rel=1e-9)


def test_marketing_by_dimension(client):
    body = client.get("/api/analysis/marketing/by", params={"by": "device"}).json()
    assert body["status"] == "ok"
    assert {row["device"] for row in body["data"]} == {"Mobile", "Desktop", "Tablet"}


def test_invalid_dimension_is_refused(client):
    body = client.get("/api/analysis/marketing/by", params={"by": "spend"}).json()
    assert body["status"] == "error"
    assert "cannot group by" in body["reason"]


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------
def test_quality_reports_what_was_removed_and_why(client):
    body = client.get("/api/analysis/quality").json()
    issues = {i["key"]: i for i in body["quality"]["issues"]}

    assert issues["orphan_transactions"]["issue_count"] == 5
    assert issues["orphan_transactions"]["examples"]
    assert issues["orphan_transactions"]["production_handling"]
    assert body["provenance"]["rows_raw"]["campaigns"] == 3494
    assert body["provenance"]["rows_clean"]["campaigns"] == 3481
