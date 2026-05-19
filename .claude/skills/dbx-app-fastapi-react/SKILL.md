---
name: dbx-app-fastapi-react
description: Build a Databricks App as FastAPI + Vite/React/TypeScript with on-behalf-of (OBO) auth, the Databricks brand design system (DM Sans / DM Mono, locally hosted), and hand-drawn SVG charts (no Tailwind, no UI library, no chart library). Use when scaffolding a new Databricks App, adding a new app to a bundle, or replicating the OBO + databricks-sql-connector backend + V0 layout primitives (BlobBg / PageHero / Card / AnimatedTileMark). Locks the folder layout, backend wrappers, design tokens, and brand iconography; leaves business routes and UI content flexible.
---

# Databricks App — FastAPI + React + Databricks brand design system

A reference layout for Databricks Apps that pair a FastAPI backend
(per-request OBO auth + `databricks-sql-connector` cursor) with a
Vite/React/TypeScript frontend rendering hand-drawn SVG charts on top of
the Databricks brand design system (DM Sans + DM Mono, full brand
palette, locally hosted under `public/ds/`). No Tailwind, no
MUI/Chakra/Mantine, no Recharts/Victory/D3-rendered DOM.

## When to use this skill

- Adding a new Databricks App under `apps/<app_name>/` in a bundle that
  already uses the `dbx-bundle-medallion-project` layout.
- Building a data-dense internal/demo UI where you want full control
  over typography, spacing, and chart aesthetics — and you want to be
  on-brand with the Databricks visual identity (lava red, navy, oat,
  DM Sans).
- Replicating the per-user OBO pattern (so Unity Catalog row/column
  security enforces against the actual caller, not a service principal)
  with a per-request `databricks-sql-connector` cursor.

If the app is a quick Streamlit/Dash demo, use one of the Python-app
skills instead — this layout earns its complexity once you want the
frontend to look intentional and you want UC permissions to apply
per-user.

---

## Folder layout (locked)

```
apps/<app_name>/
├── app.yaml                  Databricks App runtime config (env lives here, NOT in the bundle)
├── requirements.txt          runtime deps (mirrors backend/pyproject.toml's runtime subset)
├── README.md
├── .gitignore                ignores node_modules, frontend/dist, .venv
├── backend/                  the FastAPI package (NOT `server/`)
│   ├── __init__.py
│   ├── main.py               FastAPI entry — `uvicorn backend.main:app`
│   ├── auth.py               OBO via X-Forwarded-* headers + local-dev fallback
│   ├── config.py             pydantic-settings BaseSettings (env-driven)
│   ├── db.py                 per-request databricks-sql-connector cursor
│   ├── models.py             Pydantic response models
│   ├── pyproject.toml        dev workflow source of truth (uv sync, ruff, pytest)
│   ├── queries/              raw SQL files, loaded by routers (optional but tidy)
│   │   └── <domain>.sql
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── system.py         /api/healthz + /api/me
│   │   └── <domain>.py       one router per domain
│   └── tests/
└── frontend/
    ├── index.html            loads /ds/colors_and_type.css before any JS
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── public/
    │   └── ds/               design system — fonts, tokens, brand SVGs
    │       ├── colors_and_type.css   tokens + @font-face + element defaults
    │       ├── fonts/                dm-sans-*.ttf, dm-mono-*.ttf
    │       └── assets/               databricks-symbol-*.svg, lockup-primary-*.svg
    └── src/
        ├── main.tsx
        ├── App.tsx           shell — Sidebar + state-based page router
        ├── api.ts            typed fetch wrappers
        ├── types.ts          shared interfaces (mirror backend Pydantic 1:1)
        ├── format.ts         fmtUSD, fmtPct, fmtInt, fmtDate, deltaClass
        ├── hooks/
        │   ├── useDebouncedValue.ts
        │   └── useSSEStream.ts        (etc. — domain hooks live here)
        ├── components/
        │   ├── Icon.tsx               named-path SVG table
        │   ├── Sidebar.tsx            left rail with NAV registry + brand mark + user chip
        │   ├── Buttons.tsx            PrimaryBtn, SecondaryBtn, Pill, SegSelect
        │   ├── StatTile.tsx           KPI strip tile
        │   ├── layout/                shared chrome — drop these on every page
        │   │   ├── BlobBg.tsx         drifting blurred radial-gradient blobs
        │   │   ├── PageHero.tsx       eyebrow chip + 36px h1 + subtitle + right slot
        │   │   ├── Card.tsx           bordered white card, optional accent stripe + hover lift
        │   │   └── AnimatedTileMark.tsx   six reusable animated SVG marks
        │   └── <domain>/              per-page component clusters (pricing/, promo/, ...)
        ├── charts/                    hand-drawn SVG charts — d3 math, React renders
        └── pages/
            ├── Home.tsx
            ├── ComingSoon.tsx
            └── <domain>.tsx           one file per top-level page
```

Rules:
- **The backend package is `backend/`** (not `server/`). The uvicorn
  entry is `backend.main:app`.
- **`public/ds/` is the single source of truth for the design system** —
  tokens, fonts, brand SVGs. Never inline a font into `index.html` from
  Google Fonts; never duplicate brand assets.
- **No CSS files under `src/`.** Components style themselves via inline
  `style={{ ... }}` referencing `var(--token)`. The only stylesheet is
  `public/ds/colors_and_type.css`. (See [Design system](#design-system).)
- **Charts live in `src/charts/`**, not under `components/`. Domain
  component clusters live under `components/<domain>/`.
- When the bundle has multiple apps, keep one shared
  `apps/build_frontends.sh` at the apps root that builds all of them.

---

## Backend pattern

### `app.yaml` — Databricks App runtime config

```yaml
# The Apps runtime hard-requires this file at the app source root.
# Env vars MUST live here — the `config.env` block in the DAB Apps
# resource (resources/app.yml) is silently ignored at deploy time.
#
# `valueFrom:` references resource binding names declared in
# resources/app.yml's `resources:` block (warehouse / database /
# serving_endpoint), which DAB substitutes with the live IDs.
# Literal `value:` strings ship as-is — stable per workspace, so
# catalog/schema names live here as literals.

command:
  - "uvicorn"
  - "backend.main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "$DATABRICKS_APP_PORT"

env:
  # Resource bindings — DAB substitutes the live IDs at deploy time.
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: warehouse
  # The lakebase / endpoint bindings give you the DNS host or model URL —
  # but some SDK calls want the *short* instance/endpoint name. When that
  # happens, drop the binding and hardcode the literal short name.
  - name: LAKEBASE_INSTANCE_NAME
    value: "<short-instance-name>"
  - name: DATABRICKS_SERVING_ENDPOINT_NAME
    value: "<endpoint-name>"

  # Catalog / schema literals — stable per workspace.
  - name: DATABRICKS_CATALOG
    value: "<project>_catalog"
  - name: DATABRICKS_SILVER_SCHEMA
    value: "silver"
  - name: DATABRICKS_GOLD_SCHEMA
    value: "gold"
```

Rules:
- **Entry is `uvicorn backend.main:app`** with port `$DATABRICKS_APP_PORT`
  (the Apps runtime injects this). Don't hardcode `8000` — locally you
  set it yourself; in production the runtime owns it.
- **All env vars live in `app.yaml`.** A bundle's
  `resources/app.yml`'s `config.env` is silently ignored at deploy time
  for Databricks Apps. Treat this file as the runtime source of truth.
- **`valueFrom:` for resource IDs, `value:` for literals.** When an SDK
  call needs the short instance name (not the resolved DNS), use a
  literal — accept the duplication.

### `requirements.txt` + `backend/pyproject.toml`

The Apps runtime auto-installs `requirements.txt` at deploy time. It
does NOT recurse into subdirs, so `backend/pyproject.toml` is invisible
to the runtime. Keep `requirements.txt` in sync with the runtime-relevant
subset of `pyproject.toml`.

```
# requirements.txt — runtime deps only
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.7
pydantic-settings>=2.4
databricks-sdk>=0.81
databricks-sql-connector>=3.4
# Optional, add only if the app needs them:
# psycopg[binary,pool]>=3.2     # Lakebase Postgres
# pandas>=2.2                    # tabular post-processing
# numpy>=1.26                    # numerical work
# highspy>=1.7                   # MILP/LP solver
```

```toml
# backend/pyproject.toml — local dev source of truth
[project]
name = "<app>-backend"
requires-python = ">=3.11,<3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "pydantic-settings>=2.4",
  "databricks-sdk>=0.81",
  "databricks-sql-connector>=3.4",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.27", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["."]
include = ["main.py", "auth.py", "config.py", "db.py", "models.py", "routers/**", "queries/**"]
```

### `backend/main.py` — FastAPI entry

```python
"""FastAPI entrypoint.

Run locally:
    cd app/backend
    APP_DEV_ALLOW_ANONYMOUS=1 uv run uvicorn backend.main:app --reload

In Databricks Apps (configured in ../app.yaml):
    uvicorn backend.main:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import CallerIdentity, caller_identity
from .routers import system, <domain1>, <domain2>

log = logging.getLogger("<app>")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open shared resources (DB pools, model warmup) here. Yield, then close.
    yield


app = FastAPI(title="<App Name>", version="0.1.0", lifespan=lifespan)

# CORS — only meaningful in local dev (Vite on :5173 → uvicorn on :8000).
# In production, FastAPI serves the FE bundle from the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers — registration order matters: the SPA fallback below
# catches everything not matched, so API routes must be registered first.
app.include_router(system.router, prefix="/api")
app.include_router(<domain1>.router, prefix="/api")
app.include_router(<domain2>.router, prefix="/api")


# Mount the built React bundle at `/`. The build artifact lives at
# `<app>/frontend/dist/`; resolve it relative to this file so the same
# path works in local dev and inside the Apps runtime.
_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_DIST_DIR, html=True), name="frontend")
else:
    log.warning("frontend bundle not found at %s — root URL will 404", _DIST_DIR)
```

Rules:
- **All API routes share the `/api` prefix.** The `StaticFiles(html=True)`
  mount on `/` catches everything else (including `/` itself, which
  returns `index.html`). Mount it **after** all API routers.
- **`/api/healthz` lives in `routers/system.py`** alongside `/api/me`.
  Both are unauthenticated reads — `healthz` returns `{"status": "ok"}`,
  `me` reads OBO headers and returns the caller identity.
- **The mount uses a path computed from `__file__`** so cwd doesn't
  matter. The deployed runtime runs from the source root; local dev
  often runs from `backend/`.

### `backend/auth.py` — on-behalf-of identity

```python
"""On-behalf-of authentication for Databricks Apps.

Apps injects per-request user identity via these forwarded headers when
the app is configured for user authorization:

    X-Forwarded-Access-Token   OAuth access token for the calling user
    X-Forwarded-Email          User email (governed)
    X-Forwarded-Preferred-Username
    X-Forwarded-User           Workspace identity (numeric SCIM ID)

The token can be used as the bearer for any Databricks API call — UC
SQL, model serving, Lakebase credential issuance — and the call is
performed *as the user*, so UC row/column security applies.

Local dev: when `APP_DEV_ALLOW_ANONYMOUS=1`, fall back to a placeholder
anonymous identity so the FastAPI app boots without the Apps proxy in
front of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import Settings, get_settings


@dataclass(frozen=True)
class CallerIdentity:
    email: str
    user_id: str | None
    access_token: str | None  # None only in local-dev anonymous mode

    @property
    def is_anonymous(self) -> bool:
        return self.access_token is None


def caller_identity(request: Request) -> CallerIdentity:
    settings: Settings = get_settings()
    headers = request.headers

    token = headers.get("x-forwarded-access-token")
    email = (
        headers.get("x-forwarded-email")
        or headers.get("x-forwarded-preferred-username")
    )
    user_id = headers.get("x-forwarded-user")

    if token and email:
        return CallerIdentity(email=email, user_id=user_id, access_token=token)

    if settings.dev_allow_anonymous:
        return CallerIdentity(
            email=settings.dev_user_email, user_id=None, access_token=None
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Missing user identity. This route requires a Databricks Apps "
            "OBO context (X-Forwarded-Access-Token + X-Forwarded-Email)."
        ),
    )
```

Rules:
- **OBO is the default.** Every UC-touching route declares
  `caller: CallerIdentity = Depends(caller_identity)` and uses
  `caller.access_token` for the actual DB call. The service-principal
  pattern (`WorkspaceClient()` with no profile) is reserved for
  background work that doesn't need user identity.
- **`APP_DEV_ALLOW_ANONYMOUS=1` is the local escape hatch.** It returns
  a `CallerIdentity` with `access_token=None`. Any route that opens a
  warehouse connection must guard against `is_anonymous` and raise
  loudly — silent fallback to the SP credential here defeats the
  point of OBO.
- **Required Apps resource setting:** `user_api_scopes: [sql, ...]` in
  `resources/app.yml`. Without it, Apps runs in app-principal mode and
  the `X-Forwarded-*` headers are missing → every OBO route 401s.

### `backend/config.py` — pydantic-settings

```python
"""Runtime configuration loaded from environment variables.

Every variable is supplied by app.yaml in production; local dev falls
back to ~/.databrickscfg + sane defaults so the FastAPI app boots for
smoke tests.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Unity Catalog
    catalog: str = Field(default="<project>", validation_alias="DATABRICKS_CATALOG")
    silver_schema: str = Field(default="silver", validation_alias="DATABRICKS_SILVER_SCHEMA")
    gold_schema: str = Field(default="gold", validation_alias="DATABRICKS_GOLD_SCHEMA")

    # SQL warehouse (OBO target)
    warehouse_id: str = Field(default="", validation_alias="DATABRICKS_WAREHOUSE_ID")
    warehouse_http_path: str = Field(
        default="", validation_alias="DATABRICKS_WAREHOUSE_HTTP_PATH"
    )

    # Workspace host (auto-set inside Apps; set DATABRICKS_HOST locally)
    databricks_host: str = Field(default="", validation_alias="DATABRICKS_HOST")

    # Local-dev affordances
    dev_allow_anonymous: bool = Field(
        default=False, validation_alias="APP_DEV_ALLOW_ANONYMOUS"
    )
    dev_user_email: str = Field(
        default="local-dev@example.com", validation_alias="APP_DEV_USER_EMAIL"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Rules:
- **Use `validation_alias` to keep field names short** (`catalog`)
  while the env var stays loud (`DATABRICKS_CATALOG`).
- **`@lru_cache` on `get_settings()`** so the settings object is built
  once per process. FastAPI Depends will hit the cached version.
- **Compose schema-qualified names in the call site**, e.g.
  `f"{settings.catalog}.{settings.gold_schema}.<table>"`. Don't add
  bespoke `GOLD` constants here — schemas can vary per environment.

### `backend/db.py` — per-request SQL connection

```python
"""Per-request SQL warehouse connection (OBO).

Every UC-touching query opens a fresh `databricks.sql` connection using
the caller's OAuth access token. Connections are short-lived — open
inside a context manager, do the work, close. No global pool, because
the auth material is per-user.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse

from databricks import sql as dbsql

from .auth import CallerIdentity
from .config import Settings, get_settings


def _http_path(settings: Settings) -> str:
    if settings.warehouse_http_path:
        return settings.warehouse_http_path
    if settings.warehouse_id:
        return f"/sql/1.0/warehouses/{settings.warehouse_id}"
    raise RuntimeError("No SQL warehouse configured.")


def _server_hostname(settings: Settings) -> str:
    if not settings.databricks_host:
        raise RuntimeError("DATABRICKS_HOST not set.")
    return urlparse(settings.databricks_host).hostname or settings.databricks_host


@contextmanager
def warehouse_connection(caller: CallerIdentity) -> Iterator[Any]:
    if caller.is_anonymous:
        raise RuntimeError(
            "Cannot open a warehouse connection for an anonymous caller; "
            "this route requires a real OBO token."
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
    caller: CallerIdentity, sql: str, parameters: Iterable[Any] | None = None
) -> list[dict[str, Any]]:
    with warehouse_connection(caller) as conn, conn.cursor() as cur:
        cur.execute(sql, parameters or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(
    caller: CallerIdentity, sql: str, parameters: Iterable[Any] | None = None
) -> dict[str, Any] | None:
    rows = fetch_all(caller, sql, parameters)
    return rows[0] if rows else None
```

Rules:
- **Use `databricks-sql-connector` cursors, not the SDK's Statement
  Execution API.** The connector returns native Python types from the
  cursor (no string-coercion pass needed) and supports parameter binding
  natively. The SDK is fine for non-query Databricks operations.
- **One connection per request.** No pooling — the OAuth token is
  per-user, and warehouses scale by query, not by connection.
- **`fetch_all` returns `list[dict]`** so FastAPI JSON-serializes the
  response directly. For huge result sets, switch to streaming via
  `cur.fetchmany` and a generator.
- **Bound parameters via the DB-API tuple/dict positional**, not
  f-strings. Sort-column allow-lists are still needed for identifiers
  (parameters can't be column names).

### `backend/routers/<domain>.py` — domain router

```python
"""<Domain> endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all

router = APIRouter(prefix="/<domain>", tags=["<domain>"])


@router.get("")
def list_<resource>(
    filter_a: str | None = Query(default=None),
    sort_by: str = Query(default="<default_col>"),
    direction: str = Query(default="desc"),
    limit: int = Query(default=100, le=500),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    allowed_sort = {"col_a", "col_b", "col_c"}
    if sort_by not in allowed_sort:
        raise HTTPException(400, f"sort_by must be one of {sorted(allowed_sort)}")
    if direction.lower() not in {"asc", "desc"}:
        raise HTTPException(400, "direction must be asc or desc")

    s = get_settings()
    wheres: list[str] = []
    params: list[Any] = []
    if filter_a:
        wheres.append("col_a = ?")
        params.append(filter_a)
    where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ""

    sql = f"""
        SELECT col_a, col_b, col_c
        FROM {s.catalog}.{s.gold_schema}.<table>
        {where_sql}
        ORDER BY {sort_by} {direction.upper()}
        LIMIT ?
    """
    params.append(limit)
    return fetch_all(caller, sql, params)
```

Rules:
- **Every route that touches UC takes `caller: CallerIdentity = Depends(caller_identity)`**
  and passes it to `fetch_all` / `fetch_one`. The token flows through to
  the SDK call; UC enforces row/column security against the caller.
- **One DB column per query parameter that filters.** Build `WHERE`
  incrementally so empty filters drop out.
- **Identifier allow-lists for sort_by + fixed direction set.** Use `?`
  placeholders for values (DB-API positional binding).
- **Return raw `list[dict]` or `dict`** for fast iteration; promote to
  Pydantic response models once the schema is stable enough that
  `types.ts` would benefit from a generated mirror.

---

## Frontend pattern

### `package.json`

```json
{
  "name": "<app-name>",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "d3-array": "^3.2.4",
    "d3-scale": "^4.0.2",
    "d3-shape": "^3.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/d3-array": "^3.2.1",
    "@types/d3-scale": "^4.0.8",
    "@types/d3-shape": "^3.1.6",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.1"
  }
}
```

Rules:
- **Only `d3-array`, `d3-scale`, `d3-shape`** — these compute scales and
  path strings. Never import `d3-selection` or anything that touches the
  DOM. React renders SVG; d3 just does math.
- **No Tailwind, no MUI/Chakra/Mantine, no Recharts/Victory.** Charts
  are SVG components in `src/charts/`. Styling is inline `style={{ ... }}`
  referencing CSS variables from `public/ds/colors_and_type.css`.
- **No font CDN deps.** Fonts ship as `.ttf` files under
  `public/ds/fonts/` and are declared with `@font-face` in
  `public/ds/colors_and_type.css`.
- **Add `react-router-dom`** only when the app actually needs URL-driven
  routing. Demo-tier apps often live happily on state-based routing in
  `App.tsx` (see [Sidebar + page switcher](#shell-sidebar--state-based-router)).

### `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production the FastAPI backend serves the built FE assets at the
// same origin — /api/* is same-origin. In dev (`vite` on :5173) we
// proxy /api → http://localhost:8000 so the React app can call FastAPI
// without CORS gymnastics.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
```

`sourcemap: true` is locked — when something blows up in production, the
stack trace needs to map back to readable TS.

### `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

`strict: true` + `noUnusedLocals/Parameters` is non-negotiable.

### `index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title><App Title></title>
    <link rel="icon" type="image/svg+xml" href="/ds/assets/databricks-symbol-color.svg" />
    <link rel="stylesheet" href="/ds/colors_and_type.css" />
    <style>
      html, body, #root { margin: 0; padding: 0; height: 100%; }
      body {
        background: var(--db-oat-light);
        font-family: var(--font-sans);
        color: var(--fg-1);
        overflow: hidden;
      }
      #root { display: flex; height: 100vh; }
      ::-webkit-scrollbar { width: 10px; height: 10px; }
      ::-webkit-scrollbar-thumb { background: var(--db-navy-300); border-radius: 5px; }
      ::-webkit-scrollbar-track { background: transparent; }
      table { font-variant-numeric: tabular-nums; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Rules:
- **Load `/ds/colors_and_type.css` before any JS.** This ships the tokens,
  `@font-face` declarations, and element defaults to the first paint.
- **Brand favicon** points at `/ds/assets/databricks-symbol-color.svg`.
- **The only inline `<style>` block in the project** is this one — a
  micro reset (margin/scrollbar/tabular nums). Everything else flows
  through CSS variables + inline `style={{ ... }}`.

### `src/api.ts` — typed fetch wrappers

```ts
import type { OverviewResponse } from "./types";

const API = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function j<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export const getCurrentUser = () => j<CurrentUser>("/me");
export const fetchOverview = () => j<OverviewResponse>("/overview");

// POST helpers spell out fetch() so the body shape is visible inline.
export async function createSession(body: { page: string; title: string }) {
  const res = await fetch(`${API}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}
```

Rules:
- **One `j<T>()` helper for all GETs.** Don't reach for axios or
  TanStack Query for a demo-scale app.
- **Throw a typed `ApiError`** so pages can branch on `e.status === 401`
  (OBO misconfig) vs other failures.
- **Types live in `types.ts`**, mirrored 1:1 from backend Pydantic.

### `src/format.ts` — formatters (top-level, not under `lib/`)

```ts
export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function fmtInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-US");
}

export function fmtUSD(value: number | null | undefined, compact = false): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (compact) {
    const abs = Math.abs(value);
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `$${(value / 1e3).toFixed(1)}k`;
  }
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.length >= 10 ? iso.slice(0, 10) : iso;
}

export function deltaClass(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "dim";
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "dim";
}
```

Rules:
- **All formatters return `"—"` (em dash) for nullish/NaN.** Consistent
  empty-state glyph across the whole UI.
- **No locale logic beyond `en-US`** — the data is always rendered in
  one locale for these demos. Don't add i18n until you actually need it.

---

## Design system

The entire visual system lives in `public/ds/colors_and_type.css` (~360
lines: `@font-face` declarations + the `:root` token block + element
defaults). Components reference tokens via `var(--token)` inside inline
`style={{ ... }}`. **No CSS files under `src/`.** No CSS-in-JS, no
preprocessor, no Tailwind.

### `public/ds/` — locked contents

```
public/ds/
├── colors_and_type.css          tokens + @font-face + element defaults
├── fonts/
│   ├── dm-sans-regular.ttf      400 normal
│   ├── dm-sans-italic.ttf       400 italic
│   ├── dm-sans-medium.ttf       500 normal
│   ├── dm-sans-medium-italic.ttf
│   ├── dm-sans-bold.ttf         700 normal
│   ├── dm-sans-bold-italic.ttf
│   ├── dm-mono-light.ttf        300 normal
│   ├── dm-mono-regular.ttf      400 normal
│   ├── dm-mono-italic.ttf       400 italic
│   └── dm-mono-medium.ttf       500 normal
└── assets/
    ├── databricks-symbol-color.svg    on light surfaces, in-product
    ├── databricks-symbol-light.svg    on dark surfaces (sidebar etc.)
    ├── databricks-symbol-navy.svg     monochrome navy
    ├── lockup-primary-color.svg       full wordmark + symbol, light bg
    └── lockup-primary-white.svg       full wordmark + symbol, dark bg
```

Rules:
- **Fonts ship as local `.ttf` files**, not pulled from Google Fonts.
  The `@font-face` block lives in `colors_and_type.css` and references
  `./fonts/<file>.ttf`.
- **Brand SVGs are the only iconography in `public/ds/assets/`.** Don't
  add product icons here — those go in the `Icon.tsx` path table (see
  [Iconography](#iconography)).

### Token set (locked)

```css
:root {
  /* ---------- Brand primaries ---------- */
  --db-lava-600:  #FF3621;   /* primary — hot pop */
  --db-navy-800:  #1B3139;   /* primary — deep ground */
  --db-oat-medium:#EEEDE9;
  --db-oat-light: #F9F7F4;
  --db-white:     #FFFFFF;

  /* ---------- Full ramps ---------- */
  /* lava: 800 #801C17 → 300 #FABFBA            */
  /* maroon: 800 #4A121A → 300 #D69EA8           */
  /* yellow: 800 #7D5319 → 300 #FFDB96  (600 = #FFAB00) */
  /* green: 800 #095A35 → 300 #9ED6C4            */
  /* blue: 800 #04355D → 300 #BAE1FC             */
  /* navy: 900 #0B2026 → 300 #C4CCD6             */

  /* ---------- Functional grays ---------- */
  --db-gray-nav:   #303F47;
  --db-gray-text:  #5A6F77;
  --db-gray-lines: #DCE0E2;

  /* ---------- Semantic surface ---------- */
  --bg:              var(--db-oat-light);
  --bg-canvas:       var(--db-white);
  --bg-subtle:       var(--db-oat-medium);
  --bg-inverse:      var(--db-navy-800);
  --bg-inverse-deep: var(--db-navy-900);

  /* ---------- Semantic foreground ---------- */
  --fg-1:         var(--db-navy-800);     /* default body */
  --fg-2:         var(--db-gray-text);    /* secondary */
  --fg-3:         var(--db-navy-400);     /* tertiary / placeholder */
  --fg-on-dark:   var(--db-white);
  --fg-on-dark-2: var(--db-navy-300);
  --fg-accent:    var(--db-lava-600);
  --fg-link:      var(--db-lava-700);

  /* ---------- Semantic borders ---------- */
  --border:        var(--db-gray-lines);
  --border-strong: var(--db-navy-300);
  --border-dark:   var(--db-navy-700);

  /* ---------- Semantic status ---------- */
  --success: var(--db-green-700);  --success-bg: var(--db-green-300);
  --warning: var(--db-yellow-700); --warning-bg: var(--db-yellow-300);
  --danger:  var(--db-lava-700);   --danger-bg:  var(--db-lava-300);
  --info:    var(--db-blue-700);   --info-bg:    var(--db-blue-300);

  /* ---------- Type families ---------- */
  --font-sans: "DM Sans", ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --font-mono: "DM Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --font-display: "DM Sans", ui-sans-serif, sans-serif;

  /* ---------- Type scale ---------- */
  --fs-display-xl: 96px;   --fs-display-lg: 72px;   --fs-display-md: 56px;
  --fs-h1: 44px;  --fs-h2: 32px;  --fs-h3: 24px;  --fs-h4: 20px;
  --fs-body-lg: 18px;  --fs-body: 16px;  --fs-body-sm: 14px;
  --fs-caption: 12px;  --fs-eyebrow: 13px;

  --lh-tight: 1.05;  --lh-snug: 1.2;  --lh-normal: 1.45;  --lh-relaxed: 1.6;
  --tracking-tight: -0.02em;  --tracking-normal: 0;  --tracking-eyebrow: 0.08em;

  /* ---------- Spacing (4 px base) ---------- */
  --space-0: 0;  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;
  --space-4: 16px;  --space-5: 24px;  --space-6: 32px;  --space-7: 48px;
  --space-8: 64px;  --space-9: 96px;  --space-10: 128px;

  /* ---------- Radii ---------- */
  --radius-none: 0;  --radius-xs: 2px;  --radius-sm: 4px;
  --radius-md: 6px;  --radius-lg: 12px; --radius-xl: 20px; --radius-pill: 999px;

  /* ---------- Shadows ---------- */
  --shadow-xs:  0 1px 2px rgba(11,32,38,0.06);
  --shadow-sm:  0 1px 3px rgba(11,32,38,0.08), 0 1px 2px rgba(11,32,38,0.04);
  --shadow-md:  0 4px 12px rgba(11,32,38,0.08), 0 1px 3px rgba(11,32,38,0.06);
  --shadow-lg:  0 12px 32px rgba(11,32,38,0.12), 0 2px 6px rgba(11,32,38,0.06);
  --shadow-xl:  0 24px 64px rgba(11,32,38,0.18);
  --shadow-focus: 0 0 0 3px rgba(255, 54, 33, 0.28);

  /* ---------- Motion ---------- */
  --ease-out:    cubic-bezier(0.2, 0.7, 0.2, 1);
  --ease-in-out: cubic-bezier(0.5, 0, 0.2, 1);
  --dur-fast: 120ms;  --dur-base: 200ms;  --dur-slow: 320ms;
}
```

Rules:
- **Light theme only.** Oat background, navy text, lava as the single
  saturated accent. No dark mode.
- **Two type families.** DM Sans for prose, headings, UI chrome. DM Mono
  for anything numeric: KPIs, table cells, axis labels, tags, IDs, dates,
  `⌘K` chips.
- **Status colors come from the brand ramps**, not separate semantic
  hex values — `--success` aliases `--db-green-700`, etc. This keeps the
  palette tight.
- **Spacing is the 4 px scale** (`--space-1` … `--space-10`); never use
  raw `px` in inline styles for spacing decisions.

### V0 keyframes (loaded globally)

```css
@keyframes home-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.6; transform: scale(1.15); } }
@keyframes home-word  { 0% { opacity: 0; transform: translateY(8px); filter: blur(4px); } 100% { opacity: 1; transform: translateY(0); filter: blur(0); } }
@keyframes home-glow  { /* lava+yellow text-shadow oscillation */ }
@keyframes home-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }
@keyframes home-drift { 0%, 100% { transform: translate(0,0); } 50% { transform: translate(20px,-10px); } }
@keyframes home-spin  { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes home-bar   { 0%, 100% { transform: scaleY(0.4); } 50% { transform: scaleY(1); } }
@keyframes home-pop   { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.15); } }
```

These ship in `colors_and_type.css` so any page can reference them by
name without re-defining the animation. `BlobBg`, `PageHero`, and
`AnimatedTileMark` all depend on them.

### Aesthetic rules (locked)

- **No raw shadows except on hover-lift cards and tooltips.** Resting
  cards have a 1 px `--border` line, no shadow. Use `--shadow-md`
  (`0 12px 28px -10px rgba(11,18,32,0.20)`) on hover.
- **No gradients** except: (a) the optional 4 px accent stripe on top of
  `Card`, (b) the V0 `home-glow` text effect, (c) `BlobBg` radial
  gradients.
- **Borders are 1 px** in `--db-gray-lines` (`--border`). Never thicker
  except dividers in the dark sidebar (`--db-navy-700`).
- **Aggressive whitespace.** Pages use `--space-6` (32 px) between
  major blocks; cards use `--space-5` (24 px) padding by default.
- **Strip plots over bar charts; small multiples over single big
  charts.** Data ink first. Reference lines tell the viewer what "good"
  looks like at a glance.

---

## Iconography

Two layers:

### 1. Inline-SVG icons — `src/components/Icon.tsx`

A single named-path table covering the product nav + common UI verbs.
Each icon is one `<path>` rendered inside a 24×24 viewBox with stroke
linecap/linejoin "round". This is the same path table the Databricks
V0 design prototype uses — keep visual parity with the mocks.

```tsx
export type IconName =
  | "home" | "landscape" | "whatif" | "optimize" | "rep"
  | "search" | "bell" | "arrow" | "arrow-right" | "arrow-left"
  | "chev_r" | "chev_d" | "chev_l" | "plus" | "check" | "x"
  | "filter" | "download" | "upload" | "spark" | "bot" | "send"
  | "warn" | "star" | "cal" | "table" | "cart" | "lightning"
  | "cog" | "link" | "refresh" | "data" | "user" | "shield"
  | "doc" | "build" | "sliders" | "book" | "question" | "external"
  | "package" | "github";

const ICON_PATHS: Record<IconName, string> = {
  home: "M3 9l9-7 9 7v11a2 2 0 0 1-2 2h-4v-7H10v7H6a2 2 0 0 1-2-2V9z",
  landscape: "M3 18l6-8 4 5 3-4 5 7M3 21h18",
  // ...full table, see prototype's shell.jsx
};

export function Icon({ name, size = 16, color = "currentColor", stroke = 1.6, style }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth={stroke}
         strokeLinecap="round" strokeLinejoin="round"
         style={{ flexShrink: 0, ...style }}>
      <path d={ICON_PATHS[name] ?? ICON_PATHS.home} />
    </svg>
  );
}
```

Rules:
- **Add icons by extending the `IconName` union + `ICON_PATHS` table.**
  Never inline SVG markup at call sites — the union gives TypeScript
  enough information to catch typos.
- **Default size 16, stroke 1.6.** Tweak per call when needed
  (`size={13}` for sidebar search, `size={22}` for hero CTAs).
- **`color="currentColor"`** by default so icons follow text color.
  Override with `color="var(--db-lava-600)"` for accent moments.

### 2. Brand SVGs — `public/ds/assets/`

For the actual Databricks brand mark (in the Sidebar, the favicon, any
"on Databricks" lockup), load the SVG directly via `<img src=…>`:

```tsx
<img src="/ds/assets/databricks-symbol-color.svg" style={{ height: 22 }} alt="" />
```

Rules:
- **Choose the symbol variant by background:** `-color.svg` on light or
  navy surfaces, `-light.svg` for very dark surfaces where the color
  variant lacks contrast, `-navy.svg` for monochrome contexts.
- **Use the lockup (`lockup-primary-*.svg`) sparingly** — typically
  only on splash/login screens or external-facing surfaces. The
  sidebar uses the symbol-only mark.

---

## Layout primitives — `src/components/layout/`

Four shared primitives that every page composes. Pages drop `<BlobBg />`
as their first child, `<PageHero />` as the first content node, and use
`Card` for grouped content. `AnimatedTileMark` provides the V0 SVG
flourishes for landing tiles.

### `BlobBg.tsx` — drifting radial-gradient background

Three blurred radial-gradient blobs (lava, blue, yellow) at fixed
coordinates with staggered `home-drift` loops. Mount as the FIRST child
of a page's outer wrapper. The wrapper must have `position: relative` so
the blobs land behind the rest of the content (z-index: 0; content
stacks above naturally).

```tsx
import { BlobBg } from "../components/layout/BlobBg";

export function MyPage() {
  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: 32 }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1 }}>
        {/* page content */}
      </div>
    </div>
  );
}
```

### `PageHero.tsx` — eyebrow + h1 + subtitle + actions slot

Locked layout for every non-Home page header: pulsing lava-dot eyebrow
chip + 36 px h1 + optional gray subtitle + right-aligned actions slot.
Pulls from `home-pulse` for the eyebrow dot animation.

```tsx
<PageHero
  eyebrow="Plan"
  title="Promotion optimizer"
  subtitle="Optimize a quarter of promotions across your sourcing strategy."
  right={<><SecondaryBtn>Reset</SecondaryBtn><PrimaryBtn>Run</PrimaryBtn></>}
/>
```

Locked eyebrow vocabulary — pick one that matches the page's intent:
**Overview**, **Simulate**, **Plan**, **Tune**, **Review**, **Execute**,
**Knowledge**. Don't invent new ones without aligning on the family.

### `Card.tsx` — bordered white card

The default container for grouped content. White background, 14 px
radius, 1 px `--db-gray-lines` border, 20 px padding. Optional 4 px
gradient accent stripe on top. Optional hover-lift behavior (translateY
−2 px + soft shadow + border picks up the accent color).

```tsx
<Card accent="var(--db-lava-600)" accent2="var(--db-yellow-600)" hover onClick={...}>
  <h3>Title</h3>
  <p>Body</p>
</Card>
```

Rules:
- **Resting cards never carry a shadow** — only on hover.
- **Accent stripe is reserved for landing-page tiles** + select feature
  cards. Most content cards are plain (no accent prop).
- **When `onClick` is supplied, the card renders as a `<button>`**
  with `text-align: left` so it stays visually identical to a div.

### `AnimatedTileMark.tsx` — six reusable SVG marks

Kinds: `bars`, `pulse`, `orbit`, `climb`, `pop`, `gauge`. Each is a
small (~64×56 px) animated SVG that loops on a 1.4–6 s schedule using
the `home-*` keyframes. Drop one into a `Card`'s top-right corner for
visual rhythm on landing pages.

```tsx
<Card accent="var(--db-lava-600)">
  <div style={{ display: "flex", justifyContent: "space-between" }}>
    <div>{/* title + copy */}</div>
    <AnimatedTileMark kind="climb" accent="var(--db-lava-600)" accent2="var(--db-yellow-600)" />
  </div>
</Card>
```

---

## Shell: Sidebar + state-based router

`src/App.tsx` owns `page: PageId` and swaps the right-pane component on
change. No `react-router` until URL-driven routing is actually needed.
Every page change also fires a non-blocking `POST /api/sessions` (if
that endpoint exists) so a recent-sessions list on Home stays in sync.

`src/components/Sidebar.tsx` is the locked left rail:

- **232 px wide**, `--db-navy-900` background, `--db-navy-700` dividers.
- **Brand mark + app title** at top (`databricks-symbol-color.svg`).
- **Search affordance** with `⌘K` chip (monospace, navy-400).
- **NAV registry** as a const array of `{id, label, icon}` — the active
  item shows a 2 px lava bar on its left edge.
- **Persona/scenario footer** with two key/value rows.
- **User chip** at the very bottom: 28 px lava circle with initials +
  name + email.

Sample NAV vocabulary (extend per app, but keep the ids stable so the
recent-sessions log stays consistent):

```ts
export const NAV: readonly NavItem[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "landscape", label: "Overview", icon: "landscape" },
  { id: "whatif", label: "What-if simulator", icon: "whatif" },
  { id: "optimizer", label: "Promotion optimizer", icon: "optimize" },
  { id: "pricing", label: "Pricing optimizer", icon: "sliders" },
  { id: "recommender", label: "Recommender", icon: "star" },
  { id: "rep", label: "Sales rep view", icon: "rep" },
  { id: "docs", label: "Documentation", icon: "book" },
];
```

`/api/me` resolves the user (name + initials from the OBO email). While
the resolve is in flight, show a centered "resolving identity…"
placeholder in DM Mono so the shell doesn't pop into existence.

---

## Charts: hand-drawn SVG with d3 math, in `src/charts/`

The discipline: **`d3-scale` and `d3-shape` produce numbers and path
strings; React renders the SVG.** Never call d3-selection or set
attributes imperatively. Files live under `src/charts/`, not under
`components/`.

### Strip plot — one dot per record on a numeric axis

```tsx
import { scaleLinear } from "d3-scale";
import { useMemo } from "react";

export default function StripPlot({ data, width = 960, height = 150, referenceAt = 0.5 }) {
  const margin = { top: 14, right: 16, bottom: 26, left: 16 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const x = useMemo(() => scaleLinear().domain([0, 1]).range([0, innerW]), [innerW]);
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img">
      <g transform={`translate(${margin.left},${margin.top})`}>
        <line stroke="var(--db-gray-lines)" x1={0} y1={innerH} x2={innerW} y2={innerH} />
        {ticks.map((t) => (
          <g key={t} transform={`translate(${x(t)}, ${innerH})`}>
            <line stroke="var(--db-gray-lines)" y1={0} y2={4} />
            <text fontFamily="var(--font-mono)" fontSize={11} fill="var(--fg-2)"
                  y={16} textAnchor="middle">{t.toFixed(2)}</text>
          </g>
        ))}
        <line stroke="var(--db-lava-600)" strokeDasharray="3 3"
              x1={x(referenceAt)} x2={x(referenceAt)} y1={-4} y2={innerH} />
        {data.map((d) => {
          const jitter = hashSeed(d.id);  // deterministic jitter
          const cy = innerH * 0.15 + jitter * innerH * 0.7;
          return <circle key={d.id} fill="var(--db-navy-800)" cx={x(d.value)} cy={cy} r={3.2} />;
        })}
      </g>
    </svg>
  );
}
```

Rules:
- **`viewBox` + responsive width via CSS** (`svg { width: 100%; height: auto }`)
  — SVGs scale cleanly without per-resize listeners.
- **Margins explicit, inner dims computed.** Every chart uses the same
  margin pattern.
- **Deterministic jitter via a hash of the id** — avoids dots
  re-jittering on every rerender.
- **Reference lines (lava dashed) are mandatory** when there's a
  meaningful threshold.
- **Style with inline `fill`/`stroke` attributes referencing CSS
  variables**, not class names. No CSS files in `src/`.

### Sparkline + small multiples

Same shape as the previous skill rev: `d3-shape` `line` + `area` with
`curveMonotoneX`, no axes, no grids. For small multiples, **share the
y-scale across panels** — independent y-scales make small multiples
lie.

---

## Build + deploy workflow

### `apps/build_frontends.sh` — at the apps root

```bash
#!/usr/bin/env bash
# Build the React frontends for all Databricks Apps.
# Run before `databricks bundle deploy` so frontend/dist/ exists on disk
# and gets synced to the workspace.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APPS=(<app_a> <app_b>)

for app in "${APPS[@]}"; do
  echo "=== Building $app ==="
  cd "$HERE/$app/frontend"
  npm install
  npm run build
  if [ ! -f dist/index.html ]; then
    echo "FAIL: $app/frontend/dist/index.html not produced" >&2
    exit 1
  fi
  echo "  ✓ dist/ ready ($(du -sh dist | cut -f1))"
done
```

Rules:
- **`set -euo pipefail`** — a single npm failure must abort the deploy.
- **Verify `dist/index.html`** explicitly. A silent `npm run build` can
  succeed without producing assets if Vite config is wrong.
- The bundle's `databricks.yml` has
  `sync.include: ["apps/*/frontend/dist/**", "apps/*/frontend/dist/ds/**"]`
  — without it the deployed app has no static assets and the brand
  fonts/assets won't ship.

### Local dev

```bash
# Backend
cd app/backend
uv sync                                    # reads pyproject.toml
export APP_DEV_ALLOW_ANONYMOUS=1           # local-only OBO bypass
export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
export DATABRICKS_WAREHOUSE_ID=<warehouse-id>
export DATABRICKS_CATALOG=<project>
uv run uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd app/frontend
npm install
npm run dev                                # vite on :5173, proxies /api → :8000
```

When `APP_DEV_ALLOW_ANONYMOUS=1` is set, `/api/me` returns the
configured `dev_user_email` and routes that try to open a warehouse
connection will raise a 500 ("Cannot open a warehouse connection for an
anonymous caller"). To exercise UC paths locally, deploy the app to a
sandbox workspace and use the Apps UI — the proxy injects real
`X-Forwarded-*` headers.

### Deploy via bundle

```bash
./apps/build_frontends.sh
databricks bundle validate -t prod
databricks bundle deploy -t prod
```

Don't deploy with `databricks apps deploy` directly when the app lives
inside a bundle — bundle deploy handles source sync and resource updates
together. Single-source-of-truth.

### `resources/app.yml` checklist

```yaml
resources:
  apps:
    <app>:
      name: <app>
      source_code_path: ${workspace.file_path}/apps/<app>
      resources:
        - name: warehouse
          sql_warehouse:
            id: ${var.warehouse_id}
            permission: CAN_USE
        # Add `database` and `serving_endpoint` resources here
        # only if the app needs them — keep the surface narrow.
      user_api_scopes:
        - sql
      # Add: dashboards.genie, serving.serving-endpoints, etc. as needed.
```

Rules:
- **`user_api_scopes: [sql, ...]` is the gate that makes OBO work.**
  Without it, Apps runs in app-principal mode, the `X-Forwarded-*`
  headers are missing, and every `Depends(caller_identity)` route 401s.
- **`config.env` on the resource is ignored at deploy time** — set env
  in `app.yaml`. (Bundle vars like `${var.warehouse_id}` still work
  for the resource binding itself.)

---

## What this skill is NOT

- **Not for Streamlit/Dash/Gradio apps** — those have their own
  patterns. Use this when you want a hand-built React UI with the
  Databricks brand design system.
- **Not for adding component libraries.** The whole point is a bespoke
  visual identity via the DM Sans + brand palette in `public/ds/` plus
  inline styles. If you find yourself reaching for MUI, Tailwind, or
  Chakra, this isn't the right skill.
- **Not for charts that need real interactivity beyond hover/click.**
  For brushing, panning, animated transitions, you'll need to bring in
  a chart library — and that breaks the visual system here. Push back
  on the requirement first; most demos don't actually need brushing.
- **Not for service-principal-only backends.** This skill assumes
  per-user OBO with `databricks-sql-connector`. If the app legitimately
  needs to act as a service principal (background jobs, scheduled
  syncs), wrap those in a non-OBO router and document why.
- **Not the bundle layout** — for the DAB/`resources/` split, see the
  `dbx-bundle-medallion-project` skill.
