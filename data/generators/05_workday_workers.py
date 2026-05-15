# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: Workday workers (SCD Type 2)
# MAGIC
# MAGIC Writes `/Volumes/${catalog}/${schema_raw}/${raw_volume}/workday/workers.csv`
# MAGIC — a Workday-shaped HR export with full SCD Type 2 history.
# MAGIC
# MAGIC One row per `(worker × state change)`. A worker has:
# MAGIC - **One row** if hired during the demo window and still active (no changes).
# MAGIC - **N rows** if they've been transferred / terminated.
# MAGIC
# MAGIC SCD2 conventions:
# MAGIC - `effective_date` (inclusive) → when this version becomes active.
# MAGIC - `effective_through` (exclusive) → when superseded. `9999-12-31` for the current row.
# MAGIC - `is_current_row` mirrors `effective_through = '9999-12-31'`.
# MAGIC
# MAGIC Anchor-driven: active-worker count per (fy, fq, segment) tracks
# MAGIC `_meta.dim_period_anchors.headcount_total` ±2%. Achieved by attrition
# MAGIC (~6%/qtr), transfers (~1%/qtr), and topping up to the anchor target via
# MAGIC hires each quarter.
# MAGIC
# MAGIC **Full regen only.** SCD2 history is cumulative — partial regeneration would
# MAGIC break the timeline. `target_fiscal_year/quarter` widgets are ignored.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_raw", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("raw_volume", "")

catalog = get_widget("catalog", "")
schema_raw = get_widget("schema_raw", "")
schema_meta = get_widget("schema_meta", "")
raw_volume = get_widget("raw_volume", "")

assert catalog and schema_raw and schema_meta and raw_volume, "catalog/schema_raw/schema_meta/raw_volume must be set"

ensure_volume(spark, catalog, schema_raw, raw_volume)
OUT = volume_dir(catalog, schema_raw, raw_volume, "workday")
ensure_dir(OUT)
print(f"Output: {OUT}/workers.csv")

# COMMAND ----------
# MAGIC %md ## HR constants

# COMMAND ----------
JOB_FAMILIES = [
    "Engineering", "Operations", "Sales", "Customer Success",
    "Research & Development", "Finance", "G&A", "Marketing", "IT",
]

# (band, base_salary_min, base_salary_max, weight_in_population)
SENIORITY_BANDS = [
    {"band": "Entry",     "salary_min": 55_000,  "salary_max": 80_000,  "weight": 0.20},
    {"band": "Mid",       "salary_min": 80_000,  "salary_max": 125_000, "weight": 0.32},
    {"band": "Senior",    "salary_min": 125_000, "salary_max": 185_000, "weight": 0.25},
    {"band": "Staff",     "salary_min": 185_000, "salary_max": 250_000, "weight": 0.13},
    {"band": "Principal", "salary_min": 250_000, "salary_max": 350_000, "weight": 0.07},
    {"band": "Executive", "salary_min": 350_000, "salary_max": 600_000, "weight": 0.03},
]
SENIORITY_BAND_WEIGHTS = np.array([b["weight"] for b in SENIORITY_BANDS])
SENIORITY_BAND_WEIGHTS /= SENIORITY_BAND_WEIGHTS.sum()

LOADED_MULTIPLIER = 1.30   # benefits, payroll tax, equipment, etc.
ATTRITION_LO, ATTRITION_HI = 0.05, 0.08   # 5-8% per quarter (~22-30% annualized)
TRANSFER_RATE = 0.012      # 1.2% per quarter
PRE_DEMO_HIRE_WINDOW_DAYS = 1825   # 5 years before demo start

# COMMAND ----------
# MAGIC %md ## Anchors → quarter list

# COMMAND ----------
anchors = read_anchors(spark, catalog, schema_meta)
periods = quarters_to_generate(anchors, None)  # always full
print(f"Generating SCD2 history across {len(periods)} quarters: {periods[0]} → {periods[-1]}")

# COMMAND ----------
# MAGIC %md ## Generation

# COMMAND ----------
rng = rng_for("hr:workers")
g = mimesis_for("hr:workers")

# Mimesis pools
first_pool = np.array([g.person.first_name() for _ in range(800)])
last_pool  = np.array([g.person.last_name()  for _ in range(800)])

# Country mix matching the rest of the demo
countries_list = list(COUNTRY_WEIGHTS.keys())
country_probs = np.array([COUNTRY_WEIGHTS[c] for c in countries_list])
country_probs /= country_probs.sum()

# State
employees: Dict[str, Dict] = {}    # worker_id → CURRENT state dict
worker_versions: Dict[str, int] = {}  # worker_id → next version_seq
scd2_rows: List[Dict] = []         # output rows (each is one SCD2 version)
next_worker_id = 1_000_000


def make_new_worker(segment_code: str, hire_date: date) -> Dict:
    """Generate a brand-new worker with stable identity + initial role/comp."""
    global next_worker_id
    wid = f"WK-{next_worker_id:07d}"
    next_worker_id += 1

    first = str(first_pool[int(rng.integers(0, len(first_pool)))])
    last  = str(last_pool[int(rng.integers(0, len(last_pool)))])
    email_local = f"{first.lower()}.{last.lower()}.{next_worker_id - 1}".replace(" ", "")
    email = f"{email_local}@helios.example"

    band = SENIORITY_BANDS[int(rng.choice(len(SENIORITY_BANDS), p=SENIORITY_BAND_WEIGHTS))]
    base = float(round(rng.uniform(band["salary_min"], band["salary_max"]), 2))

    country = str(rng.choice(countries_list, p=country_probs))
    region = COUNTRY_TO_GEO.get(country, "OTHER")

    cc_idx = int(rng.integers(0, COST_CENTERS_PER_SEGMENT))
    cost_center = f"{segment_code[:3]}-CC{cc_idx:02d}"

    return {
        "worker_id": wid,
        "worker_name_first": first,
        "worker_name_last": last,
        "work_email": email,
        "hire_date": hire_date,
        "termination_date": None,
        "worker_status": "Active",
        "organization_id": segment_code,
        "cost_center_id": cost_center,
        "country_code": country,
        "region": region,
        "job_family": JOB_FAMILIES[int(rng.integers(0, len(JOB_FAMILIES)))],
        "compensation_grade": band["band"],
        "annual_base_salary_amount": base,
        "currency_code": "USD",
    }


def open_version(worker: Dict, effective_from: date) -> None:
    """Append a new SCD2 row representing `worker`'s current state, open-ended."""
    wid = worker["worker_id"]
    version_seq = worker_versions.get(wid, 0) + 1
    worker_versions[wid] = version_seq
    row = dict(worker)
    row.update({
        "version_seq": version_seq,
        "effective_date": effective_from,
        "effective_through": date(9999, 12, 31),
        "is_current_row": True,
    })
    scd2_rows.append(row)


def close_current_version(worker_id: str, close_date: date) -> None:
    """Find this worker's most-recent open row and close it."""
    for row in reversed(scd2_rows):
        if row["worker_id"] == worker_id and row["is_current_row"]:
            row["effective_through"] = close_date
            row["is_current_row"] = False
            return
    raise RuntimeError(f"No open row found for worker {worker_id}")


def active_in_segment(seg: str) -> List[Dict]:
    return [e for e in employees.values()
            if e["organization_id"] == seg and e["worker_status"] == "Active"]


def random_day_in_quarter(fy: int, fq: int) -> date:
    qs = quarter_start(fy, fq)
    qe = quarter_end(fy, fq)
    return qs + timedelta(days=int(rng.integers(0, (qe - qs).days + 1)))


# ---- Bootstrap: hire to anchor at the first quarter ------------------------
first_fy, first_fq = periods[0]
first_qs = quarter_start(first_fy, first_fq)
print(f"Bootstrapping initial population at {first_qs}...")

for seg in SEGMENT_CODES:
    target = int(anchor_metric(anchors, first_fy, first_fq, seg, "headcount_total"))
    if target <= 0:
        continue
    for _ in range(target):
        # Spread pre-demo hire dates across the prior 5 years
        days_back = int(rng.integers(30, PRE_DEMO_HIRE_WINDOW_DAYS))
        hire_dt = first_qs - timedelta(days=days_back)
        w = make_new_worker(seg, hire_dt)
        employees[w["worker_id"]] = w
        # Initial SCD2 row has effective_from = hire_date (not first quarter)
        open_version(w, hire_dt)
    print(f"  bootstrap {seg}: hired {target:,}")


# ---- Iterate through remaining quarters ------------------------------------
for q_idx, (fy, fq) in enumerate(periods[1:], start=1):
    qs = quarter_start(fy, fq)

    # Phase 1: attrition per segment
    for seg in SEGMENT_CODES:
        seg_active = active_in_segment(seg)
        if not seg_active:
            continue
        n_attrit = int(len(seg_active) * rng.uniform(ATTRITION_LO, ATTRITION_HI))
        if n_attrit > 0:
            terms_idx = rng.choice(len(seg_active), size=n_attrit, replace=False)
            for idx in terms_idx:
                w = seg_active[idx]
                term_dt = random_day_in_quarter(fy, fq)
                close_current_version(w["worker_id"], term_dt)
                w["worker_status"] = "Terminated"
                w["termination_date"] = term_dt
                open_version(w, term_dt)

    # Phase 2: cross-segment transfers
    all_active = [e for e in employees.values() if e["worker_status"] == "Active"]
    n_xfers = int(len(all_active) * TRANSFER_RATE)
    if n_xfers > 0:
        xfer_idx = rng.choice(len(all_active), size=n_xfers, replace=False)
        for idx in xfer_idx:
            w = all_active[idx]
            from_seg = w["organization_id"]
            to_seg = str(rng.choice([s for s in SEGMENT_CODES if s != from_seg]))
            xfer_dt = random_day_in_quarter(fy, fq)
            close_current_version(w["worker_id"], xfer_dt)
            w["organization_id"] = to_seg
            cc_idx = int(rng.integers(0, COST_CENTERS_PER_SEGMENT))
            w["cost_center_id"] = f"{to_seg[:3]}-CC{cc_idx:02d}"
            open_version(w, xfer_dt)

    # Phase 3: hire (or extra-terminate) to land on anchor headcount per segment
    for seg in SEGMENT_CODES:
        seg_active = active_in_segment(seg)
        target = int(anchor_metric(anchors, fy, fq, seg, "headcount_total"))
        delta = target - len(seg_active)
        if delta > 0:
            # Hire
            for _ in range(delta):
                hire_dt = random_day_in_quarter(fy, fq)
                w = make_new_worker(seg, hire_dt)
                employees[w["worker_id"]] = w
                open_version(w, hire_dt)
        elif delta < 0:
            # Excess attrition to shrink to target
            excess_idx = rng.choice(len(seg_active), size=-delta, replace=False)
            for idx in excess_idx:
                w = seg_active[idx]
                term_dt = random_day_in_quarter(fy, fq)
                close_current_version(w["worker_id"], term_dt)
                w["worker_status"] = "Terminated"
                w["termination_date"] = term_dt
                open_version(w, term_dt)

    if q_idx % 4 == 0:
        active_total = sum(1 for e in employees.values() if e["worker_status"] == "Active")
        print(f"  after {fy}Q{fq}: {active_total:,} active workers, {len(scd2_rows):,} SCD2 rows")

print(f"\nGeneration complete. Total SCD2 rows: {len(scd2_rows):,}")

# COMMAND ----------
# MAGIC %md ## Write CSV

# COMMAND ----------
# Explicit schema — termination_date is None for all active workers (the
# whole bootstrap population), so Polars' default inference would tag it as
# Null and choke when a real date appears later. The dict order here also
# fixes column order in the CSV.
schema = {
    "worker_id":                 pl.Utf8,
    "version_seq":               pl.Int64,
    "effective_date":            pl.Date,
    "effective_through":         pl.Date,
    "is_current_row":            pl.Boolean,
    "worker_name_first":         pl.Utf8,
    "worker_name_last":          pl.Utf8,
    "work_email":                pl.Utf8,
    "hire_date":                 pl.Date,
    "termination_date":          pl.Date,
    "worker_status":             pl.Utf8,
    "organization_id":           pl.Utf8,
    "cost_center_id":            pl.Utf8,
    "country_code":              pl.Utf8,
    "region":                    pl.Utf8,
    "job_family":                pl.Utf8,
    "compensation_grade":        pl.Utf8,
    "annual_base_salary_amount": pl.Float64,
    "currency_code":             pl.Utf8,
}

df = pl.DataFrame(scd2_rows, schema=schema)
write_csv(df, f"{OUT}/workers.csv")
print(f"Wrote {len(df):,} SCD2 rows → {OUT}/workers.csv")

# COMMAND ----------
# MAGIC %md ## Sanity — quarter-end active-headcount vs anchor

# COMMAND ----------
# Quick verification that active counts at each quarter-end track the anchor.
print(f"{'fy':<6}{'fq':<5}{'segment':<8}{'target':>10}{'actual':>10}{'delta_pct':>12}")
for fy, fq in periods:
    qe = quarter_end(fy, fq)
    for seg in SEGMENT_CODES:
        target = int(anchor_metric(anchors, fy, fq, seg, "headcount_total"))
        actual = sum(
            1 for r in scd2_rows
            if r["organization_id"] == seg
            and r["worker_status"] == "Active"
            and r["effective_date"] <= qe < r["effective_through"]
        )
        drift = (actual - target) / max(target, 1) * 100
        print(f"{fy:<6}{fq:<5}{seg:<8}{target:>10,}{actual:>10,}{drift:>11.1f}%")
