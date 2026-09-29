"""Rebuild every derived artefact from data/raw, in order.

This exists because a half-finished change once left the code and the parquet
files disagreeing, and nothing complained until a query silently returned
0 rows. Stale outputs are deleted FIRST, so a run that fails halfway cannot
leave behind files that look complete.

    uv run python scripts/build_all.py
"""
import subprocess
import sys
import time
from pathlib import Path

DERIVED = [
    "data/interim/airport_tz.parquet",
    "data/interim/flights.parquet",
    "data/interim/flights_utc.parquet",
    "data/interim/analysis.parquet",
    "data/interim/rotation.parquet",
    "data/interim/features.parquet",
]

STEPS = [
    ("python", "scripts/build_airport_tz.py"),
    ("sql",    "sql/01_raw_to_parquet.sql"),
    ("sql",    "sql/02_timestamps.sql"),
    ("sql",    "sql/03_analysis_table.sql"),
    ("sql",    "sql/04_rotation.sql"),
    ("sql",    "sql/05_features.sql"),
]

removed = 0
for path in DERIVED:
    p = Path(path)
    if p.exists():
        p.unlink()
        removed += 1
print(f"removed {removed} stale derived files\n")

t_all = time.perf_counter()
for kind, target in STEPS:
    print(f"--> {target}")
    t0 = time.perf_counter()
    cmd = ([sys.executable, target] if kind == "python"
           else [sys.executable, "scripts/run_sql.py", target])
    subprocess.run(cmd, check=True)
    print(f"    {time.perf_counter() - t0:6.1f}s\n")

for path in DERIVED:
    mb = Path(path).stat().st_size / 1e6
    print(f"{Path(path).name:28s} {mb:8.1f} MB")
print(f"\nrebuild complete in {time.perf_counter() - t_all:.0f}s")