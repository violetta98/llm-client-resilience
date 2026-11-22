"""Round 11 (internal AI review): free analyses on existing data, post hoc.

  python3 analysis/review_round11.py   -> analysis/out/review11/summary.json
1. Held-out H2 with Java S4 from JDK 26: difference with the bootstrap of Table 9 (confirm_analysis.boot_models, seed
   20261106, 2,000 resamples) and per-model differences.
2. Ablation: per-model risk differences for P1-P3 (direction counts).
3. S7 delay growth under stricter criteria (last-three median above 1.5x and 2x the first gap); last-gap median and
   90th percentile among flagged solutions; flagged C2 solutions without attempt timestamps.
4. Test-specification shares restricted to solutions that are correct in S0:
   AP3 (S0slow): correct in S0, not correct at 750 ms, and the subset whose result the task does not allow;
   AP4 (S5a, S5b): outcome not allowed or no return, among solutions correct in S0;
   AP10: silent failures in a fault scenario among solutions correct in S0 (C0).
5. Rapid retries in S9 (the AP5 assertion), per condition.
6. The 25 % variant sample: which keys were hashed.
"""
from __future__ import annotations

import ast
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "runner"))
from confirm_analysis import boot_models  # noqa: E402

OUT = REPO / "analysis" / "out" / "review11"
KEYS = ("cond", "model", "task", "lang", "sample")
FAULT = ("S1", "S2", "S3", "S4", "S5a", "S5b", "S6a", "S6b", "S7", "S8", "S9")


def rows(run):
    for line in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r.get("limit_s") == 90:
            yield r


def key(r):
    return tuple(str(r[k]) for k in KEYS)


def pct(a, n):
    return round(100 * a / n, 1) if n else None


def h2_jdk26():
    h = [r for r in csv.DictReader(open(REPO / "analysis" / "out" / "confirm" / "confirm_h.csv")) if r["hyp"] == "H2"]
    j26 = {key(r): r for r in rows("confirm-jdk26") if r["scenario"] == "S4"}
    out = {}
    for jdk in ("25", "26"):
        rs = []
        for r in h:
            k = tuple(r[x] for x in KEYS)
            y = int(r["y"])
            if jdk == "26" and r["lang"] == "java" and k in j26:
                y = int(bool(j26[k]["no_return_90"]))
            rs.append({"model": r["model"], "x": int(r["x"]), "y": y})
        obs, lo, hi, p = boot_models(rs, "x")
        per = {}
        for m in sorted({r["model"] for r in rs}):
            a = [r["y"] for r in rs if r["model"] == m and r["x"] == 1]
            b = [r["y"] for r in rs if r["model"] == m and r["x"] == 0]
            per[m] = round(100 * (sum(a) / len(a) - sum(b) / len(b)), 1) if a and b else None
        out["jdk" + jdk] = {"diff_pp": round(100 * obs, 1), "lo": round(100 * lo, 1), "hi": round(100 * hi, 1),
                            "p_le0": p, "per_model_pp": per,
                            "models_in_direction": sum(v is not None and v < 0 for v in per.values())}
    return out


def ablation_models():
    d = list(csv.DictReader(open(REPO / "analysis" / "out" / "ablation" / "ablation_p.csv")))
    out = {}
    for hyp in ("P1", "P2", "P3"):
        per = {}
        for m in sorted({r["model"] for r in d if r["hyp"] == hyp}):
            a = [int(r["y"]) for r in d if r["hyp"] == hyp and r["model"] == m and r["c"] == "1"]
            b = [int(r["y"]) for r in d if r["hyp"] == hyp and r["model"] == m and r["c"] == "0"]
            per[m] = round(100 * (sum(a) / len(a) - sum(b) / len(b)), 1) if a and b else None
        out[hyp] = {"per_model_pp": per, "in_direction": sum(v is not None and v < 0 for v in per.values()),
                    "mean_pp": round(statistics.mean(v for v in per.values() if v is not None), 1)}
    return out


def growth():
    res = {}
    for cond in ("C0", "C2"):
        flagged = no_ts = 0
        n = 0
        g1 = g15 = g2 = 0
        last = []
        for r in rows("main"):
            if r["scenario"] != "S7" or r["cond"] != cond or not r.get("excessive_retries"):
                continue
            flagged += 1
            t = r.get("attempt_times_s7")
            t = ast.literal_eval(t) if isinstance(t, str) else t
            if not t:
                no_ts += 1
                continue
            call = max(t, key=len)
            g = [(b - a) / 1e9 for a, b in zip(call, call[1:])]
            if len(g) < 4:
                continue
            n += 1
            m3 = statistics.median(g[-3:])
            g1 += m3 > g[0]
            g15 += m3 > 1.5 * g[0]
            g2 += m3 > 2 * g[0]
            last.append(m3)
        last.sort()
        res[cond] = {"flagged": flagged, "without_timestamps": no_ts, "analysed": n, "growing": g1,
                     "growing_1_5x": g15, "growing_2x": g2, "last3_median_s": round(statistics.median(last), 2),
                     "last3_p90_s": round(last[int(0.9 * len(last)) - 1], 2)}
    return res


def expected(task):
    import yaml
    return yaml.safe_load((REPO / "tasks" / task / "expected.yaml").read_text())


def spec_rows():
    main = defaultdict(dict)
    for r in rows("main"):
        main[key(r)][r["scenario"]] = r

    def ok0(k):
        s0 = main[k].get("S0")
        return bool(s0) and s0.get("outcome") == "correct" and not s0.get("no_return_90") and not s0.get("overrun")
    res = {}
    # AP4
    for sc in ("S5a", "S5b"):
        for cond in ("C0", "C2"):
            ks = [k for k in main if k[0] == cond and sc in main[k]]
            ks0 = [k for k in ks if ok0(k)]
            bad = lambda k: (not main[k][sc].get("outcome_allowed")) or bool(main[k][sc].get("no_return"))  # noqa: E731
            res[f"AP4_{sc}_{cond}"] = {"all": f"{sum(bad(k) for k in ks)}/{len(ks)}",
                                       "correct_in_S0": f"{sum(bad(k) for k in ks0)}/{len(ks0)}",
                                       "pct_correct_in_S0": pct(sum(bad(k) for k in ks0), len(ks0)),
                                       "silent_among_bad": sum(bool(main[k][sc].get("silent_failure")) for k in ks if bad(k))}
    # AP10
    for cond in ("C0", "C2"):
        ks = [k for k in main if k[0] == cond and "S0" in main[k]]
        ks0 = [k for k in ks if ok0(k)]
        sil = lambda k: any(bool(main[k][s].get("silent_failure")) for s in FAULT if s in main[k])  # noqa: E731
        res[f"AP10_{cond}"] = {"any_fault_silent_all": f"{sum(sil(k) for k in ks)}/{len(ks)}",
                               "correct_in_S0": f"{sum(sil(k) for k in ks0)}/{len(ks0)}",
                               "pct_correct_in_S0": pct(sum(sil(k) for k in ks0), len(ks0))}
    # AP5: rapid retries in S9
    for cond in ("C0", "C2"):
        rs = [main[k]["S9"] for k in main if k[0] == cond and "S9" in main[k] and main[k]["S9"].get("rapid_retries") is not None]
        res[f"AP5_S9_rapid_{cond}"] = f"{sum(bool(r['rapid_retries']) for r in rs)}/{len(rs)} ({pct(sum(bool(r['rapid_retries']) for r in rs), len(rs))} %)"
    # AP3
    slow = {}
    for line in open(REPO / "data" / "main-variants" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("harness_ok") and r.get("limit_s", 90) == 90 and r.get("dir") and Path(r["dir"]).name == "S0slow":
            slow[key(r)] = r
    ks = [k for k in slow if k in main and "S0" in main[k]]
    ks0 = [k for k in ks if ok0(k)]
    notc = [k for k in ks0 if not (slow[k].get("outcome") == "correct" and not slow[k].get("no_return_90") and not slow[k].get("overrun"))]

    def disallowed(k):
        r = slow[k]
        if r.get("no_return_90") or r.get("overrun"):
            return True
        allowed = set()
        for sc, outs in (expected(k[2]).get("allowed_outcomes") or {}).items():
            if sc != "S0":
                allowed |= set(outs)
        return r.get("outcome") not in ({"correct"} | ({"degraded"} & allowed))
    res["AP3"] = {"sample": len(ks), "correct_in_S0": len(ks0), "not_correct_at_750ms": len(notc),
                  "pct": pct(len(notc), len(ks0)), "of_which_handler": sum(k[2].startswith("H") for k in notc),
                  "of_which_degraded": sum(slow[k].get("outcome") == "degraded" for k in notc),
                  "disallowed": sum(disallowed(k) for k in notc), "pct_disallowed": pct(sum(disallowed(k) for k in notc), len(ks0))}
    return res


def variant_sample():
    import run_generated as rg  # noqa: E402
    progs = list(csv.DictReader(open(REPO / "analysis" / "out" / "main" / "programs.csv")))
    sel_all = [p for p in progs if rg.variant_selected({**p, "sample": int(p["sample"])})]
    return {"generations": len(progs), "selected_of_generations": len(sel_all),
            "selected_runnable": sum(p.get("category") == "ok" for p in sel_all),
            "runnable": sum(p.get("category") == "ok" for p in progs)}


def main():
    res = {"h2_jdk26": h2_jdk26(), "ablation_models": ablation_models(), "s7_growth": growth(), "spec": spec_rows(),
           "variant_sample": variant_sample()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
