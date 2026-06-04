# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: seed `_meta.dim_period_anchors`
# MAGIC
# MAGIC Hand-curated rows spanning FY2023 → Q1 2026 (FY consolidated + quarterly).
# MAGIC Values are at the **1/10 scale** of the reference industrial — 1/10
# MAGIC of the public filings' reported shape, with segment names and
# MAGIC NA/EMEA/APAC/LATAM geographies. Plausibly "real industrial conglomerate
# MAGIC at ~$3.9B FY revenue."
# MAGIC
# MAGIC To extend the demo to additional quarters, hand-code another tuple in
# MAGIC `CONSOL_PERIODS` below and re-run the data-generation job. Earlier
# MAGIC iterations of the demo had an AI-extraction-from-10-Q workflow; it was
# MAGIC removed in favor of direct seeding because the indirection added
# MAGIC complexity without changing what gets demoed.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")

catalog = get_widget("catalog", "")
schema = get_widget("schema", "")
print(f"Seeding {catalog}.{schema}.meta_dim_period_anchors")

# COMMAND ----------
# MAGIC %md ## Anchor values
# MAGIC
# MAGIC Top-level CONSOL totals from reference 10-K/10-Q scaled 1/10. Segment
# MAGIC splits use the mix preserved in `_lib.SEGMENTS` plus segment
# MAGIC operating-margin assumptions (AD ~28%, PA ~21%, SB ~24%, ET ~24%).

# COMMAND ----------
SEGMENT_OP_MARGIN = {"AD": 0.28, "PA": 0.21, "SB": 0.24, "ET": 0.24}

CONSOL_PERIODS = [
    # (period_type, fy, fq, period_end, revenue, cogs, sga, rd, op_inc, int_exp, tax, ni,
    #  cash, ar, inv, ap, lt_debt, total_assets, total_equity, op_cf, capex, fcf, headcount,
    #  filing_type, filing_url)
    ("FY", 2023, None, date(2023, 12, 31),
     3670.0, 2435.0, 525.0, 145.0, 625.0, 65.0, 115.0, 545.0,
     1015.0, 815.0, 555.0, 595.0, 2480.0, 6125.0, 1455.0, 605.0, 95.0, 510.0, 9980,
     "10-K", ""),
    ("FY", 2024, None, date(2024, 12, 31),
     3850.0, 2552.0, 552.0, 152.0, 656.0, 68.0, 122.0, 570.0,
     1060.0, 852.0, 580.0, 622.0, 2542.0, 6310.0, 1502.0, 631.0, 102.0, 529.0, 10200,
     "10-K", ""),
    ("Q", 2025, 1, date(2025, 3, 31),
     924.0, 612.0, 137.0, 38.0, 157.0, 17.0, 30.0, 138.0,
     1085.0, 870.0, 588.0, 632.0, 2530.0, 6362.0, 1525.0, 158.0, 25.0, 133.0, 10260,
     "10-Q", ""),
    ("Q", 2025, 2, date(2025, 6, 30),
     962.0, 638.0, 142.0, 39.0, 162.0, 17.0, 32.0, 142.0,
     1108.0, 895.0, 595.0, 645.0, 2515.0, 6420.0, 1552.0, 165.0, 26.0, 139.0, 10310,
     "10-Q", ""),
    ("Q", 2025, 3, date(2025, 9, 30),
     1001.0, 661.0, 146.0, 40.0, 170.0, 18.0, 33.0, 149.0,
     1135.0, 922.0, 612.0, 660.0, 2500.0, 6485.0, 1582.0, 172.0, 27.0, 145.0, 10355,
     "10-Q", ""),
    ("Q", 2025, 4, date(2025, 12, 31),
     1040.0, 685.0, 150.0, 41.0, 178.0, 18.0, 35.0, 156.0,
     1158.0, 945.0, 620.0, 678.0, 2487.0, 6550.0, 1612.0, 178.0, 28.0, 150.0, 10395,
     "10-K", ""),
    # FY2025 = sum of Q1-Q4 2025 P&L; balance sheet at Q4 close; cash flow summed.
    ("FY", 2025, None, date(2025, 12, 31),
     3927.0, 2596.0, 575.0, 158.0, 667.0, 70.0, 130.0, 585.0,
     1158.0, 945.0, 620.0, 678.0, 2487.0, 6550.0, 1612.0, 673.0, 106.0, 567.0, 10395,
     "10-K", ""),
    ("Q", 2026, 1, date(2026, 3, 31),
     965.0, 640.0, 143.0, 40.0, 164.0, 17.0, 31.0, 144.0,
     1180.0, 962.0, 628.0, 685.0, 2475.0, 6605.0, 1635.0, 165.0, 26.0, 139.0, 10440,
     "10-Q", ""),
]

# COMMAND ----------
# MAGIC %md ## Auto-extend to the current quarter
# MAGIC
# MAGIC So a scheduled refresh keeps producing current data with no one hand-coding
# MAGIC new quarters: project quarterly anchors forward from the last filed quarter
# MAGIC up to the current one by growing the **same quarter a year prior** (preserves
# MAGIC seasonality), and **prorate the in-progress quarter's flow metrics** to the
# MAGIC elapsed fraction of the quarter. Generators clip document dates to today
# MAGIC (see `_lib` as-of helpers), so the partial quarter ties to its prorated
# MAGIC anchor and never emits future-dated rows. Projected quarters are tagged
# MAGIC `filing_type='PROJECTED'`.

# COMMAND ----------
_YOY_GROWTH = 1.04  # ~4% YoY, matching the filed-period trend
_FLOW_IDX = (4, 5, 6, 7, 8, 9, 10, 11, 19, 20, 21)  # P&L + cash-flow flows (prorate partial qtr)


def _project_quarter(base: tuple, fy: int, fq: int, frac: float) -> tuple:
    row = list(base)
    row[0], row[1], row[2], row[3] = "Q", fy, fq, quarter_end(fy, fq)
    for i in range(4, 22):                                  # all $ metrics (P&L, BS, CF)
        row[i] = round(float(base[i]) * _YOY_GROWTH, 1)
    row[22] = int(round(float(base[22]) * _YOY_GROWTH))     # headcount
    row[23], row[24] = "PROJECTED", ""
    if frac < 1.0:                                          # in-progress quarter → prorate flows
        for i in _FLOW_IDX:
            row[i] = round(row[i] * frac, 1)
    return tuple(row)


_as_of = generation_as_of()
_cy, _cq = current_fiscal_quarter(_as_of)
_by_fq = {(r[1], r[2]): r for r in CONSOL_PERIODS if r[0] == "Q"}
_fy, _fq = max((r[1], r[2]) for r in CONSOL_PERIODS if r[0] == "Q")
_projected = []
while True:
    _fq += 1
    if _fq == 5:
        _fq, _fy = 1, _fy + 1
    if (_fy, _fq) > (_cy, _cq):
        break
    _base = _by_fq.get((_fy - 1, _fq))                      # same quarter, prior year
    if _base is None:
        continue                                            # no basis to project — skip
    _proj = _project_quarter(_base, _fy, _fq, quarter_elapsed_fraction(_fy, _fq, _as_of))
    _by_fq[(_fy, _fq)] = _proj
    _projected.append(_proj)

if _projected:
    CONSOL_PERIODS = CONSOL_PERIODS + _projected
    print(f"Auto-extended anchors with {len(_projected)} projected quarter(s): "
          f"{[(r[1], r[2]) for r in _projected]} (as_of {_as_of})")
else:
    print(f"No projection needed — anchors current through {(_cy, _cq)} (as_of {_as_of})")

# COMMAND ----------
# MAGIC %md ## Compose rows — CONSOL + per-segment

# COMMAND ----------
rows = []

for period_type, fy, fq, period_end, rev, cogs, sga, rd, opinc, intexp, tax, ni, \
        cash, ar, inv, ap, ltd, ta, te, ocf, capex, fcf, hc, ftype, furl in CONSOL_PERIODS:

    gp = rev - cogs

    rows.append({
        "period_type": period_type,
        "fiscal_year": fy,
        "fiscal_quarter": fq,
        "period_end_date": period_end,
        "segment_code": "CONSOL",
        "segment_name": "Consolidated",
        "revenue": rev, "cogs": cogs, "gross_profit": gp,
        "sga": sga, "rd": rd, "operating_income": opinc,
        "interest_expense": intexp, "tax_provision": tax, "net_income": ni,
        "cash": cash, "ar": ar, "inventory": inv, "ap": ap, "lt_debt": ltd,
        "total_assets": ta, "total_equity": te,
        "operating_cash_flow": ocf, "capex": capex, "free_cash_flow": fcf,
        "headcount_total": hc,
        "source_filing_type": ftype, "source_filing_url": furl,
        "source_extracted_at": datetime(2026, 5, 10, 0, 0, 0),
        "human_reviewed_by": "SEED",
        "human_reviewed_at": datetime(2026, 5, 10, 0, 0, 0),
        "confidence_score": 1.0,
        "notes": "Hand-seeded baseline. scale = reference filings 1/10; segment names and geographies anonymized.",
    })

    for seg in SEGMENTS:
        seg_rev = round(rev * seg["mix"], 1)
        seg_op = round(seg_rev * SEGMENT_OP_MARGIN[seg["code"]], 1)
        # Allocate COGS/SGA/RD by segment using consolidated proportions
        seg_cogs = round(cogs * seg["mix"], 1)
        seg_sga = round(sga * seg["mix"], 1)
        seg_rd_v = round(rd * seg["mix"], 1)
        seg_gp = round(seg_rev - seg_cogs, 1)
        # Segment headcount proportional to revenue mix
        seg_hc = int(hc * seg["mix"])
        rows.append({
            "period_type": period_type,
            "fiscal_year": fy,
            "fiscal_quarter": fq,
            "period_end_date": period_end,
            "segment_code": seg["code"],
            "segment_name": seg["name"],
            "revenue": seg_rev, "cogs": seg_cogs, "gross_profit": seg_gp,
            "sga": seg_sga, "rd": seg_rd_v, "operating_income": seg_op,
            "interest_expense": None, "tax_provision": None, "net_income": None,
            "cash": None, "ar": None, "inventory": None, "ap": None, "lt_debt": None,
            "total_assets": None, "total_equity": None,
            "operating_cash_flow": None, "capex": None, "free_cash_flow": None,
            "headcount_total": seg_hc,
            "source_filing_type": ftype, "source_filing_url": furl,
            "source_extracted_at": datetime(2026, 5, 10, 0, 0, 0),
            "human_reviewed_by": "SEED",
            "human_reviewed_at": datetime(2026, 5, 10, 0, 0, 0),
            "confidence_score": 1.0,
            "notes": "Segment split = mix × CONSOL with AD/PA/SB/ET op-margin assumptions.",
        })

df = pl.DataFrame(rows)
print(f"{len(df)} rows: {df['period_type'].value_counts()}")

# COMMAND ----------
# MAGIC %md ## Write to UC (overwrite, idempotent seed)

# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")

sdf = spark.createDataFrame(df.to_pandas())
(sdf.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"`{catalog}`.`{schema}`.meta_dim_period_anchors"))
print(f"Seeded {sdf.count()} rows into {catalog}.{schema}.meta_dim_period_anchors")

# COMMAND ----------
# MAGIC %md ## Initialize ml.invoice_classifications (empty until batch inference runs)
# MAGIC
# MAGIC The spend-classification model's batch-inference job MERGEs into this table.
# MAGIC silver.invoice_classification reads from it, and gold.fact_invoices LEFT
# MAGIC JOINs that view — so the table must exist (even empty) for the pipeline
# MAGIC to run before the model has ever scored anything.

# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
# CREATE OR REPLACE so the schema evolves cleanly between demo iterations.
# The table is the *inference output*; truncating between data-gen runs is
# the right behavior (stale predictions tied to old data shouldn't linger).
spark.sql(f"""
    CREATE OR REPLACE TABLE `{catalog}`.`{schema}`.ml_invoice_classifications (
        invoice_line_id BIGINT,
        predicted_primary_category STRING,
        predicted_secondary_category STRING,
        primary_confidence DOUBLE,
        secondary_confidence DOUBLE,
        model_version STRING,
        scored_at TIMESTAMP
    ) USING DELTA
""")
print(f"Created/refreshed {catalog}.{schema}.ml_invoice_classifications (2-tier schema, empty)")
