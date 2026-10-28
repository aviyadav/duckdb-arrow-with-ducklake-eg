# Using DuckDB to Rewrite Your Parquet Files

### A Simple Case of Less Is More

A working reproduction of the article by **Dean J Murphy** (Medium, Oct 13, 2026):
<https://dean-joseph-murphy.medium.com/using-duckdb-to-rewrite-your-parquet-files-69f459443be2>

The article's argument in one line: **the data did not need to change, the physical
file layout did.**

---

## The Small File Problem

Parquet is the gold standard for analytical engines because its physical design
aligns with modern CPU execution, memory layout, and cloud network I/O. Too many
small files cancel those benefits out.

A Parquet file is generally considered **"small"** if it is under **100 MB**. In
high-throughput distributed pipelines, files under **10 MB** or in the few-kilobyte
range are **"tiny files"** that actively trigger the severe Small File Problem.

Three reasons tiny Parquet files bottleneck analytics:

| Cause | Why it hurts |
| --- | --- |
| **Footer & metadata overhead** | Schema, column min/max statistics and dictionary offsets live in the file footer. On a few-KB file the metadata-to-data ratio is disproportionately high. |
| **Loss of row group efficiency** | Compression (Snappy/ZSTD) and dictionary encoding depend on large contiguous row groups (typically 128–512 MB). Tiny files mean tiny row groups, which cripples compression ratios and vectorization. |
| **I/O and S3 API throttling** | Opening thousands of tiny files over object storage incurs HTTP GET latency and listing overhead, slowing queries regardless of engine speed. |

**What to shoot for:** row groups between 128 MB and 512 MB, and scheduled
compaction jobs (merging daily/hourly micro-batches into larger files), or a table
format such as Iceberg, Delta Lake, or DuckDB's native compaction.

## The Article's Real-Life Example

AWS stores VPC Flow Logs as CSV — a poor format for analytics. The author pulls
them to local disk daily and converts them on the fly to Parquet. Convenient, but
it produces **circa 1,400 tiny Parquet files per day, 5–15 KB each**: the textbook
severe small-file case.

The fix is a daily compaction job. Three steps:

**1. Measure the starting point** with `read_blob`:

```sql
SELECT
    COUNT(*) AS files,
    ROUND(SUM(size) / 1024.0, 2) AS total_kb,
    ROUND(SUM(size) / 1024.0 / 1024.0, 2) AS total_mb,
    ROUND(AVG(size) / 1024.0, 2) AS avg_kb
FROM read_blob('*_vpcflowlogs_*.parquet');
```

**2. Compact the day** (`daily_compact.sh`):

```bash
COPY (
    SELECT *
    FROM read_parquet(
        '*_vpcflowlogs_*_${DAY}T*.parquet',
        union_by_name = true
    )
)
TO '${OUTPUT}'
(FORMAT PARQUET, COMPRESSION ZSTD);
```

Running `./daily_compact.sh 20260915` produced a single **12 MB** Parquet file,
`daily-2026-09-15.parquet` — still sub-optimal by the 100 MB guideline, but one
file instead of 1,440.

**3. Benchmark both versions** (`query.py`, 3 runs, timing wall clock, CPU time and
peak RSS around the same aggregation):

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(TRY_CAST(byt AS BIGINT)) AS total_bytes,
    ROUND(SUM(TRY_CAST(byt AS BIGINT)) / 1024 / 1024 / 1024, 2) AS total_gb
FROM read_parquet('<pattern>', union_by_name = true);
```

### The Article's Results

Both versions hold exactly **1,385,692 rows** representing the same **7.36 GB** of
network traffic. Only the file count differs.

| Version | Files | Elapsed | CPU time | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Small files | 1,440 | 0.181 s | 0.467 s | 120.5 MB |
| Compacted | 1 | 0.035 s | 0.073 s | 55.2 MB |

- **Query:** ~5.2× faster — an ~81% reduction in elapsed time (the compacted file
  takes only ~19% as long).
- **CPU:** ~84% less CPU time. This is the important part — DuckDB is doing
  substantially *less work*, not just finishing sooner.
- **Memory:** peak RSS down ~65 MB, or ~54%.

The actual data processing was never the expensive part; the small-file overhead
was large relative to the amount of data being processed.

---

## What This Repository Does

The original VPC Flow Logs are not redistributable, so this project generates
synthetic data that recreates the article's conditions and then runs the same
workflow end to end.

It provides:

1. A synthetic VPC Flow Log generator that writes ~1,440 tiny Parquet files for one
   UTC day.
2. A DuckDB daily compaction job that merges them into a single daily Parquet file.
3. A benchmark script modelled on the article's `query.py`.
4. A file-statistics script using DuckDB `read_blob`, matching the article's query.
5. A demo runner (`scripts/run_demo.sh`) and a `Makefile`.

Synthetic targets, mirroring the article:

| Property | Value |
| --- | --- |
| Date | `2026-09-15` (the article's date) |
| Files | 1,440 |
| Rows | 1,385,692 |
| Logical network bytes | 7.36 GiB |
| `byt` column | present, so the article's query runs unchanged |
| Filename glob | `*_vpcflowlogs_*.parquet`, `*_vpcflowlogs_*_20260915T*.parquet` |
| Compaction output | `data/compacted/daily-2026-09-15.parquet` |

Generated filenames look like:

```text
aws_vpcflowlogs_batch_20260915T000000Z_0000.parquet
aws_vpcflowlogs_batch_20260915T000100Z_0001.parquet
...
```

## Repository Layout

```text
Makefile                                task runner (install, generate, compact, stats-*, bench-*, demo, clean)
pyproject.toml / uv.lock                uv-managed dependencies (duckdb, pyarrow)
requirements.txt                        pip-compatible alternative
scripts/
  generate_synthetic_vpc_logs.py        writes the tiny Parquet files
  file_stats.py                         article's read_blob file-count/size query
  compact_daily.py                      article's COPY ... TO daily Parquet job
  benchmark_query.py                    article's query.py equivalent
  compact_daily.sql                     reference SQL for compaction
  benchmark_query.sql                   reference SQL for the benchmark
  run_demo.sh                           runs all six steps in order
  common.py                             shared date/quoting helpers
data/raw/                               tiny files (gitignored)
data/compacted/                         daily compacted file (gitignored)
```

## Setup

The `Makefile` and `run_demo.sh` shell out to `uv run python`, so [uv](https://docs.astral.sh/uv/)
is the intended workflow:

```bash
uv sync            # creates .venv and installs duckdb + pyarrow
```

Or, equivalently via the Makefile:

```bash
make install       # uv pip install -r requirements.txt
```

Plain pip still works if you prefer it — activate a venv first, then
`pip install -r requirements.txt`, and substitute `python` for `uv run python` in
the commands below.

Requires Python 3.14+ (per `pyproject.toml`).

## Run the Full Demo

```bash
make demo DATE=2026-09-15
```

which chains `generate → stats-small → compact → stats-compact → bench-small →
bench-compact`. The same thing via the script:

```bash
chmod +x scripts/run_demo.sh
./scripts/run_demo.sh 2026-09-15
```

## Run the Steps Manually

Each step matches the corresponding article command.

**1. Generate the tiny Parquet files**

```bash
uv run python scripts/generate_synthetic_vpc_logs.py \
  --date 2026-09-15 \
  --out-dir data/raw \
  --clean \
  --file-count 1440 \
  --total-rows 1385692 \
  --total-gb 7.36 \
  --schema slim \
  --compression zstd
```

(`make generate`)

**2. Inspect small-file statistics**

```bash
uv run python scripts/file_stats.py --glob 'data/raw/*_vpcflowlogs_*.parquet'
```

(`make stats-small`) — runs the article's `read_blob` query:

```sql
SELECT
  COUNT(*) AS files,
  ROUND(SUM(size) / 1024.0, 2) AS total_kb,
  ROUND(SUM(size) / 1024.0 / 1024.0, 2) AS total_mb,
  ROUND(AVG(size) / 1024.0, 2) AS avg_kb
FROM read_blob('data/raw/*_vpcflowlogs_*.parquet');
```

**3. Compact the daily files**

```bash
uv run python scripts/compact_daily.py \
  --date 2026-09-15 \
  --input-dir data/raw \
  --output-dir data/compacted
```

(`make compact`) — essentially the article's `daily_compact.sh`:

```sql
COPY (
  SELECT *
  FROM read_parquet('data/raw/*_vpcflowlogs_*_20260915T*.parquet', union_by_name = true)
)
TO 'data/compacted/daily-2026-09-15.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD);
```

**4. Inspect the compacted file**

```bash
uv run python scripts/file_stats.py --glob 'data/compacted/daily-2026-09-15.parquet'
```

(`make stats-compact`)

**5. Benchmark the small files**

```bash
uv run python scripts/benchmark_query.py 'data/raw/*_vpcflowlogs_*.parquet' --runs 3
```

(`make bench-small`)

**6. Benchmark the compacted file**

```bash
uv run python scripts/benchmark_query.py 'data/compacted/daily-2026-09-15.parquet' --runs 3
```

(`make bench-compact`)

### Makefile Targets

| Target | Action |
| --- | --- |
| `install` | `uv pip install -r requirements.txt` |
| `generate` | Create 1,440 tiny Parquet files in `data/raw` |
| `compact` | Merge the day into one file in `data/compacted` |
| `stats-small` / `stats-compact` | File count and size stats before / after |
| `bench-small` / `bench-compact` | 3-run benchmark before / after |
| `demo` | All of the above, in order |
| `clean` | Delete generated Parquet files |

Override the date with `DATE=`, and the interpreter with `PYTHON=` if needed.

## Results

### Article (real VPC Flow Logs)

| Version | Files | Elapsed | CPU time | Peak RSS | On-disk size |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small files | 1,440 | 0.181 s | 0.467 s | 120.5 MB | 5–15 KB each |
| Compacted | 1 | 0.035 s | 0.073 s | 55.2 MB | 12 MB |

### This reproduction (synthetic data, averaged over 3 runs)

| Version | Files | Elapsed | CPU time | Peak RSS | On-disk size |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small files | 1,440 | 0.101 s | 0.294 s | 136.6 MB | 5.62 MB total (4.00 KB avg) |
| Compacted | 1 | 0.014 s | 0.021 s | 76.3 MB | 60.94 KB |

Same direction as the article, and sharper in relative terms: ~7× faster elapsed,
~93% less CPU time, ~44% lower peak RSS, with the identical 1,385,692 rows and
7.36 GiB of logical bytes in both versions.

Your numbers will vary with machine, DuckDB version, PyArrow version and OS. The
pattern — not the magnitude — is the point.

### Why the synthetic sizes differ

The generator uses a deliberately compressible schema, so its files are ~4 KB
rather than the article's 5–15 KB, and the compacted output is ~61 KB rather than
12 MB. Most columns are constant or near-constant values that dictionary-encode and
ZSTD-compress almost away. The row count and logical byte totals still match the
article, which is what makes the query-time comparison meaningful; the on-disk
sizes are not directly comparable.

## Synthetic Data Notes

Default `--schema slim` columns:

```text
account_id, interface_id, srcaddr, dstaddr, protocol, packets, byt, start, end, action
```

`--schema full` additionally writes:

```text
version, srcport, dstport, log_status
```

`byt` values are generated deterministically so the total logical byte count hits
the `--total-gb` target (7.36 GiB by default), and so repeated runs reproduce the
same totals. Other generator flags cover `--file-count`, `--total-rows`,
`--total-bytes`, `--compression` (zstd/snappy/gzip), `--out-dir` and `--clean`.

This data is synthetic and must not be treated as real AWS VPC Flow Log data.

## Cleanup

```bash
make clean
```

or manually:

```bash
rm -f data/raw/*.parquet
rm -f data/compacted/*.parquet
```

## The Lesson

The lesson is **not** that one Parquet file is always better than 1,440. Parquet is
built for parallel analytical workloads, and splitting data across files helps when
those files are appropriately sized and organized. The lesson is that **excessive
fragmentation has a cost**. Writing a new tiny file every few minutes was convenient
for ingestion but produced a layout that was inefficient for analysis.

For the author's VPC Flow Logs the answer was not to change DuckDB or rewrite the
queries — it was to make daily Parquet compaction part of the pipeline. Fewer files
meant less metadata and file-management overhead, less CPU work, less memory, and
substantially faster queries.

The data was already good. It just needed fewer files.
