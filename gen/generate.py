"""Generation (brief 3.7): one request per (condition, model, task, language,
sample), resumable and idempotent; every request, its parameters, the raw
response, token counts, latency and the model identifier returned by the API
are logged.

Usage:
  python3 gen/generate.py --config gen/config/pilot.json [--dry-run] [--only-model ID]

Layout (brief section 5):
  data/<run>/generations/<cond>/<model>/<task>/<lang>/<sample>/
      request.json   the request without credentials, rendered prompt, parameters
      response.json  the raw API response (last successful attempt)
      attempts.jsonl every HTTP attempt (status, error, latency) - also failures
      solution.<ext> the extracted code (absent for no_code)
      meta.json      tokens, latency, model returned, extraction result, cost
  data/<run>/costs.jsonl   one line per billed request
  data/<run>/manifest.json commit, versions, host, config hash

Safety rules enforced here (brief section 2):
  * Benchmark tasks are refused unless protocol/FREEZE.json exists (protocol
    frozen and deposited, E6). The pilot uses P1-P3 only.
  * A model with a non-zero price requires BUDGET_USD in the environment; a
    request is not sent if spent + its worst-case cost would exceed the cap.
  * API keys only from environment variables; never logged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "analysis"))
import extract as X  # noqa: E402
import providers as PV  # noqa: E402
from measures import task_dir  # noqa: E402

PILOT_TASKS = {"P1", "P2", "P3"}
MAX_API_ATTEMPTS = 6


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def git_commit():
    try:
        c = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return c + ("-dirty" if dirty else "")
    except OSError:
        return None


def check_tasks_allowed(tasks):
    bench = [t for t in tasks if t not in PILOT_TASKS]
    if bench and not (REPO / "protocol" / "FREEZE.json").exists():
        sys.exit(f"REFUSED: benchmark tasks {bench} may not be sent to any model before the protocol freeze "
                 "(protocol/FREEZE.json with the deposit DOI does not exist).")


def price_of(m, usage):
    pr = m.get("price_usd_per_mtok") or {"input": 0, "output": 0}
    return ((usage.get("input_tokens") or 0) * pr["input"] + (usage.get("output_tokens") or 0) * pr["output"]) / 1e6


def worst_case_cost(m, prompt):
    pr = m.get("price_usd_per_mtok") or {"input": 0, "output": 0}
    max_out = m.get("max_output_tokens_for_budget") or 64000
    return (len(prompt) / 2 * pr["input"] + max_out * pr["output"]) / 1e6  # >= 1 token per 2 chars


class Budget:
    """Spent is re-read from costs.jsonl before every check, so that parallel processes (one per sync model, plus
    gen/batch.py) share one cap; the worst case of uncollected batches counts as held."""

    def __init__(self, path):
        self.path = path
        cap = os.environ.get("BUDGET_USD")
        self.cap = float(cap) if cap else None
        self._load()

    def _load(self):
        self.spent = 0.0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.spent += json.loads(line).get("usd", 0.0)
        d = self.path.parent / "batches"
        self.held = sum(r["worst_case_usd"] for r in (json.loads(q.read_text()) for q in d.glob("*.json"))
                        if not r.get("collected")) if d.exists() else 0.0

    def allow(self, m, prompt):
        paid = any((m.get("price_usd_per_mtok") or {}).get(k, 0) > 0 for k in ("input", "output"))
        if not paid:
            return True, None
        if self.cap is None:
            return False, "model has a non-zero price and BUDGET_USD is not set"
        self._load()
        w = worst_case_cost(m, prompt)
        if self.spent + self.held + w > self.cap:
            return False, (f"budget: spent {self.spent:.4f} + outstanding batches {self.held:.2f} + worst case {w:.4f} "
                           f"> cap {self.cap:.2f} USD")
        return True, None

    def charge(self, rec):
        self.spent += rec["usd"]
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")


def prompt_for(task, lang, cond, cfg=None, model_id=None, sample=None):
    """The task prompt; for a run with "prompt_dir" (experiment B, repair) the per-solution prompt file."""
    if cfg and cfg.get("prompt_dir"):
        return prompt_file(cfg, cond, model_id, task, lang, sample).read_text()
    return (task_dir(task) / "prompts" / lang / f"{cond}.txt").read_text()


def prompt_file(cfg, cond, model_id, task, lang, sample):
    return REPO / cfg["prompt_dir"] / cond / model_id / task / lang / f"{sample}.txt"


def selected(cfg, cond, model_id, task, lang, sample):
    """Runs with "prompt_dir" send only the requests for which a prompt file exists."""
    return not cfg.get("prompt_dir") or prompt_file(cfg, cond, model_id, task, lang, sample).exists()


def generate_one(m, cond, task, lang, sample, out, budget, run, dry, cfg=None):
    meta_p = out / "meta.json"
    if meta_p.exists() and json.loads(meta_p.read_text()).get("status") in ("ok", "submitted"):
        return "skip"  # "submitted": in a pending batch (gen/batch.py)
    prompt = prompt_for(task, lang, cond, cfg, m["id"], sample)
    ok, why = budget.allow(m, prompt)
    while not ok and budget.held > 0 and budget.spent + budget.held < budget.cap:
        time.sleep(300)  # over the cap only because of uncollected batches' worst case: wait for them to be collected
        ok, why = budget.allow(m, prompt)
    if not ok:
        raise SystemExit(f"ABORT before {cond}/{m['id']}/{task}/{lang}/{sample}: {why}")
    cfg = dict(m)
    params = dict(cfg.get("params") or {})
    if cfg.get("seed_param"):  # per-sample seed where the API supports one
        params[cfg["seed_param"]] = 1000 * sample + 1
    cfg["params"] = params
    url, headers, body = PV.build_request(cfg, prompt) if not dry else (None, {}, None)
    if dry:
        return "dry"
    out.mkdir(parents=True, exist_ok=True)
    req = {"run": run, "condition": cond, "model_id": m["id"], "task": task, "lang": lang, "sample": sample,
           "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
           "request": PV.request_record(url, headers, body), "created": now()}
    (out / "request.json").write_text(json.dumps(req, indent=1, ensure_ascii=False))
    last_err = None
    max_att = m.get("max_api_attempts", MAX_API_ATTEMPTS)
    cap = m.get("backoff_cap_s", 60)
    for attempt in range(1, max_att + 1):
        t_start = now()
        try:
            rec, raw, parsed, lat = PV.send(cfg, prompt, timeout_s=m.get("request_timeout_s", 600))
        except PV.ProviderError as e:
            last_err = e
            with open(out / "attempts.jsonl", "a") as f:
                f.write(json.dumps({"attempt": attempt, "t": t_start, "status": e.status, "error": str(e),
                                    "body": e.body if isinstance(e.body, (str, dict)) else None}, ensure_ascii=False) + "\n")
            if not e.retryable or attempt == max_att:
                break
            try:
                wait = float(e.retry_after) if e.retry_after else None
            except ValueError:
                wait = None
            # full-jitter exponential backoff, per-model cap (free endpoints are rate-limited upstream)
            if e.status in (402, 403):
                wait = 300.0  # insufficient credits / key limit: wait for batch reservations to be released or a top-up
            time.sleep(min(max(300.0, cap), wait if wait is not None else random.uniform(min(cap, 2 ** attempt) / 2, min(cap, 2 ** attempt))))
            continue
        with open(out / "attempts.jsonl", "a") as f:
            f.write(json.dumps({"attempt": attempt, "t": t_start, "status": 200, "latency_s": lat}) + "\n")
        (out / "response.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))
        usd = price_of(m, parsed)
        if usd > 0:
            budget.charge({"t": now(), "run": run, "model_id": m["id"], "condition": cond, "task": task, "lang": lang,
                           "sample": sample, "input_tokens": parsed.get("input_tokens"),
                           "output_tokens": parsed.get("output_tokens"), "usd": usd})
        ex = X.extract(parsed["text"], lang)
        if ex["code"] is not None:
            (out / f"solution.{X.EXT[lang]}").write_text(ex["code"])
        meta = {"status": "ok", "model_id": m["id"], "model_requested": m["model"], "provider": m["provider"],
                "model_returned": parsed.get("model_returned"), "provider_returned": parsed.get("provider_returned"),
                "response_id": parsed.get("response_id"), "finish_reason": parsed.get("finish_reason"),
                "input_tokens": parsed.get("input_tokens"), "output_tokens": parsed.get("output_tokens"),
                "reasoning_tokens": parsed.get("reasoning_tokens"), "latency_s": lat, "api_attempts": attempt,
                "usd": usd, "params": params, "extraction": {k: v for k, v in ex.items() if k != "code"},
                "response_chars": len(parsed["text"]), "completed": now()}
        meta_p.write_text(json.dumps(meta, indent=1))
        return "ok"
    meta_p.write_text(json.dumps({"status": "api_error", "model_id": m["id"], "error": str(last_err),
                                  "http_status": getattr(last_err, "status", None), "completed": now()}, indent=1))
    return "api_error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-model", default="")
    ap.add_argument("--shard", default="", help="i/n: this process takes every n-th request starting at i (parallel workers)")
    ap.add_argument("--limit", type=int, default=0, help="send at most N new requests per model (5%% probe, PROTOCOL 6)")
    a = ap.parse_args()
    cfgp = Path(a.config)
    cfg = json.loads(cfgp.read_text())
    check_tasks_allowed(cfg["tasks"])
    run = cfg["run"]
    base = REPO / "data" / run
    base.mkdir(parents=True, exist_ok=True)
    man = base / "manifest.json"
    entry = {"t": now(), "commit": git_commit(), "config": str(cfgp), "config_sha256": hashlib.sha256(cfgp.read_bytes()).hexdigest(),
             "host": platform.platform(), "python": platform.python_version(), "models": cfg["models"]}
    hist = json.loads(man.read_text()) if man.exists() else {"generation_sessions": []}
    hist.setdefault("generation_sessions", []).append(entry)
    if not a.dry_run:
        man.write_text(json.dumps(hist, indent=1))
    budget = Budget(base / "costs.jsonl")
    counts = {}
    for m in cfg["models"]:
        if a.only_model and m["id"] != a.only_model:
            continue
        if m.get("mode") == "batch":
            print(f"{m['id']}: mode=batch, use gen/batch.py", flush=True)
            continue
        sent = 0
        si, sn = (int(x) for x in a.shard.split("/")) if a.shard else (0, 1)
        k = -1
        for cond in cfg["conditions"]:
            for task in cfg["tasks"]:
                for lang in cfg["langs"]:
                    for s in range(1, cfg["samples"] + 1):
                        if a.limit and sent >= a.limit:
                            break
                        if not selected(cfg, cond, m["id"], task, lang, s):
                            continue
                        k += 1
                        if k % sn != si:
                            continue
                        out = base / "generations" / cond / m["id"] / task / lang / str(s)
                        r = generate_one(m, cond, task, lang, s, out, budget, run, a.dry_run, cfg)
                        counts[r] = counts.get(r, 0) + 1
                        sent += r not in ("skip", "dry")
                        if r != "skip":
                            print(f"{cond} {m['id']} {task} {lang} {s}: {r}", flush=True)
                        if r == "ok" and m.get("min_interval_s"):
                            time.sleep(m["min_interval_s"])  # free-tier request rate
    print(json.dumps({"counts": counts, "spent_usd": round(budget.spent, 4)}))


if __name__ == "__main__":
    main()
