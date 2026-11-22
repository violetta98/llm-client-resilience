"""Figure of the paper: Kaplan-Meier time to return in S1-S4 per language, drawn from rq1_km.csv.

  python3 analysis/fig_km.py [--run main]

Reads analysis/out/<run>/rq1_km.csv (written by descriptive.py) and writes fig_km.pdf and fig_km.png next to it.
Layout only: a 2x2 grid with readable fonts; the estimates are those of descriptive.py.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TITLES = {"S1": "S1  connection stall", "S2": "S2  TLS stall", "S3": "S3  response stall",
          "S4": "S4  trickled body"}
LANGS = [("python", "Python", "#0072B2", "-"), ("typescript", "TypeScript", "#E69F00", "--"),
         ("java", "Java", "#009E73", "-."), ("go", "Go", "#CC79A7", ":")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    pts = defaultdict(list)
    with open(out / "rq1_km.csv") as f:
        for r in csv.DictReader(f):
            pts[(r["scenario"], r["lang"])].append((float(r["t"]), float(r["survival"])))
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 8.5, "legend.fontsize": 7.5})
    fig, axes = plt.subplots(2, 2, figsize=(4.7, 3.5), sharex=True, sharey=True)
    for ax, sc in zip(axes.flat, ("S1", "S2", "S3", "S4")):
        for lang, name, color, ls in LANGS:
            p = pts[(sc, lang)]
            xs, ys = [0.0], [100.0]
            for x, y in p[1:]:
                xs += [x, x]
                ys += [ys[-1], 100 * y]
            xs.append(330.0)
            ys.append(ys[-1])
            ax.plot(xs, ys, color=color, ls=ls, lw=1.3, label=name)
        ax.axvline(90, color="grey", lw=0.8, ls=":")
        ax.set_title(TITLES[sc], loc="left")
        ax.set_xlim(0, 330)
        ax.set_ylim(0, 102)
        ax.set_xticks([0, 90, 180, 270, 330])
        ax.grid(axis="y", color="#dddddd", lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0, 0].text(95, 90, "90 s", color="grey", fontsize=7)
    for ax in axes[1]:
        ax.set_xlabel("seconds since the call")
    for ax in axes[:, 0]:
        ax.set_ylabel("% still waiting")
    axes[1, 0].legend(loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(out / "fig_km.pdf")
    fig.savefig(out / "fig_km.png", dpi=200)
    print("wrote", out / "fig_km.pdf")


if __name__ == "__main__":
    main()
