# Data Dictionary

Enterprise-style reference documentation for every table and column in the
dataset. Source files live in `data/raw/*.csv` and are mirrored into
`data/marketing_finance.db` (SQLite) by `src/load_to_sqlite.py`.

---

## Table: `campaigns`

Daily, campaign-level marketing performance. Grain: **one row per
campaign per day**.

| Column | Data Type | Description | Example Value |
|---|---|---|---|
| `campaign_id` | string | Unique identifier for the campaign | `CMP-1040` |
| `campaign_name` | string | Human-readable campaign name (channel + creative theme) | `Organic_Signup_Push_4` |
| `channel` | string | Marketing channel running the campaign | `Organic` |
| `objective` | string | Campaign goal: `Awareness`, `Consideration`, or `Conversion` | `Conversion` |
| `device` | string | Primary targeted device: `Mobile`, `Desktop`, or `Tablet` | `Mobile` |
| `country` | string | Target country for the campaign | `United States` |
| `audience` | string | Audience type: `New`, `Returning`, `Retargeting`, or `Lookalike` | `Lookalike` |
| `date` | date (YYYY-MM-DD) | Calendar date of the performance record | `2024-02-27` |
| `spend` | float | Media spend for that campaign-day, in USD | `0.0` |
| `impressions` | integer | Number of ad impressions served | `1620` |
| `clicks` | integer | Number of clicks recorded | `62` |
| `conversions` | integer | Number of conversion events (signups/purchases attributed to the click) | `1` |
| `revenue` | float | Revenue attributed to those conversions, in USD | `52.30` |

**Notes:** `Organic` rows always have `spend = 0` (no direct media cost).
A small number of rows contain intentionally negative `spend` values and a
few rows have `conversions > clicks` — both are seeded data-quality issues
documented in `docs/Business_Assumptions.md` and audited in
`notebooks/01_Data_Overview.ipynb`.

---

## Table: `customers`

One row per acquired customer. Grain: **one row per customer**.

| Column | Data Type | Description | Example Value |
|---|---|---|---|
| `customer_id` | string | Unique identifier for the customer | `CUST-004981` |
| `acquisition_channel` | string | Marketing channel that acquired the customer | `Organic` |
| `acquisition_date` | date (YYYY-MM-DD) | Date the customer first converted | `2024-03-02` |
| `age_group` | string | Age bracket: `18-24`, `25-34`, `35-44`, `45-54`, `55+` | `18-24` |
| `gender` | string | Self-reported gender: `Female`, `Male`, `Other` | `Male` |
| `city` | string | Customer's city | `Vancouver` |
| `country` | string | Customer's country | `Canada` |
| `subscription_plan` | string | Plan tier: `Free`, `Basic`, `Premium`, `Enterprise` | `Free` |
| `first_purchase_value` | float | Value of the customer's first (acquisition) purchase, in USD | `19.91` |

**Notes:** A small number of rows have a missing `age_group` (incomplete
profile data), a seeded data-quality issue.

---

## Table: `transactions`

Full purchase history, including repeat purchases and refunds. Grain:
**one row per transaction**.

| Column | Data Type | Description | Example Value |
|---|---|---|---|
| `transaction_id` | string | Unique identifier for the transaction | `TXN-500045` |
| `customer_id` | string | Foreign key to `customers.customer_id` | `CUST-001125` |
| `transaction_date` | date (YYYY-MM-DD) | Date of purchase | `2024-03-02` |
| `product_category` | string | Product category purchased: `Electronics`, `Apparel`, `Home & Garden`, `Beauty`, `Sports & Outdoors`, `Software Add-ons` | `Electronics` |
| `amount` | float | Gross order amount before discount, in USD | `92.46` |
| `discount` | float | Discount applied, as a decimal fraction (0.15 = 15%) | `0.15` |
| `profit` | float | Net profit on the transaction after discount, category margin, and refund adjustment | `14.15` |
| `refund_flag` | boolean | Whether the transaction was refunded | `False` |

**Notes:** When `refund_flag = True`, `profit` is negative (lost margin +
refund handling cost — see `docs/Business_Assumptions.md` §8). A small
number of rows have a missing `customer_id` or reference a `customer_id`
that does not exist in `customers` (orphan transactions) — both are seeded
data-quality issues.

---

## Table: `ab_test_campaigns`

Daily performance for a synthetic 30-day, two-variant creative experiment on
a Google Ads conversion campaign. Grain: **one row per variant per day**.

| Column | Data Type | Description | Example Value |
|---|---|---|---|
| `variant` | string | Experiment arm: `A` (control) or `B` (test creative) | `A` |
| `date` | date (YYYY-MM-DD) | Calendar date of the experiment day | `2025-09-03` |
| `impressions` | integer | Impressions served that day | `7985` |
| `clicks` | integer | Clicks recorded that day | `281` |
| `conversions` | integer | Conversions recorded that day | `12` |
| `revenue` | float | Revenue attributed to that day's conversions, in USD | `1284.62` |
| `spend` | float | Media spend that day, in USD | `325.93` |

**Notes:** Variant `B` has a deliberately built-in +18% relative
conversion-rate uplift over Variant `A` (see `docs/Business_Assumptions.md`
§9) — used in `notebooks/05_Advanced_Analytics.ipynb` to demonstrate a
real, statistically significant A/B test result.

---

## Entity Relationships

```
customers (1) ──< (many) transactions        via customer_id
campaigns (channel/date) ~ customers (acquisition_channel/acquisition_date)
    -- a directional, not strictly referential, relationship (see
       Business_Assumptions.md §4)
ab_test_campaigns -- standalone experiment table, not joined to the core schema
```

A full entity-relationship diagram is included in the project `README.md`.
