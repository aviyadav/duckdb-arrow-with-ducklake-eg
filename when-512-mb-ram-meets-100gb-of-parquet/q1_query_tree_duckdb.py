import os
import duckdb

# 1. Connect to your database file
conn = duckdb.connect("tpch_temp.db")

# 2. Define the TPC-H Q1 query string
tpch_q1 = """
SELECT
    l_returnflag,
    l_linestatus,
    SUM(l_quantity) AS sum_qty,
    SUM(l_extendedprice) AS sum_base_price,
    SUM(l_extendedprice * (1 - l_discount)) AS sum_disc_price,
    SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
    AVG(l_quantity) AS avg_qty,
    AVG(l_extendedprice) AS avg_price,
    AVG(l_discount) AS avg_disc,
    COUNT(*) AS count_order
FROM
    lineitem
WHERE
    l_shipdate <= DATE '1998-12-01' - INTERVAL '90' DAY
GROUP BY
    l_returnflag,
    l_linestatus
ORDER BY
    l_returnflag,
    l_linestatus;
"""

# 3. Enable DuckDB profiling output to JSON
conn.execute("PRAGMA enable_profiling = 'query_tree';")
conn.execute("PRAGMA profiling_output = 'q1_profile.txt';")

# 4. Execute query to generate the profile
conn.execute(tpch_q1).fetchall()

# 5. Disable profiling and close connection
conn.execute("PRAGMA disable_profiling;")
conn.close()

# Verify that the JSON profile was created
if os.path.exists("q1_profile.json"):
    print("Detailed query profiling log written to q1_profile.txt")
