"""FastAPI entrypoint for the Helios Strategic Sourcing Portal.

Run locally:
    cd apps/helios-sourcing-portal/backend
    export APP_DEV_ALLOW_ANONYMOUS=1
    export DATABRICKS_HOST=https://e2-demo-field-eng.cloud.databricks.com
    export DATABRICKS_WAREHOUSE_ID=<id>
    uv run uvicorn backend.main:app --reload --port 8000

In Databricks Apps (configured in ../app.yaml):
    uvicorn backend.main:app --host 0.0.0.0 --port $DATABRICKS_APP_PORT
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Save SP credentials under private names BEFORE clearing the originals.
# The FMAPI chatbot call uses these to obtain an M2M token so the LLM call
# runs as the app's SP (full workspace access) rather than as the OBO user.
for _src, _dst in (
    ("DATABRICKS_CLIENT_ID",     "APP_SP_CLIENT_ID"),
    ("DATABRICKS_CLIENT_SECRET", "APP_SP_CLIENT_SECRET"),
):
    _val = os.environ.get(_src, "")
    if _val:
        os.environ[_dst] = _val

# Clear the originals so the SDK does not see two conflicting auth methods
# when OBO access_token= kwargs are passed to databricks-sql-connector or
# WorkspaceClient(config=Config(...)).
for _key in ("DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET"):
    os.environ.pop(_key, None)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .lakebase import close_pool, init_pool
from .routers import chatbot, contracts, cost_savings, labeling, suppliers, system

log = logging.getLogger("sourcing_portal")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Helios Strategic Sourcing Portal",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — only meaningful in local dev (Vite on :5173 → uvicorn on :8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers — must be registered before the SPA fallback StaticFiles mount.
app.include_router(system.router, prefix="/api")
app.include_router(contracts.router, prefix="/api")
app.include_router(suppliers.router, prefix="/api")
app.include_router(cost_savings.router, prefix="/api")
app.include_router(chatbot.router, prefix="/api")
app.include_router(labeling.router, prefix="/api")

# Serve the built React bundle at /. Computed relative to this file so the
# same path works in local dev and inside the Apps runtime.
_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_DIST_DIR, html=True), name="frontend")
else:
    log.warning("Frontend bundle not found at %s — build with: cd frontend && npm run build", _DIST_DIR)
