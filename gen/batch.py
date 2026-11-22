"""Batch generation through the OpenRouter Batch API (brief 2.3: use batch APIs).

  python3 gen/batch.py submit --config gen/config/main.json --model ID [--cond C0] [--limit N] [--dry-run]
  python3 gen/batch.py poll   --config gen/config/main.json [--wait]
  python3 gen/batch.py project --config gen/config/main.json   # spent, projection per model

API (https://openrouter.ai/docs/guides/features/batch-api, read 2026-11-06):
  POST /api/v1/batches  {endpoint, model, [provider], completion_window, requests:[{custom_id, body}]}
       (the other fields must precede "requests"); GET /api/v1/batches/{id}; no cancel.
  Results arrive unordered as {custom_id, response:{status_code, body}, error}; a completed batch
  can contain failed items. Billing is estimated and reserved at submit.

Layout and files are the same as gen/generate.py (request.json, response.json, attempts.jsonl,
solution.<ext>, meta.json per sample), plus data/<run>/batches/<batch_id>.json with the submit
record (without credentials) and the final batch object.

Rules (same as generate.py): benchmark tasks only after protocol/FREEZE.json exists; a paid
model needs BUDGET_USD; before a submit, spent + the worst case of the whole batch must stay
under the cap; costs.jsonl gets one line per billed request, priced at the config's batch price.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import extract as X  # noqa: E402
import generate as G  # noqa: E402
import providers as PV  # noqa: E402

API = "https://openrouter.ai/api/v1/batches"
TERMINAL = {"completed", "failed", "expired", "cancelled"}


def http(method, url, key, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"raw": txt[:2000]}


def cid(cond, task, lang, sample):
    return f"{cond}_{task}_{lang}_{sample}"  # providers allow only [A-Za-z0-9_-] (Anthropic)


def parse_cid(c):
    """Inverse of cid(); also reads the earlier '|' form (probe batch submitted before the change)."""
    return c.split("|") if "|" in c else c.split("_")


def pending(cfg, m, conds, base):
    for cond in conds:
        for task in cfg["tasks"]:
            for lang in cfg["langs"]:
                for s in range(1, cfg["samples"] + 1):
                    if not G.selected(cfg, cond, m["id"], task, lang, s):
                        continue
                    out = base / "generations" / cond / m["id"] / task / lang / str(s)
                    mp = out / "meta.json"
                    if mp.exists():
                        st = json.loads(mp.read_text()).get("status")
                        if st in ("ok", "submitted"):
                            continue
                    yield cond, task, lang, s, out


def outstanding(base):
    """Worst case of submitted batches not yet collected (they are billed on completion)."""
    d = base / "batches"
    return sum(json.loads(p.read_text())["worst_case_usd"] for p in d.glob("*.json")
               if not json.loads(p.read_text()).get("collected")) if d.exists() else 0.0


def project(cfg):
    """Spent so far and the projection to all requests of each model, from costs.jsonl."""
    base = REPO / "data" / cfg["run"]
    rows = [json.loads(l) for l in (base / "costs.jsonl").read_text().splitlines()] if (base / "costs.jsonl").exists() else []
    n_total = len(cfg["conditions"]) * len(cfg["tasks"]) * len(cfg["langs"]) * cfg["samples"]
    out = {}
    for m in cfg["models"]:
        r = [x for x in rows if x["model_id"] == m["id"]]
        ok = sum(1 for p in (base / "generations").glob(f"*/{m['id']}/*/*/*/meta.json")
                 if json.loads(p.read_text()).get("status") == "ok") if (base / "generations").exists() else 0
        spent = sum(x["usd"] for x in r)
        out[m["id"]] = {"ok": ok, "billed": len(r), "spent_usd": round(spent, 4),
                        "mean_output_tokens": round(sum(x["output_tokens"] or 0 for x in r) / len(r)) if r else None,
                        "projected_usd_all": round(spent / len(r) * n_total, 2) if r else None,
                        "high_scenario_usd": m.get("high_scenario_usd")}
    out["_total"] = {"spent_usd": round(sum(x["usd"] for x in rows), 4), "outstanding_worst_usd": round(outstanding(base), 2),
                     "cap_usd": G.Budget(base / "costs.jsonl").cap}
    return out


def submit(cfg, m, conds, limit, dry, http_fn=http, key=None):
    G.check_tasks_allowed(cfg["tasks"])
    base = REPO / "data" / cfg["run"]
    budget = G.Budget(base / "costs.jsonl")
    items = list(pending(cfg, m, conds, base))[: limit or None]
    if not items:
        return {"submitted": 0}
    reqs, worst = [], 0.0
    for cond, task, lang, s, out in items:
        prompt = G.prompt_for(task, lang, cond, cfg, m["id"], s)
        c = dict(m)
        params = dict(c.get("params") or {})
        if c.get("seed_param"):
            params[c["seed_param"]] = 1000 * s + 1
        c["params"] = params
        body = {"model": c["model"], "messages": [{"role": "user", "content": prompt}], **params}  # = sync body
        reqs.append({"custom_id": cid(cond, task, lang, s), "body": body, "_out": out, "_prompt": prompt, "_params": params})
        worst += G.worst_case_cost(m, prompt)
    paid = any((m.get("price_usd_per_mtok") or {}).get(k, 0) > 0 for k in ("input", "output"))
    if paid:
        if budget.cap is None:
            raise SystemExit("ABORT: model has a non-zero price and BUDGET_USD is not set")
        held = outstanding(base)
        if budget.spent + held + worst > budget.cap:
            raise SystemExit(f"ABORT: spent {budget.spent:.2f} + outstanding batches {held:.2f} + worst case of this batch "
                             f"{worst:.2f} > cap {budget.cap:.2f} USD (use --limit to submit a smaller batch)")
    head = {"endpoint": "/v1/chat/completions", "model": m["model"]}
    if m.get("batch_provider_only"):
        head["provider"] = {"only": m["batch_provider_only"], "allow_fallbacks": False}
    head["completion_window"] = "24h"
    payload = {**head, "requests": [{"custom_id": r["custom_id"], "body": r["body"]} for r in reqs]}
    if dry:
        return {"dry": len(reqs), "worst_case_usd": worst, "bytes": len(json.dumps(payload))}
    status, resp = http_fn("POST", API, key or PV._key(m), payload)
    t = G.now()
    if status != 202 or not isinstance(resp, dict) or not resp.get("id"):
        raise SystemExit(f"submit failed: HTTP {status}: {json.dumps(resp)[:500]}")
    bid = resp["id"]
    (base / "batches").mkdir(parents=True, exist_ok=True)
    rec = {"batch_id": bid, "submitted": t, "model_id": m["id"], "model": m["model"], "conditions": conds,
           "n_requests": len(reqs), "worst_case_usd": worst, "head": head, "submit_response": resp,
           "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), "commit": G.git_commit()}
    (base / "batches" / f"{bid}.json").write_text(json.dumps(rec, indent=1))
    for r in reqs:
        out = r["_out"]
        out.mkdir(parents=True, exist_ok=True)
        cond, task, lang, s = parse_cid(r["custom_id"])
        (out / "request.json").write_text(json.dumps({
            "run": cfg["run"], "condition": cond, "model_id": m["id"], "task": task, "lang": lang, "sample": int(s),
            "prompt": r["_prompt"], "prompt_sha256": hashlib.sha256(r["_prompt"].encode()).hexdigest(),
            "request": {"url": API, "batch_head": head, "custom_id": r["custom_id"], "body": r["body"]},
            "batch_id": bid, "created": t}, indent=1, ensure_ascii=False))
        (out / "meta.json").write_text(json.dumps({"status": "submitted", "batch_id": bid, "model_id": m["id"],
                                                   "submitted": t}, indent=1))
    return {"submitted": len(reqs), "batch_id": bid, "worst_case_usd": worst}


def collect(cfg, models, bid, batch):
    """Writes per-sample files from a completed batch object. Returns counts."""
    base = REPO / "data" / cfg["run"]
    rec_p = base / "batches" / f"{bid}.json"
    rec = json.loads(rec_p.read_text())
    m = models[rec["model_id"]]
    budget = G.Budget(base / "costs.jsonl")
    counts = {"ok": 0, "api_error": 0}
    seen = set()
    for item in batch.get("results") or []:
        cond, task, lang, s = parse_cid(item["custom_id"])
        seen.add(item["custom_id"])
        out = base / "generations" / cond / m["id"] / task / lang / s
        with open(out / "attempts.jsonl", "a") as f:
            f.write(json.dumps({"attempt": 1, "t": G.now(), "batch_id": bid, "batch_item_id": item.get("id"),
                                "status": (item.get("response") or {}).get("status_code"),
                                "error": item.get("error")}, ensure_ascii=False) + "\n")
        resp = item.get("response") or {}
        if item.get("error") or resp.get("status_code") != 200:
            (out / "meta.json").write_text(json.dumps({"status": "api_error", "model_id": m["id"], "batch_id": bid,
                                                       "error": item.get("error"), "http_status": resp.get("status_code"),
                                                       "completed": G.now()}, indent=1))
            counts["api_error"] += 1
            continue
        raw = resp["body"]
        (out / "response.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))
        parsed = PV.parse({"provider": "openai_compat"}, raw)
        usd = G.price_of(m, parsed)
        if usd > 0:
            budget.charge({"t": G.now(), "run": cfg["run"], "model_id": m["id"], "condition": cond, "task": task,
                           "lang": lang, "sample": int(s), "batch_id": bid, "input_tokens": parsed.get("input_tokens"),
                           "output_tokens": parsed.get("output_tokens"), "usd": usd})
        ex = X.extract(parsed["text"], lang)
        if ex["code"] is not None:
            (out / f"solution.{X.EXT[lang]}").write_text(ex["code"])
        req = json.loads((out / "request.json").read_text())
        (out / "meta.json").write_text(json.dumps({
            "status": "ok", "model_id": m["id"], "model_requested": m["model"], "provider": m["provider"], "batch_id": bid,
            "model_returned": parsed.get("model_returned"), "provider_returned": parsed.get("provider_returned"),
            "response_id": parsed.get("response_id"), "finish_reason": parsed.get("finish_reason"),
            "input_tokens": parsed.get("input_tokens"), "output_tokens": parsed.get("output_tokens"),
            "reasoning_tokens": parsed.get("reasoning_tokens"), "latency_s": None, "api_attempts": 1, "usd": usd,
            "params": {k: v for k, v in req["request"]["body"].items() if k not in ("model", "messages")},
            "extraction": {k: v for k, v in ex.items() if k != "code"}, "response_chars": len(parsed["text"]),
            "completed": G.now()}, indent=1))
        counts["ok"] += 1
    # requests missing from the results are reset so that a later submit retries them
    for p in (base / "generations").glob(f"*/{m['id']}/*/*/*/meta.json"):
        mm = json.loads(p.read_text())
        if mm.get("status") == "submitted" and mm.get("batch_id") == bid:
            cond, _, task, lang, s = p.parent.parts[-5:]
            if cid(cond, task, lang, s) not in seen:
                p.write_text(json.dumps({"status": "api_error", "model_id": m["id"], "batch_id": bid,
                                         "error": f"missing from batch results (batch status {batch.get('status')})",
                                         "completed": G.now()}, indent=1))
                counts["api_error"] += 1
    rec.update(final=batch, collected=G.now(), counts=counts, usage=batch.get("usage"))
    rec_p.write_text(json.dumps(rec, indent=1))
    return counts


def poll(cfg, wait, http_fn=http, key=None):
    base = REPO / "data" / cfg["run"]
    models = {m["id"]: m for m in cfg["models"]}
    while True:
        open_ = []
        for p in sorted((base / "batches").glob("*.json")) if (base / "batches").exists() else []:
            rec = json.loads(p.read_text())
            if rec.get("collected"):
                continue
            st, b = http_fn("GET", f"{API}/{rec['batch_id']}", key or PV._key(models[rec["model_id"]]))
            if st == 429:
                open_.append(rec["batch_id"])
                continue
            if st != 200:
                print(f"{rec['batch_id']}: HTTP {st} {json.dumps(b)[:200]}", flush=True)
                open_.append(rec["batch_id"])
                continue
            status = b.get("status")
            if status in TERMINAL and (status != "completed" or b.get("results") is not None):
                c = collect(cfg, models, rec["batch_id"], b)
                print(f"{rec['batch_id']} {rec['model_id']}: {status} {c} usage={b.get('usage')}", flush=True)
            else:
                print(f"{rec['batch_id']} {rec['model_id']}: {status} {b.get('request_counts')}", flush=True)
                open_.append(rec["batch_id"])
        if not wait or not open_:
            return open_
        time.sleep(60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "poll", "project"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--model", default="")
    ap.add_argument("--cond", action="append")
    ap.add_argument("--limit", type=int, default=0, help="submit only the first N pending requests (5%% probe)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    if a.cmd == "submit":
        m = {x["id"]: x for x in cfg["models"]}[a.model]
        if m.get("mode") != "batch":
            raise SystemExit(f"{a.model} is not configured for batch (mode={m.get('mode')}); use gen/generate.py")
        print(json.dumps(submit(cfg, m, a.cond or cfg["conditions"], a.limit, a.dry_run)))
    elif a.cmd == "poll":
        print(json.dumps({"open": poll(cfg, a.wait)}))
    else:
        print(json.dumps(project(cfg), indent=1))


if __name__ == "__main__":
    main()
