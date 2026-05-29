# 2026-05-27 (late PM) — Chatbot UX polish

Two paired chatbot iterations driven by live demo feedback (raw JSON in tool cards + "feels frozen on send + slow"). Final deployment `01f159e1011f130ab211613e306e37a6` (15:31:07Z).

## Issue 6 — `ask_genie` tool card showed raw args JSON + "0 rows" for queries that returned data
Two independent bugs:
1. **Args JSON is redundant noise** — for `ask_genie` it's literally the user's prompt already shown above. Replaced the raw `<pre>{JSON.stringify(...)}</pre>` with a `<ToolArgs>` helper: `ask_genie` shows a single grey `Question: …` line; other tools render an inline mono key-value strip.
2. **"SQL · 0 rows" was a lie** — backend computed `row_count` from the message attachment, but Genie's attachment carries only the SQL definition; rows live behind a separate `/query-result` endpoint. Added a second Genie API call in `run_genie_query` after status COMPLETED; probes `manifest.total_row_count` and `result.data_array`; falls back to `null` (renders "rows pending") instead of `0`.

## Issue 7 — No "thinking" indicator + slow to respond
- **Indicator gap** — the prior `"Running…"` indicator had a `toolCards.length > 0` guard that hid it during the 5–15s window between Send and the first `tool_start`. Replaced with an always-on "Helios is thinking…" bubble (3-dot pulse via existing `home-pulse` keyframes); renames to "ran 1 tool…" once a tool fires. New `ThinkingDots` component.
- **Genie polling overhead** — flat 2s sleep per status check replaced with backoff `[0.5,0.5,0.5,0.5,1.0,1.0,1.0,1.0,2.0]` (last repeats), max 60 attempts (~90s budget preserved). Saves 1–3s on typical queries.

## Deferred (lower ROI than effort)
- FMAPI token streaming (word-by-word for non-Genie prompts; ~2h, medium SSE-parsing risk).
- Orchestration model swap (Llama 3.3 70B → Haiku / 8B Llama; 5–10× faster but may regress tool selection).
- Backgrounding the `/query-result` call (~0.5–1s, added complexity).
