"""Generate fake, dirty VPC flow logs as Hive-partitioned Parquet files."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

DEFAULT_ROW_COUNT = 100_000_000
DEFAULT_OUTPUT_DIR = Path("data/raw")


def _sql_path(path: Path) -> str:
    """Return a path suitable for use as a SQL string literal."""
    return path.resolve().as_posix().replace("'", "''")


def generate_raw_data(row_count: int, output_dir: Path) -> None:
    """Generate ``row_count`` raw flow-log rows into Hive partitions."""
    if row_count < 1:
        raise ValueError("row_count must be greater than zero")

    # Create both the parent data directory and the raw output directory when
    # the generator is run in a fresh checkout.
    data_dir = output_dir.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _sql_path(output_dir)

    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads = 4")
        con.execute(
            f"""
            COPY (
                SELECT
                    CASE WHEN random() < 0.01 THEN '-' ELSE '2' END AS version,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE concat('123456789012', CAST(1 + floor(random() * 899999) AS BIGINT))
                    END AS account_id,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE concat('eni-', lpad(to_hex(CAST(floor(random() * 4294967295) AS UBIGINT)), 8, '0'))
                    END AS interface_id,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE concat(
                            CAST(10 + floor(random() * 11) AS BIGINT), '.',
                            CAST(floor(random() * 256) AS BIGINT), '.',
                            CAST(floor(random() * 256) AS BIGINT), '.',
                            CAST(1 + floor(random() * 254) AS BIGINT)
                        )
                    END AS srcaddr,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE concat(
                            CAST(10 + floor(random() * 11) AS BIGINT), '.',
                            CAST(floor(random() * 256) AS BIGINT), '.',
                            CAST(floor(random() * 256) AS BIGINT), '.',
                            CAST(1 + floor(random() * 254) AS BIGINT)
                        )
                    END AS dstaddr,
                    CASE
                        WHEN random() < 0.02 THEN '-'
                        ELSE CAST(1 + floor(random() * 65535) AS BIGINT)::VARCHAR
                    END AS sp,
                    CASE
                        WHEN random() < 0.02 THEN '-'
                        ELSE CAST(1 + floor(random() * 65535) AS BIGINT)::VARCHAR
                    END AS dp,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE CAST(1 + floor(random() * 255) AS BIGINT)::VARCHAR
                    END AS protocol,
                    CASE
                        WHEN random() < 0.02 THEN '-'
                        ELSE CAST(1 + floor(random() * 10000) AS BIGINT)::VARCHAR
                    END AS packets,
                    CASE
                        WHEN random() < 0.02 THEN '-'
                        ELSE CAST(40 + floor(random() * 5000000) AS BIGINT)::VARCHAR
                    END AS bytes,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE CAST(1704067200 + floor(random() * 94694400) AS BIGINT)::VARCHAR
                    END AS start,
                    CASE
                        WHEN random() < 0.01 THEN '-'
                        ELSE CAST(1704067200 + floor(random() * 94694400) AS BIGINT)::VARCHAR
                    END AS end,
                    CASE
                        WHEN random() < 0.03 THEN '-'
                        ELSE (['ACCEPT', 'REJECT'])[1 + CAST(floor(random() * 2) AS INTEGER)]
                    END AS action,
                    CASE
                        WHEN random() < 0.03 THEN '-'
                        ELSE (['OK', 'NODATA', 'SKIPDATA'])[1 + CAST(floor(random() * 3) AS INTEGER)]
                    END AS log_status,
                    2024 + CAST(floor(row_id / 12000000) AS INTEGER) AS year,
                    1 + CAST(floor(row_id / 1000000) % 12 AS INTEGER) AS month
                FROM range({row_count}) AS rows(row_id)
            ) TO '{output_path}' (
                FORMAT PARQUET,
                PARTITION_BY (year, month),
                COMPRESSION ZSTD
            );
            """
        )
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate fake Hive-partitioned raw VPC flow-log Parquet files."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROW_COUNT,
        help=f"number of rows to generate (default: {DEFAULT_ROW_COUNT:,})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    print(f"Generating {args.rows:,} rows under {args.output_dir}...")
    generate_raw_data(args.rows, args.output_dir)
    print("Raw Hive-partitioned Parquet generation complete.")


if __name__ == "__main__":
    main()
