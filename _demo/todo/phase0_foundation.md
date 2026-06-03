# Phase 0 — Foundation

## Pipeline SQL — DONE ✅
- [x] `pipelines/bronze/sap_ariba.sql` — 7 Auto Loader streaming tables.
- [x] `pipelines/bronze/oracle_fusion.sql` — 11 streaming tables (CSV + Parquet).
- [x] `pipelines/bronze/inhouse_cms.sql` — 6 streaming tables (line-delimited JSON).
- [x] `pipelines/silver/*.sql` — 10 conformed entities as materialized views, source-tagged.
- [x] `pipelines/gold/*.sql` — 15 facts/dims with Phase 2 hooks reserved.

## Build the lakehouse — DONE ✅
- [x] `bundle deploy -t dev` succeeds.
- [x] `bundle run build_lakehouse -t dev` populates bronze/silver/gold (after switching flat-file bronze tables from `STREAMING TABLE` to `MATERIALIZED VIEW`).

## Polish — optional, low priority
- [ ] Quick sanity checks in SQL editor (see `sql/pipeline_exploration/spend_overview.sql`):
  ```sql
  SELECT COUNT(*) FROM horizontal_finance_dev.gold.fact_invoices;
  SELECT segment_code, fiscal_year, fiscal_quarter, SUM(amount)/1e6 AS spend_m
    FROM horizontal_finance_dev.gold.fact_invoices GROUP BY ALL ORDER BY 2,3,1;
  ```
- [ ] Implement `ml/notebooks/99_validate_gold_vs_anchors.py` (currently a no-op stub wired as the final task in `build_lakehouse.yml`) — assert gold totals tie back to `_meta.dim_period_anchors` ±2%.

## Smoke tests
- [ ] Anonymization audit: grep all UC table **contents** (not just code) for source filer name / original segment names.

## HR data layer — first cut DONE; future work
- [x] `gold.dim_employees` (SCD Type 2) sourced from `bronze_workday.workers`, anchor-driven.
- [x] `gold.fact_emp_quarterly_cost` aggregates from `dim_employees` at each anchor period's quarter-end.
- [ ] Add a silver layer for HR if/when a second HR source appears.
- [ ] Salary raises — generator doesn't model raises; ~3%/quarter raise events would add SCD2 churn + wage-inflation trends.
- [ ] Role-family per segment — currently each segment pulls from any of 9 job families; could bias for realism.
- [ ] Tie-out check for HR — extend `99_reconcile.py` to assert quarter-end active counts within ±2% of `dim_period_anchors.headcount_total`.

## Operational / dev experience — deferred
- [ ] **Per-user dev resource naming.** Dev target uses `mode: production` + `${bundle.target}` suffix. Preferred `[dev <user>]` style for ownership visibility + concurrent dev deploys. Deferred because `mode: development` was the source of prior state-drift corruption. Options: literal `${workspace.current_user.short_name}` in `name:` fields; re-enable `mode: development` with strict policy; per-user catalog override. Acceptance: two devs `bundle deploy -t dev` simultaneously without collisions.
- [ ] **Split the single `lakehouse` pipeline** into 4–6 per-subject pipelines (low priority). Monolith downsides: one subject's failure breaks the whole run; can't refresh one subject; hard to attribute compute; dev contention. Cross-pipeline deps resolved via Job DAG or expectations.

## Done ✅
- [x] DAB scaffold (`databricks.yml`, `resources/`, `jobs/`, `pipelines/`).
- [x] Direct-deployment-engine requirement for catalog resources.
- [x] Parameterized all code-path references.
- [x] `requirements.txt` + `environments` block on every job.
- [x] Self-healing `ensure_volume()` helper.
- [x] `databricks bundle validate / deploy -t dev` clean.
- [x] `generate_data` runs end-to-end; anchors seeded; raw files materialized; reconciliation passes.
- [x] All 28 pipeline SQL files implemented.
- [x] Scrub source-filer name references from committed artifacts.
