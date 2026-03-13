-- AUM query template
-- This query must return the following columns:
--   manager_firm
--   aum_prior_month
--   aum_latest_month
--
-- Adjust the FROM and WHERE clauses to match your schema.

SELECT
    manager_firm,
    SUM(aum_prior_month)  AS aum_prior_month,
    SUM(aum_latest_month) AS aum_latest_month
FROM aum_source_table
GROUP BY manager_firm
ORDER BY manager_firm;

