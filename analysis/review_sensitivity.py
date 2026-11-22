"""Sensitivity and robustness analyses requested in review (post hoc, DEVIATIONS D37). Nothing here changes a
measure, threshold or registered test; all outputs are descriptive or labelled non-preregistered.

  python3 analysis/review_sensitivity.py [--run main]

Reads  analysis/out/<run>/runs.jsonl, programs.csv, data/<run>/classify/features.csv
Writes analysis/out/<run>/review/
  thresholds_excessive.csv  share of solutions with more than 5 / 10 / 20 attempts per logical call (S7 outage, S9
                            30 s), and the distribution of the maximum attempts (median, p75, p90), per condition
  rapid_by_group.csv        rapid retries in S9 and S7 per condition, handler tasks (H, 1-3 s limits) vs the others,
                            and among handler runs that returned within their limit
  sync_sensitivity.csv      synchronized retries by attempt time (registered) and by inter-attempt interval (D18)
  flagship_sensitivity.csv  flagship minus other LLMs (pp) per condition and outcome: as registered (runnable
                            solutions), intention to treat (non-runnable generation = failure), without Granite/Qwen
  per_task.csv              no return in S4, overrun, any harmful retry per task and condition
  rule_baselines.csv        the whole-call-deadline rule against trivial rules (flag all; flag Python and Java;
                            flag by library) on the RQ5 failing definition
  exploratory_models/primary.csv  input for analysis/models.R with non-registered outcomes s4_no_return,
                            excessive_any (S7 or S9), rapid_s9 (same model as the registered outcomes)
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
FLAG = {"claude-opus-5.5", "gpt-6.1-sol", "gemini-4-argon"}
WHOLE = {"asyncio.timeout", "asyncio.timeout_at", "asyncio.wait_for", "aiohttp.ClientTimeout(total)",
         "Future.get(timeout)", "Future.result(timeout)", "orTimeout", "callTimeout",
         "AbortSignal.timeout", "AbortController+setTimeout", "Promise.race+setTimeout",
         "context.WithTimeout", "http.Client.Timeout",
         # D44: also bound the whole call
         "async_timeout.timeout", "resty SetTimeout", "ky timeout", "got timeout.request"}


def write(path, rows):
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)


def pct(k, n):
    return round(100 * k / n, 1) if n else ""


def quant(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    base = REPO / "analysis" / "out" / a.run
    out = base / "review"
    (out / "exploratory_models").mkdir(parents=True, exist_ok=True)
    per = defaultdict(list)
    for line in open(base / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r["limit_s"] == 90:
            per[tuple(str(r[k]) for k in KEYS)].append(r)
    sols = sorted(per)
    progs = {tuple(p[k] for k in KEYS): p for p in csv.DictReader(open(base / "programs.csv"))}
    feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(REPO / "data" / a.run / "classify" / "features.csv"))}

    def run(k, sc):
        return next((r for r in per[k] if r["scenario"] == sc), None)

    def maxatt(k, sc):
        r = run(k, sc)
        if not r or r.get("excessive_retries") is None:  # same exclusions as the measure (B1 in S9)
            return None
        if sc == "S7":
            c = r.get("attempts_during_outage") or {}
            return max(c.values()) if c else 0
        return r.get("attempts_within_30s")

    # 1. excessive-retry thresholds
    t = []
    for sc in ("S7", "S9"):
        for cond in ("C0", "C2"):
            xs = [maxatt(k, sc) for k in sols if k[0] == cond]
            xs = [x for x in xs if x is not None]
            row = {"scenario": sc, "cond": cond, "solutions": len(xs), "median": quant(xs, .5), "p75": quant(xs, .75),
                   "p90": quant(xs, .9), "max": max(xs)}
            for th in (5, 10, 20):
                row[f"more_than_{th}"] = pct(sum(x > th for x in xs), len(xs))
            t.append(row)
    for cond in ("C0", "C2"):
        ks = [k for k in sols if k[0] == cond]
        row = {"scenario": "S7 or S9", "cond": cond, "solutions": len(ks)}
        for th in (5, 10, 20):
            row[f"more_than_{th}"] = pct(sum(any((maxatt(k, s) or 0) > th for s in ("S7", "S9")) for k in ks), len(ks))
        t.append(row)
    write(out / "thresholds_excessive.csv", t)

    # 2. rapid retries by task group
    t = []
    for sc in ("S9", "S7"):
        for cond in ("C0", "C2"):
            for grp in ("H", "other"):
                rs = [run(k, sc) for k in sols if k[0] == cond and (k[2][0] == "H") == (grp == "H")]
                rs = [r for r in rs if r and r.get("rapid_retries") is not None]
                row = {"scenario": sc, "cond": cond, "tasks": grp, "solutions": len(rs),
                       "rapid": pct(sum(bool(r["rapid_retries"]) for r in rs), len(rs))}
                if grp == "H":
                    ok = [r for r in rs if r["rapid_retries"] and not r.get("overrun") and not r.get("no_return")]
                    row["rapid_and_within_limit"] = len(ok)
                t.append(row)
    write(out / "rapid_by_group.csv", t)

    # 3. synchronized retries, registered vs interval-based
    t = []
    for cond in ("C0", "C2"):
        rs = [run(k, "S7") for k in sols if k[0] == cond]
        rs = [r for r in rs if r and r.get("sync_retries") is not None]
        t.append({"cond": cond, "solutions": len(rs), "sync_by_time": pct(sum(bool(r["sync_retries"]) for r in rs), len(rs)),
                  "sync_by_interval": pct(sum(bool(r.get("sync_gap_retries")) for r in rs), len(rs)),
                  "both": pct(sum(bool(r["sync_retries"]) and bool(r.get("sync_gap_retries")) for r in rs), len(rs))})
    write(out / "sync_sensitivity.csv", t)

    # outcomes per solution
    def oc_s3(k):
        r = run(k, "S3")
        return None if r is None else int(bool(r.get("no_return_90")))

    def oc_s4(k):
        r = run(k, "S4")
        return None if r is None else int(bool(r.get("no_return_90")))

    def oc_over(k):
        return int(any(r.get("overrun") for r in per[k])) if k[2][0] in "BH" else None

    def oc_dup(k):
        r = run(k, "S8")
        return None if (r is None or k[2] not in ("W1", "W2", "B4")) else int(bool(r.get("unsafe_write_retry")))

    def oc_exc(k):
        v = [run(k, s) for s in ("S7", "S9")]
        v = [r.get("excessive_retries") for r in v if r and r.get("excessive_retries") is not None]
        return int(any(v)) if v else None

    def oc_rapid9(k):
        r = run(k, "S9")
        return None if r is None or r.get("rapid_retries") is None else int(bool(r["rapid_retries"]))

    def oc_harm(k):
        return int(any(r.get(m) for r in per[k] for m in ("rapid_retries", "excessive_retries", "retry_after_violation",
                                                           "unsafe_write_retry", "sync_retries")))
    OUT = {"s3_no_return": oc_s3, "s4_no_return": oc_s4, "overrun": oc_over, "unsafe_write": oc_dup}

    # 4. flagship sensitivity (descriptive differences in percentage points)
    all_gen = sorted(progs)
    t = []
    for name, f in OUT.items():
        for cond in ("C0", "C2"):
            def diff(keys, itt):
                vals = {True: [], False: []}
                for k in keys:
                    if k[0] != cond:
                        continue
                    if k in per:
                        y = f(k)
                    elif itt and progs[k]["category"] != "ok":
                        # non-runnable generation counts as failing, if the outcome applies to its task
                        y = None if (name == "overrun" and k[2][0] not in "BH") or \
                            (name == "unsafe_write" and k[2] not in ("W1", "W2", "B4")) else 1
                    else:
                        y = None
                    if y is not None:
                        vals[k[1] in FLAG].append((k[1], y))

                def model_mean(v):  # as in analysis/models.R: mean of the per-LLM shares
                    by = defaultdict(list)
                    for m, y in v:
                        by[m].append(y)
                    return sum(sum(x) / len(x) for x in by.values()) / len(by)
                fl, ot = vals[True], vals[False]
                return round(100 * (model_mean(fl) - model_mean(ot)), 1) if fl and ot else ""
            t.append({"outcome": name, "cond": cond, "registered_pp": diff(sols, False),
                      "itt_pp": diff(all_gen, True),
                      "without_granite_qwen_pp": diff([k for k in sols if k[1] not in ("granite-4.2-8b", "qwen3-coder-next")], False)})
    write(out / "flagship_sensitivity.csv", t)

    # 5. per-task rates
    t = []
    for task in sorted({k[2] for k in sols}):
        for cond in ("both", "C0", "C2"):
            ks = [k for k in sols if k[2] == task and (cond == "both" or k[0] == cond)]
            row = {"task": task, "cond": cond, "solutions": len(ks)}
            for name, f in (("s4_no_return", oc_s4), ("overrun", oc_over), ("any_harmful_retry", oc_harm)):
                v = [f(k) for k in ks]
                v = [x for x in v if x is not None]
                row[name] = pct(sum(v), len(v)) if v else ""
            t.append(row)
    write(out / "per_task.csv", t)

    # 6. rule vs trivial baselines (RQ5 failing definition)
    fail = {k: any(bool(r.get("no_return")) or bool(r.get("overrun")) for r in per[k]) for k in sols}

    def cons(k):
        return {x for x in feats[k]["timeout_constructs"].split(";") if x}
    rules = {"no_whole_call_deadline": lambda k: not (cons(k) & WHOLE),
             "flag_all": lambda k: True,
             "flag_python_java": lambda k: k[3] in ("python", "java"),
             "flag_library_requests_httpx_javanet": lambda k: any(x in feats[k]["library"] for x in
                                                                  ("requests", "httpx", "java.net.http"))}
    t = []
    for lang in ("python", "typescript", "java", "go", "all"):
        ks = [k for k in sols if lang == "all" or k[3] == lang]
        pos = [k for k in ks if fail[k]]
        neg = [k for k in ks if not fail[k]]
        for name, f in rules.items():
            tp = sum(f(k) for k in pos)
            fp = sum(f(k) for k in neg)
            t.append({"lang": lang, "rule": name, "solutions": len(ks), "failing": len(pos), "recall": pct(tp, len(pos)),
                      "precision": pct(tp, tp + fp), "false_alarm_rate": pct(fp, len(neg)), "base_rate": pct(len(pos), len(ks))})
    write(out / "rule_baselines.csv", t)

    # 7. input for the same mixed model on non-registered outcomes
    t = []
    for k in sols:
        for name, f in (("s4_no_return", oc_s4), ("excessive_any", oc_exc), ("rapid_s9", oc_rapid9)):
            y = f(k)
            if y is not None:
                t.append({**dict(zip(KEYS, k)), "flagship": int(k[1] in FLAG), "outcome": name, "y": y,
                          "n_scenarios": 1, "complete": 1})
    write(out / "exploratory_models" / "primary.csv", t)

    # 8. S4: does a solution that returns close the trickling connection? (mock responses.jsonl: the server's write
    # fails once the client has closed; bytes go out every 2 s and the driver exits 5 s after the call returns)
    import sys
    sys.path.insert(0, str(REPO / "analysis"))
    import measures as M
    t, agg = [], defaultdict(lambda: [0, 0, 0])
    for k in sols:
        r = run(k, "S4")
        if not r or r.get("no_return") or r.get("status") not in ("returned", "raised"):
            continue
        d = REPO / "data" / a.run / "runs" / Path(*k) / "S4"
        if not d.exists():
            continue
        rr = M.load_run(d)
        calls = (rr["result"] or {}).get("calls") or []
        if not calls or not calls[-1].get("t_end"):
            continue
        t_ret = max(c["t_end"] for c in calls if c.get("t_end"))
        tr = [x for x in rr["responses"] if x.get("fault") == "trickle" and x.get("outcome") in ("trickle_aborted", "run_finished")]
        if not tr:
            continue
        closed = all(x["outcome"] == "trickle_aborted" and (x["t_end"] - t_ret) / 1e9 <= 4.5 for x in tr)
        c = cons(k)
        grp = "whole-call deadline" if c & WHOLE else ("per-read or until headers only" if c else "none")
        for key in ((k[3], grp), ("all", grp), (k[3], "all"), ("all", "all")):
            agg[key][0] += 1
            agg[key][1] += int(closed)
        kind = ";".join(sorted(c & WHOLE)) or grp
        agg[(k[3], "kind: " + kind)][0] += 1
        agg[(k[3], "kind: " + kind)][1] += int(closed)
        t.append({**dict(zip(KEYS, k)), "group": grp, "closed_within_4_5s": int(closed),
                  "seconds_after_return": round(max(x["t_end"] - t_ret for x in tr) / 1e9, 2)})
    write(out / "s4_connection_closure_runs.csv", t)

    # 9. round-2 review: C2 compliance of excessive retries, task groups, matched cells, cluster bootstrap, read timeouts
    import random
    import re

    def budget(k):  # the time the requirements condition allows: the stated limit, or 10 s
        return {"B": 30, "H": None}.get(k[2][0]) or ({"H1": 2, "H2": 1, "H3": 3}.get(k[2]) or 10)

    rows9 = []
    for k in sols:
        if k[0] != "C2":
            continue
        for sc in ("S7", "S9"):
            r = run(k, sc)
            if not r or not r.get("excessive_retries"):
                continue
            durs = [x for x in (r.get("durations_s") or []) if x is not None]
            over = r.get("no_return") or (durs and max(durs) > budget(k) + 0.25)
            rows9.append({**dict(zip(KEYS, k)), "scenario": sc, "budget_s": budget(k), "max_duration_s": max(durs) if durs else "",
                          "exceeds_budget": int(bool(over))})
    write(out / "c2_excessive_budget.csv", rows9)
    n_sol = len({tuple(x[c] for c in KEYS) for x in rows9})
    n_over = len({tuple(x[c] for c in KEYS) for x in rows9 if x["exceeds_budget"]})
    within = [x for x in rows9 if not x["exceeds_budget"]]
    summary = [{"what": "C2 solutions with excessive retries in S7 or S9", "n": n_sol},
               {"what": "... of which exceed the time budget of the requirements in that scenario", "n": n_over}]

    # task groups: B/H (stated limit) vs R/W (no stated limit), S4 and RQ5 failing, per condition
    for cond in ("C0", "C2"):
        for grp, pred in (("B/H", lambda k: k[2][0] in "BH"), ("R/W", lambda k: k[2][0] in "RW")):
            ks = [k for k in sols if k[0] == cond and pred(k)]
            v = [oc_s4(k) for k in ks]
            v = [x for x in v if x is not None]
            summary.append({"what": f"S4 hang, {cond}, {grp} tasks", "n": len(v), "share": pct(sum(v), len(v))})
    for grp, pred in (("B/H", lambda k: k[2][0] in "BH"), ("R/W", lambda k: k[2][0] in "RW")):
        ks = [k for k in sols if pred(k)]
        for name, f in rules.items():
            if name != "no_whole_call_deadline":
                continue
            pos = [k for k in ks if fail[k]]
            neg = [k for k in ks if not fail[k]]
            tp = sum(f(k) for k in pos)
            fp = sum(f(k) for k in neg)
            summary.append({"what": f"rule, {grp} tasks: recall / precision / false alarms", "n": len(ks),
                            "share": f"{pct(tp, len(pos))} / {pct(tp, tp + fp)} / {pct(fp, len(neg))}"})
        for tool in ("bandit_B113", "ruff_S113"):
            pth = REPO / "data" / a.run / "lint" / tool / "findings.jsonl"
            if pth.exists():
                fl = {tuple(str(x[c]) for c in KEYS): bool(x["flagged"]) for x in map(json.loads, open(pth))}
                kk = [k for k in ks if k in fl]
                pos = [k for k in kk if fail[k]]
                summary.append({"what": f"{tool}, {grp} tasks: flagged among failing", "n": len(pos),
                                "share": pct(sum(fl[k] for k in pos), len(pos))})

    # matched cells: (model, task, lang) with at least one runnable solution in both conditions
    cells = defaultdict(set)
    for k in sols:
        cells[k[1:4]].add(k[0])
    matched = [k for k in sols if cells[k[1:4]] == {"C0", "C2"}]
    for name, f in (("s4_no_return", oc_s4), ("excessive_any", oc_exc)):
        for cond in ("C0", "C2"):
            v = [f(k) for k in matched if k[0] == cond]
            v = [x for x in v if x is not None]
            summary.append({"what": f"matched cells: {name}, {cond}", "n": len(v), "share": pct(sum(v), len(v))})

    # flagship difference with a cluster bootstrap over tasks (mean of per-LLM shares, as in models.R)
    rng = random.Random(20261106)
    tasks = sorted({k[2] for k in sols})
    for name, f in OUT.items():
        for cond in ("C0", "C2"):
            data = defaultdict(list)
            for k in sols:
                if k[0] == cond:
                    y = f(k)
                    if y is not None:
                        data[k[2]].append((k[1], y))

            def stat(ts):
                by = defaultdict(list)
                for t_ in ts:
                    for m, y in data[t_]:
                        by[m].append(y)
                fl = [sum(v) / len(v) for m, v in by.items() if m in FLAG]
                ot = [sum(v) / len(v) for m, v in by.items() if m not in FLAG]
                return (sum(fl) / len(fl) - sum(ot) / len(ot)) if fl and ot else None
            ts0 = [t_ for t_ in tasks if data[t_]]
            est = stat(ts0)
            bs = sorted(x for x in (stat([rng.choice(ts0) for _ in ts0]) for _ in range(2000)) if x is not None)
            lo, hi = bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]
            p2 = 2 * min(sum(x >= 0 for x in bs), sum(x <= 0 for x in bs)) / len(bs)
            summary.append({"what": f"flagship - others, {name}, {cond}, cluster bootstrap over tasks (pp, 95% CI, p)",
                            "n": len(ts0), "share": f"{round(100 * est, 1)} ({round(100 * lo, 1)} to {round(100 * hi, 1)}), p={round(min(1, p2), 3)}"})

    # read-timeout values of Python solutions whose only timeouts bound a read
    num = r"(\d+(?:\.\d+)?)"
    dist = defaultdict(lambda: [0, 0])
    for k in sols:
        if k[3] != "python" or not cons(k) or (cons(k) & WHOLE):
            continue
        src = (REPO / "data" / a.run / "prepared" / Path(*k) / "solution.py").read_text(errors="replace")
        tup = re.findall(r"timeout\s*=\s*\(\s*" + num + r"\s*,\s*" + num, src)
        sca = re.findall(r"timeout\s*=\s*" + num + r"\s*[,)]", src)
        reads = [float(b_) for _, b_ in tup] + [float(x) for x in sca]
        v = min(reads) if reads else None
        b_ = "no literal" if v is None else ("< 2 s" if v < 2 else ("= 2 s" if v == 2 else ("2-5 s" if v <= 5 else "> 5 s")))
        dist[b_][0] += 1
        dist[b_][1] += int(bool(oc_s4(k)))
    for b_, (n, h) in sorted(dist.items()):
        summary.append({"what": f"Python per-read-only solutions, smallest literal read timeout {b_}: S4 hang", "n": n, "share": pct(h, n)})
    write(out / "round2_summary.csv", summary)
    for x in summary:
        print(x)
    write(out / "s4_connection_closure.csv", [{"lang": l, "group": g, "returned_runs": n, "closed": c,
                                                "kept_open": n - c, "kept_open_share": pct(n - c, n)}
                                               for (l, g), (n, c, _) in sorted(agg.items())])
    print("ok", out)


if __name__ == "__main__":
    main()
