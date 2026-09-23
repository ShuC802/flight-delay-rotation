-- 把 BTS 原始 CSV 转成精简的 Parquet
-- 输入: data/raw/*.csv    输出: data/interim/flights.parquet

COPY (
    SELECT
        -- ---- 身份 ----
        FlightDate                       AS fl_date,
        Reporting_Airline                AS carrier,
        Flight_Number_Reporting_Airline  AS flight_num,
        Tail_Number                      AS tail_num,

        -- ---- 航线 ----
        Origin                           AS origin,
        Dest                             AS dest,
        Distance                         AS distance_mi,

        -- ---- 时刻表（订票时就可知）----
        CRSDepTime                       AS crs_dep_hhmm,
        CRSArrTime                       AS crs_arr_hhmm,
        CRSElapsedTime                   AS crs_elapsed_min,

        -- ---- 实际发生（事后才知）----
        DepTime                          AS dep_hhmm,
        DepDelay                         AS dep_delay,
        ArrTime                          AS arr_hhmm,
        ArrDelay                         AS arr_delay,
        ArrDel15                         AS arr_del15,

        -- ---- 状态 ----
        Cancelled                        AS cancelled,
        CancellationCode                 AS cancel_code,
        Diverted                         AS diverted,

        -- ---- x_ 前缀 = 只用于事后验证，永远不许进特征 ----
        CarrierDelay                     AS x_carrier_delay,
        WeatherDelay                     AS x_weather_delay,
        NASDelay                         AS x_nas_delay,
        LateAircraftDelay                AS x_late_aircraft_delay

    FROM read_csv_auto('data/raw/*.csv', union_by_name = true)
)
TO 'data/interim/flights.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);