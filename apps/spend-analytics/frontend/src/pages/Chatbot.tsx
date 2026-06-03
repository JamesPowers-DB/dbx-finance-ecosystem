import React, { useEffect, useRef, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { Icon } from "../components/Icon";
import { PrimaryBtn } from "../components/Buttons";
import { Markdown } from "../components/Markdown";
import { createSession, getSessions, deleteSession, getMessages, streamChatMessage, genieeFeedback } from "../api";
import type { ChatMessage, ChatSession } from "../types";

interface SseEvent {
  type: string;
  text?: string;
  name?: string;
  args?: unknown;
  result?: string;
  message?: string;
}

// One logged step: the tool name + its raw JSON result (for Genie we surface SQL).
interface Step {
  name: string;
  result?: string;
}

interface GenieInfo {
  sql?: string;
  row_count?: number | null;
  conv_id?: string;
  msg_id?: string;
  space_id?: string;
}

// Friendly, present-tense labels for the activity trace.
const TOOL_LABEL: Record<string, string> = {
  find_suppliers: "Finding suppliers",
  supplier_profile: "Pulling supplier profile",
  get_active_contract: "Checking active contracts",
  price_history: "Reviewing price history",
  expiring_contracts: "Checking contracts",
  savings_summary: "Summarizing savings",
  submit_pr: "Submitting request",
  ask_genie: "Asking Genie",
};
const toolLabel = (n?: string) => (n && TOOL_LABEL[n]) || n || "Working";

function parseGenie(result?: string): GenieInfo | null {
  if (!result) return null;
  try {
    const p = JSON.parse(result);
    if (!p.sql) return null;
    return { sql: p.sql, row_count: p.row_count, conv_id: p.conv_id, msg_id: p.msg_id, space_id: p.space_id };
  } catch {
    return null;
  }
}

const EXAMPLE_PROMPTS = [
  "Help me find a supplier for industrial sensors",
  "Submit a PR for 50 monitor mounts at $85 each",
  "Which contracts are expiring soon and haven't been used?",
  "What were our cost savings last quarter?",
];

export function Chatbot() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamBuf, setStreamBuf] = useState("");
  const [liveSteps, setLiveSteps] = useState<Step[]>([]);
  const [feedbackSent, setFeedbackSent] = useState<Record<string, "THUMBS_UP" | "THUMBS_DOWN">>({});
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const centerInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { getSessions().then(setSessions).catch(() => setSessions([])); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streamBuf, liveSteps]);

  function sendFeedback(g: GenieInfo, rating: "THUMBS_UP" | "THUMBS_DOWN") {
    if (!g.conv_id || !g.msg_id || !g.space_id) return;
    const key = `${g.conv_id}:${g.msg_id}`;
    genieeFeedback(g.conv_id, g.msg_id, g.space_id, rating).catch(() => {});
    setFeedbackSent((p) => ({ ...p, [key]: rating }));
  }

  async function startSession(initialTitle = "New conversation"): Promise<ChatSession> {
    const s = await createSession({ title: initialTitle });
    setSessions((prev) => [s, ...prev]);
    setActiveSession(s);
    setMessages([]); setError(null); setStreamBuf(""); setLiveSteps([]);
    setTimeout(() => inputRef.current?.focus(), 50);
    return s;
  }

  async function removeSession(s: ChatSession, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await deleteSession(s.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete conversation");
      return;
    }
    setSessions((prev) => prev.filter((x) => x.session_id !== s.session_id));
    if (activeSession?.session_id === s.session_id) {
      setActiveSession(null); setMessages([]); setStreamBuf(""); setLiveSteps([]); setError(null);
    }
  }

  async function selectSession(s: ChatSession) {
    setActiveSession(s); setError(null); setStreamBuf(""); setLiveSteps([]);
    const msgs = await getMessages(s.session_id).catch(() => []);
    setMessages(msgs);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function sendMessage(session: ChatSession, text: string) {
    if (!text.trim() || streaming) return;
    setStreaming(true); setStreamBuf(""); setLiveSteps([]); setError(null);

    const userMsg: ChatMessage = {
      message_id: crypto.randomUUID(), session_id: session.session_id,
      role: "user", content: text, tool_calls: null, created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setSessions((prev) => prev.map((s) =>
      s.session_id === session.session_id && (s.title === "New conversation" || !s.title)
        ? { ...s, title: text.slice(0, 48) } : s));

    let assistantContent = "";
    const steps: Step[] = [];
    try {
      for await (const event of streamChatMessage(session.session_id, text)) {
        const ev = event as SseEvent;
        if (ev.type === "content" && ev.text) {
          assistantContent += ev.text;
          setStreamBuf(assistantContent);
        } else if (ev.type === "tool_start") {
          steps.push({ name: ev.name ?? "" });
          setLiveSteps([...steps]);
        } else if (ev.type === "tool_result") {
          // attach the result to the most recent matching step
          for (let i = steps.length - 1; i >= 0; i--) {
            if (steps[i].name === ev.name && steps[i].result === undefined) {
              steps[i].result = ev.result;
              break;
            }
          }
          setLiveSteps([...steps]);
        } else if (ev.type === "error") {
          setError(ev.message ?? "Chatbot error");
        } else if (ev.type === "done") {
          break;
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setStreaming(false);
      if (assistantContent || steps.length) {
        setMessages((prev) => [...prev, {
          message_id: crypto.randomUUID(), session_id: session.session_id,
          role: "assistant", content: assistantContent,
          tool_calls: steps.length ? steps : null,
          created_at: new Date().toISOString(),
        }]);
      }
      setStreamBuf(""); setLiveSteps([]);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  async function send() {
    if (!input.trim() || streaming) return;
    const text = input.trim();
    setInput("");
    let session = activeSession;
    if (!session) session = await startSession(text.slice(0, 48));
    await sendMessage(session, text);
  }

  return (
    <div style={{ position: "relative", display: "flex", flex: 1, overflow: "hidden" }}>
      <BlobBg />

      {/* Session sidebar */}
      <div style={{ width: 220, borderRight: "1px solid var(--border)", display: "flex",
        flexDirection: "column", background: "var(--bg-canvas)", zIndex: 1, flexShrink: 0 }}>
        <div style={{ padding: "var(--space-4)", borderBottom: "1px solid var(--border)" }}>
          <PrimaryBtn
            onClick={() => { setActiveSession(null); setMessages([]); setInput(""); setTimeout(() => centerInputRef.current?.focus(), 50); }}
            style={{ width: "100%", justifyContent: "center" }}
          >+ New Chat</PrimaryBtn>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {sessions.map((s) => {
            const active = activeSession?.session_id === s.session_id;
            return (
              <div key={s.session_id} className="chat-session-row"
                style={{ display: "flex", alignItems: "center", borderBottom: "1px solid var(--border)",
                  background: active ? "var(--bg-subtle)" : "transparent" }}>
                <button onClick={() => selectSession(s)}
                  style={{ flex: 1, minWidth: 0, padding: "var(--space-3) var(--space-4)", textAlign: "left",
                    fontSize: 13, background: "transparent", border: "none", color: "var(--fg-1)",
                    cursor: "pointer", fontFamily: "var(--font-sans)" }}>
                  <div style={{ fontWeight: 500, marginBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {s.title ?? "New conversation"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>
                    {s.updated_at ? s.updated_at.slice(0, 10) : ""}
                  </div>
                </button>
                <button onClick={(e) => removeSession(s, e)} aria-label="Delete conversation" title="Delete conversation"
                  style={{ flexShrink: 0, padding: "0 var(--space-3)", alignSelf: "stretch", background: "none",
                    border: "none", cursor: "pointer", color: "var(--fg-3)", fontSize: 16, lineHeight: 1 }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = "var(--danger)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = "var(--fg-3)"; }}>
                  ×
                </button>
              </div>
            );
          })}
        </div>
        <PoweredByGenie />
      </div>

      {/* Main chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", zIndex: 1 }}>
        {!activeSession ? (
          /* ── LANDING ── */
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column", gap: "var(--space-5)", padding: "var(--space-8) var(--space-6)", overflowY: "auto" }}>
            <img src="/ds/assets/databricks-symbol-color.svg" style={{ width: 44, height: 44, opacity: 0.8 }} alt="" />
            <div style={{ textAlign: "center" }}>
              <h2 style={{ fontSize: "var(--fs-h3)", fontWeight: 700, letterSpacing: "var(--tracking-tight)",
                color: "var(--fg-1)", marginBottom: "var(--space-2)" }}>
                Procurement Assistant
              </h2>
              <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", margin: 0 }}>
                Find suppliers, submit purchase requests, check contracts, and explore spend.
              </p>
            </div>
            <div style={{ width: "100%", maxWidth: 600, display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
              <input ref={centerInputRef} autoFocus value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Ask anything about suppliers, contracts, or spend…"
                style={{ flex: 1, fontSize: "var(--fs-body-sm)", padding: "var(--space-3) var(--space-4)" }} />
              <PrimaryBtn onClick={send} disabled={!input.trim()}>
                <Icon name="send" size={14} color="currentColor" /> Send
              </PrimaryBtn>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)", width: "100%", maxWidth: 600 }}>
              {EXAMPLE_PROMPTS.map((ex) => (
                <button key={ex} onClick={() => { setInput(ex); centerInputRef.current?.focus(); }}
                  style={{ padding: "var(--space-3) var(--space-4)", background: "var(--bg-canvas)",
                    border: "1px solid var(--border)", borderRadius: "var(--radius-md)", fontSize: 13,
                    cursor: "pointer", color: "var(--fg-2)", fontFamily: "var(--font-sans)", textAlign: "left",
                    lineHeight: "var(--lh-normal)", transition: "border-color var(--dur-fast), color var(--dur-fast)" }}
                  onMouseEnter={(e) => { const el = e.currentTarget; el.style.borderColor = "var(--db-lava-600)"; el.style.color = "var(--fg-1)"; }}
                  onMouseLeave={(e) => { const el = e.currentTarget; el.style.borderColor = "var(--border)"; el.style.color = "var(--fg-2)"; }}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── ACTIVE SESSION ── */
          <>
            <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-5) var(--space-6)" }}>
              {messages.map((msg) => (
                <div key={msg.message_id} style={{ marginBottom: "var(--space-4)" }}>
                  {/* Actions card sits ABOVE the assistant bubble it produced */}
                  {msg.role === "assistant" && Array.isArray(msg.tool_calls) && (
                    <ActionsCard steps={msg.tool_calls as Step[]} feedbackSent={feedbackSent} onFeedback={sendFeedback} />
                  )}
                  <div style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
                    <div style={{ maxWidth: "72%",
                      background: msg.role === "user" ? "var(--db-lava-600)" : "var(--bg-canvas)",
                      color: msg.role === "user" ? "var(--fg-on-dark)" : "var(--fg-1)",
                      border: msg.role === "user" ? "none" : "1px solid var(--border)",
                      borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)",
                      fontSize: "var(--fs-body-sm)", lineHeight: "var(--lh-normal)",
                      whiteSpace: msg.role === "user" ? "pre-wrap" : "normal" }}>
                      {msg.role === "assistant"
                        ? (msg.content ? <Markdown text={msg.content} /> : (Array.isArray(msg.tool_calls) ? "(done)" : ""))
                        : msg.content}
                    </div>
                  </div>
                </div>
              ))}

              {/* Live: actions card (while running) + streaming answer */}
              {streaming && liveSteps.length > 0 && (
                <ActionsCard steps={liveSteps} feedbackSent={feedbackSent} onFeedback={sendFeedback} live />
              )}

              {streaming && streamBuf && (
                <div style={{ marginBottom: "var(--space-4)", display: "flex", justifyContent: "flex-start" }}>
                  <div style={{ maxWidth: "72%", background: "var(--bg-canvas)", border: "1px solid var(--border)",
                    borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--fs-body-sm)", lineHeight: "var(--lh-normal)", whiteSpace: "pre-wrap" }}>
                    {streamBuf}
                    <span style={{ display: "inline-block", width: 6, height: 14, background: "var(--db-lava-600)",
                      marginLeft: 2, borderRadius: 1, animation: "home-pulse 0.8s ease-in-out infinite" }} />
                  </div>
                </div>
              )}

              {/* Thinking — shows current step until first content token */}
              {streaming && !streamBuf && (
                <div style={{ marginBottom: "var(--space-4)", display: "flex", justifyContent: "flex-start" }}>
                  <div style={{ background: "var(--bg-canvas)", border: "1px solid var(--border)",
                    borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)",
                    display: "inline-flex", alignItems: "center", gap: "var(--space-3)",
                    color: "var(--fg-3)", fontSize: 13, fontFamily: "var(--font-sans)" }}>
                    <ThinkingDots />
                    <span>{liveSteps.length ? `${toolLabel(liveSteps[liveSteps.length - 1].name)}…` : "Thinking…"}</span>
                  </div>
                </div>
              )}

              {error && (
                <div style={{ padding: "var(--space-3)", background: "var(--danger-bg)",
                  border: "1px solid var(--danger)", borderRadius: "var(--radius-sm)", fontSize: 13,
                  color: "var(--danger)", marginBottom: "var(--space-3)" }}>
                  {error}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Bottom input bar */}
            <div style={{ padding: "var(--space-4) var(--space-6)", borderTop: "1px solid var(--border)",
              display: "flex", gap: "var(--space-3)", background: "var(--bg-canvas)", flexShrink: 0 }}>
              <input ref={inputRef} style={{ flex: 1, fontSize: "var(--fs-body-sm)" }}
                placeholder={streaming ? "Waiting for response…" : "Ask anything…"}
                value={input} disabled={streaming}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
              <PrimaryBtn onClick={send} disabled={streaming || !input.trim()}>
                <Icon name="send" size={14} color="currentColor" /> {streaming ? "…" : "Send"}
              </PrimaryBtn>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// One compact card per assistant turn listing the steps taken. For Genie steps
// it surfaces the SQL once + a single 👍/👎. No per-tool expandable widgets.
function ActionsCard({
  steps, feedbackSent, onFeedback, live,
}: {
  steps: Step[];
  feedbackSent: Record<string, "THUMBS_UP" | "THUMBS_DOWN">;
  onFeedback: (g: GenieInfo, r: "THUMBS_UP" | "THUMBS_DOWN") => void;
  live?: boolean;
}) {
  if (!steps?.length) return null;
  return (
    <div style={{ marginBottom: "var(--space-2)" }}>
      <div style={{ maxWidth: 540, border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
        background: "var(--bg-subtle)", padding: "var(--space-2) var(--space-3)" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
          textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "var(--space-1)" }}>
          {live ? "working" : "actions"}
        </div>
        {steps.map((st, i) => {
          const g = st.name === "ask_genie" ? parseGenie(st.result) : null;
          const done = st.result !== undefined;
          return (
            <div key={i} style={{ marginTop: i === 0 ? 0 : "var(--space-1)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <Icon name="lightning" size={12} color={done ? "var(--db-lava-600)" : "var(--fg-3)"} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: done ? "var(--fg-1)" : "var(--fg-3)" }}>
                  {toolLabel(st.name)}
                </span>
              </div>
              {g?.sql && (
                <div style={{ marginTop: "var(--space-1)", marginLeft: 20 }}>
                  <pre style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-2)", margin: 0,
                    overflowX: "auto", whiteSpace: "pre-wrap", background: "var(--bg-canvas)",
                    border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "var(--space-2)" }}>
                    {g.sql}
                  </pre>
                  {g.conv_id && g.msg_id && g.space_id && (() => {
                    const key = `${g.conv_id}:${g.msg_id}`;
                    return (
                      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-1)", alignItems: "center" }}>
                        {(["THUMBS_UP", "THUMBS_DOWN"] as const).map((r) => (
                          <button key={r} disabled={!!feedbackSent[key]} onClick={() => onFeedback(g, r)}
                            style={{ background: feedbackSent[key] === r ? "var(--db-lava-600)" : "var(--bg-canvas)",
                              border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                              cursor: feedbackSent[key] ? "default" : "pointer", padding: "0 6px", fontSize: 13, lineHeight: 1.6 }}>
                            {r === "THUMBS_UP" ? "👍" : "👎"}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PoweredByGenie() {
  return (
    <div style={{ padding: "var(--space-3) var(--space-4)", borderTop: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 6 }}>
      <img src="/ds/assets/databricks-symbol-color.svg" style={{ width: 14, height: 14, opacity: 0.8 }} alt="" />
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.02em" }}>
        Powered by Databricks Genie
      </span>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span aria-label="Thinking" role="status" style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
      {[0, 0.15, 0.3].map((delay, i) => (
        <span key={i} style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%",
          background: "var(--db-lava-600)", animation: "home-pulse 0.9s ease-in-out infinite", animationDelay: `${delay}s` }} />
      ))}
    </span>
  );
}
