import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { METRICS } from "../components/metricDefinitions";
import { fmtUSD, fmtPct } from "../format";
import type { KpiResponse } from "../types";

interface HomeProps {
  onNavigate: (p: string) => void;
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
    what: "One ledger of realized savings — hard cost reductions and soft cost avoidances — each tied to a sourcing event or contract and tracked as a percentage of addressable spend. Submit a saving, then have a second person attest it (segregation of duties).",
    how: "Evidence procurement's value with an auditable trail back to the originating artifact.",
    accent: "var(--db-green-700)",
    accent2: "var(--db-yellow-700)",
  },
  {
    id: "chatbot",
    label: "Procurement Chatbot",
    what: "Procurement in plain language. Find suppliers for a need, pull a supplier profile, surface expiring or under-used contracts, review last quarter's savings, or submit a purchase request — large or regulated buys auto-route to Sourcing & Contracting. Anything outside those flows falls back to Genie over the governed metric views.",
    how: "Act on procurement and ask questions in one place.",
    accent: "var(--db-lava-600)",
    accent2: "var(--db-maroon-700)",
  },
];

export function Home({ onNavigate }: HomeProps) {
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/kpis")
      .then((r) => r.json())
      .then((d: KpiResponse) => setKpis(d))
      .catch(() => setKpis(null))
      .finally(() => setLoading(false));
  }, []);

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

        {/* Module overview — what each surface does and how to use it. */}
        <div style={{ marginBottom: "var(--space-4)" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--fg-3)" }}>
            What you can do here
          </span>
          <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", lineHeight: "var(--lh-normal)", marginTop: "var(--space-1)" }}>
            Five modules cover the spend lifecycle, from a portfolio-level overview down to acting on a single purchase. Select any card to open it.
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
