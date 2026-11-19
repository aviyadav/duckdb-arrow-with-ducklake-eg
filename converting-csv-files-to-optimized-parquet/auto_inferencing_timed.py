# auto_inferencing_timed.py

import threading
import time
from pathlib import Path

import duckdb
import psutil

csv_path = Path("data") / "events.csv"

# Ensure the source file exists before testing
if not csv_path.exists():
    raise FileNotFoundError(f"Please generate the dataset first. Missing: {csv_path}")

con = duckdb.connect()
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
            current_mem = process.memory_info().rss  # Physical RAM in bytes
            if current_mem > peak_memory:
                peak_memory = current_mem
        except Exception:
            break
        time.sleep(0.005)  # Sample every 5ms for precision


# Start the memory tracking thread
mem_thread = threading.Thread(target=monitor_memory, daemon=True)
mem_thread.start()

# --- BENCHMARK CONFIGURATION ---
num_runs = 3
run_durations = []
results = None
query = f"""
    SELECT
        country,
        ROUND(SUM(revenue), 2) AS total_revenue
    FROM read_csv(
        '{csv_path}',
        header = true,
        delim = ','
        -- no all_varchar or columns parameters = default auto-inference
    )
    GROUP BY country
    ORDER BY total_revenue DESC;
"""
# Run the query multiple times
for i in range(1, num_runs + 1):
    start_time = time.perf_counter()

    # Fetch the results to force full query evaluation
    results = con.execute(query).fetchall()

    end_time = time.perf_counter()
    duration = end_time - start_time
    run_durations.append(duration)

# Stop the memory tracking thread safely
monitor_active = False
mem_thread.join()

# --- CALCULATE & PRINT RESULTS ---
avg_duration = sum(run_durations) / len(run_durations)
peak_mb = peak_memory / (1024 * 1024)

print("=" * 50)
print("DuckDB Benchmark Metrics:")
print("=" * 50)
print(f"DuckDB Version:             {db_version}")
print(f"Peak Memory Usage:          {peak_mb:.2f} MB")
print("-" * 50)

for i, duration in enumerate(run_durations, 1):
    print(f"Run {i} Execution Time:         {duration:.4f} seconds")

print("-" * 50)
print(f"Average Execution Time:     {avg_duration:.4f} seconds")
print("=" * 50)
print("\nQuery Results:")

for row in results:
    print(f"Country: {row[0]:<3} | Total Revenue: ${row[1]:,}")
