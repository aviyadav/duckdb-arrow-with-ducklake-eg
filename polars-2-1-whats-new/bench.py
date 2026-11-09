import time
import numpy as np
import polars as pl

N = 100_000_000 # increase to 50_000_000 if you have enough RAM
rng = np.random.default_rng(42)

pl.DataFrame({
    "order_id": np.arange(N),
    "customer_id": rng.integers(0, 200_000, N),
    "region": rng.choice(["north", "south", "east", "west"], N),
    "amount": rng.random(N) *1000,
}).write_parquet("data/orders.parquet")

pl.DataFrame({
    "customer_id": np.arange(200_000),
    "segment": rng.choice(["retail", "wholesale", "online"], 200_000),
}).write_parquet("data/customers.parquet")

orders = pl.scan_parquet("data/orders.parquet")
customers = pl.scan_parquet("data/customers.parquet")

queries = {
    "group_by_sum": orders.group_by("region").agg(pl.col("amount").sum()),
    "join_group_by": orders.join(customers, on="customer_id").group_by("segment").agg(pl.col("amount").mean()),
    "sort": orders.sort("amount"),
    "unique_two_keys": orders.select("customer_id", "region").unique(),
    "filter_sort": orders.filter(pl.col("amount") > 500).sort("customer_id", "amount"),
}

def best_of(lf, runs=5):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        lf.collect()
        times.append(time.perf_counter() - start)

    return min(times) * 1000

print(f"Polars {pl.__version__}, {N:,} rows")
for name, lf in queries.items():
    print(f"{name:16s} {best_of(lf):8.1f} ms")
