# Data Lakehouse with SQLMesh and DuckLake

Tooling for a minimalist data lab running on top of DuckLake, backed by RustFS and
PostgreSQL.

This is a port of the [datalab](https://github.com/DataLabTechTV/datalab) project
described in [The Data Lakehouse with dbt and DuckLake](https://datalabtechtv.com/posts/data-lakehouse-dbt-ducklake/),
with three substitutions:

| Original | This project |
| --- | --- |
| MinIO (S3-compatible object storage) | **RustFS** |
| dbt (transformations) | **SQLMesh** |
| SQLite (DuckLake metadata catalog, per data mart) | **PostgreSQL** (one database, one schema per catalog) |

Everything the article describes is kept: the dated `raw/` ingestion layout, the
`stage` and mart catalogs, the `dlctl` CLI, the parquet exports, and the full model
set (Deezer social networks, Million Song Dataset, The Atlas of Economic Complexity,
depression detection).

**Scope:** the upstream repository also carries experimental modules that do not
touch MinIO, dbt or the catalog — `ml/` (PyTorch training), `graph/` (Kuzu graph
analytics), the Kafka/Ollama/MLflow services, and the Terraform stacks. Those are not
part of this lakehouse port, so the container stack here is RustFS and PostgreSQL
only.

## Architecture

```
        ingest                 transform                   export
   ┌──────────────┐        ┌──────────────────┐      ┌──────────────────┐
   │  RustFS S3   │        │  SQLMesh         │      │  RustFS S3       │
   │  s3://.../raw│──────▶ │  DuckDB engine   │────▶ │  s3://.../exports│
   └──────────────┘        │  DuckLake tables │      └──────────────────┘
                           └────────┬─────────┘
                                    │ metadata (schemas, snapshots, statistics)
                              ┌─────▼──────┐
                              │ PostgreSQL │  DuckLake catalogs: stage,
                              │ lakehouse  │  secure_stage, graphs, analytics
                              └────────────┘
```

- **RustFS** stores raw datasets, the DuckLake-managed parquet files, and the
  exported datasets. It is S3-compatible, so DuckDB's `httpfs` and `boto3` both talk
  to it directly.
- **DuckDB** is the query engine. A local `local/engine.duckdb` file holds the
  SQLMesh state; the DuckLake catalogs are attached to it on every connection.
- **PostgreSQL** holds DuckLake metadata: one schema per catalog inside the
  `lakehouse` database. This replaces the per-mart SQLite files from the original
  project, and also makes `pg_dump` backups possible.
- **DuckLake** provides ACID tables, snapshots and time travel on top of plain
  parquet files.
- **SQLMesh** runs the transformations and the audits (the SQLMesh equivalent of the
  dbt tests).

## Object storage layout

| Prefix | Contents |
| --- | --- |
| `raw/` | Ingested datasets, one dated directory per ingestion (`<dataset>/<date>/<time>/`) |
| `stage/` | DuckLake-managed parquet for the `stage` catalog |
| `secure-stage/` | DuckLake-managed parquet for the encrypted `secure_stage` catalog |
| `marts/graphs/` | DuckLake-managed parquet for the `graphs` mart catalog |
| `marts/analytics/` | DuckLake-managed parquet for the `analytics` mart catalog |
| `exports/` | Datasets exported out of the marts, laid out as `nodes/` and `edges/` |
| `backups/` | `pg_dump` backups of the DuckLake metadata catalog |

Every ingestion and export also writes a `manifest.json` next to its dated
directory, so `latest` is always resolvable without listing everything.

## DuckLake catalogs

| Catalog | PostgreSQL schema | Purpose |
| --- | --- | --- |
| `stage` | `stage` | Cleaned, typed source data |
| `secure_stage` | `secure_stage` | Encrypted catalog (`ENCRYPTED 1`) |
| `graphs` | `graphs` | Graph marts: nodes and edges |
| `analytics` | `analytics` | Analytical marts |

Adding a mart only requires two environment variables: a
`PSQL_CATALOG_<NAME>_MART_SCHEMA` and a matching `S3_<NAME>_MART_PREFIX`. Both the
`init.sql` generator and the SQLMesh configuration pick them up automatically.

## Requirements

- [uv](https://docs.astral.sh/uv/) and Python 3.13
- [just](https://github.com/casey/just) (installed with the project dependencies)
- RustFS reachable over S3 (default `localhost:9000`, console on `localhost:9001`)
- PostgreSQL reachable (default `127.0.0.1:5432`)
- The DuckDB CLI for exploring the lakehouse manually
- The PostgreSQL client tools (`pg_dump`, `pg_restore`) for `dlctl backup`
- Docker, only if you want the bundled RustFS/PostgreSQL services

## Quick start

```sh
# 1. Install dependencies
uv sync

# 2. Configure the environment
cp .env.example .env
#    Point S3_* at your RustFS instance and PSQL_CATALOG_* at your PostgreSQL instance.

# 3. Create the RustFS bucket and the PostgreSQL catalog database
uv run just init

# 4. Load the small Music Taste fixtures (no Kaggle account needed)
uv run just seed

# 5. Run the pipeline
uv run just graphrag-transform
uv run just graphrag-test
uv run just graphrag-export
```

Every recipe invokes the project tooling through `uv run`, so the commands above work
whether or not the virtual environment is active in your shell.

`just init` creates the bucket, creates the catalog database, and writes
`local/init.sql` (which `dlctl tools generate-init-sql` also writes on its own).

The fixture path above exercises the whole pipeline in seconds. The real datasets are
ingested the same way, they are just bigger:

```sh
just graphrag-ingest        # Deezer social networks + Million Song Dataset (Kaggle)
just econ-compnet-ingest    # The Atlas of Economic Complexity (DataCite/Dataverse)
just mlops-ingest           # Depression detection datasets (Hugging Face)
```

### Windows notes

- Recipes are POSIX shell scripts, and the justfile runs them with `sh`. `bash` is
deliberately avoided because on Windows it can resolve to the WSL launcher
(`C:\Windows\System32\bash.exe`), which cannot see the project tooling. With Git for
Windows installed, `sh` resolves to its POSIX shell (`<Git>\usr\bin\sh.exe`).
- Project commands go through `uv run`, so `uv run just <recipe>` works from
PowerShell without activating anything. If you prefer an active environment, use
`source .venv/Scripts/activate` in Git Bash or `.venv\Scripts\Activate.ps1` in
PowerShell, then run `just <recipe>`.
- Run `uv sync` from the same environment you intend to use. A Windows virtual
environment is not usable from a WSL shell: if you want to work inside WSL, run
`uv sync` there as well.

## Exploring the lakehouse

```sh
just lakehouse
```

opens the DuckDB CLI with `local/init.sql` preloaded, which installs the extensions,
creates the RustFS and PostgreSQL secrets, and attaches every DuckLake catalog.

```
-- snapshot and version information; the changelog is the `changes` column of
-- snapshots(), which has no `snapshot_changes()` companion
SELECT * FROM graphs.current_snapshot();
SELECT * FROM graphs.snapshots() ORDER BY snapshot_id DESC LIMIT 10;
SELECT snapshot_id, e.key AS change, unnest(e.value) AS object
FROM (
    SELECT snapshot_id, unnest(map_entries(changes)) AS e
    FROM graphs.snapshots()
)
ORDER BY snapshot_id DESC
LIMIT 10;

-- table information, and where the catalog keeps its metadata and files
SELECT * FROM graphs.table_info();
SELECT * FROM graphs.settings();
SELECT * FROM graphs.options();
```

## CLI

| Command | Description |
| --- | --- |
| `dlctl ingest dataset <url\|name>` | Ingest a Kaggle/Hugging Face dataset, or create an empty dated directory (`--manual`), or download a known template (`-t atlas`) |
| `dlctl ingest ls [--all]` / `prune` | List or prune ingested datasets |
| `dlctl transform [-m SELECTOR]` | Plan and apply SQLMesh models (with upstream/downstream selectors) |
| `dlctl test [-m SELECTOR]` | Run the SQLMesh audits |
| `dlctl export dataset <catalog> <schema>` | Export a mart to parquet in object storage |
| `dlctl export ls` / `prune` | List or prune exported datasets |
| `dlctl docs generate` / `serve` | Render the model DAG, or serve it on port 8080 |
| `dlctl tools generate-init-sql --path local/init.sql` | Write the DuckDB init script |
| `dlctl tools create-bucket` / `init-catalog` | Create the RustFS bucket / PostgreSQL database |
| `dlctl tools catalog-info` | Show the DuckLake snapshot per catalog |
| `dlctl backup create` / `ls` / `restore` | Back up and restore the metadata catalog |
| `dlctl cache clean` / `df` | Manage the local cache |

`dlctl --help` lists everything. Selectors follow SQLMesh syntax, for example
`+graphs.music_taste.*` (that model set plus its upstream).

## Transformations

`transform/` is a SQLMesh project:

```
transform/
├── config.py       # gateways, DuckLake catalogs, RustFS secret, variables
├── audits/         # generic + project audits (the dbt tests)
├── macros/         # Jinja macros for the Deezer loaders
└── models/
    ├── stage/      # stage.dsn.*, stage.msdsl.*, stage.taoec.*, stage.dd.*
    └── marts/      # graphs.* and analytics.*
```

Model names carry over from the dbt project unchanged, as
`<catalog>.<schema>.<table>`, so `stage.dsn.hr_edges` and
`graphs.music_taste.nodes_genres` are addressed exactly as before.

### How the port maps dbt concepts to SQLMesh

| dbt | SQLMesh |
| --- | --- |
| `dbt run -m "+marts..."` | `dlctl transform -m "+graphs.music_taste.*"` |
| `dbt test` | `dlctl test` (audits) |
| `not_null`, `unique`, `relationships`, `dbt_utils.unique_combination_of_columns` | `not_null`, `unique_values`, `relationships`, `unique_combination_of_columns` |
| schema.yml descriptions | `description` / `column_descriptions` |
| `env_var("RAW__X", "NOT_FOUND")` | `@RAW__X` variables, seeded with a placeholder until the dataset is ingested |
| `profiles.yml` targets | `transform/config.py` gateways |
| `dbt docs generate/serve` | `dlctl docs generate` (DAG) and `dlctl docs serve` |

### Notes on the SQLMesh implementation

- **Mart objects are DuckLake tables.** `virtual_environment_mode` is set to
  `DEV_ONLY`, so in prod every model is materialized under its own name
  (`graphs.music_taste.nodes_genres`), exactly as dbt did, instead of being a view on
  top of a hidden physical layer.
- **Queries generated by Jinja use `JINJA_QUERY_BEGIN` / `JINJA_QUERY_END`.**
  SQLMesh only evaluates Jinja inside these blocks, so the Deezer loader macros are
  wrapped in them.
- **Ingested paths are SQLMesh variables** (`@RAW__<DATASET>__<FILE>`), resolved by
  `dlctl` from the ingestion manifests before SQLMesh starts. A new ingestion changes
  the variables, so SQLMesh re-renders and re-runs the affected models. Datasets that
  have not been ingested yet fall back to a `NOT_FOUND` placeholder so the project can
  still be loaded and a single mart can be built on its own.
- **Audits run per model.** SQLMesh evaluates audits while the plan is being applied,
  before the environment's tables are finalized, so the original cross-model
  "unique node ids" test is expressed as a `unique_values` audit on each node model.
  Node IDs are drawn from one shared sequence (`max(node_id) + row_number()`), so
  uniqueness within each model keeps IDs unique across the graph;
  `tests/test_catalog.py` asserts the cross-model invariant against real data.
- **Column descriptions stay in SQLMesh metadata** and are not pushed to the catalog
  as comments (`register_comments = False`); they show up in the rendered DAG.
- **`dlctl docs serve`** serves the rendered DAG with a small local HTTP server,
  because SQLMesh's web UI is deprecated.
- **`dlctl backup`** uses `pg_dump`/`pg_restore`, which is only possible because the
  catalog now lives in PostgreSQL.

## Infra

```sh
just infra-provision-local   # RustFS (9000/9001) + PostgreSQL (5432) in Docker
just infra-destroy-local
```

## Tests

```sh
pytest
```

Tests that need RustFS and PostgreSQL are skipped automatically when either is not
reachable. The suite covers the storage layer (manifests, dated directories, exports
readable back from S3), the DuckLake catalog, the fixture shapes, and the SQLMesh
project (model names, kinds, audits, variable resolution).
