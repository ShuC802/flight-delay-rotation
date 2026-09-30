"""Build the IATA airport code -> IANA timezone lookup.

IANA names such as America/Denver are used rather than fixed UTC offsets,
because only the named zones know when daylight saving starts and stops, and
which places (America/Phoenix, Pacific/Honolulu) never observe it at all.
Everything downstream depends on this being right.

Output: data/interim/airport_tz.parquet
"""
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

print(f"writing timezones for {len(tz_table):,} airports")

# The table covers every airport in the world, not only the ones BTS reports;
# test_every_airport_has_a_timezone checks that the ones we actually use
# are all present.
duckdb.sql("""
    COPY (SELECT * FROM tz_table)
    TO 'data/interim/airport_tz.parquet' (FORMAT PARQUET)
""")
