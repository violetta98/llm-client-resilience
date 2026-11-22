"""Stage A, step 2: one row per solution for the three primary outcomes (PROTOCOL.md section 5).

  python3 analysis/primary.py [--run main]

Reads  analysis/out/<run>/runs.jsonl (analysis/collect.py)
Writes analysis/out/<run>/primary.csv with columns
  cond, model, task, lang, sample, flagship, outcome, y, n_scenarios, complete
  outcome = s3_no_return      no return within 90 s in S3 (all tasks)
            overrun           time-limit overrun in any scenario (B and H tasks)
            unsafe_write      unsafe write retry in S8 (W1, W2, B4)
Only runs with harness_ok count. A solution is `complete` when every scenario the outcome needs is present;
the models use complete solutions only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

KEYS = ("cond", "model", "task", "lang", "sample")
FLAGSHIPS = {"claude-opus-5.5", "gpt-6.1-sol", "gemini-4-argon"}
UNSAFE_TASKS = {"W1", "W2", "B4"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    rows = [json.loads(l) for l in open(out / "runs.jsonl")]
    per = defaultdict(dict)
    for r in rows:
        if r["limit_s"] != 90 or r.get("program_category") != "ok":
            continue
        per[tuple(r[k] for k in KEYS)][r["scenario"]] = r if r.get("usable") else None
    scen = {}
    res = []
    for key, sc in sorted(per.items()):
        p = dict(zip(KEYS, key))
        t = p["task"]
        if t not in scen:
            scen[t] = yaml.safe_load((M.task_dir(t) / "expected.yaml").read_text())["scenarios"]
        base = p | {"flagship": int(p["model"] in FLAGSHIPS)}
        # 1. no return in 90 s in S3
        r = sc.get("S3")
        res.append(base | {"outcome": "s3_no_return", "y": "" if r is None else int(bool(r["no_return_90"])),
                           "n_scenarios": int(r is not None), "complete": int(r is not None)})
        # 2. time-limit overrun, B and H tasks, any scenario
        if t[0] in "BH":
            got = [x for s, x in sc.items() if x is not None]
            y = int(any(x.get("overrun") for x in got)) if got else ""
            complete = len(got) == len(scen[t])
            if not complete and y == 0:
                y = ""  # an overrun may still appear in a missing scenario
            res.append(base | {"outcome": "overrun", "y": y, "n_scenarios": len(got), "complete": int(complete)})
        # 3. unsafe write retry in S8
        if t in UNSAFE_TASKS:
            r = sc.get("S8")
            res.append(base | {"outcome": "unsafe_write", "y": "" if r is None else int(bool(r.get("unsafe_write_retry"))),
                               "n_scenarios": int(r is not None), "complete": int(r is not None)})
    with open(out / "primary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, [*KEYS, "flagship", "outcome", "y", "n_scenarios", "complete"])
        w.writeheader()
        w.writerows(res)
    summ = defaultdict(lambda: [0, 0, 0])
    for r in res:
        s = summ[r["outcome"]]
        s[0] += 1
        if r["complete"]:
            s[1] += 1
            s[2] += r["y"] if r["y"] != "" else 0
    print({k: {"solutions": v[0], "complete": v[1], "events": v[2]} for k, v in summ.items()})


if __name__ == "__main__":
    main()
