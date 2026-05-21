import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { AnimatedTileMark } from "../components/layout/AnimatedTileMark";
import { StatTile } from "../components/StatTile";
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
  {
    id: "labeling",
    label: "Spend Labeling Monitor",
    desc: "ML classification coverage, confidence distributions, and model history.",
    kind: "orbit" as const,
    accent: "var(--db-navy-800)",
    accent2: "var(--db-blue-700)",
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
          eyebrow="Overview"
          title="Strategic Sourcing Portal"
          subtitle="Helios Industrial Group — procurement intelligence for sourcing managers."
        />

        {/* KPI strip */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile
            label="Total Spend"
            value={loading ? "…" : fmtUSD(kpis?.total_spend_usd, true)}
            accent="var(--db-lava-600)"
            sub="trailing 12 months"
          />
          <StatTile
            label="Managed Spend"
            value={loading ? "…" : fmtPct(kpis?.managed_spend_pct)}
            accent="var(--db-green-700)"
            sub="of addressable"
          />
          <StatTile
            label="Contract Coverage"
            value={loading ? "…" : fmtPct(kpis?.contract_coverage_pct)}
            accent="var(--db-yellow-600)"
            sub="spend under contract"
          />
          <StatTile
            label="On-Time Payment"
            value={loading ? "…" : fmtPct(kpis?.on_time_payment_pct)}
            accent="var(--db-navy-800)"
            sub="invoice lines"
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
      </div>
    </div>
  );
}
