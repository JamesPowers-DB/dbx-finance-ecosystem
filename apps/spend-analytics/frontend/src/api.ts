import type {
  ChatMessage,
  ChatSession,
  ChatSessionCreate,
  ContractBurnDown,
  ContractInvoiceRow,
  ContractPORow,
  ContractRow,
  AnalyticsKpis,
  CompositionDetailRow,
  DateRange,
  KpiResponse,
  LifecycleFunnelRow,
  ManagedStatusResponse,
  MeResponse,
  SavingsRecord,
  SavingsKpis,
  SavingsArtifact,
  SavingsSubmit,
  SpendCompositionRow,
  SpendTrendRow,
  SupplierConcentrationRow,
  TrendGrain,
  SupplierRow,
  SupplierScorecard,
} from "./types";

const API = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function j<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── System ────────────────────────────────────────────────────────────────────
export const getMe = () => j<MeResponse>("/me");
export const getKpis = () => j<KpiResponse>("/kpis");

// ── Contracts ─────────────────────────────────────────────────────────────────
export const getContracts = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return j<ContractRow[]>(`/contracts${qs}`);
};
export const getContractBurnDown = (id: string) =>
  j<ContractBurnDown>(`/contracts/${encodeURIComponent(id)}/burn_down`);
export const getContractInvoices = (id: string, limit = 100) =>
  j<ContractInvoiceRow[]>(`/contracts/${encodeURIComponent(id)}/invoices?limit=${limit}`);
export const getContractPurchaseOrders = (id: string, limit = 100) =>
  j<ContractPORow[]>(`/contracts/${encodeURIComponent(id)}/purchase_orders?limit=${limit}`);

// ── Suppliers ─────────────────────────────────────────────────────────────────
export const getSuppliers = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return j<SupplierRow[]>(`/suppliers${qs}`);
};
export const getSupplierScorecard = (id: string) =>
  j<SupplierScorecard>(`/suppliers/${encodeURIComponent(id)}/scorecard`);

// ── Cost Savings register ─────────────────────────────────────────────────────
export const getSavingsRegister = (params?: { status?: string; savings_class?: string; fiscal_year?: number }) => {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])).toString()
    : "";
  return j<SavingsRecord[]>(`/cost_savings/register${qs}`);
};
export const getSavingsKpis = () => j<SavingsKpis>("/cost_savings/kpis");
export const searchSavingsArtifacts = (q: string, kind?: "sourcing_event" | "contract") =>
  j<SavingsArtifact[]>(`/cost_savings/artifacts?q=${encodeURIComponent(q)}${kind ? `&kind=${kind}` : ""}`);
export const submitSavings = (body: SavingsSubmit) =>
  post<SavingsRecord>("/cost_savings/register", body);
export const attestSavings = (recordId: string) =>
  post<SavingsRecord>(`/cost_savings/register/${encodeURIComponent(recordId)}/attest`, {});
export const rejectSavings = (recordId: string, reason: string) =>
  post<SavingsRecord>(`/cost_savings/register/${encodeURIComponent(recordId)}/reject`, { reason });

// ── Chatbot ───────────────────────────────────────────────────────────────────
export const createSession = (body: ChatSessionCreate) =>
  post<ChatSession>("/chat/sessions", body);
export const getSessions = () => j<ChatSession[]>("/chat/sessions");
export const deleteSession = (sessionId: string) =>
  del<{ ok: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`);
export const getMessages = (sessionId: string) =>
  j<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);

export const genieeFeedback = (
  convId: string,
  msgId: string,
  spaceId: string,
  rating: "THUMBS_UP" | "THUMBS_DOWN",
) =>
  post<{ ok: boolean }>("/chat/genie-feedback", {
    conv_id: convId,
    msg_id: msgId,
    space_id: spaceId,
    rating,
  });

// Note: EventSource is only for GET endpoints; Chatbot.tsx uses streamChatMessage (fetch-based SSE POST).

// Fetch-based SSE POST helper used by Chatbot.tsx
export async function* streamChatMessage(
  sessionId: string,
  content: string,
): AsyncGenerator<{ type: string; [k: string]: unknown }> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.replace(/^data: /, "");
      if (line.trim()) {
        try {
          yield JSON.parse(line) as { type: string; [k: string]: unknown };
        } catch {
          // ignore malformed lines
        }
      }
    }
  }
}

// ── Spend Analytics ─────────────────────────────────────────────────────────────
export const getSpendComposition = (dim: "category" | "segment" | "pr_source" = "category", range: DateRange = "t12m") =>
  j<SpendCompositionRow[]>(`/analytics/spend_composition?dim=${dim}&range=${range}`);
export const getCompositionDetail = (dim: string, value: string, range: DateRange = "t12m", limit = 8) =>
  j<CompositionDetailRow[]>(`/analytics/composition_detail?dim=${dim}&value=${encodeURIComponent(value)}&range=${range}&limit=${limit}`);
export const getManagedStatus = (range: DateRange = "t12m") =>
  j<ManagedStatusResponse>(`/analytics/managed_status?range=${range}`);
export const getSpendTrend = (grain: TrendGrain = "monthly", range: DateRange = "t12m") =>
  j<SpendTrendRow[]>(`/analytics/spend_trend?grain=${grain}&range=${range}`);
export const getSupplierConcentration = (limit = 20, range: DateRange = "t12m") =>
  j<SupplierConcentrationRow[]>(`/analytics/supplier_concentration?limit=${limit}&range=${range}`);
export const getAnalyticsKpis = (range: DateRange = "t12m") =>
  j<AnalyticsKpis>(`/analytics/kpis?range=${range}`);
export const getLifecycleFunnel = (range: DateRange = "t12m") =>
  j<LifecycleFunnelRow[]>(`/analytics/lifecycle_funnel?range=${range}`);
