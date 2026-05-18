# Databricks notebook source
# MAGIC %md
# MAGIC # Reconciliation gate — raw files vs. `_meta.dim_period_anchors`
# MAGIC
# MAGIC Reads the freshly generated source files and asserts:
# MAGIC
# MAGIC 1. **Invoice spend (Fusion `ap_invoice_lines_all`)** per (`fy`, `fq`, `segment`)
# MAGIC    within ±`tolerance_pct`% of anchor (`cogs + sga + rd`). *Tight check.*
# MAGIC 2. **CMS revenue (`billing_schedule`)** per (`fy`, `fq`, `segment`)
# MAGIC    within ±`tolerance_pct`% of `anchor.revenue`. *Tight check.*
# MAGIC 3. **Fusion GL per-JE balance**: Σ(dr) − Σ(cr) per `je_header_id` == 0 (strict).
# MAGIC 4. **PR → PO → Invoice cone (loose, directional)**: per (`fy`, `fq`, `segment`)
# MAGIC    PR$ ≈ Invoice$ × 1.56 ±15%; PO$ ≈ Invoice$ × 1.25 ±15%. (Transaction matching
# MAGIC    is hard in reality — keep this loose.)
# MAGIC 5. **AP balance**: Σ(creation_credits) − Σ(payment_debits) ≈ Σ(open invoices) by
# MAGIC    period — informational only, no hard fail.

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
loose_tol = 0.15  # loose ±15% on cross-step matching

anchors = read_anchors(spark, catalog, schema_meta)
periods = quarters_to_generate(anchors, None)

ARIBA = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba")
FUSION = volume_dir(catalog, schema_raw, raw_volume, "oracle_fusion")
CMS = volume_dir(catalog, schema_raw, raw_volume, "inhouse_cms")

# COMMAND ----------
def within_tol(actual: float, target: float, tol_frac: float) -> Tuple[bool, float]:
    if target == 0:
        return abs(actual) <= 1, 0.0
    drift = (actual - target) / target
    return abs(drift) <= tol_frac, drift


breaches: List[str] = []
warnings_list: List[str] = []


def check(label: str, actual: float, target: float, tol_frac: float, *, warn_only: bool = False):
    ok, drift = within_tol(actual, target, tol_frac)
    flag = "OK  " if ok else ("WARN" if warn_only else "FAIL")
    print(f"  {flag}  {label}: actual={actual:,.0f}  target={target:,.0f}  drift={drift * 100:+.2f}%")
    if not ok:
        msg = f"{label}: drift {drift * 100:+.2f}% > ±{tol_frac * 100:.1f}%"
        (warnings_list if warn_only else breaches).append(msg)


# COMMAND ----------
# MAGIC %md ## (1) Fusion invoice lines vs anchor spend (TIGHT ±2%)

# COMMAND ----------
print("=== Fusion ap_invoice_lines_all vs. anchor (cogs + sga + rd) ===")
for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    f = f"{FUSION}/ap_invoice_lines_all_{label}.parquet"
    if not os.path.exists(f):
        print(f"  SKIP {label}: file missing")
        continue
    lines = pl.read_parquet(f).select(["_segment_code", "amount"])
    agg = lines.group_by("_segment_code").agg(pl.col("amount").sum().alias("total"))
    for seg in SEGMENT_CODES:
        target = (anchor_metric(anchors, fy, fq, seg, "cogs")
                  + anchor_metric(anchors, fy, fq, seg, "sga")
                  + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        row = agg.filter(pl.col("_segment_code") == seg)
        actual = float(row["total"][0]) if not row.is_empty() else 0.0
        check(f"Invoice spend {label} {seg}", actual, target, tol)

# COMMAND ----------
# MAGIC %md ## (2) CMS billing vs anchor revenue (TIGHT ±2%)

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
# MAGIC %md ## (3) Fusion GL per-JE balance (strict)

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
        print(f"  FAIL {label}: {n_unbal} unbalanced JE headers")
    else:
        print(f"  OK   {label}: all JEs balanced")

# COMMAND ----------
# MAGIC %md ## (4) PR → PO → Invoice cone (LOOSE ±15%, directional only)

# COMMAND ----------
print("=== PR → PO → Invoice volumes (loose ±15%) ===")
bukrs_to_seg = {s["company_code"]: s["code"] for s in HELIOS_SEGMENTS}

for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    pr_header_f = f"{ARIBA}/EBAN_PR_HEADER_{label}.csv"
    pr_line_f = f"{ARIBA}/EBAN_PR_LINE_{label}.csv"
    po_header_f = f"{FUSION}/po_headers_all_{label}.csv"
    po_line_f = f"{FUSION}/po_lines_all_{label}.parquet"
    inv_line_f = f"{FUSION}/ap_invoice_lines_all_{label}.parquet"
    if not all(os.path.exists(p) for p in [pr_header_f, pr_line_f, po_header_f, po_line_f, inv_line_f]):
        print(f"  SKIP {label}: required file missing")
        continue

    # PR totals per segment (released PRs only)
    pr_headers = pl.read_csv(pr_header_f).select(["BANFN", "BUKRS", "STATU"])
    pr_lines = pl.read_csv(pr_line_f).select(["BANFN", "PREIS", "MENGE", "PEINH"])
    released = pr_headers.filter(pl.col("STATU") == PR_STATUS_RELEASED)
    pr_seg = released.with_columns(
        pl.col("BUKRS").cast(pl.Utf8).map_elements(
            lambda b: bukrs_to_seg.get(b, "CORP"), return_dtype=pl.Utf8
        ).alias("seg")
    )
    pr_with_lines = pr_lines.join(pr_seg.select(["BANFN", "seg"]), on="BANFN", how="inner")
    pr_with_lines = pr_with_lines.with_columns(
        (pl.col("PREIS")).alias("line_amount")  # PREIS already PEINH-normalized
    )
    pr_totals = (pr_with_lines.group_by("seg").agg(pl.col("line_amount").sum().alias("total")))

    # PO totals per segment (only invoiced POs would tie to invoices; use ALL POs for commitment view)
    po_headers = pl.read_csv(po_header_f).select(["po_header_id", "vendor_id_ext"])
    po_lines = pl.read_parquet(po_line_f).select(["po_header_id", "_segment_code", "unit_price", "quantity_committed"])
    po_lines = po_lines.with_columns(
        (pl.col("unit_price") * pl.col("quantity_committed")).alias("line_amount")
    )
    po_totals = po_lines.group_by("_segment_code").agg(pl.col("line_amount").sum().alias("total"))

    # Invoice totals per segment
    inv_lines = pl.read_parquet(inv_line_f).select(["_segment_code", "amount"])
    inv_totals = inv_lines.group_by("_segment_code").agg(pl.col("amount").sum().alias("total"))

    for seg in SEGMENT_CODES:
        inv_actual = 0.0
        r = inv_totals.filter(pl.col("_segment_code") == seg)
        if not r.is_empty():
            inv_actual = float(r["total"][0])

        po_actual = 0.0
        r = po_totals.filter(pl.col("_segment_code") == seg)
        if not r.is_empty():
            po_actual = float(r["total"][0])

        pr_actual = 0.0
        r = pr_totals.filter(pl.col("seg") == seg)
        if not r.is_empty():
            pr_actual = float(r["total"][0])

        # PO target ≈ Invoice / PO_TO_INVOICE_COVERAGE
        po_target = inv_actual / PO_TO_INVOICE_COVERAGE if inv_actual else 0.0
        check(f"PO vs Invoice cone {label} {seg}", po_actual, po_target, loose_tol, warn_only=True)

        # PR target ≈ PO / PR_TO_PO_CONVERSION (released PRs only)
        pr_target = po_actual / PR_TO_PO_CONVERSION if po_actual else 0.0
        check(f"PR vs PO cone {label} {seg}", pr_actual, pr_target, loose_tol, warn_only=True)

# COMMAND ----------
# MAGIC %md ## (5) AP balance: creation credits − payment debits ≈ open invoices (INFO)
# MAGIC
# MAGIC Informational. Won't fail the job — useful as a sanity check that payment
# MAGIC JEs are draining the AP balance correctly. The leftover should equal the
# MAGIC sum of unpaid invoices (`payment_status_flag IN ('OPEN_CURRENT', 'OPEN_PAST_DUE')`).

# COMMAND ----------
print("=== AP balance trace (informational) ===")
total_creation_cr = 0.0
total_payment_dr = 0.0
total_open_invoice = 0.0

for (fy, fq) in periods:
    label = f"{fy}Q{fq}"
    je_h_f = f"{FUSION}/gl_je_headers_{label}.csv"
    je_l_f = f"{FUSION}/gl_je_lines_{label}.parquet"
    inv_f = f"{FUSION}/ap_invoices_all_{label}.csv"
    if not all(os.path.exists(p) for p in [je_h_f, je_l_f, inv_f]):
        continue

    headers = pl.read_csv(je_h_f).select(["je_header_id", "je_category"])
    lines = pl.read_parquet(je_l_f).select(["je_header_id", "accounted_dr", "accounted_cr"])
    joined = lines.join(headers, on="je_header_id")

    creation_cr = joined.filter(pl.col("je_category") == "Purchase Invoices") \
                        .select(pl.col("accounted_cr").sum()).item()
    payment_dr = joined.filter(pl.col("je_category") == "Payments") \
                       .select(pl.col("accounted_dr").sum()).item()

    invs = pl.read_csv(inv_f).select(["invoice_amount", "payment_status_flag"])
    open_inv = invs.filter(pl.col("payment_status_flag") != "PAID") \
                   .select(pl.col("invoice_amount").sum()).item()

    total_creation_cr += creation_cr or 0.0
    total_payment_dr += payment_dr or 0.0
    total_open_invoice += open_inv or 0.0
    print(f"  {label}: created_AP=${creation_cr:>12,.0f}  paid=${payment_dr:>12,.0f}  open_invoices=${open_inv:>12,.0f}")

ap_balance_implied = total_creation_cr - total_payment_dr
print(f"\nCumulative: created_AP=${total_creation_cr:,.0f}  paid=${total_payment_dr:,.0f}  "
      f"implied_AP=${ap_balance_implied:,.0f}  open_invoices=${total_open_invoice:,.0f}")
if total_creation_cr > 0:
    drift_pct = (ap_balance_implied - total_open_invoice) / total_open_invoice * 100 if total_open_invoice else 0
    print(f"AP balance drift from open-invoice total: {drift_pct:+.2f}%")

# COMMAND ----------
# MAGIC %md ## Result

# COMMAND ----------
print()
if warnings_list:
    print(f"--- {len(warnings_list)} warning(s) (loose tolerance breaches) ---")
    for w in warnings_list:
        print(f"  - {w}")
    print()

if breaches:
    print(f"--- RECONCILIATION FAILED: {len(breaches)} breach(es) ---")
    for b in breaches:
        print(f"  - {b}")
    raise AssertionError(f"Reconciliation failed: {len(breaches)} anchor breaches.")
else:
    print("--- ALL TIGHT RECONCILIATIONS PASSED ---")
