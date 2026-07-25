"""
Synthetic data generator for the Marketing + Finance Analytics case study.

Produces four related tables under data/raw/:
    campaigns.csv          - daily campaign-level marketing performance
    customers.csv           - one row per acquired customer
    transactions.csv        - purchase history per customer (repeat purchases, churn, refunds)
    ab_test_campaigns.csv   - a synthetic 30-day A/B creative test

Every assumption baked in here (margins, churn, seasonality, channel behavior,
etc.) is documented in docs/Business_Assumptions.md. A fixed random seed makes
the output 100% reproducible: anyone who clones the repo and runs this script
gets byte-identical CSVs.
"""

import numpy as np
import pandas as pd

from pathlib import Path

SEED = 42
rng = np.random.default_rng(SEED)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = pd.Timestamp("2024-01-01")
END_DATE = pd.Timestamp("2025-12-31")
ALL_DATES = pd.date_range(START_DATE, END_DATE, freq="D")

# Holidays / demand-spike windows (Business_Assumptions.md documents the uplift %)
HOLIDAY_WINDOWS = [
    ("2024-11-25", "2024-12-02", 1.85),   # Black Friday / Cyber Monday
    ("2024-12-18", "2024-12-26", 1.45),   # Christmas
    ("2024-08-15", "2024-09-05", 1.20),   # Back to school
    ("2025-11-24", "2025-12-01", 1.90),   # Black Friday / Cyber Monday
    ("2025-12-18", "2025-12-26", 1.50),   # Christmas
    ("2025-08-15", "2025-09-05", 1.22),   # Back to school
]


def holiday_multiplier(dates: pd.DatetimeIndex) -> np.ndarray:
    mult = np.ones(len(dates))
    for start, end, factor in HOLIDAY_WINDOWS:
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        mult[mask] = factor
    return mult


def weekday_multiplier(dates: pd.DatetimeIndex) -> np.ndarray:
    # B2C-style weekly pattern: weekends slightly lower for work-hours channels (Google/LinkedIn-like),
    # slightly higher for impulse/social channels. We apply a mild generic pattern here;
    # channel-specific tilts are layered in separately.
    dow = dates.dayofweek  # 0=Mon
    base = np.where(dow >= 5, 0.9, 1.0)
    return base


# ---------------------------------------------------------------------------
# 1. CAMPAIGNS
# ---------------------------------------------------------------------------
CHANNELS = ["Google Ads", "Facebook", "Instagram", "Email", "Affiliate", "TikTok", "Organic"]
OBJECTIVES = ["Awareness", "Consideration", "Conversion"]
DEVICES = ["Mobile", "Desktop", "Tablet"]
COUNTRIES = ["United States", "United Kingdom", "India", "Canada", "Australia"]
AUDIENCES = ["New", "Returning", "Retargeting", "Lookalike"]

# Channel baseline economics (documented in Business_Assumptions.md)
CHANNEL_PARAMS = {
    "Google Ads":  dict(daily_impr=(18000, 5000), ctr=(0.032, 0.008), cvr=(0.045, 0.012), cpc=(1.15, 0.20), has_spend=True,  launch="2024-01-01"),
    "Facebook":    dict(daily_impr=(22000, 6000), ctr=(0.018, 0.005), cvr=(0.032, 0.009), cpc=(0.85, 0.15), has_spend=True,  launch="2024-01-01"),
    "Instagram":   dict(daily_impr=(19000, 5500), ctr=(0.015, 0.004), cvr=(0.026, 0.008), cpc=(0.80, 0.15), has_spend=True,  launch="2024-01-01"),
    "Email":       dict(daily_impr=(6000, 1500),  ctr=(0.12, 0.02),   cvr=(0.06, 0.015),  cpc=(0.05, 0.01), has_spend=True,  launch="2024-01-01"),
    "Affiliate":   dict(daily_impr=(9000, 2500),  ctr=(0.022, 0.006), cvr=(0.028, 0.008), cpc=(0.55, 0.12), has_spend=True,  launch="2024-01-01"),
    "TikTok":      dict(daily_impr=(15000, 5000), ctr=(0.021, 0.006), cvr=(0.018, 0.006), cpc=(0.60, 0.15), has_spend=True,  launch="2024-07-01"),
    "Organic":     dict(daily_impr=(12000, 3000), ctr=(0.028, 0.007), cvr=(0.021, 0.006), cpc=(0.0, 0.0),   has_spend=False, launch="2024-01-01"),
}

DEVICE_CVR_MULT = {"Desktop": 1.15, "Mobile": 0.90, "Tablet": 0.95}
COUNTRY_CPC_MULT = {"United States": 1.35, "United Kingdom": 1.15, "Canada": 1.05, "Australia": 1.10, "India": 0.45}
COUNTRY_VOLUME_WEIGHT = {"United States": 0.38, "United Kingdom": 0.16, "India": 0.24, "Canada": 0.12, "Australia": 0.10}
AUDIENCE_CVR_MULT = {"New": 0.80, "Returning": 1.25, "Retargeting": 1.55, "Lookalike": 0.95}
OBJECTIVE_MIX = {"Awareness": dict(impr_mult=1.6, ctr_mult=0.55, cvr_mult=0.45),
                  "Consideration": dict(impr_mult=1.0, ctr_mult=1.0, cvr_mult=0.85),
                  "Conversion": dict(impr_mult=0.65, ctr_mult=1.15, cvr_mult=1.5)}
AOV_BY_CHANNEL = {  # average order value driving campaign "revenue" field
    "Google Ads": 92, "Facebook": 78, "Instagram": 74, "Email": 68,
    "Affiliate": 85, "TikTok": 58, "Organic": 80,
}

CAMPAIGN_NAME_TEMPLATES = {
    "Awareness": ["Brand_Reach_{n}", "Video_Views_{n}", "Impression_Blitz_{n}"],
    "Consideration": ["Traffic_Push_{n}", "Product_Explainer_{n}", "Interest_Boost_{n}"],
    "Conversion": ["Sale_Drive_{n}", "Retarget_Convert_{n}", "Signup_Push_{n}"],
}


def build_campaign_roster(n_per_channel=6):
    """Create ~40 distinct campaigns, each with fixed channel/objective/device/country/audience
    and a randomly assigned active window within the 2-year horizon."""
    rows = []
    campaign_id = 1000
    for channel in CHANNELS:
        launch = pd.Timestamp(CHANNEL_PARAMS[channel]["launch"])
        for i in range(n_per_channel):
            objective = rng.choice(OBJECTIVES, p=[0.35, 0.35, 0.30])
            device = rng.choice(DEVICES, p=[0.6, 0.3, 0.1])
            country = rng.choice(COUNTRIES, p=[COUNTRY_VOLUME_WEIGHT[c] for c in COUNTRIES])
            audience = rng.choice(AUDIENCES, p=[0.35, 0.25, 0.25, 0.15])
            template = rng.choice(CAMPAIGN_NAME_TEMPLATES[objective])
            name = template.format(n=i + 1)

            earliest_start = launch
            latest_start = END_DATE - pd.Timedelta(days=45)
            span_days = (latest_start - earliest_start).days
            start_offset = int(rng.integers(0, max(span_days, 1)))
            start = earliest_start + pd.Timedelta(days=start_offset)
            duration = int(rng.integers(30, 150))
            end = min(start + pd.Timedelta(days=duration), END_DATE)

            campaign_id += 1
            rows.append(dict(
                campaign_id=f"CMP-{campaign_id}",
                campaign_name=f"{channel.replace(' ', '')}_{name}",
                channel=channel, objective=objective, device=device,
                country=country, audience=audience, start=start, end=end,
            ))
    return pd.DataFrame(rows)


def generate_campaign_daily(roster: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, camp in roster.iterrows():
        channel = camp["channel"]
        params = CHANNEL_PARAMS[channel]
        obj = OBJECTIVE_MIX[camp["objective"]]
        dates = pd.date_range(camp["start"], camp["end"], freq="D")
        n = len(dates)
        if n == 0:
            continue

        hol_mult = holiday_multiplier(dates)
        wd_mult = weekday_multiplier(dates)

        impr_mean, impr_sd = params["daily_impr"]
        impressions = rng.normal(impr_mean, impr_sd, n) * obj["impr_mult"] * hol_mult * wd_mult
        impressions = np.clip(impressions, 200, None) / n_per_channel_scale(roster, channel)
        impressions = np.round(impressions).astype(int)

        ctr_mean, ctr_sd = params["ctr"]
        ctr_vals = np.clip(rng.normal(ctr_mean, ctr_sd, n) * obj["ctr_mult"], 0.002, 0.35)
        clicks = np.round(impressions * ctr_vals).astype(int)

        cvr_mean, cvr_sd = params["cvr"]
        cvr_vals = np.clip(
            rng.normal(cvr_mean, cvr_sd, n) * obj["cvr_mult"]
            * DEVICE_CVR_MULT[camp["device"]] * AUDIENCE_CVR_MULT[camp["audience"]],
            0.002, 0.6,
        )
        conversions = np.round(clicks * cvr_vals).astype(int)

        cpc_mean, cpc_sd = params["cpc"]
        cpc_vals = np.clip(rng.normal(cpc_mean, cpc_sd, n), 0.02, None) * COUNTRY_CPC_MULT[camp["country"]]
        if params["has_spend"]:
            spend = np.round(clicks * cpc_vals, 2)
        else:
            spend = np.zeros(n)  # Organic: no direct media spend

        aov = AOV_BY_CHANNEL[channel]
        order_value = rng.normal(aov, aov * 0.18, n)
        revenue = np.round(np.clip(conversions * order_value, 0, None), 2)

        for i, d in enumerate(dates):
            records.append(dict(
                campaign_id=camp["campaign_id"], campaign_name=camp["campaign_name"],
                channel=channel, objective=camp["objective"], device=camp["device"],
                country=camp["country"], audience=camp["audience"], date=d,
                spend=spend[i], impressions=impressions[i], clicks=int(clicks[i]),
                conversions=int(conversions[i]), revenue=revenue[i],
            ))
    df = pd.DataFrame(records)
    return df.sort_values(["date", "channel", "campaign_id"]).reset_index(drop=True)


def n_per_channel_scale(roster, channel):
    """Divide baseline daily impressions across the campaigns concurrently running
    for that channel so channel-level totals stay realistic regardless of roster size."""
    return max(1, (roster["channel"] == channel).sum() // 2)


# ---------------------------------------------------------------------------
# 2. CUSTOMERS
# ---------------------------------------------------------------------------
AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55+"]
GENDERS = ["Female", "Male", "Other"]
CITIES_BY_COUNTRY = {
    "United States": ["New York", "Los Angeles", "Chicago", "Austin", "Seattle"],
    "United Kingdom": ["London", "Manchester", "Birmingham"],
    "India": ["Mumbai", "Bengaluru", "Delhi", "Pune"],
    "Canada": ["Toronto", "Vancouver", "Montreal"],
    "Australia": ["Sydney", "Melbourne"],
}
PLANS = ["Free", "Basic", "Premium", "Enterprise"]
# Channel-specific plan mix (documented): paid-search/affiliate skew higher-tier, social skews Free/Basic
CHANNEL_PLAN_WEIGHTS = {
    "Google Ads":  [0.25, 0.35, 0.30, 0.10],
    "Facebook":    [0.40, 0.35, 0.20, 0.05],
    "Instagram":   [0.45, 0.35, 0.17, 0.03],
    "Email":       [0.20, 0.35, 0.35, 0.10],
    "Affiliate":   [0.20, 0.30, 0.35, 0.15],
    "TikTok":      [0.55, 0.30, 0.13, 0.02],
    "Organic":     [0.30, 0.32, 0.28, 0.10],
}
PLAN_AOV = {"Free": 22, "Basic": 48, "Premium": 95, "Enterprise": 210}

N_CUSTOMERS = 6000


def generate_customers(campaign_daily: pd.DataFrame) -> pd.DataFrame:
    # Distribute customer acquisition volume across channels proportional to each
    # channel's total conversions (keeps customers.csv broadly consistent with campaigns.csv).
    conv_by_channel = campaign_daily.groupby("channel")["conversions"].sum()
    weights = (conv_by_channel / conv_by_channel.sum()).to_dict()

    rows = []
    for cid in range(1, N_CUSTOMERS + 1):
        channel = rng.choice(list(weights.keys()), p=list(weights.values()))
        # acquisition date weighted toward when that channel actually ran
        channel_dates = campaign_daily.loc[campaign_daily["channel"] == channel, "date"]
        acq_date = pd.Timestamp(rng.choice(channel_dates.values))

        country = rng.choice(COUNTRIES, p=[COUNTRY_VOLUME_WEIGHT[c] for c in COUNTRIES])
        city = rng.choice(CITIES_BY_COUNTRY[country])
        age_group = rng.choice(AGE_GROUPS, p=[0.22, 0.32, 0.24, 0.14, 0.08])
        gender = rng.choice(GENDERS, p=[0.48, 0.48, 0.04])
        plan = rng.choice(PLANS, p=CHANNEL_PLAN_WEIGHTS[channel])
        first_value = max(5, rng.normal(PLAN_AOV[plan], PLAN_AOV[plan] * 0.25))

        rows.append(dict(
            customer_id=f"CUST-{cid:06d}", acquisition_channel=channel,
            acquisition_date=acq_date, age_group=age_group, gender=gender,
            city=city, country=country, subscription_plan=plan,
            first_purchase_value=round(first_value, 2),
        ))
    return pd.DataFrame(rows).sort_values("acquisition_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. TRANSACTIONS (repeat purchases + churn + refunds)
# ---------------------------------------------------------------------------
PRODUCT_CATEGORIES = ["Electronics", "Apparel", "Home & Garden", "Beauty", "Sports & Outdoors", "Software Add-ons"]
CATEGORY_MARGIN = {"Electronics": 0.18, "Apparel": 0.45, "Home & Garden": 0.35,
                    "Beauty": 0.55, "Sports & Outdoors": 0.40, "Software Add-ons": 0.72}
CATEGORY_WEIGHTS = [0.22, 0.22, 0.16, 0.16, 0.14, 0.10]

# Plan-level engagement: higher plans buy more often and churn less (documented assumption)
PLAN_PURCHASE_GAP_DAYS = {"Free": (55, 25), "Basic": (40, 18), "Premium": (28, 12), "Enterprise": (21, 10)}
PLAN_CHURN_PROB = {"Free": 0.22, "Basic": 0.16, "Premium": 0.09, "Enterprise": 0.05}
# Channel-level retention tilt applied multiplicatively to churn probability
CHANNEL_CHURN_MULT = {"Google Ads": 0.85, "Email": 0.70, "Affiliate": 0.90, "Organic": 0.80,
                       "Facebook": 1.15, "Instagram": 1.20, "TikTok": 1.35}
REFUND_PROB = 0.035
DISCOUNT_CHOICES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
DISCOUNT_WEIGHTS = [0.45, 0.18, 0.15, 0.12, 0.07, 0.03]


def generate_transactions(customers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    txn_id = 500000
    for _, cust in customers.iterrows():
        plan = cust["subscription_plan"]
        gap_mean, gap_sd = PLAN_PURCHASE_GAP_DAYS[plan]
        churn_p = PLAN_CHURN_PROB[plan] * CHANNEL_CHURN_MULT[cust["acquisition_channel"]]
        churn_p = float(np.clip(churn_p, 0.02, 0.55))

        # First transaction = the acquisition purchase itself
        txn_date = cust["acquisition_date"]
        amount = cust["first_purchase_value"]
        active = True
        n_purchases = 0
        while active and txn_date <= END_DATE and n_purchases < 60:
            category = rng.choice(PRODUCT_CATEGORIES, p=CATEGORY_WEIGHTS)
            discount = rng.choice(DISCOUNT_CHOICES, p=DISCOUNT_WEIGHTS)
            if any(pd.Timestamp(s) <= txn_date <= pd.Timestamp(e) for s, e, _ in HOLIDAY_WINDOWS):
                discount = max(discount, rng.choice([0.10, 0.20, 0.30]))

            net_amount = amount * (1 - discount)
            refund_flag = rng.random() < REFUND_PROB
            margin = CATEGORY_MARGIN[category]
            if refund_flag:
                profit = round(-net_amount * 0.12, 2)  # refund handling + lost margin
            else:
                profit = round(net_amount * margin, 2)

            txn_id += 1
            rows.append(dict(
                transaction_id=f"TXN-{txn_id}", customer_id=cust["customer_id"],
                transaction_date=txn_date, product_category=category,
                amount=round(amount, 2), discount=discount, profit=profit,
                refund_flag=refund_flag,
            ))
            n_purchases += 1

            if rng.random() < churn_p:
                active = False
                break
            gap = max(3, int(rng.normal(gap_mean, gap_sd)))
            txn_date = txn_date + pd.Timedelta(days=gap)
            amount = max(5, rng.normal(PLAN_AOV[plan], PLAN_AOV[plan] * 0.3))

    return pd.DataFrame(rows).sort_values("transaction_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. A/B TEST CAMPAIGN DATA (used only in notebook 05)
# ---------------------------------------------------------------------------
def generate_ab_test() -> pd.DataFrame:
    """Two creative variants of the same Google Ads conversion campaign, run head-to-head
    for 30 days. Variant B has a deliberately built-in +18% conversion-rate uplift
    over Variant A, so the significance test in notebook 05 has a real effect to detect."""
    dates = pd.date_range("2025-09-01", periods=30, freq="D")
    rows = []
    for variant, cvr_base in [("A", 0.042), ("B", 0.042 * 1.18)]:
        for d in dates:
            impressions = int(rng.normal(9000, 900))
            ctr_vals = np.clip(rng.normal(0.03, 0.004), 0.005, None)
            clicks = int(impressions * ctr_vals)
            cvr_vals = np.clip(rng.normal(cvr_base, cvr_base * 0.15), 0.001, None)
            conversions = int(clicks * cvr_vals)
            revenue = round(conversions * rng.normal(92, 15), 2)
            spend = round(clicks * rng.normal(1.15, 0.1), 2)
            rows.append(dict(variant=variant, date=d, impressions=impressions,
                              clicks=clicks, conversions=conversions,
                              revenue=max(revenue, 0), spend=max(spend, 0)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. INJECT A SMALL NUMBER OF INTENTIONAL DATA-QUALITY ISSUES
#    (so the Data Quality Assessment in notebook 01 has real anomalies to catch)
# ---------------------------------------------------------------------------
def inject_data_quality_issues(campaigns: pd.DataFrame, customers: pd.DataFrame,
                                 transactions: pd.DataFrame):
    campaigns = campaigns.copy()
    customers = customers.copy()
    transactions = transactions.copy()

    # A handful of negative spend values (billing-credit style data entry errors)
    idx = rng.choice(campaigns.index, size=5, replace=False)
    campaigns.loc[idx, "spend"] = -campaigns.loc[idx, "spend"].abs()

    # A few duplicate campaign-day rows (double-loaded ETL rows)
    dupes = campaigns.sample(n=8, random_state=SEED)
    campaigns = pd.concat([campaigns, dupes], ignore_index=True)

    # A few missing customer_ids in transactions (orphan-adjacent join failure)
    idx = rng.choice(transactions.index, size=6, replace=False)
    transactions.loc[idx, "customer_id"] = None

    # A few orphan transactions referencing a customer_id that doesn't exist in customers.csv
    orphan_rows = transactions.sample(n=5, random_state=SEED + 1).copy()
    orphan_rows["customer_id"] = [f"CUST-{900000+i}" for i in range(len(orphan_rows))]
    transactions = pd.concat([transactions, orphan_rows], ignore_index=True)

    # A few nulls in customers.age_group (incomplete profile data)
    idx = rng.choice(customers.index, size=10, replace=False)
    customers.loc[idx, "age_group"] = None

    # A few conversions > clicks (tracking/attribution glitch -> impossible CVR)
    idx = rng.choice(campaigns.index, size=4, replace=False)
    campaigns.loc[idx, "conversions"] = campaigns.loc[idx, "clicks"] + rng.integers(5, 20, size=4)

    return campaigns, customers, transactions


def main():
    print("Generating campaign roster and daily performance...")
    roster = build_campaign_roster()
    campaigns = generate_campaign_daily(roster)

    print("Generating customers...")
    customers = generate_customers(campaigns)

    print("Generating transactions (repeat purchases, churn, refunds)...")
    transactions = generate_transactions(customers)

    print("Generating A/B test experiment data...")
    ab_test = generate_ab_test()

    print("Injecting intentional data-quality issues for the audit notebook...")
    campaigns, customers, transactions = inject_data_quality_issues(campaigns, customers, transactions)

    campaigns.to_csv(OUT_DIR / "campaigns.csv", index=False)
    customers.to_csv(OUT_DIR / "customers.csv", index=False)
    transactions.to_csv(OUT_DIR / "transactions.csv", index=False)
    ab_test.to_csv(OUT_DIR / "ab_test_campaigns.csv", index=False)

    print(f"campaigns.csv        -> {len(campaigns):,} rows")
    print(f"customers.csv        -> {len(customers):,} rows")
    print(f"transactions.csv     -> {len(transactions):,} rows")
    print(f"ab_test_campaigns.csv -> {len(ab_test):,} rows")
    print("Done. Files written to", OUT_DIR)


if __name__ == "__main__":
    main()
