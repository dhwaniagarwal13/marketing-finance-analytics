-- =============================================================================
-- business_queries.sql
-- Marketing + Finance Analytics Case Study — SQL Analysis
--
-- Target: SQLite database at data/marketing_finance.db (built by
-- src/load_to_sqlite.py from the CSVs in data/raw/). Every query below is
-- written to run as-is against that database and answers a specific,
-- realistic business question a Data/Business Analyst would be asked.
--
-- Tables:
--   campaigns          (campaign_id, campaign_name, channel, objective, device,
--                        country, audience, date, spend, impressions, clicks,
--                        conversions, revenue)
--   customers           (customer_id, acquisition_channel, acquisition_date,
--                        age_group, gender, city, country, subscription_plan,
--                        first_purchase_value)
--   transactions        (transaction_id, customer_id, transaction_date,
--                        product_category, amount, discount, profit, refund_flag)
--   ab_test_campaigns   (variant, date, impressions, clicks, conversions,
--                        revenue, spend)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. What is monthly revenue trending like across the two-year window?
-- Techniques: GROUP BY, date functions, aggregation, ORDER BY
-- -----------------------------------------------------------------------------
SELECT
    strftime('%Y-%m', date)      AS month,
    ROUND(SUM(revenue), 2)       AS total_revenue,
    ROUND(SUM(spend), 2)         AS total_spend
FROM campaigns
GROUP BY month
ORDER BY month;


-- -----------------------------------------------------------------------------
-- Q2. What is monthly profit (from actual purchases, not ad-platform revenue)?
-- Techniques: GROUP BY, date functions, aggregation, WHERE
-- -----------------------------------------------------------------------------
SELECT
    strftime('%Y-%m', transaction_date) AS month,
    ROUND(SUM(profit), 2)               AS total_profit,
    COUNT(*)                            AS transaction_count
FROM transactions
WHERE refund_flag = 0
GROUP BY month
ORDER BY month;


-- -----------------------------------------------------------------------------
-- Q3. Which campaigns deliver the best return on ad spend (ROAS)?
-- Techniques: JOIN-free aggregation, HAVING, ORDER BY, CASE
-- -----------------------------------------------------------------------------
SELECT
    campaign_id,
    campaign_name,
    channel,
    ROUND(SUM(spend), 2)                                   AS total_spend,
    ROUND(SUM(revenue), 2)                                 AS total_revenue,
    ROUND(SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0), 2)   AS roas,
    CASE
        WHEN SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0) >= 4 THEN 'Excellent'
        WHEN SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0) >= 2 THEN 'Healthy'
        WHEN SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0) >= 1 THEN 'Break-even'
        ELSE 'Underperforming'
    END                                                     AS performance_tier
FROM campaigns
WHERE spend > 0
GROUP BY campaign_id, campaign_name, channel
HAVING SUM(spend) > 500
ORDER BY roas DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q4. Which marketing channels generate the highest ROI?
-- Techniques: GROUP BY, HAVING, CASE, aggregation
-- -----------------------------------------------------------------------------
SELECT
    channel,
    ROUND(SUM(spend), 2)                                          AS total_spend,
    ROUND(SUM(revenue), 2)                                        AS total_revenue,
    ROUND((SUM(revenue) - SUM(spend)) * 1.0 / NULLIF(SUM(spend), 0), 3) AS roi,
    CASE
        WHEN (SUM(revenue) - SUM(spend)) * 1.0 / NULLIF(SUM(spend), 0) >= 1 THEN 'High ROI'
        WHEN (SUM(revenue) - SUM(spend)) * 1.0 / NULLIF(SUM(spend), 0) >= 0.3 THEN 'Moderate ROI'
        ELSE 'Low / Negative ROI'
    END AS roi_tier
FROM campaigns
WHERE spend > 0
GROUP BY channel
HAVING SUM(spend) > 1000
ORDER BY roi DESC;


-- -----------------------------------------------------------------------------
-- Q5. What is Customer Acquisition Cost (CAC) by channel?
-- Techniques: CTE, JOIN, GROUP BY, aggregation
-- -----------------------------------------------------------------------------
WITH spend_by_channel AS (
    SELECT channel, SUM(spend) AS total_spend
    FROM campaigns
    GROUP BY channel
),
customers_by_channel AS (
    SELECT acquisition_channel AS channel, COUNT(*) AS new_customers
    FROM customers
    GROUP BY acquisition_channel
)
SELECT
    s.channel,
    ROUND(s.total_spend, 2)                                   AS total_spend,
    c.new_customers,
    ROUND(s.total_spend * 1.0 / NULLIF(c.new_customers, 0), 2) AS cac
FROM spend_by_channel s
JOIN customers_by_channel c ON s.channel = c.channel
ORDER BY cac ASC;


-- -----------------------------------------------------------------------------
-- Q6. What is average Lifetime Value (LTV) by acquisition channel?
-- Techniques: CTE, JOIN, GROUP BY, aggregation
-- -----------------------------------------------------------------------------
WITH customer_profit AS (
    SELECT customer_id, SUM(profit) AS lifetime_profit
    FROM transactions
    GROUP BY customer_id
)
SELECT
    cu.acquisition_channel,
    COUNT(DISTINCT cu.customer_id)          AS customers,
    ROUND(AVG(cp.lifetime_profit), 2)       AS avg_ltv
FROM customers cu
JOIN customer_profit cp ON cu.customer_id = cp.customer_id
GROUP BY cu.acquisition_channel
ORDER BY avg_ltv DESC;


-- -----------------------------------------------------------------------------
-- Q7. LTV:CAC ratio by channel — which channels are financially efficient?
-- Techniques: CTE (chained), JOIN, aggregation, CASE
-- -----------------------------------------------------------------------------
WITH spend_by_channel AS (
    SELECT channel, SUM(spend) AS total_spend
    FROM campaigns GROUP BY channel
),
customers_by_channel AS (
    SELECT acquisition_channel AS channel, COUNT(*) AS new_customers
    FROM customers GROUP BY acquisition_channel
),
cac_tbl AS (
    SELECT s.channel, s.total_spend * 1.0 / NULLIF(c.new_customers, 0) AS cac
    FROM spend_by_channel s JOIN customers_by_channel c ON s.channel = c.channel
),
ltv_tbl AS (
    SELECT cu.acquisition_channel AS channel, AVG(cp.lifetime_profit) AS ltv
    FROM customers cu
    JOIN (SELECT customer_id, SUM(profit) AS lifetime_profit FROM transactions GROUP BY customer_id) cp
        ON cu.customer_id = cp.customer_id
    GROUP BY cu.acquisition_channel
)
SELECT
    l.channel,
    ROUND(c.cac, 2)  AS cac,
    ROUND(l.ltv, 2)  AS ltv,
    ROUND(l.ltv / NULLIF(c.cac, 0), 2) AS ltv_to_cac_ratio,
    CASE WHEN l.ltv / NULLIF(c.cac, 0) >= 3 THEN 'Efficient'
         WHEN l.ltv / NULLIF(c.cac, 0) >= 1 THEN 'Marginal'
         ELSE 'Unprofitable' END AS efficiency
FROM ltv_tbl l
JOIN cac_tbl c ON l.channel = c.channel
ORDER BY ltv_to_cac_ratio DESC;


-- -----------------------------------------------------------------------------
-- Q8. Monthly acquisition cohort retention (% of cohort still purchasing N months later)
-- Techniques: CTE, date functions, window-adjacent aggregation, JOIN
-- -----------------------------------------------------------------------------
WITH cohort AS (
    SELECT customer_id, strftime('%Y-%m', acquisition_date) AS cohort_month
    FROM customers
),
activity AS (
    SELECT t.customer_id, c.cohort_month,
           strftime('%Y-%m', t.transaction_date) AS activity_month
    FROM transactions t
    JOIN cohort c ON t.customer_id = c.customer_id
),
month_diff AS (
    SELECT customer_id, cohort_month,
           (CAST(strftime('%Y', activity_month || '-01') AS INT) - CAST(strftime('%Y', cohort_month || '-01') AS INT)) * 12
           + (CAST(strftime('%m', activity_month || '-01') AS INT) - CAST(strftime('%m', cohort_month || '-01') AS INT)) AS months_since_acquisition
    FROM activity
)
SELECT
    cohort_month,
    months_since_acquisition,
    COUNT(DISTINCT customer_id) AS active_customers
FROM month_diff
WHERE months_since_acquisition BETWEEN 0 AND 6
GROUP BY cohort_month, months_since_acquisition
ORDER BY cohort_month, months_since_acquisition;


-- -----------------------------------------------------------------------------
-- Q9. Top 10 customers by lifetime profit
-- Techniques: JOIN, GROUP BY, ORDER BY, LIMIT
-- -----------------------------------------------------------------------------
SELECT
    cu.customer_id,
    cu.acquisition_channel,
    cu.subscription_plan,
    ROUND(SUM(t.profit), 2)  AS lifetime_profit,
    COUNT(t.transaction_id)  AS total_purchases
FROM customers cu
JOIN transactions t ON cu.customer_id = t.customer_id
GROUP BY cu.customer_id, cu.acquisition_channel, cu.subscription_plan
ORDER BY lifetime_profit DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q10. Rank every campaign within its own channel by revenue
-- Techniques: Window functions — ROW_NUMBER(), RANK(), DENSE_RANK()
-- -----------------------------------------------------------------------------
SELECT
    channel,
    campaign_name,
    total_revenue,
    ROW_NUMBER() OVER (PARTITION BY channel ORDER BY total_revenue DESC) AS row_num,
    RANK()       OVER (PARTITION BY channel ORDER BY total_revenue DESC) AS rank_num,
    DENSE_RANK() OVER (PARTITION BY channel ORDER BY total_revenue DESC) AS dense_rank_num
FROM (
    SELECT channel, campaign_name, SUM(revenue) AS total_revenue
    FROM campaigns
    GROUP BY channel, campaign_name
) t
ORDER BY channel, row_num;


-- -----------------------------------------------------------------------------
-- Q11. 7-day moving average of daily revenue (smooths noisy daily totals)
-- Techniques: Window function — moving average via ROWS BETWEEN frame
-- -----------------------------------------------------------------------------
WITH daily_revenue AS (
    SELECT date, SUM(revenue) AS revenue
    FROM campaigns
    GROUP BY date
)
SELECT
    date,
    revenue,
    ROUND(AVG(revenue) OVER (
        ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS revenue_7day_moving_avg
FROM daily_revenue
ORDER BY date;


-- -----------------------------------------------------------------------------
-- Q12. Running total (cumulative) revenue across the full period
-- Techniques: Window function — running total via SUM() OVER
-- -----------------------------------------------------------------------------
WITH daily_revenue AS (
    SELECT date, SUM(revenue) AS revenue
    FROM campaigns
    GROUP BY date
)
SELECT
    date,
    revenue,
    ROUND(SUM(revenue) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING), 2) AS cumulative_revenue
FROM daily_revenue
ORDER BY date;


-- -----------------------------------------------------------------------------
-- Q13. Month-over-month revenue growth rate
-- Techniques: Window function — LAG(), date functions, CASE
-- -----------------------------------------------------------------------------
WITH monthly AS (
    SELECT strftime('%Y-%m', date) AS month, SUM(revenue) AS revenue
    FROM campaigns
    GROUP BY month
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month)              AS prior_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY month)) * 100.0
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 1
    ) AS mom_growth_pct
FROM monthly
ORDER BY month;


-- -----------------------------------------------------------------------------
-- Q14. Click-through and conversion rate by device
-- Techniques: GROUP BY, CASE, aggregation
-- -----------------------------------------------------------------------------
SELECT
    device,
    SUM(impressions)                                       AS impressions,
    SUM(clicks)                                             AS clicks,
    SUM(conversions)                                        AS conversions,
    ROUND(SUM(clicks) * 100.0 / NULLIF(SUM(impressions), 0), 2)  AS ctr_pct,
    ROUND(SUM(conversions) * 100.0 / NULLIF(SUM(clicks), 0), 2)  AS cvr_pct,
    CASE
        WHEN SUM(conversions) * 100.0 / NULLIF(SUM(clicks), 0) >= 4 THEN 'Strong Converter'
        ELSE 'Needs Optimization'
    END AS device_status
FROM campaigns
GROUP BY device
ORDER BY cvr_pct DESC;


-- -----------------------------------------------------------------------------
-- Q15. Country-level performance comparison
-- Techniques: GROUP BY, HAVING, ORDER BY, aggregation
-- -----------------------------------------------------------------------------
SELECT
    country,
    ROUND(SUM(spend), 2)    AS total_spend,
    ROUND(SUM(revenue), 2)  AS total_revenue,
    ROUND(SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0), 2) AS roas
FROM campaigns
WHERE spend > 0
GROUP BY country
HAVING SUM(spend) > 500
ORDER BY roas DESC;


-- -----------------------------------------------------------------------------
-- Q16. Customers with more than 5 lifetime purchases ("power users")
-- Techniques: GROUP BY, HAVING, JOIN
-- -----------------------------------------------------------------------------
SELECT
    cu.customer_id,
    cu.acquisition_channel,
    cu.subscription_plan,
    COUNT(t.transaction_id) AS purchase_count,
    ROUND(SUM(t.amount), 2) AS total_spent
FROM customers cu
JOIN transactions t ON cu.customer_id = t.customer_id
GROUP BY cu.customer_id, cu.acquisition_channel, cu.subscription_plan
HAVING COUNT(t.transaction_id) > 5
ORDER BY purchase_count DESC;


-- -----------------------------------------------------------------------------
-- Q17. Refund rate and lost profit by product category
-- Techniques: GROUP BY, CASE-based conditional aggregation
-- -----------------------------------------------------------------------------
SELECT
    product_category,
    COUNT(*)                                                        AS total_transactions,
    SUM(CASE WHEN refund_flag = 1 THEN 1 ELSE 0 END)                AS refunded_transactions,
    ROUND(SUM(CASE WHEN refund_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS refund_rate_pct,
    ROUND(SUM(CASE WHEN refund_flag = 1 THEN profit ELSE 0 END), 2) AS profit_lost_to_refunds
FROM transactions
GROUP BY product_category
ORDER BY refund_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- Q18. Discount depth vs. realized profit margin
-- Techniques: CASE (bucketing), GROUP BY, aggregation
-- -----------------------------------------------------------------------------
SELECT
    CASE
        WHEN discount = 0 THEN '0% (Full Price)'
        WHEN discount <= 0.10 THEN '5-10%'
        WHEN discount <= 0.20 THEN '15-20%'
        ELSE '30%+'
    END AS discount_band,
    COUNT(*)                                              AS transactions,
    ROUND(AVG(amount), 2)                                 AS avg_order_value,
    ROUND(SUM(profit) * 1.0 / NULLIF(SUM(amount), 0), 3)  AS realized_margin
FROM transactions
WHERE refund_flag = 0
GROUP BY discount_band
ORDER BY discount_band;


-- -----------------------------------------------------------------------------
-- Q19. A/B test variant comparison (feeds the statistical significance analysis)
-- Techniques: GROUP BY, aggregation, CASE
-- -----------------------------------------------------------------------------
SELECT
    variant,
    SUM(impressions)                                              AS impressions,
    SUM(clicks)                                                   AS clicks,
    SUM(conversions)                                               AS conversions,
    ROUND(SUM(conversions) * 100.0 / NULLIF(SUM(clicks), 0), 2)   AS cvr_pct,
    ROUND(SUM(revenue), 2)                                        AS revenue,
    ROUND(SUM(revenue) * 1.0 / NULLIF(SUM(spend), 0), 2)          AS roas
FROM ab_test_campaigns
GROUP BY variant
ORDER BY variant;


-- -----------------------------------------------------------------------------
-- Q20. RFM base table — Recency, Frequency, Monetary per customer with NTILE scoring
-- Techniques: CTE, window function NTILE(), JOIN, date functions
-- -----------------------------------------------------------------------------
WITH rfm_base AS (
    SELECT
        customer_id,
        CAST(julianday('2025-12-31') - julianday(MAX(transaction_date)) AS INT) AS recency_days,
        COUNT(*)         AS frequency,
        ROUND(SUM(amount), 2) AS monetary
    FROM transactions
    WHERE refund_flag = 0
    GROUP BY customer_id
)
SELECT
    customer_id,
    recency_days,
    frequency,
    monetary,
    NTILE(5) OVER (ORDER BY recency_days DESC) AS recency_score,   -- 5 = most recent
    NTILE(5) OVER (ORDER BY frequency ASC)     AS frequency_score, -- 5 = most frequent
    NTILE(5) OVER (ORDER BY monetary ASC)      AS monetary_score   -- 5 = highest spend
FROM rfm_base
ORDER BY monetary DESC
LIMIT 25;


-- -----------------------------------------------------------------------------
-- Q21. Data-quality check: orphan transactions (customer_id not present in customers)
-- Techniques: LEFT JOIN, WHERE IS NULL (anti-join pattern)
-- -----------------------------------------------------------------------------
SELECT
    t.transaction_id, t.customer_id, t.transaction_date, t.amount
FROM transactions t
LEFT JOIN customers cu ON t.customer_id = cu.customer_id
WHERE cu.customer_id IS NULL;
