"""Pipeline invariants.

These exist because scaling from one month to three years introduces data this
code has never seen: daylight-saving transitions, other years' schema quirks,
airports and carriers that come and go. Every check here was written after
something it guards against actually happened, or could have.

Run:  uv run pytest -q
"""
import duckdb

UTC = "data/interim/flights_utc.parquet"
ANALYSIS = "data/interim/analysis.parquet"
ROTATION = "data/interim/rotation.parquet"
FEATURES = "data/interim/features.parquet"
AIRPORT_TZ = "data/interim/airport_tz.parquet"


def q(sql: str):
    return duckdb.sql(sql).fetchone()


def test_no_predecessor_landed_after_its_cutoff():
    """The whole project rests on this. A predecessor whose actual arrival is
    after the cutoff was still in the air when the prediction was made, so its
    outcome did not exist yet."""
    (n,) = q(f"""
        SELECT count(*) FROM '{ROTATION}'
        WHERE has_pred AND pred_act_arr_utc > cutoff_utc
    """)
    assert n == 0, f"{n} rows use a predecessor that had not landed by the cutoff"


def test_post_hoc_columns_never_reach_the_feature_table():
    """Columns prefixed x_ are delay attributions BTS fills in after landing.
    LateAircraftDelay is null exactly when the flight was on time, so even its
    nullity gives away the label."""
    cols = duckdb.sql(f"DESCRIBE SELECT * FROM '{FEATURES}'").df().column_name
    leaked = [c for c in cols if c.startswith("x_")]
    assert not leaked, f"post-hoc columns reached the feature table: {leaked}"


def test_scheduled_arrival_round_trips_through_utc():
    """crs_arr_utc is derived from crs_dep_utc plus block time and never reads
    CRSArrTime, so converting it back to destination local time must reproduce
    that column. This is the check that would catch a daylight-saving bug."""
    n, bad = q(f"""
        SELECT count(*),
               count(*) FILTER (
                   strftime(timezone(dest_tz, timezone('UTC', crs_arr_utc)), '%H%M')
                       <> lpad(crs_arr_hhmm, 4, '0')
               )
        FROM '{UTC}'
        WHERE crs_arr_utc IS NOT NULL AND crs_arr_hhmm IS NOT NULL
    """)
    assert bad / n < 0.001, (
        f"{bad:,} of {n:,} rows ({bad / n:.3%}) disagree with CRSArrTime; "
        "0.004% is the known BTS data-entry rate"
    )


def test_every_airport_has_a_timezone():
    (n,) = q(f"""
        WITH used AS (
            SELECT DISTINCT origin AS iata FROM '{ANALYSIS}'
            UNION
            SELECT DISTINCT dest AS iata FROM '{ANALYSIS}'
        )
        SELECT count(*) FROM used u
        LEFT JOIN '{AIRPORT_TZ}' t USING (iata)
        WHERE t.iata IS NULL
    """)
    assert n == 0, f"{n} airports in the data have no timezone mapping"


def test_tail_numbers_are_normalised():
    """Allegiant reports tails without the leading N. If another carrier starts
    doing something similar in a year we have not looked at, this fails."""
    (n,) = q(f"""
        SELECT count(*) FROM '{ANALYSIS}'
        WHERE tail_num IS NOT NULL AND NOT regexp_matches(tail_num, '^N[0-9]')
    """)
    assert n == 0, f"{n} rows still carry an unnormalised tail number"


def test_natural_key_is_unique():
    """Unlike count(DISTINCT flight_id) == count(*), which row_number()
    guarantees and which therefore tests nothing, this one can fail."""
    rows, keys = q(f"""
        SELECT count(*),
               count(DISTINCT (carrier, flight_num, fl_date, origin))
        FROM '{ANALYSIS}'
    """)
    assert rows == keys, f"{rows - keys:,} duplicate (carrier, flight, date, origin) keys"


def test_analysis_population_is_completed_flights_only():
    (bad,) = q(f"""
        SELECT count(*) FROM '{ANALYSIS}'
        WHERE cancelled <> 0 OR diverted <> 0 OR arr_del15 IS NULL
    """)
    assert bad == 0, f"{bad} cancelled, diverted or outcome-less flights in scope"

def test_feature_table_has_everything_the_models_need():
    """Companion to the x_ test above. That one checks what must NOT be there,
    which passes vacuously on a table that lost half its columns -- exactly
    what happened once when an edit to 05_features.sql silently dropped the
    target block."""
    cols = set(duckdb.sql(f"DESCRIBE SELECT * FROM '{FEATURES}'").df().column_name)
    required = {
        "flight_id", "cutoff_min", "split", "fl_date",
        "is_delayed", "arr_delay",
        "carrier", "origin", "dest", "distance_mi", "crs_elapsed_min",
        "dep_hour", "dep_dow",
        "has_pred", "pred_arr_delay", "pred_staleness_h",
        "ground_time_min", "pred_contiguous", "sched_turn_min",
    }
    missing = required - cols
    assert not missing, f"feature table is missing: {sorted(missing)}"