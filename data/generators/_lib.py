# Databricks notebook source
# MAGIC %md
# MAGIC # _lib — shared helpers for Helios data generators
# MAGIC
# MAGIC Source via `%run ./_lib` from each generator notebook. Defines the
# MAGIC deterministic seed scheme, Helios constants, the 30-category spend
# MAGIC taxonomy used by the ML-classification training data, and anchor /
# MAGIC macro / volume / widget helpers.

# COMMAND ----------
import hashlib
import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl
from mimesis import Generic
from mimesis.locales import Locale

# COMMAND ----------
# MAGIC %md ## Deterministic sub-seeds
# MAGIC
# MAGIC Every generator derives its rng / Mimesis seed from a stable string
# MAGIC label so that re-running any single notebook produces identical output.

# COMMAND ----------
MASTER_SEED = 42


def derive_seed(label: str) -> int:
    h = hashlib.md5(f"{MASTER_SEED}::{label}".encode()).digest()
    return int.from_bytes(h[:4], "little")


def rng_for(label: str) -> np.random.Generator:
    return np.random.default_rng(derive_seed(label))


def mimesis_for(label: str) -> Generic:
    return Generic(locale=Locale.EN, seed=derive_seed(label))


# COMMAND ----------
# MAGIC %md ## Helios constants

# COMMAND ----------
HELIOS_SEGMENTS = [
    {"code": "HAD", "name": "Helios Aerospace & Defense", "company_code": "1100", "mix": 0.371},
    {"code": "HPA", "name": "Helios Process Automation", "company_code": "1200", "mix": 0.255},
    {"code": "HSB", "name": "Helios Smart Buildings", "company_code": "1300", "mix": 0.164},
    {"code": "HET", "name": "Helios Energy Transition", "company_code": "1400", "mix": 0.210},
]
SEGMENT_CODES = [s["code"] for s in HELIOS_SEGMENTS]
HELIOS_CORP_COMPANY_CODE = "1900"

GEOGRAPHIES = [
    {"code": "NA", "name": "North America", "mix": 0.60},
    {"code": "EMEA", "name": "EMEA", "mix": 0.22},
    {"code": "APAC", "name": "APAC", "mix": 0.13},
    {"code": "LATAM", "name": "LATAM", "mix": 0.05},
]

QUARTER_MONTHS = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}


def quarter_end(year: int, quarter: int) -> date:
    return {1: date(year, 3, 31), 2: date(year, 6, 30),
            3: date(year, 9, 30), 4: date(year, 12, 31)}[quarter]


def quarter_start(year: int, quarter: int) -> date:
    return {1: date(year, 1, 1), 2: date(year, 4, 1),
            3: date(year, 7, 1), 4: date(year, 10, 1)}[quarter]


# COMMAND ----------
# MAGIC %md ## Spend taxonomy — 30 categories with ML-training payload
# MAGIC
# MAGIC `segment` is the segment that primarily buys this category. `matgroup` is
# MAGIC the SAP material-group code that bronze ingestion will see (noisy — see
# MAGIC `MATGROUP_NOISE_RATE` for the mislabel rate). `price_mu/sigma` and
# MAGIC `qty_mu/sigma` parameterize log-normal distributions per category so the
# MAGIC amount feature has category signal. `nouns`/`adjs`/`extras` feed the
# MAGIC `TXZ01` description templates that an ML classifier learns from.

# COMMAND ----------
SPEND_CATEGORIES: List[Dict] = [
    {"code": "Aerospace_Components", "segment": "HAD", "matgroup": "1001",
     "price_mu": 5.5, "price_sigma": 1.2, "qty_mu": 0.7, "qty_sigma": 0.9, "uom": "EA",
     "nouns": ["bracket", "fastener", "fitting", "actuator", "panel", "harness", "fairing", "spar", "rib", "longeron"],
     "adjs": ["titanium", "composite", "FAA-certified", "milspec", "high-strength", "machined", "anodized"],
     "extras": ["P/N HAD-{:06d}", "fits 737NG", "fits A320 family", "fits Citation X", "AS9100 compliant"]},
    {"code": "Hydraulic_Systems", "segment": "HAD", "matgroup": "1002",
     "price_mu": 6.5, "price_sigma": 1.0, "qty_mu": 0.5, "qty_sigma": 0.6, "uom": "EA",
     "nouns": ["pump", "actuator", "manifold", "reservoir", "line", "valve", "cylinder", "filter"],
     "adjs": ["3000psi", "5000psi", "high-pressure", "stainless", "MIL-spec", "redundant"],
     "extras": ["model HA-{:05d}", "for landing gear", "for flight controls", "TSO-approved"]},
    {"code": "Composite_Materials", "segment": "HAD", "matgroup": "1003",
     "price_mu": 6.0, "price_sigma": 1.5, "qty_mu": 2.0, "qty_sigma": 1.0, "uom": "KG",
     "nouns": ["prepreg", "carbon-fiber laminate", "honeycomb core", "resin", "tape", "fabric"],
     "adjs": ["unidirectional", "twill weave", "epoxy", "BMI", "aerospace-grade"],
     "extras": ["roll {:04d}m", "lot {:06d}", "spec NCAMP", "RTM-suitable"]},
    {"code": "MRO_Services_Aero", "segment": "HAD", "matgroup": "1004",
     "price_mu": 8.5, "price_sigma": 0.9, "qty_mu": 0.0, "qty_sigma": 0.4, "uom": "HR",
     "nouns": ["inspection", "overhaul", "repair", "calibration", "certification", "field service"],
     "adjs": ["C-check", "A-check", "engine teardown", "NDT", "borescope"],
     "extras": ["aircraft N{:05d}", "engine S/N {:06d}", "FAA Part 145"]},
    {"code": "Industrial_Sensors", "segment": "HPA", "matgroup": "2001",
     "price_mu": 4.5, "price_sigma": 1.1, "qty_mu": 1.5, "qty_sigma": 0.8, "uom": "EA",
     "nouns": ["pressure transmitter", "flow meter", "temperature sensor", "level switch", "vibration probe"],
     "adjs": ["4-20mA", "HART-enabled", "explosion-proof", "Ex-d", "IP67", "intrinsically safe"],
     "extras": ["model PT-{:05d}", "for refinery duty", "SIL-2 certified"]},
    {"code": "Control_Systems", "segment": "HPA", "matgroup": "2002",
     "price_mu": 7.0, "price_sigma": 1.2, "qty_mu": 0.3, "qty_sigma": 0.5, "uom": "EA",
     "nouns": ["PLC", "DCS controller", "HMI panel", "I/O module", "drive", "VFD"],
     "adjs": ["redundant", "rack-mount", "DIN rail", "industrial", "16-channel", "32-channel"],
     "extras": ["Profinet", "EtherNet/IP", "Modbus", "model DCS-{:05d}"]},
    {"code": "Process_Software", "segment": "HPA", "matgroup": "2003",
     "price_mu": 8.0, "price_sigma": 1.0, "qty_mu": 0.0, "qty_sigma": 0.3, "uom": "LIC",
     "nouns": ["historian license", "OPC server license", "MES module", "asset management module", "analytics seat"],
     "adjs": ["annual", "perpetual", "site license", "enterprise", "developer"],
     "extras": ["{:04d} tags", "{:03d} users", "renewal", "new deployment"]},
    {"code": "Calibration_Services", "segment": "HPA", "matgroup": "2004",
     "price_mu": 6.5, "price_sigma": 0.8, "qty_mu": 0.5, "qty_sigma": 0.5, "uom": "HR",
     "nouns": ["calibration", "loop check", "verification", "traceable calibration", "field calibration"],
     "adjs": ["NIST-traceable", "ISO 17025", "annual", "on-site"],
     "extras": ["{:03d} loops", "{:03d} instruments", "cert #{:06d}"]},
    {"code": "HVAC_Equipment", "segment": "HSB", "matgroup": "3001",
     "price_mu": 7.5, "price_sigma": 1.1, "qty_mu": 0.5, "qty_sigma": 0.5, "uom": "EA",
     "nouns": ["chiller", "rooftop unit", "AHU", "VAV box", "heat pump", "boiler"],
     "adjs": ["high-efficiency", "VRF", "magnetic-bearing", "modular", "split-system"],
     "extras": ["{:03d} ton", "{:04d} CFM", "model {:05d}"]},
    {"code": "Building_Controls", "segment": "HSB", "matgroup": "3002",
     "price_mu": 5.0, "price_sigma": 1.0, "qty_mu": 1.2, "qty_sigma": 0.7, "uom": "EA",
     "nouns": ["thermostat", "DDC controller", "actuator", "damper", "zone valve", "occupancy sensor"],
     "adjs": ["BACnet", "wireless", "LonWorks", "smart", "PoE"],
     "extras": ["model T-{:04d}", "for new construction", "retrofit"]},
    {"code": "Security_Systems", "segment": "HSB", "matgroup": "3003",
     "price_mu": 5.5, "price_sigma": 1.0, "qty_mu": 1.0, "qty_sigma": 0.7, "uom": "EA",
     "nouns": ["access reader", "IP camera", "controller", "door strike", "motion sensor", "intercom"],
     "adjs": ["HID-compatible", "PoE+", "4K", "weatherproof", "vandal-resistant"],
     "extras": ["model CAM-{:04d}", "for parking", "for lobby"]},
    {"code": "Fire_Suppression", "segment": "HSB", "matgroup": "3004",
     "price_mu": 5.5, "price_sigma": 0.9, "qty_mu": 1.5, "qty_sigma": 0.8, "uom": "EA",
     "nouns": ["sprinkler head", "fire panel", "smoke detector", "horn-strobe", "pull station", "FM-200 cylinder"],
     "adjs": ["UL-listed", "FM-approved", "addressable", "intelligent"],
     "extras": ["NFPA 13 compliant", "for data hall", "for cleanroom"]},
    {"code": "Solar_Components", "segment": "HET", "matgroup": "4001",
     "price_mu": 6.0, "price_sigma": 1.3, "qty_mu": 1.8, "qty_sigma": 0.9, "uom": "EA",
     "nouns": ["PV module", "inverter", "combiner box", "tracker motor", "junction box"],
     "adjs": ["monocrystalline", "bifacial", "string-inverter", "1500V", "utility-scale"],
     "extras": ["{:03d}W", "model SM-{:05d}", "tier-1"]},
    {"code": "Battery_Materials", "segment": "HET", "matgroup": "4002",
     "price_mu": 7.0, "price_sigma": 1.4, "qty_mu": 3.0, "qty_sigma": 1.0, "uom": "KG",
     "nouns": ["cathode powder", "anode powder", "separator", "electrolyte", "lithium carbonate"],
     "adjs": ["NMC811", "LFP", "battery-grade", "high-purity", "99.95%"],
     "extras": ["lot {:06d}", "spec sheet attached", "qualification batch"]},
    {"code": "Power_Electronics", "segment": "HET", "matgroup": "4003",
     "price_mu": 6.5, "price_sigma": 1.1, "qty_mu": 0.8, "qty_sigma": 0.6, "uom": "EA",
     "nouns": ["IGBT module", "SiC MOSFET", "inverter stack", "DC link capacitor", "gate driver"],
     "adjs": ["1200V", "1700V", "SiC", "high-current", "automotive-grade"],
     "extras": ["P/N HET-{:06d}", "AEC-Q101", "for traction inverter"]},
    {"code": "Monitoring_Software", "segment": "HET", "matgroup": "4004",
     "price_mu": 7.5, "price_sigma": 1.0, "qty_mu": 0.0, "qty_sigma": 0.3, "uom": "LIC",
     "nouns": ["SCADA license", "performance monitoring seat", "predictive maintenance module"],
     "adjs": ["annual", "site license", "cloud-hosted"],
     "extras": ["{:03d} assets", "{:03d} sites", "renewal"]},
    {"code": "IT_Services", "segment": "CROSS", "matgroup": "9001",
     "price_mu": 7.0, "price_sigma": 0.9, "qty_mu": 1.0, "qty_sigma": 0.6, "uom": "HR",
     "nouns": ["managed services", "endpoint support", "network engineering", "incident response", "patch management"],
     "adjs": ["24x7", "Tier-2", "remote", "on-site"],
     "extras": ["SOW {:05d}", "ticket batch", "SLA included"]},
    {"code": "Cloud_Infrastructure", "segment": "CROSS", "matgroup": "9002",
     "price_mu": 7.5, "price_sigma": 1.2, "qty_mu": 1.0, "qty_sigma": 0.4, "uom": "MO",
     "nouns": ["compute capacity", "storage", "data transfer", "managed database", "serverless functions"],
     "adjs": ["reserved", "on-demand", "multi-region", "EU-resident"],
     "extras": ["account {:08d}", "Q{:01d} reservation", "PoC credits"]},
    {"code": "Professional_Services_Legal", "segment": "CROSS", "matgroup": "9003",
     "price_mu": 7.8, "price_sigma": 0.7, "qty_mu": 1.2, "qty_sigma": 0.5, "uom": "HR",
     "nouns": ["outside counsel", "litigation support", "IP filing", "M&A advisory", "compliance review"],
     "adjs": ["partner-level", "associate", "specialist"],
     "extras": ["matter {:06d}", "monthly retainer", "engagement letter signed"]},
    {"code": "Professional_Services_Audit", "segment": "CROSS", "matgroup": "9004",
     "price_mu": 8.0, "price_sigma": 0.6, "qty_mu": 0.5, "qty_sigma": 0.4, "uom": "HR",
     "nouns": ["external audit", "internal audit support", "SOX testing", "tax advisory"],
     "adjs": ["quarterly", "annual", "interim"],
     "extras": ["engagement {:05d}", "FY{:04d} cycle", "audit committee deliverable"]},
    {"code": "Professional_Services_Consulting", "segment": "CROSS", "matgroup": "9005",
     "price_mu": 8.2, "price_sigma": 0.8, "qty_mu": 0.7, "qty_sigma": 0.5, "uom": "HR",
     "nouns": ["strategy advisory", "process improvement", "transformation program", "PMO support"],
     "adjs": ["executive", "operating-model", "go-to-market"],
     "extras": ["phase {:01d}", "SOW {:05d}", "T&M engagement"]},
    {"code": "Office_Supplies", "segment": "CROSS", "matgroup": "9006",
     "price_mu": 2.5, "price_sigma": 0.8, "qty_mu": 2.5, "qty_sigma": 1.0, "uom": "EA",
     "nouns": ["copy paper", "toner cartridge", "notebooks", "pens", "folders", "labels"],
     "adjs": ["letter-size", "A4", "color", "monochrome", "recycled"],
     "extras": ["case of 10", "carton of 5", "pack of 12"]},
    {"code": "Facilities", "segment": "CROSS", "matgroup": "9007",
     "price_mu": 6.0, "price_sigma": 1.0, "qty_mu": 0.5, "qty_sigma": 0.4, "uom": "MO",
     "nouns": ["janitorial services", "landscaping", "pest control", "elevator maintenance", "HVAC PM"],
     "adjs": ["monthly", "quarterly", "annual contract"],
     "extras": ["site {:03d}", "building {:03d}", "scope expansion"]},
    {"code": "Travel", "segment": "CROSS", "matgroup": "9008",
     "price_mu": 6.5, "price_sigma": 0.9, "qty_mu": 0.0, "qty_sigma": 0.5, "uom": "EA",
     "nouns": ["air travel", "lodging", "car rental", "ground transportation", "conference fee"],
     "adjs": ["business-class", "economy", "premium", "domestic", "international"],
     "extras": ["traveler {:06d}", "trip {:07d}", "expense report"]},
    {"code": "Marketing", "segment": "CROSS", "matgroup": "9009",
     "price_mu": 7.0, "price_sigma": 1.0, "qty_mu": 0.5, "qty_sigma": 0.6, "uom": "EA",
     "nouns": ["digital campaign", "trade show", "branded swag", "video production", "agency retainer"],
     "adjs": ["Q{:01d} campaign", "industry-specific", "global"],
     "extras": ["program {:05d}", "vendor SOW", "media buy"]},
    {"code": "Telecommunications", "segment": "CROSS", "matgroup": "9010",
     "price_mu": 6.0, "price_sigma": 0.8, "qty_mu": 0.5, "qty_sigma": 0.4, "uom": "MO",
     "nouns": ["MPLS circuit", "SD-WAN service", "mobile fleet", "long-distance", "international roaming"],
     "adjs": ["{:03d}Mbps", "{:01d}Gbps", "global", "regional"],
     "extras": ["site {:03d}", "carrier {:05d}", "contract renewal"]},
    {"code": "Logistics_Freight", "segment": "CROSS", "matgroup": "9011",
     "price_mu": 6.5, "price_sigma": 1.2, "qty_mu": 2.0, "qty_sigma": 1.0, "uom": "KG",
     "nouns": ["air freight", "ocean freight", "trucking", "expedited delivery", "warehousing"],
     "adjs": ["LCL", "FCL", "LTL", "FTL", "temperature-controlled"],
     "extras": ["BOL {:08d}", "HAWB {:08d}", "lane US-EU"]},
    {"code": "Raw_Materials_Metals", "segment": "CROSS", "matgroup": "9012",
     "price_mu": 4.0, "price_sigma": 1.3, "qty_mu": 4.0, "qty_sigma": 1.2, "uom": "KG",
     "nouns": ["aluminum sheet", "stainless plate", "copper wire", "steel bar", "titanium bar"],
     "adjs": ["6061-T6", "316L", "C110", "1018", "Grade 5"],
     "extras": ["heat {:06d}", "mill cert attached", "cut to {:03d}mm"]},
    {"code": "Raw_Materials_Polymers", "segment": "CROSS", "matgroup": "9013",
     "price_mu": 4.5, "price_sigma": 1.2, "qty_mu": 4.5, "qty_sigma": 1.0, "uom": "KG",
     "nouns": ["PEEK pellets", "PA66 resin", "polycarbonate sheet", "ABS resin", "silicone"],
     "adjs": ["aerospace-grade", "FDA-approved", "natural", "black", "30% GF"],
     "extras": ["lot {:06d}", "drum {:03d}", "container shipment"]},
    {"code": "Training", "segment": "CROSS", "matgroup": "9014",
     "price_mu": 6.5, "price_sigma": 0.8, "qty_mu": 0.7, "qty_sigma": 0.5, "uom": "EA",
     "nouns": ["safety training", "leadership course", "compliance refresher", "technical certification"],
     "adjs": ["online", "instructor-led", "OSHA", "annual"],
     "extras": ["seats {:03d}", "cohort Q{:01d}", "vendor catalog"]},
]
assert len(SPEND_CATEGORIES) == 30, f"expected 30 categories, got {len(SPEND_CATEGORIES)}"

SPEND_CAT_BY_CODE = {c["code"]: c for c in SPEND_CATEGORIES}
SPEND_CATEGORY_CODES = [c["code"] for c in SPEND_CATEGORIES]
MATGROUP_NOISE_RATE = 0.08
MAVERICK_SPEND_RATE = 0.06


# COMMAND ----------
# MAGIC %md ## Anchor + macro readers

# COMMAND ----------
def read_anchors(spark, catalog: str, schema_meta: str) -> pl.DataFrame:
    """Read accepted anchors from `<catalog>.<schema_meta>.dim_period_anchors`
    and return a Polars DataFrame. Errors loudly if the table doesn't exist."""
    sdf = spark.table(f"{catalog}.{schema_meta}.dim_period_anchors")
    pdf = sdf.toPandas()
    return pl.from_pandas(pdf)


def read_macro(spark, catalog: str, schema_gold: str) -> pl.DataFrame:
    sdf = spark.table(f"{catalog}.{schema_gold}.dim_macro_environment")
    return pl.from_pandas(sdf.toPandas())


# COMMAND ----------
# MAGIC %md ## Volume + filesystem helpers

# COMMAND ----------
def volume_dir(catalog: str, schema_raw: str, raw_volume: str, *parts: str) -> str:
    return f"/Volumes/{catalog}/{schema_raw}/{raw_volume}/" + "/".join(parts)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(df: pl.DataFrame, path: str) -> None:
    ensure_dir(os.path.dirname(path))
    df.write_csv(path)


def write_parquet(df: pl.DataFrame, path: str) -> None:
    ensure_dir(os.path.dirname(path))
    df.write_parquet(path)


def write_jsonl(df: pl.DataFrame, path: str) -> None:
    ensure_dir(os.path.dirname(path))
    df.write_ndjson(path)


# COMMAND ----------
# MAGIC %md ## Widget reading

# COMMAND ----------
def get_widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # noqa: F821
    except Exception:
        return default


def get_target_quarter() -> Optional[Tuple[int, int]]:
    """Returns (fiscal_year, fiscal_quarter) if both target widgets are set,
    else None — meaning regenerate every period present in dim_period_anchors."""
    fy = get_widget("target_fiscal_year", "")
    fq = get_widget("target_fiscal_quarter", "")
    if fy and fq:
        return int(fy), int(fq)
    return None


def quarters_to_generate(anchors: pl.DataFrame, target: Optional[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Return the sorted list of (fy, fq) to (re)generate. If `target` is set,
    just that one quarter. Else every Q-grain row in the anchors table."""
    if target is not None:
        return [target]
    q = (anchors.filter(pl.col("period_type") == "Q")
                .select(["fiscal_year", "fiscal_quarter"]).unique()
                .sort(["fiscal_year", "fiscal_quarter"]))
    return [(int(r["fiscal_year"]), int(r["fiscal_quarter"])) for r in q.iter_rows(named=True)]


# COMMAND ----------
# MAGIC %md ## Anchor allocation helpers
# MAGIC
# MAGIC Convert quarterly anchor totals into monthly targets that downstream
# MAGIC generators must hit. Allocation weights use the macro environment so
# MAGIC within-quarter shape is realistic, but normalize to make the quarter
# MAGIC sum exactly equal the anchor.

# COMMAND ----------
def anchor_metric(anchors: pl.DataFrame, fy: int, fq: int, segment: str, metric: str) -> float:
    row = anchors.filter(
        (pl.col("period_type") == "Q")
        & (pl.col("fiscal_year") == fy)
        & (pl.col("fiscal_quarter") == fq)
        & (pl.col("segment_code") == segment)
    )
    if row.is_empty():
        return 0.0
    return float(row[metric][0])


def allocate_to_months(quarterly_total: float, weights: np.ndarray) -> np.ndarray:
    """Distribute a quarterly $ total across the 3 months of the quarter with
    the supplied weights (length 3). Normalizes so the sum equals the total."""
    w = weights.astype(np.float64)
    if w.sum() <= 0:
        w = np.ones_like(w)
    return quarterly_total * (w / w.sum())


def renormalize_amounts(rng: np.random.Generator, n: int, target_total: float,
                        mu: float, sigma: float) -> np.ndarray:
    """Generate n log-normal amounts and renormalize so they sum to target_total."""
    raw = rng.lognormal(mean=mu, sigma=sigma, size=n)
    if raw.sum() == 0:
        raw = np.ones(n)
    return raw * (target_total / raw.sum())


# COMMAND ----------
# MAGIC %md ## Mimesis text pooling
# MAGIC
# MAGIC Generating 1M unique Mimesis values is slow; we pool ~1K unique values
# MAGIC per attribute and let NumPy resample at array speed.

# COMMAND ----------
def pool_names(g: Generic, pool_size: int = 1000) -> np.ndarray:
    return np.array([g.finance.company() for _ in range(pool_size)])


def pool_addresses(g: Generic, pool_size: int = 500) -> List[Dict]:
    return [
        {"street": g.address.street_name(), "city": g.address.city(), "postal_code": g.address.postal_code()}
        for _ in range(pool_size)
    ]


# COMMAND ----------
# MAGIC %md ## Geography
# MAGIC
# MAGIC Country code → Helios geography bucket. The reference filings' literal
# MAGIC "US / Europe / Other International" phrasing is intentionally avoided.

# COMMAND ----------
COUNTRY_TO_GEO = {
    "US": "NA", "CA": "NA", "MX": "NA",
    "DE": "EMEA", "FR": "EMEA", "GB": "EMEA", "IT": "EMEA", "ES": "EMEA",
    "NL": "EMEA", "BE": "EMEA", "PL": "EMEA", "CZ": "EMEA",
    "CN": "APAC", "JP": "APAC", "IN": "APAC", "KR": "APAC", "AU": "APAC", "SG": "APAC", "TH": "APAC",
    "BR": "LATAM", "AR": "LATAM", "CL": "LATAM", "CO": "LATAM",
}
COUNTRY_WEIGHTS = {
    "US": 0.45, "DE": 0.10, "GB": 0.07, "CN": 0.06, "MX": 0.05, "IN": 0.04,
    "FR": 0.03, "JP": 0.03, "CA": 0.03, "IT": 0.025, "ES": 0.02,
    "BR": 0.02, "NL": 0.015, "AU": 0.015, "KR": 0.015, "SG": 0.01, "PL": 0.01,
    "CZ": 0.005, "TH": 0.005, "BE": 0.005, "AR": 0.005, "CL": 0.003, "CO": 0.002,
}

LANG_BY_COUNTRY = {
    "US": "EN", "GB": "EN", "CA": "EN", "AU": "EN", "SG": "EN",
    "DE": "DE", "FR": "FR", "IT": "IT", "ES": "ES", "MX": "ES", "AR": "ES", "CL": "ES", "CO": "ES",
    "BR": "PT", "PL": "PL", "CZ": "CS", "NL": "NL", "BE": "NL",
    "CN": "ZH", "JP": "JA", "IN": "EN", "KR": "KO", "TH": "TH",
}


# COMMAND ----------
# MAGIC %md ## GL chart-of-accounts skeleton
# MAGIC
# MAGIC Defined here so both Ariba (PO->GL hints) and Fusion (full COA) share it.

# COMMAND ----------
NATURAL_ACCOUNTS = {
    # COGS-bearing accounts
    "5000": ("COGS - Direct Materials", "COGS"),
    "5010": ("COGS - Direct Labor", "COGS"),
    "5020": ("COGS - Manufacturing Overhead", "COGS"),
    "5030": ("COGS - Subcontract Services", "COGS"),
    # SG&A
    "6000": ("Salaries - Sales", "SGA"),
    "6010": ("Salaries - G&A", "SGA"),
    "6020": ("Travel", "SGA"),
    "6030": ("Marketing", "SGA"),
    "6040": ("IT - SaaS", "SGA"),
    "6050": ("IT - Infrastructure", "SGA"),
    "6060": ("Legal Fees", "SGA"),
    "6070": ("Audit Fees", "SGA"),
    "6080": ("Consulting", "SGA"),
    "6090": ("Facilities", "SGA"),
    "6100": ("Office Supplies", "SGA"),
    "6110": ("Telecommunications", "SGA"),
    "6120": ("Logistics & Freight", "SGA"),
    "6130": ("Training", "SGA"),
    # R&D
    "7000": ("R&D - Salaries", "RD"),
    "7010": ("R&D - Materials", "RD"),
    "7020": ("R&D - Outside Services", "RD"),
    # Revenue
    "4000": ("Product Revenue", "REVENUE"),
    "4010": ("Service Revenue", "REVENUE"),
    "4020": ("License Revenue", "REVENUE"),
    # Below the line
    "8000": ("Interest Expense", "INTEREST"),
    "8500": ("Income Tax Provision", "TAX"),
    # Balance sheet
    "1000": ("Cash", "BS"),
    "1100": ("Accounts Receivable", "BS"),
    "1200": ("Inventory", "BS"),
    "2000": ("Accounts Payable", "BS"),
    "2500": ("Long-term Debt", "BS"),
    "3000": ("Common Equity", "BS"),
}

# Categories -> primary GL account (used by Ariba->Fusion linkage)
CATEGORY_TO_GL_ACCOUNT = {
    "Aerospace_Components": "5000", "Hydraulic_Systems": "5000", "Composite_Materials": "5000",
    "MRO_Services_Aero": "5030", "Industrial_Sensors": "5000", "Control_Systems": "5000",
    "Process_Software": "6040", "Calibration_Services": "5030",
    "HVAC_Equipment": "5000", "Building_Controls": "5000", "Security_Systems": "5000", "Fire_Suppression": "5000",
    "Solar_Components": "5000", "Battery_Materials": "5000", "Power_Electronics": "5000", "Monitoring_Software": "6040",
    "IT_Services": "6050", "Cloud_Infrastructure": "6050",
    "Professional_Services_Legal": "6060", "Professional_Services_Audit": "6070", "Professional_Services_Consulting": "6080",
    "Office_Supplies": "6100", "Facilities": "6090", "Travel": "6020", "Marketing": "6030",
    "Telecommunications": "6110", "Logistics_Freight": "6120",
    "Raw_Materials_Metals": "5000", "Raw_Materials_Polymers": "5000",
    "Training": "6130",
}

COST_CENTERS_PER_SEGMENT = 12  # 4 segments × 12 = 48 cost centers + 4 corporate = 52
