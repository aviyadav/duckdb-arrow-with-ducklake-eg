#!/usr/bin/env python3
"""Query Divvy CSV data over GizmoSQL (DuckDB + Arrow Flight SQL).

Prereq: `docker compose up -d` and `python scripts/download_divvy.py`.
"""
import os
import time

from adbc_driver_gizmosql import dbapi as gizmosql
from gizmo import conn_args

CSV_GLOB = os.environ.get("DIVVY_CSV_GLOB", "/opt/gizmosql/data/*.csv")

QUERIES = {
    "Rows and date range across all CSV files": """
        SELECT count(*)                 AS trips,
               count(DISTINCT filename) AS csv_files,
               min(started_at)          AS first_trip,
               max(started_at)          AS last_trip
        FROM trips
    """,
    "Members vs casual riders": """
        SELECT member_casual,
               count(*) AS trips,
               round(avg(date_diff('second', started_at, ended_at)) / 60, 1) AS avg_minutes
        FROM trips
        GROUP BY ALL
        ORDER BY trips DESC
    """,
    "Bike types": """
        SELECT rideable_type, count(*) AS trips
        FROM trips
        GROUP BY ALL
        ORDER BY trips DESC
    """,
    "Top 10 start stations": """
        SELECT start_station_name, count(*) AS trips
        FROM trips
        WHERE start_station_name IS NOT NULL
        GROUP BY ALL
        ORDER BY trips DESC
        LIMIT 10
    """,
    "Busiest hours of the day": """
        SELECT hour(started_at) AS hour_of_day, count(*) AS trips
        FROM trips
        GROUP BY ALL
        ORDER BY trips DESC
        LIMIT 5
    """,
}


def main() -> None:
    with gizmosql.connect(**conn_args()) as conn, conn.cursor() as cur:
        cur.execute("SELECT version() AS duckdb_version")
        print(f"Connected to GizmoSQL -- DuckDB {cur.fetchone()[0]}\n")

        cur.execute(
            "CREATE OR REPLACE VIEW trips AS "
            f"SELECT * FROM read_csv('{CSV_GLOB}', union_by_name = true, filename = true)"
        )

        for title, sql in QUERIES.items():
            start = time.perf_counter()
            cur.execute(sql)
            table = cur.fetch_arrow_table()  # results arrive as Arrow over Flight SQL
            elapsed = time.perf_counter() - start
            print(f"== {title} ({elapsed:.2f}s)")
            print(table.to_pandas().to_string(index=False))
            print()


if __name__ == "__main__":
    main()
