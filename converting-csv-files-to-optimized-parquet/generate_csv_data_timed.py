from pathlib import Path
import time
import duckdb

# Define data directory and target path
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

row_count = 10_000_000
csv_path = DATA_DIR / "events.csv"
num_runs = 3

# Connect to an in-memory DuckDB database
con = duckdb.connect()

# Output DuckDB version
db_version = con.execute("SELECT version();").fetchone()[0]
print(f"DuckDB Version: {db_version}\n")

print(f"Starting {num_runs} benchmark runs for {row_count:,} rows...")

durations = []

for i in range(1, num_runs + 1):
    start_time = time.perf_counter()

    # Generate data and write directly to CSV
    con.execute(
        f"""
        COPY (
            SELECT
                -- 1. Generate random dates between 2024-01-01 and 2026-01-31
                '2024-01-01'::DATE + CAST(floor(random() * (DATE '2026-01-31' - DATE '2024-01-01' + 1)) AS INTEGER) AS event_date,

                -- 2. Randomly pick a country from the list
                (['US', 'UK', 'DE', 'FR', 'IN', 'JP'])[CAST(floor(random() * 6) + 1 AS INTEGER)] AS country,

                -- 3. Randomly pick a marketing channel
                (['search', 'social', 'email', 'direct'])[CAST(floor(random() * 4) + 1 AS INTEGER)] AS channel,

                -- 4. Generate random user_id between 1 and 200,000
                CAST(floor(random() * 200000) + 1 AS INTEGER) AS user_id,

                -- 5. Generate random order_id between 1 and 900,000
                CAST(floor(random() * 900000) + 1 AS INTEGER) AS order_id,
                -- 6. Generate Gamma-like skewed revenue, with a 15% chance of being 0
                CASE
                    WHEN random() < 0.15 THEN 0.0
                    ELSE round(
                        (-log(random()) - log(random())) * 30.0, 2
                    )
                END AS revenue
            FROM generate_series(1, {row_count})
        ) TO '{csv_path}' (HEADER, DELIMITER ',');
        """
    )

    end_time = time.perf_counter()
    duration = end_time - start_time
    durations.append(duration)
    print(f"Run {i}: {duration:.2f} seconds")

# Calculate and display the average
avg_duration = sum(durations) / len(durations)
print(f"\nAverage run time across {num_runs} runs: {avg_duration:.2f} seconds")
