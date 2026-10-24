import duckdb

# Connect to an disk-backed instance to allow temporary spillover
con = duckdb.connect("partition_temp.db")

# Apply memory and thread safety controls
con.execute("SET memory_limit = '4GB';")
con.execute("SET threads = 4;")
con.execute("SET temp_directory = './duckdb_temp.tmp';")

print("Partitioning lineitem.parquet into smaller files...")

# 1. Partition lineitem.parquet into ~500MB chunks (approx 10 million rows per file)
con.execute("""
    COPY (SELECT * FROM read_parquet('tpch_parquet_sf100/lineitem.parquet'))
    TO 'lineitem_partitioned'
    (FORMAT PARQUET, COMPRESSION ZSTD, PER_THREAD_OUTPUT TRUE, ROW_GROUP_SIZE 100000);
""")

print("Partitioning orders.parquet...")

# 2. Partition orders.parquet
con.execute("""
    COPY (SELECT * FROM read_parquet('tpch_parquet_sf100/orders.parquet'))
    TO 'orders_partitioned'
    (FORMAT PARQUET, COMPRESSION ZSTD, PER_THREAD_OUTPUT TRUE, ROW_GROUP_SIZE 100000);
""")

con.close()
print("Partitioning complete!")
