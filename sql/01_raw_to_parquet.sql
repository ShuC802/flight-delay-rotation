-- Reduce the raw BTS export to the columns this study uses, and store it
-- columnar.
--
-- Input : data/raw/*.csv                Output: data/interim/flights.parquet
--
-- BTS ships 110 columns per month; 22 of them are enough here. The CSV is
-- also the slowest thing in the pipeline, so this is the one place it is read.
-- union_by_name tolerates the column-order changes BTS has made between years.

COPY (
    SELECT
        -- ---- identity ----
        FlightDate                       AS fl_date,
        Reporting_Airline                AS carrier,
        Flight_Number_Reporting_Airline  AS flight_num,
        Tail_Number                      AS tail_num,

        -- ---- route ----
        Origin                           AS origin,
        Dest                             AS dest,
        Distance                         AS distance_mi,

        -- ---- the timetable: known at booking time ----
        CRSDepTime                       AS crs_dep_hhmm,
        CRSArrTime                       AS crs_arr_hhmm,
        CRSElapsedTime                   AS crs_elapsed_min,

        -- ---- what actually happened: known only afterwards ----
        DepTime                          AS dep_hhmm,
        DepDelay                         AS dep_delay,
        ArrTime                          AS arr_hhmm,
        ArrDelay                         AS arr_delay,
        ArrDel15                         AS arr_del15,

        -- ---- status ----
        Cancelled                        AS cancelled,
        CancellationCode                 AS cancel_code,
        Diverted                         AS diverted,

        -- ---- x_ prefix = post-hoc only, never allowed to become a feature.
        -- BTS fills these in after arrival, and only for delayed flights, so
        -- even their nullity gives away the label. The prefix makes that
        -- rule mechanical: test/test_pipeline.py fails if an x_ column ever
        -- reaches the feature table.
        CarrierDelay                     AS x_carrier_delay,
        WeatherDelay                     AS x_weather_delay,
        NASDelay                         AS x_nas_delay,
        LateAircraftDelay                AS x_late_aircraft_delay

    FROM read_csv_auto('data/raw/*.csv', union_by_name = true)
)
TO 'data/interim/flights.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
