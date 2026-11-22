"""Stage A, step 1: measures for every (program, scenario) computed from the raw run directories alone.

  python3 analysis/collect.py [--run main] [--jobs 4]

Reads   data/<run>/programs.jsonl, data/<run>/runs/..., data/<run>/rerun330/...
Writes  analysis/out/<run>/programs.csv     one row per generation (category, extraction)
        analysis/out/<run>/runs.jsonl       one row per (program, scenario, limit): every measure
        analysis/out/<run>/runs.csv         the same, scalar columns only
        analysis/out/<run>/coverage.json    expected vs present runs, harness failures

A run directory without result.json, or with harness_ok = false, is reported as missing / not ok and
excluded from the measures (it is repeated, DEVIATIONS D27-D28); nothing is imputed.
Runs without a call result and programs that fail at import in every run are not usable (`usable`, D33).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

DATA = REPO / "data"
KEYS = ("cond", "model", "task", "lang", "sample")
NORESULT = {"import_error", "warmup_no_return", "bad_result_json", None}
_EXP = {}


def exp(task):
    if task not in _EXP:
        _EXP[task] = yaml.safe_load((M.task_dir(task) / "expected.yaml").read_text())
    return _EXP[task]


def rel(p):
    return "/".join(str(p[k]) for k in KEYS)


def one(args):
    run, p, sc, top = args
    d = DATA / run / top / rel(p) / sc
    key = {k: p[k] for k in KEYS} | {"scenario": sc, "limit_s": 90 if top == "runs" else 330}
    if not (d / "result.json").exists():
        return key | {"present": False}
    try:
        row = M.compute(M.load_run(d), exp(p["task"]), cond=p["cond"])
    except Exception as e:  # noqa: BLE001
        return key | {"present": True, "harness_ok": False, "compute_error": repr(e)}
    row.pop("task", None), row.pop("cond", None), row.pop("lang", None)
    return key | {"present": True} | {k: v for k, v in row.items() if k != "scenario"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    out.mkdir(parents=True, exist_ok=True)
    progs = [json.loads(l) for l in open(DATA / a.run / "programs.jsonl")]
    with open(out / "programs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, [*KEYS, "category", "extraction"], extrasaction="ignore")
        w.writeheader()
        w.writerows(progs)
    jobs = []
    for p in progs:
        if p["category"] != "ok":
            continue
        for sc in exp(p["task"])["scenarios"]:
            jobs.append((a.run, p, sc, "runs"))
            if (DATA / a.run / "rerun330" / rel(p) / sc / "result.json").exists():
                jobs.append((a.run, p, sc, "rerun330"))
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one, jobs, chunksize=64))
    # D33: a run that produced no call result (import failed, warm-up never returned, unreadable result) has no
    # behaviour to measure; a program whose every 90 s run failed at import is its own category, import_error.
    by_prog = {}
    for r in rows:
        if r["limit_s"] == 90:
            by_prog.setdefault(rel(r), []).append(r.get("status"))
    imp = {k for k, v in by_prog.items() if v and all(s == "import_error" for s in v)}
    for r in rows:
        r["program_category"] = "import_error" if rel(r) in imp else "ok"
        r["usable"] = bool(r["present"] and r.get("harness_ok") and r.get("status") not in NORESULT
                           and r["program_category"] == "ok")
    for p in progs:
        if p["category"] == "ok" and rel(p) in imp:
            p["category"] = "import_error"
    with open(out / "programs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, [*KEYS, "category", "extraction"], extrasaction="ignore")
        w.writeheader()
        w.writerows(progs)
    with open(out / "runs.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    cols = []
    for r in rows:
        for k, v in r.items():
            if k not in cols and (v is None or isinstance(v, (bool, int, float, str))):
                cols.append(k)
    with open(out / "runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else int(v) if isinstance(v, bool) else v)
                        for k, v in r.items() if k in cols and not isinstance(v, (list, dict))})
    main90 = [r for r in rows if r["limit_s"] == 90]
    cov = {"programs": len(progs), "ok_programs": sum(p["category"] == "ok" for p in progs),
           "runs_expected": len(main90), "runs_present": sum(r["present"] for r in main90),
           "runs_harness_not_ok": sum(r["present"] and not r.get("harness_ok", False) for r in main90),
           "reruns_330_present": sum(r["limit_s"] == 330 and r["present"] for r in rows),
           "programs_import_error": len(imp),
           "runs_no_result_in_runnable_programs": sum(r["limit_s"] == 90 and r["program_category"] == "ok" and r["present"]
                                                      and r.get("harness_ok") and not r["usable"] for r in rows),
           "runs_usable_90": sum(r["limit_s"] == 90 and r["usable"] for r in rows)}
    (out / "coverage.json").write_text(json.dumps(cov, indent=1) + "\n")
    print(json.dumps(cov, indent=1))


if __name__ == "__main__":
    main()
