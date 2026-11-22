"""Prompt ablation (protocol/ABLATION_ADDENDUM.md, D51): data for P1-P3 and the descriptive comparison.

  python3 analysis/collect_confirm.py --run ablation --jobs 4
  python3 analysis/collect_confirm.py --run confirm-s56 --jobs 4
  python3 analysis/ablation_analysis.py        -> analysis/out/ablation/ablation_p.csv, ablation_descriptive.csv
  docker run --rm --network none -v "$PWD/analysis:/a:ro" -v "$PWD/analysis/out/ablation:/d" \
        lcr-analysis-r:dev Rscript /a/ablation_model.R /d          -> ablation_tests.csv

C0 and C2 come from the held-out run (analysis/out/confirm/runs.jsonl; S5a and S6a from confirm-s56), C0b and
C2c from run `ablation`. Unit: runnable solution with usable 90 s runs in S0, S3, S4, S7 and S9.
P1: S7 excessive retries, C2c (c=1) vs C2 (c=0), all tasks.      P2: S4 hang, C2c (c=1) vs C0 (c=0), R6 and W5.
P3: S7 retries at all (more than one attempt for some logical call during the outage), C0b (c=1) vs C0 (c=0).
All three predict an odds ratio below 1.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out" / "ablation"
KEYS = ("cond", "model", "task", "lang", "sample")
CORE = ("S0", "S3", "S4", "S7", "S9")


def load(run):
    p = REPO / "analysis" / "out" / run / "runs.jsonl"
    rows = [json.loads(x) for x in open(p)] if p.exists() else []
    return [r for r in rows if r.get("usable") and r.get("limit_s") == 90]


def write(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def retried(r):
    a = r.get("attempts_during_outage") or {}
    return int(any(v > 1 for v in a.values()))


def maxatt(r):
    a = r.get("attempts_during_outage") or {}
    return max(a.values()) if a else 0


def pct(xs):
    xs = [x for x in xs if x is not None]
    return (round(100 * sum(xs) / len(xs), 1), len(xs)) if xs else (None, 0)


def q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(f * len(xs)))] if xs else None


def main():
    runs = load("confirm") + load("confirm-s56") + load("ablation")
    by = defaultdict(dict)
    for r in runs:
        by[tuple(str(r[k]) for k in KEYS)][r["scenario"]] = r
    sol = {k: v for k, v in by.items() if all(s in v for s in CORE)}
    prow = []
    for k, v in sol.items():
        cond, model, task, lang, sample = k
        base = {"model": model, "task": task, "lang": lang, "sample": sample, "cond": cond}
        if cond in ("C2", "C2c"):
            prow.append({**base, "hyp": "P1", "c": int(cond == "C2c"), "y": int(bool(v["S7"]["excessive_retries"]))})
        if cond in ("C0", "C2c") and task in ("R6", "W5"):
            prow.append({**base, "hyp": "P2", "c": int(cond == "C2c"), "y": int(bool(v["S4"]["no_return_90"]))})
        if cond in ("C0", "C0b"):
            prow.append({**base, "hyp": "P3", "c": int(cond == "C0b"), "y": retried(v["S7"])})
    write("ablation_p.csv", prow)

    # runnable share of generations
    gen = defaultdict(lambda: [0, 0])
    for run in ("confirm", "ablation"):
        p = REPO / "data" / run / "programs.jsonl"
        for x in (json.loads(l) for l in open(p)) if p.exists() else []:
            g = gen[x["cond"]]
            g[0] += x["category"] == "ok"
            g[1] += 1
    desc = []
    for cond in ("C0", "C0b", "C2", "C2c"):
        S = {k: v for k, v in sol.items() if k[0] == cond}
        rw = {k: v for k, v in S.items() if k[2] in ("R6", "W5")}
        bh = {k: v for k, v in S.items() if k[2] in ("B5", "H4")}
        d = {"cond": cond, "solutions": len(S),
             "runnable_pct_of_generations": round(100 * gen[cond][0] / gen[cond][1], 1) if gen[cond][1] else None}
        m = {
            "S3_hang": [bool(v["S3"]["no_return_90"]) for v in S.values()],
            "S4_hang": [bool(v["S4"]["no_return_90"]) for v in S.values()],
            "S4_hang_R6W5": [bool(v["S4"]["no_return_90"]) for v in rw.values()],
            "S4_hang_B5H4": [bool(v["S4"]["no_return_90"]) for v in bh.values()],
            "S5a_correct": [v["S5a"]["outcome"] == "correct" for v in S.values() if "S5a" in v],
            "S6a_correct": [v["S6a"]["outcome"] == "correct" for v in S.values() if "S6a" in v],
            "S6a_retry_after_violation": [v["S6a"].get("retry_after_violation") for v in S.values() if "S6a" in v],
            "S7_retried": [retried(v["S7"]) for v in S.values()],
            "S7_excessive": [v["S7"]["excessive_retries"] for v in S.values()],
            "S9_excessive": [v["S9"]["excessive_retries"] for v in S.values()],
            "S9_rapid": [v["S9"]["rapid_retries"] for v in S.values()],
            "overrun_stated_limit_B5H4": [any(bool(x.get("overrun")) for x in v.values()) for v in bh.values()],
            "over_10s_R6W5": [any(max([t for t in (x.get("durations_s") or []) if t is not None] or [0]) > 10.25
                                  for x in v.values()) for v in rw.values()],
        }
        for name, xs in m.items():
            d[name + "_pct"], d[name + "_n"] = pct(xs)
        att = [maxatt(v["S7"]) for v in S.values()]
        d["S7_max_attempts_median"], d["S7_max_attempts_p90"] = q(att, 0.5), q(att, 0.9)
        desc.append(d)
    write("ablation_descriptive.csv", desc)
    for d in desc:
        print(d)
    print({h: sum(1 for r in prow if r["hyp"] == h) for h in ("P1", "P2", "P3")}, "rows")


if __name__ == "__main__":
    main()
