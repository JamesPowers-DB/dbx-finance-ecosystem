# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: SAP Ariba-shaped raw files
# MAGIC
# MAGIC Ariba is upstream in the procurement chain: supplier master, sourcing
# MAGIC events, contracts, **purchase requests**, and supplier scorecards live here.
# MAGIC POs and invoices live in Fusion (see `03_fusion_files.py`).
# MAGIC
# MAGIC Outputs (CSV) under `/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/`:
# MAGIC
# MAGIC **One file each (stable across regenerations):**
# MAGIC - `LFA1_SUPPLIER_MASTER.csv` — ~3,000 suppliers. Now carries
# MAGIC   `_payment_terms` (Net15/30/45/60, supplier-level) and `_is_regulated_flag`
# MAGIC   for downstream addressability.
# MAGIC - `ARIBA_CONTRACT_WORKSPACE.csv` — ~1,500 inbound contracts
# MAGIC - `ARIBA_SOURCING_EVENT.csv` — ~2,500 RFQs / RFPs / Auctions
# MAGIC
# MAGIC **Per-quarter files:**
# MAGIC - `EBAN_PR_HEADER_<YYYYQq>.csv` — PR headers
# MAGIC - `EBAN_PR_LINE_<YYYYQq>.csv` — PR line items (the descriptions seed downstream PO/invoice lines)
# MAGIC - `ARIBA_SUPPLIER_PERFORMANCE_<YYYYQq>.csv` — quarterly scorecards
# MAGIC
# MAGIC Anchor-driven volumes: PR-line totals per (fy, fq, segment) target
# MAGIC ≈ anchor_spend × (1 / PR_TO_PO_CONVERSION / PO_TO_INVOICE_COVERAGE)
# MAGIC ≈ anchor × 1.5625. ~20% of PRs end up cancelled (status `L`); the other
# MAGIC 80% are released (status `B`) — those become POs in the Fusion generator.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_raw", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("raw_volume", "")
dbutils.widgets.text("target_fiscal_year", "")
dbutils.widgets.text("target_fiscal_quarter", "")

catalog = get_widget("catalog", "")
schema_raw = get_widget("schema_raw", "")
schema_meta = get_widget("schema_meta", "")
raw_volume = get_widget("raw_volume", "")
target = get_target_quarter()

assert catalog and schema_raw and schema_meta and raw_volume, "catalog/schema_raw/schema_meta/raw_volume required"

ensure_volume(spark, catalog, schema_raw, raw_volume)
OUT = volume_dir(catalog, schema_raw, raw_volume, "sap_ariba")
ensure_dir(OUT)
print(f"Output dir: {OUT}")
print(f"Target quarter: {target if target else 'ALL'}")

# COMMAND ----------
# MAGIC %md ## Read anchors + macro

# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
macro = read_macro(spark, catalog, "gold")
periods = quarters_to_generate(anchors, target)
print(f"Generating {len(periods)} quarter(s): {periods}")

# COMMAND ----------
# MAGIC %md ## LFA1_SUPPLIER_MASTER (~3,000 suppliers)
# MAGIC
# MAGIC Now carries:
# MAGIC - `_payment_terms` (Net15/30/45/60) — drives invoice due-date in Fusion
# MAGIC - `_is_regulated_flag` (~8%) — drives Non-Addressable spend tag on invoices

# COMMAND ----------
N_SUPPLIERS = 3000


def build_supplier_master() -> pl.DataFrame:
    rng = rng_for("ariba:lfa1")

    countries = list(COUNTRY_WEIGHTS.keys())
    cw = np.array([COUNTRY_WEIGHTS[c] for c in countries])
    cw = cw / cw.sum()
    land1 = rng.choice(countries, size=N_SUPPLIERS, p=cw)
    spras = np.array([LANG_BY_COUNTRY.get(c, "EN") for c in land1])

    days_ago = rng.lognormal(mean=7.0, sigma=0.8, size=N_SUPPLIERS).clip(30, 365 * 10)
    today_np = np.datetime64(date.today())
    ersda = (today_np - days_ago.astype("timedelta64[D]")).astype("datetime64[D]")

    seg_affinity = rng.choice(
        ["AD", "PA", "SB", "ET", "CROSS"],
        size=N_SUPPLIERS, p=[0.25, 0.25, 0.15, 0.15, 0.20],
    )

    # Fabricated, unique, segment-flavored supplier names (see _lib.make_supplier_names).
    # Keyed to seg_affinity so a supplier's name reads consistently with the
    # categories it primarily buys (cat_pri below is drawn from the same segment).
    supplier_names = make_supplier_names(rng, seg_affinity)

    cat_pri = np.empty(N_SUPPLIERS, dtype=object)
    cat_sec_serialized = np.empty(N_SUPPLIERS, dtype=object)
    for i in range(N_SUPPLIERS):
        candidates = [c["code"] for c in SPEND_CATEGORIES if c["segment"] == seg_affinity[i]]
        if not candidates:
            candidates = SPEND_CATEGORY_CODES
        cat_pri[i] = rng.choice(candidates)
        n_sec = rng.choice([0, 1, 2], p=[0.4, 0.45, 0.15])
        sec: List[str] = []
        if n_sec > 0:
            related = [c["code"] for c in SPEND_CATEGORIES
                       if c["segment"] in (seg_affinity[i], "CROSS")
                       and c["code"] != cat_pri[i]]
            sec = list(rng.choice(related, size=min(n_sec, len(related)), replace=False))
        cat_sec_serialized[i] = json.dumps(sec)

    maverick = rng.beta(2.0, 18.0, size=N_SUPPLIERS).clip(0, 0.3)

    # Payment terms per supplier (weighted draw)
    term_codes = list(PAYMENT_TERMS_WEIGHTS.keys())
    term_probs = np.array([PAYMENT_TERMS_WEIGHTS[t] for t in term_codes])
    term_probs /= term_probs.sum()
    payment_terms = rng.choice(term_codes, size=N_SUPPLIERS, p=term_probs)

    # Regulated suppliers — invoices from them are Non-Addressable regardless of category
    is_regulated = rng.random(N_SUPPLIERS) < REGULATED_SUPPLIER_RATE

    df = pl.DataFrame({
        "LIFNR": [f"SUPP-{1_000_000 + i:07d}" for i in range(N_SUPPLIERS)],
        "NAME1": supplier_names,
        "LAND1": land1,
        "ERSDA": ersda,
        "SPRAS": spras,
        "_supplier_category_primary": cat_pri.astype(str),
        "_supplier_category_secondary_json": cat_sec_serialized.astype(str),
        "_maverick_propensity": np.round(maverick, 4),
        "_industry_segment_affinity": seg_affinity,
        "_payment_terms": payment_terms,
        "_is_regulated_flag": is_regulated,
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

# Lookups
supplier_ids = suppliers_df["LIFNR"].to_numpy()
supplier_primary_cat = suppliers_df["_supplier_category_primary"].to_numpy()
supplier_secondary_cat = [json.loads(s) for s in suppliers_df["_supplier_category_secondary_json"].to_list()]
supplier_maverick = suppliers_df["_maverick_propensity"].to_numpy()
supplier_affinity = suppliers_df["_industry_segment_affinity"].to_numpy()

SUPPLIER_IDX_BY_AFFINITY = {
    seg: np.where(supplier_affinity == seg)[0]
    for seg in ["AD", "PA", "SB", "ET", "CROSS"]
}
# supplier_id -> maverick propensity (used to tilt PR source toward ManualSubmission)
maverick_by_id = dict(zip(supplier_ids, supplier_maverick))

# COMMAND ----------
# MAGIC %md ## ARIBA_CONTRACT_WORKSPACE (~1,500 contracts)

# COMMAND ----------
# Contracts and sourcing events are built into in-memory REGISTRIES here, then
# MUTATED by the per-quarter lineage pass (which mints extra contracts/events
# on demand so every intended PR→contract / PR→event link resolves), then
# WRITTEN once after the quarter loop. This is what lets contract_id /
# sourcing_event_id be stamped on PRs and ride PR→PO→invoice downstream.
# See _lib.py "Procurement document lineage".
N_CONTRACTS = 1500
N_EVENTS = 2500
CONTRACT_FILE = f"{OUT}/ARIBA_CONTRACT_WORKSPACE.csv"
EVENT_FILE = f"{OUT}/ARIBA_SOURCING_EVENT.csv"
_CONTRACT_COLS = ["ContractWorkspaceId", "ContractType", "Title", "AwardedSupplierId",
                  "EffectiveDate", "ExpirationDate", "TotalCommittedSpend",
                  "ActualSpendToDate", "Status", "OwningRegion"]
_EVENT_COLS = ["EventId", "EventType", "Title", "OwnerOrgUnit", "CreatedOn", "ClosedOn",
               "SupplierInvitedCount", "SupplierRespondedCount", "AwardedSupplierId",
               "AwardedAmount", "Status"]

contract_registry: List[Dict] = []
contracts_by_supplier: Dict[str, List[Dict]] = {}
event_registry: List[Dict] = []
events_by_supplier: Dict[str, List[Dict]] = {}


def _register_contract(row: Dict):
    contract_registry.append(row)
    contracts_by_supplier.setdefault(row["AwardedSupplierId"], []).append(row)


def _register_event(row: Dict):
    event_registry.append(row)
    events_by_supplier.setdefault(row["AwardedSupplierId"], []).append(row)


def _as_date(v):
    """Normalize a date-ish value (datetime64 / iso str / date) to datetime.date."""
    if isinstance(v, date):
        return v
    return np.datetime64(v, "D").astype("datetime64[D]").astype(object)


# ---- Base contracts ------------------------------------------------------
if target is None or not os.path.exists(CONTRACT_FILE):
    rng = rng_for("ariba:contracts")
    awarded_idx = rng.choice(N_SUPPLIERS, size=N_CONTRACTS, replace=True,
                             p=(1.0 - supplier_maverick) / (1.0 - supplier_maverick).sum())
    ct_type = rng.choice(["Master", "Statement of Work", "Amendment", "Framework"],
                         size=N_CONTRACTS, p=[0.45, 0.30, 0.10, 0.15])
    eff_days = rng.integers(0, 365 * 3, size=N_CONTRACTS)
    eff_date = (np.datetime64("2023-01-01") + eff_days.astype("timedelta64[D]")).astype("datetime64[D]")
    term_days = rng.integers(365, 365 * 3, size=N_CONTRACTS)
    exp_date = (eff_date + term_days.astype("timedelta64[D]")).astype("datetime64[D]")
    total_commit = np.round(rng.lognormal(mean=12.5, sigma=1.2, size=N_CONTRACTS), 2).clip(50_000, 50_000_000)
    actual_spend = np.round(total_commit * rng.beta(2.0, 3.0, size=N_CONTRACTS), 2)
    status = rng.choice(["Active", "Active", "Active", "Expired", "Draft"], size=N_CONTRACTS)
    region = rng.choice(["NA", "EMEA", "APAC", "LATAM"], size=N_CONTRACTS, p=[0.60, 0.22, 0.13, 0.05])
    eff_d, exp_d = eff_date.astype(object), exp_date.astype(object)
    for i in range(N_CONTRACTS):
        cat_code = supplier_primary_cat[awarded_idx[i]]
        _register_contract({
            "ContractWorkspaceId": f"CW-{2_000_000 + i:08d}",
            "ContractType": str(ct_type[i]),
            "Title": f"{ct_type[i]} — {cat_code}",
            "AwardedSupplierId": str(supplier_ids[awarded_idx[i]]),
            "EffectiveDate": eff_d[i],
            "ExpirationDate": exp_d[i],
            "TotalCommittedSpend": float(total_commit[i]),
            "ActualSpendToDate": float(actual_spend[i]),
            "Status": str(status[i]),
            "OwningRegion": str(region[i]),
            "_category": cat_code,
        })
    print(f"Prepared {len(contract_registry):,} base contracts (in memory)")
else:
    for row in pl.read_csv(CONTRACT_FILE, try_parse_dates=True).iter_rows(named=True):
        row = dict(row)
        row["EffectiveDate"] = _as_date(row["EffectiveDate"])
        row["ExpirationDate"] = _as_date(row["ExpirationDate"])
        row.setdefault("_category", None)
        _register_contract(row)
    print(f"Loaded {len(contract_registry):,} existing contracts (target mode)")

_next_contract_seq = max(
    (int(c["ContractWorkspaceId"].split("-")[1]) - 2_000_000 for c in contract_registry),
    default=N_CONTRACTS - 1) + 1

# COMMAND ----------
# MAGIC %md ## ARIBA_SOURCING_EVENT (~2,500 events)

# COMMAND ----------
# ---- Base sourcing events ------------------------------------------------
if target is None or not os.path.exists(EVENT_FILE):
    rng = rng_for("ariba:events")
    event_type = rng.choice(["RFQ", "RFP", "Auction"], size=N_EVENTS, p=[0.55, 0.30, 0.15])
    created_days = rng.integers(0, 365 * 3, size=N_EVENTS)
    created_on = (np.datetime64("2023-01-01") + created_days.astype("timedelta64[D]")).astype("datetime64[D]")
    closed_days = rng.integers(14, 90, size=N_EVENTS)
    closed_on = (created_on + closed_days.astype("timedelta64[D]")).astype("datetime64[D]")
    invited = rng.integers(3, 12, size=N_EVENTS)
    responded = (invited * rng.beta(3.0, 2.0, size=N_EVENTS)).round().astype(int)
    awarded_idx = rng.integers(0, N_SUPPLIERS, size=N_EVENTS)
    awarded_amt = np.round(rng.lognormal(mean=11.0, sigma=1.3, size=N_EVENTS), 2)
    status = rng.choice(["Awarded", "Awarded", "Awarded", "Closed - No Award"], size=N_EVENTS)
    owner = rng.choice(["Procurement-Aero", "Procurement-IA", "Procurement-BA",
                        "Procurement-ESS", "Procurement-Corp"], size=N_EVENTS)
    cre_d, clo_d = created_on.astype(object), closed_on.astype(object)
    for i in range(N_EVENTS):
        cat_code = supplier_primary_cat[awarded_idx[i]]
        _register_event({
            "EventId": f"SRC-{3_000_000 + i:08d}",
            "EventType": str(event_type[i]),
            "Title": f"{event_type[i]} — {cat_code}",
            "OwnerOrgUnit": str(owner[i]),
            "CreatedOn": cre_d[i],
            "ClosedOn": clo_d[i],
            "SupplierInvitedCount": int(invited[i]),
            "SupplierRespondedCount": int(responded[i]),
            "AwardedSupplierId": str(supplier_ids[awarded_idx[i]]),
            "AwardedAmount": float(awarded_amt[i]),
            "Status": str(status[i]),
            "_category": cat_code,
        })
    print(f"Prepared {len(event_registry):,} base sourcing events (in memory)")
else:
    for row in pl.read_csv(EVENT_FILE, try_parse_dates=True).iter_rows(named=True):
        row = dict(row)
        row["CreatedOn"] = _as_date(row["CreatedOn"])
        row["ClosedOn"] = _as_date(row["ClosedOn"])
        row.setdefault("_category", None)
        _register_event(row)
    print(f"Loaded {len(event_registry):,} existing sourcing events (target mode)")

_next_event_seq = max(
    (int(e["EventId"].split("-")[1]) - 3_000_000 for e in event_registry),
    default=N_EVENTS - 1) + 1


# ---- Lineage lookup + mint helpers ---------------------------------------
def _find_active_contract(supplier_id, on_date, cat_code=None):
    """First Active contract for the supplier whose window covers on_date (category-aligned if possible)."""
    active = [c for c in contracts_by_supplier.get(supplier_id, [])
              if c.get("Status") == "Active"
              and c["EffectiveDate"] <= on_date <= c["ExpirationDate"]]
    if not active:
        return None
    if cat_code is not None:
        for c in active:
            if c.get("_category") == cat_code:
                return c["ContractWorkspaceId"]
    return active[0]["ContractWorkspaceId"]


def _find_awarded_event(supplier_id, on_date, cat_code=None):
    """An Awarded event for the supplier whose award is still valid at on_date (created before, closed within ~2y)."""
    valid = [e for e in events_by_supplier.get(supplier_id, [])
             if e.get("Status") == "Awarded"
             and e["CreatedOn"] <= on_date <= (e["ClosedOn"] + timedelta(days=730))]
    if not valid:
        return None
    if cat_code is not None:
        for e in valid:
            if e.get("_category") == cat_code:
                return e["EventId"]
    return valid[0]["EventId"]


def _mint_contract(supplier_id, on_date, cat_code, min_commit, rng):
    """Create an Active contract covering on_date for this supplier and register it."""
    global _next_contract_seq
    seq = _next_contract_seq
    _next_contract_seq += 1
    ct = str(rng.choice(["Master", "Statement of Work", "Framework"], p=[0.40, 0.35, 0.25]))
    eff = on_date - timedelta(days=int(rng.integers(30, 540)))
    exp = on_date + timedelta(days=int(rng.integers(180, 900)))
    commit = round(float(max(min_commit, CONTRACT_REQUIRED_THRESHOLD) * rng.uniform(1.2, 4.0)), 2)
    row = {
        "ContractWorkspaceId": f"CW-{2_000_000 + seq:08d}",
        "ContractType": ct, "Title": f"{ct} — {cat_code}",
        "AwardedSupplierId": str(supplier_id), "EffectiveDate": eff, "ExpirationDate": exp,
        "TotalCommittedSpend": commit, "ActualSpendToDate": round(commit * float(rng.beta(2.0, 3.0)), 2),
        "Status": "Active", "OwningRegion": "NA", "_category": cat_code,
    }
    _register_contract(row)
    return row["ContractWorkspaceId"]


def _mint_event(supplier_id, on_date, cat_code, amt_hint, rng):
    """Create an Awarded sourcing event preceding on_date for this supplier and register it."""
    global _next_event_seq
    seq = _next_event_seq
    _next_event_seq += 1
    et = str(rng.choice(["RFQ", "RFP", "Auction"], p=[0.55, 0.30, 0.15]))
    created = on_date - timedelta(days=int(rng.integers(30, 365)))
    closed = created + timedelta(days=int(rng.integers(14, 90)))
    invited = int(rng.integers(3, 12))
    row = {
        "EventId": f"SRC-{3_000_000 + seq:08d}",
        "EventType": et, "Title": f"{et} — {cat_code}", "OwnerOrgUnit": "Procurement-Corp",
        "CreatedOn": created, "ClosedOn": closed,
        "SupplierInvitedCount": invited, "SupplierRespondedCount": int(rng.integers(2, invited + 1)),
        "AwardedSupplierId": str(supplier_id),
        "AwardedAmount": round(float(max(amt_hint, SOURCING_EVENT_REQUIRED_THRESHOLD) * rng.uniform(0.9, 1.5)), 2),
        "Status": "Awarded", "_category": cat_code,
    }
    _register_event(row)
    return row["EventId"]


def _assign_pr_source(pr_total, routine, maverick, rng):
    """Sample a PR origination channel, tilted by dollar size, category routineness, and supplier maverick propensity."""
    w = dict(PR_SOURCE_BASE_WEIGHTS)
    if pr_total < 10_000:
        w[PR_SOURCE_CATALOG] *= 2.2; w[PR_SOURCE_AGENT] *= 1.8
        w[PR_SOURCE_PORTAL] *= 0.8;  w[PR_SOURCE_MANUAL] *= 0.7
    elif pr_total > 250_000:
        w[PR_SOURCE_CATALOG] *= 0.05; w[PR_SOURCE_AGENT] *= 0.05
        w[PR_SOURCE_PORTAL] *= 1.3;   w[PR_SOURCE_MANUAL] *= 1.5
    elif pr_total > CONTRACT_REQUIRED_THRESHOLD:
        w[PR_SOURCE_CATALOG] *= 0.30; w[PR_SOURCE_AGENT] *= 0.40
        w[PR_SOURCE_PORTAL] *= 1.2;   w[PR_SOURCE_MANUAL] *= 1.2
    if routine:
        w[PR_SOURCE_CATALOG] *= 1.6; w[PR_SOURCE_AGENT] *= 1.8
    else:
        w[PR_SOURCE_AGENT] *= 0.30  # the agent channel only buys routine goods/services
    w[PR_SOURCE_MANUAL] *= (1.0 + float(maverick) * 6.0)
    p = np.array([w[k] for k in PR_SOURCES], dtype=float)
    p = p / p.sum()
    return str(rng.choice(PR_SOURCES, p=p))

# COMMAND ----------
# MAGIC %md ## Per-quarter PR generation (EBAN-style header + line)
# MAGIC
# MAGIC PRs are sized so that ~80% (the RELEASED ones) feed the Fusion PO generator
# MAGIC at PO_TO_INVOICE_COVERAGE × anchor / PR_TO_PO_CONVERSION ≈ 1.5625× anchor.
# MAGIC PRs are NOT the source of truth for spend totals — invoices are. PR amounts
# MAGIC are *estimates* and will be replaced by actual unit prices on the matched PO.

# COMMAND ----------
AVG_LINE_AMOUNT_TARGET = 13_000.0


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
    rng_pr = rng_for(f"ariba:pr:{quarter_label}")

    # Target PR amount = anchor / 0.80 / 0.80 = anchor × 1.5625
    # (anchor = invoiced; POs = anchor / 0.80; PRs = POs / 0.80)
    pr_inflate = 1.0 / (PR_TO_PO_CONVERSION * PO_TO_INVOICE_COVERAGE)

    pr_headers: List[Dict] = []
    pr_lines: List[Dict] = []
    next_pr_seq = 0  # within this quarter

    bukrs_by_seg = {s["code"]: s["company_code"] for s in SEGMENTS}

    for seg in SEGMENT_CODES:
        target_spend = (anchor_metric(anchors, fy, fq, seg, "cogs")
                        + anchor_metric(anchors, fy, fq, seg, "sga")
                        + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0
        if target_spend <= 0:
            continue
        pr_target = target_spend * pr_inflate

        weights = np.array([
            macro_weight_for_month(fy, m)["demand_idx_mfg"]
            * macro_weight_for_month(fy, m)["seasonality_idx"]
            * (0.7 + 0.3 * macro_weight_for_month(fy, m)["supply_chain_stress_idx"])
            for m in months_
        ])
        monthly_targets = allocate_to_months(pr_target, weights)

        for mi, m in enumerate(months_):
            month_target = monthly_targets[mi]
            n_lines = max(20, int(month_target / AVG_LINE_AMOUNT_TARGET))
            n_prs = max(5, int(n_lines / rng_pr.uniform(3.0, 6.0)))

            seg_pool = SUPPLIER_IDX_BY_AFFINITY[seg]
            cross_pool = SUPPLIER_IDX_BY_AFFINITY["CROSS"]
            n_cross = int(n_prs * 0.20)
            picks_seg = rng_pr.choice(seg_pool, size=n_prs - n_cross, replace=True)
            picks_cross = rng_pr.choice(cross_pool, size=n_cross, replace=True)
            picks = np.concatenate([picks_seg, picks_cross])
            rng_pr.shuffle(picks)

            month_start = date(fy, m, 1)
            month_end = (date(fy, m + 1, 1) if m < 12 else date(fy + 1, 1, 1)) - timedelta(days=1)
            month_span_days = (month_end - month_start).days

            lines_per_pr = rng_pr.integers(1, 8, size=n_prs)
            inflation = macro_weight_for_month(fy, m)["inflation_idx"]

            for i_pr in range(n_prs):
                sup_i = picks[i_pr]
                day_offset = int(rng_pr.integers(0, month_span_days + 1))
                pr_created = month_start + timedelta(days=day_offset)
                banfn = f"PR-{(fy * 10_000_000) + (fq * 1_000_000) + next_pr_seq:010d}"
                next_pr_seq += 1

                # PR-level status. 80% released (will become a PO), 20% cancelled.
                will_release = rng_pr.random() < PR_TO_PO_CONVERSION
                pr_status = PR_STATUS_RELEASED if will_release else PR_STATUS_CANCELLED

                pr_headers.append({
                    "BANFN": banfn,
                    "BUKRS": bukrs_by_seg[seg],
                    "AFNAM": f"requester.{int(rng_pr.integers(0, 5000)):05d}",
                    "ERDAT": pr_created,
                    "BSART": rng_pr.choice(["NB", "RV", "ZS"], p=[0.75, 0.15, 0.10]),
                    "STATU": pr_status,
                    "LFDAT": pr_created + timedelta(days=int(rng_pr.integers(7, 60))),
                    "_segment_code": seg,
                })

                # PR lines under this header
                n_lines_this = int(lines_per_pr[i_pr])
                for li in range(n_lines_this):
                    # Category pick: 75% primary, 19% secondary, 6% maverick-driven
                    primary = supplier_primary_cat[sup_i]
                    secondary = supplier_secondary_cat[sup_i]
                    r = rng_pr.random()
                    if r < 0.75:
                        cat_code = primary
                    elif r < 0.94 and secondary:
                        cat_code = secondary[int(rng_pr.integers(0, len(secondary)))]
                    elif rng_pr.random() < supplier_maverick[sup_i] * 5:
                        cat_code = SPEND_CATEGORY_CODES[int(rng_pr.integers(0, 30))]
                    else:
                        cat_code = primary

                    cat = SPEND_CAT_BY_CODE[cat_code]
                    qty = float(np.round(rng_pr.lognormal(cat["qty_mu"], cat["qty_sigma"]), 3))
                    unit_price = float(np.round(rng_pr.lognormal(cat["price_mu"], cat["price_sigma"]) * inflation, 2))
                    peinh = 1 if unit_price < 1000 else (100 if rng_pr.random() < 0.7 else 1000)
                    preis = round(qty * unit_price / peinh, 2)

                    if rng_pr.random() < MATGROUP_NOISE_RATE:
                        matgroup = SPEND_CATEGORIES[int(rng_pr.integers(0, 30))]["matgroup"]
                    else:
                        matgroup = cat["matgroup"]

                    matnr = f"MAT-{cat['matgroup']}-{int(rng_pr.integers(0, 1_000_000)):06d}"

                    pattern = DESCRIPTION_PATTERNS[int(rng_pr.integers(0, len(DESCRIPTION_PATTERNS)))]
                    adj = cat["adjs"][int(rng_pr.integers(0, len(cat["adjs"])))]
                    noun = cat["nouns"][int(rng_pr.integers(0, len(cat["nouns"])))]
                    extra = cat["extras"][int(rng_pr.integers(0, len(cat["extras"])))]
                    try:
                        extra_filled = extra.format(int(rng_pr.integers(0, 10_000_000)))
                    except (IndexError, ValueError):
                        extra_filled = extra
                    try:
                        txz01 = pattern.format(
                            adj=adj, noun=noun, qty=int(qty),
                            part_no=f"{int(rng_pr.integers(0, 1_000_000)):06d}",
                            model_series=extra_filled,
                        )
                    except (KeyError, IndexError):
                        txz01 = f"{adj} {noun} — {extra_filled}"

                    pr_lines.append({
                        "BANFN": banfn,
                        "BNFPO": (li + 1) * 10,
                        "_supplier_intended": supplier_ids[sup_i],  # demo-only: which supplier this PR intends to use
                        "MATNR": matnr,
                        "MATGROUP": matgroup,
                        "TXZ01": txz01,
                        "MENGE": qty,
                        "MEINS": cat["uom"],
                        "PREIS": unit_price,
                        "PEINH": peinh,
                        "_estimated_net_amount": preis,
                        "WAERS": "USD" if rng_pr.random() < 0.72 else ("EUR" if rng_pr.random() < 0.5 else "GBP"),
                        # Demo-only ground truth — wouldn't exist on real Ariba PR exports.
                        # _true_category_secondary is the 30-leaf code; _true_category_primary is its parent.
                        "_true_category_primary": cat["parent"],
                        "_true_category_secondary": cat_code,
                        "_segment_code": seg,
                        "_month": m,
                        "_year": fy,
                    })

    # Renormalize PR-line _estimated_net_amount per (segment) to hit pr_target
    # (loose — PR amounts are estimates; tight tie-out happens at invoice grain)
    for seg in SEGMENT_CODES:
        seg_lines = [l for l in pr_lines if l["_segment_code"] == seg]
        seg_target = (anchor_metric(anchors, fy, fq, seg, "cogs")
                      + anchor_metric(anchors, fy, fq, seg, "sga")
                      + anchor_metric(anchors, fy, fq, seg, "rd")) * 1_000_000.0 * pr_inflate
        actual = sum(l["_estimated_net_amount"] for l in seg_lines)
        if actual > 0 and seg_target > 0:
            scale = seg_target / actual
            for l in seg_lines:
                l["_estimated_net_amount"] = round(l["_estimated_net_amount"] * scale, 2)
                l["PREIS"] = round(l["PREIS"] * scale, 2)

    # ---- Document lineage: pr_source + contract_id + sourcing_event_id ------
    # Stamp an origination channel on every PR, then link it to a contract and/or
    # a sourcing event by value-threshold + per-source compliance (lookup-or-mint).
    # These references ride PR→PO→invoice downstream, so "managed spend" is answered
    # by document lineage, not a supplier heuristic. See _lib.py "Procurement
    # document lineage". Runs post-renorm so thresholds use final PR dollars.
    rng_lin = rng_for(f"ariba:lineage:{quarter_label}")
    created_by_banfn = {h["BANFN"]: h["ERDAT"] for h in pr_headers}
    lines_by_banfn: Dict[str, List[Dict]] = {}
    for l in pr_lines:
        lines_by_banfn.setdefault(l["BANFN"], []).append(l)

    for banfn, lns in lines_by_banfn.items():
        supplier_id = lns[0]["_supplier_intended"]
        pr_created = created_by_banfn[banfn]
        pr_total = sum(l["_estimated_net_amount"] for l in lns)
        cat_spend: Dict[str, float] = {}
        for l in lns:
            cat_spend[l["_true_category_secondary"]] = (
                cat_spend.get(l["_true_category_secondary"], 0.0) + l["_estimated_net_amount"])
        dom_cat = max(cat_spend, key=cat_spend.get)
        routine = dom_cat in ROUTINE_CATEGORIES
        mav = float(maverick_by_id.get(supplier_id, 0.1))

        src = _assign_pr_source(pr_total, routine, mav, rng_lin)
        comp = SOURCE_COMPLIANCE[src]

        # Soft (jittered) governance thresholds → did this buy *require* each doc?
        contract_req = pr_total > CONTRACT_REQUIRED_THRESHOLD * float(rng_lin.lognormal(0.0, THRESHOLD_JITTER_SIGMA))
        event_req = pr_total > SOURCING_EVENT_REQUIRED_THRESHOLD * float(rng_lin.lognormal(0.0, THRESHOLD_JITTER_SIGMA))

        # Compliance → is each doc actually present? (catalog over-complies on contracts)
        want_contract = rng_lin.random() < (comp["contract_when_required"] if contract_req else comp["contract_overcomply"])
        if rng_lin.random() < LINEAGE_EXCEPTION_RATE:
            want_contract = not want_contract
        want_event = (rng_lin.random() < comp["event_when_required"]) if event_req else False
        if event_req and rng_lin.random() < LINEAGE_EXCEPTION_RATE:
            want_event = not want_event

        contract_id = None
        if want_contract:
            contract_id = (_find_active_contract(supplier_id, pr_created, dom_cat)
                           or _mint_contract(supplier_id, pr_created, dom_cat, pr_total, rng_lin))
        sourcing_event_id = None
        if want_event:
            sourcing_event_id = (_find_awarded_event(supplier_id, pr_created, dom_cat)
                                 or _mint_event(supplier_id, pr_created, dom_cat, pr_total, rng_lin))

        # Stamp on lines, with small per-line dropout (a contracted PR can have an
        # off-contract tail line — mixed PRs are real).
        for l in lns:
            l["_pr_source"] = src
            l["_contract_id"] = None if (contract_id and rng_lin.random() < LINE_LINK_DROPOUT_RATE) else contract_id
            l["_sourcing_event_id"] = None if (sourcing_event_id and rng_lin.random() < LINE_LINK_DROPOUT_RATE) else sourcing_event_id

    # Write
    pr_header_df = pl.DataFrame(pr_headers).select([
        "BANFN", "BUKRS", "AFNAM", "ERDAT", "BSART", "STATU", "LFDAT",
    ])
    # schema_overrides: the lineage columns are mostly NULL early (sourcing is rare),
    # so let Polars know they're strings rather than inferring a Null column.
    pr_line_df = pl.DataFrame(pr_lines, schema_overrides={
        "_pr_source": pl.Utf8, "_contract_id": pl.Utf8, "_sourcing_event_id": pl.Utf8,
    }).select([
        "BANFN", "BNFPO", "MATNR", "MATGROUP", "TXZ01",
        "MENGE", "MEINS", "PREIS", "PEINH", "WAERS",
        "_supplier_intended", "_true_category_primary", "_true_category_secondary",
        "_pr_source", "_contract_id", "_sourcing_event_id",
    ])
    write_csv(pr_header_df, f"{OUT}/EBAN_PR_HEADER_{quarter_label}.csv")
    write_csv(pr_line_df,   f"{OUT}/EBAN_PR_LINE_{quarter_label}.csv")

    # Supplier scorecard for this quarter
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

    n_released = sum(1 for h in pr_headers if h["STATU"] == PR_STATUS_RELEASED)
    print(f"  {quarter_label}: {len(pr_headers):,} PRs ({n_released:,} released, "
          f"{len(pr_headers) - n_released:,} cancelled), {len(pr_lines):,} PR lines, "
          f"{len(perf_rows):,} scorecards")


for (fy, fq) in periods:
    generate_quarter(fy, fq)

# Write the contract & sourcing-event registries LAST — they now include any
# contracts/events minted on demand during the per-quarter lineage pass.
_n_minted_contracts = len(contract_registry) - N_CONTRACTS
_n_minted_events = len(event_registry) - N_EVENTS
write_csv(pl.DataFrame(contract_registry).select(_CONTRACT_COLS), CONTRACT_FILE)
write_csv(pl.DataFrame(event_registry).select(_EVENT_COLS), EVENT_FILE)
print(f"Wrote {len(contract_registry):,} contracts ({max(_n_minted_contracts, 0):,} minted) "
      f"and {len(event_registry):,} sourcing events ({max(_n_minted_events, 0):,} minted)")

print("Ariba generation complete.")
