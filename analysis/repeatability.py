"""Stage A: repeatability of outcomes on the 5 % sample (PROTOCOL.md section 3, ANALYSIS_PLAN "Also").

  python3 analysis/repeatability.py [--run main --rep main-rep]

Reads  analysis/out/<run>/runs.jsonl and analysis/out/<rep>/runs.jsonl (analysis/collect.py)
Writes analysis/out/<run>/also_repeatability.csv    agreement per measure (pairs, agree, percent, Cohen's kappa)
       analysis/out/<run>/also_repeatability_pairs.csv  one row per (program, scenario) with both values of each measure
Pairs are the 90 s runs present with harness_ok in both runs; nothing is imputed.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample", "scenario")
HARM = ("rapid_retries", "retry_after_violation", "excessive_retries", "unsafe_write_retry", "sync_retries")
MEASURES = ("outcome", "no_return_90", "overrun", *HARM, "any_harmful_retry")


def value(r, m):
    if m == "any_harmful_retry":
        return int(any(bool(r.get(h)) for h in HARM))
    v = r.get(m)
    if m == "outcome":
        return v if v is not None else ""
    return "" if v is None else int(bool(v))


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return None if pe == 1 else (po - pe) / (1 - pe)


def load(run):
    out = {}
    for line in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(line)
        if r["limit_s"] == 90 and r.get("usable"):
            out[tuple(r[k] for k in KEYS)] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--rep", default="main-rep")
    a = ap.parse_args()
    base, rep = load(a.run), load(a.rep)
    common = sorted(set(base) & set(rep), key=str)
    out = REPO / "analysis" / "out" / a.run
    with open(out / "also_repeatability_pairs.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([*KEYS, *(f"{m}_{s}" for m in MEASURES for s in ("main", "rep"))])
        for k in common:
            w.writerow([*k, *(x for m in MEASURES for x in (value(base[k], m), value(rep[k], m)))])
    rows = []
    for m in MEASURES:
        pairs = [(value(base[k], m), value(rep[k], m)) for k in common]
        pairs = [p for p in pairs if p[0] != "" and p[1] != ""]
        agree = sum(a_ == b for a_, b in pairs)
        kp = kappa(pairs)
        rows.append({"measure": m, "pairs": len(pairs), "agree": agree,
                     "percent": round(100 * agree / len(pairs), 2) if pairs else "",
                     "kappa": "" if kp is None else round(kp, 3),
                     "positives_main": sum(1 for p in pairs if p[0] == 1),
                     "positives_rep": sum(1 for p in pairs if p[1] == 1)})
    with open(out / "also_repeatability.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(common)} pairs (main {sum(1 for k in rep if k in base)}/{len(rep)} rep runs matched)")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
