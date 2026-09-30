"""Robustness check: does the headline result depend on aircraft swaps?

34,770 test flights (1.47% of the test split) have a scheduled turnaround
below zero -- the aircraft is recorded as departing before the previous leg
was due to land. Those are almost certainly aircraft swaps, and 88.7% of them
arrive late against 24.2% across the test split. But a swap is a CONSEQUENCE
of disruption, and BTS records only the tail that actually flew, so a swap
decided AFTER the cutoff would still show up in these features.

This script trains the two feature sets twice at the headline cutoff -- once
on all flights, once with those flights excluded from train, validation and
test -- and prints the two side by side.

scripts/train.py now runs both populations at all five cutoffs and is what
the README reports. This file stays because it is a single-cutoff check that
can be read and re-run on its own, without the full ablation:

    uv run python scripts/robustness_check.py
"""
import duckdb
import lightgbm as lgb
import pandas as pd
from sklearn.metrics import average_precision_score

PQ = "data/interim/features.parquet"
CUTOFF = 180          # the decision-relevant horizon

# Kept in step with scripts/train.py by hand; this is a standalone check.
CATEGORICAL = ["carrier", "origin", "dest"]
SCHEDULE_FEATURES = CATEGORICAL + [
    "distance_mi", "crs_elapsed_min", "dep_hour", "dep_dow",
]
ROTATION_FEATURES = [
    "has_pred", "pred_arr_delay", "pred_staleness_h",
    "ground_time_min", "pred_contiguous", "sched_turn_min",
]
PARAMS = dict(
    objective="binary", learning_rate=0.05, num_leaves=63,
    min_data_in_leaf=200, feature_fraction=0.9, bagging_fraction=0.8,
    bagging_freq=1, verbose=-1, seed=0,
)

raw = duckdb.sql(f"SELECT * FROM '{PQ}' WHERE cutoff_min = {CUTOFF}").df()
print(f"loaded {len(raw):,} rows at the {CUTOFF}-minute cutoff")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    for c in ["has_pred", "pred_contiguous"]:
        df[c] = df[c].astype("float64")
    df["y"] = df["is_delayed"].astype(int)
    return df


def ap_on_test(df: pd.DataFrame, features: list[str]) -> float:
    tr, va, te = (df[df.split == s] for s in ("train", "valid", "test"))
    model = lgb.train(
        PARAMS,
        lgb.Dataset(tr[features], label=tr["y"]),
        num_boost_round=3000,
        valid_sets=[lgb.Dataset(va[features], label=va["y"])],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    p = model.predict(te[features], num_iteration=model.best_iteration)
    return average_precision_score(te["y"], p)


rows = []
for label, df in [
    ("all flights", raw),
    ("excluding impossible rotations",
     raw[raw.sched_turn_min.isna() | (raw.sched_turn_min >= 0)]),
]:
    d = prepare(df)
    te = d[d.split == "test"]
    sched = ap_on_test(d, SCHEDULE_FEATURES)
    rot = ap_on_test(d, SCHEDULE_FEATURES + ROTATION_FEATURES)
    rows.append({
        "population": label,
        "train_rows": int((d.split == "train").sum()),
        "test_rows": len(te),
        "test_base_rate": round(te["y"].mean(), 4),
        "ap_schedule": round(sched, 4),
        "ap_rotation": round(rot, 4),
        "delta_ap": round(rot - sched, 4),
    })

out = pd.DataFrame(rows)
print()
print(out.to_string(index=False))

d1, d2 = out.delta_ap
print(f"\ngain on all flights                 : {d1:+.4f}")
print(f"gain excluding impossible rotations : {d2:+.4f}")
print(f"difference                          : {d2 - d1:+.4f}  "
      f"({(d2 - d1) / d1:+.1%} of the headline)")