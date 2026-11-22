"""Figure: S4 hangs (no return within 90 s, body trickled at 1 byte / 2 s) by the strongest timeout construct in the
solution and by language, both conditions (exploratory, Sect. 6.2.2; same data as rq1_s4_mechanism.csv).

  python3 analysis/s4_mechanism.py && python3 analysis/fig_s4construct.py
Writes analysis/out/main/fig_s4construct.{pdf,png}.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out" / "main"
d = {(r["lang"], r["group"]): (int(r["no_return_90"]), int(r["solutions"]))
     for r in csv.DictReader(open(OUT / "rq1_s4_mechanism.csv"))}
LANGS = [("python", "Python"), ("typescript", "TypeScript"), ("java", "Java (JDK 25)"), ("go", "Go"), ("all", "All")]
GROUPS = [("whole-call deadline", "Deadline on the whole call", "0.15", None),
          ("per-read or until-headers only", "Only per-read or until-headers timeouts", "0.62", None),
          ("no timeout", "No timeout", "white", "////")]

plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.linewidth": 0.6, "hatch.linewidth": 0.5})
fig, ax = plt.subplots(figsize=(4.8, 2.45))
h = 0.26
for i, (lang, lname) in enumerate(LANGS):
    y0 = (len(LANGS) - 1 - i)
    for j, (g, _, col, hatch) in enumerate(GROUPS):
        y = y0 + (1 - j) * h
        if (lang, g) not in d:
            ax.text(1, y, "no solutions", va="center", fontsize=6.5, color="0.35")
            continue
        e, n = d[(lang, g)]
        p = 100 * e / n
        ax.barh(y, p, height=h * 0.86, color=col, edgecolor="black", linewidth=0.5, hatch=hatch)
        ax.text(p + 1.2, y, f"{e}/{n:,}", va="center", fontsize=6.5)
ax.set_yticks(range(len(LANGS)))
ax.set_yticklabels([n for _, n in LANGS][::-1])
ax.set_xlim(0, 112)
ax.set_xticks(range(0, 101, 20))
ax.set_xlabel("Solutions that did not return within 90 s in S4 (%)")
ax.grid(axis="x", color="0.88", lw=0.5)
ax.set_axisbelow(True)
ax.tick_params(length=2)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
handles = [Patch(facecolor=col, edgecolor="black", linewidth=0.5, hatch=hatch, label=lab) for _, lab, col, hatch in GROUPS]
fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=6.8, bbox_to_anchor=(0.53, -0.005), handlelength=1.4,
           columnspacing=1.0)
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.savefig(OUT / "fig_s4construct.pdf")
fig.savefig(OUT / "fig_s4construct.png", dpi=200)
