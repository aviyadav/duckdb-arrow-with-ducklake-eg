import time
from pathlib import Path

import duckdb
import psutil

SQL_DIR = Path("sqls")


def _run_sql_file(con: duckdb.DuckDBPyConnection, filename: str) -> None:
    sql_path = SQL_DIR / filename
    if not sql_path.is_file():
        raise FileNotFoundError(
            f"Could not find {sql_path}. Run the pipeline from the project root."
        )
    con.execute(sql_path.read_text(encoding="utf-8"))


def record_execution() -> None:
    process = psutil.Process()
    start_wall = time.perf_counter()

    con = duckdb.connect()
    try:
        print("Initializing DuckLake...")
        con.execute("INSTALL ducklake; LOAD ducklake;")
        con.execute("""
            ATTACH 'ducklake:metadata.ducklake' AS my_lake (
                DATA_PATH 'data',
                OVERRIDE_DATA_PATH true
            );
        """)
        con.execute("USE my_lake;")

        print("Executing Bronze Layer Ingestion...")
        _run_sql_file(con, "bronze_layer.sql")

        print("Executing Silver Layer Transformation...")
        _run_sql_file(con, "solver_layer.sql")

        print("Executing Gold Layer Aggregation...")
        _run_sql_file(con, "gold_layer.sql")
    finally:
        con.close()

    elapsed_sec = time.perf_counter() - start_wall
    peak_ram_mb = process.memory_info().rss / (1024 * 1024)

    print("\n--- Pipeline Complete ---")
    print(f"Elapsed Wall Time : {elapsed_sec:.2f} seconds")
    print(f"Peak RAM Usage    : {peak_ram_mb:.2f} MB")


if __name__ == "__main__":
    record_execution()
