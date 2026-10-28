a complete, working project that reproduces the article’s workflow using synthetic VPC Flow Log-style Parquet files.
It creates:

1. 440 tiny Parquet files for one UTC day.
2. A DuckDB daily compaction job that merges them into one daily Parquet file.
3. A benchmark script modeled after the article’s query.py.
4. A file-size inspection script using DuckDB read_blob.
5. A demo runner and Makefile.

The synthetic data is designed to mimic the article’s conditions:
. Same date used in the article: 2026-09-15
. Approximately 1,440 small files
. Approximately 1,385,692 rows
. Approximately 7.36 GiB of logical network bytes
. A byt column, matching the article’s query
. Filenames matching the article’s glob patterns:
    *_vpcflowlogs_*.parquet
    *_vpcflowlogs_*_YYYYMMDDT*.parquet


```bash
chmod +x scripts/run_demo.sh
```

These match the article-style patterns:
```text
*_vpcflowlogs_*.parquet
```

```text
*_vpcflowlogs_*_20260915T*.parquet
```

The compaction output is:

```
data/compacted/daily-2026-09-15.parquet
```

### Setup

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows
```ps
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Run the Full Demo

#### Using the shell script

```shell
chmod +x scripts/run_demo.sh
./scripts/run_demo.sh 2026-09-15
```

Using Make

```bash
make demo DATE=2026-09-15
```

### Run Steps Manually

#### 1. Generate synthetic tiny Parquet files

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

#### 2. Inspect small-file statistics

```bash
uv run python scripts/file_stats.py \
  --glob 'data/raw/*_vpcflowlogs_*.parquet'
```

Equivalent DuckDB SQL:

```sql
SELECT
  COUNT(*) AS files,
  ROUND(SUM(size) / 1024.0, 2) AS total_kb,
  ROUND(SUM(size) / 1024.0 / 1024.0, 2) AS total_mb,
  ROUND(AVG(size) / 1024.0, 2) AS avg_kb
FROM read_blob('data/raw/*_vpcflowlogs_*.parquet');
```

#### 3. Compact the daily files

```bash
uv run python scripts/compact_daily.py \
  --date 2026-09-15 \
  --input-dir data/raw \
  --output-dir data/compacted
```

This runs essentially:

```sql
COPY (
  SELECT *
  FROM read_parquet(
    'data/raw/*_vpcflowlogs_*_20260915T*.parquet',
    union_by_name = true
  )
)
TO 'data/compacted/daily-2026-09-15.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD);
```

#### 4. Inspect compacted file statistics

```bash
uv run python scripts/file_stats.py \
  --glob 'data/compacted/daily-2026-09-15.parquet'
```

#### 5. Benchmark the small files
```bash
uv run python scripts/benchmark_query.py \
  'data/raw/*_vpcflowlogs_*.parquet' \
  --runs 3
```

#### 6. Benchmark the compacted file

```bash
uv run python scripts/benchmark_query.py \
  'data/compacted/daily-2026-09-15.parquet' \
  --runs 3
```

### Benchmark Query

The benchmark runs this aggregation:
```sql
SELECT
  COUNT(*) AS total_rows,
  SUM(TRY_CAST(byt AS BIGINT)) AS total_bytes,
  ROUND(
    SUM(TRY_CAST(byt AS BIGINT)) / 1024 / 1024 / 1024,
    2
  ) AS total_gb
FROM read_parquet('<pattern>', union_by_name = true)
```

### Expected Result

Exact numbers depend on your machine, DuckDB version, PyArrow version, and OS.
. However, the pattern from the article should still appear:
. The compacted file should usually query faster.
. CPU time should usually drop significantly.
. Peak memory should usually be lower.
. The amount of logical data should remain the same.

The article reported roughly:

Version | Files | Elapsed | CPU Time| Peak RSS
Small files| 1,440 | 0.181 s | 0.467 s | 120.5 MB
Compacted | 1 | 0.035 s | 0.073 s | 55.2 MB


Your synthetic results may differ, but the direction should be similar.

Synthetic Data Notes
The generator uses a deliberately compressible schema.
Default slim schema:

```text
account_id
interface_id
srcaddr
dstaddr
protocol
packets
byt
start
end
action
```

Optional full schema adds:

```text
version
srcport
dstport
log_status
```

The byt values are generated deterministically so that the total logical byte
count matches the requested target, approximately 7.36 GiB.
The data is synthetic and should not be treated as real AWS VPC Flow Log data.

### Cleanup

```bash
make clean
```

Or manually:

```bash
rm -f data/raw/*.parquet
rm -f data/compacted/*.parquet
```

```text

---

# How to Run It

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/run_demo.sh
./scripts/run_demo.sh 2026-09-15

```


Or:

```bash
make install
make demo DATE=2026-09-15
```


What This Project Demonstrates

This project reproduces the core lesson from the article:
    The data did not need to change.
    The physical file layout did.

By compacting many tiny Parquet files into one daily Parquet file, DuckDB has:
. Fewer files to open
. Less footer/metadata overhead
. Fewer tiny row groups
. Less planning and file-management work
. Lower CPU usage
. Lower memory pressure
. Faster analytical queries
