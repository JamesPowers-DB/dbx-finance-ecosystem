# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: `gold.dim_macro_environment`
# MAGIC
# MAGIC Monthly macro factors (2023-01 → current month). Used by the source-file
# MAGIC generators to *shape* the within-quarter distribution of transactions —
# MAGIC quarter totals themselves are pinned by `_meta.dim_period_anchors`, not
# MAGIC by this table.
# MAGIC
# MAGIC Hand-engineered narrative arc + AR(1) noise so the demo has predictable
# MAGIC story beats without looking synthetic-flat.

# COMMAND ----------
# MAGIC %run ./_lib

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_gold", "gold")

catalog = get_widget("catalog", "finance_demo")
schema_gold = get_widget("schema_gold", "gold")
print(f"Writing to {catalog}.{schema_gold}.dim_macro_environment")

# COMMAND ----------
# MAGIC %md ## Build the monthly time axis

# COMMAND ----------
start = date(2023, 1, 1)
today = date.today()
months: List[date] = []
y, m = start.year, start.month
while date(y, m, 1) <= today:
    months.append(date(y, m, 1))
    m += 1
    if m == 13:
        m, y = 1, y + 1
n = len(months)
print(f"{n} months from {months[0]} to {months[-1]}")

# COMMAND ----------
# MAGIC %md ## Hand-engineered GDP arc
# MAGIC
# MAGIC Anchor values at key months interpolated linearly; AR(1) noise layered on
# MAGIC top for texture. Beats:
# MAGIC - 2023H1 steady 2.0
# MAGIC - 2024H1 softening to 1.2
# MAGIC - 2024H2 trough at 0.6
# MAGIC - 2025H1 recovery to 1.5
# MAGIC - 2025H2 rebound to 2.5
# MAGIC - 2026 moderation back to 2.0

# COMMAND ----------
ANCHOR_GDP = {
    date(2023, 1, 1): 2.0, date(2023, 7, 1): 2.0,
    date(2024, 1, 1): 1.5, date(2024, 4, 1): 1.2,
    date(2024, 7, 1): 0.8, date(2024, 10, 1): 0.6,
    date(2025, 1, 1): 0.9, date(2025, 4, 1): 1.5,
    date(2025, 7, 1): 2.0, date(2025, 10, 1): 2.5,
    date(2026, 1, 1): 2.4, date(2026, 7, 1): 2.0,
    date(2027, 1, 1): 2.0,
}


def interp_anchors(months: List[date], anchors: Dict[date, float]) -> np.ndarray:
    keys = sorted(anchors.keys())
    out = np.zeros(len(months))
    for i, m in enumerate(months):
        prev = max([k for k in keys if k <= m], default=keys[0])
        nxt = min([k for k in keys if k >= m], default=keys[-1])
        if prev == nxt:
            out[i] = anchors[prev]
        else:
            span = (nxt - prev).days
            offset = (m - prev).days
            out[i] = anchors[prev] + (anchors[nxt] - anchors[prev]) * offset / span
    return out


gdp_base = interp_anchors(months, ANCHOR_GDP)

rng = rng_for("macro:gdp_noise")
phi = 0.6
noise = np.zeros(n)
for t in range(1, n):
    noise[t] = phi * noise[t - 1] + rng.normal(0, 0.15)
gdp_growth_idx = gdp_base + noise

# COMMAND ----------
# MAGIC %md ## Derived series

# COMMAND ----------
infl_rate_annual = 0.045 + 0.025 * np.clip(2.5 - gdp_base, 0, None) / 2.5
infl_rate_annual = np.clip(infl_rate_annual, 0.03, 0.08)
infl_monthly = (1 + infl_rate_annual) ** (1 / 12) - 1
inflation_idx = np.cumprod(1 + infl_monthly)


def beta_series(label: str, beta: float, base: np.ndarray, sigma: float = 0.08) -> np.ndarray:
    r = rng_for(label)
    eps = np.zeros(n)
    for t in range(1, n):
        eps[t] = 0.5 * eps[t - 1] + r.normal(0, sigma)
    return 1.0 + beta * (base - base.mean()) / max(base.std(), 0.1) * 0.15 + eps


demand_idx_sales = beta_series("macro:demand_sales", 1.3, gdp_base)
demand_idx_mfg = beta_series("macro:demand_mfg", 1.1, gdp_base)
demand_idx_back_office = beta_series("macro:demand_back_office", 0.6, gdp_base)

supply_chain_stress_idx = 1.0 + 0.4 * (gdp_base - gdp_base.mean()) / max(gdp_base.std(), 0.1)
supply_chain_stress_idx = supply_chain_stress_idx + rng_for("macro:supply_stress").normal(0, 0.1, n)
for i, m in enumerate(months):
    if m.year == 2024 and m.month in (10, 11, 12):
        supply_chain_stress_idx[i] += 0.3

labor_market_tightness = np.zeros(n)
for i in range(n):
    j = max(0, i - 2)
    labor_market_tightness[i] = 1.0 + 0.5 * (gdp_base[j] - gdp_base.mean()) / max(gdp_base.std(), 0.1)
labor_market_tightness += rng_for("macro:labor").normal(0, 0.06, n)

season_map = {1: 0.92, 2: 0.95, 3: 1.02,
              4: 1.00, 5: 1.03, 6: 1.05,
              7: 0.97, 8: 0.95, 9: 1.04,
              10: 1.08, 11: 1.10, 12: 1.06}
seasonality_idx = np.array([season_map[m.month] for m in months])

# COMMAND ----------
df = pl.DataFrame({
    "period_month": months,
    "gdp_growth_idx": np.round(gdp_growth_idx, 4),
    "inflation_idx": np.round(inflation_idx, 4),
    "demand_idx_sales": np.round(demand_idx_sales, 4),
    "demand_idx_mfg": np.round(demand_idx_mfg, 4),
    "demand_idx_back_office": np.round(demand_idx_back_office, 4),
    "supply_chain_stress_idx": np.round(supply_chain_stress_idx, 4),
    "labor_market_tightness": np.round(labor_market_tightness, 4),
    "seasonality_idx": np.round(seasonality_idx, 4),
})
print(df.head(6))
print(f"... ({len(df)} rows)")

# COMMAND ----------
# MAGIC %md ## Write to UC

# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema_gold}`")
sdf = spark.createDataFrame(df.to_pandas())
(sdf.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"`{catalog}`.`{schema_gold}`.dim_macro_environment"))
print(f"Wrote {sdf.count()} rows to {catalog}.{schema_gold}.dim_macro_environment")
