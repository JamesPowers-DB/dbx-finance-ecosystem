# Meeting Prep — AR / Billing / Collections (Order-to-Cash)

> **Audience:** finance teams focused on **AR, billing, and collections**.
> **What you have:** a shipped **Spend Analytics** demo (procure-to-pay). No time to
> build a new one before the call.
> **Goal of this doc:** give you the *through-lines* — connect what you know (spend, AP,
> sourcing, contracting) → what the demo shows today → what these teams care about
> tomorrow — plus a discovery script so the call earns its keep.

The call is mostly **discovery**. Your job isn't to show an AR demo you don't have;
it's to (1) show that the *exact same platform pattern* you already built for spend is
the answer for their side of the ledger, and (2) leave with a crisp picture of their
data, systems, and pain. Lead with the mental model, demo the spend assets as a
*proof of pattern*, and spend most of the time listening.

---

## 1. The one mental model: two halves of the same cash cycle

Everything you built lives on the **left** side. Everything they own lives on the
**right**. It's the *same shape, mirrored* — same lifecycle thinking, same "managed vs.
leaking" question, same governed-data problem.

```
   PROCURE-TO-PAY  (what the demo shows)      ORDER-TO-CASH  (what they own)
   ───────────────────────────────────       ──────────────────────────────────
   source / contract                          quote / contract
        → request                                  → order
        → purchase order                           → fulfill / deliver
        → supplier invoice                         → bill / invoice (the "billing" team)
        → PAY (cash out)                           → COLLECT (cash in)  (the "collections" team)

   Counterparty: SUPPLIER                     Counterparty: CUSTOMER
   Working capital: ACCOUNTS PAYABLE (~$600M) Working capital: ACCOUNTS RECEIVABLE (~$800M)
   Headline question: how much spend is       Headline question: how much revenue is
   "under management" vs. leaking?            billed correctly & collected on time vs. leaking?
```

> **The line that lands:** *"You've seen me chase every dollar going **out** the door —
> source to pay, and what leaks. AR, billing, and collections are the mirror image:
> every dollar coming **in** — contract to cash, and what leaks there. It's the same
> platform pattern, pointed at the other half of the balance sheet. And on this
> company, AR (~$800M) is actually bigger than AP (~$600M) — more cash is tied up on
> your side than on the side we just optimized."*

---

## 2. Through-line map: demo asset → AR/billing/collections analog

Use this table to answer "but my world is receivables, not spend." For each thing they'd
see in the spend demo, there's a clean mirror on their side — and in most cases the
**data model already reaches there** (see §4).

| In the spend demo today | The AR / billing / collections analog | What it answers for them |
|---|---|---|
| **Spend lifecycle funnel** (request → PO → invoice → paid) | **O2C funnel** (contract → order → billed → collected) | Where does revenue stall between booked and banked? |
| **Managed-spend %** (on-contract, sourced) | **Clean-bill % / on-time-collection %** (billed per contract, collected by terms) | How much revenue is "under management" vs. at risk? |
| **Spend leakage** (off-contract tail) | **Revenue leakage** — under-billing, missed price escalators, unbilled usage, contract non-compliance | Money you earned but never billed or collected |
| **Supplier scorecard** (spend, on-time pay, ML category) | **Customer scorecard** — DSO by customer, payment behavior, dispute rate, credit risk | Who pays late, who to put on credit hold, who to prioritize |
| **Top suppliers by spend** | **Top customers by exposure / overdue AR** | Concentration of collection risk |
| **AI/BI dashboard** (CFO view of spend) | **AR cockpit** — DSO, CEI, aging waterfall, cash forecast | One governed view of receivables health |
| **Genie: "talk to your spend"** | **Genie: "talk to your receivables"** — *"which invoices over 60 days for Aerospace?"* | Self-serve answers without a BI ticket |
| **ML spend classifier** (categorize invoices) | **ML for collections** — payment-default / late-payment prediction, **cash-application matching**, dispute-reason classification | Prioritize collectors, auto-match remittances |
| **Procurement agent** (find supplier, submit PR) | **Collections agent** — draft dunning, summarize a customer's open items, propose promise-to-pay | The "last mile": acting, not just seeing |
| **Savings register** (log realized savings) | **Recovery / dispute register** — log recovered leakage, resolved deductions | Quantify the money the platform helped capture |

> The repeating Databricks story under every row: **one governed metric layer → a
> dashboard, Genie, and an app.** One definition of "DSO" or "clean bill," used
> everywhere, no spreadsheet that disagrees. That's the same "single source of truth"
> punchline from the spend demo — just say "receivables" instead of "spend."

---

## 3. The metrics & vocabulary they'll use (so you speak their language)

Drop these naturally; they signal you understand O2C, not just AP.

**Billing**
- **Billing models:** milestone / progress (long-cycle Aerospace), usage/consumption,
  subscription/recurring, time-&-materials, contract **price escalators**.
- **Revenue leakage:** under-billing, **missed escalators**, unbilled usage/services,
  rebates/credits misapplied, contract terms not enforced at invoice time.
- **ASC 606 / performance obligations:** revenue recognized as obligations are
  satisfied — relevant because the demo's contract model already has a
  `performance_obligation` table.
- **Unbilled vs. billed AR; deferred revenue.**

**AR / Collections**
- **DSO** (Days Sales Outstanding) — the headline. **Best-Possible DSO**, **DSO delta**.
- **AR aging buckets:** current / 1-30 / 31-60 / 61-90 / 90+.
- **CEI** (Collection Effectiveness Index), **ADD** (Average Days Delinquent).
- **Cash application:** matching incoming payments + remittance to open invoices;
  **unapplied / on-account cash** is the pain (manual, error-prone — a prime ML target).
- **Deductions / disputes / chargebacks:** especially trade/short-pay in industrials.
- **Credit management:** credit limits, **credit holds**, credit risk scoring.
- **Collections strategy:** prioritization, **dunning** cadence, **promise-to-pay**,
  bad-debt / write-offs, allowance for doubtful accounts.
- **Cash forecasting:** when will open AR actually convert to cash?

---

## 4. What the demo's data model *already* contains on their side (your honest hook)

This is your credibility move. The shipped demo *surfaces* spend, but the **lakehouse
data model already extends into order-to-cash** — you don't have to pretend. Pull up
Catalog Explorer and show the latent assets:

- **`bronze_fusion`** (Oracle accounting source) already includes **`ar_invoices_all`,
  `ar_receipt_schedules`, `ar_customer_sites_all`** — the AR subledger shape.
- **`bronze_cms`** (the in-house contract system) is **outbound *customer* contracts** —
  `total_contract_value`, **`billing_schedule`**, **`performance_obligation`**,
  `contract_amendment`. That *is* the billing backbone for O2C.
- **`silver`** already conforms **`customer`**, **`invoice_ar`**, **`contract_outbound`**.
- **`gold`** has **`fact_revenue`** and **`dim_customer`**, with reserved columns
  **`contract_leakage_flag`** and **`savings_realized_usd`** — i.e. revenue-leakage
  detection was *designed in* as a Phase-2 hook.

> **The line:** *"This isn't a spend-only platform that we'd have to bolt receivables
> onto. The same medallion model already ingests your AR invoices, your customer master,
> and your billing-and-performance-obligation contract data. The spend surfaces are just
> the first ones we lit up. Standing up the receivables surfaces is **the same pattern
> on tables that are already in the model** — not a new build."*

Be honest about the boundary: those AR/contract-outbound tables exist in the *design and
schema*; the shipped demo's generators and dashboards focus on spend, so the AR facts
aren't populated/surfaced yet. That's a *fast follow*, not a *rebuild* — and that
distinction is exactly what makes the platform story credible.

---

## 5. Discovery script (the heart of the call)

Goal: leave knowing their **systems**, **data fragmentation**, **metrics they're
measured on**, and the **one process that hurts most**. Grouped so you can flow by
whoever's in the room. Don't fire all of these — pick the live threads.

**Landscape & systems**
- Walk me through your order-to-cash today — where does it start, and where's the cash
  actually applied?
- What systems hold the truth? (ERP — Oracle/SAP? a separate billing engine? a
  collections tool like HighRadius / Billtrust / a CRM?) Where do they *not* talk?
- How much of billing and cash-app is manual vs. automated today?

**Billing**
- What billing models do you run — milestone, usage, subscription, T&M? Which is messiest?
- How do you know you billed *everything* you were entitled to? How would you catch a
  missed price escalator or unbilled usage today?
- How long from "delivered/obligation met" to "invoice out the door"?

**AR & collections**
- What's your DSO, and what's the gap to best-possible DSO? How is it trending?
- How do collectors decide *who to call first* each morning — and what's that based on?
- Where does cash application break down? How much sits as unapplied / on-account?
- How do disputes and deductions get worked — and how long do they age?
- How do you set and enforce credit limits / holds? How current is the customer risk view?

**Pain, metrics & ownership**
- What number are *you* measured on — DSO, CEI, bad-debt, cash forecast accuracy?
- If you could see one thing across all of AR that you can't see today, what is it?
- When the CFO asks "when does this AR turn into cash," how do you answer — and how
  confident are you?
- Who owns the data when billing, AR, and collections sit in different tools? Who
  reconciles them?

**The bridge question (sets up the platform story)**
- Everything I just showed for spend — one governed definition feeding a dashboard,
  natural-language Q&A, and an app to act — if you had that for receivables, which part
  would change your week the most: *seeing* it, *asking* it, or *acting* on it?

---

## 6. Suggested call flow (~loose, discovery-led)

1. **(5 min) Frame the mirror** — §1 diagram. "Same cycle, opposite direction." Establish
   you already think in lifecycles and leakage.
2. **(10 min) Show the spend demo as proof-of-pattern** — *don't* sell spend; sell the
   *architecture*. Walk the funnel, hit Genie once, open the app once. Each time say the
   AR analog out loud (use §2). ~10 min, not 30.
3. **(5 min) Open Catalog Explorer** — show the latent AR / customer / billing-contract
   tables (§4). "The model already reaches your side."
4. **(25+ min) Discovery** — §5. This is the point of the meeting. Take notes live.
5. **(5 min) Close** — reflect back the one pain that hurt most, name the smallest
   credible first surface (usually an **AR cockpit dashboard + a "talk to your
   receivables" Genie** on their existing AR data), and propose a follow-up to scope it.

---

## 7. Likely objections & quick answers

| They say | You say |
|---|---|
| "This is a *spend* tool." | "It's a *governed-finance-data* pattern. Spend is the first surface; the model already ingests your AR and billing-contract data. Same pipeline, same metric layer — pointed the other direction." |
| "We already have a collections tool (HighRadius/Billtrust/etc.)." | "Great — those are great at *workflow*. The gap is usually the *governed, cross-system source of truth* underneath, and self-serve analytics on top. Databricks is the layer that makes one DSO definition true everywhere and feeds your tools, not a replacement for the collector's workbench." |
| "Our data's a mess across billing/AR/ERP." | "That's exactly the problem the medallion pipeline solved for spend — three source systems (SAP, Oracle, in-house) conformed to one model with a ±2% reconcile gate. Same approach conforms billing + AR + ERP." |
| "Can it actually *predict* who won't pay / auto-apply cash?" | "Yes — same place the spend classifier lives. Payment-default prediction and cash-application matching are textbook ML on this data; we reserved the hooks (`fact_revenue` leakage flags) by design." |
| "How fast could we see something real?" | "Because the AR tables are already in the model, the first surface — an AR cockpit + Genie on your real data — is a *fast follow*, not a ground-up build." |

---

## 8. One-screen cheat sheet (glance at this in the meeting)

- **Mental model:** P2P (spend, what I built) ↔ **O2C (AR, your world)**. Same cycle, mirrored. Cash out vs. cash in.
- **Their headline metric:** **DSO** (+ CEI, aging, cash forecast). Leakage = under-billing / missed escalators / unbilled.
- **My repeatable punchline:** one governed metric layer → dashboard + Genie + app. "Single source of truth" for *receivables*.
- **Honest hook:** the lakehouse model **already has** `ar_invoices`, `customer`, outbound billing contracts (`billing_schedule`, `performance_obligation`), `fact_revenue` w/ leakage flags. Fast follow, not rebuild.
- **Demo spend for ≤10 min as *proof of pattern*. Spend the rest listening.** Discovery is the deliverable.
- **Close on:** their worst pain, reflected back + smallest credible first surface (AR cockpit + "talk to your receivables").
```
