import time
from functools import wraps
from pathlib import Path

import polars as pl

_last_elapsed = 0.0


def timed(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        global _last_elapsed
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            diff = elapsed - _last_elapsed
            _last_elapsed = elapsed
            print(f"\n[{fn.__name__}] {elapsed:.3f}s (diff vs previous: {diff:+.3f}s)")

    return wrapper


@timed
def sql_fitst_class_citizen():
    DATA_FILE = Path() / "data" / "yellow_tripdata_2026-01.parquet"
    print(pl.scan_parquet(DATA_FILE).collect_schema().names())

    lazy_df = pl.scan_parquet(DATA_FILE)
    query = """
        SELECT
            tip_amount,
            passenger_count,
            trip_distance
        FROM
            self
        WHERE
            trip_distance > 5
    """

    result = lazy_df.sql(query=query).collect()
    print(result)


@timed
def map_datatype_eg():
    df = pl.DataFrame(
        {
            "user": ["alice", "bob", "carol"],
            "scores": pl.Series(
                [{"math": 90, "art": 75}, {"math": 60}, {}],
                dtype=pl.Map(pl.String, pl.Int64),
            ),
            "subject": ["art", "art", "math"],
        }
    )

    print(df)

    result = df.select(
        "user",
        pl.col("scores").map.get("math").alias("math"),
        pl.col("scores").map.contains_key("art").alias("has_art"),
        pl.col("scores").map.len().alias("n"),
        pl.col("scores").map.keys().alias("keys"),
        pl.col("scores").map.values().alias("values"),
    )

    print(result)


@timed
def query_multiple_df():
    TRIPS_DATA = Path() / "data" / "taxi.parquet"
    ZONE_DATA = Path() / "data" / "taxi_zones.csv"

    trips = pl.scan_parquet(TRIPS_DATA)
    zones = pl.scan_csv(ZONE_DATA)

    query = (
        trips.filter(pl.col("fare_amount") > 0, pl.col("trip_distance") > 0)
        .join(zones, left_on="PULocationID", right_on="LocationID")
        .with_columns(
            tip_rate=pl.col("tip_amount") / pl.col("fare_amount"),
            hour=pl.col("tpep_pickup_datetime").dt.hour(),
            minutes=(
                pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")
            ).dt.total_minutes(),
        )
        .group_by("Borough", "hour")
        .agg(
            pl.len().alias("trips"),
            pl.col("tip_rate").median(),
            pl.col("minutes").quantile(0.9),
            pl.col("total_amount").sum(),
        )
        .sort("Borough", "hour")
    )

    summary = query.collect()
    print(summary)


@timed
def join_does_not_prevent_row_order():
    TRIPS_DATA = Path() / "data" / "taxi.parquet"
    ZONE_DATA = Path() / "data" / "taxi_zones.csv"

    trips = pl.scan_parquet(TRIPS_DATA)
    zones = pl.scan_csv(ZONE_DATA)

    joined = (
        trips.with_row_index("row")
        .join(zones, left_on="PULocationID", right_on="LocationID")
        .select("row", "tpep_pickup_datetime", "Zone")
    )
    joined_df = joined.head(5).collect()
    print(joined_df)

    preserved_order_df = joined.sort("row").head(5).collect()  # twice slower
    print(preserved_order_df)


@timed
def streaming_engine_sql():
    TRIPS_DATA = Path() / "data" / "taxi.parquet"
    ZONE_DATA = Path() / "data" / "taxi_zones.csv"

    # pl.sql resolves table names from local variables, so these must stay bound
    trips = pl.scan_parquet(TRIPS_DATA).with_row_index("row")  # noqa: F841
    zones = pl.scan_csv(ZONE_DATA)  # noqa: F841

    query = """
    SELECT Borough, COUNT(*) AS trips, AVG(tip_amount / fare_amount) AS tip_rate
    FROM trips
    JOIN zones ON trips.PULocationID = zones.LocationID
    WHERE fare_amount > 0 AND trip_distance > 0
    GROUP BY Borough
    ORDER BY Borough
    """
    summary = pl.sql(query).collect()
    print(summary)

    query = """
    SELECT row, Zone
    FROM trips
    JOIN zones ON trips.PULocationID = zones.LocationID
    LIMIT 3
    """
    print(f"order not preserved - {pl.sql(query).collect()}")

    query = """
    SELECT row, Zone
    FROM trips
    JOIN zones ON trips.PULocationID = zones.LocationID
    ORDER BY row
    LIMIT 3
    """
    print(f"preserved order now (slower) - {pl.sql(query).collect()}")


def main():
    sql_fitst_class_citizen()
    map_datatype_eg()
    query_multiple_df()
    join_does_not_prevent_row_order()
    streaming_engine_sql()


if __name__ == "__main__":
    main()
