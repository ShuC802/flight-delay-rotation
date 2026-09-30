"""Headline figure: what the aircraft's recent history is worth, by cutoff.

Plots the GAIN in average precision rather than its level, because the two
populations have different base rates and reference models -- only the gain is
comparable between them.

The two curves bracket the answer. Aircraft swaps produce rotations that are
impossible on paper, and 88% of those flights arrive late; but BTS records
only the tail that actually flew, not when the swap was decided, so we cannot
tell whether that information was available at the cutoff. Excluding them
gives a lower bound, keeping them an upper bound.

Reads data/interim/ablation.csv and ablation_clean.csv.
Writes reports/ablation.png.
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
STRONG = "#1c5cab"      # the conservative estimate
LIGHT = "#5598e7"       # the upper bound
WASH = "#cde2fb"        # the band between them

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"],
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "axes.edgecolor": AXIS,
    "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
})

OUT = Path("reports/ablation.png")

full = pd.read_csv("data/interim/ablation.csv").sort_values("cutoff_min", ascending=False)
clean = pd.read_csv("data/interim/ablation_clean.csv").sort_values("cutoff_min", ascending=False)
for d in (full, clean):
    d["cutoff_h"] = d["cutoff_min"] / 60.0

fig, ax = plt.subplots(figsize=(8.4, 5.6), dpi=200)

# The band between the two estimates IS the uncertainty -- draw it.
ax.fill_between(full.cutoff_h, clean.delta_ap, full.delta_ap,
                color=WASH, alpha=0.75, zorder=1)

# Zero is a real baseline here, not a truncation: it means "no gain at all".
ax.axhline(0, color=AXIS, lw=1.2, zorder=2)

ax.plot(full.cutoff_h, full.delta_ap, color=LIGHT, lw=2, zorder=3,
        solid_capstyle="round", label="all flights (upper bound)")
ax.plot(full.cutoff_h, full.delta_ap, "o", ms=7, color=LIGHT,
        mec=SURFACE, mew=2, zorder=4, linestyle="none")

ax.plot(clean.cutoff_h, clean.delta_ap, color=STRONG, lw=2.4, zorder=5,
        solid_capstyle="round",
        label="excluding impossible rotations (conservative)")
ax.plot(clean.cutoff_h, clean.delta_ap, "o", ms=9, color=STRONG,
        mec=SURFACE, mew=2, zorder=6, linestyle="none")

ax.set_xscale("log")
ax.invert_xaxis()
ax.set_xticks(full.cutoff_h.tolist())
ax.set_xticklabels(["24 h", "6 h", "3 h", "1.5 h", "45 min"], fontsize=10.5)
ax.xaxis.set_minor_locator(mpl.ticker.NullLocator())
ax.set_xlim(34, 0.52)

ax.set_ylim(-0.012, full.delta_ap.max() + 0.055)
ax.tick_params(axis="y", labelsize=10.5)
ax.set_xlabel("Time before scheduled departure  (log scale  →  closer to takeoff)",
              fontsize=10.5, color=INK_2, labelpad=10)
ax.set_ylabel("Gain in average precision\nover a schedule-only model",
              fontsize=10.5, color=INK_2, labelpad=10, linespacing=1.5)
ax.grid(axis="y", color=GRID, lw=0.8)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
ax.spines["left"].set_color(AXIS)
ax.spines["bottom"].set_visible(False)

# Direct labels on the conservative curve's endpoints only.
f, l = clean.iloc[0], clean.iloc[-1]
ax.annotate(f"+{f.delta_ap:.3f}", (f.cutoff_h, f.delta_ap),
            textcoords="offset points", xytext=(7, -14),
            fontsize=10.5, fontweight="bold", color=STRONG, ha="left")
ax.annotate(f"+{l.delta_ap:.3f}", (l.cutoff_h, l.delta_ap),
            textcoords="offset points", xytext=(-6, 12),
            fontsize=12, fontweight="bold", color=STRONG, ha="right")

leg = ax.legend(loc="upper left", bbox_to_anchor=(0.015, 0.97), frameon=False,
                fontsize=9.5, handlelength=2.0, labelspacing=0.75)
for t in leg.get_texts():
    t.set_color(INK_2)

mid_x = (clean.iloc[-2].cutoff_h * clean.iloc[-1].cutoff_h) ** 0.5
mid_y = (clean.iloc[-2].delta_ap + clean.iloc[-1].delta_ap) / 2
ax.annotate("the inbound aircraft has usually\nlanded by here — median\nturnaround is 65 minutes",
            xy=(mid_x, mid_y - 0.004), xytext=(2.0, 0.026),
            fontsize=9.5, color=INK_2, ha="center", va="center", linespacing=1.5,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=1,
                            connectionstyle="arc3,rad=0.0", shrinkA=10, shrinkB=10))

fig.text(0.055, 0.965, "What knowing the aircraft is worth, and when",
         fontsize=15.5, fontweight="bold", color=INK, va="top")
fig.text(0.055, 0.905,
         "Gain over a model that sees only the timetable. 2,364,298 held-out flights, June–September 2025,\n"
         "from a model trained on October 2023 – March 2025.\n"
         "The band is the uncertainty from aircraft swaps, whose timing BTS does not record.",
         fontsize=9.5, color=INK_2, va="top", linespacing=1.6)

fig.subplots_adjust(left=0.105, right=0.975, top=0.79, bottom=0.135)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT)
print(f"wrote {OUT}")
