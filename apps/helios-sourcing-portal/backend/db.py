"""Per-request SQL warehouse connection (OBO).

Every UC-touching query opens a fresh databricks-sql-connector connection using
the caller's OAuth access token. No connection pool — auth material is per-user.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

from databricks import sql as dbsql

from .auth import CallerIdentity
from .config import Settings, get_settings


def _http_path(settings: Settings) -> str:
    if settings.warehouse_id:
        return f"/sql/1.0/warehouses/{settings.warehouse_id}"
    raise RuntimeError("DATABRICKS_WAREHOUSE_ID not configured.")


def _server_hostname(settings: Settings) -> str:
    if not settings.databricks_host:
        raise RuntimeError("DATABRICKS_HOST not set.")
    return urlparse(settings.databricks_host).hostname or settings.databricks_host


@contextmanager
def warehouse_connection(caller: CallerIdentity) -> Iterator[Any]:
    if caller.is_anonymous:
        raise RuntimeError(
            "Cannot open a warehouse connection for an anonymous caller. "
            "This route requires a real OBO token — deploy to a workspace or "
            "set DATABRICKS_TOKEN + DATABRICKS_HOST for local testing."
        )
    settings = get_settings()
    conn = dbsql.connect(
        server_hostname=_server_hostname(settings),
        http_path=_http_path(settings),
        access_token=caller.access_token,
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(
    caller: CallerIdentity, sql: str, parameters: list[Any] | None = None
) -> list[dict[str, Any]]:
    with warehouse_connection(caller) as conn, conn.cursor() as cur:
        cur.execute(sql, parameters or [])
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(
    caller: CallerIdentity, sql: str, parameters: list[Any] | None = None
) -> dict[str, Any] | None:
    rows = fetch_all(caller, sql, parameters)
    return rows[0] if rows else None


def execute(
    caller: CallerIdentity, sql: str, parameters: list[Any] | None = None
) -> None:
    """Run a DML statement (INSERT / MERGE) without returning rows."""
    with warehouse_connection(caller) as conn, conn.cursor() as cur:
        cur.execute(sql, parameters or [])
