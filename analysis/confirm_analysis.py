"""Confirmatory replication (protocol/CONFIRM_ADDENDUM.md, D43): data for H1-H3 and the test of H4.

  python3 analysis/confirm_analysis.py            -> analysis/out/confirm/confirm_h.csv, confirm_h4.csv,
                                                    confirm_descriptive.csv, confirm_boot.csv
  then: docker run --rm --network none -v "$PWD/analysis:/a:ro" -v "$PWD/analysis/out/confirm:/d" \
        lcr-analysis-r:dev Rscript /a/confirm_model.R /d          -> confirm_tests.csv

Unit: runnable solution (90 s runs with `usable`). Whole-call deadline: classifier constructs in WHOLE
(analysis/s4_mechanism.py, version frozen in protocol/CONFIRM_FREEZE.json).
H1: S4 hang ~ no whole-call deadline (+ condition), all tasks.   H2: S4 hang ~ C2, tasks R6 and W5.
H3: S7 excessive retries ~ C2, all tasks.   H4: share of failing Python solutions flagged by Bandit B113 and by
Ruff S113 < 0.10, exact one-sided binomial test, only if >= 20 failing solutions.
Bootstrap: difference in proportions over models, 2,000 resamples, seed 20261106.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402

KEYS = ("cond", "model", "task", "lang", "sample")
OUT = REPO / "analysis" / "out" / "confirm"
SEED, B = 20261106, 2000


def k(r):
    return tuple(str(r[x]) for x in KEYS)


def write(name, rows):
    with open(OUT / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def binom_upper_p(x, n, p):
    """P(X <= x) for X ~ Bin(n, p): one-sided p-value for H4 (share < p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))


def boot_models(rows, xname):
    """difference in proportions (x=1 minus x=0) with a bootstrap over models"""
    by = defaultdict(list)
    for r in rows:
        by[r["model"]].append(r)
    models = sorted(by)
    rng = random.Random(SEED)

    def diff(rs):
        a = [r["y"] for r in rs if r[xname] == 1]
        b = [r["y"] for r in rs if r[xname] == 0]
        return (sum(a) / len(a) - sum(b) / len(b)) if a and b else None
    est = []
    for _ in range(B):
        d = diff([r for m in (rng.choice(models) for _ in models) for r in by[m]])
        if d is not None:
            est.append(d)
    est.sort()
    obs = diff(rows)
    p_one = sum(e <= 0 for e in est) / len(est) if est else None
    return obs, est[int(0.025 * len(est))], est[int(0.975 * len(est)) - 1], p_one


def main():
    runs = defaultdict(dict)
    for line in open(OUT / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r.get("limit_s") == 90:
            runs[k(r)][r["scenario"]] = r
    progs = {k(p): p for p in csv.DictReader(open(OUT / "programs.csv"))}
    ok = [s for s in runs if progs.get(s, {}).get("category") == "ok"]
    feats = {k(f): f for f in csv.DictReader(open(REPO / "data" / "confirm" / "classify" / "features.csv"))}

    def whole(s):
        cons = {c.strip() for c in (feats.get(s, {}).get("timeout_constructs") or "").split(";") if c.strip()}
        return int(bool(cons & WHOLE))

    rows = []
    for s in ok:
        base = dict(zip(KEYS, s))
        c2 = int(s[0] == "C2")
        r4 = runs[s].get("S4")
        if r4 is not None:
            y = int(bool(r4.get("no_return_90")))
            rows.append({**base, "hyp": "H1", "y": y, "x": 1 - whole(s), "c2": c2})
            if s[2] in ("R6", "W5"):
                rows.append({**base, "hyp": "H2", "y": y, "x": c2, "c2": c2})
        r7 = runs[s].get("S7")
        if r7 is not None and r7.get("excessive_retries") is not None:
            rows.append({**base, "hyp": "H3", "y": int(bool(r7["excessive_retries"])), "x": c2, "c2": c2})
    write("confirm_h.csv", rows)

    boot = []
    for h in ("H1", "H2", "H3"):
        rs = [r for r in rows if r["hyp"] == h]
        obs, lo, hi, p = boot_models(rs, "x")
        boot.append({"hyp": h, "n": len(rs), "share_x1": round(100 * sum(r["y"] for r in rs if r["x"] == 1) / max(1, sum(r["x"] == 1 for r in rs)), 1),
                     "share_x0": round(100 * sum(r["y"] for r in rs if r["x"] == 0) / max(1, sum(r["x"] == 0 for r in rs)), 1),
                     "diff_pp": round(100 * obs, 1) if obs is not None else "", "lo": round(100 * lo, 1), "hi": round(100 * hi, 1),
                     "p_one_sided_boot": p})
    write("confirm_boot.csv", boot)

    # H4
    lint = {}
    for tool in ("bandit_B113", "ruff_S113"):
        f = REPO / "data" / "confirm" / "lint" / tool / "findings.jsonl"
        lint[tool] = {k(json.loads(l)): bool(json.loads(l)["flagged"]) for l in open(f)} if f.exists() else {}
    failing = [s for s in ok if s[3] == "python" and (
        any(runs[s].get(sc, {}).get("no_return_90") for sc in ("S3", "S4"))
        or any(r.get("overrun") for r in runs[s].values()))]
    h4 = []
    for tool, fl in lint.items():
        n = len(failing)
        x = sum(fl.get(s, False) for s in failing)
        h4.append({"tool": tool, "failing_python": n, "flagged": x, "share": round(100 * x / n, 1) if n else "",
                   "p_one_sided_vs_0.10": round(binom_upper_p(x, n, 0.10), 6) if n >= 20 else "",
                   "tested": int(n >= 20)})
    write("confirm_h4.csv", h4)

    desc = []
    for cond in ("C0", "C2"):
        for lang in ("all", "python", "typescript", "java", "go"):
            sel = [s for s in ok if s[0] == cond and (lang == "all" or s[3] == lang)]
            s4 = [runs[s]["S4"] for s in sel if "S4" in runs[s]]
            s7 = [runs[s]["S7"] for s in sel if "S7" in runs[s] and runs[s]["S7"].get("excessive_retries") is not None]
            desc.append({"cond": cond, "lang": lang, "solutions": len(sel),
                         "s4_hang_pct": round(100 * sum(bool(r.get("no_return_90")) for r in s4) / len(s4), 1) if s4 else "",
                         "s7_excessive_pct": round(100 * sum(bool(r["excessive_retries"]) for r in s7) / len(s7), 1) if s7 else ""})
    write("confirm_descriptive.csv", desc)
    for f in ("confirm_boot.csv", "confirm_h4.csv", "confirm_descriptive.csv"):
        print("==", f); print((OUT / f).read_text())


if __name__ == "__main__":
    main()
