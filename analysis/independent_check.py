"""Independent re-implementation of two headline measures from the raw run records, written from the protocol's
definitions (protocol/ANALYSIS_PLAN.md, protocol/thresholds.json) without importing analysis/measures.py.

  python3 analysis/independent_check.py [--run main]

  S4 hang:            the measured call did not return within 90 s (result.json: a call without t_end, status
                      no_return, or a duration above 90 s).
  S7 excessive retry: more than 10 requests for one logical call reach the faulted dependency during the 30 s
                      outage. The outage start is taken here as the first non-warmup request to the faulted
                      dependency (measures.py uses the mock's own outage timestamp); in B2 the first request of
                      each key is a poll, not a retry, and is not counted.

Compares each with the value in analysis/out/<run>/runs.jsonl (90 s runs marked usable) and writes
analysis/out/<run>/independent_check.csv (one row per measure: runs compared, agreement, Cohen's kappa, rates).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIMIT_S, WINDOW_S, MAX_ATTEMPTS = 90, 30, 10


def jl(p: Path):
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def s4_hang(d: Path):
    r = json.loads((d / "result.json").read_text())
    calls = r.get("calls") or []
    if not calls:
        return None
    for c in calls:
        if c.get("status") == "no_return" or not c.get("t_end"):
            return True
        if (c["t_end"] - c["t_start"]) / 1e9 > LIMIT_S:
            return True
    return False


def s7_excessive(d: Path, task: str):
    orch = json.loads((d / "orchestrator.json").read_text())
    dep = orch.get("fault_dep", "A")
    qs = [q for q in jl(d / "requests.jsonl") if q.get("role") != "warmup" and q.get("dep") == dep
          and q.get("logical_key") is not None]
    if not qs:
        return False
    start = min(q["t_first_byte"] for q in qs)
    by = defaultdict(list)
    for q in qs:
        if q["t_first_byte"] - start < WINDOW_S * 1e9:
            by[q["logical_key"]].append(q["t_first_byte"])
    counts = [len(v) - (1 if task == "B2" else 0) for v in by.values()]
    return any(n > MAX_ATTEMPTS for n in counts)


def kappa(pairs):
    n = len(pairs)
    a = sum(x == y for x, y in pairs) / n
    p1, p2 = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return (a - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    ref = {}
    for line in open(out / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r.get("limit_s") == 90 and r["scenario"] in ("S4", "S7"):
            ref[(r["cond"], r["model"], r["task"], r["lang"], str(r["sample"]), r["scenario"])] = r
    pairs = {"S4 hang": [], "S7 excessive": []}
    disagree = []
    for k, r in sorted(ref.items()):
        d = REPO / "data" / a.run / "runs" / Path(*k)
        if not (d / "result.json").exists():
            continue
        if k[5] == "S4":
            mine, theirs, name = s4_hang(d), bool(r.get("no_return_90")), "S4 hang"
        else:
            if r.get("excessive_retries") is None:
                continue
            mine, theirs, name = s7_excessive(d, k[2]), bool(r["excessive_retries"]), "S7 excessive"
        if mine is None:
            continue
        pairs[name].append((int(mine), int(theirs)))
        if mine != theirs:
            disagree.append({"measure": name, "run": "/".join(k), "independent": int(mine), "measures_py": int(theirs)})
    rows = []
    for name, p in pairs.items():
        rows.append({"measure": name, "runs": len(p), "agree": sum(x == y for x, y in p),
                     "agreement_pct": round(100 * sum(x == y for x, y in p) / len(p), 2),
                     "kappa": round(kappa(p), 3),
                     "rate_independent_pct": round(100 * sum(x for x, _ in p) / len(p), 1),
                     "rate_measures_py_pct": round(100 * sum(y for _, y in p) / len(p), 1)})
    with open(out / "independent_check.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(out / "independent_check_disagreements.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["measure", "run", "independent", "measures_py"])
        w.writeheader()
        w.writerows(disagree)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
