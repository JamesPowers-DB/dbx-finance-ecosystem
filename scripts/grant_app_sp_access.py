#!/usr/bin/env python3
"""Grant the Spend Analytics app service principal everything it needs — no hand-editing.

Single source of truth = the parameterized template
``sql/security/grant_app_sp_genie_access_<target>.sql`` (catalog/schema are
``${var.*}`` Databricks Asset Bundle variables). This script:

  1. Resolves the bundle's variable VALUES for the target via
     ``databricks bundle validate -t <target>`` — i.e. "whatever the bundle
     includes" (dev → main, prod → main).
  2. Resolves the app's service principal from ``databricks apps get
     spend-analytics-<target>`` (the SP is auto-created at deploy, not in the repo),
     so there's no ``<APP_SP_PRINCIPAL>`` to find/replace.
  3. Fills the template (``${var.*}`` + ``<APP_SP_PRINCIPAL>``) and runs every GRANT.
  4. Grants the SP CAN_RUN on the Genie space (a workspace ACL, not a UC grant).

Run after ``databricks bundle deploy``:

    python scripts/grant_app_sp_access.py --target dev
    python scripts/grant_app_sp_access.py --target dev --dry-run    # preview only

Auth is delegated to the Databricks CLI (`databricks ...`), so this carries no
credentials and honors --profile.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Per-target app name + default Genie space. Catalog/schema are NOT hardcoded here —
# they come from the bundle (see resolve_bundle_vars). The map is only a fallback.
TARGETS = {
    "dev": {
        "app": "spend-analytics-dev",
        "genie_space_id": "01f15c3823f2163a9560dadb4357bb31",
        "fallback_catalog": "main",
    },
    "prod": {
        "app": "spend-analytics-prod",
        "genie_space_id": "",
        "fallback_catalog": "main",
    },
}
FALLBACK_SCHEMAS = {"schema": "finance_spend_analytics"}
DEFAULT_WAREHOUSE_ID = "e9b34f7a2e4b0561"


def run_cli(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"`{' '.join(args)}` failed:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def databricks_api(method: str, path: str, *, profile: str, body: dict | None = None) -> dict:
    args = ["databricks", "api", method, path, "--profile", profile]
    if body is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(body, fh)
            args += ["--json", f"@{fh.name}"]
    out = run_cli(args)
    return json.loads(out) if out else {}


def resolve_bundle_vars(target: str, profile: str) -> dict[str, str]:
    """Return {var_name: resolved_value} for the target, from `bundle validate`."""
    try:
        out = run_cli(["databricks", "bundle", "validate", "-t", target,
                       "--profile", profile, "--var", f"warehouse_id={DEFAULT_WAREHOUSE_ID}",
                       "--output", "json"])
        variables = (json.loads(out).get("variables") or {})
        resolved = {k: v.get("value") for k, v in variables.items() if v.get("value") is not None}
        if resolved.get("catalog"):
            return resolved
    except Exception as exc:  # noqa: BLE001
        print(f"  (bundle validate unavailable: {exc}; using fallback values)")
    # Fallback to the known defaults for the target.
    return {"catalog": TARGETS[target]["fallback_catalog"], **FALLBACK_SCHEMAS}


def resolve_sp_client_id(app_name: str, profile: str) -> tuple[str, str]:
    """Return (client_id, display_name) of the app's managed service principal."""
    app = json.loads(run_cli(["databricks", "apps", "get", app_name,
                              "--profile", profile, "--output", "json"]))
    client_id = app.get("service_principal_client_id")
    if not client_id:
        raise RuntimeError(
            f"App '{app_name}' has no service_principal_client_id yet — is it deployed? "
            f"Run `databricks bundle deploy -t {app_name.rsplit('-', 1)[-1]}` first."
        )
    return client_id, app.get("service_principal_name")


def render_grants(template_path: Path, bundle_vars: dict[str, str], principal: str) -> list[str]:
    """Fill ${var.*} + <APP_SP_PRINCIPAL> in the template and return GRANT statements."""
    text = template_path.read_text()
    for name, value in bundle_vars.items():
        text = text.replace(f"${{var.{name}}}", value)
    text = text.replace("<APP_SP_PRINCIPAL>", principal)

    # Strip comment lines first (the header comments mention `${var.*}` literally and
    # would false-trip the unresolved-variable check), then split on ';'. Commented-out
    # optional grants (PR-writeback) are excluded because their lines start with '--'.
    sql = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))

    leftover = re.findall(r"\$\{var\.[^}]+\}", sql)
    if leftover:
        raise RuntimeError(f"Unresolved bundle variables in template: {sorted(set(leftover))}")

    return [s.strip() for s in sql.split(";") if s.strip().upper().startswith("GRANT")]


def execute_sql(statement: str, *, warehouse_id: str, profile: str) -> None:
    resp = databricks_api("post", "/api/2.0/sql/statements", profile=profile,
                          body={"warehouse_id": warehouse_id, "statement": statement,
                                "wait_timeout": "30s"})
    state = (resp.get("status") or {}).get("state")
    stmt_id = resp.get("statement_id")
    for _ in range(15):
        if state == "SUCCEEDED":
            return
        if state in {"FAILED", "CANCELED", "CLOSED"}:
            raise RuntimeError(f"SQL failed ({state}): "
                               f"{(resp.get('status') or {}).get('error', resp)}")
        time.sleep(2)
        resp = databricks_api("get", f"/api/2.0/sql/statements/{stmt_id}", profile=profile)
        state = (resp.get("status") or {}).get("state")
    raise RuntimeError(f"SQL did not finish in time: {statement}")


def grant_genie_can_run(space_id: str, principal: str, *, profile: str) -> None:
    """PATCH the Genie space ACL to add the SP with CAN_RUN (merges, doesn't clobber)."""
    databricks_api("patch", f"/api/2.0/permissions/genie/{space_id}", profile=profile,
                   body={"access_control_list": [
                       {"service_principal_name": principal, "permission_level": "CAN_RUN"}]})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Grant the app SP its post-deploy access.")
    p.add_argument("--target", choices=("dev", "prod"), default="dev")
    p.add_argument("--profile", default="DEFAULT", help="Databricks CLI profile.")
    p.add_argument("--warehouse-id", default=DEFAULT_WAREHOUSE_ID, help="Warehouse to run the GRANTs.")
    p.add_argument("--genie-space-id", default=None,
                   help="Genie space to grant CAN_RUN on (defaults to the target's; '' to skip).")
    p.add_argument("--dry-run", action="store_true", help="Print what would run; change nothing.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = TARGETS[args.target]
    template = REPO_ROOT / "sql" / "security" / f"grant_app_sp_genie_access_{args.target}.sql"
    genie_space_id = cfg["genie_space_id"] if args.genie_space_id is None else args.genie_space_id

    print(f"Resolving bundle variables for target '{args.target}' ...")
    bundle_vars = resolve_bundle_vars(args.target, args.profile)
    print(f"  catalog={bundle_vars.get('catalog')} "
          f"schema={bundle_vars.get('schema')}")

    print(f"Resolving service principal for app '{cfg['app']}' ...")
    principal, sp_name = resolve_sp_client_id(cfg["app"], args.profile)
    print(f"  SP: {principal}  ({sp_name})")

    stmts = render_grants(template, bundle_vars, principal)

    if args.dry_run:
        print("\n[dry-run] UC grants:")
        for s in stmts:
            print(f"  {s};")
        if genie_space_id:
            print(f"\n[dry-run] Genie CAN_RUN on space {genie_space_id} -> {principal}")
        return 0

    print(f"\nApplying UC grants (warehouse {args.warehouse_id}) ...")
    for s in stmts:
        execute_sql(s, warehouse_id=args.warehouse_id, profile=args.profile)
        print(f"  ✓ {s}")

    if genie_space_id:
        print(f"\nGranting CAN_RUN on Genie space {genie_space_id} ...")
        grant_genie_can_run(genie_space_id, principal, profile=args.profile)
        print("  ✓ Genie CAN_RUN")

    print("\nDone. Re-run scripts/validate_genie_sp_access.py to confirm SP access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
