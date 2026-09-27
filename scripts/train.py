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


def fit_and_score(df: pd.DataFrame, features: list[str], label: str):
    tr, va, te = (df[df.split == s] for s in ("train", "valid", "test"))

    model = lgb.train(
        PARAMS,
        lgb.Dataset(tr[features], label=tr["y"]),
        num_boost_round=3000,
        valid_sets=[lgb.Dataset(va[features], label=va["y"])],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    p = model.predict(te[features], num_iteration=model.best_iteration)

    metrics = {
        "ap": average_precision_score(te["y"], p),
        "brier": brier_score_loss(te["y"], p),
        "rounds": model.best_iteration,
    }
    # Keep the test-set predictions: calibration cannot be checked from a
    # summary metric, only from the probabilities themselves.
    preds = pd.DataFrame({
        "model": label,
        "flight_id": te["flight_id"].to_numpy(),
        "y": te["y"].to_numpy(),
        "p": p,
    })
    return metrics, preds


all_preds = []

# ---- the reference line: schedule only, trained once ----
base_df = load(CUTOFFS[0])
ref_metrics, ref_preds = fit_and_score(base_df, SCHEDULE_FEATURES, "schedule only")
all_preds.append(ref_preds)
floor = base_df.loc[base_df.split == "test", "y"].mean()

print(f"test base rate (AP floor)   : {floor:.4f}")
print(f"schedule-only model      AP : {ref_metrics['ap']:.4f}   "
      f"Brier {ref_metrics['brier']:.4f}   ({ref_metrics['rounds']} rounds)")
print()

# ---- one aircraft-aware model per cutoff ----
rows = []
for cutoff in CUTOFFS:
    df = load(cutoff)
    res, preds = fit_and_score(df, SCHEDULE_FEATURES + ROTATION_FEATURES,
                               f"+rotation @ {cutoff} min")
    all_preds.append(preds)
    rows.append({
        "cutoff_min": cutoff,
        "ap": res["ap"],
        "delta_ap": res["ap"] - ref_metrics["ap"],
        "brier": res["brier"],
        "rounds": res["rounds"],
    })
    print(f"cutoff {cutoff:>5} min   AP {res['ap']:.4f}   "
          f"delta {res['ap'] - ref_metrics['ap']:+.4f}   Brier {res['brier']:.4f}")

out = pd.DataFrame(rows)
out.insert(0, "ap_reference", ref_metrics["ap"])
out.insert(0, "ap_floor", floor)
out.to_csv("data/interim/ablation.csv", index=False)
print("\nsaved -> data/interim/ablation.csv")

pd.concat(all_preds, ignore_index=True).to_parquet(
    "data/interim/predictions.parquet", index=False
)
print("saved -> data/interim/predictions.parquet")