# When 512 MB of RAM Meets 100 GB of Parquet

Out-of-core analytical SQL with DuckDB: run TPC-H Query 3 against a TPC-H SF100
dataset (~100 GB raw, ~23 GB as ZSTD-compressed Parquet) under an artificially
tiny `memory_limit`, and watch DuckDB spill to disk instead of falling over —
then dissect the execution with detailed per-operator JSON profiling.

## What this project demonstrates

- **Out-of-core execution** — joins and aggregations that don't fit in RAM
  complete by spilling intermediate results to `temp_directory`.
- **Resource governing** — `memory_limit`, `threads`, `temp_directory`, and
  `preserve_insertion_order` knobs.
- **Parquet engineering** — ZSTD compression, `ROW_GROUP_SIZE`, and
  `PER_THREAD_OUTPUT` file splitting.
- **Detailed profiling** — per-operator timing trees plus planner, optimizer,
  IO, and system statistics via `PRAGMA enable_profiling='json'` +
  `SET profiling_mode='detailed'`.
- **Polars integration** — query results fetched as a Polars DataFrame
  (`con.sql(query).pl()`).

## Repository layout

```
.
├── generate_100gb.py                 # Stage 1: generate TPC-H SF100, export to Parquet
├── partition_large_parquet_files.py  # Stage 2: re-chunk lineitem/orders into smaller files
├── out_of_core_query.py              # Stage 3a: run Q3 under a 4GB cap, with profiling
├── using_file_system.py              # Stage 3b: run Q3 under a 512MB cap, monitor spill
├── json_profile.py                   # Stage 4: render profile_output.json as a tree
├── pyproject.toml / uv.lock          # dependencies (uv-managed)
├── tpch_parquet_sf100/               # 23 GB — exported TPC-H tables (ZSTD Parquet)
│   ├── lineitem.parquet              #   15 GB
│   ├── orders.parquet                #   3.8 GB
│   ├── partsupp.parquet              #   2.7 GB
│   ├── customer.parquet              #   761 MB
│   ├── part.parquet                  #   391 MB
│   ├── supplier.parquet              #   49 MB
│   └── nation/region + schema.sql, load.sql
├── lineitem_partitioned/             # 15 GB — 4 files × ~3.8 GB (per-thread output)
├── orders_partitioned/               # 3.8 GB — 4 files × ~950 MB (per-thread output)
├── tpch_temp.db                      # 28 GB — DuckDB catalog holding the generated SF100 tables
├── partition_temp.db                 # ~12 KB — scratch catalog used by the partitioning step
└── profile_output.json               # detailed profile of the last profiled run
```

`tpch_temp.db` and `partition_temp.db` are intermediates and can be deleted once
the Parquet exports exist (~28 GB reclaimed).

## Pipeline

### Stage 1 — `generate_100gb.py`: build the dataset

- Connects to a **file-backed** database (`tpch_temp.db`) so the catalog
  doesn't live purely in RAM.
- Applies `memory_limit='4GB'`, `threads=4`,
  `preserve_insertion_order=false` (cuts RAM during bulk writes), and sets
  `temp_directory='./duckdb_temp.tmp'` for spillover.
- Loads the `tpch` extension and calls `dbgen(sf=100)` — the classic TPC-H
  data generator at Scale Factor 100 (~100 GB raw).
- `EXPORT DATABASE 'tpch_parquet_sf100' (FORMAT PARQUET, COMPRESSION ZSTD)`
  streams the tables out to Parquet. Takes several minutes.

### Stage 2 — `partition_large_parquet_files.py`: re-chunk the big tables

Rewrites `lineitem.parquet` and `orders.parquet` into `lineitem_partitioned/`
and `orders_partitioned/` using:

```sql
COPY (SELECT * FROM read_parquet('tpch_parquet_sf100/lineitem.parquet'))
TO 'lineitem_partitioned'
(FORMAT PARQUET, COMPRESSION ZSTD, PER_THREAD_OUTPUT TRUE, ROW_GROUP_SIZE 100000);
```

- `PER_THREAD_OUTPUT TRUE` → one file per worker thread: lineitem becomes
  4 × ~3.8 GB files, orders 4 × ~950 MB files.
- `ROW_GROUP_SIZE 100000` → row groups of 100k rows (Q3 scans 7,599 of them
  across lineitem + orders + customer).

### Stage 3a — `out_of_core_query.py`: the profiled run (4 GB cap)

- Registers views over `lineitem_partitioned/*.parquet`,
  `orders_partitioned/*.parquet`, and `tpch_parquet_sf100/customer.parquet`.
- `memory_limit='4GB'`, `threads=4`, spill dir `./duckdb_temp.tmp`.
- Enables detailed JSON profiling → writes `profile_output.json`.
- Fetches the result as a **Polars** DataFrame: `con.sql(query).pl()`.

### Stage 3b — `using_file_system.py`: the starved run (512 MB cap)

The headline experiment. Same query and views, but:

- `memory_limit='512MB'` — smaller than the working set, forcing spills.
- A background thread polls `./duckdb_temp.tmp` every 100 ms and tracks the
  peak on-disk spill footprint.
- Prints an out-of-core summary (peak spill in GB) at the end.

### Stage 4 — `json_profile.py`: render the profile

Parses `profile_output.json` and prints an indented operator tree with
timings, plus memory/cardinality-related `extra_info` per node. Handles both
the DuckDB 2.0 schema and the legacy format.

## The query

A variant of TPC-H Query 3 (Pricing Summary Report) — unshipped orders from
the `BUILDING` market segment, ranked by revenue:

```sql
SELECT
    l_orderkey,
    sum(l_extendedprice * (1 - l_discount)) AS revenue,
    o_orderdate,
    o_shippriority
FROM customer
JOIN orders ON c_custkey = o_custkey
JOIN lineitem ON l_orderkey = o_orderkey
WHERE c_mktsegment = 'BUILDING'
  AND o_orderdate < DATE '1995-03-15'
  AND l_shipdate > DATE '1995-03-15'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC
LIMIT 10;
```

## Results on this machine

Python 3.14.2, DuckDB 2.0.0, 4 threads.

**4 GB cap (`out_of_core_query.py`)** — from `profile_output.json`:

| Metric                  | Value                          |
| ----------------------- | ------------------------------ |
| Wall time               | 5.63 s                         |
| CPU time (4 threads)    | 20.45 s                        |
| Bytes read              | 10.6 GB                        |
| Peak buffer memory      | ~811 MB                        |
| Spill to disk           | 0 B — fit within the 4 GB cap  |

Per-operator highlights: `TABLE_SCAN` (lineitem) 13.96 s, `HASH_JOIN` 1.78 s,
`HASH_GROUP_BY` 0.18 s. Operator timings overlap because 4 threads run in
parallel, so they sum to more than wall time.

**512 MB cap (`using_file_system.py`)**:

- The query **completes successfully** under a 512 MB RAM cap.
- Peak disk spill: **2.35 GB** into `./duckdb_temp.tmp` (cleaned up
  automatically when the connection closes).

Sample `json_profile.py` output (4 GB run):

```
=== DETAILED QUERY EXECUTION PROFILE ===
Total Query Time: 5.63s

▸ RESULT_COLLECTOR (Timing: 0.00s)
  ▸ TOP_N (Timing: 0.00s)
     └─ Estimated Cardinality: 10
    ▸ PROJECTION (Timing: 0.00s)
       └─ Estimated Cardinality: 22025397
      ▸ HASH_GROUP_BY (Timing: 0.18s)
         └─ Estimated Cardinality: 22025397
        ▸ PROJECTION (Timing: 0.02s)
          ▸ HASH_JOIN (Timing: 1.78s)
            ▸ TABLE_SCAN (Timing: 13.96s)
               └─ Estimated Cardinality: 119972733
            ▸ PROJECTION (Timing: 0.03s)
              ▸ HASH_JOIN (Timing: 0.85s)
                ▸ TABLE_SCAN (Timing: 3.44s)
                   └─ Estimated Cardinality: 30267523
                ▸ TABLE_SCAN (Timing: 0.20s)
                   └─ Estimated Cardinality: 3000000
```

## Reading `profile_output.json` (DuckDB 2.0 schema)

| Section            | Contents                                                                                       |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| `operator`         | List holding the physical plan root. Each node: `type`, `timing` (seconds), `extra_info` (e.g. `Estimated Cardinality`), `intermediate_rows`, `intermediate_size_bytes`, `children` |
| `query`            | `sql`, `total_time` (wall), `cpu_time`, rows/row-group counters                                 |
| `io`               | `total_bytes_read`, `total_bytes_written`                                                       |
| `system`           | `peak_buffer_memory`, `total_memory_allocated`, `peak_temp_dir_size`, `blocked_thread_time`      |
| `planner` / `physical_planner` | Binding and plan-construction timings                                                |
| `optimizer`        | Per-optimizer timings (`join_order`, `filter_pushdown`, `statistics_propagation`, …)            |

## DuckDB 2.0 gotchas hit in this project

1. **Polars fetch lives on the relation, not the connection.**
   `con.execute(q)` returns the connection, which has no `.pl()` in 2.0 —
   use `con.sql(q).pl()` (the relation's method). `.df()` (pandas) still
   works on both.
2. **The profiling JSON schema changed.** The plan tree now sits under
   `operator` (a list) and total time under `query.total_time`; the legacy
   `tree` / `latency` top-level keys no longer exist. `json_profile.py`
   resolves the root and latency with fallbacks so both formats work.

## Requirements

- Python 3.14+
- duckdb ≥ 2.0.0, polars ≥ 2.0.0, pyarrow ≥ 26.0.0
  (pyarrow is what DuckDB's `.pl()` uses to hand results to Polars —
  `arrow_table(to_polars=True)`; nothing in this project needs numpy.
  See `pyproject.toml`; the project is uv-managed — `uv.lock` is included)
- ~45 GB free disk for the Parquet data, plus a few GB of headroom for
  spill files and the ~28 GB intermediate `tpch_temp.db` if you regenerate
  from scratch

## Running from scratch

```bash
uv sync                                  # or: pip install duckdb polars pyarrow
python generate_100gb.py                 # several minutes → tpch_parquet_sf100/ (23 GB)
python partition_large_parquet_files.py  # → lineitem_partitioned/ + orders_partitioned/ (~19 GB)
python out_of_core_query.py              # 4 GB cap → prints timing, writes profile_output.json
python using_file_system.py              # 512 MB cap → prints peak spill
python json_profile.py                   # renders profile_output.json as a tree
```

## Tuning knobs

| Setting                    | Used in            | Effect                                                             |
| -------------------------- | ------------------ | ------------------------------------------------------------------ |
| `memory_limit`             | all scripts        | RAM ceiling; working sets beyond it spill to `temp_directory`       |
| `threads`                  | all scripts        | Parallelism (4 here); also sets file count with `PER_THREAD_OUTPUT` |
| `temp_directory`           | all scripts        | Spill-file location                                                 |
| `preserve_insertion_order` | `generate_100gb.py`| `false` lowers RAM during bulk writes                               |
| `profiling_mode`           | `out_of_core_query.py` | `detailed` enables per-operator + phase statistics              |
| `ROW_GROUP_SIZE`           | `partition_large_parquet_files.py` | Row-group granularity inside each Parquet file      |
| `PER_THREAD_OUTPUT`        | `partition_large_parquet_files.py` | One output file per worker thread                  |
