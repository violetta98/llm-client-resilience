"""Internal AI review, round 13 (D57): free analyses on existing data, exploratory.

  python3 analysis/review_round13.py   -> analysis/out/review13/summary.json
1. Test specification on the stated assertions, baseline: S1 and S3 return within the stated limit (10 s if none)
   plus 0.25 s; S9 more than 10 attempts without the polling task B2; S9 more than three connect calls in the first
   500 ms of a logical call (5 ms SYN merge); delay growth among flagged S7 solutions without B2.
2. Prompt ablation, R6/W5: over 10.25 s in any scenario, counting runs that do not return (the definition of the
   main study); ablation_analysis.py counted returned runs only.
"""
from __future__ import annotations

import ast
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

OUT = REPO / "analysis" / "out" / "review13"
KEYS = ("cond", "model", "task", "lang", "sample")


def rows(run):
    for line in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r.get("limit_s") == 90:
            yield r


def key(r):
    return tuple(str(r[k]) for k in KEYS)


def pct(a, n):
    return round(100 * a / n, 1) if n else None


def spec():
    import yaml
    res = {}
    for sc in ("S1", "S3"):
        rs = [r for r in rows("main") if r["scenario"] == sc and r["cond"] == "C0"]
        fail = 0
        for r in rs:
            lim = r.get("time_limit_s") or 10.0
            d = [x for x in (r.get("durations_s") or []) if x is not None]
            fail += int(bool(r.get("no_return_90")) or not d or max(d) > lim + 0.25)
        res[f"{sc}_assertion_C0"] = f"{fail}/{len(rs)} ({pct(fail, len(rs))} %)"
    s9 = [r for r in rows("main") if r["scenario"] == "S9" and r["cond"] == "C0" and r.get("excessive_retries") is not None]
    nb = [r for r in s9 if r["task"] != "B2"]
    res["S9_excessive_noB2_C0"] = f"{sum(bool(r['excessive_retries']) for r in nb)}/{len(nb)} ({pct(sum(bool(r['excessive_retries']) for r in nb), len(nb))} %)"
    exp, n, burst = {}, 0, 0
    for r in rows("main"):
        if r["scenario"] != "S9" or r["cond"] != "C0" or r.get("rapid_retries") is None:
            continue
        t = r["task"]
        exp.setdefault(t, yaml.safe_load((M.task_dir(t) / "expected.yaml").read_text()))
        port = M.PORT[exp[t]["fault_dependency"]]
        d = REPO / "data" / "main" / "runs" / r["cond"] / r["model"] / t / r["lang"] / str(r["sample"]) / "S9"
        syn = sorted((s for s in M.jl(d / "syns.jsonl") if s["dst_port"] == port and not s["retransmission"]), key=lambda s: s["t"])
        ct = M.connect_calls([s["t"] for s in syn])
        n += 1
        burst += int(len(ct) > 3 and (ct[3] - ct[0]) / 1e9 < 0.5)
    res["S9_more_than_3_in_500ms_C0"] = f"{burst}/{n} ({pct(burst, n)} %)"
    for cond in ("C0", "C2"):
        n = g = 0
        for r in rows("main"):
            if r["scenario"] != "S7" or r["cond"] != cond or not r.get("excessive_retries") or r["task"] == "B2":
                continue
            t = r.get("attempt_times_s7")
            t = ast.literal_eval(t) if isinstance(t, str) else t
            if not t:
                continue
            call = max(t, key=len)
            gaps = [(b - a) / 1e9 for a, b in zip(call, call[1:])]
            if len(gaps) < 4:
                continue
            n += 1
            g += int(statistics.median(gaps[-3:]) > gaps[0])
        res[f"S7_growth_noB2_{cond}"] = f"{g}/{n}"
    return res


def ablation_over10():
    per = defaultdict(dict)
    for run in ("confirm", "ablation", "confirm-s56"):
        for r in rows(run):
            if r["task"] in ("R6", "W5"):
                per[key(r)].setdefault(r["scenario"], r)
    out = {}
    for cond in ("C0", "C0b", "C2", "C2c"):
        ks = [k for k in per if k[0] == cond and "S4" in per[k]]
        def over(v, incl):
            return any((incl and bool(x.get("no_return"))) or
                       max([t for t in (x.get("durations_s") or []) if t is not None] or [0]) > 10.25 for x in v.values())
        a = sum(over(per[k], True) for k in ks)
        out[cond] = {"n": len(ks), "returned_only": sum(over(per[k], False) for k in ks), "with_no_return": a,
                     "pct_with_no_return": pct(a, len(ks))}
    return out


def main():
    res = {"spec": spec(), "ablation_over10_R6W5": ablation_over10()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
