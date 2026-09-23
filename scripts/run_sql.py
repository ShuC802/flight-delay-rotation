"""执行一个 .sql 文件。用法: uv run python scripts/run_sql.py sql/01_xxx.sql"""
import sys
import time
from pathlib import Path

import duckdb

sql_path = Path(sys.argv[1])
sql = sql_path.read_text(encoding="utf-8")

t0 = time.perf_counter()
duckdb.sql(sql)
print(f"✓ {sql_path}  ({time.perf_counter() - t0:.1f}s)")