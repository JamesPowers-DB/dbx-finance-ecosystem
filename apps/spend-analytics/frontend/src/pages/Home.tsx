import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { Icon } from "../components/Icon";
import { METRICS } from "../components/metricDefinitions";
import { fmtUSD, fmtPct } from "../format";
import { getAttention, getSavingsKpis } from "../api";
import type { KpiResponse, AttentionResponse, SavingsKpis } from "../types";

interface HomeProps {
  onNavigate: (p: string) => void;
}

// One actionable item in the "Needs your attention" queue. Each maps to a
// module so the entry point is "here's what to act on", not "here's a menu".
interface AttentionItem {
  page: string;
  count: number;
  label: string;
  metric: string;
  cta: string;
  accent: string;
}

const TILES = [
  {
    id: "analytics",
    label: "Spend Analytics",
    what: "The executive starting point. A lifecycle funnel (request → order → invoice → paid), a spend-trend chart you can switch between daily, weekly, monthly, and quarterly grains, and composition breakdowns by category, segment, or PR source. Click any bar or supplier to drill in and jump straight to that supplier's scorecard.",
    how: "See where spend concentrates and where it leaks past management.",
    accent: "var(--db-lava-600)",
    accent2: "var(--db-yellow-600)",
  },
  {
    id: "contracts",
    label: "Contracts",
    what: "Every inbound contract ranked by renewal risk — expiring soon, under-utilized, or already exhausted. Expand a row for its burn-down curve, commercial terms, and the invoices and POs drawing against it.",
    how: "Get ahead of renewals and catch commitments you're paying for but not consuming.",
    accent: "var(--db-yellow-600)",
    accent2: "var(--db-lava-600)",
  },
  {
    id: "suppliers",
    label: "Supplier Performance",
    what: "A scorecard per supplier: trailing spend, on-time payment, DPO, maverick-vs-managed mix, ML-assigned category, top PO commitments, and dimensional attributes. Expand a supplier to model a renegotiation what-if across payment-terms, discount, and under-management levers and see the forecast impact.",
    how: "Prioritize which supplier relationships to renegotiate.",
    accent: "var(--db-navy-800)",
    accent2: "var(--db-blue-700)",
  },
  {
    id: "savings",
    label: "Cost Savings",
    what: "One ledger of realized savings — hard cost reductions and soft cost avoidances — each tied to a sourcing event or contract and tracked as a percentage of addressable spend. A two-step workflow: submit a saving, then a second person attests it (segregation of duties) before it counts.",
    how: "Log a saving and route it for second-person attestation — an auditable approval trail.",
    accent: "var(--db-green-700)",
    accent2: "var(--db-yellow-700)",
  },
];

export function Home({ onNavigate }: HomeProps) {
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [attention, setAttention] = useState<AttentionResponse | null>(null);
  const [savings, setSavings] = useState<SavingsKpis | null>(null);

  useEffect(() => {
    fetch("/api/kpis")
      .then((r) => r.json())
      .then((d: KpiResponse) => setKpis(d))
      .catch(() => setKpis(null))
      .finally(() => setLoading(false));
    // The attention queue degrades gracefully — a failed fetch just hides the
    // corresponding item rather than blocking the page.
    getAttention().then(setAttention).catch(() => setAttention(null));
    getSavingsKpis().then(setSavings).catch(() => setSavings(null));
  }, []);

  // Build the prioritized action queue from the two UC-backed items + the
  // Lakebase-backed savings-attestation count. Only items with work to do show.
  const attentionItems: AttentionItem[] = [
    attention && attention.contracts.count > 0 && {
      page: "contracts",
      count: attention.contracts.count,
      label: attention.contracts.count === 1 ? "contract needs a renewal decision" : "contracts need a renewal decision",
      metric: `${fmtUSD(attention.contracts.committed_usd, true)} committed at risk`,
      cta: "Review renewals",
      accent: "var(--db-yellow-600)",
    },
    attention && attention.suppliers.count > 0 && {
      page: "suppliers",
      count: attention.suppliers.count,
      label: attention.suppliers.count === 1 ? "top supplier is under-managed" : "top suppliers are under-managed",
      metric: `${fmtUSD(attention.suppliers.spend_usd, true)} spend below 50% managed`,
      cta: "Prioritize renegotiation",
      accent: "var(--db-navy-800)",
    },
    savings && savings.pending_count > 0 && {
      page: "savings",
      count: savings.pending_count,
      label: savings.pending_count === 1 ? "saving awaits attestation" : "savings await attestation",
      metric: `${fmtUSD(savings.pending_total, true)} pending sign-off`,
      cta: "Attest savings",
      accent: "var(--db-green-700)",
    },
  ].filter(Boolean) as AttentionItem[];

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1100, margin: "0 auto" }}>
        <PageHero
          eyebrow="End-to-end spend visibility"
          title="Strategic Spend Analytics"
          subtitle="Follow every dollar across the spend lifecycle — source/contract → request → order → invoice → paid — and see what's under management vs. leaking to the tail."
        />

        {/* Powered-by note — pulled to the top as the framing statement: this app
            is one consumption surface; the value is the governed lakehouse under it. */}
        <div
          style={{
            marginBottom: "var(--space-6)",
            padding: "var(--space-4) var(--space-5)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid var(--db-lava-600)",
            borderRadius: "var(--radius-lg)",
            background: "var(--bg-subtle)",
            boxShadow: "var(--shadow-sm)",
            lineHeight: "var(--lh-normal)",
          }}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-body-sm)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--db-lava-600)" }}>
            Powered by Databricks
          </span>
          <div style={{ marginTop: "var(--space-2)", fontSize: "var(--fs-body)", color: "var(--fg-1)" }}>
            Every metric resolves through governed Unity Catalog <strong>Metric Views</strong> (one source of truth shared by this app, the AI/BI dashboards, and Genie). The chatbot is a <strong>Genie</strong> Space querying those metric views; spend is synthesized → curated by a <strong>Lakeflow</strong> pipeline; categories come from an <strong>MLflow</strong> classifier; app state persists in <strong>Lakebase</strong>; and every query runs as the signed-in user via <strong>OBO</strong>. This portal is one surface over that lakehouse — not the product.
          </div>
        </div>

        {/* KPI strip — trailing 12 months, paid invoices only.
            "Managed Spend" = addressable spend with a PR or active contract.
            "Contract Coverage" = paid invoice spend matched to an active
            contract / addressable spend (same period).
            "On-Time Payment %" is spend-weighted. */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile
            label="Total Spend"
            value={loading ? "…" : fmtUSD(kpis?.total_spend_usd, true)}
            accent="var(--db-lava-600)"
            sub="trailing 12 months, paid"
            tooltip={METRICS.totalSpend}
          />
          <StatTile
            label="Managed Spend"
            value={loading ? "…" : fmtPct(kpis?.managed_spend_pct)}
            accent="var(--db-green-700)"
            sub="contracted or sourced"
            tooltip={METRICS.managedSpend}
          />
          <StatTile
            label="Contract Coverage"
            value={loading ? "…" : fmtPct(kpis?.contract_coverage_pct)}
            accent="var(--db-yellow-600)"
            sub="paid spend under contract"
            tooltip={METRICS.contractCoverage}
          />
          <StatTile
            label="On-Time Payment %"
            value={loading ? "…" : fmtPct(kpis?.on_time_payment_pct)}
            accent="var(--db-navy-800)"
            sub="spend-weighted"
            tooltip={METRICS.onTimePayment}
          />
        </div>

        {/* Procurement Agent — the primary entry point. Ask in plain language;
            the agent runs the procurement tools and routes you to the right
            module to act. Prominent by design (the recommended "way in"). */}
        <div
          onClick={() => onNavigate("chatbot")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onNavigate("chatbot"); } }}
          style={{
            marginBottom: "var(--space-6)",
            padding: "var(--space-5)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            background: "linear-gradient(135deg, var(--db-navy-800) 0%, var(--db-maroon-700) 100%)",
            color: "var(--fg-on-dark)",
            cursor: "pointer",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            gap: "var(--space-5)",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: "1 1 320px", minWidth: 280 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
              <div style={{ width: 38, height: 38, borderRadius: "var(--radius-md)", background: "var(--db-lava-600)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon name="bot" size={20} color="var(--fg-on-dark)" />
              </div>
              <div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--db-lava-300, #ffb3a3)", fontWeight: 600 }}>
                  Start here
                </span>
                <h3 style={{ fontSize: "var(--fs-h3)", fontWeight: 700, margin: 0, color: "var(--fg-on-dark)" }}>
                  Procurement Agent
                </h3>
              </div>
            </div>
            <p style={{ fontSize: "var(--fs-body)", color: "var(--fg-on-dark-2)", lineHeight: "var(--lh-normal)", margin: 0, maxWidth: 620 }}>
              Ask in plain language — find suppliers, check expiring contracts, review savings, or submit a purchase request. The agent runs the right tool and links you straight to the module to act. Anything open-ended falls back to Genie over the governed metric views.
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", alignItems: "stretch", flex: "0 1 280px" }}>
            {["Which contracts expire soon and are unused?", "Find suppliers for industrial sensors", "What were our cost savings last quarter?"].map((ex) => (
              <span key={ex} style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-on-dark)", background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.18)", borderRadius: "var(--radius-pill)", padding: "var(--space-2) var(--space-3)", lineHeight: "var(--lh-tight)" }}>
                “{ex}”
              </span>
            ))}
            <span style={{ fontSize: "var(--fs-body-sm)", fontWeight: 700, color: "var(--fg-on-dark)", marginTop: "var(--space-1)", textAlign: "right" }}>
              Open the agent <span aria-hidden="true">→</span>
            </span>
          </div>
        </div>

        {/* Needs your attention — the action queue. Turns "here's information"
            into "here's what to do next", each item deep-linking to its module. */}
        {attentionItems.length > 0 && (
          <div style={{ marginBottom: "var(--space-6)" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--fg-3)" }}>
              Needs your attention
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
              {attentionItems.map((it) => (
                <div
                  key={it.page}
                  onClick={() => onNavigate(it.page)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onNavigate(it.page); } }}
                  className="attention-row"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-4)",
                    padding: "var(--space-3) var(--space-4)",
                    background: "var(--bg-canvas)",
                    border: "1px solid var(--border)",
                    borderLeft: `3px solid ${it.accent}`,
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                  }}
                >
                  <span style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-h3)", fontWeight: 700, color: it.accent, minWidth: 44, textAlign: "center" }}>
                    {it.count}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "var(--fs-body)", fontWeight: 600, color: "var(--fg-1)" }}>
                      {it.count} {it.label}
                    </div>
                    <div style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)" }}>
                      {it.metric}
                    </div>
                  </div>
                  <span style={{ flexShrink: 0, fontSize: "var(--fs-body-sm)", fontWeight: 600, color: it.accent, whiteSpace: "nowrap" }}>
                    {it.cta} <span aria-hidden="true">→</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Module overview — what each surface does and how to use it. */}
        <div style={{ marginBottom: "var(--space-4)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--fg-3)" }}>
            Explore the modules
          </span>
          <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", lineHeight: "var(--lh-normal)", marginTop: "var(--space-1)" }}>
            Four modules cover the spend lifecycle, from a portfolio-level overview down to acting on a single purchase. Select any card to open it.
          </p>
        </div>

        {/* Feature tiles — alignItems:start so each card hugs its own content
            and top-aligns within the row rather than stretching to equal height. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "var(--space-4)",
            alignItems: "start",
          }}
        >
          {TILES.map((t) => (
            <Card
              key={t.id}
              accent={t.accent}
              accent2={t.accent2}
              hover
              onClick={() => onNavigate(t.id)}
            >
              <h3 style={{ fontSize: "var(--fs-h4)", fontWeight: 700, marginBottom: "var(--space-2)" }}>
                {t.label}
              </h3>
              <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", lineHeight: "var(--lh-normal)", margin: 0 }}>
                {t.what}
              </p>
              {/* Divider + "How to use" call-to-action */}
              <div
                style={{
                  marginTop: "var(--space-3)",
                  paddingTop: "var(--space-3)",
                  borderTop: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "baseline",
                  gap: "var(--space-2)",
                }}
              >
                <span
                  style={{
                    flexShrink: 0,
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--fs-caption)",
                    textTransform: "uppercase",
                    letterSpacing: "var(--tracking-eyebrow)",
                    fontWeight: 600,
                    color: t.accent,
                  }}
                >
                  How to use
                </span>
                <span style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-1)", lineHeight: "var(--lh-normal)" }}>
                  {t.how} <span aria-hidden="true" style={{ color: t.accent, fontWeight: 700 }}>→</span>
                </span>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
