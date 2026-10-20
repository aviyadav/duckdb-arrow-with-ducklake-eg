# Polars 2.0 Features Demo

A small, runnable playground for the features that landed in **Polars 2.0**. Each
function in `main.py` is a self-contained example that prints its result, so you
can read the code and the output side by side.

## Objective

Show, with real NYC taxi data, how Polars 2.0 changes everyday query work:

- SQL is a first-class citizen (`LazyFrame.sql`, `pl.sql`) instead of a bolt-on.
- A native `Map` dtype with a `.map` namespace for key/value columns.
- Querying several frames in one expression, mixing the expression API with joins.
- What joins do to row order, and what it costs to restore it.
- The streaming engine executing SQL queries.

Every example is timed, so the cost of each approach is visible rather than
asserted.

## Requirements

- Python >= 3.14
- `polars >= 2.0.0`, `pyarrow >= 26.0.0` (declared in `pyproject.toml`, pinned in `uv.lock`)

## Setup and run

```sh
uv sync
uv run main.py
```

Or with an existing virtualenv:

```sh
.venv/bin/python main.py
```

## Data

All files live in `data/` and are read lazily with `pl.scan_parquet` / `pl.scan_csv`:

| File | Size | Description |
| --- | --- | --- |
| `taxi.parquet` | ~48 MB | Yellow taxi trips: timestamps, fare/tip/total amounts, `PULocationID`, `DOLocationID`, `trip_distance`, ... |
| `yellow_tripdata_2026-01.parquet` | ~62 MB | A single month of yellow taxi trips, used by the SQL example. |
| `taxi_zones.csv` | ~13 KB | Zone lookup: `LocationID`, `Borough`, `Zone`, `service_zone`. |

The trip tables join to the zone table via `PULocationID = LocationID`.

## Code layout

`main.py` holds everything:

| Function | Demonstrates |
| --- | --- |
| `sql_fitst_class_citizen` | `LazyFrame.sql()` with `FROM self`, plus `collect_schema()` to inspect columns without reading data. |
| `map_datatype_eg` | The `pl.Map(pl.String, pl.Int64)` dtype and the `.map` namespace: `get`, `contains_key`, `len`, `keys`, `values`. |
| `query_multiple_df` | A lazy pipeline over two frames: filter, join with the zone table, derive `tip_rate`/`hour`/`minutes`, then `group_by` + `agg` (count, median, 0.9 quantile, sum). |
| `join_does_not_prevent_row_order` | A join does not preserve input order; `sort("row")` restores it but costs roughly twice as much. |
| `streaming_engine_sql` | `pl.sql()` across registered frames: an aggregate query, then `LIMIT` with and without `ORDER BY row`. |

`main()` runs the examples in that order.

### Timing helper

`timed` is a decorator applied to every example. It wraps the call in
`time.perf_counter()` and prints the elapsed time plus the delta against the
previous example:

```
[sql_fitst_class_citizen] 0.020s (diff vs previous: +0.020s)
[map_datatype_eg] 0.001s (diff vs previous: -0.019s)
[query_multiple_df] 0.127s (diff vs previous: +0.126s)
[join_does_not_prevent_row_order] 0.039s (diff vs previous: -0.088s)
[streaming_engine_sql] 0.053s (diff vs previous: +0.013s)
```

The delta compares consecutive *examples*, not the two variants inside a single
example, so read it as a rough profile of the run rather than a benchmark.
Timings include printing the results.

## Notes

- `join_does_not_prevent_row_order` and `streaming_engine_sql` both show the same
  trade-off: `LIMIT` without `ORDER BY` returns arbitrary rows and is fast;
  adding `ORDER BY` gives deterministic output at extra cost.
- `sql_fitst_class_citizen` is spelled that way in the source; the README keeps
  the name so it matches the code.
- Polars truncates long frames when printing, so the trip-level results appear as
  previews rather than every row.


### Data

```
wget https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-01.parquet
wget https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet
mv yellow_tripdata_2024-01.parquet taxi.parquet
wget https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv
mv taxi_zone_lookup.csv taxi_zones.csv
```
