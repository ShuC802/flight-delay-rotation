-- Put every flight on a single UTC timeline, so that legs flown by the same
-- aircraft can be ordered against each other.
--
-- Input : data/interim/flights.parquet + data/interim/airport_tz.parquet
-- Output: data/interim/flights_utc.parquet
--
-- Strategy: convert EXACTLY ONE clock-face time -- scheduled departure -- and
-- derive the other three by adding minute counts to it. Adding minutes to an
-- absolute instant cannot go wrong, so midnight rollover, timezone boundaries
-- and daylight saving are handled once instead of four times.
--
-- CRSArrTime is deliberately NOT used in this computation. That leaves it free
-- to serve as an independent cross-check: crs_arr_utc converted back to
-- destination local time must reproduce it. See
-- test_scheduled_arrival_round_trips_through_utc.

COPY (

WITH with_tz AS (
    SELECT
        f.*,
        o.tz AS origin_tz,
        d.tz AS dest_tz
    FROM 'data/interim/flights.parquet' f
    LEFT JOIN 'data/interim/airport_tz.parquet' o ON f.origin = o.iata
    LEFT JOIN 'data/interim/airport_tz.parquet' d ON f.dest   = d.iata
),

parsed AS (
    SELECT
        *,
        -- BTS stores departure time as an unpadded HHMM integer: 729 means
        -- 07:29. lpad restores the leading zero before splitting.
        -- "2400" needs no special case: to_hours(24) rolls into the next day.
        CAST(substr(lpad(crs_dep_hhmm, 4, '0'), 1, 2) AS BIGINT) AS h,
        CAST(substr(lpad(crs_dep_hhmm, 4, '0'), 3, 2) AS BIGINT) AS m
    FROM with_tz
),

stamped AS (
    SELECT
        *,
        -- Inner timezone(origin_tz, naive): read this wall-clock reading as a
        --   local time at the origin airport, producing a real instant.
        -- Outer timezone('UTC', instant): express that instant as UTC.
        -- origin_tz is an IANA name such as America/Denver, not a fixed
        -- offset, which is what makes daylight saving come out right.
        timezone(
            'UTC',
            timezone(
                origin_tz,
                fl_date::TIMESTAMP + to_hours(h) + to_minutes(m)
            )
        ) AS crs_dep_utc
    FROM parsed
)

SELECT
    * EXCLUDE (h, m),
    -- All three derived from crs_dep_utc by pure minute arithmetic.
    crs_dep_utc + to_minutes(CAST(crs_elapsed_min AS BIGINT))              AS crs_arr_utc,
    crs_dep_utc + to_minutes(CAST(dep_delay       AS BIGINT))              AS act_dep_utc,
    crs_dep_utc + to_minutes(CAST(crs_elapsed_min AS BIGINT))
                + to_minutes(CAST(arr_delay       AS BIGINT))              AS act_arr_utc
FROM stamped

)
TO 'data/interim/flights_utc.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
