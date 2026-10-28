#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from common import parse_date


SLIM_FIELDS = [
    ("account_id", pa.string()),
    ("interface_id", pa.string()),
    ("srcaddr", pa.string()),
    ("dstaddr", pa.string()),
    ("protocol", pa.int32()),
    ("packets", pa.int32()),
    ("byt", pa.int64()),
    ("start", pa.int64()),
    ("end", pa.int64()),
    ("action", pa.string()),
]

FULL_FIELDS = [
    ("version", pa.int32()),
    ("account_id", pa.string()),
    ("interface_id", pa.string()),
    ("srcaddr", pa.string()),
    ("dstaddr", pa.string()),
    ("srcport", pa.int32()),
    ("dstport", pa.int32()),
    ("protocol", pa.int32()),
    ("packets", pa.int32()),
    ("byt", pa.int64()),
    ("start", pa.int64()),
    ("end", pa.int64()),
    ("action", pa.string()),
    ("log_status", pa.string()),
]


def make_schema(kind: str) -> pa.Schema:
    if kind == "slim":
        return pa.schema(SLIM_FIELDS)
    if kind == "full":
        return pa.schema(FULL_FIELDS)

    raise ValueError(f"Unknown schema kind: {kind}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic VPC Flow Log-style tiny Parquet files "
            "matching the patterns used in the article."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        help="UTC date for the synthetic logs, e.g. 2026-09-15 or 20260915.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/raw",
        help="Directory where tiny Parquet files will be written.",
    )
    parser.add_argument(
        "--file-count",
        type=int,
        default=1440,
        help="Number of tiny Parquet files to generate. Default: 1440.",
    )
    parser.add_argument(
        "--total-rows",
        type=int,
        default=1_385_692,
        help="Total synthetic rows across all files. Default: 1,385,692.",
    )
    parser.add_argument(
        "--total-gb",
        type=float,
        default=7.36,
        help=(
            "Total logical bytes represented as GiB. "
            "Default: 7.36 GiB, matching the article's reported total_gb."
        ),
    )
    parser.add_argument(
        "--total-bytes",
        type=int,
        default=None,
        help=(
            "Optional exact total bytes. If supplied, overrides --total-gb."
        ),
    )
    parser.add_argument(
        "--schema",
        choices=["slim", "full"],
        default="slim",
        help=(
            "slim uses fewer columns and usually produces smaller files. "
            "full uses a broader VPC-flow-log-like schema."
        ),
    )
    parser.add_argument(
        "--compression",
        choices=["zstd", "snappy", "gzip"],
        default="zstd",
        help="Parquet compression codec for generated tiny files.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing .parquet files in --out-dir before generating.",
    )

    parser.add_argument("--account-id", default="123456789012")
    parser.add_argument("--interface-id", default="eni-0a1b2c3d4e5f67890")
    parser.add_argument("--srcaddr", default="10.0.1.50")
    parser.add_argument("--dstaddr", default="10.0.2.60")
    parser.add_argument("--srcport", type=int, default=49152)
    parser.add_argument("--dstport", type=int, default=443)
    parser.add_argument("--protocol", type=int, default=6)
    parser.add_argument("--action", default="ACCEPT")
    parser.add_argument("--log-status", default="OK")

    args = parser.parse_args()

    if args.file_count <= 0:
        raise ValueError("--file-count must be positive.")

    if args.total_rows <= 0:
        raise ValueError("--total-rows must be positive.")

    if args.file_count > args.total_rows:
        raise ValueError(
            "--file-count cannot exceed --total-rows in this generator, "
            "because every file is expected to contain at least one row."
        )

    d = parse_date(args.date)
    day_compact = d.strftime("%Y%m%d")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        for old_file in out_dir.glob("*.parquet"):
            old_file.unlink()

    schema = make_schema(args.schema)

    total_rows = args.total_rows

    if args.total_bytes is not None:
        total_bytes = args.total_bytes
    else:
        total_bytes = int(round(args.total_gb * (1024 ** 3)))

    # Each row must have at least 1 byte.
    if total_bytes < total_rows:
        total_bytes = total_rows

    base_rows, extra_rows = divmod(total_rows, args.file_count)
    base_byte, byte_remainder = divmod(total_bytes, total_rows)

    # Low-cardinality cyclic variation keeps files tiny while still producing
    # a non-constant byt column.
    spread = 101
    half_spread = spread // 2
    byte_multiplier = 7919

    day_epoch = int(
        datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp()
    )

    remaining_bytes = total_bytes
    row_offset = 0
    files_written = 0
    on_disk_bytes = 0

    account_id = args.account_id
    interface_id = args.interface_id
    srcaddr = args.srcaddr
    dstaddr = args.dstaddr
    srcport = args.srcport
    dstport = args.dstport
    protocol = args.protocol
    action = args.action
    log_status = args.log_status

    for file_idx in range(args.file_count):
        nrows = base_rows + (1 if file_idx < extra_rows else 0)

        if nrows <= 0:
            continue

        minute_of_day = file_idx % 1440
        hour = minute_of_day // 60
        minute = minute_of_day % 60
        ts = f"{hour:02d}{minute:02d}00Z"

        # This filename intentionally matches:
        #   *_vpcflowlogs_*.parquet
        # and:
        #   *_vpcflowlogs_*_YYYYMMDDT*.parquet
        filename = (
            f"aws_vpcflowlogs_batch_{day_compact}T{ts}_"
            f"{file_idx:04d}.parquet"
        )
        path = out_dir / filename

        is_last_file = file_idx == args.file_count - 1

        cols = {field.name: [] for field in schema}
        file_byte_sum = 0

        start_value = day_epoch + file_idx * 60
        end_value = start_value + 59

        for local_idx in range(nrows):
            global_idx = row_offset + local_idx

            if is_last_file and local_idx == nrows - 1:
                # Force the final row to make the synthetic total exact.
                byt_value = remaining_bytes - file_byte_sum
            else:
                byt_value = (
                    base_byte
                    + (1 if global_idx < byte_remainder else 0)
                    + ((global_idx * byte_multiplier) % spread)
                    - half_spread
                )

            if byt_value < 1:
                byt_value = 1

            file_byte_sum += byt_value

            packets_value = 1 + ((global_idx * 17) % 20)

            for field in schema:
                name = field.name

                if name == "version":
                    cols[name].append(1)
                elif name == "account_id":
                    cols[name].append(account_id)
                elif name == "interface_id":
                    cols[name].append(interface_id)
                elif name == "srcaddr":
                    cols[name].append(srcaddr)
                elif name == "dstaddr":
                    cols[name].append(dstaddr)
                elif name == "srcport":
                    cols[name].append(srcport)
                elif name == "dstport":
                    cols[name].append(dstport)
                elif name == "protocol":
                    cols[name].append(protocol)
                elif name == "packets":
                    cols[name].append(packets_value)
                elif name == "byt":
                    cols[name].append(byt_value)
                elif name == "start":
                    cols[name].append(start_value)
                elif name == "end":
                    cols[name].append(end_value)
                elif name == "action":
                    cols[name].append(action)
                elif name == "log_status":
                    cols[name].append(log_status)
                else:
                    raise ValueError(f"Unhandled schema field: {name}")

        remaining_bytes -= file_byte_sum

        table = pa.table(
            {
                field.name: pa.array(cols[field.name], type=field.type)
                for field in schema
            }
        )

        pq.write_table(
            table,
            path,
            compression=args.compression,
            row_group_size=nrows,
            use_dictionary=True,
            write_statistics=True,
        )

        files_written += 1
        row_offset += nrows
        on_disk_bytes += path.stat().st_size

    avg_file_kib = (on_disk_bytes / files_written / 1024) if files_written else 0.0
    total_mib = on_disk_bytes / (1024 ** 2)

    print("Synthetic VPC Flow Log generation complete.")
    print(f"  Date:              {d.isoformat()}")
    print(f"  Output directory:  {out_dir}")
    print(f"  Schema:            {args.schema}")
    print(f"  Compression:       {args.compression}")
    print(f"  Files written:     {files_written:,}")
    print(f"  Total rows:        {row_offset:,}")
    print(f"  Target bytes:      {total_bytes:,}")
    print(f"  On-disk size:      {total_mib:.2f} MiB")
    print(f"  Average file size: {avg_file_kib:.2f} KiB")

    if remaining_bytes != 0:
        print(
            "WARNING: remaining byte adjustment is non-zero: "
            f"{remaining_bytes:,}. This should not happen with default inputs."
        )


if __name__ == "__main__":
    main()