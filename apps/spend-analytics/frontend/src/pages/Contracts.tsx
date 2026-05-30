import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill, SegSelect } from "../components/Buttons";
import { MetricTooltip } from "../components/MetricTooltip";
import { HeaderLabel } from "../components/HeaderLabel";
import { METRICS } from "../components/metricDefinitions";
import { BurnDownChart } from "../charts/BurnDownChart";
import {
  getContracts,
  getRenewals,
  getContractBurnDown,
  getContractInvoices,
  getContractPurchaseOrders,
} from "../api";
import { fmtUSD, fmtPct, fmtDate, fmtDays, fmtInt } from "../format";
import type {
  ContractRow,
  ContractBurnDown,
  ContractInvoiceRow,
  ContractPORow,
} from "../types";

type DetailTab = "summary" | "invoices" | "pos";

export function Contracts({ searchQuery = "" }: { searchQuery?: string }) {
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [renewals, setRenewals] = useState<ContractRow[]>([]);
  const [view, setView] = useState<"active" | "renewals">("active");
  const [selected, setSelected] = useState<string | null>(null);
  const [burnDown, setBurnDown] = useState<ContractBurnDown | null>(null);
  const [burnDownError, setBurnDownError] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<ContractInvoiceRow[] | null>(null);
  const [pos, setPOs] = useState<ContractPORow[] | null>(null);
  const [tab, setTab] = useState<DetailTab>("summary");
  const [tabLoading, setTabLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getContracts(), getRenewals()])
      .then(([c, r]) => { setContracts(c); setRenewals(r); })
      .finally(() => setLoading(false));
  }, []);

  // Summary tab loads burn-down. Other tabs lazy-load only when first opened
  // to keep round-trips cheap if the user only wants the chart. All .catch
  // handlers log to console so silent 500s surface in DevTools instead of
  // hiding behind an indefinite "Loading…" indicator.
  useEffect(() => {
    if (!selected) {
      setBurnDown(null);
      setBurnDownError(null);
      setInvoices(null);
      setPOs(null);
      setTab("summary");
      return;
    }
    setBurnDown(null);
    setBurnDownError(null);
    setInvoices(null);
    setPOs(null);
    setTab("summary");
    getContractBurnDown(selected)
      .then(setBurnDown)
      .catch((e) => {
        console.error("burn-down fetch failed", e);
        setBurnDownError(e instanceof Error ? e.message : String(e));
      });
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    if (tab === "invoices" && invoices === null) {
      setTabLoading(true);
      getContractInvoices(selected)
        .then(setInvoices)
        .catch((e) => {
          console.error("contract invoices fetch failed", e);
          setInvoices([]);
        })
        .finally(() => setTabLoading(false));
    } else if (tab === "pos" && pos === null) {
      setTabLoading(true);
      getContractPurchaseOrders(selected)
        .then(setPOs)
        .catch((e) => {
          console.error("contract POs fetch failed", e);
          setPOs([]);
        })
        .finally(() => setTabLoading(false));
    }
  }, [tab, selected, invoices, pos]);

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

  const selectedRow = useMemo(
    () => baseRows.find((c) => c.contract_workspace_id === selected) ?? null,
    [baseRows, selected],
  );

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
                <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {[
                        { label: "Supplier" },
                        { label: "Type" },
                        { label: "Title" },
                        { label: "Committed", tooltip: METRICS.contractCommitted },
                        { label: "Consumed", tooltip: METRICS.pctConsumed },
                        { label: "Expires", tooltip: METRICS.expires },
                      ].map((h) => (
                        <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                          <HeaderLabel label={h.label} tooltip={h.tooltip} />
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
                            <MetricTooltip content={METRICS.contractTypePill} hoverOnly>
                              <Pill active={false}>{c.contract_type}</Pill>
                            </MetricTooltip>
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

          {/* Drilldown panel — tabbed: Summary | Linked Invoices | Linked POs */}
          {selected && (
            <Card accent="var(--db-lava-600)">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                marginBottom: "var(--space-3)" }}>
                <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700 }}>
                  {burnDown?.title ?? selectedRow?.title ?? selected}
                </h3>
                <button
                  onClick={() => setSelected(null)}
                  aria-label="Close panel"
                  style={{ background: "none", border: "none", cursor: "pointer",
                    color: "var(--fg-3)", fontSize: 18, lineHeight: 1, padding: 0 }}
                >
                  ×
                </button>
              </div>

              {/* Meta block — always visible above the tabs */}
              {selectedRow && (
                <div style={{ marginBottom: "var(--space-3)", display: "grid",
                  gridTemplateColumns: "1fr 1fr", rowGap: "var(--space-1)", columnGap: "var(--space-3)",
                  fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>
                  <div>Supplier: <span style={{ color: "var(--fg-1)" }}>{selectedRow.supplier_name ?? selectedRow.supplier_id}</span></div>
                  <div>
                    <HeaderLabel label="Type" tooltip={METRICS.contractTypePill} />:{" "}
                    <span style={{ color: "var(--fg-1)" }}>{selectedRow.contract_type}</span>
                  </div>
                  <div>Region: <span style={{ color: "var(--fg-1)" }}>{selectedRow.region ?? "—"}</span></div>
                  <div>
                    <HeaderLabel label="Expires" tooltip={METRICS.expires} />:{" "}
                    <span style={{ color: "var(--fg-1)" }}>{fmtDays(selectedRow.days_to_expiration)}</span>
                  </div>
                  <div>
                    <HeaderLabel label="Committed" tooltip={METRICS.contractCommitted} />:{" "}
                    <span style={{ color: "var(--fg-1)" }}>{fmtUSD(selectedRow.total_committed_spend, true)}</span>
                  </div>
                  <div>
                    <HeaderLabel label="Consumed" tooltip={METRICS.pctConsumed} />:{" "}
                    <span style={{ color: "var(--fg-1)" }}>{fmtPct(selectedRow.pct_consumed)}</span>
                  </div>
                </div>
              )}

              <div style={{ marginBottom: "var(--space-3)" }}>
                <SegSelect
                  options={[
                    { label: "Summary", value: "summary" },
                    { label: "Invoices", value: "invoices" },
                    { label: "POs", value: "pos" },
                  ]}
                  value={tab}
                  onChange={(v) => setTab(v as DetailTab)}
                />
              </div>

              {tab === "summary" && (
                burnDownError ? (
                  <div style={{ padding: "var(--space-5) 0", textAlign: "center",
                    color: "var(--danger)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
                    Failed to load burn-down.
                    <div style={{ marginTop: "var(--space-1)", color: "var(--fg-3)", fontSize: 11 }}>
                      {burnDownError}
                    </div>
                  </div>
                ) : burnDown ? (
                  burnDown.points.length === 0 ? (
                    <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                      No paid invoices in this contract's window yet.
                    </div>
                  ) : (
                    <>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)",
                        display: "flex", alignItems: "center", gap: 4 }}>
                        Burn-Down (contract-scoped)
                        <MetricTooltip content={METRICS.burnDown} placement="bottom-right" />
                      </div>
                      <BurnDownChart
                        points={burnDown.points}
                        committedSpend={burnDown.total_committed_spend ?? undefined}
                        width={360}
                        height={200}
                      />
                    </>
                  )
                ) : (
                  <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                    Loading burn-down…
                  </div>
                )
              )}

              {tab === "invoices" && (
                <DrilldownTable
                  loading={tabLoading || invoices === null}
                  empty="No paid invoices found inside this contract window."
                  columns={[
                    "Date",
                    "Amount",
                    "Category",
                    { label: "Status", tooltip: METRICS.paymentStatusPaid },
                  ]}
                  rows={(invoices ?? []).map((i) => [
                    fmtDate(i.invoice_date),
                    fmtUSD(i.amount, true),
                    i.true_category_primary ?? "—",
                    i.payment_status ?? "—",
                  ])}
                />
              )}

              {tab === "pos" && (
                <DrilldownTable
                  loading={tabLoading || pos === null}
                  empty="No POs found for this supplier inside the contract window."
                  columns={["PO #", "Line", "Amount", "Category"]}
                  rows={(pos ?? []).map((p) => [
                    p.po_number,
                    fmtInt(p.po_line_num),
                    fmtUSD(p.extended_amount, true),
                    p.true_category_primary ?? "—",
                  ])}
                />
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// Compact two-column drilldown table used by the Invoices and POs tabs.
// Pulled into its own component so the column layout / mono styling matches
// across both tabs and stays consistent with the global table convention.
// Columns can be plain strings, OR { label, tooltip } objects when the column
// header needs a metric-definition tooltip (e.g. payment_status).
type DrilldownColumn = string | { label: string; tooltip?: import("../components/MetricTooltip").MetricTooltipContent };

function DrilldownTable({
  loading,
  empty,
  columns,
  rows,
}: {
  loading: boolean;
  empty: string;
  columns: DrilldownColumn[];
  rows: (string | number)[][];
}) {
  if (loading) {
    return (
      <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
        Loading…
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
        {empty}
      </div>
    );
  }
  return (
    <div style={{ maxHeight: 260, overflowY: "auto", overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {columns.map((c) => {
              const label = typeof c === "string" ? c : c.label;
              const tooltip = typeof c === "string" ? undefined : c.tooltip;
              return (
                <th
                  key={label}
                  style={{
                    padding: "var(--space-2)",
                    textAlign: "left",
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    color: "var(--fg-3)",
                    fontWeight: 500,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    position: "sticky",
                    top: 0,
                    background: "var(--bg)",
                  }}
                >
                  <HeaderLabel label={label} tooltip={tooltip} />
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
              {r.map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    padding: "var(--space-2)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--fg-1)",
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
