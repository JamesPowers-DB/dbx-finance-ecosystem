# `sql/` — hand-written SQL by purpose

This folder holds ad-hoc SQL files grouped by the kind of work they support. The first category is `pipeline_exploration/` — queries for poking around the demo's gold/silver/bronze tables in the SQL editor. Future categories (metric views, Genie space SQL, AI_QUERY/AI_FORECAST examples) will live as sibling folders.

## Layout

```
sql/
├── README.md
└── pipeline_exploration/                ← demo data exploration
    ├── spend_overview.sql               ← procurement: POs, AP, sourcing, suppliers
    ├── revenue_overview.sql             ← sales: AR, billing, customers, contracts
    ├── accounting_overview.sql          ← GL: journals, trial balance, COA
    ├── legal_overview.sql               ← contracts (inbound + outbound), amendments, leakage
    ├── parties_overview.sql             ← supplier / customer master data
    ├── fpa_overview.sql                 ← actuals vs budget vs forecast, variance, growth
    ├── hr_overview.sql                  ← headcount cost (derived from anchors)
    └── reference_data_overview.sql      ← calendar, segments, macro environment
```

## How to use

Each `*_overview.sql` is a collection of independent queries separated by section comments. Open in the Databricks SQL editor, scroll to the section you want, and run that block (Cmd+Enter on Mac).

Every file starts with:

```sql
USE CATALOG horizontal_finance_dev;
```

Change this line to point at whichever catalog the bundle deployed to (e.g. `horizontal_finance` for prod).

## What each file covers

| File | Useful for |
|---|---|
| `pipeline_exploration/spend_overview.sql` | Spend mix — totals by segment × quarter, top suppliers, category distribution, AP match rate, sourcing-event throughput, **maverick spend** (the hard cases the ML model targets). |
| `pipeline_exploration/revenue_overview.sql` | Revenue by segment × quarter, top customers, billing status, currency / FX mix, contract value distribution. |
| `pipeline_exploration/accounting_overview.sql` | Per-JE balance check, trial balance for the most recent period, COA usage by segment, top-N active accounts. |
| `pipeline_exploration/legal_overview.sql` | Active inbound + outbound contracts, contract utilization (committed vs actual), amendment frequency, expiration calendar, **off-contract spend** (Phase 2 leakage hint). |
| `pipeline_exploration/parties_overview.sql` | Supplier counts by region × category, **maverick-propensity distribution** (the slice the ML model is evaluated against), top suppliers / customers, Ariba scorecards. |
| `pipeline_exploration/fpa_overview.sql` | Side-by-side actual vs budget vs forecast for the latest quarter, YoY revenue growth, operating-margin trend per segment. |
| `pipeline_exploration/hr_overview.sql` | Quarterly headcount cost by segment, QoQ change. (Cost is derived from anchor headcount × loaded-cost assumption — real HR feed is later.) |
| `pipeline_exploration/reference_data_overview.sql` | Calendar dim sanity, the four Helios segments, the macroeconomic arc (GDP / inflation / demand / supply stress) used to shape within-quarter transaction distributions. |

## Conventions

- Amounts displayed in millions (`/ 1e6`) for readability — the underlying values are full USD.
- Quarter-level rollups use `(fiscal_year * 10 + fiscal_quarter)` to keep ordering stable.
- Multiple sections per file — they don't share state, so you can run any one in isolation.

## Future categories (sibling folders to `pipeline_exploration/`)

As the demo grows, other purposes get their own folder under `sql/`:

| Folder | Purpose |
|---|---|
| `metrics/` | UC metric views — managed-spend %, tail-spend, category coverage, PO compliance, cash obligations, revenue growth, headcount productivity, FP&A planning. Phase 1 work, deferred behind the ML model. |
| `genie/` | SQL + synonyms for a Genie space on top of the gold layer. |
| `ai_functions/` | `AI_FORECAST` / `AI_QUERY` examples (ported from the old `fin_demo` repo's `03.Queries/`). |
| `validations/` | Hand-written tie-out queries — gold-vs-anchor checks, segment cross-foot, period-close diagnostics. |
