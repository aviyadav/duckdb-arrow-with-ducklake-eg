# GizmoData — DuckDB + Arrow Flight SQL demo

A working project based on the *Data Engineering Central* article
**"DuckDB + ArrowFlight = GizmoData"**. It runs the open-source
**GizmoSQL** server (DuckDB wrapped in Apache Arrow Flight SQL) in Docker,
loads real Chicago Divvy bike-trip data, queries it from Python over the
ADBC driver, stress-tests it with concurrent writers + readers, and wires up
dbt and Airflow.

## What's included

| Path | What it is |
|------|------------|
| `docker-compose.yml` | Runs the `gizmodata/gizmosql` server (port 31337) |
| `scripts/download_divvy.py` | Downloads + unzips Divvy trip CSVs |
| `scripts/query_demo.py` | Analytical SQL over Arrow Flight SQL |
| `scripts/stress_test.py` | Concurrent write/read stress test |
| `scripts/iceberg_delta_check.py` | Iceberg + Delta Lake sanity check |
| `scripts/gizmo.py` | Shared connection config (env / `.env`) |
| `dbt/` | dbt project using the `dbt-gizmosql` adapter |
| `airflow/` | Airflow image (`Dockerfile`) + the two DAGs |

## Prerequisites

- Docker Desktop (running)
- Python 3.12+ (tested on 3.12) and `uv` (or plain `pip`)

## Quickstart

```bash
# 1. Configure credentials (dev defaults; change for anything non-local)
cp .env.example .env

# 2. Python environment + client libraries
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt  # optional

# 3. Start the GizmoSQL server
docker compose up -d

# 4. Fetch some Divvy data (Jan + Feb 2024 by default)
./.venv/Scripts/python.exe scripts/download_divvy.py 202604 202605 202606 202607 202608 202609

# 5. Run analytical queries over Arrow Flight SQL
./.venv/Scripts/python.exe scripts/query_demo.py
```

The server exposes Arrow Flight SQL on `localhost:31337` (TLS with a
self-signed cert, so clients pass `tls_skip_verify=True`). Its persisted
DuckDB database lives at `./data/divvy.duckdb`.

## Stress test (concurrent writers + readers)

```bash
./.venv/Scripts/python.exe scripts/stress_test.py            # defaults: 8 writers, 2 readers
./.venv/Scripts/python.exe scripts/stress_test.py --workers 4 --readers 1
./.venv/Scripts/python.exe scripts/stress_test.py --skip-embedded   # Part B only
```

- **Part A** opens one local DuckDB file from N processes directly —
  only one read-write process can hold the file, so the rest fail.
- **Part B** gives each of N processes its own ADBC session and ingests
  Arrow batches into GizmoSQL while reader processes poll the row count.
  Reads are never blocked and the row count never goes backwards.

## dbt

```bash
cd dbt
set -a && . ../.env && set +a        # load GIZMOSQL_PASSWORD for profiles.yml
../.venv/Scripts/dbt.exe run   --profiles-dir .
../.venv/Scripts/dbt.exe test  --profiles-dir .
```

`profiles.yml` points dbt at GizmoSQL over Arrow Flight SQL. The staging
model (`models/staging/stg_trips.sql`) selects from the `trips` view over
the CSV files and is verified with `unique` / `not_null` tests on `ride_id`.

## Iceberg / Delta Lake

```bash
./.venv/Scripts/python.exe scripts/iceberg_delta_check.py
```

- **Iceberg**: written *and* read back through GizmoSQL via DuckDB's
  `iceberg` extension.
- **Delta Lake**: written on the host with `deltalake` (the way Spark /
  Delta pipelines produce tables), then read through GizmoSQL via
  `delta_scan`. Note: DuckDB's Delta extension is read-only in these
  versions (no `COPY ... FORMAT DELTA`), so the write side uses `deltalake`.

## Airflow

`airflow/` runs a lightweight, single-container Airflow (scheduler + webserver +
SQLite metadata DB) on the same Docker network as GizmoSQL. The image installs
`adbc-driver-gizmosql` for the Python DAG, and dbt in an isolated virtualenv for
the dbt DAG.

### What the DAGs do

| DAG | Schedule | Steps |
| --- | --- | --- |
| `divvy_daily` | `@daily` | `load_raw` creates a `raw_trips` view over `/opt/gizmosql/data/*.csv` inside GizmoSQL; `station_daily` aggregates trips per start station per day. |
| `divvy_dbt` | `@daily` | `dbt run`, then `dbt test`, on the mounted `dbt/` project. |

Both read the `gizmosql_default` Airflow connection, created from
`AIRFLOW_CONN_GIZMOSQL_DEFAULT` in `docker-compose.yml` (host `gizmosql`,
port `31337`, credentials taken from `.env`).

### Build and start

```bash
docker compose build airflow     # first build pulls the base image; a few minutes
docker compose up -d airflow
docker compose logs -f airflow   # wait for the webserver to bind on 8080
```

Then open <http://localhost:8080>. Airflow's `standalone` command creates an
`admin` user and prints its generated password once, at first startup:

```bash
docker compose logs airflow | grep "Password for user 'admin'"
```

```
ZcAg3KMA8xu2TW7A
```

No password is stored in this repository. Removing the container and
starting it again rotates it.

### View and run the DAGs

DAGs are created unpaused (`AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=false`),
so the `@daily` schedule is live as soon as the scheduler starts.

```bash
# what the scheduler loaded
docker compose exec airflow airflow dags list

# trigger a run now instead of waiting for the schedule
docker compose exec airflow airflow dags trigger divvy_daily
docker compose exec airflow airflow dags trigger divvy_dbt

# recent runs, then the task states of a given run
docker compose exec airflow airflow dags list-runs divvy_daily
docker compose exec airflow airflow tasks states-for-dag-run divvy_daily <run_id>
```

### Confirm the results landed in DuckDB

```bash
python scripts/query_demo.py    # creates/refreshes the trips view
```

`station_daily` and the dbt view `stg_trips` are then queryable over Arrow
Flight SQL like any other table.

### Notes and limits

- One container with `LocalExecutor` and a SQLite metadata DB: right for a
  local demo, not for production. The metadata DB is ephemeral, so
  `docker compose down` resets DAG history; the DuckDB data in `./data` is
  untouched.
- Both DAGs use `catchup=False`, so Airflow runs only the current interval and
  never backfills history.
- `divvy_dbt` needs the `trips` view that `scripts/query_demo.py` creates - run
  that once before triggering the dbt DAG.
- The published Divvy extracts contain ~35 `ride_id`s that appear twice (the
  same trip re-published across monthly files). `stg_trips` deduplicates
  them so `dbt test` passes; `divvy_daily` aggregates the raw rows as-is.
- Stop everything with `docker compose down`.

## Configuration

Credentials are read from environment variables or an optional `.env` at
the project root — never hardcoded in source. See `.env.example`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GIZMOSQL_USERNAME` | `gizmosql_user` | server username |
| `GIZMOSQL_PASSWORD` | (required) | server password |
| `GIZMOSQL_URI` | `gizmosql://localhost:31337` | client connection URI |
| `GIZMOSQL_TLS_SKIP_VERIFY` | `1` | skip self-signed cert check |
| `DIVVY_DATA_DIR` | `./data` | host CSV dir for the stress test |

## Teardown

```bash
docker compose down            # stop the container
docker compose down -v         # also remove the persisted database volume
```
