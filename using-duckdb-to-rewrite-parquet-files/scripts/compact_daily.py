#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from common import parse_date, sql_quote


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compact daily tiny VPC Flow Log Parquet files using DuckDB."
    )

    parser.add_argument(
        "--date",
        required=True,
        help="UTC date to compact, e.g. 2026-09-15 or 20260915.",
    )
    parser.add_argument(
        "--input-dir",
        default="data/raw",
        help="Directory containing tiny Parquet files.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/compacted",
        help="Directory for the compacted daily Parquet file.",
    )
    parser.add_argument(
        "--row-group-rows",
        type=int,
        default=0,
        help=(
            "Optional DuckDB Parquet ROW_GROUP_SIZE in rows. "
            "If 0, DuckDB's default is used."
        ),
    )

    args = parser.parse_args()

    d = parse_date(args.date)
    day_compact = d.strftime("%Y%m%d")
    iso_date = d.isoformat()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    glob_pattern = f"*_vpcflowlogs_*_{day_compact}T*.parquet"
    input_glob = input_dir / glob_pattern

    matches = list(input_dir.glob(glob_pattern))

    if not matches:
        raise FileNotFoundError(
            f"No files matched: {input_glob}. "
            "Run the generator first."
        )

    output_path = output_dir / f"daily-{iso_date}.parquet"

    if output_path.exists():
        output_path.unlink()

    options = [
        "FORMAT PARQUET",
        "COMPRESSION ZSTD",
    ]

    if args.row_group_rows > 0:
        options.append(f"ROW_GROUP_SIZE {args.row_group_rows}")

    sql = f"""
        COPY (
            SELECT *
            FROM read_parquet({sql_quote(str(input_glob))}, union_by_name=true)
        )
        TO {sql_quote(str(output_path))}
        ({', '.join(options)})
    """

    con = duckdb.connect()
    try:
        con.execute(sql)
    finally:
        con.close()

    output_size = output_path.stat().st_size

    print("Daily compaction complete.")
    print(f"  Matched files: {len(matches):,}")
    print(f"  Input glob:    {input_glob}")
    print(f"  Output file:   {output_path}")
    print(f"  Output size:   {output_size / (1024 ** 2):.2f} MiB")


if __name__ == "__main__":
    main()