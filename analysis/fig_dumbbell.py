"""Figure: per-model shift from the baseline (C0) to the requirements prompt (C2) in S4 hangs and S7 excessive
retries (exploratory, Sect. 6.3.1). Reads analysis/out/main/runs.jsonl; writes analysis/out/main/fig_dumbbell.{pdf,png}
and fig_dumbbell.csv.

  python3 analysis/fig_dumbbell.py
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out" / "main"
MODELS = [("claude-opus-5.5", "Claude Opus 5.5"), ("gpt-6.1-sol", "GPT-6.1 Sol"), ("gemini-4-argon", "Gemini 4 Argon"),
          ("claude-haiku-5.5", "Claude Haiku 5.5"), ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash"), ("kimi-k3", "Kimi K3"),
          ("qwen3-coder-next", "Qwen3-Coder-Next"), ("granite-4.2-8b", "Granite 4.2 8B")]
agg = defaultdict(lambda: [0, 0])
for line in open(OUT / "runs.jsonl"):
    r = json.loads(line)
    if not r.get("usable") or r.get("limit_s") != 90:
        continue
    if r["scenario"] == "S4":
        k = ("S4", r["model"], r["cond"]); agg[k][0] += bool(r.get("no_return_90")); agg[k][1] += 1
    elif r["scenario"] == "S7":
        k = ("S7", r["model"], r["cond"]); agg[k][0] += bool(r.get("excessive_retries")); agg[k][1] += 1
rows = []
for m, _ in MODELS:
    for s in ("S4", "S7"):
        for c in ("C0", "C2"):
            e, n = agg[(s, m, c)]
            rows.append({"scenario": s, "model": m, "cond": c, "events": e, "n": n, "share": round(100 * e / n, 1)})
with open(OUT / "fig_dumbbell.csv", "w", newline="") as f:
    w = csv.DictWriter(f, list(rows[0])); w.writeheader(); w.writerows(rows)
share = {(r["scenario"], r["model"], r["cond"]): r["share"] for r in rows}

plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.linewidth": 0.6})
fig, axes = plt.subplots(1, 2, figsize=(4.7, 2.6), sharey=True)
ys = list(range(len(MODELS)))[::-1]
for ax, s, title in ((axes[0], "S4", "S4: no return in 90 s\n(% of solutions)"), (axes[1], "S7", "S7: over 10 attempts\nper call (% of solutions)")):
    for y, (m, _) in zip(ys, MODELS):
        a, b = share[(s, m, "C0")], share[(s, m, "C2")]
        ax.annotate("", xy=(b, y), xytext=(a, y), arrowprops=dict(arrowstyle="-|>", color="0.55", lw=0.9, shrinkA=3, shrinkB=3, mutation_scale=7))
        ax.plot(a, y, "o", ms=4.5, mfc="white", mec="black", mew=0.8, zorder=3)
        ax.plot(b, y, "o", ms=4.5, color="black", zorder=3)
    ax.set_xlim(-3, 103)
    ax.set_title(title, fontsize=8)
    ax.grid(axis="x", color="0.88", lw=0.5)
    ax.tick_params(length=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
axes[0].set_yticks(ys)
axes[0].set_yticklabels([n for _, n in MODELS])
axes[0].plot([], [], "o", ms=4.5, mfc="white", mec="black", label="Baseline (C0)")
axes[0].plot([], [], "o", ms=4.5, color="black", label="Requirements (C2)")
fig.legend(loc="lower center", ncol=2, frameon=False, fontsize=7.5, bbox_to_anchor=(0.6, -0.01))
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.savefig(OUT / "fig_dumbbell.pdf")
fig.savefig(OUT / "fig_dumbbell.png", dpi=200)
for r in rows:
    print(r)
