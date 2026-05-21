#!/usr/bin/env python3
"""Validate Genie + UC access for Databricks App service principal.

This script performs repeatable checks for both dev/prod apps:
1) App scopes + warehouse resource binding
2) Genie Conversation API access using app SP token
3) SQL probe queries on required UC objects using same SP token
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


REQUIRED_SCOPES = {
    "sql",
    "postgres",
    "serving.serving-endpoints",
    "dashboards.genie",
}

PROBE_OBJECTS = (
    "gold.fact_invoices",
    "gold.dim_supplier",
    "gold.fact_purchase_requests",
    "gold.fact_purchase_orders",
    "gold.fact_cost_savings",
    "gold.dim_spend_category",
    "silver.contract_inbound",
    "silver.sourcing_event",
)


@dataclass
class AppTarget:
    app_name: str
    catalog: str


def run_cmd(args: list[str]) -> dict:
    proc = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def ensure_https(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host.startswith("http"):
        return f"https://{host}"
    return host


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {payload[:600]}") from exc


def get_app_details(profile: str, app_name: str) -> dict:
    return run_cmd(["databricks", "apps", "get", app_name, "--profile", profile, "--output", "json"])


def extract_warehouse_id(app_details: dict) -> str:
    for resource in app_details.get("resources", []):
        sql_wh = resource.get("sql_warehouse")
        if sql_wh and sql_wh.get("id"):
            return sql_wh["id"]
    raise RuntimeError("No SQL warehouse resource binding found on app.")


def check_scopes(app_details: dict) -> tuple[bool, set[str], set[str]]:
    present = set(app_details.get("user_api_scopes", []))
    missing = REQUIRED_SCOPES - present
    return not missing, present, missing


def get_sp_token(host: str, client_id: str, client_secret: str) -> str:
    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": "all-apis",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(
        f"{host}/oidc/v1/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("OIDC token response did not include access_token.")
    return token


def genie_probe(host: str, space_id: str, token: str, question: str) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    start = request_json(
        f"{host}/api/2.0/genie/spaces/{space_id}/start-conversation",
        method="POST",
        body={"content": question},
        headers=headers,
    )
    conv_id = start.get("conversation_id")
    msg_id = start.get("message_id")
    if not conv_id or not msg_id:
        return False, f"Failed to start conversation: {start}"

    for _ in range(45):
        time.sleep(2)
        msg = request_json(
            f"{host}/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}",
            headers=headers,
        )
        status = msg.get("status")
        if status == "COMPLETED":
            return True, "COMPLETED"
        if status in {"FAILED", "CANCELLED"}:
            return False, f"{status}: {msg}"
        if msg.get("error_code"):
            return False, f"{msg.get('error_code')}: {msg.get('message')}"
    return False, "Timed out waiting for Genie completion."


def sql_statement(host: str, token: str, warehouse_id: str, statement: str) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return request_json(
        f"{host}/api/2.0/sql/statements",
        method="POST",
        headers=headers,
        body={"warehouse_id": warehouse_id, "statement": statement, "wait_timeout": "50s"},
        timeout=60,
    )


def probe_uc_objects(host: str, token: str, warehouse_id: str, catalog: str) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for obj in PROBE_OBJECTS:
        full_name = f"{catalog}.{obj}"
        stmt = f"SELECT COUNT(*) AS row_count FROM {full_name}"
        try:
            resp = sql_statement(host, token, warehouse_id, stmt)
            status = resp.get("status", {}).get("state", "UNKNOWN")
            if status == "SUCCEEDED":
                results.append((full_name, True, "ok"))
            else:
                results.append((full_name, False, f"status={status} response={resp}"))
        except Exception as exc:  # noqa: BLE001
            results.append((full_name, False, str(exc)))
    return results


def validate_target(
    *,
    profile: str,
    host: str,
    space_id: str,
    sp_client_id: str,
    sp_client_secret: str,
    target: AppTarget,
    question: str,
) -> int:
    failures = 0
    print(f"\n=== Validating {target.app_name} ({target.catalog}) ===")
    app = get_app_details(profile, target.app_name)
    ok_scopes, present_scopes, missing_scopes = check_scopes(app)
    print(f"Scopes present: {sorted(present_scopes)}")
    if not ok_scopes:
        failures += 1
        print(f"[FAIL] Missing required scopes: {sorted(missing_scopes)}")
    else:
        print("[OK] Required app scopes present")

    warehouse_id = extract_warehouse_id(app)
    print(f"Warehouse binding: {warehouse_id}")

    token = get_sp_token(host, sp_client_id, sp_client_secret)
    genie_ok, genie_msg = genie_probe(host, space_id, token, question)
    if not genie_ok:
        failures += 1
        print(f"[FAIL] Genie probe failed: {genie_msg}")
    else:
        print(f"[OK] Genie probe: {genie_msg}")

    uc_results = probe_uc_objects(host, token, warehouse_id, target.catalog)
    for full_name, passed, detail in uc_results:
        if passed:
            print(f"[OK] UC probe {full_name}")
        else:
            failures += 1
            print(f"[FAIL] UC probe {full_name}: {detail}")

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Genie SP access for app dev/prod targets.")
    parser.add_argument("--profile", default="e2-demo-field-eng", help="Databricks CLI profile.")
    parser.add_argument("--host", required=True, help="Workspace host (with or without https://).")
    parser.add_argument("--genie-space-id", required=True, help="Genie Space ID used by the app.")
    parser.add_argument("--sp-client-id", required=True, help="App service principal client ID.")
    parser.add_argument("--sp-client-secret", required=True, help="App service principal client secret.")
    parser.add_argument(
        "--question",
        default="What is our total spend by category this year?",
        help="Validation question for Genie.",
    )
    parser.add_argument("--dev-app", default="helios-sourcing-portal-dev", help="Dev app name.")
    parser.add_argument("--prod-app", default="helios-sourcing-portal-prod", help="Prod app name.")
    parser.add_argument("--dev-catalog", default="horizontal_finance_dev", help="Dev catalog.")
    parser.add_argument("--prod-catalog", default="horizontal_finance", help="Prod catalog.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    host = ensure_https(args.host)
    targets = [
        AppTarget(app_name=args.dev_app, catalog=args.dev_catalog),
        AppTarget(app_name=args.prod_app, catalog=args.prod_catalog),
    ]
    failures = 0
    for target in targets:
        try:
            failures += validate_target(
                profile=args.profile,
                host=host,
                space_id=args.genie_space_id,
                sp_client_id=args.sp_client_id,
                sp_client_secret=args.sp_client_secret,
                target=target,
                question=args.question,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] Target {target.app_name} validation crashed: {exc}")

    if failures:
        print(f"\nValidation finished with {failures} failure(s).")
        return 1
    print("\nValidation finished successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
