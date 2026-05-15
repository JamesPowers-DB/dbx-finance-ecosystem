-- ============================================================================
-- GOLD — dim_employees (SCD Type 2)
-- ============================================================================
-- One row per (employee × state change). Renames Workday-shaped bronze columns
-- to Helios-canonical names, applies type casts, and derives the quarterly
-- loaded cost (annual base × 1.30 / 4) used by fact_emp_quarterly_cost.
--
-- Query pattern for a snapshot at a given date D:
--   SELECT *
--   FROM gold.dim_employees
--   WHERE effective_from <= D
--     AND D < effective_to
--     AND employment_status = 'active'
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_employees
COMMENT "Employee dimension (SCD Type 2). Source: bronze_workday.workers. Filter on (effective_from <= D < effective_to) AND employment_status='active' for a snapshot."
AS
SELECT
  worker_id                                          AS employee_id,
  CAST(version_seq AS INT)                           AS version_seq,
  CAST(effective_date AS DATE)                       AS effective_from,
  CAST(effective_through AS DATE)                    AS effective_to,
  CAST(is_current_row AS BOOLEAN)                    AS is_current,

  worker_name_first                                  AS first_name,
  worker_name_last                                   AS last_name,
  work_email                                         AS email,

  CAST(hire_date AS DATE)                            AS hire_date,
  CAST(termination_date AS DATE)                     AS termination_date,
  LOWER(worker_status)                               AS employment_status,

  organization_id                                    AS segment_code,
  cost_center_id                                     AS cost_center_code,
  country_code,
  region,

  job_family,
  compensation_grade                                 AS seniority_band,

  CAST(annual_base_salary_amount AS DECIMAL(18, 2))  AS annual_base_salary_usd,
  CAST(annual_base_salary_amount * 1.30 / 4.0
       AS DECIMAL(18, 2))                            AS quarterly_loaded_cost_usd,
  currency_code
FROM ${schema_bronze_workday}.workers;
