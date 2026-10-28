#!/usr/bin/env python3
from __future__ import annotations

import argparse

import duckdb

from common import sql_quote


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show Parquet file count and size statistics using DuckDB."
    )

    parser.add_argument(
        "--glob",
        required=True,
        help="File glob, e.g. data/raw/*_vpcflowlogs_*.parquet",
    )

    args = parser.parse_args()

    sql = f"""
        SELECT
            COUNT(*) AS files,
            COALESCE(SUM(size), 0) AS total_bytes,
            ROUND(COALESCE(SUM(size), 0) / 1024.0, 2) AS total_kb,
            ROUND(COALESCE(SUM(size), 0) / 1024.0 / 1024.0, 2) AS total_mb,
            ROUND(COALESCE(AVG(size), 0) / 1024.0, 2) AS avg_kb
        FROM read_blob({sql_quote(args.glob)})
    """

    con = duckdb.connect()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()

    files, total_bytes, total_kb, total_mb, avg_kb = row

    print("File statistics")
    print("=" * 60)
    print(f"Glob:        {args.glob}")
    print(f"Files:       {files:,}")
    print(f"Total bytes: {int(total_bytes):,}")
    print(f"Total KB:    {float(total_kb):,.2f}")
    print(f"Total MB:    {float(total_mb):,.2f}")
    print(f"Average KB:  {float(avg_kb):,.2f}")


if __name__ == "__main__":
    main()