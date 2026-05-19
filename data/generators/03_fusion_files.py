# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: Oracle Fusion-shaped raw files
# MAGIC
# MAGIC Fusion is downstream of Ariba: receives released PRs, issues POs,
# MAGIC books AP invoices, posts to GL, and tracks payments. Outputs in
# MAGIC `/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/`.
# MAGIC
# MAGIC **Reference (one file each):**
# MAGIC - `gl_periods.csv` — calendar periods (YYYY-MM)
# MAGIC - `gl_code_combinations.csv` — 7-segment COA
# MAGIC - `ap_supplier_sites_all.csv` — supplier site addresses
# MAGIC - `ar_customer_sites_all.csv` — customer site addresses
# MAGIC
# MAGIC **Per-quarter (`*_<YYYYQq>.{csv|parquet}`):**
# MAGIC - **NEW** `po_headers_all_*.csv` / `po_lines_all_*.parquet` — POs from released Ariba PRs
# MAGIC - `ap_invoices_all_*.csv` — invoice headers w/ payment_terms, due_date, payment_date, payment_status
# MAGIC - **NEW** `ap_invoice_lines_all_*.parquet` — invoice line grain (replaces ap_invoice_distributions_all)
# MAGIC - `gl_je_headers_*.csv` / `gl_je_lines_*.parquet` — double-entry GL incl. **payment JEs** (DR AP / CR Cash)
# MAGIC - `gl_trial_balance_*.csv` / `gl_balances_*.parquet`
# MAGIC - `ar_invoices_all_*.csv` — customer invoices
# MAGIC
# MAGIC Chain: Ariba EBAN (released) → Fusion po_headers / po_lines → ap_invoices /
# MAGIC ap_invoice_lines → GL. AP balance drains as payment JEs post.

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

ARIBA = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba")

# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
macro = read_macro(spark, catalog, schema_gold)
periods = quarters_to_generate(anchors, target)
print(f"Output: {OUT}\nQuarters: {periods}")

# COMMAND ----------
# MAGIC %md ## Supplier lookup (payment_terms + regulated flag from Ariba LFA1)

# COMMAND ----------
lfa1_path = f"{ARIBA}/LFA1_SUPPLIER_MASTER.csv"
if not os.path.exists(lfa1_path):
    raise RuntimeError(f"Ariba LFA1 must be generated before Fusion. Missing: {lfa1_path}")

lfa1 = pl.read_csv(lfa1_path, try_parse_dates=True)
supplier_terms = {row["LIFNR"]: row["_payment_terms"] for row in lfa1.iter_rows(named=True)}
supplier_regulated = {row["LIFNR"]: bool(row["_is_regulated_flag"]) for row in lfa1.iter_rows(named=True)}
print(f"Loaded {len(supplier_terms):,} supplier payment-terms lookups")

# COMMAND ----------
# MAGIC %md ## Reference files (unchanged)

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
        if m == 13:
            m, y = 1, y + 1
    df = pl.DataFrame({
        "period_name": [f"{m.year:04d}-{m.month:02d}" for m in months],
        "period_year": [m.year for m in months],
        "period_num":  [m.month for m in months],
        "start_date":  months,
        "end_date":    [(date(m.year, m.month + 1, 1) if m.month < 12 else date(m.year + 1, 1, 1)) - timedelta(days=1) for m in months],
        "period_status": ["Closed"] * (len(months) - 1) + ["Open"],
    })
    write_csv(df, PERIODS_FILE)
    print(f"Wrote {len(df)} GL periods")

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
            picks = rng.choice(natural_accts, size=20, replace=False)
            for acct in picks:
                rows.append({
                    "code_combination_id": ccid,
                    "segment1_entity": ent,
                    "segment2_cost_center": cc,
                    "segment3_natural_account": acct,
                    "segment4_product": rng.choice(products),
                    "segment5_intercompany": rng.choice(intercompany),
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
SUPP_SITES_FILE = f"{OUT}/ap_supplier_sites_all.csv"
if target is None or not os.path.exists(SUPP_SITES_FILE):
    suppliers = lfa1.select(["LIFNR", "LAND1"])
    rng = rng_for("fusion:sites:supp")
    g = mimesis_for("fusion:sites:supp")
    addr_pool = pool_addresses(g, 500)
    rows = []
    for sup_id, country in suppliers.iter_rows():
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
# MAGIC %md ## Per-quarter PO → invoice → JE generation

# COMMAND ----------
def macro_factor(year: int, month: int, key: str) -> float:
    row = macro.filter(pl.col("period_month") == date(year, month, 1))
    return float(row[key][0]) if not row.is_empty() else 1.0


def period_name_for(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def determine_payment_status(invoice_date: date, payment_terms: str, rng: np.random.Generator) -> Tuple[str, Optional[date]]:
    """Pick PAID / OPEN_CURRENT / OPEN_PAST_DUE based on age + terms.
    Returns (status, payment_date_or_None). Aggregated across all invoices in the
    demo window this distributes roughly to PAYMENT_STATUS_MIX_OVERALL."""
    days_term = PAYMENT_TERMS_DAYS.get(payment_terms, 30)
    today = date.today()
    days_old = (today - invoice_date).days
    due_date = invoice_date + timedelta(days=days_term)

    if days_old < days_term:                       # within terms — mostly open
        weights = np.array([0.30, 0.70, 0.00])
    elif days_old < days_term * 2:                 # just past due
        weights = np.array([0.70, 0.05, 0.25])
    elif days_old < days_term * 4:                 # well past — almost all paid
        weights = np.array([0.93, 0.00, 0.07])
    else:                                          # very old — settled
        weights = np.array([0.98, 0.00, 0.02])

    status = str(rng.choice(["PAID", "OPEN_CURRENT", "OPEN_PAST_DUE"], p=weights))

    if status == "PAID":
        if rng.random() < ON_TIME_PAYMENT_RATE:
            # On-time: between due_date - days_term/2 and due_date
            offset = int(rng.integers(int(days_term * 0.4), days_term + 1))
        else:
            # Late: 1-30 days past due
            offset = days_term + int(rng.integers(1, 31))
        payment_dt = invoice_date + timedelta(days=offset)
        if payment_dt > today:
            payment_dt = today
        return "PAID", payment_dt
    return status, None


def apply_recording_noise(actual_leaf: str, rng_local: np.random.Generator) -> str:
    """With probability LABEL_NOISE_RATE, swap `actual_leaf` to a sibling under
    the same parent. Returns the original leaf otherwise (and also when the
    parent has no siblings). Intra-parent only — parent tier is unaffected.

    Real category managers mis-tag inconsistently (~5-15% in practice);
    LABEL_NOISE_RATE is set to 0.08 in _lib. The line's content (vocabulary,
    gl_account, supplier) stays consistent with `actual_leaf` — only the
    recorded label is noisy."""
    if rng_local.random() >= LABEL_NOISE_RATE:
        return actual_leaf
    parent = CHILD_TO_PARENT.get(actual_leaf)
    if not parent:
        return actual_leaf
    siblings = [c for c in PARENT_TO_CHILDREN[parent] if c != actual_leaf]
    if not siblings:
        return actual_leaf
    return str(rng_local.choice(siblings))


def generate_quarter_fusion(fy: int, fq: int):
    quarter_label = f"{fy}Q{fq}"
    months_ = QUARTER_MONTHS[fq]
    rng = rng_for(f"fusion:q:{quarter_label}")
    # Dedicated RNG for label noise so changing the noise rate doesn't shift
    # every other random draw downstream.
    rng_noise = rng_for(f"fusion:label_noise:{quarter_label}")

    # ---- 1. Read released Ariba PRs for this quarter ------------------------
    pr_header_file = f"{ARIBA}/EBAN_PR_HEADER_{quarter_label}.csv"
    pr_line_file = f"{ARIBA}/EBAN_PR_LINE_{quarter_label}.csv"
    if not os.path.exists(pr_header_file) or not os.path.exists(pr_line_file):
        raise RuntimeError(f"Ariba PR files missing for {quarter_label} — run Ariba generator first")

    # try_parse_dates=True so ERDAT/LFDAT come back as date objects (not strings)
    pr_headers = pl.read_csv(pr_header_file, try_parse_dates=True)
    pr_lines = pl.read_csv(pr_line_file, try_parse_dates=True)

    # Only released PRs (status = 'B') become POs
    released_prs = pr_headers.filter(pl.col("STATU") == PR_STATUS_RELEASED)
    released_banfns = set(released_prs["BANFN"].to_list())
    print(f"  {quarter_label}: {len(released_prs):,} released PRs → POs (of {len(pr_headers):,} total)")

    # Group PR lines by header
    pr_lines_by_banfn: Dict[str, List[Dict]] = {}
    for row in pr_lines.iter_rows(named=True):
        if row["BANFN"] in released_banfns:
            pr_lines_by_banfn.setdefault(row["BANFN"], []).append(row)

    # Header attributes lookup
    pr_header_by_banfn: Dict[str, Dict] = {row["BANFN"]: row for row in released_prs.iter_rows(named=True)}

    # ---- 2. Generate POs (one PO per released PR, 1:1 line mapping) --------
    po_headers_rows: List[Dict] = []
    po_lines_rows: List[Dict] = []
    bukrs_to_seg = {s["company_code"]: s["code"] for s in HELIOS_SEGMENTS}

    next_po_header_id = (fy * 100_000_000) + (fq * 10_000_000)
    next_po_line_id   = next_po_header_id

    po_line_index_by_banfn_bnfpo: Dict[Tuple[str, int], Dict] = {}

    for banfn, pr_header in pr_header_by_banfn.items():
        bukrs = str(pr_header["BUKRS"])
        seg = bukrs_to_seg.get(bukrs, "CORP")
        if seg == "CORP":
            continue  # corporate PRs not invoiced through this flow
        pr_lines_for_this = pr_lines_by_banfn.get(banfn, [])
        if not pr_lines_for_this:
            continue
        supplier_id = pr_lines_for_this[0]["_supplier_intended"]
        po_header_id = next_po_header_id
        next_po_header_id += 1
        po_number = f"PO-{fy}{fq}-{po_header_id:09d}"
        pr_created = pr_header["ERDAT"]
        # PR-to-PO lead time: ~5-25 days after PR creation
        po_approved = pr_created + timedelta(days=int(rng.integers(5, 26)))

        po_headers_rows.append({
            "po_header_id": po_header_id,
            "segment1": po_number,
            "type_lookup_code": "STANDARD",
            "vendor_id_ext": supplier_id,
            "vendor_site_code": f"{supplier_id}-01",
            "currency_code": pr_lines_for_this[0]["WAERS"],
            "creation_date": pr_created,
            "approved_date": po_approved,
            "po_status": "OPEN",
            "source_requisition_number_ext": banfn,
            "_helios_segment_code": seg,
        })

        # PO lines mirror PR lines (qty + unit_price stay; some price variation simulating negotiation)
        for prl in pr_lines_for_this:
            po_line_id = next_po_line_id
            next_po_line_id += 1
            # Price variation: PO is 0.95-1.02 of PR estimate (typically negotiated down)
            price_factor = float(rng.uniform(0.95, 1.02))
            po_unit_price = round(float(prl["PREIS"]) * price_factor, 2)
            line_row = {
                "po_line_id": po_line_id,
                "po_header_id": po_header_id,
                "line_num": int(prl["BNFPO"]),
                "item_id_ext": prl["MATNR"],
                "item_description": prl["TXZ01"],
                "quantity_committed": float(prl["MENGE"]),
                "unit_price": po_unit_price,
                "currency_code": prl["WAERS"],
                "material_group_code": prl["MATGROUP"],
                "uom": prl["MEINS"],
                "source_pr_number_ext": banfn,
                "source_pr_line_num_ext": int(prl["BNFPO"]),
                "_segment_code": seg,
                "_true_category_primary": prl["_true_category_primary"],
                "_true_category_secondary": prl["_true_category_secondary"],
                "_intended_invoice_amount": po_unit_price * float(prl["MENGE"]),
            }
            po_lines_rows.append(line_row)
            po_line_index_by_banfn_bnfpo[(banfn, int(prl["BNFPO"]))] = line_row

    print(f"  {quarter_label}: built {len(po_headers_rows):,} POs / {len(po_lines_rows):,} PO lines")

    # ---- 3. Decide which POs get invoiced this quarter ----------------------
    # PO_TO_INVOICE_COVERAGE of POs are invoiced; rest stay open
    invoiced_po_ids: set = set()
    for po in po_headers_rows:
        if rng.random() < PO_TO_INVOICE_COVERAGE:
            invoiced_po_ids.add(po["po_header_id"])
    # Mark closed
    for po in po_headers_rows:
        if po["po_header_id"] in invoiced_po_ids:
            po["po_status"] = "CLOSED"

    # ---- 4. Generate invoice headers + lines for invoiced POs --------------
    ap_invoices_rows: List[Dict] = []
    ap_invoice_lines_rows: List[Dict] = []
    next_invoice_id = (fy * 100_000_000) + (fq * 10_000_000) + 500_000
    next_invoice_line_id = next_invoice_id

    for po in po_headers_rows:
        if po["po_header_id"] not in invoiced_po_ids:
            continue
        # Find PO lines for this PO
        po_lines = [l for l in po_lines_rows if l["po_header_id"] == po["po_header_id"]]
        if not po_lines:
            continue

        supplier_id = po["vendor_id_ext"]
        payment_terms = supplier_terms.get(supplier_id, "Net30")
        days_term = PAYMENT_TERMS_DAYS[payment_terms]

        # Invoice arrives 0-60 days after PO approval, but within the same quarter mostly
        po_approved = po["approved_date"]
        inv_offset = int(np.clip(rng.lognormal(mean=2.7, sigma=0.5), 1, 60))
        invoice_date = po_approved + timedelta(days=inv_offset)
        # Keep invoice within quarter or just past it
        qe = quarter_end(fy, fq)
        if invoice_date > qe + timedelta(days=30):
            invoice_date = qe + timedelta(days=int(rng.integers(0, 30)))

        due_date = invoice_date + timedelta(days=days_term)
        status, payment_dt = determine_payment_status(invoice_date, payment_terms, rng)

        invoice_id = next_invoice_id
        next_invoice_id += 1
        invoice_num = f"INV-{fy}{fq}-{invoice_id:010d}"

        # Build invoice line for each PO line
        line_total = 0.0
        for poline in po_lines:
            line_amount = round(float(poline["_intended_invoice_amount"]), 2)
            line_total += line_amount
            invoice_line_id = next_invoice_line_id
            next_invoice_line_id += 1

            seg = poline["_segment_code"]
            # `cat_code` is the ACTUAL category — the buyer knew what they bought.
            # GL coding follows the actual purchase. Then we apply ~8% recording
            # noise to the RECORDED label (sibling within same parent).
            cat_code = poline["_true_category_secondary"]
            cat_parent = poline["_true_category_primary"]
            acct = CATEGORY_TO_GL_ACCOUNT.get(cat_code, "5000")
            acct_type = NATURAL_ACCOUNTS[acct][1]
            ccid = pick_ccid(rng, seg, acct_type)
            recorded_cat_code = apply_recording_noise(cat_code, rng_noise)
            # Parent stays — noise is intra-parent only.

            ap_invoice_lines_rows.append({
                "invoice_line_id": invoice_line_id,
                "invoice_id": invoice_id,
                "line_number": int(poline["line_num"]),
                "line_type_lookup_code": "ITEM",
                "item_description": poline["item_description"],
                "quantity": float(poline["quantity_committed"]),
                "unit_price": float(poline["unit_price"]),
                "amount": line_amount,
                "po_line_id": poline["po_line_id"],
                "code_combination_id": ccid,
                "_segment_code": seg,
                "_true_category_primary": cat_parent,
                "_true_category_secondary": recorded_cat_code,
            })

        ap_invoices_rows.append({
            "invoice_id": invoice_id,
            "invoice_num": invoice_num,
            "vendor_id_ext": supplier_id,
            "invoice_amount": round(line_total, 2),
            "invoice_currency": po["currency_code"],
            "invoice_date": invoice_date,
            "gl_date": invoice_date,
            "period_name": period_name_for(invoice_date.year, invoice_date.month),
            "payment_terms_name": payment_terms,
            "due_date": due_date,
            "payment_date": payment_dt,
            "payment_status_flag": status,
            "po_matched_flag": "Y",
            "source_po_header_id": po["po_header_id"],
            "_segment_code": po["_helios_segment_code"],
        })

    # ---- 5. Add non-PO direct vouchers (~10% of invoices) ------------------
    n_po_invoices = len(ap_invoices_rows)
    n_non_po = int(n_po_invoices * NON_PO_INVOICE_RATE / (1 - NON_PO_INVOICE_RATE))
    rng_npov = rng_for(f"fusion:non_po:{quarter_label}")
    qs = quarter_start(fy, fq)
    qe = quarter_end(fy, fq)
    for _ in range(n_non_po):
        # Pick random supplier weighted by segment
        seg = SEGMENT_CODES[int(rng_npov.integers(0, len(SEGMENT_CODES)))]
        # Cross-segment supplier for non-PO direct vouchers
        supplier_id = f"SUPP-{1_000_000 + int(rng_npov.integers(0, 3000)):07d}"
        payment_terms = supplier_terms.get(supplier_id, "Net30")
        days_term = PAYMENT_TERMS_DAYS[payment_terms]
        invoice_date = qs + timedelta(days=int(rng_npov.integers(0, (qe - qs).days + 1)))
        due_date = invoice_date + timedelta(days=days_term)
        amount = round(float(rng_npov.lognormal(8.5, 1.2)), 2)
        status, payment_dt = determine_payment_status(invoice_date, payment_terms, rng_npov)

        invoice_id = next_invoice_id
        next_invoice_id += 1
        invoice_num = f"INV-DV-{fy}{fq}-{invoice_id:010d}"

        # Direct voucher gets a randomly-picked category for ML signal
        cat_code = SPEND_CATEGORY_CODES[int(rng_npov.integers(0, 30))]
        cat = SPEND_CAT_BY_CODE[cat_code]
        # Single-line invoice
        pattern = DESCRIPTION_PATTERNS[int(rng_npov.integers(0, len(DESCRIPTION_PATTERNS)))]
        adj = cat["adjs"][int(rng_npov.integers(0, len(cat["adjs"])))]
        noun = cat["nouns"][int(rng_npov.integers(0, len(cat["nouns"])))]
        extra = cat["extras"][int(rng_npov.integers(0, len(cat["extras"])))]
        try:
            extra_filled = extra.format(int(rng_npov.integers(0, 10_000_000)))
        except (IndexError, ValueError):
            extra_filled = extra
        try:
            desc = pattern.format(
                adj=adj, noun=noun, qty=1,
                part_no=f"{int(rng_npov.integers(0, 1_000_000)):06d}",
                model_series=extra_filled,
            )
        except (KeyError, IndexError):
            desc = f"{adj} {noun} — {extra_filled}"

        # GL account derived from the ACTUAL category. Recording noise is
        # applied only to the recorded label (sibling within same parent).
        acct = CATEGORY_TO_GL_ACCOUNT.get(cat_code, "6010")
        acct_type = NATURAL_ACCOUNTS[acct][1]
        ccid = pick_ccid(rng_npov, seg, acct_type)
        recorded_cat_code = apply_recording_noise(cat_code, rng_noise)

        invoice_line_id = next_invoice_line_id
        next_invoice_line_id += 1
        ap_invoice_lines_rows.append({
            "invoice_line_id": invoice_line_id,
            "invoice_id": invoice_id,
            "line_number": 1,
            "line_type_lookup_code": "ITEM",
            "item_description": desc,
            "quantity": 1.0,
            "unit_price": amount,
            "amount": amount,
            "po_line_id": None,
            "code_combination_id": ccid,
            "_segment_code": seg,
            "_true_category_primary": CHILD_TO_PARENT[cat_code],
            "_true_category_secondary": recorded_cat_code,
        })
        ap_invoices_rows.append({
            "invoice_id": invoice_id,
            "invoice_num": invoice_num,
            "vendor_id_ext": supplier_id,
            "invoice_amount": amount,
            "invoice_currency": "USD",
            "invoice_date": invoice_date,
            "gl_date": invoice_date,
            "period_name": period_name_for(invoice_date.year, invoice_date.month),
            "payment_terms_name": payment_terms,
            "due_date": due_date,
            "payment_date": payment_dt,
            "payment_status_flag": status,
            "po_matched_flag": "N",
            "source_po_header_id": None,
            "_segment_code": seg,
        })

    # ---- 6. Renormalize invoice amounts to hit anchor per segment ---------
    # Tight tie-out: total invoice amount per (fy, fq, segment) ≈ anchor cogs+sga+rd ±2%
    for seg in SEGMENT_CODES:
        target_spend = (anchor_metric(anchors, fy, fq, seg, "cogs")
                        + anchor_metric(anchors, fy, fq, seg, "sga")
                        + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        if target_spend <= 0:
            continue
        seg_lines = [l for l in ap_invoice_lines_rows if l["_segment_code"] == seg]
        actual = sum(l["amount"] for l in seg_lines)
        if actual <= 0:
            continue
        scale = target_spend / actual
        # Apply scale to invoice line amounts
        for l in seg_lines:
            l["amount"] = round(l["amount"] * scale, 2)
            l["unit_price"] = round(l["unit_price"] * scale, 2)
        # Recompute invoice header totals
        line_totals: Dict[int, float] = {}
        for l in seg_lines:
            line_totals[l["invoice_id"]] = line_totals.get(l["invoice_id"], 0.0) + l["amount"]
        for inv in ap_invoices_rows:
            if inv["_segment_code"] == seg and inv["invoice_id"] in line_totals:
                inv["invoice_amount"] = round(line_totals[inv["invoice_id"]], 2)

    # ---- 7. Generate creation JEs (DR expense × N lines, CR AP total) ------
    je_headers_rows: List[Dict] = []
    je_lines_rows: List[Dict] = []
    next_je_id = (fy * 100_000_000) + (fq * 10_000_000) + 1_500_000

    inv_by_id = {inv["invoice_id"]: inv for inv in ap_invoices_rows}
    lines_by_inv: Dict[int, List[Dict]] = {}
    for l in ap_invoice_lines_rows:
        lines_by_inv.setdefault(l["invoice_id"], []).append(l)

    for inv in ap_invoices_rows:
        seg = inv["_segment_code"]
        inv_lines = lines_by_inv.get(inv["invoice_id"], [])
        if not inv_lines:
            continue

        # Creation JE
        je_id = next_je_id
        next_je_id += 1
        je_headers_rows.append({
            "je_header_id": je_id,
            "period_name": inv["period_name"],
            "ledger_id": 1,
            "je_source": "Payables",
            "je_category": "Purchase Invoices",
            "posted_flag": "Y",
            "posted_date": inv["invoice_date"],
            "currency_code": inv["invoice_currency"],
            "_helios_segment_code": seg,
        })
        # Rounded debits — last one absorbs drift so JE balances to the cent
        debit_amts = [round(float(l["amount"]), 2) for l in inv_lines]
        total_inv = round(inv["invoice_amount"], 2)
        debit_amts[-1] = round(total_inv - sum(debit_amts[:-1]), 2)
        for di, (line, amt) in enumerate(zip(inv_lines, debit_amts), start=1):
            je_lines_rows.append({
                "je_header_id": je_id,
                "je_line_num": di,
                "code_combination_id": line["code_combination_id"],
                "entered_dr": amt,
                "entered_cr": 0.0,
                "accounted_dr": amt,
                "accounted_cr": 0.0,
                "description": f"AP {inv['invoice_num']} line {di}",
            })
        ap_ccid = pick_ccid(rng, seg, "BS")
        je_lines_rows.append({
            "je_header_id": je_id,
            "je_line_num": len(inv_lines) + 1,
            "code_combination_id": ap_ccid,
            "entered_dr": 0.0,
            "entered_cr": total_inv,
            "accounted_dr": 0.0,
            "accounted_cr": total_inv,
            "description": f"AP {inv['invoice_num']} credit",
        })

        # Payment JE (if paid and payment_date within this quarter or before)
        if inv["payment_date"] is not None:
            pay_je_id = next_je_id
            next_je_id += 1
            pay_period = period_name_for(inv["payment_date"].year, inv["payment_date"].month)
            je_headers_rows.append({
                "je_header_id": pay_je_id,
                "period_name": pay_period,
                "ledger_id": 1,
                "je_source": "Payables",
                "je_category": "Payments",
                "posted_flag": "Y",
                "posted_date": inv["payment_date"],
                "currency_code": inv["invoice_currency"],
                "_helios_segment_code": seg,
            })
            cash_ccid = pick_ccid(rng, seg, "BS")
            je_lines_rows.append({
                "je_header_id": pay_je_id,
                "je_line_num": 1,
                "code_combination_id": ap_ccid,
                "entered_dr": total_inv,
                "entered_cr": 0.0,
                "accounted_dr": total_inv,
                "accounted_cr": 0.0,
                "description": f"Payment {inv['invoice_num']} DR AP",
            })
            je_lines_rows.append({
                "je_header_id": pay_je_id,
                "je_line_num": 2,
                "code_combination_id": cash_ccid,
                "entered_dr": 0.0,
                "entered_cr": total_inv,
                "accounted_dr": 0.0,
                "accounted_cr": total_inv,
                "description": f"Payment {inv['invoice_num']} CR Cash",
            })

    # ---- 8. AR invoices (anchored to revenue) — unchanged from before -----
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
            n_inv = max(15, int(target_m / 85_000.0))
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

                # AR JE: DR AR / CR Revenue
                je_id = next_je_id
                next_je_id += 1
                je_headers_rows.append({
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
                je_lines_rows.append({
                    "je_header_id": je_id, "je_line_num": 1,
                    "code_combination_id": ar_ccid,
                    "entered_dr": amt, "entered_cr": 0.0,
                    "accounted_dr": amt, "accounted_cr": 0.0,
                    "description": f"AR {ar_inv_rows[-1]['trx_number']} debit",
                })
                je_lines_rows.append({
                    "je_header_id": je_id, "je_line_num": 2,
                    "code_combination_id": rev_ccid,
                    "entered_dr": 0.0, "entered_cr": amt,
                    "accounted_dr": 0.0, "accounted_cr": amt,
                    "description": f"AR {ar_inv_rows[-1]['trx_number']} revenue",
                })

    # ---- 9. Write files ---------------------------------------------------
    write_csv(
        pl.DataFrame(po_headers_rows).drop("_helios_segment_code"),
        f"{OUT}/po_headers_all_{quarter_label}.csv",
    )
    # Keep _segment_code (used by silver/gold for segment-level rollups) and the
    # 2-tier label columns (_true_category_primary + _true_category_secondary —
    # the supervised-label propagation path PR→PO→invoice line for ML).
    # Drop only the purely-internal _intended_invoice_amount used during gen.
    write_parquet(
        pl.DataFrame(po_lines_rows).drop("_intended_invoice_amount"),
        f"{OUT}/po_lines_all_{quarter_label}.parquet",
    )

    # AP invoice header — explicit schema because payment_date is None for most early bootstrap rows
    ap_inv_schema = {
        "invoice_id": pl.Int64,
        "invoice_num": pl.Utf8,
        "vendor_id_ext": pl.Utf8,
        "invoice_amount": pl.Float64,
        "invoice_currency": pl.Utf8,
        "invoice_date": pl.Date,
        "gl_date": pl.Date,
        "period_name": pl.Utf8,
        "payment_terms_name": pl.Utf8,
        "due_date": pl.Date,
        "payment_date": pl.Date,
        "payment_status_flag": pl.Utf8,
        "po_matched_flag": pl.Utf8,
        "source_po_header_id": pl.Int64,
        "_segment_code": pl.Utf8,
    }
    write_csv(
        pl.DataFrame(ap_invoices_rows, schema=ap_inv_schema).drop("_segment_code"),
        f"{OUT}/ap_invoices_all_{quarter_label}.csv",
    )

    ap_line_schema = {
        "invoice_line_id": pl.Int64,
        "invoice_id": pl.Int64,
        "line_number": pl.Int64,
        "line_type_lookup_code": pl.Utf8,
        "item_description": pl.Utf8,
        "quantity": pl.Float64,
        "unit_price": pl.Float64,
        "amount": pl.Float64,
        "po_line_id": pl.Int64,
        "code_combination_id": pl.Int64,
        "_segment_code": pl.Utf8,
        "_true_category_primary": pl.Utf8,
        "_true_category_secondary": pl.Utf8,
    }
    write_parquet(
        pl.DataFrame(ap_invoice_lines_rows, schema=ap_line_schema),
        f"{OUT}/ap_invoice_lines_all_{quarter_label}.parquet",
    )

    write_csv(pl.DataFrame(ar_inv_rows).drop("_helios_segment_code"),
              f"{OUT}/ar_invoices_all_{quarter_label}.csv")

    write_csv(pl.DataFrame(je_headers_rows).drop("_helios_segment_code"),
              f"{OUT}/gl_je_headers_{quarter_label}.csv")
    write_parquet(pl.DataFrame(je_lines_rows), f"{OUT}/gl_je_lines_{quarter_label}.parquet")

    # Trial balance + balances
    je_lines_df = pl.DataFrame(je_lines_rows)
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

    n_paid = sum(1 for inv in ap_invoices_rows if inv["payment_status_flag"] == "PAID")
    print(f"  {quarter_label}: {len(po_headers_rows):,} POs ({len(invoiced_po_ids):,} invoiced) / "
          f"{len(ap_invoices_rows):,} invoices ({n_paid:,} paid, "
          f"{len(ap_invoices_rows) - n_paid:,} open) / "
          f"{len(je_headers_rows):,} JEs / {len(je_lines_rows):,} JE lines")


for (fy, fq) in periods:
    generate_quarter_fusion(fy, fq)

print("Fusion generation complete.")
