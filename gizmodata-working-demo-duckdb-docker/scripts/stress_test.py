#!/usr/bin/env python3
"""Concurrent write/read test for the GizmoSQL server (bounded local demo).

Part A: N processes write to ONE local DuckDB file directly (DuckDB
        allows only one read-write process per file).
Part B: N processes, each with its own ADBC session, ingest Arrow
        batches into GizmoSQL while reader processes poll the row count.

The workload size follows the local Divvy CSVs and the --workers/--readers
caps (defaults match the article). Nothing is written outside ./data.
"""
import argparse
import multiprocessing as mp
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv
from adbc_driver_gizmosql import dbapi as gizmosql
from gizmo import conn_args

DATA_DIR = Path(os.environ.get(
    "DIVVY_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
TARGET_TABLE = "trips_ingested"
LOG_TABLE = "ingest_log"


def connect():
    return gizmosql.connect(**conn_args())


def embedded_writer(db_path, worker, barrier):
    barrier.wait()
    try:
        con = duckdb.connect(db_path)
        con.execute("CREATE TABLE IF NOT EXISTS t (worker INT, ts TIMESTAMP)")
        con.execute("INSERT INTO t VALUES (?, now())", [worker])
        time.sleep(1)  # hold the connection open, like a long-lived client
        con.close()
        return "ok"
    except duckdb.Error as e:
        return f"FAILED: {str(e).splitlines()[0][:110]}"


def part_a(workers):
    print(f"\n=== Part A: {workers} processes writing to ONE local DuckDB file ===")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "embedded.duckdb")
        with mp.Manager() as manager:
            barrier = manager.Barrier(workers)
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(
                    embedded_writer, [db_path] * workers, range(workers),
                    [barrier] * workers))
    for i, r in enumerate(results):
        print(f"  process {i}: {r}")
    ok = results.count("ok")
    print(f"  -> {ok}/{workers} succeeded (DuckDB allows one read-write process per file).")


_conn = None


def init_worker():
    global _conn
    _conn = connect()


def to_ipc(table):
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as w:
        w.write_table(table)
    return sink.getvalue().to_pybytes()


def ingest_batch(batch_id, payload):
    batch = pa.ipc.open_stream(payload).read_all()
    start = time.perf_counter()
    with _conn.cursor() as cur:
        rows = cur.adbc_ingest(TARGET_TABLE, batch, mode="append")
        cur.execute(
            f"INSERT INTO {LOG_TABLE} VALUES (?, ?, ?, now())",
            parameters=[batch_id, os.getpid(), rows],
        )
    return batch_id, os.getpid(), rows, time.perf_counter() - start


def reader(stop, out):
    """Poll the row count while writers run; reads must never block."""
    seen = []
    with connect() as conn, conn.cursor() as cur:
        while not stop.is_set():
            cur.execute(f"SELECT count(*) FROM {TARGET_TABLE}")
            seen.append(cur.fetchone()[0])
            time.sleep(0.05)
    out.put(seen)


def load_source(limit_files):
    files = sorted(DATA_DIR.glob("*.csv"))[:limit_files]
    if not files:
        raise SystemExit(f"No CSV files in {DATA_DIR}")
    tables = []
    for f in files:
        names = pacsv.open_csv(f).schema.names
        opts = pacsv.ConvertOptions(
            column_types={n: pa.string() for n in names}, strings_can_be_null=True)
        tables.append(pacsv.read_csv(f, convert_options=opts))
    print(f"Loaded {sum(t.num_rows for t in tables):,} rows from "
          f"{len(files)} CSV file(s) on the client")
    return pa.concat_tables(tables, promote_options="default").combine_chunks()


def setup_tables(source):
    with connect() as conn, conn.cursor() as cur:
        cols = ", ".join(f'"{name}" VARCHAR' for name in source.schema.names)
        cur.execute(f"CREATE OR REPLACE TABLE {TARGET_TABLE} ({cols})")
        cur.execute(f"DROP TABLE IF EXISTS {LOG_TABLE}")
        cur.execute(f"CREATE TABLE {LOG_TABLE} "
                    f"(batch_id INT, pid INT, rows BIGINT, written_at TIMESTAMP)")


def part_b(source, workers, batch_rows, readers):
    batches = [to_ipc(source.slice(off, batch_rows))
               for off in range(0, source.num_rows, batch_rows)]
    print(f"\n=== Part B: {workers} processes x own ADBC session -> GizmoSQL ===")
    print(f"  {len(batches)} batches of up to {batch_rows:,} rows, "
          f"{readers} reader process(es) polling")

    setup_tables(source)

    stop, out = mp.Event(), mp.Queue()
    reader_procs = [mp.Process(target=reader, args=(stop, out)) for _ in range(readers)]
    for p in reader_procs:
        p.start()

    results, errors = [], []
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker) as pool:
        futures = [pool.submit(ingest_batch, i, b) for i, b in enumerate(batches)]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append(repr(e))
    elapsed = time.perf_counter() - start

    stop.set()
    reader_counts = [out.get() for _ in reader_procs]
    for p in reader_procs:
        p.join()

    total_rows = sum(r[2] for r in results)
    print(f"  wrote {total_rows:,} rows in {elapsed:.2f}s "
          f"({total_rows / elapsed:,.0f} rows/s, {len(results) * 2} write requests)")
    print(f"  errors: {len(errors)}")
    for e in errors[:5]:
        print(f"    {e}")
    if results:
        lat = sorted(r[3] for r in results)
        print(f"  per-batch latency: p50 {lat[len(lat) // 2]:.3f}s, max {lat[-1]:.3f}s")
    for i, counts in enumerate(reader_counts):
        monotonic = all(a <= b for a, b in zip(counts, counts[1:]))
        print(f"  reader {i}: {len(counts)} reads during writes, "
              f"saw {counts[0]:,} -> {counts[-1]:,} rows, "
              f"never went backwards: {monotonic}")
    return results, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=8, help="writer processes")
    ap.add_argument("--batch-rows", type=int, default=5_000, help="rows per ingest")
    ap.add_argument("--readers", type=int, default=2, help="reader processes polling")
    ap.add_argument("--files", type=int, default=None, help="limit CSV files loaded")
    ap.add_argument("--skip-embedded", action="store_true", help="skip Part A")
    args = ap.parse_args()

    if not args.skip_embedded:
        part_a(args.workers)

    source = load_source(args.files)
    results, errors = part_b(source, args.workers, args.batch_rows, args.readers)
    total_rows = sum(r[2] for r in results)
    if not errors and total_rows == source.num_rows:
        print("\nNo failures: GizmoSQL absorbed concurrent writes and reads "
              "without breaking.")
    else:
        print("\nDone (see errors above).")


if __name__ == "__main__":
    main()
