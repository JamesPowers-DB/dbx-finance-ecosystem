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
"""


def _get_obo_conninfo(caller: CallerIdentity) -> str:
    """Build conninfo using the calling user's OBO token.

    Uses an explicit Config object so the SDK does not fall back to env vars
    (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET) that the Apps runtime
    injects for the SP — those would conflict with the OBO token and cause
    'more than one authorization method' errors.
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config

    settings = get_settings()
    w = WorkspaceClient(config=Config(
        host=settings.databricks_host,
        token=caller.access_token,
    ))
    me = w.current_user.me()
    cred = w.postgres.generate_database_credential(
        endpoint=settings.lakebase_endpoint
    )
    return (
        f"host={settings.lakebase_host} "
        f"port={settings.lakebase_port} "
        f"dbname={settings.lakebase_database} "
        f"user={me.user_name} "
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
    """Run DDL once on the first authenticated user request (lazy init)."""
    global _ddl_done
    if _ddl_done:
        return
    async with _ddl_lock:
        if _ddl_done:
            return
        conninfo = await asyncio.to_thread(_get_obo_conninfo, caller)
        async with await psycopg.AsyncConnection.connect(conninfo) as conn:
            await conn.execute(DDL)
        _ddl_done = True
        settings = get_settings()
        log.info("Lakebase DDL applied — pool ready (%s/%s)", settings.lakebase_host, settings.lakebase_database)


@asynccontextmanager
async def db_conn(caller: CallerIdentity) -> AsyncIterator[psycopg.AsyncConnection]:
    """Open a per-request Lakebase connection using the caller's OBO token."""
    if not _lakebase_configured:
        raise RuntimeError(
            "Lakebase not configured. Set LAKEBASE_HOST in app.yaml."
        )
    if caller.is_anonymous:
        raise RuntimeError(
            "Lakebase writes require a real OBO token — anonymous mode not supported."
        )
    await _ensure_ddl(caller)
    conninfo = await asyncio.to_thread(_get_obo_conninfo, caller)
    async with await psycopg.AsyncConnection.connect(conninfo) as conn:
        yield conn
