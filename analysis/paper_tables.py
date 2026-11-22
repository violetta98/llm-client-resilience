"""Tables of the paper, as CSV, from the outputs of `make analyze` (no new analysis).

  python3 analysis/paper_tables.py [--run main] [--out analysis/out/main/paper] [--print]

Reads  analysis/out/<run>/runs.jsonl, primary.csv, primary_cells.csv, primary_contrasts.csv, rq1_s4_mechanism.csv,
       rq5_linters.csv, analysis/out/table_ix.csv
Writes <out>/table07_stalls.csv           Table 7: no return in 90 s in S1-S4 and time-limit overrun, per LLM,
                                          per language, overall and per condition (share of solutions, 95 % bootstrap over tasks)
       <out>/table09_library_defaults.csv Table 9: library defaults in every scenario (copy of table_ix.csv)
       <out>/table10_primary.csv         Table 10: primary outcomes per LLM and condition, Family A contrasts
       <out>/table08_retries.csv        Table 8: harmful retries in the scenarios where each is defined, C0 vs C2
       <out>/table12_s4_mechanism.csv    Table 12: S4 by kind of timeout construct (exploratory, D32)
       <out>/table11_linters.csv         Table 11: linters vs fault injection, all LLMs
Same rules as the other scripts: 90 s runs with `usable` only; bootstrap over tasks, 2,000 resamples, seed 20261106.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

from descriptive import LANGS, MODELS, STALL, boot_tasks, share

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
RETRY_ROWS = [("rapid_retries", "S9"), ("rapid_retries", "S7"), ("excessive_retries", "S9"),
              ("excessive_retries", "S7"), ("retry_after_violation", "S6a"), ("retry_after_violation", "S6b"),
              ("sync_retries", "S7"), ("unsafe_write_retry", "S8"), ("late_requests", "all")]


def cell(items):
    """items: [(task, 0/1)] -> share, lo, hi, n, events"""
    v = [x for _, x in items]
    if not v:
        return {"n": 0, "events": 0, "share": "", "lo": "", "hi": ""}
    lo, hi = boot_tasks(items, share)
    return {"n": len(v), "events": sum(v), "share": round(share(v), 6), "lo": round(lo, 6), "hi": round(hi, 6)}


def write(path, rows):
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--out", default="")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()
    src = REPO / "analysis" / "out" / a.run
    out = Path(a.out) if a.out else src / "paper"
    out.mkdir(parents=True, exist_ok=True)

    runs = [json.loads(x) for x in open(src / "runs.jsonl")]
    runs = [r for r in runs if r["limit_s"] == 90 and r.get("usable")]
    sol = defaultdict(dict)  # key -> scenario -> run
    for r in runs:
        sol[tuple(str(r[k]) for k in KEYS)][r["scenario"]] = r
    overrun = {}
    for r in csv.DictReader(open(src / "primary.csv")):
        if r["outcome"] == "overrun" and r["y"] != "NA":
            overrun[tuple(r[k] for k in KEYS)] = int(r["y"])

    # Table 7
    groups = [("model", m) for m in MODELS] + [("lang", lg) for lg in LANGS] + [("all", "all"), ("cond", "C0"),
                                                                                 ("cond", "C2")]
    t8 = []
    for kind, val in groups:
        keys = [k for k in sol if kind == "all" or (kind == "model" and k[1] == val) or (kind == "lang" and k[3] == val)
                or (kind == "cond" and k[0] == val)]
        row = {"group": kind, "value": val, "solutions": len(keys)}
        for sc in STALL:
            c = cell([(k[2], int(bool(sol[k][sc]["no_return_90"]))) for k in keys if sc in sol[k]])
            row |= {f"{sc}_{f}": c[f] for f in ("share", "lo", "hi")}
        c = cell([(k[2], int(any(bool(sol[k][s]["no_return_90"]) for s in STALL if s in sol[k]))) for k in keys])
        row |= {f"any_S1_S4_{f}": c[f] for f in ("events", "share", "lo", "hi")}
        c = cell([(k[2], overrun[k]) for k in keys if k in overrun])
        row |= {"overrun_n": c["n"]} | {f"overrun_{f}": c[f] for f in ("events", "share", "lo", "hi")}
        t8.append(row)
    write(out / "table07_stalls.csv", t8)

    shutil.copyfile(REPO / "analysis" / "out" / "table_ix.csv", out / "table09_library_defaults.csv")

    # Table 10
    cells = {(r["outcome"], r["model"], r["cond"]): r for r in csv.DictReader(open(src / "primary_cells.csv"))}
    con = {(r["outcome"], r["contrast"]): r for r in csv.DictReader(open(src / "primary_contrasts.csv"))}
    t10 = []
    for oc in ("s3_no_return", "overrun", "unsafe_write"):
        for m in MODELS:
            c0, c2 = cells.get((oc, m, "C0")), cells.get((oc, m, "C2"))
            k = con.get((oc, f"{m}: C2 vs C0"), {})
            t10.append({"outcome": oc, "model": m,
                        "C0_events": c0 and c0["events"], "C0_n": c0 and c0["n"],
                        "C2_events": c2 and c2["events"], "C2_n": c2 and c2["n"],
                        "estimate": k.get("estimate"), "lo": k.get("lo"), "hi": k.get("hi"), "scale": k.get("scale"),
                        "test": k.get("test"), "p": k.get("p"), "p_holm": k.get("p_holm")})
        for (o, ct), k in con.items():
            if o == oc and k["family"] == "B":
                t10.append({"outcome": oc, "model": ct, "estimate": k["estimate"], "lo": k["lo"], "hi": k["hi"],
                            "scale": k["scale"], "test": k["test"], "p": k["p"], "p_holm": k["p_holm"]})
    write(out / "table10_primary.csv", t10)

    # Table 8
    t11 = []
    for meas, sc in RETRY_ROWS:
        row = {"measure": meas, "scenario": sc}
        for cond in ("C0", "C2"):
            if sc == "all":  # late requests: any scenario, per solution
                items = [(k[2], int(any(bool(r.get(meas)) for r in sol[k].values())))
                         for k in sol if k[0] == cond and any(r.get(meas) is not None for r in sol[k].values())]
            else:
                items = [(k[2], int(bool(sol[k][sc][meas]))) for k in sol
                         if k[0] == cond and sc in sol[k] and sol[k][sc].get(meas) is not None]
            c = cell(items)
            row |= {f"{cond}_{f}": c[f] for f in ("n", "events", "share", "lo", "hi")}
        t11.append(row)
    write(out / "table08_retries.csv", t11)

    shutil.copyfile(src / "rq1_s4_mechanism.csv", out / "table12_s4_mechanism.csv")
    write(out / "table11_linters.csv", [r for r in csv.DictReader(open(src / "rq5_linters.csv")) if r["model"] == "all"])

    if a.print:
        for f in sorted(out.glob("table*.csv")):
            if f.name.startswith("table10_"):
                continue
            print(f"== {f.name}")
            print(f.read_text())


if __name__ == "__main__":
    main()
