# 2026-05-29 — De-brand to "Strategic Spend Analytics" (outcome-centered, Databricks-first)

Demo coordination requires demos to be **outcome-centered, not entity/technology-centered** — anything anchored on a fake company is rejected. This pass removes the "Helios" entity entirely and re-anchors on the **end-to-end spend-visibility** outcome and the spend lifecycle (*source/contract → request → order → invoice → paid*), with **Databricks-first** surfaces (the app is auxiliary).

## What changed
- **Every "Helios" / "HIG" / "Industrial Group" reference removed** from the repo (code, data identifiers, columns, UI, docs). `grep -rin "helios"` → zero.
- **Segment codes** `HAD/HPA/HSB/HET` → **`AD/PA/SB/ET`** (opaque, UPPER_CASE; +`CORP`/`CONSOL`). Segment **names** genericized: Aerospace & Defense, Process Automation, Smart Buildings, Energy Transition, Corporate, Consolidated.
- **Columns** renamed: `_helios_segment_code` → `_segment_code`, `helios_entity_segment` → `entity_segment`. `_lib.HELIOS_SEGMENTS`/`HELIOS_CORP_COMPANY_CODE` → `SEGMENTS`/`CORP_COMPANY_CODE`. Email domain `@helios.example` → `@example.com`. Contract party `"Helios — {seg}"` → `"Internal — {seg}"`. SKU prefixes normalized.
- **App** `apps/helios-sourcing-portal/` → **`apps/spend-analytics/`** (git mv); resource key `spend_analytics`, name `spend-analytics-${target}`. Sidebar/Home/Chatbot/CostSavings/metricDefinitions de-branded; Home hero reframed on the lifecycle outcome; added a **"Powered by Databricks"** panel (Metric Views · Genie · Lakeflow · MLflow · Lakebase · OBO) making the unique positioning explicit.
- **Genie** space description/instructions de-branded; **repo references the space by ID** so no app impact. *Workspace space display name "Helios Spend Analytics" → rename to "Strategic Spend Analytics" via the Genie UI (1-click; not a repo artifact).*
- **Docs** (README, design context, `_demo/*`, `ml/`, `sql/`, generator READMEs) re-led with the Databricks lakehouse + lifecycle outcome.
- **Catalog `horizontal_finance[_dev]` kept** (already neutral). Company codes (SAP bukrs) kept.

## ⚠️ Follow-ups
- **Regen required:** the warehouse still holds the old codes/columns until `generate_data` → full pipeline refresh → `apply_metric_views` are re-run on the de-branded code. (Totals unchanged — identity-only change; reconcile must stay green.)
- **Lakebase project:** code now points at `projects/spend-analytics` (was `projects/helios-sourcing`). **Re-provision the Lakebase project under the new name** (or repoint) before the app's chatbot/savings-ledger features work — app is auxiliary + deploy-gated, so non-blocking.
- **Deferred (deployment phase):** landing-page tagging + a single orchestrating entry-point job.

## Out of scope
- Catalog rename; SAP company-code rename; ML model changes.
