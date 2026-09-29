"""Ablation: how much does the aircraft's recent history add, at each cutoff?

Runs the whole experiment twice, over two populations:

  all    every flight in the analysis table.
  clean  flights whose recorded rotation is physically possible. 1.8% of
         flights have a scheduled turnaround below zero -- the aircraft
         departs before it was scheduled to arrive -- which in practice means
         an aircraft swap. 90% of those flights arrive late, but a swap is a
         CONSEQUENCE of disruption, and BTS records only the tail that flew,
         not when the swap was decided. So we cannot tell whether that
         information would have been available at the cutoff.

Neither population is "the right answer". Together they bracket it: `all` is
an upper bound, `clean` a lower bound.

The schedule-only model does not depend on the cutoff, so it is trained once
per population and used as a single reference line.

Writes:
  data/interim/ablation.csv        the `all` population
  data/interim/ablation_clean.csv  the `clean` population
  data/interim/predictions.csv     test predictions from `all`, for calibration
"""
import duckdb
import lightgbm as lgb
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss

PQ = "data/interim/features.parquet"
CUTOFFS = [1440, 360, 180, 90, 45]
HEADLINE = 180                      # the decision-relevant horizon

CATEGORICAL = ["carrier", "origin", "dest"]

SCHEDULE_FEATURES = CATEGORICAL + [
    "distance_mi", "crs_elapsed_min", "dep_hour", "dep_dow",
]
# dep_day is deliberately EXCLUDED. With one month of data it separates train
# (days 1-20) from test (days 25-30) almost perfectly, so the model would
# learn a calendar artefact instead of anything about flights.

ROTATION_FEATURES = [
    "has_pred", "pred_arr_delay", "pred_staleness_h",
    "ground_time_min", "pred_contiguous", "sched_turn_min",
]

PARAMS = dict(
    objective="binary", learning_rate=0.05, num_leaves=63,
    min_data_in_leaf=200, feature_fraction=0.9, bagging_fraction=0.8,
    bagging_freq=1, verbose=-1, seed=0,
)


# Only what the models and the split need. SELECT * would also pull
# timestamps and text columns, which at 24 months is gigabytes of nothing.
NEEDED = list(dict.fromkeys(
    ["flight_id", "split", "is_delayed"] + SCHEDULE_FEATURES + ROTATION_FEATURES
))


def load(cutoff: int, population: str) -> pd.DataFrame:
    cols = ", ".join(NEEDED)
    df = duckdb.sql(
        f"SELECT {cols} FROM '{PQ}' WHERE cutoff_min = {cutoff}"
    ).df()
    if population == "clean":
        df = df[df.sched_turn_min.isna() | (df.sched_turn_min >= 0)]
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    for c in ["has_pred", "pred_contiguous"]:
        df[c] = df[c].astype("float64")
    # float32 is plenty for LightGBM and halves the memory.
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    df["y"] = df["is_delayed"].astype("int8")
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
    preds = pd.DataFrame({
        "model": label,
        "flight_id": te["flight_id"].to_numpy(),
        "y": te["y"].to_numpy(),
        "p": p,
    })
    return metrics, preds


headline = {}

for population, suffix in [("all", ""), ("clean", "_clean")]:
    base = load(CUTOFFS[0], population)
    test_n = int((base.split == "test").sum())
    floor = base.loc[base.split == "test", "y"].mean()
    ref, ref_preds = fit_and_score(base, SCHEDULE_FEATURES, "schedule only")

    print(f"\n=== population: {population} ===")
    print(f"test flights {test_n:,}   base rate {floor:.4f}")
    print(f"schedule-only        AP {ref['ap']:.4f}   Brier {ref['brier']:.4f}")

    rows, preds = [], [ref_preds]
    for cutoff in CUTOFFS:
        df = load(cutoff, population)
        res, pr = fit_and_score(df, SCHEDULE_FEATURES + ROTATION_FEATURES,
                                f"+rotation @ {cutoff} min")
        preds.append(pr)
        rows.append({"cutoff_min": cutoff, "ap": res["ap"],
                     "delta_ap": res["ap"] - ref["ap"],
                     "brier": res["brier"], "rounds": res["rounds"]})
        print(f"cutoff {cutoff:>5} min   AP {res['ap']:.4f}   "
              f"delta {res['ap'] - ref['ap']:+.4f}   Brier {res['brier']:.4f}")
        if cutoff == HEADLINE:
            headline[population] = res["ap"] - ref["ap"]

    out = pd.DataFrame(rows)
    out.insert(0, "ap_reference", ref["ap"])
    out.insert(0, "ap_floor", floor)
    out.insert(0, "test_rows", test_n)
    out.to_csv(f"data/interim/ablation{suffix}.csv", index=False)

    # Calibration is checked on the full population only.
    if population == "all":
        pd.concat(preds, ignore_index=True).to_parquet(
            "data/interim/predictions.parquet", index=False
        )

a, c = headline["all"], headline["clean"]
print(f"\n=== headline at {HEADLINE} minutes ===")
print(f"upper bound (all flights)          : {a:+.4f}")
print(f"lower bound (clean rotations only) : {c:+.4f}")
print(f"the swap group accounts for        : {a - c:+.4f}  "
      f"({(a - c) / a:.1%} of the upper bound)")