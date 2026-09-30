-- Turn the rotation table into something a model can consume: add the
-- schedule-side features and assign the chronological split.
--
-- Input : data/interim/rotation.parquet
-- Output: data/interim/features.parquet

COPY (
SELECT
    flight_id,
    cutoff_min,
    cutoff_h,

    -- ---- schedule features: known at booking time ----
    carrier,
    origin,
    dest,
    -- route is not used by the LightGBM models (carrier/origin/dest are fed
    -- as categoricals instead); it exists for the route x hour lookup
    -- baseline in scripts/baseline.py.
    origin || '-' || dest                     AS route,
    distance_mi,
    crs_elapsed_min,
    -- Local clock hour at the origin airport. Congestion follows the LOCAL
    -- day, not UTC -- 07:00 is rush hour anywhere on earth.
    extract('hour' FROM timezone(origin_tz, timezone('UTC', crs_dep_utc)))::INT
                                              AS dep_hour,
    extract('dow'  FROM fl_date)::INT         AS dep_dow,
    -- dep_day is carried through but deliberately NOT trained on; see the
    -- note in scripts/train.py.
    extract('day'  FROM fl_date)::INT         AS dep_day,

    -- ---- rotation features: only the aircraft-aware models use these ----
    has_pred,
    pred_arr_delay,
    pred_staleness_h,
    ground_time_min,
    pred_contiguous,
    sched_turn_min,

    -- ---- target and bookkeeping ----
    is_delayed,
    arr_delay,
    fl_date,
    crs_dep_utc,
    cutoff_utc,

    -- Chronological split over 24 months: 18 train / 2 validation / 4 test.
    -- Training covers a full seasonal cycle, but only ONE summer, while the
    -- test period is entirely June-September. Measured outcome: the models
    -- still under-predict by 0.024 to 0.042, so this reduced the regime
    -- mismatch of the one-month experiment without removing it. Splitting on
    -- time rather than at random is still required: a random split would let
    -- a flight's own day leak across the boundary.
    CASE
        WHEN fl_date <= DATE '2025-03-31' THEN 'train'
        WHEN fl_date <= DATE '2025-05-31' THEN 'valid'
        ELSE                                   'test'
    END                                       AS split
FROM 'data/interim/rotation.parquet'
)
TO 'data/interim/features.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);