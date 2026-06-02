import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { AnimatedTileMark } from "../components/layout/AnimatedTileMark";
import { StatTile } from "../components/StatTile";
import { METRICS } from "../components/metricDefinitions";
import { fmtUSD, fmtPct } from "../format";
import type { KpiResponse } from "../types";

interface HomeProps {
  onNavigate: (p: string) => void;
}

const TILES = [
  {
    id: "contracts",
    label: "Contract Burn-Down",
    desc: "Monitor contract consumption, days-to-expiration, and renewal queue.",
    kind: "gauge" as const,
    accent: "var(--db-lava-600)",
    accent2: "var(--db-yellow-600)",
  },
  {
    id: "suppliers",
    label: "Supplier Performance",
    desc: "Scorecard, on-time payment, DPO, and payment-terms renegotiation targets.",
    kind: "climb" as const,
    accent: "var(--db-navy-800)",
    accent2: "var(--db-blue-700)",
  },
  {
    id: "savings",
    label: "Cost Savings",
    desc: "Auto-detected reductions + manual avoidance ledger vs FP&A budget.",
    kind: "bars" as const,
    accent: "var(--db-green-700)",
    accent2: "var(--db-yellow-700)",
  },
  {
    id: "chatbot",
    label: "Procurement Chatbot",
    desc: "Natural-language PR intake: suggest suppliers, check contracts, submit PRs.",
    kind: "pulse" as const,
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

        {/* Feature tiles */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "var(--space-4)",
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
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ fontSize: "var(--fs-h4)", fontWeight: 700, marginBottom: "var(--space-2)" }}>
                    {t.label}
                  </h3>
                  <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", lineHeight: "var(--lh-normal)" }}>
                    {t.desc}
                  </p>
                </div>
                <AnimatedTileMark kind={t.kind} accent={t.accent} accent2={t.accent2} />
              </div>
            </Card>
          ))}
        </div>

        {/* Powered-by note — this app is one consumption surface; the value is
            the governed Databricks lakehouse underneath it. */}
        <div
          style={{
            marginTop: "var(--space-6)",
            padding: "var(--space-4) var(--space-5)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            background: "var(--bg-subtle)",
            fontSize: "var(--fs-body-sm)",
            color: "var(--fg-2)",
            lineHeight: "var(--lh-normal)",
          }}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", textTransform: "uppercase", letterSpacing: "var(--tracking-eyebrow)", color: "var(--fg-3)" }}>
            Powered by Databricks
          </span>
          <div style={{ marginTop: "var(--space-2)" }}>
            Every metric resolves through governed Unity Catalog <strong>Metric Views</strong> (one source of truth shared by this app, the AI/BI dashboards, and Genie). The chatbot is a <strong>Genie</strong> Space querying those metric views; spend is synthesized → curated by a <strong>Lakeflow</strong> pipeline; categories come from an <strong>MLflow</strong> classifier; app state persists in <strong>Lakebase</strong>; and every query runs as the signed-in user via <strong>OBO</strong>. This portal is one surface over that lakehouse — not the product.
          </div>
        </div>
      </div>
    </div>
  );
}
