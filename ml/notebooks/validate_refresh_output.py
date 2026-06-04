# Databricks notebook source
# MAGIC %md
# MAGIC # Validate weekly-refresh output
# MAGIC
# MAGIC Final task of the `finance-spend-analytics-setup` (weekly refresh) job. It
# MAGIC asserts the refresh actually produced **fresh, labeled, non-future** data so
# MAGIC an unattended run fails loudly instead of silently shipping stale or broken
# MAGIC output.
# MAGIC
# MAGIC Hard failures (raise → task fails):
# MAGIC   - `gold_fact_invoices` missing or empty
# MAGIC   - any invoice dated in the **future** (the as-of cap regressed)
# MAGIC   - ML label coverage below the floor (inference didn't propagate)
# MAGIC
# MAGIC Soft warnings (printed, non-fatal):
# MAGIC   - latest invoice older than the freshness window (data not reaching "now")
# MAGIC   - latest fiscal quarter behind the current calendar quarter

# COMMAND ----------
from datetime import date

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "finance_spend_analytics")
dbutils.widgets.text("min_label_coverage_pct", "90")
dbutils.widgets.text("freshness_window_days", "45")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
min_label_coverage_pct = float(dbutils.widgets.get("min_label_coverage_pct"))
freshness_window_days = int(dbutils.widgets.get("freshness_window_days"))
assert catalog and schema, "catalog / schema must be set"

fact = f"`{catalog}`.`{schema}`.gold_fact_invoices"
preds = f"`{catalog}`.`{schema}`.ml_invoice_classifications"
print(f"Validating refresh output in {catalog}.{schema}")

failures: list[str] = []
warnings: list[str] = []

# COMMAND ----------
# MAGIC %md ## 1. fact_invoices exists and is non-empty

# COMMAND ----------
try:
    total_rows = spark.table(fact).count()
except Exception as e:
    raise AssertionError(f"HARD FAIL: cannot read {fact} — pipeline did not build gold. ({e})")

print(f"gold_fact_invoices rows: {total_rows:,}")
if total_rows == 0:
    failures.append("gold_fact_invoices is empty")

# COMMAND ----------
# MAGIC %md ## 2. No future-dated invoices + freshness

# COMMAND ----------
bounds = spark.sql(f"""
    SELECT MIN(invoice_date) AS min_dt,
           MAX(invoice_date) AS max_dt,
           DATEDIFF(CURRENT_DATE(), MAX(invoice_date)) AS days_behind,
           SUM(CASE WHEN invoice_date > CURRENT_DATE() THEN 1 ELSE 0 END) AS future_rows,
           MAX(fiscal_year) AS max_fy
    FROM {fact}
""").collect()[0]

print(f"invoice_date range: {bounds['min_dt']} → {bounds['max_dt']} "
      f"({bounds['days_behind']} days behind today)")
print(f"future-dated rows: {bounds['future_rows']:,}")

if (bounds["future_rows"] or 0) > 0:
    failures.append(f"{bounds['future_rows']:,} invoices are dated in the FUTURE (as-of cap regressed)")

if bounds["days_behind"] is not None and bounds["days_behind"] > freshness_window_days:
    warnings.append(
        f"latest invoice is {bounds['days_behind']} days old "
        f"(> {freshness_window_days}d window) — data may not be reaching 'now'"
    )

# Latest fiscal quarter vs current calendar quarter
cur_fy, cur_fq = date.today().year, (date.today().month - 1) // 3 + 1
latest_q = spark.sql(f"""
    SELECT fiscal_year AS fy, fiscal_quarter AS fq
    FROM {fact}
    ORDER BY fiscal_year DESC, fiscal_quarter DESC
    LIMIT 1
""").collect()[0]
print(f"latest quarter in data: {latest_q['fy']}Q{latest_q['fq']}  |  current: {cur_fy}Q{cur_fq}")
if (latest_q["fy"], latest_q["fq"]) < (cur_fy, cur_fq):
    warnings.append(
        f"latest data quarter {latest_q['fy']}Q{latest_q['fq']} is behind the current "
        f"quarter {cur_fy}Q{cur_fq} — auto-extend may not have added it"
    )

# COMMAND ----------
# MAGIC %md ## 3. ML label coverage (inference propagated into gold)

# COMMAND ----------
# Coverage measured against the prediction table the inference step writes, joined
# on the invoice-line key. Low coverage means batch_inference / the incremental
# refresh didn't run or didn't propagate.
cov = spark.sql(f"""
    SELECT ROUND(100.0 * SUM(CASE WHEN p.invoice_line_id IS NOT NULL THEN 1 ELSE 0 END)
                 / COUNT(*), 2) AS coverage_pct
    FROM {fact} f
    LEFT JOIN {preds} p ON f.invoice_line_id = p.invoice_line_id
""").collect()[0]
coverage_pct = float(cov["coverage_pct"] or 0.0)
print(f"ML label coverage: {coverage_pct}%  (floor {min_label_coverage_pct}%)")
if coverage_pct < min_label_coverage_pct:
    failures.append(
        f"ML label coverage {coverage_pct}% is below the {min_label_coverage_pct}% floor "
        "— inference or the incremental refresh did not propagate labels"
    )

# COMMAND ----------
# MAGIC %md ## 4. Verdict

# COMMAND ----------
print("=" * 60)
if warnings:
    print("WARNINGS:")
    for w in warnings:
        print(f"  ⚠️  {w}")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  ❌ {f}")
    raise AssertionError(
        f"Refresh validation FAILED ({len(failures)} hard issue(s)): " + "; ".join(failures)
    )
print(f"✓ Refresh output validated — {total_rows:,} invoices, "
      f"latest {bounds['max_dt']}, {coverage_pct}% labeled."
      + (f" ({len(warnings)} warning(s))" if warnings else ""))
