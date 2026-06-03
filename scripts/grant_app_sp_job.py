# Databricks notebook source
# ============================================================================
# grant_app_sp_job — grant the app's auto-created service principal everything
# it needs, IN-BUNDLE. Canonical path (run via the `setup` job / `bundle run`).
#
#   1. Resolve the app SP (databricks apps get -> service_principal_client_id).
#   2. Schema-level UC grants via spark.sql (USE CATALOG + USE SCHEMA, SELECT on
#      gold/silver/ml) — covers every current + future table and metric view.
#   3. Grant the SP CAN_RUN on the Genie space (resolved by title).
#
# Catalog/schema arrive as job parameters (${var.*}, DAB-substituted) so there's
# no ${var} in SQL. Runs on serverless as the job's run_as identity.
# ============================================================================

# COMMAND ----------
dbutils.widgets.text("catalog", "horizontal_finance_dev")
dbutils.widgets.text("schema_gold", "gold")
dbutils.widgets.text("schema_silver", "silver")
dbutils.widgets.text("schema_ml", "ml")
dbutils.widgets.text("app_name", "spend-analytics-dev")
dbutils.widgets.text("target", "dev")

catalog = dbutils.widgets.get("catalog")
schemas = [dbutils.widgets.get(k) for k in ("schema_gold", "schema_silver", "schema_ml")]
app_name = dbutils.widgets.get("app_name")
target = dbutils.widgets.get("target")

# COMMAND ----------
import os, sys, json
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
sys.path.insert(0, "/Workspace" + os.path.dirname(os.path.dirname(_nb)) + "/genie")
from genie_space_def import space_title

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# 1. Resolve the app service principal (created by the Apps platform at deploy).
app = w.api_client.do("GET", f"/api/2.0/apps/{app_name}")
sp = app.get("service_principal_client_id")
if not sp:
    raise SystemExit(f"App '{app_name}' has no service_principal_client_id — deploy the app first.")
print(f"App SP: {sp}  ({app.get('service_principal_name')})")

# COMMAND ----------
# 2. Schema-level UC grants (idempotent).
stmts = [f"GRANT USE CATALOG ON CATALOG {catalog} TO `{sp}`"]
stmts += [f"GRANT USE SCHEMA, SELECT ON SCHEMA {catalog}.{s} TO `{sp}`" for s in schemas]
for s in stmts:
    spark.sql(s)
    print("✓", s)

# COMMAND ----------
# 3. Genie CAN_RUN (resolve the space by title, then PATCH its ACL — merges).
title = space_title(target)
def find_space_id(title):
    token = None
    while True:
        q = {"page_size": 100}
        if token:
            q["page_token"] = token
        res = w.api_client.do("GET", "/api/2.0/genie/spaces", query=q)
        for sp_ in res.get("spaces", []):
            if sp_.get("title") == title:
                return sp_.get("space_id")
        token = res.get("next_page_token")
        if not token:
            return None

space_id = find_space_id(title)
if space_id:
    w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{space_id}",
                    body={"access_control_list": [
                        {"service_principal_name": sp, "permission_level": "CAN_RUN"}]})
    print(f"✓ Genie CAN_RUN on {space_id} ({title})")
else:
    print(f"⚠ Genie space titled '{title}' not found — run provision_genie first.")

print("Done.")
