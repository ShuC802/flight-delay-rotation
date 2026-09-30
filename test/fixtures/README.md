# Test fixture

`bts_sample.csv` is a four-day slice (1-4 November 2024) of the US DOT
Bureau of Transportation Statistics *On-Time Reporting Carrier On-Time
Performance* file for November 2024, reduced to the 22 columns that
`sql/01_raw_to_parquet.sql` reads. 76,194 flights, 7 MB.

It exists so that continuous integration can rebuild the entire pipeline from
raw input on every push. The real input is roughly 7 GB of CSV and is
gitignored; without a committed sample, CI could only lint the code, not run
the checks that matter.

Why these four days:

- **3 November 2024 is the daylight-saving transition.** Every US timezone
  except Arizona and Hawaii repeats the 01:00 hour that morning. A pipeline
  that used fixed UTC offsets instead of IANA timezones would pass on any
  ordinary day and fail here, which is exactly what
  `test_scheduled_arrival_round_trips_through_utc` is for. On this sample
  the test finds 10 mismatches in 76,194 flights (0.013%), all of them
  BTS data-entry noise; a broken conversion would produce thousands.
- **Four consecutive days** give each aircraft a real rotation, so the ASOF
  join in `sql/04_rotation.sql` has predecessors to find at every cutoff.
- **All carriers and all airports** are kept, so the tail-normalization and
  timezone-coverage checks see the same variety as the full dataset.

Regenerate with:

```sql
COPY (
    SELECT FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline,
           Tail_Number, Origin, Dest, Distance,
           CRSDepTime, CRSArrTime, CRSElapsedTime,
           DepTime, DepDelay, ArrTime, ArrDelay, ArrDel15,
           Cancelled, CancellationCode, Diverted,
           CarrierDelay, WeatherDelay, NASDelay, LateAircraftDelay
    FROM read_csv_auto('data/raw/2024_11.csv')
    WHERE FlightDate BETWEEN DATE '2024-11-01' AND DATE '2024-11-04'
    ORDER BY FlightDate, CRSDepTime
) TO 'test/fixtures/bts_sample.csv' (FORMAT CSV, HEADER);
```

Source data is in the public domain (US federal government work).
