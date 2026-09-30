"""Execute one .sql file against DuckDB.

The SQL files write their own outputs with COPY ... TO, so nothing is
returned here; this is just a thin runner with timing.

    uv run python scripts/run_sql.py sql/01_raw_to_parquet.sql
"""
import sys
import time
from pathlib import Path

import duckdb

sql_path = Path(sys.argv[1])
sql = sql_path.read_text(encoding="utf-8")

t0 = time.perf_counter()
duckdb.sql(sql)
print(f"OK {sql_path}  ({time.perf_counter() - t0:.1f}s)")
