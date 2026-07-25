# Business Assumptions — Synthetic Data Generator

This document records every assumption baked into `src/generate_data.py`.
The dataset is synthetic but **intentionally designed**: every rate, margin,
and probability below was chosen to produce a coherent, analyzable business
story rather than pure randomness. All generation is seeded (`SEED = 42`), so
re-running the script reproduces byte-identical output.

The company simulated is a mid-size, subscription-plus-purchases DTC/e-commerce
business operating across five countries, acquiring customers through seven
marketing channels, over a two-year window: **2024-01-01 to 2025-12-31**.

---

## 1. Marketing Channels

| Channel | Launch date | Role in the mix |
|---|---|---|
| Google Ads | 2024-01-01 | Paid search — highest intent, highest CPC |
| Facebook | 2024-01-01 | Paid social — broad reach, mid CVR |
| Instagram | 2024-01-01 | Paid social — visual/impulse, lower CVR than Facebook |
| Email | 2024-01-01 | Owned channel — near-zero cost, highest CVR |
| Affiliate | 2024-01-01 | Performance/referral — commission-style cost |
| TikTok | 2024-07-01 | Newest channel, added mid-2024 to model channel-mix evolution |
| Organic | 2024-01-01 | Unpaid/SEO — zero direct media spend |

Baseline daily impressions, CTR, and CVR ranges are channel-specific (see
`CHANNEL_PARAMS` in `generate_data.py`) — e.g., Email is modeled with a ~12%
CTR (open+click on a send) and ~6% CVR, reflecting an owned, highly-engaged
audience; TikTok is modeled with the lowest baseline CVR (~1.8%), reflecting
an earlier-funnel, lower-intent audience.

## 2. Funnel Modifiers

- **Objective** (`Awareness` / `Consideration` / `Conversion`) reshapes the
  funnel: Awareness campaigns get 1.6x impressions but 0.45x CTR and 0.45x CVR
  multipliers; Conversion campaigns get 0.65x impressions but 1.5x CVR —
  modeling the classic reach-vs-efficiency tradeoff.
- **Device**: Desktop converts best (1.15x CVR multiplier), Tablet is neutral
  (0.95x), Mobile converts worst (0.90x) — reflecting higher purchase friction
  on mobile checkout flows.
- **Audience**: Retargeting converts best (1.55x), Returning next (1.25x),
  Lookalike near-neutral (0.95x), New converts worst (0.80x) — standard
  funnel-stage economics.
- **Country CPC multiplier**: US (1.35x) and UK (1.15x) are the most expensive
  auction markets; India is cheapest (0.45x), reflecting real-world CPC
  disparities across ad markets.

## 3. Seasonality

- **Holiday demand spikes** are modeled as date-window multipliers on
  impressions/conversions:
  - Black Friday / Cyber Monday: **+85–90%**
  - Christmas week: **+45–50%**
  - Back-to-school (mid-Aug–early-Sep): **+20–22%**
- **Weekday effect**: weekend days run at 0.90x volume relative to weekdays,
  a mild generic dampening (no single channel is modeled as weekend-peaking).

## 4. Customers

- **6,000 customers** acquired over the two-year window.
- Acquisition volume per channel is weighted proportional to that channel's
  total campaign conversions, so `customers.csv` stays broadly consistent
  with `campaigns.csv` (this is a simplification — in reality "conversions"
  in ad platforms include more than first-time signups, e.g. repeat-purchase
  conversions, so the two tables are directionally, not perfectly, reconciled).
- **Subscription plan mix is channel-dependent**: paid-search/affiliate skew
  toward higher-tier plans (Google Ads: 10% Enterprise, Affiliate: 15%
  Enterprise) since those channels are modeled as targeting higher-intent,
  higher-budget audiences; social channels (TikTok, Instagram) skew toward
  Free/Basic (TikTok: 55% Free), reflecting a younger, lower-spend audience.
- **Demographics**: age group skews 25–34 (32%), gender is modeled near-even
  (48% female / 48% male / 4% other), cities are drawn from a fixed pool per
  country.

## 5. Purchases, Retention & Churn

- Each customer's **first transaction is their acquisition purchase**,
  dated on `acquisition_date`.
- **Purchase cadence** (average days between purchases) and **churn
  probability per purchase** both depend on subscription plan:

  | Plan | Avg. days between purchases | Churn probability per purchase |
  |---|---|---|
  | Free | 55 | 22% |
  | Basic | 40 | 16% |
  | Premium | 28 | 9% |
  | Enterprise | 21 | 5% |

  Higher-tier plans are modeled as more engaged and stickier — a standard
  SaaS/subscription-commerce assumption.
- **Channel retention tilt**: churn probability is further multiplied by a
  channel factor — Email-acquired customers churn least (0.70x, owned-channel
  effect), TikTok-acquired customers churn most (1.35x, lower-intent
  acquisition). This is what drives the channel-retention differences
  surfaced in the cohort analysis (notebook 03).
- A customer stops generating transactions once they churn, or after 60
  purchases (a practical cap), or once the simulation clock passes
  2025-12-31.

## 6. Product Categories & Margins

| Category | Assumed gross margin |
|---|---|
| Software Add-ons | 72% |
| Beauty | 55% |
| Apparel | 45% |
| Sports & Outdoors | 40% |
| Home & Garden | 35% |
| Electronics | 18% |

These reflect typical real-world category economics (software/digital goods
carry near-zero marginal cost; electronics is thin-margin/high-ticket).
`profit = net_amount x category_margin` for standard sales.

## 7. Discounts

- 45% of transactions are full price; the remainder draw from a
  {5%, 10%, 15%, 20%, 30%} discount ladder, weighted toward shallower
  discounts.
- Any transaction falling inside a holiday window is **floored at a 10–30%
  discount**, modeling seasonal promotional pricing.

## 8. Refunds

- **3.5% flat refund probability** per transaction, applied uniformly
  (no category/channel skew, to keep the mechanic simple and auditable).
- A refunded transaction is modeled as a **profit-negative event**:
  `profit = -12% of net amount`, representing lost margin plus refund
  handling/logistics cost — it is not simply zeroed out, since reversing a
  sale has a real operational cost.

## 9. A/B Test (`ab_test_campaigns.csv`)

- Two variants of the same Google Ads conversion campaign, run head-to-head
  for **30 days** starting 2025-09-01.
- Variant A (control) baseline CVR: **4.2%**.
- Variant B (test creative) has a **deliberately built-in +18% relative CVR
  uplift** (baseline x 1.18), so the significance test in notebook 05 has a
  real, detectable effect rather than pure noise — the point of the exercise
  is to correctly measure and interpret a genuine difference, not to guess
  whether one exists.

## 10. Intentional Data-Quality Issues

A small number of realistic anomalies are deliberately injected after
generation, specifically so the Data Quality Assessment in notebook 01 has
real issues to catch (see `inject_data_quality_issues()`):

| Issue | Count | Real-world analogue |
|---|---|---|
| Negative spend values | 5 | Billing credit / refund mis-tagged as spend |
| Duplicate campaign-day rows | 8 | Double-loaded ETL batch |
| Missing `customer_id` in transactions | 6 | Broken join key at checkout |
| Orphan transactions (customer_id not in `customers`) | 5 | Late-arriving dimension record |
| Missing `age_group` in customers | 10 | Incomplete profile / optional signup field |
| Conversions > clicks | 4 | Attribution/tracking double-count glitch |

These are intentionally small relative to the full dataset (tens of
thousands of rows) — enough to validate that the QA checks work, without
overwhelming the otherwise-clean analytical signal.
