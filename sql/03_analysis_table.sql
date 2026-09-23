-- Build the analysis population: which flights this study is about.
--
-- Input : data/interim/flights_utc.parquet
-- Output: data/interim/analysis.parquet
--
-- Decisions (mirrored in README):
--   * Scope is completed, non-diverted flights. Cancellations are EXCLUDED,
--     never silently counted as on-time. Modelling them is future work.
--   * Carrier G4 (Allegiant) reports tail numbers without the leading "N".
--     125 of 125 of its tails are affected and prefixing "N" collides with no
--     existing tail, so we normalise instead of dropping -- dropping would
--     remove one entire airline from the study.
--   * Flights with no usable tail number are KEPT and flagged. They can have
--     no rotation features, but the ablation requires both feature sets to be
--     scored on the SAME test flights.
--   * A handful of rows per month where CRSArrTime disagrees with
--     CRSDepTime + CRSElapsedTime are dropped: BTS data-entry errors.

COPY (

WITH normalised AS (
    SELECT
        * EXCLUDE (tail_num),
        CASE
            WHEN tail_num IS NULL OR tail_num = ''   THEN NULL
            WHEN regexp_matches(tail_num, '^N[0-9]') THEN tail_num
            WHEN regexp_matches(tail_num, '^[0-9]')  THEN 'N' || tail_num
            ELSE NULL                                -- unrecognised format
        END AS tail_num
    FROM 'data/interim/flights_utc.parquet'
),

filtered AS (
    SELECT *
    FROM normalised
    WHERE cancelled = 0
      AND diverted  = 0
      AND arr_del15       IS NOT NULL
      AND crs_elapsed_min IS NOT NULL
      AND strftime(timezone(dest_tz, timezone('UTC', crs_arr_utc)), '%H%M')
            = lpad(crs_arr_hhmm, 4, '0')
)

SELECT
    row_number() OVER (
        ORDER BY crs_dep_utc, carrier, flight_num, origin
    )                            AS flight_id,
    *,
    CAST(arr_del15 AS BOOLEAN)   AS is_delayed,   -- prediction target
    tail_num IS NOT NULL         AS has_tail
FROM filtered

)
TO 'data/interim/analysis.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);