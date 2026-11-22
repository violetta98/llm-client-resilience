"""D62: precision of the registered requirements contrast, post hoc, on existing data only.

  python3 analysis/precision_d62.py   -> analysis/out/precision/summary.json

For each primary outcome (no return in 90 s in S3; time-limit overrun in B and H tasks; duplicate write in S8 in W1,
W2, B4) the pooled risk difference C2 - C0 over runnable solutions, with a 95 % percentile interval from a bootstrap
over tasks (10,000 resamples, seed 1). Pooled over models, so it answers a different question than the registered
per-model contrasts: how large an average effect of the requirements prompt the data still allow. Reported with and
without Qwen and Granite, the two models whose runnable shares and baseline rates differ most.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
OUT = REPO / "analysis" / "out" / "precision"
WEAK = {"qwen3-coder-next", "granite-4.2-8b"}


def load():
    sol = defaultdict(dict)
    for line in open(REPO / "analysis" / "out" / "main" / "runs.jsonl"):
        r = json.loads(line)
        if r["limit_s"] == 90 and r.get("usable"):
            sol[tuple(str(r[k]) for k in KEYS)][r["scenario"]] = r
    return sol


def rows_for(sol, name):
    out = []
    for k, v in sol.items():
        t = k[2]
        if name == "s3_hang" and "S3" in v:
            out.append((k, int(bool(v["S3"].get("no_return_90")))))
        elif name == "overrun" and t[0] in "BH":
            out.append((k, int(any(bool(x.get("overrun")) for x in v.values()))))
        elif name == "duplicate_write" and t in ("W1", "W2", "B4") and "S8" in v:
            out.append((k, int(bool(v["S8"].get("unsafe_write_retry")))))
        elif name == "s4_hang" and "S4" in v:
            out.append((k, int(bool(v["S4"].get("no_return_90")))))
    return out


def rd(by_task, tasks):
    a = {"C0": [0, 0], "C2": [0, 0]}
    for t in tasks:
        for c in ("C0", "C2"):
            a[c][0] += by_task[t][c][0]
            a[c][1] += by_task[t][c][1]
    if not a["C0"][0] or not a["C2"][0]:
        return None
    return 100 * (a["C2"][1] / a["C2"][0] - a["C0"][1] / a["C0"][0]), a


def summarize(rows):
    by = defaultdict(lambda: {"C0": [0, 0], "C2": [0, 0]})
    for k, y in rows:
        by[k[2]][k[0]][0] += 1
        by[k[2]][k[0]][1] += y
    tasks = sorted(by)
    est, a = rd(by, tasks)
    rng = random.Random(1)
    bs = []
    for _ in range(10000):
        r = rd(by, [rng.choice(tasks) for _ in tasks])
        if r is not None:
            bs.append(r[0])
    bs.sort()
    lo, hi = bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]
    return {"C0": f"{a['C0'][1]}/{a['C0'][0]} ({100 * a['C0'][1] / a['C0'][0]:.1f} %)",
            "C2": f"{a['C2'][1]}/{a['C2'][0]} ({100 * a['C2'][1] / a['C2'][0]:.1f} %)",
            "rd_pp": round(est, 1), "ci95": [round(lo, 1), round(hi, 1)], "tasks": len(tasks)}


def main():
    sol = load()
    res = {}
    for name in ("s3_hang", "overrun", "duplicate_write", "s4_hang"):
        rows = rows_for(sol, name)
        res[name] = {"all": summarize(rows), "without_qwen_granite": summarize([r for r in rows if r[0][1] not in WEAK])}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
