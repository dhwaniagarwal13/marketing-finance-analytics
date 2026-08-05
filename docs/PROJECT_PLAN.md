# Project plan

How this project was actually sequenced, the decisions made along the way, and what's
still open. Grounded in the real commit history, not a retrofit narrative.

## Objective

Simulate a full Business/Marketing Analyst engagement for a mid-size DTC company: not
just descriptive metrics, but a consulting-style chain of Business Question →
Methodology → Analysis → Visualization → Key Insight → quantified Business
Recommendation, on a synthetic but fully reproducible dataset.

## Build order and why

The project was built in two distinct passes, not one continuous sprint.

**Pass 1 — the analyst engagement itself.** Six notebooks (data quality audit →
marketing performance → customer analytics → financial analysis → advanced analytics
→ executive report), the 21-query SQL layer, the data dictionary and assumptions doc,
and the generated PDF executive report. This is the actual deliverable a
business/marketing analyst would hand to leadership, and it was scoped and finished
as a complete, self-contained unit before anything else was touched.

**Pass 2 — productionizing it.** Once the analysis itself was validated, the notebook
logic was extracted into a tested `analytics/` package (rather than leaving the real
logic trapped in notebook cells), then wrapped with a FastAPI backend, a React/
TypeScript live dashboard, and Docker + Fly.io deploy config. This turned a
one-off analysis into something that runs as a live service, not just a report.

The ordering matters: refactoring analysis logic into a package *before* it's been
validated in notebook form risks locking in a wrong formula behind a clean interface.
Doing it after means the package is a faithful extraction of already-checked logic,
not a rewrite that has to be re-trusted from scratch.

## Decisions that shaped the scope

- **Fully synthetic, seeded data — no external downloads, no API keys.** Anyone
  cloning the repo gets byte-identical results from `src/generate_data.py`. This
  was a deliberate reproducibility choice over using a real (and therefore
  gated, licensed, or non-reproducible) dataset.
- **Intentional data-quality issues seeded into the generator.** Negative spend,
  duplicate rows, orphan transactions, impossible CTR/CVR — planted specifically
  so the Chapter 1 data-quality audit has real anomalies to catch, rather than
  auditing a suspiciously clean dataset.
- **Every recommendation is quantified in dollars**, not left as a directive like
  "improve retention." The budget-reallocation, creative-variant, and market-pilot
  recommendations all carry a modeled dollar impact, because an unquantified
  recommendation isn't something a stakeholder can prioritize against another one.
- **`churn_ml` is a declared capability, not a shipped feature.** `analytics/ingest.py`
  carries a `churn_ml` flag and `scikit-learn` is a declared dependency, but there is
  no `analytics/churn.py` — this was deliberately scoped out rather than shipped
  half-built. Flagging the capability without building it lets the ingestion contract
  anticipate the feature without pretending it exists.

## What's still open

From the README's own future-improvements list — these are real, prioritized next
steps, not filler:

1. Deploy the executive dashboard as a live Streamlit/Dash app instead of a static
   notebook export.
2. Move to SARIMA/Prophet once more than two years of history exist, to properly
   separate trend from annual seasonality — the current forecast is backtested
   but limited by how little history a synthetic two-year dataset can provide.
3. Add a marketing-mix modelling layer instead of assuming constant marginal ROI
   in the budget-reallocation model.
4. Automate the data-quality checks as a scheduled test suite (dbt tests or Great
   Expectations) against the SQLite/warehouse layer, instead of a notebook-driven
   one-time audit.
5. Build out `churn_ml` for real, now that the ingestion contract already anticipates it.
