---
name: dbx-app-fastapi-react
description: Build a Databricks App as FastAPI + Vite/React/TypeScript with a hand-built CSS design system and hand-drawn SVG charts (no Tailwind, no UI library, no chart library). Use when scaffolding a new Databricks App, adding a new app to a bundle, or replicating the dual-mode auth + Statement Execution backend pattern. Locks the folder layout, backend wrappers, and design tokens; leaves business routes and UI content flexible.
---

# Databricks App — FastAPI + React + custom design system

A reference layout for Databricks Apps that pair a FastAPI backend
(running queries via the SDK's Statement Execution API) with a
Vite/React/TypeScript frontend rendering hand-drawn SVG charts on top
of a CSS-custom-property design system. No Tailwind, no MUI/Chakra,
no Recharts/Victory/D3-rendered DOM.

## When to use this skill

- Adding a new Databricks App under `apps/<app_name>/` in a bundle that
  already uses the `dbx-bundle-medallion-project` layout.
- Building a data-dense internal/demo UI where you want full control
  over typography, spacing, and chart aesthetics (strip plots, small
  multiples, sparklines).
- Replicating the dual-mode auth pattern (CLI profile locally, SP in
  Databricks Apps runtime) with parameterized SQL via the Statement
  Execution API.

If the app is a quick Streamlit/Dash demo, use one of the Python-app
skills instead — this layout earns its complexity once you want the
frontend to look intentional.

---

## Folder layout (locked)

```
apps/<app_name>/
├── app.yaml                  Databricks App runtime config
├── app.py                    FastAPI entry — mounts /api + serves frontend/dist
├── requirements.txt
├── README.md
├── .gitignore                ignores node_modules, frontend/dist, .venv
├── server/
│   ├── __init__.py
│   ├── config.py             dual-mode auth + workspace client + warehouse id
│   ├── db.py                 Statement-execution wrapper (parameterized, typed)
│   └── routes/
│       ├── __init__.py
│       └── <domain>.py       one router per domain — overview.py, etc.
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── index.css         design tokens + all component styles
        ├── api.ts            typed fetch wrappers
        ├── types.ts          shared interfaces
        ├── lib/
        │   ├── format.ts     fmtUSD, fmtPct, fmtInt, fmtDate, deltaClass
        │   └── <other>.ts    domain helpers (e.g. tier color/class)
        ├── components/       leaf components — header, cards, charts, tables
        └── pages/            top-level page composition
```

When the bundle has multiple apps, keep one shared
`apps/build_frontends.sh` at the apps root that builds all of them.

---

## Backend pattern

### `app.yaml` — Databricks App runtime config

```yaml
command:
  - "python"
  - "-m"
  - "uvicorn"
  - "app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: warehouse        # bound to the `warehouse` resource in resources/app.yml
```

Rules:
- **Entry is `uvicorn app:app`** on port 8000. The Databricks Apps
  runtime fronts it.
- **`valueFrom: warehouse`** is the bridge to the `sql_warehouse`
  resource declared in the bundle's `resources/app.yml`. The runtime
  injects `DATABRICKS_WAREHOUSE_ID` automatically — locally you have to
  export it yourself.
- **Project-wide config (catalog name) comes from the bundle**, not
  from `app.yaml`. The bundle's `resources/app.yml` sets
  `<PROJECT>_CATALOG` env via `config.env`.

### `requirements.txt`

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
databricks-sdk>=0.40.0
pydantic>=2.6.0
python-multipart>=0.0.9
```

Keep this list lean. No SQLAlchemy, no requests-with-retries — the SDK
handles auth and retries.

### `app.py` — FastAPI entry

```python
"""<App Name> — FastAPI entry point.

Mounts the React build as static assets and exposes the /api routes.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.routes import <domain1>, <domain2>

app = FastAPI(
    title="<App Name>",
    description="<one-line description>",
    version="0.1.0",
)

app.include_router(<domain1>.router, prefix="/api")
app.include_router(<domain2>.router, prefix="/api")


@app.get("/api/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# Serve the React build. Vite outputs to frontend/dist.
_frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_frontend_dir):
    _assets_dir = os.path.join(_frontend_dir, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # Route unknown paths to the SPA's index.html — React Router takes over.
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
```

Rules:
- **All API routes share the `/api` prefix.** The catch-all SPA route
  must be defined *after* all `/api` routers are mounted.
- **`/api/healthz`** is a flat dict — not a router — so health checks
  work even if routers fail to import.
- **Mount `/assets` separately from the SPA fallback** so Vite's
  hashed asset URLs serve directly with correct MIME types.

### `server/config.py` — dual-mode auth

```python
"""Dual-mode auth + workspace config.

Running under Databricks Apps → auto-injected service principal credentials.
Running locally → falls back to the Databricks CLI profile (default: DEFAULT).
"""

from __future__ import annotations

import os

from databricks.sdk import WorkspaceClient


IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# Unity Catalog targets — pass via bundle env (config.env in resources/app.yml).
CATALOG = os.environ.get("<PROJECT>_CATALOG", "<project>_demo")
GOLD = f"{CATALOG}.gold"
ML = f"{CATALOG}.ml"


def get_workspace_client() -> WorkspaceClient:
    """Authenticated WorkspaceClient for the current environment."""
    if IS_DATABRICKS_APP:
        return WorkspaceClient()                           # SP creds, auto-injected
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_warehouse_id() -> str:
    """SQL warehouse id used for all statement execution."""
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not wh:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is not set. "
            "Locally: `export DATABRICKS_WAREHOUSE_ID=<id>`. "
            "In Databricks Apps: confirm app.yaml declares a `warehouse` resource "
            "with `valueFrom: warehouse` on this env var."
        )
    return wh
```

Rules:
- **`IS_DATABRICKS_APP` is detected from `DATABRICKS_APP_NAME`** — the
  Apps runtime sets it. Don't try to detect via hostname or file paths.
- **Local runs read a CLI profile**, default `DEFAULT`. Document this in
  the README so contributors know to set up a profile.
- **Catalog comes from env, never hardcoded** in the wrapper. Compose
  `GOLD` / `ML` / `SILVER` / etc. as module constants for ergonomic
  f-string interpolation in routes.
- **Fail loud on missing warehouse id** — silent fallback to a wrong
  warehouse is a long debugging session.

### `server/db.py` — Statement Execution wrapper

```python
"""Thin wrapper over the Databricks SQL Statement Execution API.

Returns rows as dicts so FastAPI can JSON-serialize them directly. Parameters
are passed via the API's `parameters` field (server-side substitution) rather
than client-side string formatting — safer and pipeline-friendly.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from .config import get_warehouse_id, get_workspace_client


def _param(name: str, value: Any) -> StatementParameterListItem:
    if isinstance(value, bool):
        return StatementParameterListItem(name=name, value=str(value).lower(), type="BOOLEAN")
    if isinstance(value, int):
        return StatementParameterListItem(name=name, value=str(value), type="INT")
    if isinstance(value, float):
        return StatementParameterListItem(name=name, value=str(value), type="DOUBLE")
    return StatementParameterListItem(name=name, value=str(value), type="STRING")


def execute(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a SQL statement on the configured warehouse and return rows as dicts."""
    w = get_workspace_client()
    warehouse_id = get_warehouse_id()
    parameters: list[StatementParameterListItem] = []
    if params:
        parameters = [_param(k, v) for k, v in params.items()]

    response = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="30s",
        parameters=parameters or None,
    )

    statement_id = response.statement_id
    while response.status and response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.5)
        response = w.statement_execution.get_statement(statement_id)

    state = response.status.state if response.status else None
    if state != StatementState.SUCCEEDED:
        err = response.status.error.message if response.status and response.status.error else "unknown"
        raise RuntimeError(f"SQL failed ({state}): {err}")

    schema = response.manifest.schema if response.manifest else None
    schema_cols = schema.columns if schema else []
    columns: list[str] = [c.name for c in schema_cols]
    type_names: list[str] = [str(c.type_name) if c.type_name else "" for c in schema_cols]
    data_array: Iterable[list[str]] = []
    if response.result and response.result.data_array:
        data_array = response.result.data_array

    rows: list[dict[str, Any]] = []
    for row in data_array:
        rows.append(
            {col: _coerce(val, t) for col, val, t in zip(columns, row, type_names)}
        )
    return rows


_INT_TYPES = {"BYTE", "SHORT", "INT", "LONG"}
_FLOAT_TYPES = {"FLOAT", "DOUBLE", "DECIMAL"}


def _coerce(value: Any, type_name: str) -> Any:
    """Cast string values from the Statement Execution API to native Python types.

    The API returns every cell as a JSON string regardless of column type; the
    frontend then crashes when number formatters meet a string. Cast here.
    """
    if value is None:
        return None
    t = type_name.split(".")[-1].upper()
    if t in _INT_TYPES:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if t in _FLOAT_TYPES:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if t == "BOOLEAN":
        return value in (True, "true", "TRUE", "True", 1, "1")
    return value
```

Rules:
- **Always parameterize** — pass values through `params` and reference
  them as `:name` in SQL. Never f-string user input into SQL.
- **The type-coercion step is non-optional** — the Statement Execution
  API returns every cell as a string regardless of declared type, and
  frontend formatters crash on `"1234".toFixed(0)`. Cast on the way out.
- **Polling is part of `execute()`**, not the caller's job. 30s wait
  timeout + 0.5s poll interval handles long-running queries without
  needing async/await ceremony.
- **Raise `RuntimeError` on failure** — let FastAPI's default handler
  return 500. Routes that need different status codes catch and re-raise
  as `HTTPException`.

### `server/routes/<domain>.py` — domain router

```python
"""<Domain> endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import GOLD
from ..db import execute

router = APIRouter()


@router.get("/<resource>")
def list_<resource>(
    filter_a: str | None = Query(default=None),
    sort_by: str = Query(default="<default_col>"),
    direction: str = Query(default="desc"),
    limit: int = Query(default=100, le=500),
) -> list[dict]:
    # Validate sort_by against an allow-list — sort columns can't be parameterized,
    # so the only safe path is a fixed allow-list.
    allowed_sort = {"col_a", "col_b", "col_c"}
    if sort_by not in allowed_sort:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of {sorted(allowed_sort)}")
    if direction.lower() not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="direction must be asc or desc")

    wheres = []
    params: dict = {}
    if filter_a:
        wheres.append("col_a = :filter_a")
        params["filter_a"] = filter_a
    where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ""

    sql = f"""
        SELECT col_a, col_b, col_c
        FROM {GOLD}.<table>
        {where_sql}
        ORDER BY {sort_by} {direction.upper()}
        LIMIT :lim
    """
    params["lim"] = limit
    return execute(sql, params)
```

Rules:
- **`/api/<domain>` per file**, e.g. `routes/overview.py` →
  `/api/overview`. Mount with `app.include_router(<domain>.router, prefix="/api")`.
- **One DB column per query parameter** that filters; build the
  `WHERE` clause incrementally so empty filters drop out.
- **Sort columns require an allow-list** (Statement Execution can't
  parameterize identifiers). Direction is a fixed `{asc, desc}` set.
- **Return raw `list[dict]` or `dict`** — let FastAPI serialize.
  Pydantic response models are fine if the schema is stable, but for
  fast-moving demos the dicts from `execute()` are usually enough.

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
    "preview": "vite preview"
  },
  "dependencies": {
    "d3-array": "^3.2.4",
    "d3-scale": "^4.0.2",
    "d3-shape": "^3.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
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
  are SVG components in `src/components/`. Styling is pure CSS in
  `src/index.css`.
- **`react-router-dom`** is included by convention even if the SPA
  starts as a single page — easy to grow, doesn't hurt the bundle.

### `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
```

The `/api` proxy is what makes local dev frictionless — frontend on
:5173, backend on :8000, fetch(`/api/...`) just works.

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
    "allowImportingTsExtensions": false,
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
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
    />
    <title><App Title></title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Inter + JetBrains Mono via Google Fonts** is the locked typography
choice. Inter for prose, JetBrains Mono for everything numeric, axis
labels, tags, monospaced alignment.

### `src/api.ts` — typed fetch wrappers

```ts
import type { OverviewResponse } from "./types";

const API = "/api";

async function j<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export function fetchOverview(): Promise<OverviewResponse> {
  return j<OverviewResponse>("/overview");
}

// POST helpers spell out fetch() so the body shape is visible inline:
export async function logAction(
  id: string,
  body: { action: string; note?: string }
): Promise<{ status: string; logged_at: string }> {
  const res = await fetch(`${API}/items/${encodeURIComponent(id)}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}
```

Rules:
- **One `j<T>()` helper for all GETs.** Don't reach for axios or
  TanStack Query for a demo-scale app.
- **Always `encodeURIComponent` ids** in path segments.
- **Types live in `types.ts`**, mirrored to the backend response shape.

### `src/lib/format.ts` — formatters

```ts
export function fmtPct(value: number | null | undefined, fractionDigits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(fractionDigits)}%`;
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

export function fmtProb(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(3);
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

## Design system (locked tokens, flexible composition)

The entire visual system lives in `src/index.css` — ~700 lines of plain
CSS. No CSS-in-JS, no preprocessor, no Tailwind. Components reference
tokens via `var(--token)`.

### Token set (locked)

```css
:root {
  /* core palette */
  --bg:            #faf9f6;
  --panel:         #ffffff;
  --panel-muted:   #f5f3ee;
  --text:          #0b1423;
  --text-dim:      #5b6b82;
  --text-faint:    #a5afc0;
  --border:        #e6e3dd;
  --border-faint:  #eeece7;
  --rule:          #d7d3ca;

  /* semantic — risk / status tiers (muted, print-safe) */
  --tier-critical: #be1931;
  --tier-high:     #c6680d;
  --tier-medium:   #9a8400;
  --tier-low:      #6f7a8c;
  --tier-low-dot:  #a5afc0;

  /* accents (used sparingly) */
  --link:          #204e90;

  /* typography */
  --sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", "SF Mono", ui-monospace, Consolas, monospace;

  /* spacing scale (rem) */
  --s-1:  0.25rem;
  --s-2:  0.5rem;
  --s-3:  0.75rem;
  --s-4:  1rem;
  --s-5:  1.5rem;
  --s-6:  2rem;
  --s-7:  3rem;
  --s-8:  4rem;

  /* font sizes */
  --fs-tiny:   0.6875rem;     /*  11px — axis labels, tags */
  --fs-small:  0.8125rem;     /*  13px — table cells, captions */
  --fs-base:   0.9375rem;     /*  15px — body */
  --fs-big:    1.25rem;       /*  20px — section headings */
  --fs-stat:   1.75rem;       /*  28px — summary numbers */
  --fs-hero:   2.5rem;        /*  40px — single dominant KPI */
}
```

Rules — these tokens are locked across apps so the family looks coherent:
- **Light theme only.** Cream background, dark navy text. No dark mode.
- **Two type families.** Inter for prose, JetBrains Mono for *anything
  numeric*: KPIs, table cells, axis labels, tags, IDs, dates.
- **Tier colors are muted and print-safe.** No saturated reds/greens.
  Status semantics: `critical > high > medium > low`, with `low-dot` as
  a non-text dot color.
- **Spacing is a numbered scale** (`--s-1` through `--s-8`); never use
  raw `px` or `rem` in components.

### Aesthetic rules (locked)

- **No shadows** anywhere except the faintest tooltip
  (`box-shadow: 0 1px 2px rgba(11, 20, 35, 0.06)`).
- **No gradients.** Solid fills only.
- **Borders are 1px** in `--border` or `--border-faint`. Never thicker.
- **Aggressive whitespace.** Panels have generous padding. Section
  heads are uppercased, letter-spaced, in `--text-dim`.
- **Strip plots over bar charts; small multiples over single big charts.**
  Data ink first.
- **Reference lines** (dashed verticals) tell the viewer what "good"
  looks like at a glance.
- **Tooltips are monospaced**, panel-bordered, fixed-positioned with
  `pointer-events: none`.

### Common building blocks (in `index.css`)

These class names are conventions — flexible to extend, but reuse
existing ones where possible:

- `.panel` — bordered white card, padding `--s-5`.
- `.panel-head h2` — uppercase, letter-spaced, `--text-dim`, `--fs-small`.
- `.grid.cols-4` / `.grid.cols-2` / `.grid.main` — common grid layouts.
- `.stat .label / .value / .delta` — KPI summary blocks.
- `.tier.critical / .high / .medium / .low` — pill with leading dot.
- `.filter-pill` — bordered toggle, monospace, uppercase.
- `.chart-wrap` — `position: relative` for tooltip anchoring.
- `.tooltip` — fixed-position, panel-style.
- `.loading` / `.empty` — centered monospace placeholder.
- helpers: `.mono`, `.dim`, `.faint`, `.neg`, `.pos`, `.upper`.

---

## Charts: hand-drawn SVG with d3 math

The discipline: **`d3-scale` and `d3-shape` produce numbers and path
strings; React renders the SVG.** Never call d3-selection or set
attributes imperatively.

### Strip plot — one dot per record on a numeric axis

```tsx
import { scaleLinear } from "d3-scale";
import { useMemo, useState } from "react";

export default function StripPlot({ data, width = 960, height = 150, referenceAt = 0.5 }) {
  const margin = { top: 14, right: 16, bottom: 26, left: 16 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const x = useMemo(() => scaleLinear().domain([0, 1]).range([0, innerW]), [innerW]);
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img">
      <g transform={`translate(${margin.left},${margin.top})`}>
        <line className="axis-line" x1={0} y1={innerH} x2={innerW} y2={innerH} />
        {ticks.map((t) => (
          <g key={t} transform={`translate(${x(t)}, ${innerH})`}>
            <line className="axis-line" y1={0} y2={4} />
            <text className="axis-tick" y={16} textAnchor="middle">{t.toFixed(2)}</text>
          </g>
        ))}
        <line className="reference" x1={x(referenceAt)} x2={x(referenceAt)} y1={-4} y2={innerH} />
        {data.map((d) => {
          const jitter = hashSeed(d.id);                         // deterministic jitter
          const cy = innerH * 0.15 + jitter * innerH * 0.7;
          return <circle key={d.id} className="strip-dot" cx={x(d.value)} cy={cy} r={3.2} />;
        })}
      </g>
    </svg>
  );
}
```

Rules:
- **`viewBox` + responsive width via CSS** (`svg { width: 100%; height: auto }`)
  — SVGs scale cleanly without per-resize listeners.
- **Margins explicit, inner dims computed.** Every chart has the same
  margin pattern.
- **Deterministic jitter via a hash of the id** — avoids dots
  re-jittering on every rerender.
- **Reference lines are mandatory** when there's a meaningful threshold.

### Sparkline — line + area, dots for events

```tsx
import { extent, max } from "d3-array";
import { scaleLinear, scaleTime } from "d3-scale";
import { area as d3Area, line as d3Line, curveMonotoneX } from "d3-shape";

export default function Sparkline({ points, width = 140, height = 32 }) {
  const [minDate, maxDate] = extent(points, (d) => new Date(d.date)) as [Date, Date];
  const maxY = max(points, (d) => d.value) as number || 1;
  const x = scaleTime().domain([minDate, maxDate]).range([0, width]);
  const y = scaleLinear().domain([0, maxY]).range([height, 0]).nice();

  const linePath = d3Line<typeof points[number]>()
    .x((d) => x(new Date(d.date)))
    .y((d) => y(d.value))
    .curve(curveMonotoneX)(points) || "";

  const areaPath = d3Area<typeof points[number]>()
    .x((d) => x(new Date(d.date)))
    .y0(height)
    .y1((d) => y(d.value))
    .curve(curveMonotoneX)(points) || "";

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
      <path className="spark-area" d={areaPath} />
      <path className="spark-path" d={linePath} />
    </svg>
  );
}
```

Sparklines have no axes and no grids. `curveMonotoneX` keeps lines
honest (no spline overshoot below zero).

### Small multiples

A grid of mini-panels with a **shared y-axis** so comparisons are honest.
Each mini panel is a sparkline-shaped thing with a tiny title row.
Don't give each panel its own y-scale — that's what makes small
multiples lie.

---

## Build + deploy workflow

### `apps/build_frontends.sh` — at the apps root

```bash
#!/usr/bin/env bash
# Build the React frontends for all Databricks Apps.
# Run this before `databricks bundle deploy` so frontend/dist/ exists on disk
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
- The bundle's `databricks.yml` has `sync.include: apps/*/frontend/dist/**`
  — without it the deployed app has no static assets.

### Local dev

```bash
# Backend
cd apps/<app>
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
export DATABRICKS_PROFILE=DEFAULT
export DATABRICKS_WAREHOUSE_ID=<warehouse-id>
export <PROJECT>_CATALOG=<project>_demo
uv run uvicorn app:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                                 # vite on :5173, proxies /api → :8000
```

### Deploy via bundle

```bash
./apps/build_frontends.sh
databricks bundle validate -t prod
databricks bundle deploy -t prod
```

Don't deploy apps with `databricks apps deploy` directly when they live
inside a bundle — bundle deploy handles source sync and resource updates
together. Single-source-of-truth.

---

## What this skill is NOT

- **Not for Streamlit/Dash/Gradio apps** — those have their own
  patterns. Use this when you want a hand-built React UI.
- **Not for adding component libraries.** The whole point is bespoke
  visual identity via 14 CSS variables + ~700 lines of CSS. If you find
  yourself reaching for MUI, this isn't the right skill.
- **Not for charts that need real interactivity beyond hover/click.**
  For brushing, panning, animated transitions, reach for a chart library
  — but understand that breaks the visual system here.
- **Not the bundle layout** — for the DAB/`resources/` split, see the
  `dbx-bundle-medallion-project` skill.
