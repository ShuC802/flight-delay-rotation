"""Download BTS monthly on-time performance files into data/raw/.

BTS publishes a prezipped file per month at a predictable URL. Each zip is
30-60 MB and expands to roughly 280 MB of CSV.

Months already on disk are skipped, so this is safe to re-run and safe to
interrupt halfway.

    uv run python scripts/download.py 2023-10 2025-09
"""
import io
import sys
import time
import zipfile
from pathlib import Path

import requests

URL = ("https://transtats.bts.gov/PREZIP/"
       "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip")
RAW = Path("data/raw")
HEADERS = {"User-Agent": "flight-delay-rotation (educational use)"}


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch(y: int, m: int) -> None:
    # Zero-padded so that alphabetical order is chronological order.
    dest = RAW / f"{y}_{m:02d}.csv"
    if dest.exists():
        print(f"{dest.name}  already present, skipping")
        return

    r = requests.get(URL.format(y=y, m=m), headers=HEADERS, timeout=900)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        dest.write_bytes(z.read(name))

    print(f"{dest.name}  {dest.stat().st_size / 1e6:,.0f} MB")


RAW.mkdir(parents=True, exist_ok=True)
for year, month in months(sys.argv[1], sys.argv[2]):
    fetch(year, month)
    time.sleep(1)          # be polite to a public server
print("done")