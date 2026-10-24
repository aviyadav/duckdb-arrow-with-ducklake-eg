import time
import duckdb

con = duckdb.connect()

# Resource constraints
con.execute("SET memory_limit = '4GB';")
con.execute("SET threads = 4;")
con.execute("SET temp_directory = './duckdb_temp.tmp';")

# 1. Enable Detailed Profiling
con.execute("PRAGMA enable_profiling = 'json';")
con.execute("SET profiling_mode = 'detailed';")
con.execute("PRAGMA profiling_output = 'profile_output.json';")

# 2. Register Parquet Views
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
FROM
    customer
JOIN
    orders ON c_custkey = o_custkey
JOIN
    lineitem ON l_orderkey = o_orderkey
WHERE
    c_mktsegment = 'BUILDING'
    AND o_orderdate < DATE '1995-03-15'
    AND l_shipdate > DATE '1995-03-15'
GROUP BY
    l_orderkey,
    o_orderdate,
    o_shippriority
ORDER BY
    revenue DESC
LIMIT 10;
"""

print("Executing query with detailed profiling enabled...")
start = time.time()

res = con.sql(query).pl()

elapsed = time.time() - start

print(f"Query completed in {elapsed:.2f} seconds.")
con.close()
