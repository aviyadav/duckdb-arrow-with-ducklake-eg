import duckdb

# Connect to a file-based database (avoids storing the catalog purely in RAM)
con = duckdb.connect("tpch_temp.db")

# 1. Apply system resource constraints
con.execute("SET memory_limit = '4GB';")
con.execute("SET threads = 4;")
con.execute("SET preserve_insertion_order = false;") # Reduces RAM usage during writes

# 2. Set directory for temp files if DuckDB spills to disk during creation
con.execute("SET temp_directory = './duckdb_temp.tmp';")

# 3. Load the TPC-H extension
con.execute("INSTALL tpch;")
con.execute("LOAD tpch;")
print("Generating TPC-H data (SF=100)… This will take a few minutes.")

# 4. Generate the dataset at Scale Factor 100 into DuckDB tables
con.execute("CALL dbgen(sf=100);")
print("Exporting tables to Parquet files…")

# 5. Export all tables to compressed Parquet files directly
# DuckDB streams the data out, keeping memory footprint low
con.execute("""
EXPORT DATABASE 'tpch_parquet_sf100'
(FORMAT PARQUET, COMPRESSION ZSTD);
""")

# Clean up DuckDB connection and temporary catalog file
con.close()
print("Export complete! Parquet files are saved in the 'tpch_parquet_sf100' folder.")
