"""Every number quoted in the README, regenerated from the current data.

The point is that no figure in the documentation is typed by hand from a
terminal scroll-back. Re-run this after any rebuild and update the README from
its output.

    uv run python scripts/report_numbers.py
"""
import duckdb

RAW = "data/interim/flights.parquet"
UTC = "data/interim/flights_utc.parquet"
ANALYSIS = "data/interim/analysis.parquet"
ROTATION = "data/interim/rotation.parquet"
FEATURES = "data/interim/features.parquet"


def show(title: str, sql: str) -> None:
    print(f"\n=== {title} ===")
    print(duckdb.sql(sql))


show("Scope", f"""
    SELECT count(*)                                    AS analysis_flights,
           count(DISTINCT tail_num)                    AS aircraft,
           count(DISTINCT carrier)                     AS carriers,
           min(fl_date)                                AS first_day,
           max(fl_date)                                AS last_day,
           round(avg(is_delayed::INT), 4)              AS delay_rate,
           round(avg(arr_delay), 1)                    AS mean_delay_min,
           round(quantile_cont(arr_delay, 0.5), 1)     AS median_delay_min
    FROM '{ANALYSIS}'
""")

show("Raw rows before filtering", f"SELECT count(*) AS raw_rows FROM '{RAW}'")

show("Legs per aircraft per day", f"""
    SELECT round(count(*)::DOUBLE
                 / count(DISTINCT tail_num)
                 / count(DISTINCT fl_date), 2) AS legs_per_aircraft_per_day
    FROM '{ANALYSIS}'
""")

show("Timestamp cross-check against the unused CRSArrTime column", f"""
    WITH chk AS (
        SELECT lpad(crs_arr_hhmm, 4, '0') = strftime(
                   timezone(dest_tz, timezone('UTC', crs_arr_utc)), '%H%M'
               ) AS ok
        FROM '{UTC}'
        WHERE crs_arr_utc IS NOT NULL AND crs_arr_hhmm IS NOT NULL
    )
    SELECT count(*) AS checked,
           count(*) FILTER (ok)     AS match,
           count(*) FILTER (NOT ok) AS mismatch,
           round(100.0 * count(*) FILTER (NOT ok) / count(*), 4) AS pct_mismatch
    FROM chk
""")

show("Rotation health (one row per flight, cutoff-independent)", f"""
    SELECT count(*)                                            AS legs,
           count(*) FILTER (sched_turn_min < 0)                AS impossible,
           round(100.0 * count(*) FILTER (sched_turn_min < 0)
                       / count(*), 2)                          AS pct_impossible,
           round(avg(is_delayed::INT) FILTER (sched_turn_min < 0), 3)
                                                               AS impossible_delay_rate,
           round(avg(is_delayed::INT), 3)                      AS overall_delay_rate
    FROM '{ROTATION}' WHERE cutoff_min = 180
""")

show("Scheduled turnaround distribution (minutes)", f"""
    SELECT round(quantile_cont(sched_turn_min, 0.10)) AS p10,
           round(quantile_cont(sched_turn_min, 0.50)) AS median,
           round(quantile_cont(sched_turn_min, 0.90)) AS p90
    FROM '{ROTATION}'
    WHERE cutoff_min = 180 AND sched_turn_min IS NOT NULL
""")

# Two different quantities, previously reported under one name:
#   pred_staleness_h  how old the information already was AT THE CUTOFF
#   ground_time_min   how long the aircraft sits on the ground in total,
#                     from its actual arrival to this flight's scheduled
#                     departure. Equals staleness + cutoff_min by definition.
show("Predecessor availability and information age, by cutoff", f"""
    SELECT cutoff_min,
           round(100.0 * avg(has_pred::INT), 1)          AS pct_with_pred,
           round(median(pred_staleness_h), 2)            AS median_age_at_cutoff_h,
           round(median(ground_time_min) / 60.0, 2)      AS median_ground_time_h
    FROM '{ROTATION}' GROUP BY cutoff_min ORDER BY cutoff_min DESC
""")

show("How often a naive LAG() would have used the future", f"""
    WITH naive AS (
        SELECT flight_id,
               LAG(act_arr_utc) OVER (
                   PARTITION BY tail_num ORDER BY crs_dep_utc
               ) AS lag_act_arr_utc
        FROM '{ANALYSIS}' WHERE tail_num IS NOT NULL
    )
    SELECT r.cutoff_min,
           round(100.0 * count(*) FILTER (n.lag_act_arr_utc > r.cutoff_utc)
                       / nullif(count(*) FILTER (n.lag_act_arr_utc IS NOT NULL), 0), 1)
               AS pct_would_leak
    FROM '{ROTATION}' r JOIN naive n USING (flight_id)
    GROUP BY r.cutoff_min ORDER BY r.cutoff_min DESC
""")

show("Tail number normalisation", f"""
    SELECT count(DISTINCT tail_num) FILTER (carrier = 'G4') AS g4_tails,
           count(*) FILTER (carrier = 'G4')                 AS g4_flights,
           count(*) FILTER (NOT regexp_matches(tail_num, '^N[0-9]')) AS still_malformed
    FROM '{ANALYSIS}'
""")

show("Flights with no tail number are cancellations", f"""
    SELECT cancelled, diverted, count(*) AS n
    FROM '{UTC}' WHERE tail_num IS NULL
    GROUP BY cancelled, diverted ORDER BY n DESC
""")

show("Chronological split", f"""
    SELECT split,
           count(*)                        AS flights,
           min(fl_date)                    AS first_day,
           max(fl_date)                    AS last_day,
           round(avg(is_delayed::INT), 4)  AS delay_rate
    FROM '{FEATURES}'
    WHERE cutoff_min = 45
    GROUP BY split
    ORDER BY first_day
""")



