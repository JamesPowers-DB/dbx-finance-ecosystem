> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# MFG Prod Deployment — Requirements & Readiness

> **Status: DRAFT for review. No deployment work has started.** This doc captures
> what the MFG industry-prod program requires of our demo, where we comply today,
> and the gaps/decisions to close before we publish. James + team to review this,
> and the app content, before we go for full deployment.

## Sources
- **Slack** (group DM `C0B5WDZUUET`): https://databricks.enterprise.slack.com/archives/C0B5WDZUUET
- **MFG Rules of the Road — Compliance Report** (example audit, the 9-criterion checklist applied to the O&G fleet): https://docs.google.com/document/d/1mzzxGiV7013WCZGFoxhHuX1vMzvAjHJoU0cd9s0fl0k
- **Operating Guide / Industry Solution Environments** (`go/mfg/demo` rules): https://docs.google.com/document/d/1ESbGDgZN3_dCQNa7oLPnVpb3YTggTASCdSSYuFcJLQ8
- Landing page / outcome hub: `go/mfg/demo` → https://mfg-demo-7474653700457519.aws.databricksapps.com/

## The ask (timeline)
- Our demo is **#1 of the first three to load**: *"Spend Visibility & Strategic Sourcing Intelligence — Functional Teams / Finance"* (Hayley, 2026‑05‑29).
- First three demos load **Monday 2026‑06‑01**; James: **Finance still targeting EOD Wednesday 2026‑06‑03**.
- Approver / workspace owner: **David Rogers** (sole approver for now); secondary **Josh Melton**.

## Target environment (hard constraints)
- **Workspace:** `fevm-mfg-industry-prod` (FEVM Stable, **US‑East‑1 AWS**) — a *different* workspace from our current `e2-demo-field-eng`.
- **⚠️ NO DEV WORK in the prod workspace.** Non‑compliance = access removed + assets torn down, "no exceptions or appeals." We build in our dev workspace (`go/fe-vm`) and only deploy finished, DAB‑packaged assets.
- **Only two top‑level catalogs exist:** `manufacturing` and `energy_utilities`. **All demos create data at the schema level and below** — we do **not** get our own catalog. (Lakebase exceptions "handled as needed.")
- **Generic only** — no customer‑specific entities (we already de‑branded off "Helios").
- **DAB‑only deploys** so assets can be reset quickly. Developers get **one week** to move assets in once access is granted.
- Quarterly audit; unused/broken demos torn down.

---

## Publication checklist (9 criteria) — our status

| # | Criterion | Our status | Notes / gap |
|---|-----------|-----------|-------------|
| 1 | Generic — no customer entities | ✅ Likely | De‑branded to opaque codes (AD/PA/SB/ET). Verify no residual real‑company names in synthetic supplier data. |
| 2 | Single entry point | ⚠️ Decide | We have app + AI/BI dashboard + Genie. Need to designate ONE entry point (likely the app) for the landing page. |
| 3 | Touches Databricks (not just a front‑end) | ✅ | Lakeflow pipeline + UC + metric views + Genie + Lakebase + (ML). |
| 4 | DAB‑deployable (`databricks.yml`) | ✅ partial | Bundle exists, but **not yet targeted at the prod workspace/catalog** (see gap A). |
| 5 | Databricks‑unique value | ✅ | Genie over **metric views**, Lakebase app state, governed pipeline. Make this explicit in the app's architecture tab (gap D). |
| 6 | Schema‑level in a prod catalog (`manufacturing`) | ❌ Gap A | We use catalog `horizontal_finance[_dev]`; must become **schema(s) under `manufacturing`**. Biggest structural change. |
| 7 | Governed tags applied at schema level | ❌ Gap B | Need `mfg_subindustry` + outcome tag (see tagging note) via `ALTER SCHEMA … SET TAGS`. |
| 8 | 3–5 slide pitch deck + 5‑min video | ❌ Gap C | Must live in `go/manufacturing/fe-build/<demo>`; schema description links to that folder. (O&G fleet shipped one‑pagers + READMEs as interim — may be acceptable.) |
| 9 | GitHub + DABs SDLC | ✅ | Repo + bundle in place. |

---

## Tagging — IMPORTANT nuance for a *functional* demo
The Operating Guide names `mfg_subindustry` + **`mfg_outcome_usecase`** (the 40‑value subindustry outcome taxonomy). But our demo is a **horizontal/functional** demo, and Hayley's 2026‑05‑29 guidance adds a **functional** path:
- **`mfg_subindustry` = `Functional Teams`** (the cross‑subindustry bucket for horizontal/functional demos — must be added as a tag value).
- **NEW tag `mfg_outcome_function` = `Finance`** (values: Finance, HR, Legal, Marketing, Strategic Revenue).

→ **Open question Q1:** Confirm with Hayley/David that our schema tags are `mfg_subindustry=Functional Teams` + `mfg_outcome_function=Finance` (NOT `mfg_outcome_usecase`), and that the governed tag `mfg_outcome_function` + the `Functional Teams` value already exist in the workspace's governed tags. The nightly tag‑sync job (03:00 ET) picks tagged schemas up onto the landing page.

---

## Structural gaps & decisions (the real work, once approved)

**A. Catalog → schema migration (biggest item).**
- Today: bundle var `catalog = horizontal_finance` (prod) / `horizontal_finance_dev` (dev); both targets point at `e2-demo-field-eng`.
- Required: data lives as **schema(s) under `manufacturing`** in `fevm-mfg-industry-prod`.
- **Open question Q2:** one schema (e.g. `manufacturing.spend_analytics`) holding gold/silver/ml as table prefixes, or a small set of schemas? The landing page tags a **schema**, and our pipeline currently writes to `bronze_*/silver/gold/ml/_meta` schemas — that layout has to collapse under one (or few) `manufacturing.*` schema(s). Affects pipeline, metric views, Genie identifiers, app config, dashboard datasets, grant scripts.
- Add a real `mfg-prod` bundle target (host `fevm-mfg-industry-prod`, catalog `manufacturing`, schema vars remapped). Keep our existing dev target for development.

**B. Governed tags** — apply via `ALTER SCHEMA manufacturing.<schema> SET TAGS (...)` after deploy (see Q1).

**C. Enablement assets** — 3–5 slide pitch deck + 5‑min walkthrough video in `go/manufacturing/fe-build/<demo>`; link from the schema description. (Confirm whether one‑pager + README interim is accepted, per the O&G precedent — **Q3**.)

**D. App "help/demo/architecture" tab** — REQUIRED by the rules ("Apps should have a help/demo/architecture tab explaining the flow", ex: critical‑minerals‑demo `/demo`). Our app pages today are home/analytics/contracts/suppliers/savings/chatbot/labeling — **no architecture tab**. Need to add one that explains the lifecycle + why Databricks (Genie→metric views, Lakebase state, pipeline, ML).

**E. Single entry point (Q4)** — designate the app as the entry point; confirm the dashboard + Genie are reachable *from* it rather than being separate tiles.

**F. Lakebase region/exception (Q5)** — our Lakebase project is `projects/spend-analytics` in **us‑west‑2**; the prod workspace is **us‑east‑1**. Rules say "Lakebase exceptions handled as needed" — confirm whether we re‑provision Lakebase in‑region or get an exception.

**G. Genie self‑enablement** — predefined questions sequenced + written in the description (we have sample questions + instructions; verify they meet the "sequenced in description" bar). Genie must also be reachable/owned correctly in the prod workspace.

**H. Usage tracking** — integrate `dbdemos-tracker` (`Tracker.setup_streamlit_tracker(...)` / event tracking) so the demo reports usage to the homepage/telemetry.

**I. App SP + grants in the new workspace** — the app's auto‑created SP is per‑workspace; re‑run `scripts/grant_app_sp_access.py` against the prod target (already bundle‑var parameterized) once deployed.

---

## Blockers / dependencies
- **B1. Schema‑create access in `manufacturing`.** Jacob Hummel (2026‑05‑31) was *blocked from creating a schema in the `manufacturing` catalog* and escalated to David Rogers. We will likely hit the same — **need David to grant our builder schema‑create access** (1‑week move‑in window starts then).
- **B2. David Rogers approval** to place the demo (sole approver).
- **B3. Workspace access** to `fevm-mfg-industry-prod` (Okta/Opal via MFG org).

---

## Proposed sequence (NOT started — for review)
1. **Confirm decisions Q1–Q5** with Hayley/David (tagging, schema layout, enablement format, single entry point, Lakebase).
2. **Get access** to `fevm-mfg-industry-prod` + schema‑create grant in `manufacturing` (B1–B3).
3. **Refactor bundle** for the catalog→schema model + add the `mfg-prod` target (gap A). Keep all dev work in `e2-demo-field-eng`.
4. **Add the app architecture/demo tab** (gap D) + wire usage tracking (gap H). ← *James wants to review app content before full deployment.*
5. **Deploy via DAB** to prod; run pipeline + `apply_metric_views`; provision Genie; run grants.
6. **Apply governed tags** (gap B) and verify the nightly sync surfaces us on `go/mfg/demo`.
7. **Enablement assets** (gap C) + link from schema description.
8. **Validate** against the 9 criteria; confirm single entry point + Genie/app self‑explainability.

## Open questions (consolidated)
- **Q1** Tagging: `mfg_subindustry=Functional Teams` + `mfg_outcome_usecase=Finance` — confirm + ensure the governed tag/value exist.
    - Links:
        - [mfg_subindustry](https://fevm-mfg-industry-prod.cloud.databricks.com/governance/governed-tags/mfg_subindustry?o=7474653700457519)
        - [mfg_outcome_usecase](https://fevm-mfg-industry-prod.cloud.databricks.com/governance/governed-tags/mfg_outcome_usecase?o=7474653700457519)
    - NOTES: 
        - (As of 2026-06-01) Tags have not been updated to include these items. 
- **Q2** Schema layout under `manufacturing` (one schema vs few); how our bronze/silver/gold/ml/_meta collapse.
    - NOTES: 
        - (As of 2026-06-01)We are likely going to have to switch the schema naming conventions. The directories under "Pipelines" directory should become the schema names likely. This is going to be a larger refactoring effort that we can plan for later. 
- **Q3** Enablement: full deck + 5‑min video now, or one‑pager + README interim (O&G precedent)?
    - NOTES: 
        - (As of 2026-06-01) Working to complete this on the side. This will be finalized once the demo is complete.
- **Q4** Single entry point = the app? Dashboard/Genie reachable from it?
    - We can make it the dashboard and then embed a link to heads to the Genie Space.
- **Q5** Lakebase: re‑provision in us‑east‑1 vs region exception.
    - 
