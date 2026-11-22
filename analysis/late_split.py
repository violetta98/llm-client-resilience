"""Late requests split into HTTP requests and connection attempts (D49, post hoc, found in review).

  python3 analysis/late_split.py [--run main]

The registered measure (analysis/measures.py) counts as late both HTTP requests to the dependency and, under the
connection-level faults S1, S2 and S9, new SYNs seen by packet capture within 5 s after the function returned. Under S1
and S2 Node's undici opens a new connection about 10 s after the previous attempt regardless of the solution, so a
SYN counts as late only when the function happened to return in the 5 s before it. This script recomputes, per
solution, whether any run has a late HTTP request and whether any has only late SYNs, with the same windows and
tolerance as measures.py, and writes analysis/out/<run>/review/late_split.csv (by condition and language).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

TH = json.loads((REPO / "protocol" / "thresholds.json").read_text())
KEYS = ("cond", "model", "task", "lang", "sample")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    sol = defaultdict(lambda: {"any": False, "http": False, "syn": False})
    for line in open(out / "runs.jsonl"):
        r = json.loads(line)
        if not r.get("usable") or r["limit_s"] != 90:
            continue
        k = tuple(str(r[x]) for x in KEYS)
        s = sol[k]
        if not r.get("late_requests"):
            continue
        s["any"] = True
        run = M.load_run(REPO / "data" / a.run / "runs" / Path(*k) / r["scenario"])
        calls = (run["result"] or {}).get("calls") or []
        ends = [c.get("t_end") for c in calls if c.get("t_end")]
        w = TH["late_window_s"] * 1e9
        http = any(0 < q["t_first_byte"] - te <= w for q in run["requests"] if q["role"] == "dep" for te in ends)
        s["http"] |= http
        s["syn"] |= not http
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for k, s in sol.items():
        for g in (k[0] + " all", k[0] + " " + k[3]):
            a_ = agg[g]
            a_[0] += 1
            a_[1] += s["any"]
            a_[2] += s["http"]
            a_[3] += s["any"] and not s["http"]
    rows = [{"group": g, "solutions": v[0], "late_registered_pct": round(100 * v[1] / v[0], 1),
             "late_http_pct": round(100 * v[2] / v[0], 1), "late_syn_only_pct": round(100 * v[3] / v[0], 1)}
            for g, v in sorted(agg.items())]
    (out / "review").mkdir(parents=True, exist_ok=True)
    with open(out / "review" / "late_split.csv", "w", newline="") as fh:
        w_ = csv.DictWriter(fh, list(rows[0]))
        w_.writeheader()
        w_.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
