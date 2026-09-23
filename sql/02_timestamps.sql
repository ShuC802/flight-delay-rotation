-- 把本地时间转成 UTC 时间戳
-- 输入: data/interim/flights.parquet + data/interim/airport_tz.parquet
-- 输出: data/interim/flights_utc.parquet
--
-- 策略: 只对「计划起飞」做一次时区转换，其余三个时刻用分钟数加法推出来。
--       这样跨午夜、跨时区、夏令时全部自动正确。

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
        -- "0729" 拆成 7 和 29；"2400" 拆成 24 和 0
        CAST(substr(lpad(crs_dep_hhmm, 4, '0'), 1, 2) AS BIGINT) AS h,
        CAST(substr(lpad(crs_dep_hhmm, 4, '0'), 3, 2) AS BIGINT) AS m
    FROM with_tz
),

stamped AS (
    SELECT
        *,
        -- 内层 timezone(origin_tz, naive) : 把这个「墙上的钟面时间」按出发地时区解释成一个真实瞬间
        -- 外层 timezone('UTC', instant)   : 把那个瞬间换算成 UTC 的钟面时间
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
    crs_dep_utc + to_minutes(CAST(crs_elapsed_min AS BIGINT))              AS crs_arr_utc,
    crs_dep_utc + to_minutes(CAST(dep_delay       AS BIGINT))              AS act_dep_utc,
    crs_dep_utc + to_minutes(CAST(crs_elapsed_min AS BIGINT))
                + to_minutes(CAST(arr_delay       AS BIGINT))              AS act_arr_utc
FROM stamped

)
TO 'data/interim/flights_utc.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);