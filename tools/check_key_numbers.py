"""Recompute the article's key numbers from the released data in under a minute (standard library only, no Docker).

  python3 tools/check_key_numbers.py

Reads the summary data of the repository (data/runs.csv, data/features.csv, data/programs.csv, data/repair/,
data/docs/, data/tables/); in the working repository the same files are read from analysis/out/. Prints each number
next to the value printed in the article and exits with status 1 if any differs. The full pipeline that produces these
files from the raw run records is `make analyze` (README.md, Reproducing the paper).
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402

PUBLIC = {"runs": "data/runs.csv", "features": "data/features.csv", "programs": "data/programs.csv",
          "repair": "data/repair/repair_summary.csv", "docs": "data/docs/summary.csv",
          "linters": "data/tables/table11_linters.csv"}
WORKING = {"runs": "analysis/out/main/runs.csv", "features": "data/main/classify/features.csv",
           "programs": "analysis/out/main/programs.csv", "repair": "analysis/out/repair/repair_summary.csv",
           "docs": "analysis/out/docs/summary.csv", "linters": "analysis/out/main/paper/table11_linters.csv"}
KEYS = ("cond", "model", "task", "lang", "sample")


def path(name):
    p = ROOT / PUBLIC[name]
    return p if p.exists() else ROOT / WORKING[name]


def rows(name):
    with open(path(name), newline="") as fh:
        return list(csv.DictReader(fh))


def pct(a, n):
    return round(100 * a / n, 1)


def flag(v):
    return v not in ("", "0", "False", "false", "None")


def main():
    runs = defaultdict(dict)
    for r in rows("runs"):
        if r["limit_s"] == "90" and flag(r["usable"]):
            runs[tuple(r[k] for k in KEYS)][r["scenario"]] = r
    feats = {tuple(r[k] for k in KEYS): r for r in rows("features")}
    checks = []

    def check(label, value, expected):
        checks.append((label, value, expected, value == expected))

    check("Runnable solutions", sum(1 for r in rows("programs") if r["category"] == "ok"), 2531)

    s4 = {k: flag(v["S4"]["no_return_90"]) for k, v in runs.items() if "S4" in v}
    c0 = [h for k, h in s4.items() if k[0] == "C0"]
    check("S4 hang, baseline (%)", pct(sum(c0), len(c0)), 34.8)

    def split(keep):
        a = {"whole": [0, 0], "perread": [0, 0]}
        for k, h in s4.items():
            if k not in feats or not keep(k):
                continue
            t = {x for x in feats[k]["timeout_constructs"].split(";") if x}
            g = "whole" if t & WHOLE else "perread" if t else None
            if g:
                a[g][0] += h
                a[g][1] += 1
        return a
    a = split(lambda k: k[3] != "java")
    check("S4 hang without Java, per-read only (%)", pct(*a["perread"]), 67.1)
    check("S4 hang without Java, whole-call deadline (%)", pct(*a["whole"]), 2.6)
    a = split(lambda k: True)
    check("S4 hang, per-read only, all languages (%)", pct(*a["perread"]), 73.7)
    check("S4 hang, whole-call deadline, all languages (%)", pct(*a["whole"]), 2.2)

    for cond, exp in (("C0", 48.8), ("C2", 32.4)):
        v = [h for k, h in s4.items() if k[0] == cond and k[2][0] in "RW"]
        check(f"S4 hang in tasks without a limit, {cond} (%)", pct(sum(v), len(v)), exp)

    s7 = {k: flag(v["S7"]["excessive_retries"]) for k, v in runs.items() if "S7" in v and v["S7"]["excessive_retries"] != ""}
    v = [x for k, x in s7.items() if k[0] == "C0"]
    check("S7 excessive retries, baseline (%)", pct(sum(v), len(v)), 10.2)
    v = [x for k, x in s7.items() if k[0] == "C0" and k[2] != "B2"]
    check("S7 excessive retries, baseline, without B2 (%)", pct(sum(v), len(v)), 6.8)

    lint = {r["tool"]: r for r in rows("linters") if r.get("model", "all") == "all"}
    check("Bandit B113: failing Python solutions flagged", f'{lint["bandit_B113"]["failing_flagged"]} of {lint["bandit_B113"]["failing"]}', "5 of 440")

    rep = {r["value"]: r for r in rows("repair") if r["group"] == "all"}
    check("Repair with the test report: fixed (%)", float(rep["R0"]["fixed"]), 79.3)
    check("Repair after a review request: fixed (%)", float(rep["R1"]["fixed"]), 29.7)
    check("Repair: failing solutions", int(rep["R0"]["solutions"]), 653)

    docs = rows("docs")
    miss = sum(1 for r in docs if flag(r["S4_hang"]) or (r["S4_s"] and float(r["S4_s"]) > 10.25))
    check("Documentation examples missing a 10 s deadline in S4", f"{miss} of {len(docs)}", "14 of 19")

    w = max(len(c[0]) for c in checks)
    for label, value, expected, ok in checks:
        print(f"{label:<{w}}  {str(value):>10}  article {str(expected):>10}  {'ok' if ok else 'DIFFERS'}")
    bad = sum(not c[3] for c in checks)
    print(f"\n{len(checks) - bad} of {len(checks)} numbers match the article.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
