"""从 airportsdata 生成 IATA 机场码 → IANA 时区 的对照表。"""
import airportsdata
import duckdb
import pandas as pd

airports = airportsdata.load("IATA")

tz_table = pd.DataFrame(
    [
        {"iata": code, "tz": info["tz"], "airport_name": info["name"]}
        for code, info in airports.items()
        if info.get("tz")
    ]
)

print(f"写入 {len(tz_table):,} 个机场的时区")

duckdb.sql("""
    COPY (SELECT * FROM tz_table)
    TO 'data/interim/airport_tz.parquet' (FORMAT PARQUET)
""")