import type {
  AvoidanceEntry,
  AvoidanceEntryCreate,
  ChatMessage,
  ChatSession,
  ChatSessionCreate,
  ConfidenceBucket,
  ContractBurnDown,
  ContractRow,
  CostReductionRow,
  DisagreementRow,
  KpiResponse,
  LabelingCoverageRow,
  MeResponse,
  ModelHistoryRow,
  RenegotiationTarget,
  SavingsSummaryRow,
  SupplierRow,
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

// ── System ────────────────────────────────────────────────────────────────────
export const getMe = () => j<MeResponse>("/me");
export const getKpis = () => j<KpiResponse>("/kpis");

// ── Contracts ─────────────────────────────────────────────────────────────────
export const getContracts = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return j<ContractRow[]>(`/contracts${qs}`);
};
export const getRenewals = (daysOut?: number) =>
  j<ContractRow[]>(`/contracts/renewals${daysOut ? `?days_out=${daysOut}` : ""}`);
export const getContractBurnDown = (id: string) =>
  j<ContractBurnDown>(`/contracts/${encodeURIComponent(id)}/burn_down`);

// ── Suppliers ─────────────────────────────────────────────────────────────────
export const getSuppliers = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return j<SupplierRow[]>(`/suppliers${qs}`);
};
export const getRenegotiationTargets = () =>
  j<RenegotiationTarget[]>("/suppliers/renegotiation_targets");
export const getSupplierScorecard = (id: string) =>
  j<Record<string, unknown>>(`/suppliers/${encodeURIComponent(id)}/scorecard`);

// ── Cost Savings ──────────────────────────────────────────────────────────────
export const getCostReductions = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return j<CostReductionRow[]>(`/cost_savings/reductions${qs}`);
};
export const getAvoidanceEntries = (fiscalYear?: number) =>
  j<AvoidanceEntry[]>(`/cost_savings/avoidance${fiscalYear ? `?fiscal_year=${fiscalYear}` : ""}`);
export const createAvoidanceEntry = (body: AvoidanceEntryCreate) =>
  post<AvoidanceEntry>("/cost_savings/avoidance", body);
export const getSavingsSummary = () => j<SavingsSummaryRow[]>("/cost_savings/summary");

// ── Chatbot ───────────────────────────────────────────────────────────────────
export const createSession = (body: ChatSessionCreate) =>
  post<ChatSession>("/chat/sessions", body);
export const getSessions = () => j<ChatSession[]>("/chat/sessions");
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

// ── Labeling Monitor ──────────────────────────────────────────────────────────
export const getLabelingCoverage = () =>
  j<LabelingCoverageRow[]>("/labeling/coverage");
export const getConfidenceDistribution = (tier: "primary" | "secondary" = "secondary") =>
  j<ConfidenceBucket[]>(`/labeling/confidence?tier=${tier}`);
export const getDisagreements = (limit = 200) =>
  j<DisagreementRow[]>(`/labeling/disagreements?limit=${limit}`);
export const getModelHistory = () =>
  j<ModelHistoryRow[]>("/labeling/model_history");
