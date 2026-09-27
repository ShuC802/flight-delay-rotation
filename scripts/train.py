"""Ablation: how much does the aircraft's recent history add, at each cutoff?

The schedule-only model does not depend on the cutoff at all -- it uses the
same features and the same flights however far out you stand. So it is a
single fixed REFERENCE LINE, and the question is how far above it the
aircraft-aware models sit at each cutoff.

Everything is scored on the SAME test flights. The number that matters is the
DELTA in average precision, not either model's absolute score.
"""
import duckdb
import lightgbm as lgb
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

PQ = "data/interim/features.parquet"
CUTOFFS = [1440, 360, 180, 90, 45]

CATEGORICAL = ["carrier", "origin", "dest"]

# Known at booking time, independent of which aircraft gets assigned.
SCHEDULE_FEATURES = CATEGORICAL + [
    "distance_mi", "crs_elapsed_min", "dep_hour", "dep_dow",
]
# dep_day is deliberately EXCLUDED. With one month of data it separates train
# (days 1-20) from test (days 25-30) almost perfectly, so the model would
# learn a calendar artefact instead of anything about flights.

# Only available once the aircraft is known and has been flying.
ROTATION_FEATURES = [
    "has_pred", "pred_arr_delay", "pred_staleness_h",
    "ground_time_min", "pred_contiguous", "sched_turn_min",
]

BOOLEAN_COLS = ["has_pred", "pred_contiguous"]

PARAMS = dict(
    objective="binary",
    learning_rate=0.05,
    num_leaves=63,
    min_data_in_leaf=200,
    feature_fraction=0.9,
    bagging_fraction=0.8,
    bagging_freq=1,
    verbose=-1,
    seed=0,
)


def load(cutoff: int) -> pd.DataFrame:
    df = duckdb.sql(f"SELECT * FROM '{PQ}' WHERE cutoff_min = {cutoff}").df()
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    # True -> 1.0, False -> 0.0, NULL -> NaN. LightGBM handles NaN natively;
    # do NOT fill it with 0, which would mean "no, definitely not".
    for c in BOOLEAN_COLS:
        df[c] = df[c].astype("float64")
    df["y"] = df["is_delayed"].astype(int)
    return df


def fit_and_score(df: pd.DataFrame, features: list[str]) -> dict:
    tr, va, te = (df[df.split == s] for s in ("train", "valid", "test"))

    model = lgb.train(
        PARAMS,
        lgb.Dataset(tr[features], label=tr["y"]),
        num_boost_round=3000,
        valid_sets=[lgb.Dataset(va[features], label=va["y"])],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    p = model.predict(te[features], num_iteration=model.best_iteration)
    return {
        "ap": average_precision_score(te["y"], p),
        "brier": brier_score_loss(te["y"], p),
        "rounds": model.best_iteration,
    }


# ---- the reference line: schedule only, trained once ----
base_df = load(CUTOFFS[0])
ref = fit_and_score(base_df, SCHEDULE_FEATURES)
floor = base_df.loc[base_df.split == "test", "y"].mean()

print(f"test base rate (AP floor)   : {floor:.4f}")
print(f"schedule-only model      AP : {ref['ap']:.4f}   "
      f"Brier {ref['brier']:.4f}   ({ref['rounds']} rounds)")
print()

# ---- one aircraft-aware model per cutoff ----
rows = []
for cutoff in CUTOFFS:
    df = load(cutoff)
    res = fit_and_score(df, SCHEDULE_FEATURES + ROTATION_FEATURES)
    rows.append({
        "cutoff_min": cutoff,
        "ap": res["ap"],
        "delta_ap": res["ap"] - ref["ap"],
        "brier": res["brier"],
        "rounds": res["rounds"],
    })
    print(f"cutoff {cutoff:>5} min   AP {res['ap']:.4f}   "
          f"delta {res['ap'] - ref['ap']:+.4f}   Brier {res['brier']:.4f}")

out = pd.DataFrame(rows)
out.insert(0, "ap_reference", ref["ap"])
out.insert(0, "ap_floor", floor)
out.to_csv("data/interim/ablation.csv", index=False)
print("\nsaved -> data/interim/ablation.csv")
