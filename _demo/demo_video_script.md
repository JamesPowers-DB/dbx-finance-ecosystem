# 5-Minute Demo Video — Spend Analytics on Databricks

A single-presenter, screen-recorded narrative. Emphasis: **why** (the outcome) and
**how** (the way Databricks uniquely delivers it). Three surfaces shown in order:
**AI/BI Dashboard → Genie Space → the Databricks App.**

> **Before you record — fill these live values** (read them off the dashboard once
> the regen + pipeline finish), and have three browser tabs pre-loaded:
> 1. the AI/BI dashboard (Spend Visibility) · 2. the Genie space · 3. the app (Home).
> Placeholders to replace: `[TOTAL_SPEND]` (e.g. ~$2.9B), `[MANAGED_PCT]` (e.g. ~50%),
> `[LEAKAGE]` (unmanaged/off-contract $).
>
> Spoken word count ≈ 690 → ~5:00 at a calm ~135 wpm. Timestamps are guides.

---

## 0:00 – 0:40 · The "why" (hook + outcome)

**SHOW:** App Home page (the module overview + "Powered by Databricks" note), or a title slide.

**SAY:**
"Every large company spends billions with suppliers — but the spend is scattered
across sourcing, procurement, AP, and the general ledger. The number nobody can
answer cleanly is: *how much of our spend is actually under management* — on a
contract, competitively sourced — versus leaking to the tail, off-contract, where
we have no leverage.

That's the outcome this solution delivers: **end-to-end visibility across the spend
lifecycle — source and contract, to request, to order, to invoice, to paid — and a
clear line on what's managed versus what's leaking.** Today that's
`[TOTAL_SPEND]` in spend, with only about `[MANAGED_PCT]` under management. Let me
show you how Databricks turns that scattered data into something you can see, ask,
and act on."

---

## 0:40 – 1:20 · The "how" (the architecture, in one breath)

**SHOW:** Catalog Explorer — the single schema with `bronze_ / silver_ / gold_` tables
and the `gold_mv_*` metric views. (Or the "Powered by Databricks" note on Home.)

**SAY:**
"Here's how. Raw exports from the source systems land in the lakehouse and a
**Lakeflow declarative pipeline** curates them bronze to silver to gold — every
quarter, governed, reconciled to the penny. On top of gold we define **Unity
Catalog Metric Views** — the business logic for 'managed spend,' 'addressable
spend,' contract coverage — written **once**. That's the key idea: the dashboard,
Genie, and the app you're about to see all read the *same* governed metric views.
One definition, one source of truth, three experiences. No metric drift, no
spreadsheet that disagrees with the dashboard. A **MLflow** model classifies spend
categories, and the app's operational state lives in **Lakebase**. Let's look."

---

## 1:20 – 2:30 · Surface 1 — the AI/BI Dashboard

**SHOW:** The Spend Visibility dashboard. Walk top-to-bottom: KPI tiles → spend trend
→ managed-status / PR-source breakdown → lifecycle funnel → top suppliers.

**SAY:**
"First, the AI/BI dashboard — the executive view, served directly from the metric
views. Up top, the headline KPIs: total spend, managed-spend percentage, contract
coverage, on-time payment. Then the trend, and the breakdown by how each purchase
*originated* — catalog, guided portal, or manual off-contract requests.

This is the funnel that tells the story: of the spend that *requested* through the
system, here's what made it onto a purchase order, and what actually got paid — and
at each step you can see the value that **escaped management**, the off-contract
leakage. And here are the suppliers concentrating the most spend. In one screen, a
CFO sees where the money goes and where the leverage is — all governed, all
refreshed by the pipeline, no manual prep."

---

## 2:30 – 3:30 · Surface 2 — the Genie Space

**SHOW:** The Genie space. Type 2 questions live, e.g.
"What was our total managed spend in the last 12 months?" then
"Which suppliers have the most off-contract spend?"

**SAY:**
"But executives ask follow-up questions a fixed dashboard can't anticipate. That's
Genie. This is the *same governed metric views*, exposed in natural language — so
when I ask 'what was our managed spend over the last twelve months,' Genie answers
with the exact same definition the dashboard uses. Watch — I'll ask it live.

[ask question 1] … and a follow-up: 'which suppliers have the most off-contract
spend?' [ask question 2]. Notice it's writing governed SQL against the metric views
and showing its work — this isn't a black box, and it isn't a separate copy of the
logic. Anyone on the team can interrogate spend in plain English and trust the
answer, because it resolves through the same source of truth."

---

## 3:30 – 4:40 · Surface 3 — the Databricks App

**SHOW:** The app. Spend Analytics tab (funnel + drill) → Supplier scorecard (expand a
supplier) → Savings Register → Procurement Chatbot (ask it to find a supplier / submit a PR).

**SAY:**
"Seeing and asking is half of it. The last mile is *acting* — and that's the
Databricks App. It's a full custom application running on Databricks, reading the
same metric views, with every query executed **as the signed-in user** through
on-behalf-of auth, so governance carries all the way to the UI.

A buyer can drill from the spend funnel straight into a supplier's scorecard — spend,
on-time payment, an ML-assigned category — and model a renegotiation. Procurement
teams log realized savings in the **Savings Register**, backed by Lakebase. And the
**procurement assistant** — powered by a Databricks model-serving endpoint plus
Genie — lets someone find a supplier, check contracts, or submit a purchase request
in plain language, with guardrails that route large or regulated buys to sourcing.
The lakehouse isn't just for analysts anymore — it's the backend for the people
doing the work."

---

## 4:40 – 5:00 · Close (recap why + how)

**SHOW:** Back to the Home page / "Powered by Databricks" note.

**SAY:**
"So that's the why and the how. The *why*: one trusted view of spend, and a clear
line on what's managed versus leaking — so you can go capture it. The *how*: a
governed Databricks lakehouse, with **Unity Catalog Metric Views as the single
source of truth** feeding a dashboard, Genie, and a custom app — plus ML and Lakebase
on the same platform. One copy of the data, one copy of the logic, three ways to use
it. That's what makes this uniquely Databricks. Thanks for watching."

---

## Delivery tips
- **Pace:** ~135 wpm. If you run long, trim the architecture paragraph (0:40) — the
  surfaces sell themselves.
- **The throughline to hammer:** *one governed metric-view layer powers all three
  surfaces.* Say "same source of truth" at least once per surface.
- **Have the Genie questions pre-typed** in a notes file to paste — don't type live
  on camera (latency + typos kill momentum).
- **Pre-run the chatbot prompt once** before recording so the model is warm and you
  know the answer it gives.
- If a live number looks off after regen, just speak to the *shape* ("about half is
  under management") rather than a precise figure.
