# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: Oracle Fusion-shaped raw files
# MAGIC
# MAGIC Outputs in `/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/`:
# MAGIC
# MAGIC **Reference (one file each):**
# MAGIC - `gl_periods.csv` — calendar periods
# MAGIC - `gl_code_combinations.csv` — 7-segment COA combos
# MAGIC - `ap_supplier_sites_all.csv` — supplier site addresses
# MAGIC - `ar_customer_sites_all.csv` — customer site addresses
# MAGIC
# MAGIC **Per-quarter (`*_YYYYQq.{csv|parquet}`):**
# MAGIC - `gl_je_headers_*.csv` / `gl_je_lines_*.parquet` — double-entry GL
# MAGIC - `gl_trial_balance_*.csv` / `gl_balances_*.parquet`
# MAGIC - `ap_invoices_all_*.csv` / `ap_invoice_distributions_all_*.parquet`
# MAGIC - `ar_invoices_all_*.csv`
# MAGIC
# MAGIC Cross-system shape: ~80% of AP invoices have an Ariba PO match
# MAGIC (`po_matched_flag = 'Y'`); the remaining 20% are direct vouchers.
# MAGIC AR side is anchored to `revenue` per quarter × segment.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_raw", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("schema_gold", "")
dbutils.widgets.text("raw_volume", "")
dbutils.widgets.text("target_fiscal_year", "")
dbutils.widgets.text("target_fiscal_quarter", "")

catalog = get_widget("catalog", "")
schema_raw = get_widget("schema_raw", "")
schema_meta = get_widget("schema_meta", "")
schema_gold = get_widget("schema_gold", "")
raw_volume = get_widget("raw_volume", "")
target = get_target_quarter()

ensure_volume(spark, catalog, schema_raw, raw_volume)
OUT = volume_dir(catalog, schema_raw, raw_volume, "oracle_fusion")
ensure_dir(OUT)
print(f"Output dir: {OUT}")
print(f"Target quarter: {target if target else 'ALL'}")


# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
macro = read_macro(spark, catalog, schema_raw if False else "gold")
periods = quarters_to_generate(anchors, target)
print(f"Output: {OUT}\nQuarters: {periods}")

# COMMAND ----------
# MAGIC %md ## `gl_periods.csv` — calendar periods 2023-01 → end of last quarter

# COMMAND ----------
PERIODS_FILE = f"{OUT}/gl_periods.csv"
if target is None or not os.path.exists(PERIODS_FILE):
    months: List[date] = []
    y, m = 2023, 1
    end_y = max(fy for fy, _ in periods)
    end_q = max(fq for fy, fq in periods if fy == end_y)
    end_m = end_q * 3
    while (y, m) <= (end_y, end_m):
        months.append(date(y, m, 1))
        m += 1
        if m == 13: m, y = 1, y + 1
    df = pl.DataFrame({
        "period_name": [f"{m.year:04d}-{m.month:02d}" for m in months],
        "period_year": [m.year for m in months],
        "period_num": [m.month for m in months],
        "start_date": months,
        "end_date": [(date(m.year, m.month + 1, 1) if m.month < 12 else date(m.year + 1, 1, 1)) - timedelta(days=1) for m in months],
        "period_status": ["Closed"] * (len(months) - 1) + ["Open"],
    })
    write_csv(df, PERIODS_FILE)
    print(f"Wrote {len(df)} GL periods")

# COMMAND ----------
# MAGIC %md ## `gl_code_combinations.csv` — 7-segment COA
# MAGIC
# MAGIC entity (4 segs + corp) × cost_center (~12/segment) × natural_account (~30 high-volume)
# MAGIC × product (~30) × intercompany (10) × future1/future2 placeholders.

# COMMAND ----------
COA_FILE = f"{OUT}/gl_code_combinations.csv"
if target is None or not os.path.exists(COA_FILE):
    rng = rng_for("fusion:coa")
    rows = []
    ccid = 100_000
    entities = [s["company_code"] for s in HELIOS_SEGMENTS] + [HELIOS_CORP_COMPANY_CODE]
    seg_codes = SEGMENT_CODES + ["CORP"]
    natural_accts = list(NATURAL_ACCOUNTS.keys())
    products = [f"P{i:03d}" for i in range(30)]
    intercompany = ["0000"] + [f"{s['company_code']}" for s in HELIOS_SEGMENTS] + [HELIOS_CORP_COMPANY_CODE] + [f"99{i:02d}" for i in range(4)]
    for ent_idx, ent in enumerate(entities):
        seg = seg_codes[ent_idx]
        n_cc = COST_CENTERS_PER_SEGMENT if seg != "CORP" else 6
        for cc_i in range(n_cc):
            cc = f"{seg[:3]}-CC{cc_i:02d}"
            # not every CC × account exists — random pick of ~30 accounts
            picks = rng.choice(natural_accts, size=20, replace=False)
            for acct in picks:
                product = rng.choice(products)
                ic = rng.choice(intercompany)
                rows.append({
                    "code_combination_id": ccid,
                    "segment1_entity": ent,
                    "segment2_cost_center": cc,
                    "segment3_natural_account": acct,
                    "segment4_product": product,
                    "segment5_intercompany": ic,
                    "segment6_future1": "0000",
                    "segment7_future2": "0000",
                    "natural_account_description": NATURAL_ACCOUNTS[acct][0],
                    "natural_account_type": NATURAL_ACCOUNTS[acct][1],
                    "_helios_segment_code": seg,
                    "enabled_flag": "Y",
                })
                ccid += 1
    coa_df = pl.DataFrame(rows)
    write_csv(coa_df, COA_FILE)
    print(f"Wrote {len(coa_df)} COA combinations")
else:
    coa_df = pl.read_csv(COA_FILE)

# Build per-(segment, account_type) lookup of ccids for fast sampling
COA_BY_SEG_TYPE: Dict[Tuple[str, str], np.ndarray] = {}
for seg in SEGMENT_CODES + ["CORP"]:
    for at in {v[1] for v in NATURAL_ACCOUNTS.values()}:
        mask = (coa_df["_helios_segment_code"] == seg) & (coa_df["natural_account_type"] == at)
        ids = coa_df.filter(mask)["code_combination_id"].to_numpy()
        if len(ids) > 0:
            COA_BY_SEG_TYPE[(seg, at)] = ids


def pick_ccid(rng: np.random.Generator, segment: str, acct_type: str) -> int:
    key = (segment, acct_type)
    if key not in COA_BY_SEG_TYPE:
        key = ("CORP", acct_type)
    return int(rng.choice(COA_BY_SEG_TYPE[key]))


# COMMAND ----------
# MAGIC %md ## Supplier and customer site files (stable)

# COMMAND ----------
SUPP_SITES_FILE = f"{OUT}/ap_supplier_sites_all.csv"
if target is None or not os.path.exists(SUPP_SITES_FILE):
    # Pull Ariba LFA1 supplier ids and create 1-3 sites per supplier
    ariba_supp_path = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba", "LFA1_SUPPLIER_MASTER.csv")
    try:
        suppliers = pl.read_csv(ariba_supp_path)
    except Exception:
        suppliers = pl.DataFrame({"LIFNR": [f"SUPP-{1_000_000 + i:07d}" for i in range(3000)],
                                  "LAND1": ["US"] * 3000})

    rng = rng_for("fusion:sites:supp")
    g = mimesis_for("fusion:sites:supp")
    addr_pool = pool_addresses(g, 500)
    rows = []
    for sup_id, country in suppliers.select(["LIFNR", "LAND1"]).iter_rows():
        n_sites = int(rng.choice([1, 1, 1, 2, 3], p=[0.45, 0.20, 0.10, 0.15, 0.10]))
        for s in range(n_sites):
            addr = addr_pool[int(rng.integers(0, len(addr_pool)))]
            rows.append({
                "vendor_site_id": int(rng.integers(1_000_000, 9_000_000)),
                "vendor_id_ext": sup_id,
                "vendor_site_code": f"{sup_id}-{s+1:02d}",
                "country": country,
                "address_line1": addr["street"],
                "city": addr["city"],
                "postal_code": addr["postal_code"],
                "purchasing_site_flag": "Y" if s == 0 else "N",
                "pay_site_flag": "Y" if s == 0 else "N",
            })
    write_csv(pl.DataFrame(rows), SUPP_SITES_FILE)
    print(f"Wrote {len(rows)} supplier sites")

CUST_SITES_FILE = f"{OUT}/ar_customer_sites_all.csv"
if target is None or not os.path.exists(CUST_SITES_FILE):
    rng = rng_for("fusion:sites:cust")
    g = mimesis_for("fusion:sites:cust")
    name_pool = pool_names(g, 800)
    addr_pool = pool_addresses(g, 500)
    n_customers = 2500
    countries = list(COUNTRY_WEIGHTS.keys())
    cw = np.array([COUNTRY_WEIGHTS[c] for c in countries])
    cw = cw / cw.sum()
    rows = []
    for i in range(n_customers):
        country = rng.choice(countries, p=cw)
        n_sites = int(rng.choice([1, 1, 2, 3, 4], p=[0.55, 0.20, 0.13, 0.08, 0.04]))
        cust_id = f"CUST-{4_000_000 + i:07d}"
        cust_name = name_pool[int(rng.integers(0, len(name_pool)))]
        for s in range(n_sites):
            addr = addr_pool[int(rng.integers(0, len(addr_pool)))]
            rows.append({
                "cust_acct_site_id": int(rng.integers(1_000_000, 9_000_000)),
                "cust_account_id_ext": cust_id,
                "customer_name": cust_name,
                "site_use_code": rng.choice(["BILL_TO", "SHIP_TO", "BILL_TO"]),
                "country": country,
                "address_line1": addr["street"],
                "city": addr["city"],
                "postal_code": addr["postal_code"],
            })
    write_csv(pl.DataFrame(rows), CUST_SITES_FILE)
    print(f"Wrote {len(rows)} customer sites")


# COMMAND ----------
# MAGIC %md ## Per-quarter GL + AP + AR generation

# COMMAND ----------
def macro_factor(year: int, month: int, key: str) -> float:
    row = macro.filter(pl.col("period_month") == date(year, month, 1))
    return float(row[key][0]) if not row.is_empty() else 1.0


def period_name_for(year: int, month: int) -> str:
    # YYYY-MM (sorts lexicographically = sorts chronologically). Diverges slightly
    # from Oracle's usual MMM-YY format ("JAN-25") in favor of demo usability.
    return f"{year:04d}-{month:02d}"


def generate_quarter_fusion(fy: int, fq: int):
    quarter_label = f"{fy}Q{fq}"
    months_ = QUARTER_MONTHS[fq]
    rng = rng_for(f"fusion:q:{quarter_label}")

    # ---------- AP invoices (mirrors RBKP scale, 80% PO-matched) ----------
    ap_inv_rows, ap_dist_rows = [], []
    je_headers, je_lines = [], []
    next_je_header_id = (fy * 10_000_000) + (fq * 1_000_000)
    next_je_line = 0

    for seg in SEGMENT_CODES:
        target_spend = (anchor_metric(anchors, fy, fq, seg, "cogs")
                        + anchor_metric(anchors, fy, fq, seg, "sga")
                        + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        if target_spend <= 0:
            continue

        weights = np.array([macro_factor(fy, m, "demand_idx_mfg")
                            * macro_factor(fy, m, "seasonality_idx") for m in months_])
        monthly_targets = allocate_to_months(target_spend, weights)

        for mi, m in enumerate(months_):
            target_m = monthly_targets[mi]
            n_inv = max(30, int(target_m / 35_000.0))  # avg invoice ~$35k
            amounts = renormalize_amounts(rng, n_inv, target_m, mu=10.0, sigma=0.9)
            for idx in range(n_inv):
                inv_amt = round(float(amounts[idx]), 2)
                po_matched = rng.random() < 0.80
                inv_date = date(fy, m, int(rng.integers(1, 28)))
                inv_num = f"INV-FUSION-{next_je_header_id + idx:010d}"
                ap_inv_rows.append({
                    "invoice_id": next_je_header_id + idx,
                    "invoice_num": inv_num,
                    "vendor_id_ext": f"SUPP-{1_000_000 + int(rng.integers(0, 3000)):07d}",
                    "invoice_amount": inv_amt,
                    "invoice_date": inv_date,
                    "gl_date": inv_date,
                    "period_name": period_name_for(fy, m),
                    "invoice_currency": rng.choice(["USD", "EUR", "GBP", "JPY"], p=[0.70, 0.15, 0.10, 0.05]),
                    "po_matched_flag": "Y" if po_matched else "N",
                    "payment_status": rng.choice(["PAID", "OPEN", "PARTIAL"], p=[0.70, 0.25, 0.05]),
                    "_helios_segment_code": seg,
                })

                # 1-4 distribution lines per invoice.
                # Round each debit independently, then have the last one absorb
                # the rounding drift so Σ(rounded debits) == inv_amt exactly.
                n_d = int(rng.choice([1, 2, 3, 4], p=[0.40, 0.30, 0.20, 0.10]))
                amts_d = renormalize_amounts(rng, n_d, inv_amt, mu=0.0, sigma=0.5)
                debit_amts = [round(float(amts_d[di]), 2) for di in range(n_d)]
                debit_amts[-1] = round(inv_amt - sum(debit_amts[:-1]), 2)
                for di in range(n_d):
                    acct_type = rng.choice(["COGS", "SGA", "RD"], p=[0.70, 0.25, 0.05])
                    ccid = pick_ccid(rng, seg, acct_type)
                    ap_dist_rows.append({
                        "invoice_distribution_id": int(rng.integers(1_000_000, 9_999_999)),
                        "invoice_id": next_je_header_id + idx,
                        "distribution_line_number": di + 1,
                        "code_combination_id": ccid,
                        "amount": debit_amts[di],
                        "period_name": period_name_for(fy, m),
                    })

                # Corresponding JE: DR expense / CR AP (balanced to the cent)
                je_id = next_je_header_id + 500_000 + idx
                je_headers.append({
                    "je_header_id": je_id,
                    "period_name": period_name_for(fy, m),
                    "ledger_id": 1,
                    "je_source": "Payables",
                    "je_category": "Purchase Invoices",
                    "posted_flag": "Y",
                    "posted_date": inv_date,
                    "currency_code": ap_inv_rows[-1]["invoice_currency"],
                    "_helios_segment_code": seg,
                })
                line_no = 0
                for di in range(n_d):
                    line_no += 1
                    je_lines.append({
                        "je_header_id": je_id,
                        "je_line_num": line_no,
                        "code_combination_id": ap_dist_rows[-n_d + di]["code_combination_id"],
                        "entered_dr": debit_amts[di],
                        "entered_cr": 0.0,
                        "accounted_dr": debit_amts[di],
                        "accounted_cr": 0.0,
                        "description": f"AP {inv_num} line {di + 1}",
                    })
                line_no += 1
                ap_ccid = pick_ccid(rng, seg, "BS")
                je_lines.append({
                    "je_header_id": je_id,
                    "je_line_num": line_no,
                    "code_combination_id": ap_ccid,
                    "entered_dr": 0.0,
                    "entered_cr": inv_amt,
                    "accounted_dr": 0.0,
                    "accounted_cr": inv_amt,
                    "description": f"AP {inv_num} credit",
                })
            next_je_header_id += n_inv

    write_csv(pl.DataFrame(ap_inv_rows).drop("_helios_segment_code"),
              f"{OUT}/ap_invoices_all_{quarter_label}.csv")
    write_parquet(pl.DataFrame(ap_dist_rows), f"{OUT}/ap_invoice_distributions_all_{quarter_label}.parquet")

    # ---------- AR invoices (anchored to revenue) ----------
    ar_inv_rows = []
    for seg in SEGMENT_CODES:
        target_rev = anchor_metric(anchors, fy, fq, seg, "revenue") * 1_000_000.0
        if target_rev <= 0:
            continue
        weights = np.array([macro_factor(fy, m, "demand_idx_sales")
                            * macro_factor(fy, m, "seasonality_idx") for m in months_])
        monthly_targets = allocate_to_months(target_rev, weights)
        for mi, m in enumerate(months_):
            target_m = monthly_targets[mi]
            n_inv = max(15, int(target_m / 85_000.0))  # avg AR invoice larger (~$85k)
            amounts = renormalize_amounts(rng, n_inv, target_m, mu=11.0, sigma=1.0)
            for idx in range(n_inv):
                amt = round(float(amounts[idx]), 2)
                inv_date = date(fy, m, int(rng.integers(1, 28)))
                ar_inv_rows.append({
                    "customer_trx_id": int(rng.integers(10_000_000, 99_999_999)),
                    "trx_number": f"AR-{(fy * 10_000_000) + (fq * 1_000_000) + idx:010d}",
                    "cust_account_id_ext": f"CUST-{4_000_000 + int(rng.integers(0, 2500)):07d}",
                    "trx_date": inv_date,
                    "gl_date": inv_date,
                    "period_name": period_name_for(fy, m),
                    "invoice_currency_code": rng.choice(["USD", "EUR", "GBP", "JPY"], p=[0.72, 0.16, 0.07, 0.05]),
                    "total_amount": amt,
                    "status": rng.choice(["PAID", "OPEN", "PARTIAL"], p=[0.72, 0.22, 0.06]),
                    "_helios_segment_code": seg,
                })

                # JE: DR AR / CR Revenue
                je_id = next_je_header_id
                next_je_header_id += 1
                je_headers.append({
                    "je_header_id": je_id,
                    "period_name": period_name_for(fy, m),
                    "ledger_id": 1,
                    "je_source": "Receivables",
                    "je_category": "Sales Invoices",
                    "posted_flag": "Y",
                    "posted_date": inv_date,
                    "currency_code": ar_inv_rows[-1]["invoice_currency_code"],
                    "_helios_segment_code": seg,
                })
                ar_ccid = pick_ccid(rng, seg, "BS")
                rev_ccid = pick_ccid(rng, seg, "REVENUE")
                je_lines.append({
                    "je_header_id": je_id, "je_line_num": 1,
                    "code_combination_id": ar_ccid,
                    "entered_dr": amt, "entered_cr": 0.0,
                    "accounted_dr": amt, "accounted_cr": 0.0,
                    "description": f"AR {ar_inv_rows[-1]['trx_number']} debit",
                })
                je_lines.append({
                    "je_header_id": je_id, "je_line_num": 2,
                    "code_combination_id": rev_ccid,
                    "entered_dr": 0.0, "entered_cr": amt,
                    "accounted_dr": 0.0, "accounted_cr": amt,
                    "description": f"AR {ar_inv_rows[-1]['trx_number']} revenue",
                })

    write_csv(pl.DataFrame(ar_inv_rows).drop("_helios_segment_code"),
              f"{OUT}/ar_invoices_all_{quarter_label}.csv")

    # ---------- Write GL ----------
    write_csv(pl.DataFrame(je_headers).drop("_helios_segment_code"),
              f"{OUT}/gl_je_headers_{quarter_label}.csv")
    write_parquet(pl.DataFrame(je_lines), f"{OUT}/gl_je_lines_{quarter_label}.parquet")

    # ---------- Trial balance + balances (period-end summary) ----------
    je_lines_df = pl.DataFrame(je_lines)
    tb = (je_lines_df.group_by("code_combination_id")
                     .agg([pl.col("accounted_dr").sum().alias("period_net_dr"),
                           pl.col("accounted_cr").sum().alias("period_net_cr")])
                     .with_columns([
                         pl.lit(period_name_for(fy, months_[-1])).alias("period_name"),
                         (pl.col("period_net_dr") - pl.col("period_net_cr")).alias("period_net_balance"),
                     ]))
    write_csv(tb, f"{OUT}/gl_trial_balance_{quarter_label}.csv")
    write_parquet(tb.rename({"period_net_balance": "balance"}),
                  f"{OUT}/gl_balances_{quarter_label}.parquet")

    print(f"  {quarter_label}: {len(ap_inv_rows):,} AP / {len(ar_inv_rows):,} AR / "
          f"{len(je_headers):,} JEs / {len(je_lines):,} JE lines")


for (fy, fq) in periods:
    generate_quarter_fusion(fy, fq)

print("Fusion generation complete.")
