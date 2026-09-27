"""Historical-rate baseline: how far can you get with no model at all?

For each (route, local departure hour), take the delay rate observed in the
TRAINING split, and use it as the predicted probability on the test split.
Every model we build later has to beat this number to justify existing.
"""
import duckdb
from sklearn.metrics import average_precision_score, brier_score_loss

PQ = "data/interim/features.parquet"

# The features table has one row per (flight x cutoff). This baseline uses no
# rotation features at all, so any single cutoff gives us one row per flight.
# 45 minutes = 0.75 hours
ONE_ROW_PER_FLIGHT = "cutoff_h = 0.75"

df = duckdb.sql(f"""
    WITH train AS (
        SELECT * FROM '{PQ}' WHERE split = 'train' AND {ONE_ROW_PER_FLIGHT}
    ),
    prior AS (
        SELECT avg(is_delayed::INT) AS global_rate FROM train
    ),
    -- Additive smoothing toward the global rate. A route-hour cell seen twice
    -- should not be trusted to say "100% delayed"; k=20 means a cell needs
    -- ~20 flights before its own rate dominates the prior.
    rates AS (
        SELECT t.route, t.dep_hour,
               (sum(t.is_delayed::INT) + 20 * p.global_rate)
                   / (count(*) + 20)  AS rate,
               count(*)                AS n_train
        FROM train t CROSS JOIN prior p
        GROUP BY t.route, t.dep_hour, p.global_rate
    )
    SELECT
        te.is_delayed::INT               AS y,
        coalesce(r.rate, p.global_rate)  AS p_hat,
        (r.route IS NULL)                AS unseen_cell
    FROM '{PQ}' te
    CROSS JOIN prior p
    LEFT JOIN rates r ON te.route = r.route AND te.dep_hour = r.dep_hour
    WHERE te.split = 'test' AND te.{ONE_ROW_PER_FLIGHT}
""").df()

base_rate = df.y.mean()

print(f"test flights        : {len(df):,}")
print(f"base rate (delayed) : {base_rate:.4f}")
print(f"unseen route-hours  : {df.unseen_cell.sum():,} "
      f"({df.unseen_cell.mean():.1%})")
print()
print(f"AP  of always-base-rate : {base_rate:.4f}   <- the floor")
print(f"AP  of this baseline    : {average_precision_score(df.y, df.p_hat):.4f}")
print(f"Brier of this baseline  : {brier_score_loss(df.y, df.p_hat):.4f}")