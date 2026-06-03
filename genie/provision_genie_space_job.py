# Databricks notebook source
# ============================================================================
# provision_genie_space_job — create/refresh the Strategic Spend Analytics
# Genie space, IDEMPOTENTLY BY TITLE. Canonical (in-bundle) provisioning path.
#
# The app resolves the space id by this same title at runtime, so nothing has to
# write an id back into app.yaml — re-running this job keeps the same space.
#
# Shares the exact space definition with the CLI via genie/genie_space_def.py.
# Runs on serverless as the job's run_as identity (no stored credentials).
# ============================================================================

# COMMAND ----------
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "finance_spend_analytics")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("target", "prod")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
target = dbutils.widgets.get("target")

# COMMAND ----------
# Import the shared, pure-Python space definition from the synced bundle files.
import os, sys, json
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
sys.path.insert(0, "/Workspace" + os.path.dirname(_nb))
from genie_space_def import build_serialized_space, DEFAULT_DESCRIPTION, space_title

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

title = space_title(target)
serialized = json.dumps(build_serialized_space(catalog, schema))
print(f"Provisioning Genie space '{title}' over {catalog}.{schema} metric views ...")

# COMMAND ----------
# Find an existing space with this exact title (idempotent by name).
def find_space_id(title: str) -> str | None:
    token = None
    while True:
        q = {"page_size": 100}
        if token:
            q["page_token"] = token
        res = w.api_client.do("GET", "/api/2.0/genie/spaces", query=q)
        for s in res.get("spaces", []):
            if s.get("title") == title:
                return s.get("space_id")
        token = res.get("next_page_token")
        if not token:
            return None

existing = find_space_id(title)
body = {"title": title, "description": DEFAULT_DESCRIPTION,
        "warehouse_id": warehouse_id, "serialized_space": serialized}

if existing:
    print(f"Updating existing space {existing} in place ...")
    w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=body)
    space_id = existing
else:
    me = w.current_user.me().user_name
    body["parent_path"] = f"/Users/{me}"
    print(f"Creating new space under /Users/{me} ...")
    resp = w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)
    space_id = resp.get("space_id")

print(f"✓ Genie space ready: {space_id}  (title: {title})")

# COMMAND ----------
# Return the id (and title) so the orchestrator/run logs capture it. The app
# resolves by title, so downstream tasks don't need this value.
dbutils.notebook.exit(json.dumps({"space_id": space_id, "title": title}))
