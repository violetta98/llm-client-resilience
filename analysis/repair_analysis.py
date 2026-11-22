"""Experiment B (protocol/REPAIR_ADDENDUM.md): did the revised solutions pass the tests their originals failed?

  python3 analysis/repair_analysis.py [--run repair] [--src main]

Reads  data/<run>/prompts/selection.csv, analysis/out/<src>/runs.jsonl, analysis/out/<run>/runs.jsonl,
       analysis/out/<run>/programs.csv, data/<run>/classify/features.csv (if present)
Writes analysis/out/<run>/
  repair_solutions.csv  one row per selected solution: failed tests, fixed, regressions, sibling and C2 references
  repair_summary.csv    fixed / regression / reference shares overall, per model, language and failure type,
                        with 95 % bootstrap intervals over tasks (2,000 resamples, seed 20261106)
  repair_test.csv       long data for the single registered test (analysis/repair_model.R)

A test is a (scenario, kind) pair; kinds: time (no return in 90 s or time-limit overrun), retries (excessive or rapid
retries in S7/S9), retry_after (S6a/S6b), unsafe_write (S8), silent (silent failure). Fixed: the revision is runnable
and none of the original's failed tests fails again. Regression: a test the original passed that the revision fails,
or an S0 outcome that was correct and no longer is.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
SEED, B = 20261106, 2000
KINDS = ("time", "retries", "retry_after", "unsafe_write", "silent")


def tests_failed(runs):
    out = set()
    for r in runs:
        sc = r["scenario"]
        if r.get("no_return") or r.get("overrun"):
            out.add((sc, "time"))
        if sc in ("S7", "S9") and (r.get("excessive_retries") or r.get("rapid_retries")):
            out.add((sc, "retries"))
        if sc in ("S6a", "S6b") and r.get("retry_after_violation"):
            out.add((sc, "retry_after"))
        if sc == "S8" and r.get("unsafe_write_retry"):
            out.add((sc, "unsafe_write"))
        if r.get("silent_failure"):
            out.add((sc, "silent"))
    return out


def s0_correct(runs):
    return any(r["scenario"] == "S0" and r.get("outcome") == "correct" for r in runs)


def load_runs(path):
    per = defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        if r.get("usable") and r["limit_s"] == 90:
            per[tuple(str(r[k]) for k in KEYS)].append(r)
    return per


def boot(rows, field, seed=SEED):
    """mean of field with a 95 % bootstrap interval over tasks"""
    vals = [r[field] for r in rows if r[field] is not None]
    if not vals:
        return "", "", "", 0
    by = defaultdict(list)
    for r in rows:
        if r[field] is not None:
            by[r["task"]].append(r[field])
    tasks = sorted(by)
    rng = random.Random(seed)
    est = []
    for _ in range(B):
        s = [x for t in (rng.choice(tasks) for _ in tasks) for x in by[t]]
        est.append(sum(s) / len(s))
    est.sort()
    return round(100 * sum(vals) / len(vals), 1), round(100 * est[int(0.025 * B)], 1), round(100 * est[int(0.975 * B) - 1], 1), len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="repair")
    ap.add_argument("--src", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    src = load_runs(REPO / "analysis" / "out" / a.src / "runs.jsonl")
    rep = load_runs(out / "runs.jsonl")
    progs = {tuple(p[k] for k in KEYS): p for p in csv.DictReader(open(out / "programs.csv"))}
    feats = {}
    fp = REPO / "data" / a.run / "classify" / "features.csv"
    if fp.exists():
        feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(fp))}
    sel = sorted({tuple(r[k] for k in KEYS) for r in csv.DictReader(open(REPO / "data" / a.run / "prompts" / "selection.csv"))})

    rows, long = [], []
    for k in sel:
      orig = tests_failed(src[k])
      for arm in ("R0", "R1"):  # R0: test report; R1: review request without report (D39)
        rk = (arm,) + k[1:]
        runnable = rk in rep and progs.get(rk, {}).get("category") == "ok"
        new = tests_failed(rep[rk]) if runnable else None
        fixed = int(runnable and not (orig & new))
        regress = None
        if runnable:
            regress = int(bool(new - orig) or (s0_correct(src[k]) and not s0_correct(rep[rk])))
        # references without feedback: the other C0 samples and the C2 samples of the same model, task, language
        sib, c2 = [], []
        for s in ("1", "2", "3"):
            for cond, lst in (("C0", sib), ("C2", c2)):
                kk = (cond,) + k[1:4] + (s,)
                if kk == k:
                    continue
                lst.append(int(kk in src and not (orig & tests_failed(src[kk]))))  # not runnable = not passing
        kinds = sorted({kind for _, kind in orig})
        row = {**dict(zip(KEYS, k)), "arm": arm, "still_failing_now": int(bool(orig)), "failed_tests": ";".join(f"{sc}:{kd}" for sc, kd in sorted(orig)),
               "kinds": ";".join(kinds), "category": progs.get(rk, {}).get("category", "missing"),
               "fixed": fixed, "regression": regress,
               "fixed_tests_share": (round(len(orig - new) / len(orig), 3) if runnable else 0.0) if orig else None,  # orig empty: no longer failing after D36
               "sibling_pass": round(sum(sib) / len(sib), 3) if sib else None,
               "c2_pass": round(sum(c2) / len(c2), 3) if c2 else None,
               "whole_call_deadline": feats[rk]["timeout_constructs"] if rk in feats else ""}
        for kd in KINDS:  # per kind: the original's failed tests of this kind
            ok_kind = {t for t in orig if t[1] == kd}
            if not ok_kind:
                row[f"fixed_{kd}"] = row[f"sibling_{kd}"] = None
                continue
            row[f"fixed_{kd}"] = int(runnable and not (ok_kind & new))
            sk = [int(kk in src and not (ok_kind & tests_failed(src[kk])))
                  for kk in (("C0",) + k[1:4] + (s,) for s in ("1", "2", "3")) if kk != k]
            row[f"sibling_{kd}"] = round(sum(sk) / len(sk), 3)
        rows.append(row)
        sid = "/".join(k[1:])
        if orig:  # solutions that no longer fail any selection test under the corrected measures are reported apart
            long.append({"solution": sid, "model": k[1], "task": k[2], "lang": k[3],
                         "arm": "feedback" if arm == "R0" else "review", "y": fixed})

    def write(name, rs):
        cols = list(dict.fromkeys(c for r in rs for c in r))
        with open(out / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, cols)
            w.writeheader()
            w.writerows(rs)

    rows_all = rows
    write("repair_solutions.csv", rows_all)
    write("repair_test.csv", long)
    summ = []
    rows = [r for r in rows_all if r["still_failing_now"]]
    groups = []
    for arm in ("R0", "R1"):
        ra = [r for r in rows if r["arm"] == arm]
        groups.append(("all", arm, ra))
        for m in sorted({r["model"] for r in ra}):
            groups.append(("model " + arm, m, [r for r in ra if r["model"] == m]))
        for l in ("python", "typescript", "java", "go"):
            groups.append(("lang " + arm, l, [r for r in ra if r["lang"] == l]))
        for kd in KINDS:
            groups.append(("kind " + arm, kd, [{**r, "fixed": r[f"fixed_{kd}"], "sibling_pass": r[f"sibling_{kd}"]}
                                              for r in ra if kd in r["kinds"].split(";")]))
    for g, v, rs in groups:
        if not rs:
            continue
        line = {"group": g, "value": v, "solutions": len(rs),
                "runnable": sum(r["category"] == "ok" for r in rs)}
        for f in ("fixed", "regression", "sibling_pass", "c2_pass"):
            p, lo, hi, n = boot(rs, f)
            line.update({f: p, f"{f}_lo": lo, f"{f}_hi": hi})
        summ.append(line)
        print(f"{g:6s} {v:22s} n={len(rs):4d} fixed {line['fixed']} ({line['fixed_lo']}-{line['fixed_hi']}) "
              f"regr {line['regression']} sib {line['sibling_pass']} c2 {line['c2_pass']}")
    write("repair_summary.csv", summ)


if __name__ == "__main__":
    main()
