"""Internal AI review, round 12 (D56): free analyses on existing data, exploratory.

  python3 analysis/review_round12.py   -> analysis/out/review12/summary.json
1. JDK 26 hybrid (Java S4 runs from main-jdk26, everything else JDK 25): time-limit overrun per condition and model;
   S4 hangs per condition (all tasks, R/W); the construct split (whole-call deadline vs per-read group); 95 %
   bootstrap intervals over tasks (2,000 resamples, seed 20261121) for the baseline rows.
2. Rapid retries in S9 (main run): among flagged runs, how many show growing delays (a later gap of at least 200 ms)
   and how many are tight loops (at least eight attempts, every gap under 100 ms); flags with a 20 ms instead of 5 ms
   SYN merge window for Java.
3. Test-specification S4 row on its stated assertion: return within the stated limit (10 s if none) plus 0.25 s.
4. S0slow: the 28 solutions correct in S0 but not at 750 ms, split into allowed degraded results within the limit and
   results the task does not allow.
5. Retry mechanism: overlap of hand-written loops and retry libraries.
6. Ablation: C2c minus C2 in R6/W5 on JDK 25 and JDK 26, bootstrap over models (2,000 resamples, seed 20261121).
7. Costs: repair run and cross-model reviews.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402
from s4_mechanism import WHOLE  # noqa: E402

OUT = REPO / "analysis" / "out" / "review12"
KEYS = ("cond", "model", "task", "lang", "sample")
SEED, B = 20261121, 2000


def rows(run):
    for line in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r.get("limit_s") == 90:
            yield r


def key(r):
    return tuple(str(r[k]) for k in KEYS)


def pct(a, n):
    return round(100 * a / n, 1) if n else None


def task_boot(items, stat):
    """items: list of (task, value); stat: function of a list of values -> number. Percentile bootstrap over tasks."""
    by = defaultdict(list)
    for t, v in items:
        by[t].append(v)
    tasks = sorted(by)
    rng = random.Random(SEED)
    est = sorted(stat([v for t in (rng.choice(tasks) for _ in tasks) for v in by[t]]) for _ in range(B))
    return round(100 * est[int(.025 * B)], 1), round(100 * est[int(.975 * B) - 1], 1)


def mean(v):
    return sum(v) / len(v) if v else 0.0


def jdk26():
    main = defaultdict(dict)
    for r in rows("main"):
        main[key(r)][r["scenario"]] = r
    s26 = {key(r): r for r in rows("main-jdk26") if r["scenario"] == "S4"}
    feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv"))}
    res = {}
    for jdk in ("25", "26"):
        def sc(k, s):
            if jdk == "26" and s == "S4" and k[3] == "java" and k in s26:
                return s26[k]
            return main[k].get(s)
        out = {}
        for cond in ("C0", "C2"):
            ks = [k for k in main if k[0] == cond and "S4" in main[k]]
            hang = [(k[2], int(bool(sc(k, "S4")["no_return_90"]))) for k in ks]
            rw = [(t, y) for t, y in hang if t[0] in "RW"]
            bh = [k for k in ks if k[2][0] in "BH"]
            over = [(k[2], int(any(bool((sc(k, s) or {}).get("overrun")) for s in main[k]))) for k in bh]
            out[cond] = {"s4_all": f"{sum(y for _, y in hang)}/{len(hang)}", "s4_all_pct": pct(sum(y for _, y in hang), len(hang)),
                         "s4_rw": f"{sum(y for _, y in rw)}/{len(rw)}", "s4_rw_pct": pct(sum(y for _, y in rw), len(rw)),
                         "overrun": f"{sum(y for _, y in over)}/{len(over)}", "overrun_pct": pct(sum(y for _, y in over), len(over))}
            if cond == "C0":
                out[cond]["s4_all_ci_tasks"] = task_boot(hang, mean)
                out[cond]["s4_rw_ci_tasks"] = task_boot(rw, mean)
                out[cond]["overrun_ci_tasks"] = task_boot(over, mean)
            per = {}
            for m in sorted({k[1] for k in bh}):
                mk = [k for k in bh if k[1] == m]
                per[m] = f"{sum(any(bool((sc(k, s) or {}).get('overrun')) for s in main[k]) for k in mk)}/{len(mk)}"
            out[cond]["overrun_per_model"] = per
        # construct split, both conditions
        split = defaultdict(lambda: [0, 0])
        for k in main:
            if "S4" not in main[k]:
                continue
            cons = {c.strip() for c in (feats.get(k, {}).get("timeout_constructs") or "").split(";") if c.strip()}
            g = "whole" if cons & WHOLE else ("none" if not cons else "per_read")
            split[g][0] += int(bool(sc(k, "S4")["no_return_90"]))
            split[g][1] += 1
        out["construct_split_both"] = {g: f"{a}/{n} ({pct(a, n)} %)" for g, (a, n) in split.items()}
        res["jdk" + jdk] = out
    return res


def rapid_s9():
    exp = {}
    flagged = defaultdict(lambda: {"flagged": 0, "growing": 0, "tight": 0})
    java20 = defaultdict(lambda: [0, 0])
    for r in rows("main"):
        if r["scenario"] != "S9" or r.get("rapid_retries") is None:
            continue
        t = r["task"]
        exp.setdefault(t, json.loads(json.dumps(__import__("yaml").safe_load((M.task_dir(t) / "expected.yaml").read_text()))))
        port = M.PORT[exp[t]["fault_dependency"]]
        d = REPO / "data" / "main" / "runs" / r["cond"] / r["model"] / t / r["lang"] / str(r["sample"]) / "S9"
        syn = sorted((s for s in M.jl(d / "syns.jsonl") if s["dst_port"] == port and not s["retransmission"]), key=lambda s: s["t"])
        times = [s["t"] for s in syn]
        ct = M.connect_calls(times)
        g = [(b - a) / 1e9 for a, b in zip(ct, ct[1:])]
        grp = r["cond"] + ("_H" if t[0] == "H" else "_RWB")
        if r["rapid_retries"]:
            flagged[grp]["flagged"] += 1
            flagged[grp]["growing"] += int(any(x >= 0.2 for x in g))
            flagged[grp]["tight"] += int(len(ct) >= 8 and all(x < 0.1 for x in g))
        if r["lang"] == "java":
            java20[r["cond"]][0] += int(bool(r["rapid_retries"]))
            java20[r["cond"]][1] += int(M.rapid(M.connect_calls(times, merge=0.020)))
    return {"flagged": dict(flagged), "java_flags_5ms_vs_20ms": {c: {"5ms": a, "20ms": b} for c, (a, b) in java20.items()}}


def s4_assertion():
    out = {}
    for cond in ("C0", "C2"):
        n = fail = 0
        for r in rows("main"):
            if r["scenario"] != "S4" or r["cond"] != cond:
                continue
            lim = r.get("time_limit_s") or 10.0
            d = [x for x in (r.get("durations_s") or []) if x is not None]
            n += 1
            fail += int(bool(r.get("no_return_90")) or not d or max(d) > lim + 0.25)
        out[cond] = f"{fail}/{n} ({pct(fail, n)} %)"
    return out


def s0slow_split():
    main_s0 = {key(r): r for r in rows("main") if r["scenario"] == "S0"}
    slow = {}
    for line in open(REPO / "data" / "main-variants" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("harness_ok") and r.get("limit_s", 90) == 90 and r.get("dir") and Path(r["dir"]).name == "S0slow":
            slow[key(r)] = r
    ok = lambda r: r.get("outcome") == "correct" and not r.get("no_return_90") and not r.get("overrun")  # noqa: E731
    ks = [k for k in slow if k in main_s0 and ok(main_s0[k])]
    bad = [k for k in ks if not ok(slow[k])]
    deg_ok = [k for k in bad if slow[k].get("outcome") == "degraded" and not slow[k].get("overrun") and not slow[k].get("no_return_90")]
    deg_over = [k for k in bad if slow[k].get("outcome") == "degraded" and (slow[k].get("overrun") or slow[k].get("no_return_90"))]
    return {"correct_in_S0": len(ks), "not_correct_at_750ms": len(bad), "degraded_within_limit": len(deg_ok),
            "degraded_but_overrun": len(deg_over), "other": len(bad) - len(deg_ok) - len(deg_over),
            "disallowed": len(bad) - len(deg_ok), "pct_disallowed": pct(len(bad) - len(deg_ok), len(ks))}


def retry_mechanism():
    feats = list(csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv")))
    progs = {tuple(p[k] for k in KEYS): p for p in csv.DictReader(open(REPO / "analysis" / "out" / "main" / "programs.csv"))}
    ok = [f for f in feats if progs.get(tuple(f[k] for k in KEYS), {}).get("category") == "ok"]
    cols = [c for c in ok[0] if "retry" in c.lower()] if ok else []
    return {"n": len(ok), "columns": cols}


def ablation_c2c_c2():
    base = {key(r): r for run in ("confirm", "ablation") for r in rows(run) if r["scenario"] == "S4"}
    j26 = {key(r): r for run in ("confirm-jdk26", "ablation-jdk26") for r in rows(run) if r["scenario"] == "S4"}
    out = {}
    for jdk in ("25", "26"):
        by = defaultdict(list)
        for k, r in base.items():
            if k[0] not in ("C2", "C2c") or k[2] not in ("R6", "W5"):
                continue
            rr = j26.get(k, r) if jdk == "26" and k[3] == "java" else r
            by[k[1]].append((int(k[0] == "C2c"), int(bool(rr["no_return_90"]))))
        models = sorted(by)

        def rd(xs):
            a = [y for c, y in xs if c == 1]; b = [y for c, y in xs if c == 0]
            return sum(a) / len(a) - sum(b) / len(b) if a and b else None
        rng = random.Random(SEED)
        est = sorted(e for e in (rd([x for m in (rng.choice(models) for _ in models) for x in by[m]]) for _ in range(B)) if e is not None)
        out["jdk" + jdk] = {"rd_pp": round(100 * rd([x for m in models for x in by[m]]), 1),
                            "lo": round(100 * est[int(.025 * len(est))], 1), "hi": round(100 * est[int(.975 * len(est)) - 1], 1)}
    return out


def costs():
    out = {}
    for name, p in (("repair", REPO / "data" / "repair" / "costs.jsonl"), ("main", REPO / "data" / "main" / "costs.jsonl")):
        if p.exists():
            tot = 0.0
            for line in open(p):
                try:
                    x = json.loads(line)
                except ValueError:
                    continue
                tot += float(x.get("usd") or x.get("cost_usd") or 0)
            out[name] = round(tot, 2)
    rv = 0.0
    for p in (REPO / "reports").glob("reviews_round*/xmodel_costs.jsonl"):
        for line in open(p):
            try:
                x = json.loads(line)
            except ValueError:
                continue
            rv += float(x.get("usd") or x.get("cost_usd") or 0)
    out["cross_model_reviews"] = round(rv, 2)
    return out


def main():
    res = {"jdk26_hybrid": jdk26(), "rapid_s9": rapid_s9(), "s4_assertion": s4_assertion(), "s0slow": s0slow_split(),
           "retry_mechanism": retry_mechanism(), "ablation_c2c_minus_c2": ablation_c2c_c2(), "costs": costs()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
