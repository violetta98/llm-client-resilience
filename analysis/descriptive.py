"""Stage A, step 4: descriptive analyses RQ1-RQ5 and "also" (protocol/ANALYSIS_PLAN.md; no hypothesis tests).

  python3 analysis/descriptive.py [--run main]

Reads  analysis/out/<run>/runs.jsonl, programs.csv (analysis/collect.py); data/<run>/classify/features.csv;
       data/<run>/lint/*/findings.jsonl; data/<run>/costs.jsonl and generations/*/meta.json.
Writes analysis/out/<run>/*.csv and fig_*.png / fig_*.pdf (listed in analysis/out/README.md).
Bootstrap intervals: over tasks, 2,000 resamples, seed 20261106. Only runs with harness_ok count.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
KEYS = ("cond", "model", "task", "lang", "sample")
MODELS = ["claude-opus-5.5", "gpt-6.1-sol", "gemini-4-argon", "claude-haiku-5.5", "deepseek-v4.1-flash", "kimi-k3",
          "qwen3-coder-next", "granite-4.2-8b"]
LANGS = ["python", "typescript", "java", "go"]
STALL = ["S1", "S2", "S3", "S4"]
SEED, B = 20261106, 2000
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}


def write(out, name, rows, cols=None):
    if not rows:
        rows = [{"note": "no data"}]
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    with open(out / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def boot_tasks(items, stat, seed=SEED):
    """items: list of (task, value); stat over a list of values -> 95 % percentile interval by resampling tasks."""
    by = defaultdict(list)
    for t, v in items:
        by[t].append(v)
    tasks = sorted(by)
    rnd = random.Random(seed)
    vals = []
    for _ in range(B):
        pool = [v for t in (rnd.choice(tasks) for _ in tasks) for v in by[t]]
        if pool:
            vals.append(stat(pool))
    vals.sort()
    if not vals:
        return None, None
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def share(v):
    return sum(v) / len(v) if v else None


def prop_row(items, **kw):
    v = [x for _, x in items]
    lo, hi = boot_tasks(items, share) if v else (None, None)
    return kw | {"n": len(v), "events": sum(v), "share": round(share(v), 4) if v else "", "lo": _r(lo), "hi": _r(hi)}


def _r(x):
    return "" if x is None else round(x, 4)


def km(times_events):
    """Kaplan-Meier: [(t, event)] -> [(t, S(t))] step points."""
    pts = [(0.0, 1.0)]
    s = 1.0
    data = sorted(times_events)
    n = len(data)
    i = 0
    while i < len(data):
        t = data[i][0]
        d = sum(1 for x in data[i:] if x[0] == t and x[1])
        c = sum(1 for x in data[i:] if x[0] == t)
        if d:
            s *= 1 - d / n
            pts.append((t, s))
        n -= c
        i += c
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run
    rows = [json.loads(l) for l in open(out / "runs.jsonl")]
    ok = [r for r in rows if r.get("usable")]
    r90 = [r for r in ok if r["limit_s"] == 90]
    r330 = {tuple(r[k] for k in (*KEYS, "scenario")): r for r in ok if r["limit_s"] == 330}

    # ---------------------------------------------------------------- RQ1
    t = []
    for sc in STALL:
        for m in MODELS + ["all"]:
            for cond in ("C0", "C2", "all"):
                it = [(r["task"], int(bool(r["no_return_90"]))) for r in r90 if r["scenario"] == sc
                      and (m == "all" or r["model"] == m) and (cond == "all" or r["cond"] == cond)]
                t.append(prop_row(it, scenario=sc, model=m, cond=cond))
    write(out, "rq1_no_return_90.csv", t)

    # time to return: max call duration; censored at the limit (330 s if repeated, else 90 s)
    tte = defaultdict(list)
    for r in r90:
        if r["scenario"] not in STALL:
            continue
        k = tuple(r[x] for x in (*KEYS, "scenario"))
        rr = r330.get(k) if r["no_return"] else None
        src = rr or r
        lim = src["limit_s"]
        ev = not src["no_return"]
        d = [x for x in (src.get("durations_s") or []) if x is not None]
        tt = max(d) if (ev and d) else float(lim)
        tte[(r["scenario"], r["lang"])].append((min(tt, lim), ev))
    km_rows = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 4, figsize=(14, 3.4), sharey=True)
        for ax, sc in zip(axes, STALL):
            for lang in LANGS:
                pts = km(tte[(sc, lang)])
                xs, ys = [0.0], [1.0]
                for x, y in pts[1:]:
                    xs += [x, x]
                    ys += [ys[-1], y]
                xs.append(330.0)
                ys.append(ys[-1])
                ax.plot(xs, ys, label=lang, lw=1.4)
                km_rows += [{"scenario": sc, "lang": lang, "t": round(x, 3), "survival": round(y, 4)} for x, y in pts]
            ax.set_title(sc)
            ax.set_xlabel("time to return (s)")
            ax.axvline(90, color="grey", lw=0.6, ls=":")
            ax.set_xlim(0, 330)
        axes[0].set_ylabel("share not yet returned")
        axes[-1].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "fig_rq1_km.png", dpi=200)
        fig.savefig(out / "fig_rq1_km.pdf")
        plt.close(fig)
    except ImportError:
        km_rows = [{"scenario": sc, "lang": l, "t": round(x, 3), "survival": round(y, 4)}
                   for (sc, l), v in tte.items() for x, y in km(v)]
    write(out, "rq1_km.csv", km_rows)

    # classification of non-returning runs by the 330 s repetition (S1-S3 all; S4 sample)
    cls = []
    for r in r90:
        if r["scenario"] not in STALL or not r["no_return_90"]:
            continue
        rr = r330.get(tuple(r[x] for x in (*KEYS, "scenario")))
        if rr is None:
            c = "not repeated"
        elif rr["no_return"]:
            c = "not bounded"
        else:
            d = max(x for x in rr["durations_s"] if x is not None)
            # OS connect limit (Linux tcp_syn_retries=6: ~127-131 s per connect attempt) times connect attempts
            n = max(1, rr.get("n_conn_attempts_faulted_dep") or 1)
            c = "OS-bounded" if any(abs(d - k * 129) <= 6 for k in range(1, n + 1)) and r["scenario"] in ("S1",) else "library-bounded"
        cls.append({**{k: r[k] for k in KEYS}, "scenario": r["scenario"], "class": c})
    write(out, "rq1_rerun330_class_runs.csv", cls)
    write(out, "rq1_rerun330_class.csv",
          [{"scenario": sc, "lang": l, "class": c, "n": n} for (sc, l, c), n in
           sorted(Counter((x["scenario"], x["lang"], x["class"]) for x in cls).items())])

    # time-limit overruns, B and H tasks, per scenario
    t = []
    scen = sorted({r["scenario"] for r in r90})
    for sc in scen:
        for m in MODELS + ["all"]:
            for cond in ("C0", "C2", "all"):
                it = [(r["task"], int(bool(r["overrun"]))) for r in r90 if r["scenario"] == sc and r["task"][0] in "BH"
                      and (m == "all" or r["model"] == m) and (cond == "all" or r["cond"] == cond)]
                if it:
                    t.append(prop_row(it, scenario=sc, model=m, cond=cond))
    write(out, "rq1_overrun_by_scenario.csv", t)

    # ---------------------------------------------------------------- RQ2
    t = []
    for sc in ("S5a", "S5b", "S6a", "S6b"):
        for m in MODELS + ["all"]:
            for cond in ("C0", "C2"):
                v = [r for r in r90 if r["scenario"] == sc and (m == "all" or r["model"] == m) and r["cond"] == cond]
                c = Counter(_outcome_class(r) for r in v)
                t.append({"scenario": sc, "model": m, "cond": cond, "n": len(v),
                          **{k: c.get(k, 0) for k in ("recovered", "degraded", "failed", "silent", "no_return", "other")}})
    write(out, "rq2_outcomes_s5_s6.csv", t)

    MEAS = [("rapid_retries", None), ("retry_after_violation", None), ("excessive_retries", None),
            ("late_requests", lambda v: v > 0), ("sync_retries", None), ("unsafe_write_retry", None)]
    t = []
    for name, f in MEAS:
        for m in MODELS + ["all"]:
            for cond in ("C0", "C2", "all"):
                it = [(r["task"], int(bool(f(r[name]) if f else r[name]))) for r in r90 if r.get(name) is not None
                      and (m == "all" or r["model"] == m) and (cond == "all" or r["cond"] == cond)]
                if it:
                    t.append(prop_row(it, measure=name, model=m, cond=cond))
    write(out, "rq2_measures.csv", t)

    t = []
    for m in MODELS + ["all"]:
        for cond in ("C0", "C2"):
            v = sorted(r["load_requests_per_logical_call"] for r in r90 if r["scenario"] == "S7" and
                       r.get("load_requests_per_logical_call") is not None and (m == "all" or r["model"] == m) and r["cond"] == cond)
            if v:
                t.append({"model": m, "cond": cond, "n": len(v), "median": round(v[len(v) // 2], 3),
                          "p90": round(v[int(0.9 * (len(v) - 1))], 3), "max": round(v[-1], 3)})
    write(out, "rq2_s7_load.csv", t)

    # ---------------------------------------------------------------- RQ3 (+ RQ4 descriptives of features)
    fpath = DATA / a.run / "classify" / "features.csv"
    runnable = {tuple(str(r[k]) for k in KEYS) for r in r90}
    feats = [f for f in (csv.DictReader(open(fpath)) if fpath.exists() else []) if tuple(f[k] for k in KEYS) in runnable]
    t = []
    for lang in LANGS:
        for m in MODELS:
            for cond in ("C0", "C2"):
                v = [f for f in feats if f["lang"] == lang and f["model"] == m and f["cond"] == cond]
                if not v:
                    continue
                libs = Counter(f["library"] for f in v)
                t.append({"lang": lang, "model": m, "cond": cond, "n": len(v),
                          "libraries": "; ".join(f"{k} {n}" for k, n in libs.most_common()),
                          "timeout_explicit": sum(int(f["timeout_explicit"]) for f in v),
                          "timeout_total": sum(int(f["timeout_total"]) for f in v),
                          **{f"retry_{k}": sum(k in f["retry_mechanism"].split(";") for f in v)
                             for k in ("none", "hand_loop", "retry_library", "library_builtin")}})
    write(out, "rq3_features.csv", t)

    # ---------------------------------------------------------------- RQ4: every measure by condition
    t = []
    for name in ("no_return_90", "overrun", "c2_overrun", "outcome_allowed", "silent_failure", "rapid_retries",
                 "retry_after_violation", "excessive_retries", "sync_retries", "unsafe_write_retry"):
        for cond in ("C0", "C2"):
            for m in MODELS + ["all"]:
                it = [(r["task"], int(bool(r[name]))) for r in r90 if r.get(name) is not None and r["cond"] == cond
                      and (m == "all" or r["model"] == m) and (name != "no_return_90" or r["scenario"] in STALL)]
                if it:
                    t.append(prop_row(it, measure=name, cond=cond, model=m))
    write(out, "rq4_by_condition.csv", t)

    # ---------------------------------------------------------------- RQ5: linters
    fail = defaultdict(lambda: None)  # per solution: no return in 90 s (S1-S4) or overrun anywhere
    for r in r90:
        k = tuple(r[x] for x in KEYS)
        bad = bool(r.get("no_return")) or bool(r.get("overrun"))  # no return in 90 s in any scenario, or overrun
        fail[k] = bad or bool(fail[k])
    t = []
    for tool in ("bandit_B113", "ruff_S113", "golangci_noctx"):
        p = DATA / a.run / "lint" / tool / "findings.jsonl"
        if not p.exists():
            continue
        lint = {tuple(x[k] for k in KEYS): x["flagged"] for x in map(json.loads, open(p))}
        for m in MODELS + ["all"]:
            ks = [k for k in lint if k in fail and (m == "all" or k[1] == m)]
            failing = [k for k in ks if fail[k]]
            passing = [k for k in ks if not fail[k]]
            t.append({"tool": tool, "model": m, "solutions": len(ks), "failing": len(failing),
                      "failing_flagged": sum(lint[k] for k in failing), "passing": len(passing),
                      "false_alarms": sum(lint[k] for k in passing),
                      "recall": _r(sum(lint[k] for k in failing) / len(failing)) if failing else "",
                      "false_alarm_rate": _r(sum(lint[k] for k in passing) / len(passing)) if passing else ""})
    write(out, "rq5_linters.csv", t)

    # ---------------------------------------------------------------- also
    progs = list(csv.DictReader(open(out / "programs.csv")))
    write(out, "also_categories.csv",
          [{"model": m, "lang": l, "cond": c, **Counter(p["category"] for p in progs if p["model"] == m and p["lang"] == l and p["cond"] == c)}
           for m in MODELS for l in LANGS for c in ("C0", "C2")],
          ["model", "lang", "cond", "ok", "import_error", "compile_error", "missing_dependency", "no_code", "api_error"])
    # distinct solutions after normalization (comments and whitespace removed)
    t = []
    for m in MODELS:
        for l in LANGS:
            for c in ("C0", "C2"):
                hs = defaultdict(set)
                for p in progs:
                    if p["model"] == m and p["lang"] == l and p["cond"] == c:
                        f = DATA / a.run / "generations" / c / m / p["task"] / l / p["sample"] / f"solution.{EXT[l]}"
                        if f.exists():
                            hs[p["task"]].add(_norm_hash(f.read_text(), l))
                t.append({"model": m, "lang": l, "cond": c, "tasks": len(hs),
                          "distinct_per_task_mean": _r(sum(len(v) for v in hs.values()) / len(hs)) if hs else ""})
    write(out, "also_distinct.csv", t)
    # tokens, cost, latency, providers per model
    agg = defaultdict(lambda: {"requests": 0, "in": 0, "out": 0, "usd": 0.0, "lat": [], "prov": Counter()})
    for f in (DATA / a.run / "generations").glob("*/*/*/*/*/meta.json"):
        mt = json.loads(f.read_text())
        g = agg[f.parts[-5]]
        g["requests"] += 1
        g["in"] += mt.get("input_tokens") or 0
        g["out"] += mt.get("output_tokens") or 0
        g["usd"] += float(mt.get("usd") or 0)
        if mt.get("latency_s") is not None:
            g["lat"].append(mt["latency_s"])
        g["prov"][mt.get("provider_returned") or "?"] += 1
    write(out, "also_tokens_cost.csv",
          [{"model": m, "requests": g["requests"], "prompt_tokens": g["in"], "completion_tokens": g["out"],
            "cost_usd": round(g["usd"], 2), "latency_median_s": round(sorted(g["lat"])[len(g["lat"]) // 2], 1) if g["lat"] else "",
            "providers": "; ".join(f"{k} {n}" for k, n in g["prov"].most_common())} for m, g in sorted(agg.items())])
    print("descriptive tables ->", out)


def _outcome_class(r):
    o = r.get("outcome")
    if r.get("no_return"):
        return "no_return"
    if r.get("silent_failure"):
        return "silent"
    return {"correct": "recovered", "degraded": "degraded", "error": "failed"}.get(o, "other")


def _norm_hash(src, lang):
    if lang == "python":
        src = re.sub(r"#[^\n]*", "", src)
        src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
    else:
        src = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", src)
    return hashlib.sha256(re.sub(r"\s+", "", src).encode()).hexdigest()


if __name__ == "__main__":
    main()
