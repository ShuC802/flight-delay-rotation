-- Reconstruct, for every flight and every prediction cutoff, what was
-- knowable about the aircraft at that moment.
--
-- Input : data/interim/analysis.parquet
-- Output: data/interim/rotation.parquet   (one row per flight x cutoff)
--
-- This is the file the whole project turns on. See the ASOF join below.

COPY (

-- Prediction cutoffs, in MINUTES before scheduled departure.
-- 1440 = 24h (floor), 45 = boarding time (ceiling: median turnaround is 65 min,
-- so this is the first cutoff at which the immediately preceding leg has
-- usually landed).
WITH cutoffs(cutoff_min, cutoff_h) AS (
    VALUES 
        (1440, 24.0), 
        (360,  6.0), 
        (180,  3.0), 
        (90,   1.5), 
        (45,   0.75)
),

-- Chain health, from the SCHEDULE only, one value per flight.
-- A negative scheduled turnaround is physically impossible for a single
-- aircraft -- it departs before the previous leg was due to land -- so the
-- tail linkage around that flight cannot be trusted. In practice these are
-- aircraft swaps. 169,069 of 13,840,915 legs (1.22%) across Oct 2023 -
-- Sep 2025; 87.5% of them arrive late, against 20.6% overall.
--
-- LAG is used here ONLY to diagnose the chain, never to build a feature:
-- "the previous row" is not the same thing as "what had already happened",
-- which is what the ASOF join below is for.
chain AS (
    SELECT
        flight_id,
        date_diff('minute', LAG(crs_arr_utc) OVER w, crs_dep_utc) AS sched_turn_min
    FROM 'data/interim/analysis.parquet'
    WHERE tail_num IS NOT NULL
    WINDOW w AS (PARTITION BY tail_num ORDER BY crs_dep_utc)
),

-- Fan each flight out across the cutoffs.
targets AS (
    SELECT
        f.*,
        c.cutoff_min,
        c.cutoff_h,
        f.crs_dep_utc - to_minutes(c.cutoff_min::BIGINT) AS cutoff_utc,
        ch.sched_turn_min,
        -- No predecessor at all is fine; a negative turnaround is not.
        coalesce(ch.sched_turn_min >= 0, TRUE)       AS chain_ok
    FROM 'data/interim/analysis.parquet' f
    CROSS JOIN cutoffs c
    LEFT JOIN chain ch USING (flight_id)
),

-- The core join, and the reason this project exists.
--
-- LAG gives the previous row in the sequence, which at the cutoff may still
-- be in the air; its arrival delay does not exist yet. ASOF gives the most
-- recent leg whose ACTUAL arrival is at or before the cutoff, which is what
-- a forecaster would really have had. A naive LAG would use post-cutoff
-- information on 73.4% of rows at the 3-hour horizon and 98.1% at 24 hours,
-- and a chronological train/test split would not catch any of it, because
-- the leak is inside the row rather than across rows.
--
-- LEFT is deliberate: "no eligible predecessor" is a real and common state
-- that the model should be able to learn from, not a row to drop.
matched AS (
    SELECT
        t.*,
        p.flight_id   AS match_flight_id,
        p.dest        AS match_dest,
        p.arr_delay   AS match_arr_delay,
        p.act_arr_utc AS match_act_arr_utc
    FROM targets t
    ASOF LEFT JOIN 'data/interim/analysis.parquet' p
           ON  t.tail_num   =  p.tail_num
           AND t.cutoff_utc >= p.act_arr_utc
),

flagged AS (
    SELECT *,
           (match_flight_id IS NOT NULL AND chain_ok) AS has_pred
    FROM matched
)

SELECT
    -- keys
    flight_id, cutoff_min, cutoff_h,

    -- schedule facts (known at booking time)
    carrier, flight_num, origin, dest, fl_date,
    crs_dep_utc, crs_elapsed_min, distance_mi, origin_tz,

    -- audit trail: keep these so the leakage test below can actually fail
    cutoff_utc,
    match_act_arr_utc AS pred_act_arr_utc,

    -- rotation features. NULL when has_pred is false, so "unknown" stays
    -- explicit instead of being silently imputed as zero.
    has_pred,
    CASE WHEN has_pred THEN match_arr_delay END                              AS pred_arr_delay,
    CASE WHEN has_pred THEN date_diff('minute', match_act_arr_utc, cutoff_utc) / 60.0 END
                                                                             AS pred_staleness_h,
    CASE WHEN has_pred THEN date_diff('minute', match_act_arr_utc, crs_dep_utc) END
                                                                             AS ground_time_min,
    CASE WHEN has_pred THEN (match_dest = origin) END                        AS pred_contiguous,
    sched_turn_min,
    chain_ok,

    -- target
    is_delayed, arr_delay
FROM flagged

)
TO 'data/interim/rotation.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);