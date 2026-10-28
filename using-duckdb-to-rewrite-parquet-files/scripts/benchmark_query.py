#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import duckdb

from common import sql_quote

try:
    import resource
except ImportError:
    resource = None  # type: ignore


def peak_memory_mb() -> Optional[float]:
    """
    Return process peak RSS in MiB when possible.

    Linux:   ru_maxrss is typically kilobytes.
    macOS:   ru_maxrss is typically bytes.
    Windows: resource module may be unavailable.
    """
    if resource is None:
        return None

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    if sys.platform == "darwin":
        return raw / (1024.0 * 1024.0)

    return raw / 1024.0


def format_mb(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} MB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a DuckDB Parquet aggregation query."
    )

    parser.add_argument(
        "pattern",
        help=(
            "Parquet file or glob pattern, e.g. "
            "data/raw/*_vpcflowlogs_*.parquet"
        ),
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of benchmark runs. Default: 3.",
    )

    args = parser.parse_args()

    if args.runs <= 0:
        raise ValueError("--runs must be positive.")

    pattern_sql = sql_quote(args.pattern)

    query = f"""
        SELECT
            COUNT(*) AS total_rows,
            SUM(TRY_CAST(byt AS BIGINT)) AS total_bytes,
            ROUND(
                SUM(TRY_CAST(byt AS BIGINT)) / 1024 / 1024 / 1024,
                2
            ) AS total_gb
        FROM read_parquet({pattern_sql}, union_by_name=true)
    """

    results = []

    print()
    print("=" * 60)
    print("DuckDB VPC Flow Log Benchmark")
    print("=" * 60)
    print(f"Input: {args.pattern}")
    print(f"Runs:  {args.runs}")

    for run in range(1, args.runs + 1):
        start_time = time.perf_counter()
        start_cpu = time.process_time()

        con = duckdb.connect()
        try:
            row = con.execute(query).fetchone()
        finally:
            con.close()

        end_time = time.perf_counter()
        end_cpu = time.process_time()

        elapsed = end_time - start_time
        cpu_time = end_cpu - start_cpu
        cpu_percent = (cpu_time / elapsed) * 100.0 if elapsed > 0 else 0.0
        memory = peak_memory_mb()

        total_rows = int(row[0] or 0)
        total_bytes = int(row[1] or 0)
        total_gb = float(row[2] or 0.0)

        results.append(
            {
                "elapsed": elapsed,
                "cpu_time": cpu_time,
                "cpu_percent": cpu_percent,
                "memory": memory,
                "total_rows": total_rows,
                "total_bytes": total_bytes,
                "total_gb": total_gb,
            }
        )

        print()
        print(f"Run {run}")
        print("-" * 60)
        print(f"Rows:                 {total_rows:,}")
        print(f"Total bytes:          {total_bytes:,}")
        print(f"Total GB:             {total_gb:.2f}")
        print(f"Elapsed time:         {elapsed:.3f} seconds")
        print(f"CPU time:             {cpu_time:.3f} seconds")
        print(f"CPU utilization:      {cpu_percent:.1f}%")
        print(f"Peak memory (RSS):    {format_mb(memory)}")

    avg_elapsed = sum(r["elapsed"] for r in results) / args.runs
    avg_cpu_time = sum(r["cpu_time"] for r in results) / args.runs
    avg_cpu_percent = sum(r["cpu_percent"] for r in results) / args.runs

    memories = [r["memory"] for r in results if r["memory"] is not None]
    avg_memory = sum(memories) / len(memories) if memories else None

    print()
    print("=" * 60)
    print(f"Average of {args.runs} Runs")
    print("=" * 60)
    print(f"Average elapsed time:      {avg_elapsed:.3f} seconds")
    print(f"Average CPU time:          {avg_cpu_time:.3f} seconds")
    print(f"Average CPU utilization:   {avg_cpu_percent:.1f}%")
    print(f"Average peak memory (RSS): {format_mb(avg_memory)}")
    print("=" * 60)


if __name__ == "__main__":
    main()