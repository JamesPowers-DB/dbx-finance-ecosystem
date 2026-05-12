-- ============================================================================
-- GOLD — dim_date (2023-01-01 → 2027-12-31)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_date
COMMENT "Calendar dim. Date key, fiscal-year/quarter/month, day-of-week, month-name."
AS
SELECT
  d                                                         AS date_key,
  YEAR(d)                                                   AS calendar_year,
  YEAR(d)                                                   AS fiscal_year,
  QUARTER(d)                                                AS fiscal_quarter,
  MONTH(d)                                                  AS calendar_month,
  DATE_FORMAT(d, 'MMM')                                     AS month_short_name,
  DATE_FORMAT(d, 'MMMM')                                    AS month_long_name,
  DATE_TRUNC('MONTH', d)                                    AS first_of_month,
  DAY(d)                                                    AS day_of_month,
  DAYOFWEEK(d)                                              AS day_of_week,
  DATE_FORMAT(d, 'EEEE')                                    AS day_name,
  CASE WHEN DAYOFWEEK(d) IN (1, 7) THEN TRUE ELSE FALSE END AS is_weekend
FROM (
  SELECT EXPLODE(SEQUENCE(DATE '2023-01-01', DATE '2027-12-31', INTERVAL 1 DAY)) AS d
);
