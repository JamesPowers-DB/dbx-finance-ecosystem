---
name: dbx-bundle-medallion-project
description: Scaffold a Databricks Asset Bundle (DAB) project using the bundle root + databricks.yml + resources/*.yml split pattern. Use when starting a new Databricks demo/project that needs Unity Catalog + Lakeflow pipelines + Databricks Apps managed as one bundle. Locks the folder layout and bundle shape; leaves domain/table content flexible.
---

# Databricks Asset Bundle — root + resources split

A reference layout for DAB projects that bundle Unity Catalog assets,
Lakeflow pipelines, jobs, and Databricks Apps together. The pattern
keeps `databricks.yml` slim and pushes per-domain resource definitions
into `resources/*.yml` so each concern is a single file you can read
end-to-end.

## When to use this skill

- Starting a new Databricks project where everything (catalog, schemas,
  pipelines, jobs, apps) is owned by one repo and deployed by one bundle.
- Migrating a workspace-clicked-together demo to bundle-as-code.
- Adding a new domain (e.g. another pipeline, another app) to an existing
  bundle that already follows this shape.

If the project only needs one job or one notebook, use a flat bundle
instead — this layout earns its complexity once you have ≥2 resource
domains.

---

## Folder layout (locked)

```
<project-root>/
├── databricks.yml                  bundle root, variables, sync, targets
├── resources/                      one file per resource domain
│   ├── catalog.yml                 catalog + schemas + volumes
│   ├── pipeline.yml                Lakeflow pipeline(s) + library file refs
│   └── app.yml                     Databricks Apps (one per app, all here)
├── jobs/                           jobs each in their own file
│   └── <job_name>.yml
├── pipelines/                      pipeline source files (SQL or notebooks)
├── ml/                             notebooks referenced by jobs
├── sql/                            ad-hoc SQL, metric views, genie assets
├── dashboards/                     dashboard build scripts / definitions
├── apps/                           one folder per Databricks App
│   └── <app_name>/                 see dbx-app-fastapi-react skill
├── data/                           seed data + generators
├── docs/                           architecture, demo script, glossary
└── .gitignore
```

Why split this way:
- **`resources/` vs `jobs/`** — jobs change frequently (cron, retries,
  task DAGs); keeping them in their own directory means `git log -- jobs/`
  shows scheduling churn cleanly. `databricks.yml` includes both globs.
- **`resources/catalog.yml` separate from `pipeline.yml`** — catalogs and
  schemas are foundational; pipelines reference them. Splitting keeps
  destructive changes (catalog renames) visible in their own file.
- **One file per app in `resources/app.yml`** is fine when apps share env
  conventions; split if they diverge significantly.

---

## `databricks.yml` (root) — the shape

```yaml
bundle:
  name: <project-name>             # e.g. dbx-payment-revenue-monitor

include:
  - resources/*.yml                # catalog, pipeline, app
  - jobs/*.yml                     # one job per file

# Apps are deployed via source_code_path → workspace files. The frontend
# build output (dist/) must be on disk before `databricks bundle deploy`,
# and this sync rule makes it part of the bundle artifact.
sync:
  include:
    - apps/*/frontend/dist/**

variables:
  catalog:
    description: Unity Catalog name for this project
    default: <project>_demo
  schema_raw:
    description: Raw landing zone (volume + Delta-share tables)
    default: raw_data
  schema_bronze:
    default: bronze
  schema_silver:
    default: silver
  schema_gold:
    default: gold
  schema_ml:
    default: ml
  raw_volume:
    description: Managed volume name under the raw_data schema
    default: files

targets:
  prod:
    mode: production
    workspace:
      host: https://<workspace>.cloud.databricks.com
      profile: DEFAULT
      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}
```

Rules:
- **Variables go at the top level**, not inside targets, when they are
  the same per-environment but you still want them parameterizable.
  Override per target only when values genuinely differ.
- **`sync.include` for app dist/**: Vite outputs to `apps/<app>/frontend/dist/`
  which is `.gitignore`d. Without this rule the deployed app has no
  static assets. Run `apps/build_frontends.sh` before
  `databricks bundle deploy` (see dbx-app-fastapi-react skill).
- **`mode: production`** on prod target — locks the bundle to
  production semantics (no dev prefix, schedules unpaused, etc.).
- **`profile: DEFAULT`** — assumes the user has a CLI profile of
  that name. Document the profile name in the README.

Optional: add a `dev` target with `mode: development` if the demo needs
per-user dev workspaces. Most single-author demo bundles get away with
prod-only.

---

## `resources/catalog.yml` — catalog + schemas + volumes

```yaml
resources:
  catalogs:
    <project>_demo:
      name: ${var.catalog}
      comment: <one-line description of what this catalog is for>

  schemas:
    raw_data:
      catalog_name: ${var.catalog}
      name: ${var.schema_raw}
      comment: Raw landing zone — files in the managed volume + Delta-shared inputs
    bronze:
      catalog_name: ${var.catalog}
      name: ${var.schema_bronze}
      comment: Streaming ingestion with audit columns, one-to-one with sources
    silver:
      catalog_name: ${var.catalog}
      name: ${var.schema_silver}
      comment: Cleaned, deduplicated, conformed — per source, no cross-source joins
    gold:
      catalog_name: ${var.catalog}
      name: ${var.schema_gold}
      comment: Denormalized detail tables joined across sources for business users
    ml:
      catalog_name: ${var.catalog}
      name: ${var.schema_ml}
      comment: ML feature tables and registered models

  volumes:
    raw_files:
      catalog_name: ${var.catalog}
      schema_name: ${var.schema_raw}
      name: ${var.raw_volume}
      volume_type: MANAGED
      comment: Landing zone for seed CSV + JSON files
```

Rules:
- The catalog key (`<project>_demo`) is the bundle-internal handle, the
  `name:` field is the actual UC name. They can match, but the key is
  what other resources reference if needed.
- **Comment every schema** — DAB comments become UC catalog comments
  visible in the catalog explorer. They're free documentation.
- **Use comments to encode the medallion contract**: bronze = audit + 1:1,
  silver = cleaned + per-source, gold = joined + business-facing.

---

## `resources/pipeline.yml` — Lakeflow pipeline

```yaml
resources:
  pipelines:
    <project>_pipeline:
      name: <project>-pipeline
      catalog: ${var.catalog}
      schema: ${var.schema_bronze}     # default schema for unqualified refs
      serverless: true
      continuous: false
      development: false
      photon: true
      libraries:
        - file:
            path: ../pipelines/bronze/<source_a>.sql
        - file:
            path: ../pipelines/bronze/<source_b>.sql
        - file:
            path: ../pipelines/silver/<source_a>.sql
        - file:
            path: ../pipelines/silver/<source_b>.sql
        - file:
            path: ../pipelines/gold/<entity>.sql
        # ... etc
      configuration:
        # These show up as ${catalog}, ${schema_bronze}, ... inside SQL
        catalog: ${var.catalog}
        schema_raw: ${var.schema_raw}
        schema_bronze: ${var.schema_bronze}
        schema_silver: ${var.schema_silver}
        schema_gold: ${var.schema_gold}
        raw_volume: ${var.raw_volume}
```

Rules:
- **Always serverless + photon** for new pipelines unless you have a
  specific reason not to.
- **`configuration` block is the bridge** — variables defined there
  appear inside SQL files as `${catalog}`, `${schema_bronze}`, etc.
  Don't hardcode catalog/schema names in pipeline SQL.
- **List every library file explicitly**, not by glob. Explicit list
  doubles as the dependency manifest in code review.

---

## `resources/app.yml` — Databricks Apps

```yaml
resources:
  apps:
    <app-key>:
      name: '<app-name>'                          # URL-safe, kebab-case
      description: '<one-line user-facing description>'
      source_code_path: ../apps/<app_folder>      # relative to resources/
      config:
        env:
          - name: <PROJECT>_CATALOG
            value: ${var.catalog}
      resources:
        - name: 'warehouse'
          sql_warehouse:
            id: <warehouse-id>
            permission: CAN_USE
```

Rules:
- **`source_code_path` is relative to the resources file**. The convention
  `../apps/<folder>` matches the canonical layout above.
- **`name:` becomes the deploy handle** (kebab-case URL slug); the YAML key
  is just the bundle-internal handle.
- **Pass project-wide env via `config.env`** — typically a catalog name.
  The app reads it through `os.environ`. App-specific secrets go in
  Databricks-managed secret scopes, not here.
- **`sql_warehouse` resource auto-injects `DATABRICKS_WAREHOUSE_ID`**
  into the app's runtime environment when the app declares
  `valueFrom: warehouse` in its `app.yaml` (see dbx-app-fastapi-react skill).
- All apps for a project go in one `app.yml` file; split only if their
  resource needs diverge sharply.

---

## `jobs/<name>.yml` — one job per file

```yaml
resources:
  jobs:
    <job_key>:
      name: <project>-<job_key>
      description: >
        <Multi-line description of what the job does and why it exists.>
      schedule:
        quartz_cron_expression: 0 30 6 * * ?
        timezone_id: America/New_York
        pause_status: UNPAUSED
      max_concurrent_runs: 1
      email_notifications: {}
      tasks:
        - task_key: <step_1>
          notebook_task:
            notebook_path: ../ml/notebooks/01_<step_1>.py
            source: WORKSPACE

        - task_key: <step_2>
          depends_on:
            - task_key: <step_1>
          notebook_task:
            notebook_path: ../ml/notebooks/02_<step_2>.py
            source: WORKSPACE

      queue:
        enabled: true
```

Rules:
- **One file per job, named after the job** (`attrition_scoring.yml`,
  not `jobs.yml`). Easy to find, easy to diff, easy to delete.
- **Description is multi-line** when the job has nuance worth capturing
  (e.g. "training inline for demo; split weekly in prod").
- **`notebook_path` relative to the jobs file** — `../ml/notebooks/...`
  is the canonical path because notebooks live in `ml/` at project root.
- **`queue.enabled: true`** by default — prevents skipped runs when one
  is still in progress.

---

## Deploy workflow

```bash
# 1. Build frontends (if any apps are present)
./apps/build_frontends.sh

# 2. Validate the bundle
databricks bundle validate -t prod

# 3. Deploy
databricks bundle deploy -t prod

# 4. Run the pipeline / job once if needed
databricks bundle run <project>_pipeline -t prod
databricks bundle run <job_key> -t prod
```

The `apps/build_frontends.sh` step is required because the bundle's
`sync.include` rule expects `apps/*/frontend/dist/**` to exist on disk.

---

## What this skill is NOT

- **Not opinionated about pipeline SQL content** — the medallion layering
  contract is documented above (bronze/silver/gold definitions in schema
  comments) but the SQL itself can be whatever the project needs.
- **Not opinionated about job content** — job DAGs vary widely; the layout
  rule is "one file per job, in `jobs/`."
- **Not a Databricks App skill** — for the FastAPI + React + design-system
  app pattern, see `dbx-app-fastapi-react`.
