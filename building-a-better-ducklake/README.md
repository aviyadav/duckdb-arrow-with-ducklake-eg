# Building a Better DuckLake

A small DuckDB/DuckLake medallion-pipeline project that demonstrates how raw,
partitioned Parquet data can be ingested into Bronze, cleaned into Silver, and
aggregated for Gold-layer analytics.

## Requirements

- Python 3.13 or newer
- [`uv`](https://docs.astral.sh/uv/)

Install the project dependencies with:

```bash
uv sync
```

## Project layout

```text
.
├── data/
│   └── raw/                         # Hive-partitioned input Parquet files
├── sqls/
│   ├── bronze_layer.sql             # Raw Parquet ingestion
│   ├── solver_layer.sql             # Silver cleansing and type conversion
│   └── gold_layer.sql               # Aggregations and analytical view
├── src/building_a_better_ducklake/
│   ├── generate_raw_data.py         # Fake raw-data generator
│   └── run_medallion_pipeline.py    # Pipeline entry point
└── pyproject.toml
```

The pipeline creates or uses `metadata.ducklake` and stores DuckLake-managed
data under `data/`.

## Medallion pipeline

The pipeline runs the SQL files in this order:

1. **Bronze** (`sqls/bronze_layer.sql`)
   - Reads `data/raw/**/*.parquet`.
   - Enables Hive partition discovery.
   - Uses `union_by_name = true` to combine partition files.
   - Creates `bronze.vpc_flowlogs`.

2. **Silver** (`sqls/solver_layer.sql`)
   - Converts dirty string values into typed columns using `TRY_CAST`.
   - Converts UNIX epoch seconds into timestamps.
   - Carries the `year` and `month` Hive partition columns forward.
   - Creates `silver.vpc_flowlogs`.

3. **Gold** (`sqls/gold_layer.sql`)
   - Creates monthly traffic metrics in `gold.monthly_traffic_summary`.
   - Creates `gold.v_top_traffic_destinations` for traffic analysis by destination.

Run the complete pipeline from the project root so the runner can find the
`sqls/` directory:

```bash
uv run run-medallion-pipeline
```

The runner reports elapsed wall-clock time and the process's final resident
memory usage when the pipeline finishes.

## Generate test data

`generate-raw-data` uses DuckDB's vectorized row generation and Parquet writer,
so it can create large test datasets without building 100 million Python row
objects in memory.

Generate the default 100 million rows under `data/raw`:

```bash
uv run generate-raw-data
```

Generate a smaller dataset for a quick test:

```bash
uv run generate-raw-data --rows 1000000
```

Choose a different output directory:

```bash
uv run generate-raw-data --rows 1000000 --output-dir data/raw
```

The generated files are Hive-partitioned by `year` and `month`, for example:

```text
data/raw/year=2024/month=1/*.parquet
data/raw/year=2024/month=2/*.parquet
```

The raw records contain the columns expected by the Silver SQL, including
network addresses, ports, packet and byte counts, epoch timestamps, action,
log status, and partition columns. A small percentage of values are deliberately
set to `-` to exercise the Silver layer's cleansing logic.

## Development commands

Build the package:

```bash
uv build
```

Compile-check the Python source:

```bash
uv run python -m compileall -q src
```

The SQL files are intentionally kept separate from the Python runner so that
the transformations can be reviewed and modified independently of the pipeline
orchestration code.
