#!/usr/bin/env python3
"""Download and unzip Divvy Bike Trip CSV files into data/.

Divvy publishes monthly trip data as zips at:
    https://divvy-tripdata.s3.amazonaws.com/<YYYYMM>-divvy-tripdata.zip
"""
import argparse
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://divvy-tripdata.s3.amazonaws.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def download_month(month: str, out_dir: Path) -> Path:
    url = f"{BASE_URL}/{month}-divvy-tripdata.zip"
    zip_path = out_dir / f"{month}-divvy-tripdata.zip"
    if zip_path.exists():
        print(f"[skip] {zip_path.name} already downloaded")
        return zip_path
    print(f"downloading {url} ...")
    with urllib.request.urlopen(url) as resp, open(zip_path, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    print(f"  saved {zip_path.name} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("months", nargs="*", default=["202401", "202402"],
                    help="YYYYMM Divvy months to download (default: 202401 202402)")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = ap.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    for month in args.months:
        zip_path = download_month(month, args.data_dir)
        csv_name = f"{month}-divvy-tripdata.csv"
        csv_path = args.data_dir / csv_name
        if csv_path.exists():
            print(f"[skip] {csv_name} already extracted")
            continue
        with zipfile.ZipFile(zip_path) as z:
            z.extract(csv_name, args.data_dir)
        print(f"  extracted {csv_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
