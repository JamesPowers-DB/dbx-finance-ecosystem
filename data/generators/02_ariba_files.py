# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: SAP Ariba-shaped raw files
# MAGIC
# MAGIC Produces 7 CSV exports in
# MAGIC `/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/`:
# MAGIC
# MAGIC - `LFA1_SUPPLIER_MASTER.csv` — supplier master (one file, ~3,000 rows)
# MAGIC - `ARIBA_CONTRACT_WORKSPACE.csv` — inbound contracts (~1,500 rows)
# MAGIC - `ARIBA_SOURCING_EVENT.csv` — sourcing events (~2,500 rows)
# MAGIC - `EKKO_PO_HEADER_YYYYQq.csv` — PO headers, one file per fiscal quarter
# MAGIC - `EKPO_PO_LINE_YYYYQq.csv` — PO line items (ML training payload)
# MAGIC - `RBKP_INVOICE_HEADER_YYYYQq.csv` — invoice headers
# MAGIC - `ARIBA_SUPPLIER_PERFORMANCE_YYYYQq.csv` — supplier scorecards
# MAGIC
# MAGIC Anchor-driven: for every (`fiscal_year`, `fiscal_quarter`, `segment_code`)
# MAGIC row in `_meta.dim_period_anchors`, the sum of PO-line amounts mapped to
# MAGIC that segment lands within ±2% of `cogs + sga + rd`.
# MAGIC
# MAGIC Quarter-scoped regeneration: set widgets `target_fiscal_year` and
# MAGIC `target_fiscal_quarter` to limit to one quarter. Supplier master,
# MAGIC contracts, and sourcing events are NOT regenerated in that mode.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")
dbutils.widgets.text("target_fiscal_year", "")
dbutils.widgets.text("target_fiscal_quarter", "")

catalog = get_widget("catalog", "finance_demo")
schema_raw = get_widget("schema_raw", "raw_data")
schema_meta = get_widget("schema_meta", "_meta")
raw_volume = get_widget("raw_volume", "files")
target = get_target_quarter()

OUT = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba")
ensure_dir(OUT)
print(f"Output dir: {OUT}")
print(f"Target quarter: {target if target else 'ALL'}")

# COMMAND ----------
# MAGIC %md ## Read anchors and macro (driver-side Polars frames)

# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
macro = read_macro(spark, catalog, schema_raw if False else "gold")
periods = quarters_to_generate(anchors, target)
print(f"Generating {len(periods)} quarter(s): {periods}")

# COMMAND ----------
# MAGIC %md ## LFA1_SUPPLIER_MASTER (3,000 suppliers)
# MAGIC
# MAGIC Stable across regenerations — only rewritten when running in full mode.

# COMMAND ----------
N_SUPPLIERS = 3000


def build_supplier_master() -> pl.DataFrame:
    rng = rng_for("ariba:lfa1")
    g = mimesis_for("ariba:lfa1")
    name_pool = pool_names(g, pool_size=1500)
    suppliers = rng.integers(0, len(name_pool), size=N_SUPPLIERS)
    countries = list(COUNTRY_WEIGHTS.keys())
    cw = np.array([COUNTRY_WEIGHTS[c] for c in countries])
    cw = cw / cw.sum()
    land1 = rng.choice(countries, size=N_SUPPLIERS, p=cw)
    spras = np.array([LANG_BY_COUNTRY.get(c, "EN") for c in land1])

    # ERSDA — older = more likely. Lognormal days-ago, capped.
    days_ago = rng.lognormal(mean=7.0, sigma=0.8, size=N_SUPPLIERS).clip(30, 365 * 10)
    today_np = np.datetime64(date.today())
    ersda = (today_np - days_ago.astype("timedelta64[D]")).astype("datetime64[D]")

    # Segment affinity weights: 25/25/15/15/20 for HAD/HPA/HSB/HET/CROSS
    seg_affinity = rng.choice(
        ["HAD", "HPA", "HSB", "HET", "CROSS"],
        size=N_SUPPLIERS, p=[0.25, 0.25, 0.15, 0.15, 0.20],
    )

    # Primary category — drawn from categories matching the affinity
    cat_pri = np.empty(N_SUPPLIERS, dtype=object)
    cat_sec_serialized = np.empty(N_SUPPLIERS, dtype=object)
    for i in range(N_SUPPLIERS):
        candidates = [c["code"] for c in SPEND_CATEGORIES if c["segment"] == seg_affinity[i]]
        if not candidates:
            candidates = SPEND_CATEGORY_CODES
        cat_pri[i] = rng.choice(candidates)
        # Secondary categories — 0-2 picks
        n_sec = rng.choice([0, 1, 2], p=[0.4, 0.45, 0.15])
        sec = []
        if n_sec > 0:
            related = [c["code"] for c in SPEND_CATEGORIES
                       if c["segment"] in (seg_affinity[i], "CROSS")
                       and c["code"] != cat_pri[i]]
            sec = list(rng.choice(related, size=min(n_sec, len(related)), replace=False))
        cat_sec_serialized[i] = json.dumps(sec)

    maverick = rng.beta(2.0, 18.0, size=N_SUPPLIERS).clip(0, 0.3)

    df = pl.DataFrame({
        "LIFNR": [f"SUPP-{1_000_000 + i:07d}" for i in range(N_SUPPLIERS)],
        "NAME1": name_pool[suppliers],
        "LAND1": land1,
        "ERSDA": ersda,
        "SPRAS": spras,
        "_supplier_category_primary": cat_pri.astype(str),
        "_supplier_category_secondary_json": cat_sec_serialized.astype(str),
        "_maverick_propensity": np.round(maverick, 4),
        "_industry_segment_affinity": seg_affinity,
    })
    return df


SUPPLIER_FILE = f"{OUT}/LFA1_SUPPLIER_MASTER.csv"
if target is None or not os.path.exists(SUPPLIER_FILE):
    suppliers_df = build_supplier_master()
    write_csv(suppliers_df, SUPPLIER_FILE)
    print(f"Wrote {len(suppliers_df)} suppliers")
else:
    suppliers_df = pl.read_csv(SUPPLIER_FILE)
    print(f"Reusing existing supplier master ({len(suppliers_df)} rows)")

# Lookup arrays for fast access during PO generation
supplier_ids = suppliers_df["LIFNR"].to_numpy()
supplier_primary_cat = suppliers_df["_supplier_category_primary"].to_numpy()
supplier_secondary_cat = [json.loads(s) for s in suppliers_df["_supplier_category_secondary_json"].to_list()]
supplier_maverick = suppliers_df["_maverick_propensity"].to_numpy()
supplier_affinity = suppliers_df["_industry_segment_affinity"].to_numpy()
supplier_land = suppliers_df["LAND1"].to_numpy()

# Pre-index suppliers by affinity for weighted sampling
SUPPLIER_IDX_BY_AFFINITY = {
    seg: np.where(supplier_affinity == seg)[0]
    for seg in ["HAD", "HPA", "HSB", "HET", "CROSS"]
}

# COMMAND ----------
# MAGIC %md ## ARIBA_CONTRACT_WORKSPACE (~1,500 contracts)

# COMMAND ----------
N_CONTRACTS = 1500
CONTRACT_FILE = f"{OUT}/ARIBA_CONTRACT_WORKSPACE.csv"
if target is None or not os.path.exists(CONTRACT_FILE):
    rng = rng_for("ariba:contracts")
    awarded_idx = rng.choice(N_SUPPLIERS, size=N_CONTRACTS, replace=True,
                             p=(1.0 - supplier_maverick) / (1.0 - supplier_maverick).sum())
    awarded_supplier = supplier_ids[awarded_idx]
    ct_type = rng.choice(["Master", "Statement of Work", "Amendment", "Framework"],
                          size=N_CONTRACTS, p=[0.45, 0.30, 0.10, 0.15])
    eff_days = rng.integers(0, 365 * 3, size=N_CONTRACTS)
    eff_date = (np.datetime64("2023-01-01") + eff_days.astype("timedelta64[D]")).astype("datetime64[D]")
    term_days = rng.integers(365, 365 * 3, size=N_CONTRACTS)
    exp_date = (eff_date.astype("datetime64[D]") + term_days.astype("timedelta64[D]")).astype("datetime64[D]")
    total_commit = np.round(rng.lognormal(mean=12.5, sigma=1.2, size=N_CONTRACTS), 2).clip(50_000, 50_000_000)
    actual_pct = rng.beta(2.0, 3.0, size=N_CONTRACTS)
    actual_spend = np.round(total_commit * actual_pct, 2)
    status = rng.choice(["Active", "Active", "Active", "Expired", "Draft"], size=N_CONTRACTS)
    region = rng.choice(["NA", "EMEA", "APAC", "LATAM"], size=N_CONTRACTS, p=[0.60, 0.22, 0.13, 0.05])

    df = pl.DataFrame({
        "ContractWorkspaceId": [f"CW-{2_000_000 + i:08d}" for i in range(N_CONTRACTS)],
        "ContractType": ct_type,
        "Title": [f"{ct_type[i]} — {SPEND_CAT_BY_CODE[supplier_primary_cat[awarded_idx[i]]]['code']}" for i in range(N_CONTRACTS)],
        "AwardedSupplierId": awarded_supplier,
        "EffectiveDate": eff_date,
        "ExpirationDate": exp_date,
        "TotalCommittedSpend": total_commit,
        "ActualSpendToDate": actual_spend,
        "Status": status,
        "OwningRegion": region,
    })
    write_csv(df, CONTRACT_FILE)
    print(f"Wrote {len(df)} contracts")
else:
    print("Skipping contracts (target quarter mode)")

# COMMAND ----------
# MAGIC %md ## ARIBA_SOURCING_EVENT (~2,500 events)

# COMMAND ----------
N_EVENTS = 2500
EVENT_FILE = f"{OUT}/ARIBA_SOURCING_EVENT.csv"
if target is None or not os.path.exists(EVENT_FILE):
    rng = rng_for("ariba:events")
    event_type = rng.choice(["RFQ", "RFP", "Auction"], size=N_EVENTS, p=[0.55, 0.30, 0.15])
    created_days = rng.integers(0, 365 * 3, size=N_EVENTS)
    created_on = (np.datetime64("2023-01-01") + created_days.astype("timedelta64[D]")).astype("datetime64[D]")
    closed_days = rng.integers(14, 90, size=N_EVENTS)
    closed_on = (created_on.astype("datetime64[D]") + closed_days.astype("timedelta64[D]")).astype("datetime64[D]")
    invited = rng.integers(3, 12, size=N_EVENTS)
    responded = (invited * rng.beta(3.0, 2.0, size=N_EVENTS)).round().astype(int)
    awarded_idx = rng.integers(0, N_SUPPLIERS, size=N_EVENTS)
    awarded_amt = np.round(rng.lognormal(mean=11.0, sigma=1.3, size=N_EVENTS), 2)
    status = rng.choice(["Awarded", "Awarded", "Awarded", "Closed - No Award"], size=N_EVENTS)

    cat_titles = [SPEND_CAT_BY_CODE[supplier_primary_cat[awarded_idx[i]]]["code"] for i in range(N_EVENTS)]

    df = pl.DataFrame({
        "EventId": [f"SRC-{3_000_000 + i:08d}" for i in range(N_EVENTS)],
        "EventType": event_type,
        "Title": [f"{event_type[i]} — {cat_titles[i]}" for i in range(N_EVENTS)],
        "OwnerOrgUnit": rng.choice(["Procurement-Aero", "Procurement-IA", "Procurement-BA",
                                    "Procurement-ESS", "Procurement-Corp"], size=N_EVENTS),
        "CreatedOn": created_on,
        "ClosedOn": closed_on,
        "SupplierInvitedCount": invited,
        "SupplierRespondedCount": responded,
        "AwardedSupplierId": supplier_ids[awarded_idx],
        "AwardedAmount": awarded_amt,
        "Status": status,
    })
    write_csv(df, EVENT_FILE)
    print(f"Wrote {len(df)} sourcing events")
else:
    print("Skipping sourcing events (target quarter mode)")

# COMMAND ----------
# MAGIC %md ## Per-quarter PO + line + invoice generation
# MAGIC
# MAGIC Loop over (fy, fq) in `periods`. For each segment with a Q anchor row,
# MAGIC compute `target_spend = cogs + sga + rd`, allocate across the 3 months
# MAGIC of the quarter using macro factors, then synthesize POs/lines hitting
# MAGIC the segment's target within ±2%.

# COMMAND ----------
AVG_LINE_AMOUNT_TARGET = 13_000.0  # average extended amount per PO line


def macro_weight_for_month(year: int, month: int) -> Dict[str, float]:
    row = macro.filter(pl.col("period_month") == date(year, month, 1))
    if row.is_empty():
        return {"demand_idx_mfg": 1.0, "seasonality_idx": 1.0,
                "supply_chain_stress_idx": 1.0, "inflation_idx": 1.0}
    r = row.row(0, named=True)
    return {k: float(r[k]) for k in ("demand_idx_mfg", "seasonality_idx",
                                     "supply_chain_stress_idx", "inflation_idx")}


def generate_quarter(fy: int, fq: int):
    quarter_label = f"{fy}Q{fq}"
    months_ = QUARTER_MONTHS[fq]
    rng_po = rng_for(f"ariba:po:{quarter_label}")

    all_ekko: List[Dict] = []
    all_ekpo: List[Dict] = []
    bukrs_by_seg = {s["code"]: s["company_code"] for s in HELIOS_SEGMENTS}

    for seg in SEGMENT_CODES:
        target_spend = (anchor_metric(anchors, fy, fq, seg, "cogs")
                        + anchor_metric(anchors, fy, fq, seg, "sga")
                        + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        if target_spend <= 0:
            continue

        weights = np.array([
            macro_weight_for_month(fy, m)["demand_idx_mfg"]
            * macro_weight_for_month(fy, m)["seasonality_idx"]
            * (0.7 + 0.3 * macro_weight_for_month(fy, m)["supply_chain_stress_idx"])
            for m in months_
        ])
        monthly_targets = allocate_to_months(target_spend, weights)

        for mi, m in enumerate(months_):
            month_target = monthly_targets[mi]
            n_lines = max(20, int(month_target / AVG_LINE_AMOUNT_TARGET))
            n_pos = max(5, int(n_lines / rng_po.uniform(4.0, 7.0)))

            # Pick suppliers for this month's POs — biased by segment affinity
            seg_pool = SUPPLIER_IDX_BY_AFFINITY[seg]
            cross_pool = SUPPLIER_IDX_BY_AFFINITY["CROSS"]
            n_cross = int(n_pos * 0.20)
            picks_seg = rng_po.choice(seg_pool, size=n_pos - n_cross, replace=True)
            picks_cross = rng_po.choice(cross_pool, size=n_cross, replace=True)
            picks = np.concatenate([picks_seg, picks_cross])
            rng_po.shuffle(picks)

            month_start = date(fy, m, 1)
            month_end = (date(fy, m + 1, 1) if m < 12 else date(fy + 1, 1, 1)) - timedelta(days=1)
            month_span_days = (month_end - month_start).days

            lines_per_po = rng_po.integers(1, 13, size=n_pos)
            inflation = macro_weight_for_month(fy, m)["inflation_idx"]

            # Build PO headers + lines, accumulate amounts
            line_idx_offset = len(all_ekpo)
            for i_po in range(n_pos):
                sup_i = picks[i_po]
                day_offset = int(rng_po.integers(0, month_span_days + 1))
                aedat = month_start + timedelta(days=day_offset)
                ebeln = f"PO-{(fy * 10_000_000) + (fq * 1_000_000) + line_idx_offset + i_po:010d}"
                waers = "USD" if rng_po.random() < 0.70 else \
                        ("EUR" if rng_po.random() < 0.45 else
                         ("GBP" if rng_po.random() < 0.4 else "JPY"))
                bsart = rng_po.choice(["NB", "FO", "K", "ZUB", "NB"], p=[0.62, 0.15, 0.05, 0.03, 0.15])
                all_ekko.append({
                    "EBELN": ebeln, "BUKRS": bukrs_by_seg[seg], "LIFNR": supplier_ids[sup_i],
                    "BSART": bsart, "AEDAT": aedat, "BEDAT": aedat + timedelta(days=int(rng_po.integers(-2, 4))),
                    "WAERS": waers, "_segment_code": seg,
                })

                n_lines_this = int(lines_per_po[i_po])
                for li in range(n_lines_this):
                    # Pick category: 75% primary, 19% secondary, 6% maverick
                    primary = supplier_primary_cat[sup_i]
                    secondary = supplier_secondary_cat[sup_i]
                    r = rng_po.random()
                    if r < 0.75:
                        cat_code = primary
                    elif r < 0.94 and secondary:
                        cat_code = secondary[int(rng_po.integers(0, len(secondary)))]
                    else:
                        # Maverick — random category, weighted by supplier's maverick_propensity
                        if rng_po.random() < supplier_maverick[sup_i] * 5:
                            cat_code = SPEND_CATEGORY_CODES[int(rng_po.integers(0, 30))]
                        else:
                            cat_code = primary

                    cat = SPEND_CAT_BY_CODE[cat_code]
                    qty = float(np.round(rng_po.lognormal(cat["qty_mu"], cat["qty_sigma"]), 3))
                    unit_price = float(np.round(rng_po.lognormal(cat["price_mu"], cat["price_sigma"]) * inflation, 2))
                    peinh = 1 if unit_price < 1000 else (100 if rng_po.random() < 0.7 else 1000)
                    netwr = round(qty * unit_price / peinh, 2)

                    # MATGROUP — usually category's matgroup, sometimes wrong (~8%)
                    if rng_po.random() < MATGROUP_NOISE_RATE:
                        matgroup = SPEND_CATEGORIES[int(rng_po.integers(0, 30))]["matgroup"]
                    else:
                        matgroup = cat["matgroup"]

                    # MATNR: MAT-<catCode4>-<seq>
                    matnr = f"MAT-{cat['matgroup']}-{int(rng_po.integers(0, 1_000_000)):06d}"

                    # Build TXZ01 description from category templates
                    pattern = cat["patterns"][int(rng_po.integers(0, len(cat["patterns"])))]
                    adj = cat["adjs"][int(rng_po.integers(0, len(cat["adjs"])))]
                    noun = cat["nouns"][int(rng_po.integers(0, len(cat["nouns"])))]
                    extra = cat["extras"][int(rng_po.integers(0, len(cat["extras"])))]
                    try:
                        extra_filled = extra.format(int(rng_po.integers(0, 10_000_000)))
                    except (IndexError, ValueError):
                        extra_filled = extra
                    try:
                        if "{adj}" in pattern and "{noun}" in pattern and ("{qty}" in pattern):
                            txz01 = pattern.format(adj=adj, noun=noun, qty=int(qty),
                                                    part_no=f"{int(rng_po.integers(0, 1_000_000)):06d}",
                                                    model_series=extra_filled)
                        else:
                            txz01 = pattern.format(adj=adj, noun=noun,
                                                    part_no=f"{int(rng_po.integers(0, 1_000_000)):06d}",
                                                    model_series=extra_filled)
                    except (KeyError, IndexError):
                        txz01 = f"{adj} {noun} — {extra_filled}"

                    all_ekpo.append({
                        "EBELN": ebeln, "EBELP": (li + 1) * 10,
                        "MATNR": matnr, "MATGROUP": matgroup, "TXZ01": txz01,
                        "MENGE": qty, "MEINS": cat["uom"], "NETPR": unit_price, "PEINH": peinh,
                        "NETWR": netwr, "WAERS": waers,
                        "_segment_code": seg, "_true_spend_category": cat_code,
                        "_month": m, "_year": fy,
                    })

        # Renormalize this segment's amounts to match anchor target ± 2%
        seg_lines = [l for l in all_ekpo if l["_segment_code"] == seg
                     and (l["_year"], l["_month"]) in [(fy, m) for m in months_]]
        actual_total = sum(l["NETWR"] for l in seg_lines)
        if actual_total > 0:
            scale = target_spend / actual_total
            for l in seg_lines:
                l["NETWR"] = round(l["NETWR"] * scale, 2)
                l["NETPR"] = round(l["NETPR"] * scale, 2)

    # Now flush PO header and line files for this quarter
    ekko_df = pl.DataFrame(all_ekko).drop("_segment_code")
    ekpo_cols = ["EBELN", "EBELP", "MATNR", "MATGROUP", "TXZ01", "MENGE", "MEINS",
                 "NETPR", "PEINH", "NETWR", "WAERS", "_true_spend_category"]
    ekpo_df = pl.DataFrame(all_ekpo).select(ekpo_cols + ["_segment_code"]).drop("_segment_code")

    write_csv(ekko_df, f"{OUT}/EKKO_PO_HEADER_{quarter_label}.csv")
    write_csv(ekpo_df, f"{OUT}/EKPO_PO_LINE_{quarter_label}.csv")

    # Invoices — match 80% of POs
    rng_inv = rng_for(f"ariba:inv:{quarter_label}")
    invoice_rows: List[Dict] = []
    for h in all_ekko:
        if rng_inv.random() < 0.80:
            po_lines = [l for l in all_ekpo if l["EBELN"] == h["EBELN"]]
            net = sum(l["NETWR"] for l in po_lines)
            tax = round(net * rng_inv.uniform(0.0, 0.08), 2)
            bldat = h["AEDAT"] + timedelta(days=int(rng_inv.lognormal(2.0, 0.4).clip(0, 60)))
            invoice_rows.append({
                "BELNR": f"INV-{(fy * 10_000_000) + (fq * 1_000_000) + len(invoice_rows):010d}",
                "EBELN": h["EBELN"], "LIFNR": h["LIFNR"], "BUKRS": h["BUKRS"],
                "BLDAT": bldat, "BUDAT": bldat + timedelta(days=int(rng_inv.integers(0, 6))),
                "WRBTR": round(net + tax, 2), "WAERS": h["WAERS"],
                "ZFBDT": bldat + timedelta(days=int(rng_inv.choice([30, 45, 60, 90]))),
            })
    if invoice_rows:
        write_csv(pl.DataFrame(invoice_rows), f"{OUT}/RBKP_INVOICE_HEADER_{quarter_label}.csv")

    # Supplier scorecard for this quarter (per active supplier)
    rng_sc = rng_for(f"ariba:perf:{quarter_label}")
    perf_rows: List[Dict] = []
    stress = macro_weight_for_month(fy, months_[1])["supply_chain_stress_idx"]
    for sid in supplier_ids:
        on_time = float(np.round(rng_sc.beta(8.0, 1.5 + stress) * 100, 1).clip(50, 100))
        quality = float(np.round(rng_sc.beta(7.0, 1.5) * 5, 2))
        responsiveness = float(np.round(rng_sc.beta(6.0, 2.0) * 5, 2))
        overall = round((on_time / 20 + quality + responsiveness) / 3, 2)
        perf_rows.append({
            "SupplierId": sid, "EvaluationQuarter": quarter_label,
            "OnTimeDeliveryPct": on_time, "QualityScore": quality,
            "ResponsivenessScore": responsiveness, "OverallRating": overall,
            "EvaluatorOrgUnit": rng_sc.choice(["Procurement-Aero", "Procurement-IA",
                                                "Procurement-BA", "Procurement-ESS",
                                                "Procurement-Corp"]),
        })
    write_csv(pl.DataFrame(perf_rows), f"{OUT}/ARIBA_SUPPLIER_PERFORMANCE_{quarter_label}.csv")

    print(f"  {quarter_label}: {len(all_ekko):,} POs, {len(all_ekpo):,} lines, "
          f"{len(invoice_rows):,} invoices, {len(perf_rows):,} scorecards")


for (fy, fq) in periods:
    generate_quarter(fy, fq)

print("Ariba generation complete.")
