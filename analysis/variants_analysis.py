"""S4 at other trickle gaps (D38) and the held-out check of the revisions (D39).

  python3 analysis/variants_analysis.py

Main run (data/main-variants): for the 25 % sample of runnable programs, the share that does not return within 90 s
in S4 at the registered gap (2 s, from analysis/out/main/runs.jsonl) and in the variants S4g05 (0.5 s), S4g5 (5 s)
and S4h (headers, then no body for an hour), overall, per condition, per language and per kind of timeout construct
(whole-call deadline / per-read or until-headers only / none; classifier of D34/D38). Only runs with harness_ok.
For B and H tasks also the share that overruns its time limit.

Revisions (data/repair-variants): for revisions of solutions whose original hung or overran in S4, the share that
passes S4 at 2 s (from analysis/out/repair/runs.jsonl) and, among those, the share that also passes at 0.5 s, per
arm (R0 feedback, R1 review). Pass = returns within 90 s and, for B/H tasks, within the time limit.

Control S0slow (D45): S0 with every response delayed by 750 ms, within the p99 800 ms of the API excerpts. Share
with the correct result (and no time-limit overrun) at S0 and S0slow, for the main sample and the revisions.

Writes analysis/out/main/variants/s4_gaps.csv, s4_gaps_by_construct.csv, s4_gaps_by_lang.csv, revisions_heldout.csv, revisions_g5h.csv,
s0slow.csv.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
import sys  # noqa: E402
sys.path.insert(0, str(REPO / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402

GAPS = [("S4g05", "0.5 s"), ("S4", "2 s (registered)"), ("S4g5", "5 s"), ("S4h", "headers, no body")]


def key(r):
    return tuple(str(r[k]) for k in KEYS)


def variant(r):
    return Path(r["dir"]).name if r.get("dir") else r["scenario"]


def pct(a, n):
    return round(100 * a / n, 1) if n else ""


def write(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def construct_group(feat):
    cons = {c.strip() for c in (feat.get("timeout_constructs") or "").split(";") if c.strip()}
    if cons & WHOLE:
        return "whole-call deadline"
    return "per-read or until headers only" if cons else "none"


def main():
    out = REPO / "analysis" / "out" / "main" / "variants"
    feats = {key(f): f for f in csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv"))}
    res = defaultdict(dict)  # program -> variant -> row
    for line in open(REPO / "data" / "main-variants" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("harness_ok") and r.get("limit_s", 90) == 90:
            res[key(r)][variant(r)] = r
    sample = set(res)
    for line in open(REPO / "analysis" / "out" / "main" / "runs.jsonl"):
        r = json.loads(line)
        if r["scenario"] == "S4" and r.get("usable") and r["limit_s"] == 90 and key(r) in sample:
            res[key(r)]["S4"] = r
    progs = [k for k in sample if all(g in res[k] for g, _ in GAPS)]

    def rows_for(group_fn, label):
        agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # group -> gap -> [n, hang, n_bh, overrun]
        for k in progs:
            for g, _ in GAPS:
                r = res[k][g]
                for grp in group_fn(k):
                    a = agg[grp][g]
                    a[0] += 1
                    a[1] += int(bool(r.get("no_return_90")))
                    if k[2][0] in "BH":
                        a[2] += 1
                        a[3] += int(bool(r.get("overrun")) or bool(r.get("no_return_90")))
        rows = []
        for grp in sorted(agg):
            row = {label: grp, "programs": agg[grp]["S4"][0]}
            for g, name in GAPS:
                n, h, nb, o = agg[grp][g]
                row[f"hang_{g}"] = pct(h, n)
                row[f"overrun_BH_{g}"] = pct(o, nb)
            rows.append(row)
        return rows

    write(out / "s4_gaps.csv", rows_for(lambda k: ["all", "cond " + k[0], "tasks " + ("B/H" if k[2][0] in "BH" else "R/W")], "group"))
    write(out / "s4_gaps_by_lang.csv", rows_for(lambda k: [k[3]], "lang"))
    write(out / "s4_gaps_by_construct.csv",
          rows_for(lambda k: [construct_group(feats.get(k, {}))] if k in feats else [], "construct"))

    # revisions: held-out gap
    rep2 = {}
    for line in open(REPO / "analysis" / "out" / "repair" / "runs.jsonl"):
        r = json.loads(line)
        if r["scenario"] == "S4" and r.get("usable") and r["limit_s"] == 90:
            rep2[key(r)] = r
    rep05 = {}
    for line in open(REPO / "data" / "repair-variants" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("harness_ok") and r.get("limit_s", 90) == 90 and variant(r) == "S4g05":
            rep05[key(r)] = r

    def passes(r, task):
        return not r.get("no_return_90") and not (task[0] in "BH" and r.get("overrun"))
    rows = []
    for arm in ("R0", "R1"):
        ks = [k for k in rep05 if k[0] == arm and k in rep2]
        p2 = [k for k in ks if passes(rep2[k], k[2])]
        both = [k for k in p2 if passes(rep05[k], k[2])]
        rows.append({"arm": arm, "revisions": len(ks), "pass_2s": len(p2), "pass_2s_pct": pct(len(p2), len(ks)),
                     "also_pass_0_5s": len(both), "also_pass_0_5s_pct_of_pass_2s": pct(len(both), len(p2)),
                     "pass_0_5s_pct": pct(sum(passes(rep05[k], k[2]) for k in ks), len(ks))})
    write(out / "revisions_heldout.csv", rows)

    # revisions at 5 s and headers-only (D61, run repair-g5h)
    g5h = defaultdict(dict)
    for line in open(REPO / "data" / "repair-g5h" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("harness_ok") and r.get("limit_s", 90) == 90:
            g5h[variant(r)][key(r)] = r
    rows = []
    for arm in ("R0", "R1"):
        ks = [k for k in rep2 if k[0] == arm and k in rep05 and all(k in g5h[v] for v in ("S4g5", "S4h"))]
        row = {"arm": arm, "revisions": len(ks)}
        for v, src in (("0_5s", rep05), ("2s", rep2), ("5s", g5h["S4g5"]), ("headers", g5h["S4h"])):
            row[f"pass_{v}"] = sum(passes(src[k], k[2]) for k in ks)
            row[f"pass_{v}_pct"] = pct(row[f"pass_{v}"], len(ks))
        allp = sum(all(passes(s[k], k[2]) for s in (rep05, rep2, g5h["S4g5"], g5h["S4h"])) for k in ks)
        row["pass_all4"], row["pass_all4_pct"] = allp, pct(allp, len(ks))
        rows.append(row)
    write(out / "revisions_g5h.csv", rows)

    # S0slow (D45)
    def ok(r):
        return r.get("outcome") == "correct" and not r.get("no_return_90") and not r.get("overrun")
    main_s0 = {}
    for line in open(REPO / "analysis" / "out" / "main" / "runs.jsonl"):
        r = json.loads(line)
        if r["scenario"] == "S0" and r.get("usable") and r["limit_s"] == 90:
            main_s0[key(r)] = r
    rep_s0 = {}
    for line in open(REPO / "analysis" / "out" / "repair" / "runs.jsonl"):
        r = json.loads(line)
        if r["scenario"] == "S0" and r.get("usable") and r["limit_s"] == 90:
            rep_s0[key(r)] = r

    def slow(path):
        d = {}
        for line in open(path):
            r = json.loads(line)
            if r.get("harness_ok") and r.get("limit_s", 90) == 90 and variant(r) == "S0slow":
                d[key(r)] = r
        return d
    slow_main, slow_rep = slow(REPO / "data" / "main-variants" / "measures.jsonl"), slow(REPO / "data" / "repair-variants" / "measures.jsonl")
    rows = []
    for grp, sl, s0, sel in [("main all", slow_main, main_s0, lambda k: True),
                             ("main C0", slow_main, main_s0, lambda k: k[0] == "C0"),
                             ("main C2", slow_main, main_s0, lambda k: k[0] == "C2"),
                             ("revisions R0", slow_rep, rep_s0, lambda k: k[0] == "R0"),
                             ("revisions R1", slow_rep, rep_s0, lambda k: k[0] == "R1"),
                             ("revisions R0 passing S4 2 s", slow_rep, rep_s0, lambda k: k[0] == "R0" and k in rep2 and passes(rep2[k], k[2])),
                             ("revisions R1 passing S4 2 s", slow_rep, rep_s0, lambda k: k[0] == "R1" and k in rep2 and passes(rep2[k], k[2]))]:
        ks = [k for k in sl if k in s0 and sel(k)]
        rows.append({"group": grp, "programs": len(ks), "correct_S0_pct": pct(sum(ok(s0[k]) for k in ks), len(ks)),
                     "correct_S0slow_pct": pct(sum(ok(sl[k]) for k in ks), len(ks)),
                     "correct_S0_not_S0slow": sum(ok(s0[k]) and not ok(sl[k]) for k in ks)})
    write(out / "s0slow.csv", rows)
    for f in ("s4_gaps.csv", "s4_gaps_by_construct.csv", "s4_gaps_by_lang.csv", "revisions_heldout.csv", "revisions_g5h.csv", "s0slow.csv"):
        print("==", f)
        print((out / f).read_text())


if __name__ == "__main__":
    main()
