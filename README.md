# How much is it worth knowing where your aircraft is?

Measuring how much an aircraft's recent operating history improves flight-delay
prediction beyond schedule information, and how that value changes as departure
approaches.

This project uses ~600,000 US domestic flights from June 2025 and evaluates
predictions at five points before departure.

![Gain in average precision by prediction cutoff](reports/ablation.png)

## Key result

A flight's timetable already contains most of the predictive signal. Aircraft
history adds to it, and the amount it adds grows sharply close to departure.

| Model | Average precision | Gain vs. schedule-only |
| --- | ---: | ---: |
| No-skill floor (base rate) | 0.333 | — |
| Route × departure-hour lookup | 0.541 | — |
| Schedule-only model | 0.572 | — |
| + aircraft state, 24 h out | 0.623 | +0.051 |
| + aircraft state, 6 h out | 0.636 | +0.063 |
| **+ aircraft state, 3 h out** | **0.667** | **+0.095** |
| + aircraft state, 1.5 h out | 0.694 | +0.122 |
| + aircraft state, 45 min out | 0.763 | +0.191 |

At 3 hours before departure — while a traveller can still act on the
information — adding aircraft state improves average precision by 0.095, about
40% of what the timetable alone is worth.

In concrete terms: 45 minutes before departure the model identifies a tenth of
flights of which **91% do arrive late**. Three hours out, that tenth is 80%
late. Using the timetable alone, the worst tenth is 66%.

Much of the additional signal appears in the final 90 minutes, when the inbound
aircraft's actual operating state becomes observable.

## Preventing leakage at the prediction cutoff

BTS provides a `LateAircraftDelay` column — the delay the Department of
Transportation attributes to the previous flight of the same aircraft. It is
populated only after the flight has landed, and only for flights that were
late, so even its nullity gives away the outcome. Aircraft-history features
therefore have to be reconstructed using only information that would have been
available at each prediction cutoff.

```sql
-- Wrong: the previous scheduled leg may still be in the air
LAG(arr_delay) OVER (
    PARTITION BY tail_num
    ORDER BY crs_dep_utc
)
```

```sql
-- Correct: the most recent leg that had already landed
ASOF LEFT JOIN flights p
       ON  t.tail_num   =  p.tail_num
      AND  t.cutoff_utc >= p.act_arr_utc
```

Measured on this data, the naive version would use post-cutoff information on
**75.3% of rows at a 3-hour horizon** and **98.5% at 24 hours**.

This distinction matters because a chronological train/test split alone does
not prevent leakage *inside* an individual row. The split is still necessary —
it solves a different problem.

Three independent measurements — the leakage rate of the naive join, the gain
from aircraft features, and the staleness of the usable information — all pivot
between the 90- and 45-minute cutoffs, which is where the median 65-minute
scheduled turnaround sits.

| Cutoff | Naive join would leak | Gain in AP | Median age of usable information |
| ---: | ---: | ---: | ---: |
| 90 min | 65.8% | +0.122 | 3.4 h |
| 45 min | 25.7% | +0.191 | 1.3 h |

## Method

```text
BTS CSV
  → selected columns + parquet
  → UTC timestamps
  → completed, non-diverted flights
  → aircraft rotation reconstruction (ASOF join, per cutoff)
  → cutoff-specific feature tables
  → chronological train / validation / test split
  → LightGBM ablation
```

Two feature sets are compared on the same test flights:

- **Schedule-only:** carrier, origin, destination, distance, scheduled block
  time, local departure hour, day of week
- **Schedule + aircraft state:** delay of the last leg that had landed by the
  cutoff, how stale that information is, observed ground time remaining,
  whether the rotation chain is contiguous, scheduled turnaround

The model configuration, seed and test population are identical for both, so
the difference measures the predictive value added by aircraft history.

All local airport times are converted to UTC before aircraft legs are ordered;
without that, legs crossing a timezone sort incorrectly. Only the *scheduled
departure* is converted, and the other three timestamps are derived from it by
adding plain minute counts, so midnight rollovers and daylight saving never
require reasoning about a clock face. The untouched `CRSArrTime` column is then
used as a cross-check: **611,549 of 611,573 rows agree to the minute.**

### Evaluation

- Average precision, reported against the base rate as a no-skill floor
- Brier score (0.190 for the schedule-only model, 0.146 with aircraft state at
  45 minutes)
- Reliability diagram
- A historical route × departure-hour delay rate as the baseline any model must
  beat

Chronological split:

```text
Train:      June 1–20
Validation: June 21–24
Test:       June 25–30
```

## Calibration

![Reliability diagram](reports/calibration.png)

Average precision only judges the ordering of the predictions. This figure
judges the numbers themselves. All three models sit above the diagonal: they
predict 0.28 on average where the observed rate is 0.33.

The training period ran at a 27% delay rate; the test period ran at 33%. The
models learned a calmer regime than the one they were scored in. Adding
aircraft state sharpens the ranking and widens the range of probabilities the
model is willing to use, but it does not move the level.

Recalibrating on the validation split would not fix this, because the
validation split belongs to the same calm period as the training data. A
training set spanning more regimes would.

## Data

Source: US Department of Transportation, Bureau of Transportation Statistics,
[*Reporting Carrier On-Time Performance (1987–present)*](https://www.transtats.bts.gov/Tables.asp?QO_VQ=EFD).
Airlines above a size threshold are required by regulation to report every
domestic flight, so this is a census rather than a sample.

For June 2025:

```text
611,575 raw rows (110 columns)
599,456 flights after scope filters
  5,648 aircraft
  28.3% overall delay rate (ArrDel15)
```

Tail numbers make it possible to reconstruct aircraft rotations across flights;
most public flight datasets identify the flight but not the aircraft. BTS
covers US domestic flights only, so an aircraft that flies abroad disappears
from the data and reappears later.

### Data quality findings

Each of these changed what the code does.

| Finding | Measured | Handling |
| --- | --- | --- |
| Aircraft fly several legs per day | 3.6 / day | The premise of the project. At one leg per day there is no propagation to measure. |
| Schedules physically impossible for a single aircraft | 9,814 legs (1.64%) | Previous leg's scheduled *arrival* falls after this leg's scheduled *departure*, so the tail linkage cannot be trusted. Those rows are marked as having no eligible predecessor. |
| Previous destination ≠ this origin | 14,045 legs (2.34%) | Mostly international legs invisible to BTS. Flagged, not dropped. |
| Allegiant (G4) reports tail numbers without the leading `N` | 125 of 125 of its tails | A naive "drop malformed tail numbers" filter removes one entire airline. Normalised instead, after confirming zero collisions. |
| Flights with no tail number | 921, all cancellations | No aircraft was ever assigned; the cancellation filter removes them anyway. |
| Arrival delay is heavily right-skewed | median −3 min, mean +15.5 min | Half of all flights arrive early, which is why the target is binary rather than a regression on minutes. |

## Run

```bash
uv sync

# Put one or more BTS monthly CSVs in data/raw/

uv run python scripts/build_all.py
uv run python scripts/baseline.py
uv run python scripts/train.py
uv run python scripts/plot_ablation.py
uv run python scripts/plot_calibration.py
```

`build_all.py` deletes every derived artefact before rebuilding, so a run that
fails halfway cannot leave behind files that look complete.

## Limitations

- The current experiment uses only one month of data, so the results should be
  treated as directional rather than general estimates.
- Test-period delay rates were higher than training-period rates, causing the
  models to under-predict absolute probabilities by about five points.
- BTS covers US domestic flights only, so international legs create gaps in
  aircraft rotation history.
- The 45-minute cutoff is mainly an upper bound on the value of aircraft state
  rather than a practically useful decision point — by then you are at the gate.
- Aircraft assignment is assumed to be known at the cutoff. That is reasonable
  a few hours out and less certain a day ahead, so the 24-hour figure should be
  read as an upper bound.
- This measures predictive value, not causation. A late inbound aircraft and a
  late departure may share a cause, such as the same weather system.
- This is a historical simulation, not a live prediction system. BTS publishes
  monthly archives.

## Repository structure

```text
sql/
  01_raw_to_parquet.sql     110 columns -> 21, CSV -> parquet
  02_timestamps.sql         local wall-clock -> UTC
  03_analysis_table.sql     scope filters, tail normalisation, target
  04_rotation.sql           ASOF join: what was knowable at each cutoff
  05_features.sql           schedule features + chronological split

scripts/
  build_all.py              rebuild every derived artefact, in order
  run_sql.py                execute one .sql file
  build_airport_tz.py       IATA code -> IANA timezone
  baseline.py
  train.py
  plot_ablation.py
  plot_calibration.py

reports/
  ablation.png
  calibration.png

data/                       gitignored; regenerate from the source above
```

## License

Flight data: US Department of Transportation, Bureau of Transportation
Statistics. US government work, public domain.

Code: MIT.
