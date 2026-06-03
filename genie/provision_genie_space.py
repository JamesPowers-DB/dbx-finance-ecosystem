#!/usr/bin/env python3
"""Provision the *Strategic Spend Analytics* Genie space — local CLI (ad-hoc).

The CANONICAL provisioning path is the in-bundle job task
(``genie/provision_genie_space_job.py``, run via ``databricks bundle run
provision_genie`` / the ``setup`` job). This CLI is kept for local, ad-hoc use;
both share the exact same definition in ``genie/genie_space_def.py``.

Idempotent by TITLE: pass ``--space-id`` to update in place, ``--recreate`` to
delete + recreate, or neither to create fresh. Auth is delegated to the
Databricks CLI (``databricks api ...``) so this carries no credentials.

    python genie/provision_genie_space.py --target dev --warehouse-id <wh> \
        --parent-path /Users/me@databricks.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile

from genie_space_def import build_serialized_space, DEFAULT_DESCRIPTION, space_title


def build_outer_payload(*, title, description, warehouse_id, serialized_space, parent_path):
    payload = {"title": title, "description": description, "warehouse_id": warehouse_id,
               "serialized_space": json.dumps(serialized_space)}
    if parent_path:
        payload["parent_path"] = parent_path
    return payload


def databricks_api(method: str, path: str, *, profile: str, body: dict | None = None) -> dict:
    args = ["databricks", "api", method, path, "--profile", profile]
    if body is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(body, fh)
            args += ["--json", f"@{fh.name}"]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"`{' '.join(args)}` failed:\n{proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Provision the Strategic Spend Analytics Genie space (CLI).")
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--target", choices=("dev", "prod"), default="prod")
    p.add_argument("--catalog", default=None, help="Defaults to the target's catalog.")
    p.add_argument("--schema", default="finance_spend_analytics")
    p.add_argument("--warehouse-id", default="", help="Serving warehouse for the space.")
    p.add_argument("--title", default=None, help="Override the per-target title.")
    p.add_argument("--parent-path", default=None, help="Workspace folder for a NEW space.")
    p.add_argument("--space-id", default=None, help="Existing space id to PATCH (or DELETE with --recreate).")
    p.add_argument("--recreate", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    catalog = a.catalog or "main"
    title = a.title or space_title(a.target)
    serialized = build_serialized_space(catalog, a.schema)
    payload = build_outer_payload(title=title, description=DEFAULT_DESCRIPTION,
                                  warehouse_id=a.warehouse_id, serialized_space=serialized,
                                  parent_path=a.parent_path)
    if a.dry_run:
        print(json.dumps(serialized, indent=2))
        print(f"\ntitle={title} catalog={catalog} "
              f"tables={[t['identifier'] for t in serialized['data_sources']['tables']]}")
        return 0

    if a.space_id and not a.recreate:
        print(f"PATCH existing space {a.space_id} ...")
        databricks_api("patch", f"/api/2.0/genie/spaces/{a.space_id}", profile=a.profile, body=payload)
        print(f"Updated: {a.space_id}")
        return 0
    if a.space_id and a.recreate:
        print(f"DELETE space {a.space_id} ...")
        databricks_api("delete", f"/api/2.0/genie/spaces/{a.space_id}", profile=a.profile)

    print("POST new space ...")
    resp = databricks_api("post", "/api/2.0/genie/spaces", profile=a.profile, body=payload)
    print(f"Created space_id: {resp.get('space_id')}  title: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
