"""Lakebase Postgres connection — per-request OBO auth, lazy DDL.

Uses the same OBO pattern as db.py: every connection runs as the logged-in
user. No shared pool; each request opens a fresh psycopg3 connection using
the caller's Databricks OAuth token to generate a Lakebase credential.

DDL is run lazily on the first user request (not at startup) so it always
executes with a real user's OBO token. The app's service principal does not
need direct access to the Lakebase instance.
"""

from __future__ import annotations

import asyncio
import logging

import psycopg
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .auth import CallerIdentity
from .config import get_settings

log = logging.getLogger("sourcing_portal.lakebase")

# Set to True once host is configured; DDL is run lazily on first use.
_lakebase_configured: bool = False
_ddl_done: bool = False
_ddl_lock = asyncio.Lock()

DDL = """
CREATE TABLE IF NOT EXISTS chatbot_sessions (
    session_id    TEXT PRIMARY KEY,
    user_email    TEXT NOT NULL,
    title         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chatbot_messages (
    message_id    TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES chatbot_sessions(session_id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content       TEXT NOT NULL,
    tool_calls    JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chatbot_messages_session
    ON chatbot_messages (session_id, created_at);

CREATE TABLE IF NOT EXISTS savings_avoidance_entries (
    entry_id         TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL DEFAULT 'manual',
    source_id        TEXT,
    segment_code     TEXT,
    fiscal_year      INTEGER NOT NULL,
    fiscal_quarter   INTEGER NOT NULL,
    category_primary TEXT,
    supplier_id      TEXT,
    supplier_name    TEXT,
    savings_amount_usd NUMERIC(18,2) NOT NULL,
    baseline_context TEXT,
    notes            TEXT,
    attested_by      TEXT NOT NULL,
    attested_at      TIMESTAMPTZ DEFAULT NOW(),
    approved         BOOLEAN DEFAULT FALSE
);

-- Idempotent column adds for the approval workflow. Older deployments may
-- have the table without these columns; ADD COLUMN IF NOT EXISTS makes the
-- DDL safe to re-run on each startup.
ALTER TABLE savings_avoidance_entries
    ADD COLUMN IF NOT EXISTS approved_by       TEXT,
    ADD COLUMN IF NOT EXISTS approved_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejected_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rejection_reason  TEXT;

-- Unified savings register: one ledger for every logged saving (cost reduction
-- OR cost avoidance), tied to a sourcing event or contract, with a two-step
-- submit → attest workflow. Replaces the split reductions/avoidance model.
CREATE TABLE IF NOT EXISTS savings_register (
    record_id            TEXT PRIMARY KEY,
    artifact_type        TEXT NOT NULL,            -- 'sourcing_event' | 'contract'
    artifact_id          TEXT NOT NULL,
    artifact_title       TEXT,
    savings_class        TEXT NOT NULL,            -- 'reduction' | 'avoidance'
    savings_type         TEXT NOT NULL,            -- taxonomy key (see cost_savings.SAVINGS_TYPES)
    supplier_id          TEXT,
    supplier_name        TEXT,
    segment_code         TEXT,
    fiscal_year          INTEGER NOT NULL,
    fiscal_quarter       INTEGER NOT NULL,
    baseline_amount_usd  NUMERIC(18,2),
    realized_amount_usd  NUMERIC(18,2),
    savings_amount_usd   NUMERIC(18,2) NOT NULL,
    baseline_context     TEXT,
    notes                TEXT,
    submitted_by         TEXT NOT NULL,
    submitted_at         TIMESTAMPTZ DEFAULT NOW(),
    status               TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'attested' | 'rejected'
    attested_by          TEXT,
    attested_at          TIMESTAMPTZ,
    rejection_reason     TEXT
);

CREATE INDEX IF NOT EXISTS idx_savings_register_status ON savings_register (status);

-- Contracting-workflow kickoffs initiated from a contract's renewal-risk banner.
-- One row per contract (the latest workflow) so re-opening a contract recalls
-- the agentic action that was already triggered against it.
CREATE TABLE IF NOT EXISTS contract_workflows (
    contract_workspace_id TEXT PRIMARY KEY,
    workflow_id           TEXT NOT NULL,
    workflow_kind         TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'initiated',
    supplier_name         TEXT,
    contract_title        TEXT,
    routed_to             TEXT,
    message               TEXT NOT NULL,
    initiated_by          TEXT NOT NULL,
    initiated_at          TIMESTAMPTZ DEFAULT NOW()
);
"""


def _conninfo(caller: CallerIdentity) -> str:
    """Build a Lakebase conninfo, preferring the app service principal but
    falling back to the calling user (OBO).

    Identity → Postgres role (postgres_role) → conninfo `user`:
      - SP path: if the Apps runtime exposes the SP's OAuth creds
        (DATABRICKS_CLIENT_ID/SECRET), connect as the SP — its Lakebase role's
        postgres_role is the client id.
      - OBO fallback: this app runtime did NOT expose SP M2M creds to the SDK
        (bare WorkspaceClient() can't auth), so use the caller's forwarded OBO
        token; their postgres_role is their email. Requires the user to have a
        Lakebase role + the `postgres` user_api_scope.

    Either way, a short-lived credential is minted per request (auto-rotation),
    and human attribution (submitted_by/attested_by) is recorded separately from
    caller.email at the app layer.
    """
    import os
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config

    s = get_settings()
    client_id = os.getenv("DATABRICKS_CLIENT_ID")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET")
    if client_id and client_secret:
        w = WorkspaceClient(config=Config(
            host=s.databricks_host, client_id=client_id, client_secret=client_secret,
        ))
        pg_user = client_id
    else:
        if caller.is_anonymous:
            raise RuntimeError("Lakebase requires an authenticated caller (no SP creds available).")
        w = WorkspaceClient(config=Config(
            host=s.databricks_host, token=caller.access_token,
        ))
        pg_user = caller.email
    cred = w.postgres.generate_database_credential(endpoint=s.lakebase_endpoint)
    return (
        f"host={s.lakebase_host} "
        f"port={s.lakebase_port} "
        f"dbname={s.lakebase_database} "
        f"user={pg_user} "
        f"password={cred.token} "
        f"sslmode=require"
    )


async def init_pool() -> None:
    """Mark Lakebase as configured if LAKEBASE_HOST is set. No connection attempt."""
    global _lakebase_configured
    settings = get_settings()
    if not settings.lakebase_host:
        log.warning(
            "LAKEBASE_HOST not configured — Lakebase features (chatbot history, "
            "cost-avoidance ledger) will be unavailable."
        )
        return
    _lakebase_configured = True
    log.info(
        "Lakebase configured (%s, endpoint: %s) — DDL will run on first user request.",
        settings.lakebase_host,
        settings.lakebase_endpoint,
    )


async def close_pool() -> None:
    global _lakebase_configured, _ddl_done
    _lakebase_configured = False
    _ddl_done = False


async def _ensure_ddl(caller: CallerIdentity) -> None:
    """Run DDL once on the first request (lazy init)."""
    global _ddl_done
    if _ddl_done:
        return
    async with _ddl_lock:
        if _ddl_done:
            return
        conninfo = await asyncio.to_thread(_conninfo, caller)
        async with await psycopg.AsyncConnection.connect(conninfo) as conn:
            await conn.execute(DDL)
        _ddl_done = True
        settings = get_settings()
        log.info("Lakebase DDL applied — pool ready (%s/%s)", settings.lakebase_host, settings.lakebase_database)


@asynccontextmanager
async def db_conn(caller: CallerIdentity) -> AsyncIterator[psycopg.AsyncConnection]:
    """Open a per-request Lakebase connection (SP if its creds are available,
    else OBO as the caller — see _conninfo)."""
    if not _lakebase_configured:
        raise RuntimeError(
            "Lakebase not configured. Set LAKEBASE_HOST in app.yaml."
        )
    if caller.is_anonymous:
        raise RuntimeError(
            "Lakebase requires an authenticated caller — not available in local "
            "anonymous dev."
        )
    await _ensure_ddl(caller)
    conninfo = await asyncio.to_thread(_conninfo, caller)
    async with await psycopg.AsyncConnection.connect(conninfo) as conn:
        yield conn
