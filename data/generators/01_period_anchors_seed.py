# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: seed `_meta.dim_period_anchors`
# MAGIC
# MAGIC Hand-curated rows for FY2023, FY2024, Q1 2025, Q2 2025, Q3 2025.
# MAGIC Values are at the **Helios 1/10 scale** (reference 10-K/10-Q divided by
# MAGIC 10, with Helios segment names and NA/EMEA/APAC/LATAM geographies).
# MAGIC Numbers approximate the reference filings' reported shape but are not
# MAGIC exact — plausibly "real industrial conglomerate at $3.85B FY revenue."
# MAGIC
# MAGIC Future quarters are NOT added here. They flow through:
# MAGIC `ml/notebooks/01_extract_10q.py` → `02_review_anchor_draft.py` →
# MAGIC MERGE into this table.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_meta", "")

catalog = get_widget("catalog", "")
schema_meta = get_widget("schema_meta", "")
print(f"Seeding {catalog}.{schema_meta}.dim_period_anchors")

# COMMAND ----------
# MAGIC %md ## Anchor values
# MAGIC
# MAGIC Top-level CONSOL totals from reference 10-K/10-Q scaled 1/10. Segment
# MAGIC splits use the mix preserved in `_lib.HELIOS_SEGMENTS` plus segment
# MAGIC operating-margin assumptions (HAD ~28%, HPA ~21%, HSB ~24%, HET ~24%).

# COMMAND ----------
SEGMENT_OP_MARGIN = {"HAD": 0.28, "HPA": 0.21, "HSB": 0.24, "HET": 0.24}

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
]

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
        "segment_name": "Helios Industrial Group (Consolidated)",
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
        "notes": "Hand-seeded baseline. Helios scale = reference filings 1/10; segment names and geographies anonymized.",
    })

    for seg in HELIOS_SEGMENTS:
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
            "notes": "Segment split = mix × CONSOL with HAD/HPA/HSB/HET op-margin assumptions.",
        })

df = pl.DataFrame(rows)
print(f"{len(df)} rows: {df['period_type'].value_counts()}")

# COMMAND ----------
# MAGIC %md ## Write to UC (overwrite, idempotent seed)

# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema_meta}`")

sdf = spark.createDataFrame(df.to_pandas())
(sdf.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"`{catalog}`.`{schema_meta}`.dim_period_anchors"))
print(f"Seeded {sdf.count()} rows into {catalog}.{schema_meta}.dim_period_anchors")

# COMMAND ----------
# MAGIC %md ## Initialize the draft table (empty until first 10-Q lands)

# COMMAND ----------
empty = spark.createDataFrame([], sdf.schema)
(empty.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"`{catalog}`.`{schema_meta}`.dim_period_anchors_draft"))
print(f"Initialized empty {catalog}.{schema_meta}.dim_period_anchors_draft")
