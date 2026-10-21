#!/usr/bin/env python3
"""Sanity check: Iceberg and Delta Lake through GizmoSQL.

Iceberg: full round-trip (write + read) via DuckDB's `iceberg` extension.
Delta:   written with the `deltalake` library (as Spark/Delta pipelines
         do), then read through GizmoSQL via DuckDB's `delta_scan`.
"""
import shutil
from pathlib import Path

import pyarrow.csv as pacsv
from adbc_driver_gizmosql import dbapi as gizmosql
from deltalake import write_deltalake
from gizmo import conn_args

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

ICEBERG_DIR = "/opt/gizmosql/data/iceberg_trips"
DELTA_DIR = "/opt/gizmosql/data/delta_trips"
HOST_DELTA_DIR = DATA_DIR / "delta_trips"


def fetch_one(cur, sql):
    cur.execute(sql)
    return cur.fetch_arrow_table().to_pandas().iloc[0, 0]


def main():
    files = sorted(DATA_DIR.glob("*.csv"))[:1]
    sample = pacsv.read_csv(files[0]).select(
        ["ride_id", "rideable_type", "member_casual", "started_at"]).slice(0, 2000)
    print(f"sample: {sample.num_rows:,} rows")

    if HOST_DELTA_DIR.exists():
        shutil.rmtree(HOST_DELTA_DIR)
    write_deltalake(str(HOST_DELTA_DIR), sample)
    print("wrote Delta table on the host (via deltalake)")

    with gizmosql.connect(**conn_args()) as conn, conn.cursor() as cur:
        print("== Iceberg (write + read through GizmoSQL) ==")
        cur.execute("INSTALL iceberg; LOAD iceberg;")
        cur.execute(
            "CREATE OR REPLACE TABLE sample_trips AS "
            "SELECT ride_id, rideable_type, member_casual, started_at "
            "FROM trips LIMIT 2000")
        cur.execute(f"COPY sample_trips TO '{ICEBERG_DIR}' (FORMAT ICEBERG)")
        n = fetch_one(cur, f"SELECT count(*) FROM iceberg_scan('{ICEBERG_DIR}')")
        print(f"  wrote + read back {n:,} rows from Iceberg")

        print("== Delta Lake (read through GizmoSQL) ==")
        cur.execute("INSTALL delta; LOAD delta;")
        n = fetch_one(cur, f"SELECT count(*) FROM delta_scan('{DELTA_DIR}')")
        print(f"  read back {n:,} rows from Delta Lake")


if __name__ == "__main__":
    main()
