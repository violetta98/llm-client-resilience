"""D61: S4 at a 0.25 s trickle gap on the 25 % main sample (run main-g025), next to 0.5 s, 2 s and 5 s.

  python3 analysis/g025_d61.py   -> analysis/out/main/variants/s4_g025.csv

Share that does not return within 90 s, overall, per condition, per language and per timeout construct (whole-call
deadline / per-read or until headers only / none), on the programs with a harness-ok run at every gap.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from variants_analysis import construct_group, key, pct, variant, write  # noqa: E402

GAPS = ["S4g025", "S4g05", "S4", "S4g5"]


def main():
    res = defaultdict(dict)
    for src in ("main-g025", "main-variants"):
        for line in open(REPO / "data" / src / "measures.jsonl"):
            r = json.loads(line)
            if r.get("harness_ok") and r.get("limit_s", 90) == 90:
                res[key(r)][variant(r)] = r
    for line in open(REPO / "analysis" / "out" / "main" / "runs.jsonl"):
        r = json.loads(line)
        if r["scenario"] == "S4" and r.get("usable") and r["limit_s"] == 90 and key(r) in res:
            res[key(r)]["S4"] = r
    feats = {key(f): f for f in csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv"))}
    progs = [k for k in res if all(g in res[k] for g in GAPS)]
    groups = defaultdict(list)
    for k in progs:
        for g in ("all", "cond " + k[0], "lang " + k[3], "construct " + construct_group(feats.get(k, {}))):
            groups[g].append(k)
    rows = []
    for g in sorted(groups):
        ks = groups[g]
        row = {"group": g, "programs": len(ks)}
        for v in GAPS:
            h = sum(bool(res[k][v].get("no_return_90")) for k in ks)
            row[f"hang_{v}"] = f"{h} ({pct(h, len(ks))})"
        rows.append(row)
    write(REPO / "analysis" / "out" / "main" / "variants" / "s4_g025.csv", rows)
    print(f"programs with all gaps: {len(progs)} of {len(res)}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
