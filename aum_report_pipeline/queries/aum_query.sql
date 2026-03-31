-- AUM query parameterized by anchor month.
-- It must return the following columns:
--   manager_firm
--   aum_prior_month
--   aum_latest_month
--
-- The Python code passes a parameter named `anchor_month` (date),
-- and this query computes:
--   - latest_month_end: last business day of the anchor month
--   - prior_month_end: last business day of the previous month

WITH latest_allocations AS (
    SELECT DISTINCT ON (sleeve_id, sponsor_cd)
        sleeve_id,
        sponsor_cd,
        model_code
    FROM sleeve_allocations
    ORDER BY sleeve_id, sponsor_cd, as_of_date DESC
),
month_dates AS (
    SELECT
        (
            SELECT MAX(value_date)
            FROM aum_daily_values
            WHERE value_date <= date_trunc('month', %(anchor_month)s::date) - interval '1 day'
              AND EXTRACT(DOW FROM value_date) BETWEEN 1 AND 5
        ) AS latest_month_end,
        (
            SELECT MAX(value_date)
            FROM aum_daily_values
            WHERE value_date <= date_trunc('month', %(anchor_month)s::date) - interval '1 month' - interval '1 day'
              AND EXTRACT(DOW FROM value_date) BETWEEN 1 AND 5
        ) AS prior_month_end
)
SELECT
    pm.manager_firm,
    pm.model_name,
    SUM(adv.daily_value) FILTER (
        WHERE adv.value_date = md.latest_month_end
    ) AS aum_latest_month,
    SUM(adv.daily_value) FILTER (
        WHERE adv.value_date = md.prior_month_end
    ) AS aum_prior_month
FROM aum_daily_values adv
JOIN latest_allocations la
    ON adv.sleeve_id = la.sleeve_id
   AND adv.sponsor_cd = la.sponsor_cd
LEFT JOIN product_master pm
    ON la.model_code = pm.aris_model_code
CROSS JOIN month_dates md
WHERE adv.value_date IN (md.latest_month_end, md.prior_month_end)
  AND pm.product_fee_type = 'Active'
GROUP BY pm.manager_firm, pm.model_name
ORDER BY pm.manager_firm, pm.model_name;


