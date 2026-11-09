# What's New in Polars 2.1

Code for the CodeCut article "What's New in Polars 2.1: Group-Bys That Spill, Fuller SQL, and Encrypted Parquet".

Groups ~33M NYC yellow taxi trip rows (Jan–Oct 2024) by route and pickup hour with Polars' new out-of-core group-by, and reports the query time.

## Files

```text
polars-2-1-whats-new/
├── download_data.py  # script to download data - Jan to Oct 2024 NYC taxi trips and the zone lookup into data/ (stdlib` only)
├── 01_groupby.py     # route-by-hour group-by over 10 months (33M rows), timed
├── 02_sql_fuller.py  # read_parquet with a list of paths, DATE_TRUNC, generate_series
├── 03_encrypt.py     # writes and reads a Parquet file with encrypted payment columns
├── join_where_full.py  # range join that keeps unmatched rows from both sides
├── 05_approx.py      # exact vs approximate median on 33M fares
├── 06_masked.py      # NumPy masked arrays to Polars nulls and back
├── bench.py          # benchmark of core lazy operations on synthetic data
├── bench_scripts.py  # benchmark of the logic in 01_groupby.py through 05_approx_quantile.py
└── data/             # downloaded parquet files (about 540 MB)
```  


## Setup

1. Install Polars 2.1. This project uses [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync
   ```

   or plain pip:

   ```bash
   pip install polars==2.1.0 numpy
   ```

2. Download the data (about 540 MB):

   ```bash
   uv run python download_data.py
   ```

## Run

```bash
uv run python 01_groupby.py
uv run python 02_sql_fuller.py
uv run python 03_encrypt.py
uv run python join_where_full.py
uv run python 05_approx.py
uv run python 06_masked.py
```

Output: the grouped result shape and the query time (about 0.5s on this data).

## Benchmarks

Two benchmarks time Polars workloads and report the best of 5 runs (the minimum
wall-clock time, in milliseconds) for each query.

### `bench.py`

Generates synthetic data (`data/orders.parquet`, `data/customers.parquet`) and
times five core lazy operations: `group_by_sum`, `join_group_by`, `sort`,
`unique_two_keys`, and `filter_sort`.

```bash
uv run python bench.py
```

### `bench_scripts.py`

Runs the logic from `01_groupby.py` through `05_approx_quantile.py` against the
downloaded taxi data, timing each script's workload:

| Query | Source | Workload |
| --- | --- | --- |
| `01_groupby` | `01_groupby.py` | route-by-hour group-by over 10 months |
| `02_sql_queries` | `02_sql_queries.py` | list-of-paths `read_parquet`, `DATE_TRUNC`, `generate_series` |
| `03_encrypt` | `03_encrypt.py` | encrypt and read back encrypted Parquet |
| `04_join_where_full` | `04_join_where_full.py` | range join keeping unmatched rows |
| `05_approx_quantile` | `05_approx_quantile.py` | exact vs approximate median on 33M fares |

```bash
uv run python bench_scripts.py
```

Example output:

```text
Polars 2.1.0
01_groupby              435.7 ms
02_sql_queries           12.9 ms
03_encrypt              147.1 ms
04_join_where_full        0.6 ms
05_approx_quantile      203.7 ms
```

## Data

NYC TLC Trip Record Data: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
