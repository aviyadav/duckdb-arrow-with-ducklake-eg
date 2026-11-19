import threading
import time
from pathlib import Path

import duckdb
import psutil

# File paths
csv_path = Path("data") / "events.csv"
parquet_path = Path("data") / "events.parquet"

# Ensure the source file exists
if not csv_path.exists():
    raise FileNotFoundError(
        f"Please generate the CSV dataset first. Missing: {csv_path}"
    )

con = duckdb.connect()
# --- DUCKDB 2.0 FEATURE: Session Variables ($variable syntax) ---
con.execute("SET VARIABLE target_compression = 'ZSTD';")

# --- IDENTIFY DUCKDB VERSION ---
db_version = con.execute("SELECT version();").fetchone()[0]

# --- BACKGROUND MEMORY MONITOR LOGIC ---
peak_memory = 0
monitor_active = True


def monitor_memory():
    """Continuously tracks the process memory to catch the peak spike."""
    global peak_memory
    process = psutil.Process()
    while monitor_active:
        try:
            current_mem = process.memory_info().rss
            if current_mem > peak_memory:
                peak_memory = current_mem
        except Exception:
            break
        time.sleep(0.005)


mem_thread = threading.Thread(target=monitor_memory, daemon=True)
mem_thread.start()
# --- BENCHMARK CONFIGURATION ---
num_runs = 3
run_durations = []

# --- DUCKDB 2.0 FEATURE: CTE inside COPY + $variable reference ---
query = f"""
    COPY (
        WITH extracted_events AS (
            SELECT
                event_date,
                country,
                channel,
                user_id,
                order_id,
                revenue
            FROM read_csv(
                '{csv_path}',
                header = true,
                delim = ',',
                columns = {{
                    'event_date': 'DATE',
                    'country': 'VARCHAR',
                    'channel': 'VARCHAR',
                    'user_id': 'INTEGER',
                    'order_id': 'INTEGER',
                    'revenue': 'DOUBLE'
                }}
            )
        )
        SELECT * FROM extracted_events
    ) TO '{parquet_path}' (FORMAT 'PARQUET', COMPRESSION $target_compression);
"""
# --- RUN CONVERSION MULTIPLE TIMES ---
for i in range(1, num_runs + 1):
    start_time = time.perf_counter()
    con.execute(query)
    end_time = time.perf_counter()

    duration = end_time - start_time
    run_durations.append(duration)

# Stop the memory tracking thread safely
monitor_active = False
mem_thread.join()

# --- CALCULATE & PRINT RESULTS ---
avg_duration = sum(run_durations) / len(run_durations)
peak_mb = peak_memory / (1024 * 1024)
csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
parquet_size_mb = parquet_path.stat().st_size / (1024 * 1024)

print("=" * 50)
print("CSV to Parquet Export Metrics (DuckDB 2.0 Optimized):")
print("=" * 50)
print(f"DuckDB Version:          {db_version}")
print(f"Peak Memory Usage:       {peak_mb:.2f} MB")
print("-" * 50)
for i, duration in enumerate(run_durations, 1):
    print(f"Run {i} Conversion Time:     {duration:.4f} seconds")
print("-" * 50)
print(f"Average Conversion Time: {avg_duration:.4f} seconds")
print("-" * 50)
print(f"Original CSV Size:       {csv_size_mb:.2f} MB")
print(f"Optimized Parquet Size:  {parquet_size_mb:.2f} MB")
print("=" * 50)
print(f"File successfully saved to: {parquet_path}")
