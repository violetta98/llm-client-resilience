"""Analyses requested by the round-8 reviews (D50, post hoc, found in review). Existing data only; no new runs.

  python3 analysis/review_round8.py

Writes analysis/out/main/review/:
  task_level.csv      per task (16 main + 4 held-out): S4 hang and S7 excessive-retry rates by condition, and the
                      exact one-sided sign tests over tasks for "C2 lowers S4 hangs in tasks without a stated limit"
                      and "C2 raises S7 excessive retries" (ties dropped);
  strata.csv          S4 hangs by task group and without Java; S7 excessive retries without the polling task B2;
                      per-call share of S7 logical calls with more than ten attempts (instead of any of ten);
  h1_by_lang.csv      held-out H1 (S4 hang by whole-call deadline) within each language, and the marginal odds ratios
                      of H2 and H3 from the 2x2 tables;
  s4_writes.csv       duplicate state changes in S4 (W1, W2, B4): the mock processes every trickled write before it
                      sends the headers, so a client that times out and repeats the write can duplicate it.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

OUT = REPO / "analysis" / "out" / "main" / "review"
KEYS = ("cond", "model", "task", "lang", "sample")
GROUP = {"R": "read", "W": "write", "B": "background", "H": "handler"}
NO_LIMIT = {"R1", "R2", "R3", "R4", "R5", "W1", "W2", "W3", "W4", "R6", "W5"}


def sign_p(pos: int, neg: int) -> float:
    n = pos + neg
    return sum(comb(n, k) for k in range(pos, n + 1)) / 2 ** n


def write(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def main():
    runs = [json.loads(l) for l in open(REPO / "analysis/out/main/runs.jsonl")]
    runs = [r for r in runs if r.get("usable") and r["limit_s"] == 90]
    by = defaultdict(lambda: [0, 0])  # (scenario, task, cond) -> [events, n]
    for r in runs:
        if r["scenario"] == "S4":
            v = by[("S4", r["task"], r["cond"])]
            v[0] += bool(r["no_return_90"]); v[1] += 1
        if r["scenario"] == "S7" and r["excessive_retries"] is not None:
            v = by[("S7", r["task"], r["cond"])]
            v[0] += bool(r["excessive_retries"]); v[1] += 1
    for r in csv.DictReader(open(REPO / "analysis/out/confirm/confirm_h.csv")):
        sc = {"H2": "S4", "H3": "S7"}.get(r["hyp"])
        if sc:
            v = by[(sc, r["task"], r["cond"])]
            v[0] += int(r["y"]); v[1] += 1
    tasks = sorted({k[1] for k in by})
    rows, sign = [], {"S4": [0, 0, 0], "S7": [0, 0, 0]}
    for t in tasks:
        row = {"task": t, "held_out": t in ("R6", "W5", "B5", "H4")}
        for sc in ("S4", "S7"):
            a, b = by[(sc, t, "C0")], by[(sc, t, "C2")]
            p0, p2 = pct(*a), pct(*b)
            row[f"{sc}_C0"], row[f"{sc}_C2"] = p0, p2
            if sc == "S4" and t not in NO_LIMIT:
                continue
            s = sign[sc]
            want_down = sc == "S4"
            if p0 == p2:
                s[2] += 1
            elif (p2 < p0) == want_down:
                s[0] += 1
            else:
                s[1] += 1
        rows.append(row)
    for sc, (pos, neg, tie) in sign.items():
        rows.append({"task": f"sign test {sc} ({'C2 lower, tasks without a stated limit' if sc == 'S4' else 'C2 higher'})",
                     "held_out": "", "S4_C0": pos, "S4_C2": neg, "S7_C0": tie, "S7_C2": round(sign_p(pos, neg), 5)})
    write("task_level.csv", rows)
    print("sign tests (in direction, against, ties, one-sided p):",
          {sc: (*v, round(sign_p(v[0], v[1]), 5)) for sc, v in sign.items()})

    # strata
    st = []
    def add(name, pred, sc, field):
        for cond in ("C0", "C2"):
            sel = [r for r in runs if r["scenario"] == sc and r["cond"] == cond and pred(r) and r[field] is not None]
            st.append({"measure": f"{sc} {field}", "stratum": name, "cond": cond, "n": len(sel),
                       "pct": pct(sum(bool(r[field]) for r in sel), len(sel))})
    for g, name in GROUP.items():
        add(name, lambda r, g=g: r["task"].startswith(g), "S4", "no_return_90")
    add("without Java", lambda r: r["lang"] != "java", "S4", "no_return_90")
    add("Java only", lambda r: r["lang"] == "java", "S4", "no_return_90")
    add("all", lambda r: True, "S7", "excessive_retries")
    add("without B2", lambda r: r["task"] != "B2", "S7", "excessive_retries")
    for cond in ("C0", "C2"):
        shares = []
        for r in runs:
            if r["scenario"] == "S7" and r["cond"] == cond and r["excessive_retries"] is not None:
                a = r.get("attempts_during_outage") or {}
                if a:
                    shares.append(sum(v > 10 for v in a.values()) / len(a))
        st.append({"measure": "S7 share of logical calls with >10 attempts (mean over solutions)", "stratum": "all",
                   "cond": cond, "n": len(shares), "pct": round(100 * sum(shares) / len(shares), 1)})
    write("strata.csv", st)
    for s in st:
        print(s)

    # held-out H1 within language; marginal ORs
    h = [r for r in csv.DictReader(open(REPO / "analysis/out/confirm/confirm_h.csv"))]
    hl = []
    for lang in ("python", "typescript", "java", "go"):
        sel = [r for r in h if r["hyp"] == "H1" and r["lang"] == lang]
        no = [r for r in sel if r["x"] == "1"]
        yes = [r for r in sel if r["x"] == "0"]
        hl.append({"what": f"H1 {lang}", "a": f"{sum(int(r['y']) for r in no)}/{len(no)} hang without deadline",
                   "b": f"{sum(int(r['y']) for r in yes)}/{len(yes)} hang with deadline"})
    for hyp in ("H2", "H3"):
        sel = [r for r in h if r["hyp"] == hyp]
        c = {(cc, y): sum(1 for r in sel if r["c2"] == cc and r["y"] == y) for cc in "01" for y in "01"}
        orr = (c[("1", "1")] * c[("0", "0")]) / max(1, c[("1", "0")] * c[("0", "1")])
        hl.append({"what": f"{hyp} marginal OR (C2 vs C0)", "a": round(orr, 2), "b": json.dumps({f"{k[0]}{k[1]}": v for k, v in c.items()})})
    write("h1_by_lang.csv", hl)
    for x in hl:
        print(x)

    # duplicate writes in S4
    dw = defaultdict(lambda: [0, 0])
    for r in runs:
        if r["scenario"] != "S4" or r["task"] not in ("W1", "W2", "B4"):
            continue
        k = tuple(str(r[x]) for x in KEYS)
        run = M.load_run(REPO / "data" / "main" / "runs" / Path(*k) / "S4")
        e = [x for x in run["effects"] if x.get("role") == "dep"]
        if r["task"] == "W1":
            per = defaultdict(int)
            for x in e:
                if x["kind"] == "payment_created":
                    per[x["detail"]["order_id"]] += 1
            dup = any(v > 1 for v in per.values())
        elif r["task"] == "W2":
            dup = sum(1 for x in e if x["kind"] == "sms_sent") > 1
        else:
            per = defaultdict(int)
            for x in e:
                if x["kind"] == "delivery_accepted":
                    per[x["key"]] += 1
            dup = any(v > 1 for v in per.values())
        v = dw[(r["cond"], r["task"])]
        v[0] += dup; v[1] += 1
    rows = [{"cond": c, "task": t, "duplicates": v[0], "solutions": v[1], "pct": pct(*v)} for (c, t), v in sorted(dw.items())]
    write("s4_writes.csv", rows)
    for x in rows:
        print(x)


if __name__ == "__main__":
    main()
