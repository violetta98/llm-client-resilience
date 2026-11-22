"""Stage A, RQ3: generated solutions vs the default call of the library they use (Table IX baselines).

  python3 analysis/vs_baseline.py [--run main]

Reads  analysis/out/<run>/runs.jsonl, data/<run>/classify/features.csv, analysis/out/baselines_raw.json (E4)
Writes analysis/out/<run>/rq3_vs_baseline.csv         match / better / worse / mixed per model x language x scenario
       analysis/out/<run>/rq3_vs_baseline_runs.csv    one row per compared run
       analysis/out/<run>/rq3_harmful_source.csv      harmful retries: library default vs generated code

Operationalization (DEVIATIONS D30; fixed before this script was first run on main data):
- A solution is compared when its import rules give exactly one HTTP library that has a baseline (net/http -> net-http);
  the baseline program is the library's GET or POST call, chosen by the task's faulted request.
- Each 90 s run and its baseline run in the same scenario are scored on two binary dimensions:
  no return in 90 s, and a harmful retry (rapid retries, Retry-After violation, excessive retries, unsafe write retry,
  synchronized retries). Equal on both -> match; never higher and lower on at least one -> better; never lower and
  higher on at least one -> worse; otherwise mixed.
- A harmful retry in a solution is attributed to the library default when the baseline of that library shows the same
  flag in that scenario and the solution has no own retry (retry mechanism none or library_builtin only); to generated
  code when the solution has a hand loop or a retry library; otherwise unattributed.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
HARM = ("rapid_retries", "retry_after_violation", "excessive_retries", "unsafe_write_retry", "sync_retries")
LIB_ALIAS = {"net/http": "net-http"}


def harm(r):
    return {h for h in HARM if r.get(h)}


def score(sol, base):
    a = (int(bool(sol.get("no_return_90"))), int(bool(harm(sol))))
    b = (int(bool(base.get("no_return_90"))), int(bool(harm(base))))
    if a == b:
        return "match"
    if all(x <= y for x, y in zip(a, b)):
        return "better"
    if all(x >= y for x, y in zip(a, b)):
        return "worse"
    return "mixed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    base = json.load(open(REPO / "analysis" / "out" / "baselines_raw.json"))
    libs_with_base = {k.split("|")[0] for k in base}
    feats = {tuple(r[k] for k in KEYS): r for r in csv.DictReader(open(REPO / "data" / a.run / "classify" / "features.csv"))}
    call = {}
    runs_rows, agg, src = [], defaultdict(Counter), Counter()
    not_comparable = Counter()
    cf = Counter()
    for line in open(out / "runs.jsonl"):
        r = json.loads(line)
        if r["limit_s"] != 90 or not r.get("usable"):
            continue
        k = tuple(str(r[x]) for x in KEYS)
        f = feats.get(k)
        libs = [LIB_ALIAS.get(x, x) for x in (f["library"].split(";") if f and f["library"] else [])]
        if len(libs) != 1 or libs[0] not in libs_with_base:
            not_comparable[(r["model"], r["lang"])] += 1
            continue
        t = r["task"]
        if t not in call:
            fr = yaml.safe_load((REPO / "tasks" / t / "expected.yaml").read_text()).get("faulted_request", "")
            call[t] = "post" if "POST" in str(fr).upper().split() else "get"  # PUT/DELETE tasks: GET baseline (D33)
        b = base.get(f"{libs[0]}|{call[t]}|{r['scenario']}")
        if b is None:
            not_comparable[(r["model"], r["lang"])] += 1
            continue
        s = score(r, b)
        own = set(f["retry_mechanism"].split(";")) & {"hand_loop", "retry_library"}
        runs_rows.append({**{x: r[x] for x in KEYS}, "scenario": r["scenario"], "library": libs[0], "call": call[t],
                          "retry_mechanism": f["retry_mechanism"], "sol_no_return_90": int(bool(r.get("no_return_90"))),
                          "base_no_return_90": int(bool(b.get("no_return_90"))),
                          "sol_harm": ";".join(sorted(harm(r))), "base_harm": ";".join(sorted(harm(b))), "score": s})
        agg[(r["model"], r["lang"], r["scenario"])][s] += 1
        agg[(r["model"], "all", "all")][s] += 1
        agg[("all", "all", "all")][s] += 1
        for h in harm(r):
            # counterfactual: would the library default alone raise the same flag in the same scenario?
            cf[("own retries" if own else "no own retries", "flags")] += 1
            cf[("own retries" if own else "no own retries", "default raises the same flag")] += int(h in harm(b))
            if h in harm(b) and not own:
                who = "library default"
            elif own:
                who = "generated code"
            else:
                who = "unattributed"
            src[(r["model"], h, who)] += 1
            src[("all", h, who)] += 1
    with open(out / "rq3_counterfactual.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["solutions", "count", "flags"])
        for (grp, what), n in sorted(cf.items()):
            w.writerow([grp, what, n])
    print("counterfactual:", dict(cf))
    with open(out / "rq3_vs_baseline_runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(runs_rows[0]))
        w.writeheader()
        w.writerows(runs_rows)
    with open(out / "rq3_vs_baseline.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "lang", "scenario", "n", "match", "better", "worse", "mixed", "not_comparable_runs"])
        for (m, lg, sc), c in sorted(agg.items()):
            nc = sum(v for (mm, ll), v in not_comparable.items() if (m == "all" or mm == m) and (lg == "all" or ll == lg)) \
                if sc == "all" else ""
            w.writerow([m, lg, sc, sum(c.values()), c["match"], c["better"], c["worse"], c["mixed"], nc])
    with open(out / "rq3_harmful_source.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "flag", "source", "runs"])
        for (m, h, who), n in sorted(src.items()):
            w.writerow([m, h, who, n])
    print("compared runs:", len(runs_rows), "not comparable:", sum(not_comparable.values()))
    print("all:", dict(agg[("all", "all", "all")]))
    print({(h, who): n for (m, h, who), n in src.items() if m == "all"})


if __name__ == "__main__":
    main()
