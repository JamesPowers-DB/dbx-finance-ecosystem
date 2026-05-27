import React, { useEffect, useRef, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Icon } from "../components/Icon";
import { PrimaryBtn } from "../components/Buttons";
import { createSession, getSessions, getMessages, streamChatMessage, genieeFeedback } from "../api";
import type { ChatMessage, ChatSession } from "../types";

interface GenieResult {
  sql?: string;
  // null when the backend couldn't fetch the actual row count (e.g. /query-result
  // call failed); undefined when ask_genie never returned a SQL result at all.
  row_count?: number | null;
  conv_id?: string;
  msg_id?: string;
  space_id?: string;
}

interface SseEvent {
  type: string;
  text?: string;
  name?: string;
  args?: unknown;
  result?: string;
  message?: string;
  genieResult?: GenieResult;
}

const EXAMPLE_PROMPTS = [
  "I need 50 monitor mounts for the Austin office",
  "Who are our top MRO suppliers in the Americas?",
  "What is our total spend by category this year?",
  "Which contracts are expiring in the next 90 days?",
];

export function Chatbot() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamBuf, setStreamBuf] = useState("");
  const [toolCards, setToolCards] = useState<SseEvent[]>([]);
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());
  const [feedbackSent, setFeedbackSent] = useState<Record<number, "THUMBS_UP" | "THUMBS_DOWN">>({});
  const [error, setError] = useState<string | null>(null);

  function toggleTool(i: number) {
    setExpandedTools(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const centerInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSessions().then(setSessions).catch(() => setSessions([]));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamBuf]);

  function focusInput() {
    setTimeout(() => {
      if (activeSession) {
        inputRef.current?.focus();
      } else {
        centerInputRef.current?.focus();
      }
    }, 50);
  }

  async function startSession(initialTitle = "New conversation"): Promise<ChatSession> {
    const s = await createSession({ title: initialTitle });
    setSessions((prev) => [s, ...prev]);
    setActiveSession(s);
    setMessages([]);
    setError(null);
    setStreamBuf("");
    setToolCards([]);
    setTimeout(() => inputRef.current?.focus(), 50);
    return s;
  }

  async function selectSession(s: ChatSession) {
    setActiveSession(s);
    setError(null);
    setStreamBuf("");
    setToolCards([]);
    const msgs = await getMessages(s.session_id).catch(() => []);
    setMessages(msgs);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function sendMessage(session: ChatSession, text: string) {
    if (!text.trim() || streaming) return;
    setStreaming(true);
    setStreamBuf("");
    setToolCards([]);
    setExpandedTools(new Set());
    setFeedbackSent({});
    setError(null);

    const userMsg: ChatMessage = {
      message_id: crypto.randomUUID(),
      session_id: session.session_id,
      role: "user",
      content: text,
      tool_calls: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    setSessions((prev) =>
      prev.map((s) =>
        s.session_id === session.session_id && (s.title === "New conversation" || !s.title)
          ? { ...s, title: text.slice(0, 48) }
          : s,
      ),
    );

    let assistantContent = "";
    try {
      for await (const event of streamChatMessage(session.session_id, text)) {
        const ev = event as SseEvent;
        if (ev.type === "content" && ev.text) {
          assistantContent += ev.text;
          setStreamBuf(assistantContent);
        } else if (ev.type === "tool_start" || ev.type === "tool_result") {
          const enriched = ev as SseEvent;
          if (ev.type === "tool_result" && enriched.name === "ask_genie" && enriched.result) {
            try {
              const parsed = JSON.parse(enriched.result as string);
              enriched.genieResult = {
                sql: parsed.sql,
                row_count: parsed.row_count,
                conv_id: parsed.conv_id,
                msg_id: parsed.msg_id,
                space_id: parsed.space_id,
              };
            } catch { /* ignore malformed result */ }
          }
          setToolCards((prev) => [...prev, enriched]);
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
      if (assistantContent) {
        setMessages((prev) => [...prev, {
          message_id: crypto.randomUUID(),
          session_id: session.session_id,
          role: "assistant",
          content: assistantContent,
          tool_calls: null,
          created_at: new Date().toISOString(),
        }]);
        setStreamBuf("");
      }
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  // Send — auto-creates a session if none exists yet
  async function send() {
    if (!input.trim() || streaming) return;
    const text = input.trim();
    setInput("");

    let session = activeSession;
    if (!session) {
      session = await startSession(text.slice(0, 48));
    }
    await sendMessage(session, text);
  }

  return (
    <div style={{ position: "relative", display: "flex", flex: 1, overflow: "hidden" }}>
      <BlobBg />

      {/* Session sidebar */}
      <div style={{
        width: 220, borderRight: "1px solid var(--border)", display: "flex",
        flexDirection: "column", background: "var(--bg-canvas)", zIndex: 1, flexShrink: 0,
      }}>
        <div style={{ padding: "var(--space-4)", borderBottom: "1px solid var(--border)" }}>
          <PrimaryBtn
            onClick={() => { setActiveSession(null); setMessages([]); setInput(""); setTimeout(() => centerInputRef.current?.focus(), 50); }}
            style={{ width: "100%", justifyContent: "center" }}
          >
            + New Chat
          </PrimaryBtn>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => selectSession(s)}
              style={{
                display: "block", width: "100%", padding: "var(--space-3) var(--space-4)",
                textAlign: "left", fontSize: 13, borderBottom: "1px solid var(--border)",
                background: activeSession?.session_id === s.session_id ? "var(--bg-subtle)" : "transparent",
                color: "var(--fg-1)", cursor: "pointer", fontFamily: "var(--font-sans)",
              }}
            >
              <div style={{ fontWeight: 500, marginBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {s.title ?? "New conversation"}
              </div>
              <div style={{ fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>
                {s.updated_at ? s.updated_at.slice(0, 10) : ""}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", zIndex: 1 }}>

        {!activeSession ? (
          /* ── LANDING STATE: centered hero with inline input above prompts ── */
          <div style={{
            flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column", gap: "var(--space-5)", padding: "var(--space-8) var(--space-6)",
            overflowY: "auto",
          }}>
            <img src="/ds/assets/databricks-symbol-color.svg" style={{ width: 44, height: 44, opacity: 0.8 }} alt="" />
            <div style={{ textAlign: "center" }}>
              <h2 style={{
                fontSize: "var(--fs-h3)", fontWeight: 700, letterSpacing: "var(--tracking-tight)",
                color: "var(--fg-1)", marginBottom: "var(--space-2)",
              }}>
                Helios Procurement Assistant
              </h2>
              <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", margin: 0 }}>
                Ask about spend, find suppliers, check contracts, or submit a purchase request.
              </p>
            </div>

            {/* Centered input row — above the prompts */}
            <div style={{
              width: "100%", maxWidth: 600, display: "flex",
              gap: "var(--space-3)", alignItems: "center",
            }}>
              <input
                ref={centerInputRef}
                autoFocus
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Ask anything about spend, suppliers, or contracts…"
                style={{ flex: 1, fontSize: "var(--fs-body-sm)", padding: "var(--space-3) var(--space-4)" }}
              />
              <PrimaryBtn onClick={send} disabled={!input.trim()}>
                <Icon name="send" size={14} color="currentColor" />
                Send
              </PrimaryBtn>
            </div>

            {/* Prompt tiles — clicking populates the input */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: "var(--space-3)", width: "100%", maxWidth: 600,
            }}>
              {EXAMPLE_PROMPTS.map((ex) => (
                <button
                  key={ex}
                  onClick={() => {
                    setInput(ex);
                    centerInputRef.current?.focus();
                  }}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    background: "var(--bg-canvas)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    fontSize: 13,
                    cursor: "pointer",
                    color: "var(--fg-2)",
                    fontFamily: "var(--font-sans)",
                    textAlign: "left",
                    lineHeight: "var(--lh-normal)",
                    transition: "border-color var(--dur-fast), color var(--dur-fast)",
                  }}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = "var(--db-lava-600)";
                    el.style.color = "var(--fg-1)";
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = "var(--border)";
                    el.style.color = "var(--fg-2)";
                  }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

        ) : (
          /* ── ACTIVE SESSION: message list + bottom input bar ── */
          <>
            <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-5) var(--space-6)" }}>

              {messages.map((msg) => (
                <div key={msg.message_id} style={{ marginBottom: "var(--space-4)", display: "flex",
                  justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
                  <div style={{
                    maxWidth: "72%",
                    background: msg.role === "user" ? "var(--db-lava-600)" : "var(--bg-canvas)",
                    color: msg.role === "user" ? "var(--fg-on-dark)" : "var(--fg-1)",
                    border: msg.role === "user" ? "none" : "1px solid var(--border)",
                    borderRadius: "var(--radius-lg)",
                    padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--fs-body-sm)",
                    lineHeight: "var(--lh-normal)",
                    whiteSpace: "pre-wrap",
                  }}>
                    {msg.content}
                  </div>
                </div>
              ))}

              {/* Tool cards */}
              {toolCards.map((ev, i) => ev.type === "tool_start" && (
                <div key={i} style={{ marginBottom: "var(--space-3)" }}>
                  <Card style={{ maxWidth: 480 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                        <Icon name="lightning" size={14} color="var(--db-lava-600)" />
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: "var(--db-lava-600)" }}>
                          {ev.name}
                        </span>
                      </div>
                      <button
                        onClick={() => toggleTool(i)}
                        title={expandedTools.has(i) ? "Hide args" : "Show args"}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "var(--fg-3)", display: "flex" }}
                      >
                        <Icon name={expandedTools.has(i) ? "chev_d" : "chev_r"} size={14} color="var(--fg-3)" />
                      </button>
                    </div>
                    {expandedTools.has(i) && (
                      <>
                        <ToolArgs name={ev.name} args={ev.args} />
                        {(() => {
                          const resultEv = toolCards[i + 1];
                          const gr = resultEv?.genieResult;
                          if (!gr?.sql) return null;
                          const rowCountLabel =
                            gr.row_count == null
                              ? "rows pending"
                              : gr.row_count === 1
                                ? "1 row"
                                : `${gr.row_count.toLocaleString()} rows`;
                          return (
                            <div style={{ marginTop: "var(--space-3)", borderTop: "1px solid var(--border)", paddingTop: "var(--space-2)" }}>
                              <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: "var(--space-1)" }}>
                                SQL · {rowCountLabel}
                              </div>
                              <pre style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-2)", margin: 0, overflowX: "auto", whiteSpace: "pre-wrap" }}>
                                {gr.sql}
                              </pre>
                              <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)", alignItems: "center" }}>
                                {(["THUMBS_UP", "THUMBS_DOWN"] as const).map(rating => (
                                  <button
                                    key={rating}
                                    disabled={!!feedbackSent[i]}
                                    onClick={() => {
                                      if (!gr.conv_id || !gr.msg_id || !gr.space_id) return;
                                      genieeFeedback(gr.conv_id, gr.msg_id, gr.space_id, rating).catch(() => {});
                                      setFeedbackSent(prev => ({ ...prev, [i]: rating }));
                                    }}
                                    style={{
                                      background: feedbackSent[i] === rating ? "var(--db-lava-600)" : "var(--bg-subtle)",
                                      color: feedbackSent[i] === rating ? "var(--fg-on-dark)" : "var(--fg-2)",
                                      border: "1px solid var(--border)",
                                      borderRadius: "var(--radius-sm)",
                                      cursor: feedbackSent[i] ? "default" : "pointer",
                                      padding: "2px 8px",
                                      fontSize: 16,
                                      fontFamily: "var(--font-sans)",
                                      lineHeight: 1,
                                    }}
                                  >
                                    {rating === "THUMBS_UP" ? "👍" : "👎"}
                                  </button>
                                ))}
                                {feedbackSent[i] && (
                                  <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Feedback sent</span>
                                )}
                              </div>
                            </div>
                          );
                        })()}
                      </>
                    )}
                  </Card>
                </div>
              ))}

              {/* Streaming response */}
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

              {/* Thinking indicator — shown from t=0 (the moment Send fires)
                  until the first content token streams in. Gives the user
                  instant feedback that the request is in flight, including
                  the gap before any tool_start event arrives. */}
              {streaming && !streamBuf && (() => {
                const toolCount = toolCards.filter((t) => t.type === "tool_start").length;
                return (
                  <div style={{ marginBottom: "var(--space-4)", display: "flex", justifyContent: "flex-start" }}>
                    <div style={{
                      background: "var(--bg-canvas)", border: "1px solid var(--border)",
                      borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-4)",
                      display: "inline-flex", alignItems: "center", gap: "var(--space-3)",
                      color: "var(--fg-3)", fontSize: 13, fontFamily: "var(--font-sans)",
                    }}>
                      <ThinkingDots />
                      <span>
                        Helios is thinking
                        {toolCount > 0 && ` — ran ${toolCount} tool${toolCount === 1 ? "" : "s"}`}
                        …
                      </span>
                    </div>
                  </div>
                );
              })()}

              {/* Error */}
              {error && (
                <div style={{ padding: "var(--space-3)", background: "var(--danger-bg)",
                  border: "1px solid var(--danger)", borderRadius: "var(--radius-sm)", fontSize: 13,
                  color: "var(--danger)", marginBottom: "var(--space-3)" }}>
                  {error}
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Bottom input bar — only when session is active */}
            <div style={{ padding: "var(--space-4) var(--space-6)", borderTop: "1px solid var(--border)",
              display: "flex", gap: "var(--space-3)", background: "var(--bg-canvas)", flexShrink: 0 }}>
              <input
                ref={inputRef}
                style={{ flex: 1, fontSize: "var(--fs-body-sm)" }}
                placeholder={streaming ? "Waiting for response…" : "Ask anything…"}
                value={input}
                disabled={streaming}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              />
              <PrimaryBtn onClick={send} disabled={streaming || !input.trim()}>
                <Icon name="send" size={14} color="currentColor" />
                {streaming ? "…" : "Send"}
              </PrimaryBtn>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Animated 3-dot "typing" indicator used in the Thinking bubble. The
// existing `home-pulse` keyframes are defined globally in index.html /
// colors_and_type.css (already used by the streaming-content cursor and
// the home page tile pulse). We stagger the animation-delay per dot so
// they ripple in sequence rather than blink together.
function ThinkingDots() {
  return (
    <span
      aria-label="Thinking"
      role="status"
      style={{ display: "inline-flex", alignItems: "center", gap: 3 }}
    >
      {[0, 0.15, 0.3].map((delay, i) => (
        <span
          key={i}
          style={{
            display: "inline-block",
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "var(--db-lava-600)",
            animation: "home-pulse 0.9s ease-in-out infinite",
            animationDelay: `${delay}s`,
          }}
        />
      ))}
    </span>
  );
}

// Inline args renderer for tool cards. For ask_genie, we surface a single
// "Question: …" line (the args is literally the user's prompt, which already
// appears in the bubble above — no value in showing it as raw JSON). For
// other tools, we render a clean key-value strip in mono — much friendlier
// to a procurement / executive audience than raw JSON.stringify output.
function ToolArgs({ name, args }: { name?: string; args?: unknown }) {
  if (!args || typeof args !== "object") return null;
  const argObj = args as Record<string, unknown>;

  if (name === "ask_genie" && typeof argObj.question === "string") {
    return (
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
        margin: "var(--space-2) 0 0", lineHeight: "var(--lh-normal)",
      }}>
        <span style={{ color: "var(--fg-3)" }}>Question:</span>{" "}
        <span style={{ color: "var(--fg-2)" }}>{argObj.question}</span>
      </div>
    );
  }

  const entries = Object.entries(argObj).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return null;

  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
      margin: "var(--space-2) 0 0", lineHeight: "var(--lh-normal)",
      display: "flex", flexWrap: "wrap", gap: "var(--space-1) var(--space-3)",
    }}>
      {entries.map(([k, v]) => (
        <span key={k}>
          <span style={{ color: "var(--fg-3)" }}>{k}:</span>{" "}
          <span style={{ color: "var(--fg-2)" }}>
            {typeof v === "object" ? JSON.stringify(v) : String(v)}
          </span>
        </span>
      ))}
    </div>
  );
}
