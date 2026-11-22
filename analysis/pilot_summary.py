"""E5 pilot summary: tokens, latency, extraction/prepare categories, outcomes,
slot time, and the E7 cost / E8 machine-time estimates (brief E5).

Usage: python3 analysis/pilot_summary.py [--run pilot]
Writes analysis/out/pilot_summary.json.
Slot seconds: a resumed row has slot_s = null, so measured slot times are merged from
earlier outputs of the same run kept in data/<run>/aborted/measures-*.jsonl (by run dir).
Every number in reports/pilot.md comes from these files.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out"

# Table VI of the draft -> OpenRouter list-price ids in price_snapshot.json (gateway prices;
# vendor direct and batch prices are re-checked at E7). The Gemini slot is "best GA Gemini
# at freeze" and the small open model is not chosen yet: both are bracketed.
TABLE_VI = [
    ("Claude Opus 5.5", "anthropic/claude-opus-5.5", "anthropic/claude-opus-5.5:batch"),
    ("GPT-6.1 Sol", "openai/gpt-6.1-sol", "openai/gpt-6.1-sol:batch"),
    ("Gemini (best GA at freeze; priced as gemini-3.1-pro-preview)", "google/gemini-3.1-pro-preview",
     "google/gemini-3.1-pro-preview:batch"),
    ("Claude Haiku 5.5", "anthropic/claude-haiku-5.5", "anthropic/claude-haiku-5.5:batch"),
    ("DeepSeek V4.1 Flash (priced as the -1017 listing, the higher one)", "deepseek/deepseek-v4.1-flash-1017", None),
    ("Kimi K3", "moonshotai/kimi-k3", None),
    ("Qwen3-Coder-Next", "qwen/qwen3-coder-next", None),
    ("Small open coding model (TBD; priced as qwen3-coder-30b-a3b, an upper bound)", "qwen/qwen3-coder-30b-a3b-instruct", None),
]
N_BENCH_TASKS, N_LANGS, N_SAMPLES, CONDS = 16, 4, 5, ("C0", "C1", "C2")


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None


def desc(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"n": len(xs), "mean": st.mean(xs), "median": st.median(xs), "p90": q(xs, 0.9), "max": max(xs), "min": min(xs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="pilot")
    a = ap.parse_args()
    base = REPO / "data" / a.run
    gens = []
    for mp in sorted((base / "generations").glob("*/*/*/*/*/meta.json")):
        cond, model, task, lang, sample = mp.parent.parts[-5:]
        m = json.loads(mp.read_text())
        att = [json.loads(l) for l in (mp.parent / "attempts.jsonl").read_text().splitlines() if l.strip()] \
            if (mp.parent / "attempts.jsonl").exists() else []
        gens.append({"model": model, "task": task, "lang": lang, "sample": int(sample), "meta": m, "attempts": att})
    progs = [json.loads(l) for l in (base / "programs.jsonl").read_text().splitlines()]
    meas = [json.loads(l) for l in (base / "measures.jsonl").read_text().splitlines()]
    summ = json.loads((base / "run_summary.json").read_text())
    slot_by_dir = {}
    for f in sorted((base / "aborted").glob("measures-*.jsonl")) if (base / "aborted").exists() else []:
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if r.get("slot_s") is not None and "harness_error" not in r and r.get("dir"):
                slot_by_dir[r["dir"]] = r["slot_s"]
    for r in meas:
        if r.get("slot_s") is None and r.get("dir") in slot_by_dir:
            r["slot_s"] = slot_by_dir[r["dir"]]

    # ---- generation ----
    by_model = defaultdict(list)
    for g in gens:
        by_model[g["model"]].append(g)
    gen_out = {}
    for model, gs in by_model.items():
        ok = [g for g in gs if g["meta"].get("status") == "ok"]
        att = Counter(x.get("status") for g in gs for x in g["attempts"])
        gen_out[model] = {
            "generations": len(gs), "ok": len(ok),
            "attempt_status_counts": {str(k): v for k, v in att.items()},
            "finish_reason": dict(Counter(g["meta"].get("finish_reason") for g in ok)),
            "extraction": dict(Counter(g["meta"]["extraction"]["status"] for g in ok)),
            "input_tokens": desc([g["meta"].get("input_tokens") for g in ok]),
            "output_tokens": desc([g["meta"].get("output_tokens") for g in ok]),
            "reasoning_tokens": desc([g["meta"].get("reasoning_tokens") for g in ok]),
            "latency_s": desc([g["meta"].get("latency_s") for g in ok]),
            "usd": sum(g["meta"].get("usd") or 0 for g in ok),
            "output_tokens_by_task_lang": {f"{t}/{l}": desc([g["meta"]["output_tokens"] for g in ok if g["task"] == t and g["lang"] == l])
                                           for t in sorted({g["task"] for g in ok}) for l in sorted({g["lang"] for g in ok})},
            "returned_ids": sorted({str(g["meta"].get("model_returned")) for g in ok}),
            "providers": sorted({str(g["meta"].get("provider_returned")) for g in ok}),
            "reasoning_gt_output": sum(1 for g in ok if (g["meta"].get("reasoning_tokens") or 0) > (g["meta"].get("output_tokens") or 0)),
        }

    # ---- prepare categories ----
    cats = defaultdict(Counter)
    for p in progs:
        cats[f"{p['model']}/{p['lang']}"][p["category"]] += 1
    reasons = [{"program": f"{p['model']}/{p['task']}/{p['lang']}/{p['sample']}", "category": p["category"],
                "missing": (p.get("prepare_info") or {}).get("missing"),
                "errors": (p.get("prepare_info") or {}).get("errors"),
                "build_log": ((p.get("prepare_info") or {}).get("build_log") or "")[:400] or None}
               for p in progs if p["category"] in ("compile_error", "missing_dependency", "no_code")]

    # ---- outcomes per scenario (90 s runs; 330 s rows reported separately) ----
    main_rows = [r for r in meas if r.get("limit_s") == 90 and "harness_error" not in r]
    long_rows = [r for r in meas if r.get("limit_s") == 330 and "harness_error" not in r]
    outc = defaultdict(Counter)
    allowed = defaultdict(Counter)
    for r in main_rows:
        k = f"{r['model']}/{r['lang']}/{r['scenario']}"
        outc[k][r["outcome"]] += 1
        allowed[k][bool(r.get("outcome_allowed"))] += 1
    s0_fail = [f"{r['model']}/{r['task']}/{r['lang']}/{r['sample']}: {r['outcome']}" for r in main_rows
               if r["scenario"] == "S0" and r["outcome"] != "correct"]
    long_out = Counter((r["scenario"], r["outcome"]) for r in long_rows)
    libs = Counter()
    for p in progs:
        if p["category"] == "ok":
            src = (base / "generations" / p["cond"] / p["model"] / p["task"] / p["lang"] / str(p["sample"]))
            f = next(src.glob("solution.*"))
            t = f.read_text()
            if p["lang"] == "python":
                for lib in ("requests", "httpx", "aiohttp", "urllib3", "urllib.request", "tenacity", "backoff"):
                    if f"import {lib}" in t or f"from {lib}" in t:
                        libs[f"python:{lib}"] += 1
            else:
                for lib in ("net/http", "hashicorp/go-retryablehttp", "go-resty", "cenkalti/backoff"):
                    if lib in t:
                        libs[f"go:{lib}"] += 1

    # ---- slot time per program ----
    n_ok = sum(1 for p in progs if p["category"] == "ok")
    slot90 = [r["slot_s"] for r in meas if r.get("limit_s") == 90 and r.get("slot_s") is not None]
    slot330 = [r["slot_s"] for r in meas if r.get("limit_s") == 330 and r.get("slot_s") is not None]
    runs_per_prog = len(main_rows) / n_ok if n_ok else None
    sec90_per_run = st.mean(slot90) if slot90 else None
    nr90 = [r for r in main_rows if r.get("no_return_90")]
    share_nr = {sc: sum(1 for r in nr90 if r["scenario"] == sc) / max(1, sum(1 for r in main_rows if r["scenario"] == sc))
                for sc in ("S1", "S2", "S3", "S4")}

    # ---- E7 cost estimate ----
    prompt_chars = {}
    for c in CONDS:
        xs = [len(f.read_text()) for f in (REPO / "tasks").glob(f"*/prompts/*/{c}.txt")]
        prompt_chars[c] = {"n": len(xs), "mean": st.mean(xs) if xs else None}
    pil_chars = [len(f.read_text()) for f in (REPO / "pilot" / "tasks").glob("*/prompts/*/C0.txt")]
    in_tok = [g["meta"]["input_tokens"] for g in gens if g["meta"].get("status") == "ok" and g["meta"].get("input_tokens")]
    chars_per_tok = st.mean(pil_chars) / st.mean(in_tok) if in_tok else 3.5
    bench_in_tok = st.mean([prompt_chars[c]["mean"] for c in CONDS]) / chars_per_tok
    out_scen = {
        "low (Nemotron mean)": gen_out.get("nemotron-3-ultra", {}).get("output_tokens", {}).get("mean"),
        "mid (mean of both pilot models)": st.mean([g["meta"]["output_tokens"] for g in gens
                                                    if g["meta"].get("status") == "ok" and g["model"] != "north-mini-code"]),
        "high (p90 over both pilot models)": q([g["meta"]["output_tokens"] for g in gens
                                                if g["meta"].get("status") == "ok" and g["model"] != "north-mini-code"], 0.9),
    }
    prices = {m["id"]: (float(m["prompt_usd_per_tok"]), float(m["completion_usd_per_tok"]))
              for m in json.loads((OUT / "price_snapshot.json").read_text())["models"]}
    n_req_model = N_BENCH_TASKS * N_LANGS * N_SAMPLES * len(CONDS)
    cost = []
    for name, lid, bid in TABLE_VI:
        row = {"model": name, "list_id": lid, "batch_id": bid, "requests": n_req_model}
        for sk, ot in out_scen.items():
            pi, po = prices[lid]
            row[f"list_usd {sk}"] = n_req_model * (bench_in_tok * pi + ot * po)
            if bid:
                bi, bo = prices[bid]
                row[f"batch_usd {sk}"] = n_req_model * (bench_in_tok * bi + ot * bo)
        cost.append(row)
    totals = {}
    for sk in out_scen:
        totals[f"list {sk}"] = sum(r[f"list_usd {sk}"] for r in cost)
        totals[f"batch-where-available {sk}"] = sum(r.get(f"batch_usd {sk}", r[f"list_usd {sk}"]) for r in cost)

    # ---- E8 machine-time estimate ----
    n_programs = 8 * N_BENCH_TASKS * N_LANGS * N_SAMPLES * len(CONDS)
    bench_scen = []
    for t in sorted((REPO / "tasks").glob("*/expected.yaml")):
        import yaml
        bench_scen.append(len(yaml.safe_load(t.read_text())["scenarios"]))
    runs_bench = n_programs * st.mean(bench_scen)
    e8 = {"programs": n_programs, "mean_scenarios_per_task": st.mean(bench_scen), "runs_90": runs_bench,
          "slot_s_per_run_90_pilot": sec90_per_run,
          "container_hours_90": runs_bench * (sec90_per_run or 0) / 3600}
    # 330 s reruns: brief rule S1-S3 all no-return + S4 (aiohttp + 10 %); upper bound: all no-return in S1-S4
    rerun_s = st.mean(slot330) if slot330 else 330
    per_prog_rr_s123 = sum(share_nr[s] for s in ("S1", "S2", "S3"))
    e8["rerun_share_no_return_pilot"] = share_nr
    e8["container_hours_330_S1-S3"] = n_programs * per_prog_rr_s123 * rerun_s / 3600
    e8["container_hours_330_S4_all_no_return (upper bound)"] = n_programs * share_nr["S4"] * rerun_s / 3600
    e8["container_hours_330_S4_10pct"] = n_programs * share_nr["S4"] * 0.10 * rerun_s / 3600
    e8["total_container_hours_brief_rule"] = e8["container_hours_90"] + e8["container_hours_330_S1-S3"] + e8["container_hours_330_S4_10pct"]
    e8["total_container_hours_upper"] = e8["container_hours_90"] + e8["container_hours_330_S1-S3"] + e8["container_hours_330_S4_all_no_return (upper bound)"]
    for k in (5, 16, 32):
        e8[f"days_on_{k}_slots_brief_rule"] = e8["total_container_hours_brief_rule"] / k / 24
        e8[f"days_on_{k}_slots_upper"] = e8["total_container_hours_upper"] / k / 24

    res = {"run": a.run, "generation": gen_out, "categories": {k: dict(v) for k, v in cats.items()},
           "prepare_failures": reasons, "outcomes_90": {k: dict(v) for k, v in sorted(outc.items())},
           "allowed_90": {k: {str(b): n for b, n in v.items()} for k, v in sorted(allowed.items())},
           "s0_not_correct": s0_fail, "outcomes_330": {f"{s}/{o}": n for (s, o), n in sorted(long_out.items())},
           "libraries_in_runnable_programs": dict(libs),
           "run_summary": summ, "runnable_programs": n_ok, "runs_per_runnable_program": runs_per_prog,
           "slot_s_per_run_90": desc(slot90), "slot_s_per_rerun_330": desc(slot330),
           "e7": {"chars_per_input_token_pilot": chars_per_tok, "benchmark_prompt_chars": prompt_chars,
                  "benchmark_input_tokens_est": bench_in_tok, "output_token_scenarios": out_scen,
                  "requests_per_model": n_req_model, "per_model": cost, "totals_usd": totals},
           "e8": e8}
    OUT.mkdir(exist_ok=True)
    (OUT / "pilot_summary.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("categories", "runnable_programs", "s0_not_correct", "outcomes_330",
                                          "libraries_in_runnable_programs")}, indent=1))
    print(json.dumps(res["e7"]["totals_usd"], indent=1))
    print(json.dumps(e8, indent=1))


if __name__ == "__main__":
    main()
