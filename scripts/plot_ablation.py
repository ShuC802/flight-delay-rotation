"""Render the headline figure: what aircraft-rotation state is worth, by cutoff.

Reads data/interim/ablation.csv (written by scripts/train.py) and writes
reports/ablation.png for the README.
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

# ---- chart palette (light surface) ----
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = "#2a78d6"
SERIES_WASH = "#cde2fb"

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

CSV = Path("data/interim/ablation.csv")
OUT = Path("reports/ablation.png")

df = pd.read_csv(CSV).sort_values("cutoff_min", ascending=False)
df["cutoff_h"] = df["cutoff_min"] / 60.0
ref = float(df["ap_reference"].iloc[0])      # schedule-only model
floor = float(df["ap_floor"].iloc[0])        # base rate = no-skill AP

fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=200)

# The gain IS the vertical gap between the reference line and the curve,
# so draw it as an area rather than making the reader subtract.
ax.fill_between(df.cutoff_h, ref, df.ap, color=SERIES_WASH, alpha=0.6, zorder=1)

# Reference rules are not data: dashed and recessive.
ax.axhline(ref, color=INK_2, lw=1.2, ls=(0, (5, 3)), zorder=2)
ax.axhline(floor, color=MUTED, lw=1.2, ls=(0, (5, 3)), zorder=2)

ax.plot(df.cutoff_h, df.ap, color=SERIES, lw=2, zorder=4, solid_capstyle="round")
ax.plot(df.cutoff_h, df.ap, "o", ms=9, color=SERIES,
        mec=SURFACE, mew=2, zorder=5, linestyle="none")

# ---- axes ----
ax.set_xscale("log")
ax.invert_xaxis()
ax.set_xticks(df.cutoff_h.tolist())
ax.set_xticklabels(["24 h", "6 h", "3 h", "1.5 h", "45 min"], fontsize=10.5)
ax.xaxis.set_minor_locator(mpl.ticker.NullLocator())
ax.set_xlim(34, 0.5)

ax.set_ylim(floor - 0.035, df.ap.max() + 0.075)
ax.set_yticks([0.40, 0.50, 0.60, 0.70, 0.80])
ax.tick_params(axis="y", labelsize=10.5)

ax.set_xlabel("Time before scheduled departure  (log scale  →  closer to takeoff)",
              fontsize=10.5, color=INK_2, labelpad=10)
ax.set_ylabel("Average precision", fontsize=10.5, color=INK_2, labelpad=10)

ax.grid(axis="y", color=GRID, lw=0.8)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
ax.spines["left"].set_color(AXIS)
ax.spines["bottom"].set_color(AXIS)

# ---- selective direct labels: the two endpoints only ----
first, last = df.iloc[0], df.iloc[-1]
ax.annotate(f"+{first.delta_ap:.3f}", (first.cutoff_h, first.ap),
            textcoords="offset points", xytext=(6, 11),
            fontsize=11, fontweight="bold", color=SERIES, ha="left")
ax.annotate(f"+{last.delta_ap:.3f}", (last.cutoff_h, last.ap),
            textcoords="offset points", xytext=(-4, 13),
            fontsize=12.5, fontweight="bold", color=SERIES, ha="right")

# ---- reference line labels, left-aligned where the plot is empty ----
ax.annotate(f"schedule features only — {ref:.3f}",
            xy=(0.012, ref), xycoords=("axes fraction", "data"),
            textcoords="offset points", xytext=(0, -15),
            fontsize=9.5, color=INK_2, ha="left")
ax.annotate(f"no-skill floor (base rate) — {floor:.3f}",
            xy=(0.012, floor), xycoords=("axes fraction", "data"),
            textcoords="offset points", xytext=(0, 7),
            fontsize=9.5, color=MUTED, ha="left")

# ---- name the mechanism behind the final jump ----
mid_x = (df.iloc[-2].cutoff_h * df.iloc[-1].cutoff_h) ** 0.5
mid_y = (df.iloc[-2].ap + df.iloc[-1].ap) / 2
ax.annotate(
    "the inbound aircraft has usually\nlanded by here — median\nturnaround is 65 minutes",
    xy=(mid_x, mid_y - 0.012), xytext=(2.05, 0.452),
    fontsize=9.5, color=INK_2, ha="center", va="center", linespacing=1.5,
    arrowprops=dict(arrowstyle="-", color=MUTED, lw=1,
                    connectionstyle="arc3,rad=0.0", shrinkA=10, shrinkB=8),
)

# ---- title block ----
fig.text(0.055, 0.965, "Most of the gain arrives in the final 90 minutes",
         fontsize=15.5, fontweight="bold", color=INK, va="top")
fig.text(0.055, 0.905,
         "Each point is a model that can see the aircraft's recent history at that cutoff; the dashed line is the\n"
         "same model without it. 118,428 held-out flights, 25–30 June 2025.",
         fontsize=9.5, color=INK_2, va="top", linespacing=1.6)

fig.subplots_adjust(left=0.085, right=0.975, top=0.79, bottom=0.135)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT)
print(f"wrote {OUT}")