import argparse
import os
import time
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
from adbc_driver_gizmosql import dbapi as gizmosql

# Read-only key published by Backblaze for the public Drive Stats bucket
B2_KEY_ID = os.environ.get("B2_KEY_ID", "0045f0571db506a0000000017")
B2_SECRET = os.environ.get("B2_SECRET", "K004Fs/bgmTk5dgo6GAVm2Waj3Ka+TE")
B2_REGION = "us-west-004"
B2_ENDPOINT = "s3.us-west-004.backblazeb2.com"
TABLE_ROOT = "s3://drivestats-iceberg/drivestats"

LOCAL_DB = Path(__file__).parent / "data" / "drivestats_results.duckdb"
RESULT_TABLE = "model_monthly_health"

CONN_ARGS = dict(
    uri=os.environ.get("GIZMOSQL_URI", "gizmosql://benchmark-97f775ae655c49188bd5159d953c4106.us-east-2.aws.sql.gizmodata.com:443"),
    username=os.environ.get("GIZMOSQL_USERNAME", "gizmosql_admin"),
    password=os.environ.get("GIZMOSQL_PASSWORD", "bingbongdingdong"),
    tls_skip_verify=os.environ.get("GIZMOSQL_TLS_SKIP_VERIFY", "0") == "1",  # set to 1 for the local container's self-signed cert
)

# Per drive, per day: window functions over each drive's daily history, then
# a rollup to model x month. RANGE frames use calendar days, so gaps in a
# drive's reporting don't stretch the windows.
#
# The query runs one chunk of whole months at a time so it fits in server
# memory. Every frame reaches at most 30 days back or forward, so each chunk
# scans MARGIN_DAYS of extra data on both sides, then keeps only its own
# months. Chunks never share a month, so their outputs just concatenate.
MARGIN_DAYS = 31
WINDOW_SQL = """
WITH daily AS (
    SELECT date, serial_number, model, capacity_bytes, failure,
           smart_5_raw   AS reallocated_sectors,
           smart_9_raw   AS power_on_hours,
           smart_194_raw AS temperature_c
    FROM drivestats
    WHERE date >= DATE '{start}' - INTERVAL {margin} DAY AND date < DATE '{end}' + INTERVAL {margin} DAY
),
per_drive AS (
    SELECT *,
           reallocated_sectors - lag(reallocated_sectors) OVER d                                      AS realloc_delta,
           avg(temperature_c)          OVER (d RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW) AS temp_7d_avg,
           max(temperature_c)          OVER (d RANGE BETWEEN INTERVAL 29 DAYS PRECEDING AND CURRENT ROW) AS temp_30d_max,
           max(failure)                OVER (d RANGE BETWEEN CURRENT ROW AND INTERVAL 29 DAYS FOLLOWING) AS fails_within_30d
    FROM daily
    WINDOW d AS (PARTITION BY serial_number ORDER BY date)
)
SELECT model,
       date_trunc('month', date)::DATE                                        AS month,
       any_value(capacity_bytes) / 1e12                                       AS capacity_tb,
       count(*)                                                               AS drive_days,
       count(DISTINCT serial_number)                                          AS drives,
       sum(failure)                                                           AS failures,
       round(sum(failure) * 365.0 * 100 / count(*), 3)                        AS annualized_failure_rate_pct,
       round(avg(temp_7d_avg), 2)                                             AS avg_temp_7d,
       max(temp_30d_max)                                                      AS max_temp_30d,
       round(avg(power_on_hours) / 24 / 365, 2)                               AS avg_age_years,
       count(*) FILTER (WHERE realloc_delta > 0)                              AS realloc_growth_days,
       count(*) FILTER (WHERE fails_within_30d = 1)                           AS pre_failure_drive_days,
       round(avg(reallocated_sectors) FILTER (WHERE fails_within_30d = 1), 1) AS avg_realloc_pre_failure,
       round(avg(reallocated_sectors) FILTER (WHERE fails_within_30d = 0), 1) AS avg_realloc_healthy
FROM per_drive
WHERE date >= DATE '{start}' AND date < DATE '{end}'
GROUP BY ALL
ORDER BY month, model
"""


def setup_source(cur) -> str:
    """Point the server session at the Iceberg table and return the metadata file used."""
    cur.execute("INSTALL httpfs; LOAD httpfs; INSTALL iceberg; LOAD iceberg;")
    cur.execute(f"""
        CREATE OR REPLACE SECRET drivestats_b2 (
            TYPE s3, KEY_ID '{B2_KEY_ID}', SECRET '{B2_SECRET}',
            REGION '{B2_REGION}', ENDPOINT '{B2_ENDPOINT}', URL_STYLE 'path',
            SCOPE '{TABLE_ROOT}'
        )
    """)
    # No version-hint.text in the bucket: pick the newest metadata file.
    # Names start with a zero-padded sequence number, so max() is the latest.
    cur.execute(f"SELECT max(file) FROM glob('{TABLE_ROOT}/metadata/*.metadata.json')")
    metadata = cur.fetchone()[0]
    cur.execute(f"CREATE OR REPLACE TEMP VIEW drivestats AS SELECT * FROM iceberg_scan('{metadata}')")
    return metadata


def show(cur, title: str, sql: str, max_rows: int = 50) -> None:
    start = time.perf_counter()
    cur.execute(sql)
    df = cur.fetch_arrow_table().to_pandas()
    print(f"\n== {title}  ({time.perf_counter() - start:.2f}s)")
    print(df.to_string(index=False, max_rows=max_rows))


def stats(cur, metadata: str, start: str, end: str) -> None:
    # File-level row counts come from the manifests, so nothing is scanned here.
    # Partition values are month strings, so filter on the date_month= path part.
    show(cur, f"Rows to process, {start} to {end} (from Iceberg manifests)", f"""
        WITH files AS (
            SELECT regexp_extract(file_path, 'date_month=([0-9-]+)', 1) AS month, record_count
            FROM iceberg_metadata('{metadata}')
            WHERE status <> 'DELETED'
        )
        SELECT left(month, 4) AS year, count(*) AS data_files, sum(record_count) AS rows
        FROM files
        WHERE month >= left('{start}', 7) AND month < left('{end}', 7)
        GROUP BY ALL
        UNION ALL
        SELECT 'TOTAL', count(*), sum(record_count)
        FROM files
        WHERE month >= left('{start}', 7) AND month < left('{end}', 7)
        ORDER BY year
    """)
    show(cur, "Whole table (current snapshot)", f"""
        SELECT count(*) AS data_files, sum(record_count) AS rows,
               min(regexp_extract(file_path, 'date_month=([0-9-]+)', 1)) AS first_month,
               max(regexp_extract(file_path, 'date_month=([0-9-]+)', 1)) AS last_month
        FROM iceberg_metadata('{metadata}')
        WHERE status <> 'DELETED'
    """)

    cur.execute("DESCRIBE drivestats")
    schema = cur.fetch_arrow_table().to_pandas()
    smart = schema[schema.column_name.str.startswith("smart_")]
    other = schema[~schema.column_name.str.startswith("smart_")]
    print(f"\n== Schema: {len(schema)} columns ({len(smart)} SMART attributes)")
    print(other[["column_name", "column_type"]].to_string(index=False))
    print(f"  + {len(smart)} smart_<id>_raw / smart_<id>_normalized BIGINT columns")

    show(cur, "Sample rows (columns used by the benchmark)", f"""
        SELECT date, serial_number, model, capacity_bytes, failure,
               smart_5_raw, smart_9_raw, smart_194_raw, datacenter
        FROM drivestats
        WHERE date = DATE '{start}'
        LIMIT 10
    """)


def month_chunks(start: str, end: str, months: int) -> list[tuple[str, str]]:
    """Split [start, end) into consecutive ranges of whole months."""
    chunks, cur, stop = [], date.fromisoformat(start), date.fromisoformat(end)
    while cur < stop:
        m = cur.month - 1 + months
        nxt = min(date(cur.year + m // 12, m % 12 + 1, 1), stop)
        chunks.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2023-01-01", help="inclusive, YYYY-MM-DD (default %(default)s)")
    parser.add_argument("--end", default="2026-01-01", help="exclusive, YYYY-MM-DD (default %(default)s)")
    parser.add_argument("--skip-stats", action="store_true", help="only run the benchmark query")
    parser.add_argument("--chunk-months", type=int, default=3,
                        help="months per server query; lower it if the server runs out of memory (default %(default)s)")
    args = parser.parse_args()

    total_start = time.perf_counter()
    with gizmosql.connect(**CONN_ARGS) as conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(f"Connected to {CONN_ARGS['uri']} (DuckDB {cur.fetchone()[0]})")
        cur.execute("SELECT current_setting('threads'), current_setting('memory_limit')")
        threads, mem = cur.fetchone()
        print(f"Server: {threads} threads, memory_limit {mem}")

        metadata = setup_source(cur)
        print(f"Iceberg metadata: {metadata}")

        if not args.skip_stats:
            stats(cur, metadata, args.start, args.end)

        cur.execute("SET preserve_insertion_order = false")  # lets DuckDB spill more freely
        chunks = month_chunks(args.start, args.end, args.chunk_months)
        print(f"\n== Benchmark: window functions per drive, {args.start} to {args.end}"
              f" ({len(chunks)} chunks of {args.chunk_months} months, {MARGIN_DAYS}-day margins)")
        query_start = time.perf_counter()
        parts = []
        for chunk_start, chunk_end in chunks:
            t = time.perf_counter()
            cur.execute(WINDOW_SQL.format(start=chunk_start, end=chunk_end, margin=MARGIN_DAYS))
            parts.append(cur.fetch_arrow_table())  # Arrow over Flight SQL
            print(f"  {chunk_start} to {chunk_end}: {time.perf_counter() - t:7.2f}s"
                  f"  {sum(parts[-1].column('drive_days').to_pylist()):>12,} drive-days")
        result = pa.concat_tables(parts)
        query_secs = time.perf_counter() - query_start

    write_start = time.perf_counter()
    LOCAL_DB.parent.mkdir(exist_ok=True)
    with duckdb.connect(str(LOCAL_DB)) as local:
        local.execute(f"CREATE OR REPLACE TABLE {RESULT_TABLE} AS SELECT * FROM result")
        rows_in, drive_days, failures = local.execute(
            f"SELECT count(*), sum(drive_days)::BIGINT, sum(failures)::BIGINT FROM {RESULT_TABLE}"
        ).fetchone()
        top = local.execute(f"""
            SELECT model, sum(drive_days)::BIGINT AS drive_days, sum(failures)::BIGINT AS failures,
                   round(sum(failures) * 365.0 * 100 / sum(drive_days), 2) AS afr_pct
            FROM {RESULT_TABLE}
            GROUP BY model
            HAVING sum(drive_days) > 1000000
            ORDER BY afr_pct DESC
            LIMIT 10
        """).df()
    write_secs = time.perf_counter() - write_start

    print(f"  server scan + windows + fetch: {query_secs:.2f}s")
    print(f"  local DuckDB write:            {write_secs:.2f}s")
    print(f"  total wall clock:              {time.perf_counter() - total_start:.2f}s")
    print(f"  source rows processed:         {drive_days:,} drive-days, {failures:,} failures")
    print(f"  result:                        {rows_in:,} rows -> {LOCAL_DB}:{RESULT_TABLE}")
    print("\n== Highest annualized failure rate (models with >1M drive-days in range)")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
