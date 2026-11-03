# range join that keeps unmatched rows from both sides

import time

start = time.perf_counter()

import polars as pl

trips = pl.DataFrame({"pickup_hour": [8, 13]})
rush = pl.DataFrame({"period": ["morning", "evening"], "start": [7, 17], "end": [9, 19]})

joined = trips.join_where(
    rush, pl.col("pickup_hour").is_between("start", "end"), how="full"
)
print("trips", trips, sep="\n")
print("rush", rush, sep="\n")
print("joined", joined, sep="\n")

print(f"time: {time.perf_counter() - start:.2f}s")