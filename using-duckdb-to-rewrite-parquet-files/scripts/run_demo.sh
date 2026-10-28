#!/usr/bin/env bash
set -euo pipefail

DATE="${1:-2026-09-15}"

RAW_DIR="data/raw"
COMPACT_DIR="data/compacted"

echo
echo "=============================================================="
echo "Generating synthetic tiny Parquet files"
echo "=============================================================="

uv run python scripts/generate_synthetic_vpc_logs.py \
  --date "$DATE" \
  --out-dir "$RAW_DIR" \
  --clean \
  --file-count 1440 \
  --total-rows 1385692 \
  --total-gb 7.36 \
  --schema slim \
  --compression zstd

echo
echo "=============================================================="
echo "File stats before compaction"
echo "=============================================================="

uv run python scripts/file_stats.py \
  --glob "$RAW_DIR/*_vpcflowlogs_*.parquet"

echo
echo "=============================================================="
echo "Compacting daily files with DuckDB"
echo "=============================================================="

uv run python scripts/compact_daily.py \
  --date "$DATE" \
  --input-dir "$RAW_DIR" \
  --output-dir "$COMPACT_DIR"

echo
echo "=============================================================="
echo "File stats after compaction"
echo "=============================================================="

uv run python scripts/file_stats.py \
  --glob "$COMPACT_DIR/daily-${DATE}.parquet"

echo
echo "=============================================================="
echo "Benchmark: many small files"
echo "=============================================================="

uv run python scripts/benchmark_query.py \
  "$RAW_DIR/*_vpcflowlogs_*.parquet" \
  --runs 3

echo
echo "=============================================================="
echo "Benchmark: one compacted file"
echo "=============================================================="

uv run python scripts/benchmark_query.py \
  "$COMPACT_DIR/daily-${DATE}.parquet" \
  --runs 3

echo
echo "Demo complete."
