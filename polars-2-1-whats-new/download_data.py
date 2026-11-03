#!/usr/bin/env python3
"""Download Jan to Oct 2024 NYC yellow taxi trips and the zone lookup into data/."""
import shutil
import urllib.request
from pathlib import Path

BASE = "https://d37ci6vzurychx.cloudfront.net"
DATA = Path("data")
DATA.mkdir(exist_ok=True)

for month in range(1, 11):
    name = f"yellow_tripdata_2024-{month:02d}.parquet"
    dest = DATA / name
    print(f"downloading {name} ...", flush=True)
    urllib.request.urlretrieve(f"{BASE}/trip-data/{name}", dest)

shutil.copy(DATA / "yellow_tripdata_2024-01.parquet", DATA / "taxi.parquet")
print("downloading taxi_zones.csv ...", flush=True)
urllib.request.urlretrieve(f"{BASE}/misc/taxi_zone_lookup.csv", DATA / "taxi_zones.csv")
print("done")
