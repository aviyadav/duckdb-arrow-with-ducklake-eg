import time
import tracemalloc
from pathlib import Path
from typing import NamedTuple

import duckdb
import pyarrow as pa

DATA_DIR = Path("data")

# The three sources under test; only the FROM clause differs between queries.
SOURCES = {
    "CSV": f"read_csv('{DATA_DIR / 'events.csv'}', header = true)",
    "Parquet (ZSTD)": f"read_parquet('{DATA_DIR / 'events_compressed.parquet'}')",
    "Parquet (uncompressed)": f"read_parquet('{DATA_DIR / 'events_uncompressed.parquet'}')",
}

QUERY_TEMPLATE = """
SELECT
    country,
    SUM(revenue) AS revenue
FROM {source}
WHERE CAST(event_date AS DATE) >= DATE '2025-01-01'
  AND country IN ('US', 'UK', 'DE')
  AND revenue > 0
GROUP BY country
ORDER BY revenue DESC;
"""


class BenchmarkResult(NamedTuple):
    label: str
    table: pa.Table
    elapsed_sec: float
    peak_mem_mb: float


def run_benchmark(label: str, source: str) -> BenchmarkResult:
    """Run the aggregation query against one source, timing it and tracking peak memory."""
    query = QUERY_TEMPLATE.format(source=source)

    tracemalloc.start()
    start_time = time.perf_counter()

    table = duckdb.sql(query).arrow().read_all()

    elapsed_sec = time.perf_counter() - start_time
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return BenchmarkResult(label, table, elapsed_sec, peak_mem / (1024 * 1024))


def print_summary(results: list[BenchmarkResult]) -> None:
    print("\n" + "=" * 62)
    print(" - - Performance Summary - -")
    print("=" * 62)
    print(f"{'Source':<26} | {'Time (s)':>10} | {'Peak Memory (MB)':>18}")
    print("-" * 62)
    for r in results:
        print(f"{r.label:<26} | {r.elapsed_sec:>10.4f} | {r.peak_mem_mb:>18.2f}")
    print("=" * 62)


def main() -> None:
    results = [run_benchmark(label, source) for label, source in SOURCES.items()]

    for r in results:
        print(f"\n - - Query Result: {r.label} - -")
        print(r.table)

    print_summary(results)


if __name__ == "__main__":
    main()
