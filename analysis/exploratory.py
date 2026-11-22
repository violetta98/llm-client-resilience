"""Exploratory analyses added for the journal version (post hoc, DEVIATIONS D34). No measure, threshold, model or
pre-registered test is changed; everything here is descriptive and must be labelled exploratory.

  python3 analysis/exploratory.py [--run main]

Reads  analysis/out/<run>/runs.jsonl, data/<run>/classify/features.csv, data/<run>/lint/*/findings.jsonl,
       data/<run>/prepared/<cond>/<model>/<task>/<lang>/<sample>/solution.*
Writes analysis/out/<run>/exploratory/
  whole_call_rule.csv      a static rule "no whole-call deadline" (the D32 grouping used as a check), against
                           fault injection, per language and condition, next to the existing linters
  python_perread_s4.csv    Python solutions whose only timeout bounds a read: why some return in S4
  power.csv                power of the per-LLM C2-vs-C0 contrasts (Fisher exact, alpha 0.05/8 = Holm's first step;
                           ignores task clustering, so it is an upper bound on the power of the registered test)
  antipatterns.csv         solutions per anti-pattern (both conditions, C0, C2), with the scenario that exposes it
  antipattern_examples.csv up to 5 shortest solutions per anti-pattern (for choosing listings)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
LANGS = ["python", "typescript", "java", "go"]
MODELS = ["claude-opus-5.5", "gpt-6.1-sol", "gemini-4-argon", "claude-haiku-5.5", "deepseek-v4.1-flash", "kimi-k3",
          "qwen3-coder-next", "granite-4.2-8b"]
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
STALL = ("S1", "S2", "S3", "S4")
# identical to analysis/s4_mechanism.py (D32)
WHOLE = {"asyncio.timeout", "asyncio.timeout_at", "asyncio.wait_for", "aiohttp.ClientTimeout(total)",
         "Future.get(timeout)", "Future.result(timeout)", "orTimeout", "callTimeout",
         "AbortSignal.timeout", "AbortController+setTimeout", "Promise.race+setTimeout",
         "context.WithTimeout", "http.Client.Timeout",
         # D44: also bound the whole call
         "async_timeout.timeout", "resty SetTimeout", "ky timeout", "got timeout.request"}
ALPHA = 0.05 / 8


def write(path, rows):
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(rows)


def pct(k, n):
    return round(100 * k / n, 1) if n else ""


# ---------------------------------------------------------------- exact power (Fisher, two-sided)
def _logc(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


_PV = {}


def fisher_reject(n0, n1):
    """set of (x0, x1) for which the two-sided Fisher exact test rejects at ALPHA."""
    if (n0, n1) in _PV:
        return _PV[(n0, n1)]
    rej = set()
    for t in range(n0 + n1 + 1):
        lo, hi = max(0, t - n1), min(t, n0)
        lp = {x: _logc(n0, x) + _logc(n1, t - x) - _logc(n0 + n1, t) for x in range(lo, hi + 1)}
        ps = {x: math.exp(v) for x, v in lp.items()}
        for x, p in ps.items():
            pv = sum(q for q in ps.values() if q <= p * (1 + 1e-7))
            if pv < ALPHA:
                rej.add((x, t - x))
    _PV[(n0, n1)] = rej
    return rej


def binom(n, p):
    if p <= 0:
        return [1.0] + [0.0] * n
    if p >= 1:
        return [0.0] * n + [1.0]
    return [math.exp(_logc(n, k) + k * math.log(p) + (n - k) * math.log(1 - p)) for k in range(n + 1)]


def power(n0, n1, p0, p1):
    rej = fisher_reject(n0, n1)
    b0, b1 = binom(n0, p0), binom(n1, p1)
    return sum(b0[x] * b1[y] for x, y in rej)


def mde_reduction(n0, n1, p0, target=0.8):
    """smallest p0 - p1 (p1 < p0) with power >= target; None if even p1 = 0 does not reach it."""
    if power(n0, n1, p0, 0.0) < target:
        return None
    lo, hi = 0.0, p0
    for _ in range(30):
        mid = (lo + hi) / 2
        if power(n0, n1, p0, p0 - mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def mde_increase(n0, n1, p0, target=0.8):
    lo, hi = 0.0, 1 - p0
    if power(n0, n1, p0, 1.0) < target:
        return None
    for _ in range(30):
        mid = (lo + hi) / 2
        if power(n0, n1, p0, p0 + mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    out = REPO / "analysis" / "out" / a.run / "exploratory"
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in open(REPO / "analysis" / "out" / a.run / "runs.jsonl")]
    r90 = [r for r in rows if r.get("usable") and r["limit_s"] == 90]
    feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(REPO / "data" / a.run / "classify" / "features.csv"))}

    per = defaultdict(list)
    for r in r90:
        per[tuple(str(r[k]) for k in KEYS)].append(r)
    sols = sorted(per)

    def any_(k, name, scen=None):
        return any(bool(r.get(name)) for r in per[k] if scen is None or r["scenario"] in scen)

    fail = {k: any(bool(r.get("no_return")) or bool(r.get("overrun")) for r in per[k]) for k in sols}  # = RQ5
    s4 = {k: any_(k, "no_return_90", ("S4",)) for k in sols}

    def constructs(k):
        return {x for x in feats[k]["timeout_constructs"].split(";") if x}

    rule = {k: not (constructs(k) & WHOLE) for k in sols}  # flagged: no whole-call deadline

    # ------------------------------------------------ A3: the whole-call-deadline rule against fault injection
    lint = {}
    for tool in ("bandit_B113", "ruff_S113", "golangci_noctx"):
        p = REPO / "data" / a.run / "lint" / tool / "findings.jsonl"
        if p.exists():
            lint[tool] = {tuple(str(x[k]) for k in KEYS): bool(x["flagged"]) for x in map(json.loads, open(p))}

    def score(flag, truth, ks, **lab):
        pos = [k for k in ks if truth[k]]
        neg = [k for k in ks if not truth[k]]
        tp = sum(flag[k] for k in pos)
        fp = sum(flag[k] for k in neg)
        return {**lab, "solutions": len(ks), "failing": len(pos), "flagged": tp + fp, "flagged_failing": tp,
                "recall": pct(tp, len(pos)), "precision": pct(tp, tp + fp), "false_alarms": fp,
                "false_alarm_rate": pct(fp, len(neg))}

    t = []
    for tgt_name, tgt in (("fail_any", fail), ("no_return_S4", s4)):
        for cond in ("all", "C0", "C2"):
            for lang in LANGS + ["all"]:
                ks = [k for k in sols if (cond == "all" or k[0] == cond) and (lang == "all" or k[3] == lang)]
                t.append(score(rule, tgt, ks, tool="no_whole_call_deadline", target=tgt_name, cond=cond, lang=lang))
                for tool, fl in lint.items():
                    kk = [k for k in ks if k in fl]
                    if kk:
                        t.append(score(fl, tgt, kk, tool=tool, target=tgt_name, cond=cond, lang=lang))
    write(out / "whole_call_rule.csv", t)
    for r in t:
        if r["cond"] == "all" and r["target"] == "fail_any":
            print("A3", r["tool"], r["lang"], r["solutions"], r["failing"], "recall", r["recall"], "prec", r["precision"],
                  "FA", r["false_alarm_rate"])

    # ------------------------------------------------ Python per-read-only solutions: S4 outcome vs timeout value
    num = r"(\d+(?:\.\d+)?)"
    t = []
    for k in sols:
        if k[3] != "python" or not constructs(k) or (constructs(k) & WHOLE):
            continue
        src = (REPO / "data" / a.run / "prepared" / Path(*k) / "solution.py").read_text(errors="replace")
        vals = [float(v) for v in re.findall(r"timeout\s*=\s*\(?\s*" + num, src)]
        tup = re.findall(r"timeout\s*=\s*\(\s*" + num + r"\s*,\s*" + num, src)
        reads = [float(b) for _, b in tup]
        consts = [float(v) for v in re.findall(r"[A-Z_]*TIMEOUT[A-Z_]*\s*=\s*" + num, src)]
        s4r = [r for r in per[k] if r["scenario"] == "S4"]
        t.append({**dict(zip(KEYS, k)), "library": feats[k]["library"], "s4_status": s4r[0]["status"] if s4r else "",
                  "no_return_S4": int(s4[k]), "min_literal_timeout": min(vals + consts) if vals + consts else "",
                  "read_timeouts": ";".join(map(str, reads)), "stream": int("stream=True" in src or "iter_content" in src
                                                                          or ".stream(" in src),
                  "remaining_budget": int("remaining" in src)})
    write(out / "python_perread_s4.csv", t)
    ret = [x for x in t if not x["no_return_S4"]]
    hang = [x for x in t if x["no_return_S4"]]

    def rd2(xs):  # an explicit (connect, read) tuple whose read timeout is below the 2 s gap of the trickle
        return sum(1 for x in xs if x["read_timeouts"] and min(map(float, x["read_timeouts"].split(";"))) < 2)

    def rem(xs):  # the source mentions a remaining budget (timeouts recomputed per attempt)
        return sum(x["remaining_budget"] for x in xs)
    print(f"py per-read only: {len(t)}; return or raise in S4 {len(ret)} (read timeout < 2 s: {rd2(ret)}; "
          f"'remaining': {rem(ret)}; status {Counter(x['s4_status'] for x in ret)}); "
          f"hang {len(hang)} (read timeout < 2 s: {rd2(hang)}; 'remaining': {rem(hang)})")

    # ------------------------------------------------ A2: power of the per-LLM C2-vs-C0 contrasts
    def cell(model, cond, name, scen=None, task_ok=None):
        ks = [k for k in sols if k[1] == model and k[0] == cond and (task_ok is None or k[2][0] in task_ok)]
        if name == "overrun":
            ev = [k for k in ks if any_(k, "overrun")]
        else:
            ks = [k for k in ks if any(r["scenario"] in scen for r in per[k])]
            ev = [k for k in ks if any_(k, name, scen)]
        return len(ks), len(ev)

    t = []
    for oc, name, scen, tasks in (("S3 no return", "no_return_90", ("S3",), None),
                                  ("S4 no return (secondary)", "no_return_90", ("S4",), None),
                                  ("time-limit overrun", "overrun", None, ("B", "H"))):
        for m in MODELS:
            n0, e0 = cell(m, "C0", name, scen, tasks)
            n1, e1 = cell(m, "C2", name, scen, tasks)
            p0 = e0 / n0
            red = mde_reduction(n0, n1, p0)
            t.append({"outcome": oc, "model": m, "n_C0": n0, "events_C0": e0, "n_C2": n1, "events_C2": e1,
                      "p_C0": pct(e0, n0), "p_C2": pct(e1, n1),
                      "power_halving": round(power(n0, n1, p0, p0 / 2), 3),
                      "power_to_zero": round(power(n0, n1, p0, 0.0), 3),
                      "mde_reduction_pp": round(100 * red, 1) if red is not None else "not reachable",
                      "mde_increase_pp": round(100 * mde_increase(n0, n1, p0), 1)})
            print("A2", oc, m, n0, e0, n1, e1, t[-1]["power_halving"], t[-1]["power_to_zero"], t[-1]["mde_reduction_pp"],
                  t[-1]["mde_increase_pp"])
    write(out / "power.csv", t)

    # ------------------------------------------------ A4: anti-pattern catalogue
    def has(k, *names):
        return bool(constructs(k) & set(names))

    def fetch_no_timeout(k):
        return k[3] == "typescript" and "fetch" in feats[k]["library"] and not constructs(k)

    aps = [
        ("AP1", "Attempt or read timeout without a deadline on the call", "S4",
         lambda k: bool(constructs(k)) and not (constructs(k) & WHOLE), lambda k: s4[k]),
        ("AP2", "No timeout at all", "S3, S4", lambda k: not constructs(k),
         lambda k: any_(k, "no_return_90", STALL)),
        ("AP3", "Retry without delay against a refused connection", "S9",
         lambda k: any_(k, "rapid_retries", ("S9",)), None),
        ("AP4", "Retry without an attempt limit or budget", "S7, S9",
         lambda k: any_(k, "excessive_retries", ("S7", "S9")), None),
        ("AP5", "Retry-After ignored or not parsed in date form", "S6a, S6b",
         lambda k: any_(k, "retry_after_violation", ("S6a", "S6b")), None),
        ("AP6", "Backoff without jitter", "S7", lambda k: any_(k, "sync_retries", ("S7",)), None),
        ("AP7", "Retry of a non-idempotent write without a key", "S8",
         lambda k: any_(k, "unsafe_write_retry", ("S8",)), None),
        ("AP8", "Requests continue after the function returned", "any", lambda k: any(r.get("late_requests") for r in per[k]),
         None),
        ("AP9", "Partial result reported as complete", "S3-S8", lambda k: any_(k, "silent_failure"), None),
    ]
    # numbering of the paper's Table 14 (AP1 there merges AP1 and AP2 here; AP2 there, a deadline that does not cancel
    # the request, comes from the connection-closure analysis; backoff without jitter is not in the paper's table)
    PAPER_AP = {"AP1": "AP1", "AP2": "AP1", "AP3": "AP3", "AP4": "AP4", "AP5": "AP5", "AP6": "-", "AP7": "AP6",
                "AP8": "AP7", "AP9": "AP8"}
    t, ex = [], []
    for ap_id, name, scen, pred, harm in aps:
        row = {"id": ap_id, "paper_id": PAPER_AP[ap_id], "anti_pattern": name, "exposed_by": scen}
        for cond in ("all", "C0", "C2"):
            ks = [k for k in sols if cond == "all" or k[0] == cond]
            hit = [k for k in ks if pred(k)]
            row[f"solutions_{cond}"] = len(hit)
            row[f"share_{cond}"] = pct(len(hit), len(ks))
            if harm and cond == "all":
                row["harm_among_hits"] = pct(sum(harm(k) for k in hit), len(hit))
        hits = [k for k in sols if pred(k)]
        row["by_lang"] = "; ".join(f"{l} {sum(k[3] == l for k in hits)}" for l in LANGS)
        row["by_model_top3"] = "; ".join(f"{m} {c}" for m, c in Counter(k[1] for k in hits).most_common(3))
        t.append(row)
        sized = []
        for k in hits:
            p = REPO / "data" / a.run / "prepared" / Path(*k) / f"solution.{EXT[k[3]]}"
            if p.exists():
                sized.append((len(p.read_text(errors="replace").splitlines()), k))
        for n, k in sorted(sized)[:5]:
            ex.append({"id": ap_id, **dict(zip(KEYS, k)), "lines": n})
        print("A4", ap_id, name, row["solutions_all"], row["share_all"], row["solutions_C0"], row["solutions_C2"],
              row.get("harm_among_hits", ""))
    write(out / "antipatterns.csv", t)
    write(out / "antipattern_examples.csv", ex)
    print("solutions:", len(sols), Counter(k[0] for k in sols))


if __name__ == "__main__":
    main()
