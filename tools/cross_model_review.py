"""Independent reviews by non-Claude models (D48): the manuscript and the measure code, sent to GPT-6.1 Sol and Gemini
4 Argon through OpenRouter. Paid; run only with the author's approval.

  python3 tools/cross_model_review.py [--dry-run] [--cap-usd 3]

Two requests per model:
  paper   - referee report on SQJ_submission/latex_source/paper.tex (desk-reject risks, unsupported claims,
            statistical problems, inconsistencies);
  code    - bug hunt in analysis/measures.py against protocol/ANALYSIS_PLAN.md and protocol/thresholds.json.
Outputs reports/reviews_round7/xmodel_<model>_<kind>.md and appends the cost of each request to
reports/reviews_round7/xmodel_costs.jsonl. The API key is read from OPENROUTER_API_KEY and never printed or stored.
The cap is checked before each request against a worst-case estimate (input tokens + max_tokens at list price).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAPER = REPO.parent / "SQJ_submission" / "latex_source" / "paper.tex"
OUT = REPO / "reports" / "reviews_round7"
MODELS = [("gpt-6.1-sol", "openai/gpt-6.1-sol"), ("gemini-4-argon", "google/gemini-4-argon")]
PRICE_IN, PRICE_OUT = 2.0, 10.0  # USD per million tokens, both models (gen/config/confirm_sync.json)
MAX_OUT = 16000

PAPER_PROMPT = """You are a demanding referee for Springer's Software Quality Journal. Below is the full LaTeX source of a
submitted empirical software engineering paper. Write a referee report. Be concrete and skeptical; do not praise
generically. Cover: (1) issues that could lead to desk rejection or major revision; (2) claims in the abstract,
introduction or conclusions that the results do not support; (3) statistical or methodological errors (unit of
analysis, multiple testing, post-hoc analyses presented as confirmatory, separation, power); (4) internal
inconsistencies between numbers in different places (quote both places); (5) missing threats to validity;
(6) unclear, padded, or machine-sounding writing, and tables or figures that are hard to read; (7) whether the
number of tasks, languages, models, samples and fault cases is enough for the claims, and which additional
experiments a referee would demand. For each point give severity (critical/major/minor), location, and a concrete fix.
End with your recommendation (accept / minor / major / reject) and the three changes that would most improve the
chance of acceptance.

=== paper.tex ===
"""

CODE_PROMPT = """You are reviewing research code for correctness. The study runs generated HTTP client code against a
fault-injecting mock and computes per-run measures. Below are the analysis plan, the thresholds, and the measure
implementation. Find bugs: places where the code does not compute what the plan defines, edge cases that are
mishandled (multiple calls per run, polling tasks, missing records, time units, off-by-one in attempt counts,
windows, reruns), and anything that would bias a reported rate. For each finding give the function and line,
a concrete input that triggers it, and the likely effect. Say explicitly if you find nothing serious.

"""


def tokens(s: str) -> int:
    return len(s) // 3  # conservative for LaTeX/code


def ask(model: str, prompt: str) -> dict:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": MAX_OUT}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={
        "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json",
        "X-Title": "research-review"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cap-usd", type=float, default=3.0)
    ap.add_argument("--out", default=str(OUT), help="output folder (round 8: reports/reviews_round8)")
    ap.add_argument("--kinds", default="paper,code", help="comma-separated: paper, code")
    a = ap.parse_args()
    out = Path(a.out)
    code = "".join(f"\n=== {p} ===\n" + (REPO / p).read_text() for p in
                   ("protocol/ANALYSIS_PLAN.md", "protocol/thresholds.json", "analysis/measures.py"))
    jobs = [(mid, slug, kind, (PAPER_PROMPT + PAPER.read_text()) if kind == "paper" else CODE_PROMPT + code)
            for mid, slug in MODELS for kind in a.kinds.split(",")]
    costs = out / "xmodel_costs.jsonl"
    spent = sum(json.loads(x)["usd"] for x in costs.read_text().splitlines() if x.strip()) if costs.exists() else 0.0
    out.mkdir(parents=True, exist_ok=True)
    for mid, slug, kind, prompt in jobs:
        dst = out / f"xmodel_{mid}_{kind}.md"
        worst = (tokens(prompt) * PRICE_IN + MAX_OUT * PRICE_OUT) / 1e6
        print(f"{mid} {kind}: ~{tokens(prompt)} input tokens, worst case {worst:.2f} USD, spent so far {spent:.2f}")
        if dst.exists():
            print("  done already, skipped")
            continue
        if spent + worst > a.cap_usd:
            print("  would exceed the cap, stopped")
            break
        if a.dry_run:
            spent += worst
            continue
        t0 = time.time()
        r = ask(slug, prompt)
        u = r.get("usage", {})
        usd = (u.get("prompt_tokens", 0) * PRICE_IN + u.get("completion_tokens", 0) * PRICE_OUT) / 1e6
        if isinstance(u.get("cost"), (int, float)):
            usd = float(u["cost"])
        spent += usd
        text = r["choices"][0]["message"].get("content") or ""
        dst.write_text(f"# {mid} — {kind} review\n\nModel: {r.get('model', slug)}; {u.get('prompt_tokens')} input / "
                       f"{u.get('completion_tokens')} output tokens; {usd:.3f} USD; {time.time() - t0:.0f} s\n\n{text}\n")
        with open(costs, "a") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": mid, "kind": kind, "usd": usd,
                                "usage": u}) + "\n")
        print(f"  {usd:.3f} USD -> {dst.name}")
    print(f"total spent on cross-model reviews: {spent:.2f} USD")


if __name__ == "__main__":
    main()
