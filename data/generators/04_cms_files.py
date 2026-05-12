# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: In-house Contract Management System (CMS) JSON files
# MAGIC
# MAGIC Outputs line-delimited JSON to
# MAGIC `/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/`.
# MAGIC
# MAGIC **One file each (full mode only):**
# MAGIC - `contract.jsonl` — outbound commercial contracts (~5,000)
# MAGIC - `contract_party.jsonl` — customer + Helios entity per contract
# MAGIC - `contract_line_item.jsonl` — revenue-bearing lines
# MAGIC - `contract_amendment.jsonl` — version history
# MAGIC - `performance_obligation.jsonl` — ASC 606-style obligations
# MAGIC
# MAGIC **Per-quarter:**
# MAGIC - `billing_schedule_YYYYQq.jsonl` — scheduled billings (revenue trigger)
# MAGIC
# MAGIC Contract values aggregate to anchor revenue per (quarter, segment).

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
OUT = volume_dir(catalog, schema_raw, raw_volume, "inhouse_cms")
ensure_dir(OUT)
print(f"Output dir: {OUT}")
print(f"Target quarter: {target if target else 'ALL'}")

# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
macro = read_macro(spark, catalog, schema_raw if False else "gold")
periods = quarters_to_generate(anchors, target)
print(f"Output: {OUT}\nQuarters: {periods}")

# COMMAND ----------
# MAGIC %md ## Customer pool — derived from Fusion `ar_customer_sites_all` when available

# COMMAND ----------
N_CUSTOMERS = 1200
CUSTOMER_POOL_FILE = f"{OUT}/_customer_pool.jsonl"
if target is None or not os.path.exists(CUSTOMER_POOL_FILE):
    rng = rng_for("cms:customers")
    g = mimesis_for("cms:customers")
    names = pool_names(g, 800)

    seg_weights = np.array([s["mix"] for s in HELIOS_SEGMENTS])
    seg_weights /= seg_weights.sum()
    customers = []
    for i in range(N_CUSTOMERS):
        cust_id = f"CUST-{4_000_000 + i:07d}"
        primary_seg = SEGMENT_CODES[int(rng.choice(4, p=seg_weights))]
        customers.append({
            "customer_id": cust_id,
            "customer_name": str(names[int(rng.integers(0, len(names)))]),
            "primary_segment": primary_seg,
            "industry": rng.choice(["Aerospace", "Manufacturing", "Energy", "Utilities", "Real Estate",
                                    "Logistics", "Government", "Healthcare", "Technology", "Education"]),
            "annual_spend_tier": str(rng.choice(["Tier-1", "Tier-2", "Tier-3"], p=[0.10, 0.30, 0.60])),
        })
    customer_df = pl.DataFrame(customers)
    write_jsonl(customer_df, CUSTOMER_POOL_FILE)
    print(f"Wrote {len(customer_df)} customers (pool)")
else:
    customer_df = pl.read_ndjson(CUSTOMER_POOL_FILE)

customer_ids = customer_df["customer_id"].to_numpy()
customer_primary_seg = customer_df["primary_segment"].to_numpy()
customer_spend_tier = customer_df["annual_spend_tier"].to_numpy()

# COMMAND ----------
# MAGIC %md ## Build contracts (full mode only)
# MAGIC
# MAGIC ~5,000 active contracts spanning 2022–2027, with sizes drawn from a tier
# MAGIC distribution that sums (over a typical year) close to anchor revenue.

# COMMAND ----------
N_CONTRACTS = 5000
CONTRACT_FILE = f"{OUT}/contract.jsonl"
LINE_FILE = f"{OUT}/contract_line_item.jsonl"
PARTY_FILE = f"{OUT}/contract_party.jsonl"
AMEND_FILE = f"{OUT}/contract_amendment.jsonl"
PO_FILE = f"{OUT}/performance_obligation.jsonl"

if target is None or not os.path.exists(CONTRACT_FILE):
    rng = rng_for("cms:contracts")
    contracts: List[Dict] = []
    lines: List[Dict] = []
    parties: List[Dict] = []
    amendments: List[Dict] = []
    obligations: List[Dict] = []

    SKU_BY_SEG = {
        "HAD": [(f"SKU-AERO-{i:04d}", f"Aerospace product line {i}") for i in range(120)],
        "HPA": [(f"SKU-HPA-{i:04d}", f"Process automation product {i}") for i in range(100)],
        "HSB": [(f"SKU-HSB-{i:04d}", f"Smart building solution {i}") for i in range(80)],
        "HET": [(f"SKU-HET-{i:04d}", f"Energy transition product {i}") for i in range(90)],
    }

    for ci in range(N_CONTRACTS):
        cust_i = int(rng.integers(0, N_CUSTOMERS))
        cust_id = customer_ids[cust_i]
        seg = customer_primary_seg[cust_i]
        tier = customer_spend_tier[cust_i]

        # Value: tier-based log-normal
        if tier == "Tier-1":
            tcv = float(np.round(rng.lognormal(15.5, 0.7), 2))  # ~$5M+
        elif tier == "Tier-2":
            tcv = float(np.round(rng.lognormal(13.5, 0.8), 2))  # ~$700K
        else:
            tcv = float(np.round(rng.lognormal(11.5, 0.9), 2))  # ~$100K
        tcv = max(50_000.0, tcv)

        contract_id = f"CON-{2024_000_000 + ci:013d}"
        signed_date = date(2022, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 4)))
        start_date = signed_date + timedelta(days=int(rng.integers(0, 60)))
        term_days = int(rng.choice([365, 365, 730, 1095, 1460], p=[0.40, 0.25, 0.20, 0.10, 0.05]))
        end_date = start_date + timedelta(days=term_days)
        status = "Active" if end_date > date.today() else "Expired"

        contracts.append({
            "contract_id": contract_id,
            "contract_number": f"CON-{signed_date.year}-{ci % 100_000:05d}",
            "customer_id": cust_id,
            "helios_entity_segment": seg,
            "signed_date": signed_date.isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_contract_value": tcv,
            "currency": str(rng.choice(["USD", "EUR", "GBP", "JPY"], p=[0.70, 0.16, 0.09, 0.05])),
            "status": status,
            "commercial_terms": str(rng.choice(["Net 30", "Net 45", "Net 60", "Net 90"], p=[0.45, 0.25, 0.20, 0.10])),
            "governing_law": str(rng.choice(["DE-Delaware", "EN-England", "DE-Germany", "JP-Japan"],
                                            p=[0.60, 0.20, 0.15, 0.05])),
        })

        # Parties — Helios entity + customer
        parties.append({"contract_id": contract_id, "party_role": "Provider",
                        "party_id": HELIOS_CORP_COMPANY_CODE,
                        "party_name": f"Helios — {seg}",
                        "segment_code": seg})
        parties.append({"contract_id": contract_id, "party_role": "Customer",
                        "party_id": cust_id,
                        "party_name": str(customer_df.row(cust_i, named=True)["customer_name"]),
                        "segment_code": None})

        # Lines (3-12 per contract)
        n_lines = int(rng.choice([3, 4, 5, 6, 7, 8, 12], p=[0.20, 0.25, 0.20, 0.15, 0.08, 0.07, 0.05]))
        sku_pool = SKU_BY_SEG[seg]
        line_amounts = renormalize_amounts(rng, n_lines, tcv, mu=0.0, sigma=0.6)
        for li in range(n_lines):
            sku, sku_desc = sku_pool[int(rng.integers(0, len(sku_pool)))]
            qty = int(rng.integers(1, 50))
            amt = round(float(line_amounts[li]), 2)
            unit_price = round(amt / qty, 2)
            method = str(rng.choice(["Over-time", "Point-in-time"], p=[0.55, 0.45]))
            lines.append({
                "contract_id": contract_id, "line_no": li + 1,
                "product_sku": sku, "product_description": sku_desc,
                "qty": qty, "unit_price": unit_price, "currency": contracts[-1]["currency"],
                "revenue_recognition_method": method,
                "pct_complete": float(np.round(rng.beta(2.0, 2.0), 3)),
                "line_amount": amt,
            })
            obligations.append({
                "obligation_id": f"PO-OBL-{ci:06d}-{li:02d}",
                "contract_id": contract_id,
                "description": f"Deliver {sku_desc.lower()}",
                "standalone_selling_price": unit_price,
                "recognition_pattern": method,
                "expected_completion_date": (start_date + timedelta(days=int(rng.integers(30, term_days)))).isoformat(),
            })

        # 0-2 amendments per contract (15% have any)
        if rng.random() < 0.25:
            n_amend = int(rng.choice([1, 1, 2], p=[0.7, 0.2, 0.1]))
            for ai in range(n_amend):
                amendments.append({
                    "contract_id": contract_id,
                    "amendment_no": ai + 1,
                    "amendment_type": str(rng.choice(["Extension", "Value Change", "Scope Change", "Termination"],
                                                     p=[0.45, 0.30, 0.20, 0.05])),
                    "effective_date": (signed_date + timedelta(days=int(rng.integers(90, term_days)))).isoformat(),
                    "value_delta": float(np.round(rng.normal(0, tcv * 0.05), 2)),
                })

    write_jsonl(pl.DataFrame(contracts), CONTRACT_FILE)
    write_jsonl(pl.DataFrame(parties), PARTY_FILE)
    write_jsonl(pl.DataFrame(lines), LINE_FILE)
    write_jsonl(pl.DataFrame(amendments), AMEND_FILE)
    write_jsonl(pl.DataFrame(obligations), PO_FILE)
    print(f"Wrote {len(contracts)} contracts, {len(lines)} lines, "
          f"{len(parties)} parties, {len(amendments)} amendments, "
          f"{len(obligations)} obligations")
else:
    print("Skipping contracts (target quarter mode)")

# COMMAND ----------
# MAGIC %md ## Per-quarter billing schedule
# MAGIC
# MAGIC Bills are the revenue trigger. Generated per (quarter, segment) so the
# MAGIC quarterly sum lands at anchor.revenue ± 2%.

# COMMAND ----------
def macro_factor(year: int, month: int, key: str) -> float:
    row = macro.filter(pl.col("period_month") == date(year, month, 1))
    return float(row[key][0]) if not row.is_empty() else 1.0


def generate_quarter_bills(fy: int, fq: int):
    quarter_label = f"{fy}Q{fq}"
    months_ = QUARTER_MONTHS[fq]
    rng = rng_for(f"cms:bill:{quarter_label}")
    rows = []
    for seg in SEGMENT_CODES:
        target_rev = anchor_metric(anchors, fy, fq, seg, "revenue") * 1_000_000.0
        if target_rev <= 0:
            continue
        weights = np.array([macro_factor(fy, m, "demand_idx_sales")
                            * macro_factor(fy, m, "seasonality_idx") for m in months_])
        monthly_targets = allocate_to_months(target_rev, weights)
        seg_customers = np.where(customer_primary_seg == seg)[0]
        for mi, m in enumerate(months_):
            target_m = monthly_targets[mi]
            n_bills = max(30, int(target_m / 65_000.0))
            amounts = renormalize_amounts(rng, n_bills, target_m, mu=10.5, sigma=0.9)
            for idx in range(n_bills):
                cust_i = int(rng.choice(seg_customers)) if len(seg_customers) > 0 else 0
                bill_date = date(fy, m, int(rng.integers(1, 28)))
                rows.append({
                    "schedule_id": f"BILL-{(fy * 10_000_000) + (fq * 1_000_000) + len(rows):010d}",
                    "contract_id": f"CON-{2024_000_000 + int(rng.integers(0, N_CONTRACTS)):013d}",
                    "customer_id": str(customer_ids[cust_i]),
                    "segment_code": seg,
                    "bill_date": bill_date.isoformat(),
                    "amount": round(float(amounts[idx]), 2),
                    "currency": str(rng.choice(["USD", "EUR", "GBP", "JPY"], p=[0.70, 0.16, 0.09, 0.05])),
                    "status": str(rng.choice(["Billed", "Scheduled", "Paid"], p=[0.20, 0.10, 0.70])),
                })
    write_jsonl(pl.DataFrame(rows), f"{OUT}/billing_schedule_{quarter_label}.jsonl")
    print(f"  {quarter_label}: {len(rows):,} billings")


for (fy, fq) in periods:
    generate_quarter_bills(fy, fq)

print("CMS generation complete.")
