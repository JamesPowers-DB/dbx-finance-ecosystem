import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill, SegSelect } from "../components/Buttons";
import { BurnDownChart } from "../charts/BurnDownChart";
import { getContracts, getRenewals, getContractBurnDown } from "../api";
import { fmtUSD, fmtPct, fmtDate, fmtDays } from "../format";
import type { ContractRow, ContractBurnDown } from "../types";

export function Contracts({ searchQuery = "" }: { searchQuery?: string }) {
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [renewals, setRenewals] = useState<ContractRow[]>([]);
  const [view, setView] = useState<"active" | "renewals">("active");
  const [selected, setSelected] = useState<string | null>(null);
  const [burnDown, setBurnDown] = useState<ContractBurnDown | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getContracts(), getRenewals()])
      .then(([c, r]) => { setContracts(c); setRenewals(r); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    getContractBurnDown(selected).then(setBurnDown).catch(() => setBurnDown(null));
  }, [selected]);

  const q = searchQuery.toLowerCase();
  const baseRows = view === "active" ? contracts : renewals;
  const rows = q
    ? baseRows.filter(
        (c) =>
          c.supplier_name?.toLowerCase().includes(q) ||
          c.title?.toLowerCase().includes(q) ||
          c.contract_type?.toLowerCase().includes(q) ||
          c.region?.toLowerCase().includes(q),
      )
    : baseRows;

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200 }}>
        <PageHero
          eyebrow="Review"
          title="Contract Burn-Down"
          subtitle="Active contracts with spend consumed, days to expiration, and upcoming renewals."
          right={
            <SegSelect
              options={[{ label: "Active", value: "active" }, { label: "Renewals (180d)", value: "renewals" }]}
              value={view}
              onChange={(v) => setView(v as "active" | "renewals")}
            />
          }
        />

        <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 400px" : "1fr", gap: "var(--space-5)" }}>
          {/* Contract table */}
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Supplier", "Type", "Title", "Committed", "Consumed", "Expires"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => {
                      const urgency = (c.days_to_expiration ?? 999) < 60 ? "var(--danger)" :
                        (c.days_to_expiration ?? 999) < 120 ? "var(--warning)" : "var(--fg-1)";
                      return (
                        <tr
                          key={c.contract_workspace_id}
                          onClick={() => setSelected(selected === c.contract_workspace_id ? null : c.contract_workspace_id)}
                          style={{
                            borderBottom: "1px solid var(--border)",
                            background: selected === c.contract_workspace_id ? "var(--bg-subtle)" : "transparent",
                            cursor: "pointer",
                          }}
                        >
                          <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>
                            {c.supplier_name ?? c.supplier_id}
                          </td>
                          <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                            <Pill active={false}>{c.contract_type}</Pill>
                          </td>
                          <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13, maxWidth: 220,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {c.title}
                          </td>
                          <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                            {fmtUSD(c.total_committed_spend, true)}
                          </td>
                          <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                              <div style={{ width: 60, height: 6, background: "var(--bg-subtle)", borderRadius: 3 }}>
                                <div style={{ width: `${Math.min(c.pct_consumed ?? 0, 100)}%`, height: "100%",
                                  background: (c.pct_consumed ?? 0) > 90 ? "var(--danger)" : "var(--db-lava-600)",
                                  borderRadius: 3, transition: "width 0.3s" }} />
                              </div>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                                {fmtPct(c.pct_consumed)}
                              </span>
                            </div>
                          </td>
                          <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)",
                            fontSize: 12, color: urgency }}>
                            {fmtDate(c.expiration_date)} ({fmtDays(c.days_to_expiration)})
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Burn-down detail */}
          {selected && burnDown && (
            <Card accent="var(--db-lava-600)">
              <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700, marginBottom: "var(--space-3)" }}>
                {burnDown.title ?? selected}
              </h3>
              <div style={{ marginBottom: "var(--space-3)" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)" }}>
                  Committed: {fmtUSD(burnDown.total_committed_spend, true)}
                </span>
              </div>
              <BurnDownChart
                points={burnDown.points}
                committedSpend={burnDown.total_committed_spend ?? undefined}
                width={360}
                height={200}
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
