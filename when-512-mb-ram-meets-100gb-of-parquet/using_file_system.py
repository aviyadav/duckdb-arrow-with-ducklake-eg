import os
import threading
import time
import duckdb

peak_spill_bytes = 0
monitoring = True


def monitor_spill_directory(temp_dir):
    global peak_spill_bytes, monitoring
    while monitoring:
        if os.path.exists(temp_dir):
            try:
                current_bytes = sum(
                    os.path.getsize(os.path.join(temp_dir, f))
                    for f in os.listdir(temp_dir)
                    if os.path.isfile(os.path.join(temp_dir, f))
                )
                if current_bytes > peak_spill_bytes:
                    peak_spill_bytes = current_bytes
            except Exception:
                pass
        time.sleep(0.1)


# Start background monitor thread
temp_dir = "./duckdb_temp.tmp"
# memory_limit = "4GB"
memory_limit = "512MB"
monitor_thread = threading.Thread(
    target=monitor_spill_directory, args=(temp_dir,)
)
monitor_thread.start()

# --- Run Query ---
con = duckdb.connect()
con.execute(f"SET memory_limit = '{memory_limit}';")
con.execute("SET threads = 4;")
con.execute(f"SET temp_directory = '{temp_dir}';")

base_path = "tpch_parquet_sf100"
con.execute(
    f"CREATE VIEW lineitem AS SELECT * FROM read_parquet('lineitem_partitioned/*.parquet');"
)
con.execute(
    f"CREATE VIEW orders AS SELECT * FROM read_parquet('orders_partitioned/*.parquet');"
)
con.execute(
    f"CREATE VIEW customer AS SELECT * FROM read_parquet('{base_path}/customer.parquet');"
)

query = """
SELECT
    l_orderkey,
    sum(l_extendedprice * (1 - l_discount)) AS revenue,
    o_orderdate,
    o_shippriority
FROM customer
JOIN orders ON c_custkey = o_custkey
JOIN lineitem ON l_orderkey = o_orderkey
WHERE c_mktsegment = 'BUILDING'
  AND o_orderdate < DATE '1995-03-15'
  AND l_shipdate > DATE '1995-03-15'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC
LIMIT 10;
"""

print("Executing query...")
# res = con.execute(query).df()
res = con.sql(query).pl()

# Stop background monitor thread
monitoring = False
monitor_thread.join()

con.close()

print(f"\n--- Out-of-Core Execution Summary ---")
print(f"Peak RAM Cap Allowed: '{memory_limit}'")
print(f"Peak Disk Space Used for Spilling: {peak_spill_bytes / (1024**3):.2f} GB")
