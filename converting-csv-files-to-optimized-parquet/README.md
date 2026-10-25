# Converting CSV Files to Optimized Parquet

A hands-on benchmark showing why **Parquet** beats raw **CSV** for analytical
workloads. Using [DuckDB](https://duckdb.org/) and `psutil`, this project
generates a large CSV dataset, converts it to Parquet (both ZSTD-compressed
and uncompressed), and measures the time and peak memory of each approach.

## What it demonstrates

- How to stream a 100M-row CSV into a compact Parquet file without loading it
  all into memory.
- The performance difference between querying a raw CSV, a ZSTD-compressed
  Parquet file, and an uncompressed Parquet file.
- Why **explicit typing** matters: with `all_varchar = true`, numeric columns
  become text and aggregations such as `SUM(revenue)` fail with a
  `BinderException`.
- How to measure peak process memory from a background thread while a query
  runs.

## Project structure

| File | Purpose |
| --- | --- |
| `generate_csv_data.py` | Generates `data/events.csv` (100M rows) using DuckDB's `generate_series`. |
| `generate_csv_pyarrow.py` | Generates `data/events_py.csv` with the same shape using NumPy + PyArrow only (no DuckDB), in parallel batches with bounded memory. |
| `convert_to_parquet.py` | Converts the CSV twice, writing `data/events_compressed.parquet` (ZSTD) and `data/events_uncompressed.parquet`, and prints a side-by-side report of conversion time, peak RSS, and file size. |
| `auto_inferencing.py` | Runs a `GROUP BY country` aggregation on the CSV using DuckDB's default type auto-inference. Reports time and peak memory. |
| `query_parquet_file.py` | Runs the same aggregation directly against the Parquet file. Reports time and peak memory. |
| `test_speed.py` | Runs one filtered `GROUP BY country` aggregation against all three sources (CSV, ZSTD Parquet, uncompressed Parquet) from a single `main()` and prints a comparison summary table. |
| `everything_varchar.py` | Forces every column to `VARCHAR` to show the error you get when summing text instead of numbers. |

## Dataset schema

The generated `events.csv` contains 100M rows with the following columns:

| Column | Type | Description |
| --- | --- | --- |
| `event_date` | `DATE` | Random date between 2024-01-01 and 2026-01-31. |
| `country` | `VARCHAR` | One of `US`, `UK`, `DE`, `FR`, `IN`, `JP`. |
| `channel` | `VARCHAR` | One of `search`, `social`, `email`, `direct`. |
| `user_id` | `INTEGER` | Random value between 1 and 200,000. |
| `order_id` | `INTEGER` | Random value between 1 and 900,000. |
| `revenue` | `DOUBLE` | Skewed value; 15% of rows are `0.0`. |

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- Dependencies: `duckdb`, `numpy`, `psutil`, `pyarrow` (plus `ruff` for linting)

## Setup

```sh
uv sync
```

Or with pip:

```sh
pip install duckdb numpy psutil pyarrow
```

## Usage

Run the scripts from the project root, in order. The first step generates a
multi-gigabyte file, so make sure you have disk space available.

```sh
# 1. Generate the source CSV (~3.7 GB)
uv run python generate_csv_data.py

#    Or generate an equivalent file with NumPy + PyArrow instead of DuckDB
uv run python generate_csv_pyarrow.py

# 2. Convert the CSV to Parquet twice: ZSTD-compressed (~950 MB) and
#    uncompressed (~3.6 GB). test_speed.py in step 3 expects both files.
uv run python convert_to_parquet.py

# 3. Query the CSV and the Parquet file to compare performance
uv run python auto_inferencing.py
uv run python query_parquet_file.py

#    Or benchmark the CSV against both Parquet files in a single run
uv run python test_speed.py

# 4. See what happens when numeric columns are treated as text
uv run python everything_varchar.py
```

### `generate_csv_pyarrow.py` options

`generate_csv_pyarrow.py` accepts a few flags so you can tune or smoke-test it:

```sh
uv run python generate_csv_pyarrow.py \
    --rows 100000000 \
    --batch-size 1000000 \
    --workers 8 \
    --output data/events_py.csv \
    --seed 42
```

It uses a `ProcessPoolExecutor` to build batches in parallel and writes them
through a `pyarrow.csv.CSVWriter` in order. Only a bounded window of batches
(`2 x workers`) is ever kept in memory, so resident memory stays roughly
constant even for hundreds of millions of rows.

## Sample output

`convert_to_parquet.py` prints a report like:

```
Found source file: data/events.csv (3.70 GB)
Starting benchmarks…

Starting conversion to Parquet (ZSTD) from data/events.csv…
Starting conversion to Parquet (UNCOMPRESSED) from data/events.csv…

=======================================================
 DUCKDB CONVERSION PERFORMANCE REPORT 
=======================================================
Metric                  | Compressed (ZSTD) | Uncompressed
-------------------------------------------------------
Time Elapsed            | 45.12 seconds | 18.34 seconds
Peak Memory (RSS)       | 612.34 MB | 598.12 MB
Output File Size        | 945.71 MB | 3612.88 MB
=======================================================
```

`auto_inferencing.py` and `query_parquet_file.py` print the query time and peak
memory for the same `GROUP BY country` aggregation, so you can compare the two
storage formats directly.

`test_speed.py` runs the same filtered aggregation against all three sources in
one process, prints each result table, and finishes with a summary:

```
==============================================================
 - - Performance Summary - -
==============================================================
Source                     |   Time (s) |   Peak Memory (MB)
--------------------------------------------------------------
CSV                        |     1.4772 |               0.01
Parquet (ZSTD)             |     0.2278 |               0.00
Parquet (uncompressed)     |     0.1454 |               0.00
==============================================================
```

## Notes

- `convert_to_parquet.py` writes two Parquet outputs: **ZSTD**-compressed
  (typically ~4x smaller than the raw CSV) and uncompressed, so you can trade
  conversion time and disk usage against query speed.
- Most scripts sample peak memory every 5 ms from a daemon thread calling
  `psutil.Process().memory_info().rss`.
- `test_speed.py` instead uses `tracemalloc`, which only tracks Python-level
  allocations. DuckDB executes queries in C++, so its peak-memory column reads
  near zero; the timing numbers are the meaningful output there.
- Generated data in `data/` is not intended to be committed to version control.
