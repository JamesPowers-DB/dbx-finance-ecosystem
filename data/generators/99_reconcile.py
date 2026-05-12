# Databricks notebook source
# MAGIC %md
# MAGIC # Reconciliation gate — raw files vs. `_meta.dim_period_anchors`
# MAGIC
# MAGIC Reads the freshly generated source files and asserts:
# MAGIC
# MAGIC 1. **Ariba spend (RBKP / EKPO):** Σ(net amounts) per (`fy`, `fq`, `segment`)
# MAGIC    within ±`tolerance_pct`% of `anchor.cogs + anchor.sga + anchor.rd`.
# MAGIC 2. **CMS revenue (billing_schedule):** Σ(amount) per (`fy`, `fq`, `segment`)
# MAGIC    within ±`tolerance_pct`% of `anchor.revenue`.
# MAGIC 3. **Fusion GL balance:** Σ(dr) − Σ(cr) per `je_header_id` == 0 (strict).
# MAGIC
# MAGIC Fails the job loudly on first breach.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
import glob

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_raw", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("raw_volume", "")
dbutils.widgets.text("tolerance_pct", "2.0")

catalog = get_widget("catalog", "")
schema_raw = get_widget("schema_raw", "")
schema_meta = get_widget("schema_meta", "")
raw_volume = get_widget("raw_volume", "")
tol = float(get_widget("tolerance_pct", "2.0")) / 100.0

anchors = read_anchors(spark, catalog, schema_meta)
periods = quarters_to_generate(anchors, None)

ARIBA = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba")
FUSION = volume_dir(catalog, schema_raw, raw_volume, "oracle_fusion")
CMS = volume_dir(catalog, schema_raw, raw_volume, "inhouse_cms")

# COMMAND ----------
# MAGIC %md ## Helpers

# COMMAND ----------
def within_tol(actual: float, target: float, tol_frac: float) -> Tuple[bool, float]:
    if target == 0:
        return abs(actual) <= 1, 0.0
    drift = (actual - target) / target
    return abs(drift) <= tol_frac, drift


breaches: List[str] = []


def check(label: str, actual: float, target: float, tol_frac: float):
    ok, drift = within_tol(actual, target, tol_frac)
    flag = "OK " if ok else "FAIL"
    print(f"  {flag}  {label}: actual={actual:,.0f}  target={target:,.0f}  drift={drift * 100:+.2f}%")
    if not ok:
        breaches.append(f"{label}: drift {drift * 100:+.2f}% > ±{tol_frac * 100:.1f}%")


# COMMAND ----------
# MAGIC %md ## (1) Ariba EKPO line totals vs. anchor spend

# COMMAND ----------
print("=== Ariba EKPO vs. anchor spend (cogs + sga + rd) ===")
for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    line_file = f"{ARIBA}/EKPO_PO_LINE_{label}.csv"
    head_file = f"{ARIBA}/EKKO_PO_HEADER_{label}.csv"
    if not os.path.exists(line_file) or not os.path.exists(head_file):
        print(f"  SKIP {label}: file missing")
        continue
    lines = pl.read_csv(line_file).select(["EBELN", "NETWR"])
    heads = pl.read_csv(head_file).select(["EBELN", "BUKRS"])
    bukrs_to_seg = {s["company_code"]: s["code"] for s in HELIOS_SEGMENTS}
    joined = (lines.join(heads, on="EBELN")
                   .with_columns(pl.col("BUKRS").cast(pl.Utf8).map_elements(
                       lambda b: bukrs_to_seg.get(b, "CORP"), return_dtype=pl.Utf8).alias("seg")))
    agg = joined.group_by("seg").agg(pl.col("NETWR").sum().alias("total"))
    for seg in SEGMENT_CODES:
        target = (anchor_metric(anchors, fy, fq, seg, "cogs")
                  + anchor_metric(anchors, fy, fq, seg, "sga")
                  + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        row = agg.filter(pl.col("seg") == seg)
        actual = float(row["total"][0]) if not row.is_empty() else 0.0
        check(f"Ariba spend {label} {seg}", actual, target, tol)

# COMMAND ----------
# MAGIC %md ## (2) CMS billing_schedule vs. anchor revenue

# COMMAND ----------
print("=== CMS billing_schedule vs. anchor revenue ===")
for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    f = f"{CMS}/billing_schedule_{label}.jsonl"
    if not os.path.exists(f):
        print(f"  SKIP {label}: file missing")
        continue
    bills = pl.read_ndjson(f).select(["segment_code", "amount"])
    agg = bills.group_by("segment_code").agg(pl.col("amount").sum().alias("total"))
    for seg in SEGMENT_CODES:
        target = anchor_metric(anchors, fy, fq, seg, "revenue") * 1_000_000.0
        row = agg.filter(pl.col("segment_code") == seg)
        actual = float(row["total"][0]) if not row.is_empty() else 0.0
        check(f"CMS revenue {label} {seg}", actual, target, tol)

# COMMAND ----------
# MAGIC %md ## (3) Fusion GL per-JE balance (strict — must be exactly zero per header)

# COMMAND ----------
print("=== Fusion GL per-JE balance (strict) ===")
for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    f = f"{FUSION}/gl_je_lines_{label}.parquet"
    if not os.path.exists(f):
        print(f"  SKIP {label}: file missing")
        continue
    lines = pl.read_parquet(f).select(["je_header_id", "accounted_dr", "accounted_cr"])
    per_je = (lines.group_by("je_header_id")
                   .agg([(pl.col("accounted_dr").sum() - pl.col("accounted_cr").sum()).alias("net")])
                   .filter(pl.col("net").abs() > 0.01))
    if not per_je.is_empty():
        n_unbal = len(per_je)
        breaches.append(f"GL {label}: {n_unbal} unbalanced JE headers")
        print(f"  FAIL {label}: {n_unbal} unbalanced JE headers (sample: "
              f"{per_je.head(3).to_dicts()})")
    else:
        print(f"  OK   {label}: all JEs balanced")

# COMMAND ----------
# MAGIC %md ## Result

# COMMAND ----------
if breaches:
    print(f"\n--- RECONCILIATION FAILED: {len(breaches)} breach(es) ---")
    for b in breaches:
        print(f"  - {b}")
    raise AssertionError(f"Reconciliation failed: {len(breaches)} anchor breaches.")
else:
    print("\n--- ALL RECONCILIATIONS PASSED ---")
