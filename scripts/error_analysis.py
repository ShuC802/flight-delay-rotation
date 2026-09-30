"""Where does the model fail, and where does aircraft state actually help?

Three questions, each of which could falsify part of the story:

  1. Does the gain concentrate in flights with tight scheduled turnarounds?
     If the mechanism is delay propagating through an aircraft, it should.
  2. Is the calibration bias uniform, or concentrated in particular carriers
     or times of day?
  3. On flights with no eligible predecessor, does the aircraft-aware model
     behave like the schedule-only model? It has no extra information there,
     so it should.

Uses the 3-hour cutoff: the last point at which a traveller can still act.
"""
import duckdb
import pandas as pd
from sklearn.metrics import average_precision_score

CUTOFF = 180
PRED = "data/interim/predictions.parquet"
FEAT = "data/interim/features.parquet"

df = duckdb.sql(f"""
    SELECT
        f.flight_id, f.carrier, f.origin, f.dep_hour,
        f.has_pred, f.sched_turn_min, f.pred_contiguous,
        f.is_delayed::INT AS y,
        s.p AS p_schedule,
        r.p AS p_rotation
    FROM '{FEAT}' f
    JOIN '{PRED}' s ON s.flight_id = f.flight_id AND s.model = 'schedule only'
    JOIN '{PRED}' r ON r.flight_id = f.flight_id
                   AND r.model = '+rotation @ {CUTOFF} min'
    WHERE f.cutoff_min = {CUTOFF} AND f.split = 'test'
""").df()

print(f"test flights at the {CUTOFF}-minute cutoff: {len(df):,}")
print(f"overall  AP schedule {average_precision_score(df.y, df.p_schedule):.4f}"
      f"   AP +rotation {average_precision_score(df.y, df.p_rotation):.4f}\n")


def ap_delta(g: pd.DataFrame) -> pd.Series:
    """AP for both models within one slice. Comparing two models on the SAME
    rows is valid; comparing AP ACROSS slices is not, because the base rate
    differs -- so read the delta column, not the level."""
    out = {"n": len(g), "base_rate": g.y.mean()}
    if g.y.nunique() < 2 or len(g) < 500:
        out.update(ap_sched=float("nan"), ap_rot=float("nan"), delta=float("nan"))
    else:
        a = average_precision_score(g.y, g.p_schedule)
        b = average_precision_score(g.y, g.p_rotation)
        out.update(ap_sched=a, ap_rot=b, delta=b - a)
    return pd.Series(out)


# ---------- Q1: does the gain follow scheduled turnaround? ----------
# pd.cut is right-closed, so the first bucket is (-inf, 0] and the second is
# (0, 45]. Note the boundary differs very slightly from chain_ok in
# sql/04_rotation.sql, which treats a turnaround of exactly 0 as valid:
# 5,651 legs sit on that line, so they are labelled "impossible" here but
# kept in the `clean` population. Too few to move any number below.
df["turn_bucket"] = pd.cut(
    df.sched_turn_min,
    bins=[-1e9, 0, 45, 75, 120, 360, 1e9],
    labels=["≤0 min (impossible)", "≤45 min", "45–75", "75–120",
            "2–6 h", "overnight (>6 h)"],
)
print("=== Q1. Gain by scheduled turnaround ===")
print(df.groupby("turn_bucket", observed=True)
        .apply(ap_delta, include_groups=False)
        .round(4).to_string())

# ---------- Q3: no eligible predecessor -> no extra information ----------
print("\n=== Q3. Gain by whether an eligible predecessor exists ===")
print(df.groupby("has_pred", observed=True)
        .apply(ap_delta, include_groups=False)
        .round(4).to_string())

print("\n=== Q3b. Gain by whether the rotation chain is contiguous ===")
print(df.groupby("pred_contiguous", observed=True, dropna=False)
        .apply(ap_delta, include_groups=False)
        .round(4).to_string())


# ---------- Q2: where is the level wrong? ----------
def bias_table(keys: str | list[str]) -> pd.DataFrame:
    t = df.groupby(keys, observed=True).agg(
        n=("y", "size"),
        observed=("y", "mean"),
        predicted=("p_rotation", "mean"),
    )
    t["bias"] = t.predicted - t.observed
    return t[t.n >= 500].round(4)


print("\n=== Q2a. Calibration bias by carrier (most under-predicted first) ===")
print(bias_table("carrier").sort_values("bias").to_string())

print("\n=== Q2b. Calibration bias by local departure hour ===")
print(bias_table("dep_hour").sort_index().to_string())

print("\n=== Q2c. Worst 10 origin airports by under-prediction ===")
print(bias_table("origin").sort_values("bias").head(10).to_string())