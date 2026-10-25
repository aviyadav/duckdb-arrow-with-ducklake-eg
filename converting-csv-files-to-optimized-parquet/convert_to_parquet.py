from pathlib import Path
import threading
import time
import duckdb
import psutil

# Define your paths using pathlib matching your directory structure
DATA_DIR = Path("data")
csv_path = DATA_DIR / "events.csv"
compressed_parquet_path = DATA_DIR / "events_compressed.parquet"
uncompressed_parquet_path = DATA_DIR / "events_uncompressed.parquet"

# Global variables for background memory tracking thread
peak_memory = 0
monitor_active = True


def monitor_memory():
    """Continuously tracks the process memory to catch the absolute peak spike."""
    global peak_memory
    process = psutil.Process()
    while monitor_active:
        try:
            current_mem = process.memory_info().rss  # Physical RAM used
            if current_mem > peak_memory:
                peak_memory = current_mem
        except Exception:
            break
        time.sleep(0.01)  # Sample every 10ms


def convert_csv_to_parquet(
    input_csv: Path, output_parquet: Path, compression_type: str
):
    global peak_memory, monitor_active

    # Reset metrics for this specific run
    peak_memory = 0
    monitor_active = True

    # Start the memory tracking background thread
    mem_thread = threading.Thread(target=monitor_memory, daemon=True)
    mem_thread.start()

    # Establish an in-memory DuckDB worker connection
    con = duckdb.connect()
    print(
        f"Starting conversion to Parquet ({compression_type}) from {input_csv}…"
    )
    start_time = time.perf_counter()

    # Stream the data straight from CSV into Parquet format
    con.execute(f"""
    COPY '{input_csv}'
    TO '{output_parquet}'
    (FORMAT 'PARQUET', COMPRESSION '{compression_type}');
    """)
    end_time = time.perf_counter()

    # Shut down the monitoring thread cleanly
    monitor_active = False
    mem_thread.join()
    con.close()

    # Calculate metrics
    elapsed_time = end_time - start_time
    peak_mb = peak_memory / (1024 * 1024)
    file_size_mb = output_parquet.stat().st_size / (1024 * 1024)

    return elapsed_time, peak_mb, file_size_mb


# Ensure the source file actually exists before wasting CPU cycles
if not csv_path.exists():
    raise FileNotFoundError(
        f"Could not find the generated data file at: {csv_path}"
    )

print(
    f"Found source file: {csv_path} ({csv_path.stat().st_size / (1024*1024*1024):.2f} GB)"
)
print("Starting benchmarks…\n")

# Run Method 1: ZSTD Compressed
time_comp, mem_comp, size_comp = convert_csv_to_parquet(
    csv_path, compressed_parquet_path, "ZSTD"
)

# Run Method 2: Uncompressed
time_uncomp, mem_uncomp, size_uncomp = convert_csv_to_parquet(
    csv_path, uncompressed_parquet_path, "UNCOMPRESSED"
)

# - - PRINT RUN PERFORMANCE REPORT - -
print("\n" + "=" * 55)
print(" DUCKDB CONVERSION PERFORMANCE REPORT ")
print("=" * 55)
print(f"{'Metric':<23} | {'Compressed (ZSTD)':<16} | {'Uncompressed':<12}")
print("-" * 55)
print(
    f"{'Time Elapsed':<23} | {time_comp:.2f} seconds | {time_uncomp:.2f} seconds"
)
print(
    f"{'Peak Memory (RSS)':<23} | {mem_comp:.2f} MB | {mem_uncomp:.2f} MB"
)
print(
    f"{'Output File Size':<23} | {size_comp:.2f} MB | {size_uncomp:.2f} MB"
)
print("=" * 55)
