# Benchmarks the logic from 01_groupby.py through 05_approx_quantile.py,
# running each script's workload 5 times and reporting the best time.

import time

import polars as pl

months = [f"data/yellow_tripdata_2024-{m:02d}.parquet" for m in range(1, 11)]


def groupby():
    # 01_groupby.py - route-by-hour group-by over 10 months (33M rows)
    trips = pl.scan_parquet(months)
    return (
        trips.group_by(
            "PULocationID",
            "DOLocationID",
            pl.col("tpep_pickup_datetime").dt.truncate("1h").alias("pickup_hour"),
        )
        .agg(
            pl.len().alias("trips"),
            pl.col("fare_amount").mean().alias("avg_fare"),
        )
        .collect()
    )


def sql_queries():
    # 02_sql_queries.py - read_parquet with a list of paths, DATE_TRUNC, generate_series
    trips = pl.scan_parquet("data/taxi.parquet")

    pl.sql(
        """
        SELECT COUNT(*) AS trips
        FROM read_parquet([
            'data/yellow_tripdata_2024-01.parquet',
            'data/yellow_tripdata_2024-02.parquet',
            'data/yellow_tripdata_2024-03.parquet'
        ])
        """,
        eager=True,
    )

    pl.sql(
        """
        SELECT
            tpep_pickup_datetime,
            DATE_TRUNC('hour', tpep_pickup_datetime) AS pickup_hour
        FROM trips
        WHERE PULocationID = 12
          AND CAST(tpep_pickup_datetime AS DATE) = '2024-01-02'
        ORDER BY tpep_pickup_datetime
        LIMIT 4
        """,
        eager=True,
    )

    pl.sql(
        """
        SELECT *
        FROM generate_series(
            TIMESTAMP '2024-01-02 06:00:00',
            TIMESTAMP '2024-01-02 09:00:00',
            INTERVAL '1 hour'
        ) AS t(pickup_hour)
        """,
        eager=True,
    )


def encrypt():
    # 03_encrypt.py - write and read a Parquet file with encrypted payment columns
    trips = pl.read_parquet("data/taxi.parquet")

    footer_key = b"footer-key-16byt"
    payment_key = b"payment-key-16by"
    payment_columns = {"fare_amount": payment_key, "tip_amount": payment_key}

    encryption = pl.ParquetEncryptionProperties(
        footer_key=footer_key,
        column_keys=payment_columns,
        plaintext_footer=True,
    )
    trips.write_parquet("data/trips_encrypted.parquet", encryption=encryption)

    pl.read_parquet("data/trips_encrypted.parquet", columns=["PULocationID", "trip_distance"])

    decryption = pl.ParquetDecryptionProperties(footer_key=footer_key, column_keys=payment_columns)
    pl.read_parquet(
        "data/trips_encrypted.parquet",
        columns=["fare_amount", "tip_amount"],
        decryption=decryption,
    )


def join_where_full():
    # 04_join_where_full.py - range join that keeps unmatched rows from both sides
    trips = pl.DataFrame({"pickup_hour": [8, 13]})
    rush = pl.DataFrame({"period": ["morning", "evening"], "start": [7, 17], "end": [9, 19]})

    return trips.join_where(
        rush, pl.col("pickup_hour").is_between("start", "end"), how="full"
    )


def approx_quantile():
    # 05_approx_quantile.py - exact vs approximate median on 33M fares
    fares = pl.scan_parquet(months)

    exact = pl.col("fare_amount").quantile(0.5).alias("exact_median")
    approx = pl.col("fare_amount").approx_quantile(0.5).alias("approx_median")

    return fares.select([exact, approx]).collect()


queries = {
    "01_groupby": groupby,
    "02_sql_queries": sql_queries,
    "03_encrypt": encrypt,
    "04_join_where_full": join_where_full,
    "05_approx_quantile": approx_quantile,
}


def best_of(fn, runs=5):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)

    return min(times) * 1000


print(f"Polars {pl.__version__}")
for name, fn in queries.items():
    print(f"{name:20s} {best_of(fn):8.1f} ms")
