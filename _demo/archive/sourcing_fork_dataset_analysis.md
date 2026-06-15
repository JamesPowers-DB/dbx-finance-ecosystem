> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Dataset Usage & Lineage Analysis — "Strategic Sourcing" Fork

**Date:** 2026-06-02
**Purpose:** Inventory every dataset in the repo and classify it by whether a *consumption surface* (Dashboard, Genie space, App) reads it, or whether it is *upstream* of something a surface reads. Use this to decide what to cut when forking a leaner **Strategic Sourcing**–only repo.

> Analysis only — no files were modified. Schemas use the bundle's logical names: `bronze_ariba` / `bronze_fusion` / `bronze_cms` / `bronze_workday`, `silver`, `gold`, `_meta`, `ml`.

---

## 1. The consumption surfaces (what actually gets read)

| Surface | Reads |
|---|---|
| **Dashboard** (`dashboards/spend_visibility.lvdash.json`) | `gold.mv_spend`, `gold.mv_supplier_performance` |
| **Genie space** (`genie/genie_space_def.py`) | `gold.mv_spend`, `gold.mv_supplier_performance`, `gold.mv_contracts`, `gold.mv_purchase_orders`, `gold.mv_cost_savings` (all 5 metric views) |
| **App** (`apps/spend-analytics/backend`) | `gold.mv_spend`, `gold.mv_supplier_performance`, `gold.mv_purchase_orders`, `gold.fact_invoices`, `gold.fact_purchase_orders`, `gold.dim_supplier`, `gold.fact_cost_savings`, **`gold.fact_fpa_budgets`**, `silver.contract_inbound`, `bronze_ariba.EBAN_PR_LINE` (chatbot **writes** PRs), `ml.spend_clf_eval_runs` (orphaned — see §5) + Lakebase (`chatbot_sessions`, `chatbot_messages`, `savings_avoidance_entries`) |
| **ML pipeline** (`ml/spend_classification`) | reads `gold.fact_invoices`, `gold.dim_supplier`, `gold.dim_spend_category`; writes `ml.spend_clf_*`, `ml.invoice_classifications`, registers `ml.spend_classifier` |

**Key structural fact:** the five **metric views are the bridge**. The dashboard/Genie/most-of-app never touch base tables directly — they go through `mv_*`. So "what's consumed" = the metric views + their sources + the handful of base tables the app/ML hit directly.

Metric-view sources (from `metric_views/apply_metric_views.py`):

| Metric view | Source | Join | Used by |
|---|---|---|---|
| `mv_spend` | `gold.fact_invoices` | — | Dashboard, Genie, App, (nests into mv_supplier_performance) |
| `mv_supplier_performance` | `gold.mv_spend` (nested) | — | Dashboard, Genie, App |
| `mv_purchase_orders` | `gold.fact_purchase_orders` | `gold.fact_purchase_requests` | Genie, App (funnel) |
| `mv_contracts` | `silver.contract_inbound` | `gold.dim_supplier` | **Genie only** |
| `mv_cost_savings` | `gold.fact_cost_savings` | — | **Genie only** |

---

## 2. Classification tiers

- **Tier A — Directly consumed** by a surface.
- **Tier B — Upstream** (transitively required to build a Tier-A dataset).
- **Tier C — Unused**: nothing consumes it and it is not upstream of anything consumed → safe to drop in a sourcing fork.

### Tier A — directly consumed

| Dataset | Consumed by |
|---|---|
| `gold.mv_spend` | Dashboard, Genie, App |
| `gold.mv_supplier_performance` | Dashboard, Genie, App |
| `gold.mv_purchase_orders` | Genie, App |
| `gold.mv_contracts` | Genie only |
| `gold.mv_cost_savings` | Genie only |
| `gold.fact_invoices` | App (suppliers, contracts, chatbot), ML; source of `mv_spend` |
| `gold.fact_purchase_orders` | App (supplier commitments); source of `mv_purchase_orders` |
| `gold.fact_purchase_requests` | join in `mv_purchase_orders` |
| `gold.fact_cost_savings` | App (Cost Savings); source of `mv_cost_savings` |
| `gold.fact_fpa_budgets` | App (Cost Savings summary, chatbot budget tool) ⚠️ pulls in accounting+FP&A |
| `gold.dim_supplier` | App (scorecard attributes, contracts, chatbot); join in `mv_contracts`; in every spend fact |
| `gold.dim_spend_category` | ML (taxonomy in train/eval) |
| `silver.contract_inbound` | App (contracts), source of `mv_contracts` |
| `bronze_ariba.EBAN_PR_LINE` | App chatbot **writes** new PRs here; also upstream of PR fact |
| `ml.invoice_classifications` | read by `silver.invoice_classification` → `fact_invoices` |
| `ml.spend_clf_train / _holdout / _maverick_holdout / _eval_runs`, model `ml.spend_classifier` | ML train/eval/inference loop |

### Tier B — required upstream (to build Tier A)

**`gold.fact_invoices`** ← `silver.invoice_ap` ← `bronze_fusion.ap_invoices_all`, `bronze_fusion.ap_invoice_lines_all`; ← `gold.dim_supplier`; ← `bronze_fusion.gl_code_combinations` (**accounting bronze** — for direct/indirect); ← `silver.invoice_classification` ← `ml.invoice_classifications`.

**`gold.fact_purchase_orders`** ← `silver.purchase_order` ← `bronze_fusion.po_headers_all`, `bronze_fusion.po_lines_all`; ← `gold.dim_supplier`.

**`gold.fact_purchase_requests`** ← `silver.purchase_request` ← `bronze_ariba.EBAN_PR_HEADER`, `bronze_ariba.EBAN_PR_LINE`; ← `gold.dim_supplier`.

**`gold.fact_cost_savings`** ← `silver.sourcing_event` ← `bronze_ariba.ARIBA_SOURCING_EVENT`; ← `gold.dim_supplier`.

**`gold.dim_supplier`** ← `silver.supplier` ← `bronze_ariba.LFA1_SUPPLIER_MASTER`, `bronze_fusion.ap_supplier_sites_all`.

**`silver.contract_inbound`** ← `bronze_ariba.ARIBA_CONTRACT_WORKSPACE`.

**`gold.fact_fpa_budgets`** ⚠️ ← `gold.fact_fpa_actuals` ← `gold.fact_gl_entries` ← `silver.gl_journal_header/line` ← `bronze_fusion.gl_je_headers/lines`; (+ `silver.coa_account` ← `bronze_fusion.gl_code_combinations`). **This is the entire accounting-journal + FP&A chain, pulled in by one app feature.**

ML training upstreams: `ml.spend_clf_train/holdout/...` ← `gold.fact_invoices`, `gold.dim_supplier`, `gold.dim_spend_category`.

### Tier C — unused (drop candidates)

| Dataset | Pillar | Why droppable |
|---|---|---|
| `bronze_cms.billing_schedule`, `bronze_fusion.ar_invoices_all`, `silver.invoice_ar`, `gold.fact_revenue` | **Revenue** | No surface reads revenue; nothing downstream. |
| `bronze_workday.workers`, `gold.dim_employees`, `gold.fact_emp_quarterly_cost` | **HR** | No surface reads HR. |
| `silver.customer`, `gold.dim_customer` | Parties (customer) | No surface reads customer. (Dropping `silver.customer` removes its `bronze_cms` read.) |
| `silver.contract_outbound` + `bronze_cms.contract`, `contract_party`, `contract_line_item`, `contract_amendment`, `performance_obligation` | **Legal (outbound)** | Only feed `fact_revenue` (dropped) and `silver.customer` (dropped). |
| `bronze_fusion.gl_je_headers/lines`, `gl_trial_balance`, `gl_balances`, `gl_periods`, `silver.gl_journal_header/line`, `silver.coa_account`, `gold.dim_account`, `gold.dim_cost_center`, `gold.fact_gl_entries`, `gold.fact_trial_balance` | **Accounting** | Only upstream of FP&A. Droppable **iff** the FP&A budget feature is cut (§3). **Exception:** `bronze_fusion.gl_code_combinations` must stay — `fact_invoices` reads it. |
| `gold.fact_fpa_actuals`, `gold.fact_fpa_budgets`, `gold.fact_fpa_forecasts` | **FP&A** | Droppable iff the two budget features are cut (§3). |
| `gold.dim_date`, `gold.dim_segment`, `gold.dim_macro_environment` | Reference | Not joined by any metric view/surface (facts carry segment/category denormalized; `dim_macro_environment` is generator-side). Static + tiny — cheap to keep, but not required. |
| `bronze_ariba.ARIBA_SUPPLIER_PERFORMANCE` | Spend (bronze) | Produced but **no downstream reader found** — verify, then drop. |

---

## 3. The one decision that unlocks the big cut: FP&A budget

`gold.fact_fpa_budgets` is the *only* thing tying the lean sourcing surfaces to the accounting-journal + FP&A pillars. It is used in exactly two places:

1. **Cost Savings → summary** (`cost_savings.py` `savings_summary`) — budget-vs-paid column.
2. **Chatbot → `get_remaining_budget` tool** (`chatbot.py`) — "size a PR against budget capacity."

**If you drop those two features**, you can delete the *entire* accounting-journal chain (`gl_je_*`, `gl_trial_balance`, `gl_balances`, `gl_periods`, `gl_journal_*`, `coa_account`, `dim_account`, `dim_cost_center`, `fact_gl_entries`, `fact_trial_balance`) **and** all of FP&A (`fact_fpa_actuals/budgets/forecasts`). You keep only `bronze_fusion.gl_code_combinations` (needed by `fact_invoices` for the direct/indirect + addressability flags).

**If you keep them**, the accounting-GL + FP&A chain stays — a large pillar carried by one column and one chatbot tool.

> Recommendation for an "immediate need" sourcing demo: **cut the FP&A budget feature.** It's the single highest-leverage simplification.

Two more optional levers:
- **Cost Savings surface** (`fact_cost_savings` + `mv_cost_savings` + sourcing_event chain + Lakebase avoidance ledger). Previously flagged low-priority. Cutting it drops `silver.sourcing_event` + `bronze_ariba.ARIBA_SOURCING_EVENT`. ⚠️ *Verify first* that the `sourced`/managed-spend logic in `mv_spend` relies on the denormalized `sourcing_event_id` column on invoice lines (it does) and **not** on the `sourcing_event` table — if so, dropping the table is safe for managed-spend math.
- **Genie-only views** (`mv_contracts`, `mv_cost_savings`): if the forked Genie space is descoped, these drop. `mv_contracts`'s source (`contract_inbound`) is still needed by the app; `mv_cost_savings` follows the Cost Savings decision above.

---

## 4. Recommended "Strategic Sourcing" keep-set

A lean fork that preserves the Dashboard + a sourcing Genie space + the App (minus FP&A budget) + the ML classifier:

**Pillars to KEEP (trimmed):**
- **Spend** — full (invoices, POs, PRs; cost_savings optional per §3).
- **Parties** — supplier side only (`bronze_ariba.LFA1_SUPPLIER_MASTER`, `bronze_fusion.ap_supplier_sites_all` → `silver.supplier` → `gold.dim_supplier`). **Drop customer side.**
- **Legal** — inbound only (`bronze_ariba.ARIBA_CONTRACT_WORKSPACE` → `silver.contract_inbound`). **Drop outbound + all `bronze_cms`.**
- **Reference** — `dim_spend_category` (ML needs it); `dim_segment`/`dim_date` optional (cheap, static).
- **Accounting** — `bronze_fusion.gl_code_combinations` **only** (for `fact_invoices`). Drop the rest.
- **ML** — full classification loop.
- **Metric views** — `mv_spend`, `mv_supplier_performance`, `mv_purchase_orders` (+ `mv_contracts`, `mv_cost_savings` if Genie keeps those answers).

**Pillars to DROP entirely:** Revenue, HR, FP&A, and the accounting GL-journal chain.

**Net base-table footprint of the keep-set** (excluding metric views / ML / Lakebase):
`bronze_ariba`: EBAN_PR_HEADER, EBAN_PR_LINE, ARIBA_SOURCING_EVENT*, ARIBA_CONTRACT_WORKSPACE, LFA1_SUPPLIER_MASTER ·
`bronze_fusion`: ap_invoices_all, ap_invoice_lines_all, po_headers_all, po_lines_all, ap_supplier_sites_all, gl_code_combinations ·
`silver`: invoice_ap, invoice_classification, purchase_order, purchase_request, sourcing_event*, supplier, contract_inbound ·
`gold`: fact_invoices, fact_purchase_orders, fact_purchase_requests, fact_cost_savings*, dim_supplier, dim_spend_category (+ dim_segment/dim_date optional)
(* = drops if Cost Savings is also cut.)

That removes roughly **half** the datasets (all of Revenue, HR, FP&A, accounting-journals, customer/outbound-contracts).

---

## 5. Caveats & things to verify before cutting

- **Orphaned but live backend:** the **Labeling** router (`routers/labeling.py`) still reads `gold.fact_invoices` + `ml.spend_clf_eval_runs`, even though the Labeling **tab was removed from the UI**. Endpoints are unreachable from the app now — remove the router too in the fork (or it keeps `spend_clf_eval_runs` "consumed").
- **`fact_invoices` ↔ accounting:** keeping `fact_invoices` *requires* `bronze_fusion.gl_code_combinations`. Don't delete all of accounting blindly — keep that one bronze table (or inline the direct/indirect + addressability derivation and drop it too).
- **ML round-trip:** `fact_invoices` LEFT-JOINs `silver.invoice_classification` ← `ml.invoice_classifications`. Predicted-category columns are NULL until `batch_inference.py` runs. Keep the ML loop if the supplier scorecard's classification visual matters.
- **Generators & bundle, not just pipelines:** this analysis covers pipeline/surface datasets. A real fork must also trim the matching pieces in `data/generators/` (00–05, `99_reconcile.py`), the DAB `resources/*.yml` / `jobs/*.yml`, and `_meta` seeds (`dim_period_anchors` etc.) to the same keep-set. The dependency graph above is the source of truth for what to keep.
- **`ARIBA_SUPPLIER_PERFORMANCE`** (bronze): no downstream reader found in the lineage sweep — confirm before dropping (the old `parties_overview.sql` referenced Ariba scorecards, but that's exploration SQL, not a surface).
- **Sourcing-event vs cost-savings:** confirm `mv_spend`'s `sourced`/managed measures use the denormalized `sourcing_event_id` on invoice/PO lines (carried from bronze) rather than the `silver.sourcing_event` table, so cutting Cost Savings doesn't break managed-spend math.
- **Reference dims:** `dim_segment` / `dim_date` aren't joined by any metric view today (facts are denormalized), so they're technically Tier C — but they're static and tiny; keeping them is low-cost insurance if you later add dim joins.

---

## 6. One-glance pillar verdict

| Pillar | Verdict |
|---|---|
| **Spend** | **Keep** — the core. |
| **Parties** | **Keep supplier**, drop customer. |
| **Legal** | **Keep inbound contracts**, drop outbound + `bronze_cms`. |
| **Reference** | Keep `dim_spend_category`; `dim_segment`/`dim_date` optional; drop `dim_macro_environment`. |
| **Accounting** | Drop all **except** `bronze_fusion.gl_code_combinations`. |
| **FP&A** | **Drop** (cut the budget feature first — §3). |
| **Revenue** | **Drop** entirely. |
| **HR** | **Drop** entirely. |
| **ML** | Keep (classification loop). |
| **Metric views** | Keep `mv_spend`, `mv_supplier_performance`, `mv_purchase_orders`; `mv_contracts`/`mv_cost_savings` per Genie/Cost-Savings scope. |
