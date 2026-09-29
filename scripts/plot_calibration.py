"""Reliability diagram: are the predicted probabilities believable?

Average precision only judges the ORDER of the predictions. This figure judges
the numbers themselves: of the flights the model called "40% likely to be
late", were about 40% actually late?

Reads data/interim/predictions.parquet (written by scripts/train.py) and
writes reports/calibration.png for the README.
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]   # validated slots 1-3

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"],
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
})

PQ = Path("data/interim/predictions.parquet")
OUT = Path("reports/calibration.png")
N_BINS = 10

# Three is the readable maximum here; the cutoffs in between tell the same story.
SHOW = ["schedule only", "+rotation @ 180 min", "+rotation @ 45 min"]
NICE = {
    "schedule only": "schedule only",
    "+rotation @ 180 min": "+ aircraft state, 3 h out",
    "+rotation @ 45 min": "+ aircraft state, 45 min out",
}

preds = pd.read_parquet(PQ)

fig, ax = plt.subplots(figsize=(8.0, 7.6), dpi=200)

# Perfect calibration. Not data, so it is a thin neutral rule.
ax.plot([0, 1], [0, 1], color=MUTED, lw=1.2, ls=(0, (5, 3)), zorder=2)

summary, curves, hi = [], [], 0.0
for colour, name in zip(SERIES, SHOW):
    d = preds.loc[preds.model == name, ["y", "p"]].copy()
    # Equal-COUNT bins, not equal-width: the high-probability tail is thin, and
    # equal-width bins there would be dominated by sampling noise.
    d["bin"] = pd.qcut(d.p, N_BINS, labels=False, duplicates="drop")
    g = d.groupby("bin", observed=True).agg(
        predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size")
    )
    curves.append((colour, name, g))
    hi = max(hi, g.predicted.max(), g.observed.max())
    summary.append((NICE[name], d.p.mean(), d.y.mean()))

# Crop to the region the data actually occupies; an empty upper-right
# quadrant would shrink the part of the chart that carries the message.
top = min(1.0, round(hi + 0.08, 1))
for colour, name, g in curves:
    label = (f"{NICE[name]}  —  says {g.predicted.mean():.2f}, "
             f"actually {g.observed.mean():.2f}")
    ax.plot(g.predicted, g.observed, color=colour, lw=2, zorder=4,
            solid_capstyle="round", label=label)
    ax.plot(g.predicted, g.observed, "o", ms=8, color=colour,
            mec=SURFACE, mew=2, zorder=5, linestyle="none")

ax.annotate("perfectly calibrated", xy=(top * 0.86, top * 0.86),
            xytext=(0, -15), textcoords="offset points",
            fontsize=9.5, color=MUTED, rotation=45,
            rotation_mode="anchor", ha="center")

ax.set_xlim(-0.015, top)
ax.set_ylim(-0.015, top)
ax.set_aspect("equal")
ticks = [t / 10 for t in range(0, int(top * 10) + 1, 2)]
ax.set_xticks(ticks)
ax.set_yticks(ticks)
ax.tick_params(labelsize=10.5)
ax.set_xlabel("Predicted probability of delay", fontsize=10.5,
              color=INK_2, labelpad=10)
ax.set_ylabel("Observed share of flights actually delayed", fontsize=10.5,
              color=INK_2, labelpad=10)
ax.grid(color=GRID, lw=0.8)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
ax.spines["left"].set_color(AXIS)
ax.spines["bottom"].set_color(AXIS)

# Under-prediction puts every curve above the diagonal, so the lower right
# triangle is the empty region. The bias numbers live in the legend labels so
# the colour and its number are never separated.
leg = ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.02), frameon=False,
                fontsize=9.5, handlelength=2.0, labelspacing=0.9)
for t in leg.get_texts():
    t.set_color(INK_2)

fig.text(0.058, 0.975, "The models rank well, but predict too low",
         fontsize=16, fontweight="bold", color=INK, va="top")
fig.text(0.058, 0.935,
         "Trained on October 2023 – March 2025, when 19.7% of flights ran late; tested on June–September\n"
         "2025, when 24.2% did. Aircraft state improves both the ranking and the level — but not enough.",
         fontsize=9.5, color=INK_2, va="top", linespacing=1.6)
fig.text(0.058, 0.022,
         "Each point is a decile of predicted probability: ~236,000 flights, bin standard error ≈ 0.001. "
         "The gap is not sampling noise.",
         fontsize=8.8, color=MUTED, va="bottom")

fig.subplots_adjust(left=0.10, right=0.97, top=0.865, bottom=0.145)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT)
print(f"wrote {OUT}")
for name, mp, my in summary:
    print(f"{name:32s} mean predicted {mp:.4f}   observed {my:.4f}   bias {mp - my:+.4f}")