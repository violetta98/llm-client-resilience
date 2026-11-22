"""Experiment B (repair with fault-injection feedback; protocol/REPAIR_ADDENDUM.md): build one repair prompt per
C0 solution of the main run that failed at least one fault test.

  python3 gen/repair_prompts.py [--src main] [--run repair] [--dry-run]

Reads  analysis/out/<src>/runs.jsonl, data/<src>/generations/C0/<model>/<task>/<lang>/<sample>/solution.<ext> (the extracted code),
       tasks/<task>/prompts/<lang>/C0.txt
Writes data/<run>/prompts/R0/<model>/<task>/<lang>/<sample>.txt   the prompt sent to the model that wrote the solution
       data/<run>/prompts/selection.csv                           one row per selected solution and failed test

A solution is selected when, in some 90 s run of the main experiment, it (a) did not return, (b) overran its time
limit, (c) made excessive or rapid retries in S7 or S9, (d) violated Retry-After in S6, (e) repeated a write in S8,
or (f) returned a result the task does not allow (silent failure). The report states the stub's behaviour, what was
observed and what the test expects, in the words of Tables III-V of the paper; it does not say how to fix the code.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = ("cond", "model", "task", "lang", "sample")
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
FENCE = {"python": "python", "typescript": "typescript", "java": "java", "go": "go"}
LAST_LINE = "Respond with the complete code in a single code block."

# faulted request per task (paper Table IV)
FAULTED = {"R1": "the request", "R2": "the request", "R3": "the download request", "R4": "the request for the second page",
           "R5": "the flag request", "W1": "the payment request", "W2": "the SMS request", "W3": "the upload request",
           "W4": "the cancel request", "B1": "the request for the fifth record", "B2": "the status request",
           "B3": "the API call (the token request works normally)", "B4": "the webhook request",
           "H1": "the recommendations request", "H2": "the readiness request",
           "H3": "the request to one of the three suppliers"}
# correct behaviour under faults (paper Table IV)
CORRECT = {"R1": "the correct result, or an error", "R2": "the correct result, or an error",
           "R3": "the correct result, or an error; never a partial file reported as complete",
           "R4": "all orders, or an error; never a partial list returned as complete",
           "R5": "the documented default value", "W1": "at most one payment; every retry reuses the same Idempotency-Key",
           "W2": "at most one SMS; an error when the outcome is unknown",
           "W3": "success or an error", "W4": "success or an error (a 404 after a retried DELETE counts as success)",
           "B1": "all records, or an error, within 30 s; no record skipped silently",
           "B2": "the export result, or an error, within 30 s", "B3": "the result, or an error, within 30 s",
           "B4": "at most one delivery per event ID, or an error, within 30 s",
           "H1": "the profile without recommendations within 2 s", "H2": "\"not ready\" within 1 s",
           "H3": "the best price of the other two suppliers within 3 s"}
LIMIT = {"B1": 30, "B2": 30, "B3": 30, "B4": 30, "H1": 2, "H2": 1, "H3": 3}

STUB = {
    "S1": "The API host does not answer TCP connection attempts (SYN packets are dropped).",
    "S2": "The API host accepts the TCP connection but never answers the TLS handshake.",
    "S3": "The API reads {req} but never sends a response.",
    "S4": "For {req}, the API sends the response headers with Content-Length: 4096 and then sends the body at one byte "
          "every 2 s.",
    "S5a": "The API answers {req} with 503 twice, then succeeds.",
    "S5b": "The API answers {req} with 503 and \"Retry-After: 1\" twice, then succeeds.",
    "S6a": "The API answers {req} with 429 and \"Retry-After: 3\", then succeeds.",
    "S6b": "The API answers {req} with 429 and a Retry-After header that gives an HTTP date 3 s in the future, then "
           "succeeds.",
    "S7": "The API answers every request with 503 for 30 s, then recovers; ten calls of the function run concurrently.",
    "S8": "The API processes {req}, then resets the connection without sending a response (first attempt only).",
    "S9": "Connections to the API host are refused immediately.",
    "S0": "The API behaves normally.",
}


def bound(task):
    return f"within its time limit of {LIMIT[task]} s" if task in LIMIT else "within 90 s"


def failures(task, runs):
    """list of (scenario, observed, expected) for the failed tests of one solution, in scenario order."""
    out = []
    order = ["S0", "S1", "S2", "S3", "S4", "S5a", "S5b", "S6a", "S6b", "S7", "S8", "S9"]
    for r in sorted(runs, key=lambda r: order.index(r["scenario"])):
        sc = r["scenario"]
        apc = r.get("attempts_per_logical_call") or {}
        mx = max(apc.values()) if apc else None
        if r.get("no_return"):
            out.append((sc, "the call had not returned or raised after 90 s",
                        f"the call returns or raises an error {bound(task)}"))
        elif r.get("overrun"):
            d = max(x for x in (r.get("durations_s") or [0]) if x is not None)
            out.append((sc, f"the call returned after {d:.1f} s", f"the call returns or raises an error {bound(task)}"))
        if sc in ("S7", "S9") and (r.get("excessive_retries") or r.get("rapid_retries")):
            obs = f"one call made {mx} attempts" + (" during the 30 s outage" if sc == "S7" else " within 30 s")
            if r.get("rapid_retries"):
                obs += ", with less than 100 ms between consecutive attempts"
            out.append((sc, obs, "at most 10 attempts per call within 30 s, with a delay between attempts"))
        if sc in ("S6a", "S6b") and r.get("retry_after_violation"):
            out.append((sc, "the function sent the next attempt earlier than Retry-After allowed",
                        "no attempt before the time given by Retry-After"))
        if sc == "S8" and r.get("unsafe_write_retry"):
            what = {"W2": "the request was sent again and the SMS was sent twice",
                    "W1": "a second payment was created because the retry did not reuse the Idempotency-Key",
                    "B4": "the webhook was delivered twice because the retry did not reuse the event ID"}[task]
            out.append((sc, what, CORRECT[task]))
        if r.get("silent_failure"):
            out.append((sc, "the function returned a result that the task does not allow under this fault",
                        CORRECT[task]))
    return out


REVIEW_REQUEST = ("Review this function for resilience to a slow, failing, or rate-limiting API, and improve it where "
                  "needed. It must still work when the API behaves normally.")


def render_review(task, lang, code):
    """Arm R1 (D39): the same solution, without any test report."""
    base = (REPO / "tasks" / task / "prompts" / lang / "C0.txt").read_text().rstrip("\n")
    assert base.endswith(LAST_LINE), (task, lang)
    base = base[: -len(LAST_LINE)].rstrip("\n")
    lines = [base, "", "Here is a solution to this task:", f"```{FENCE[lang]}", code.rstrip("\n"), "```", "",
             REVIEW_REQUEST, LAST_LINE]
    return "\n".join(lines) + "\n"


def render(task, lang, code, fails):
    base = (REPO / "tasks" / task / "prompts" / lang / "C0.txt").read_text().rstrip("\n")
    assert base.endswith(LAST_LINE), (task, lang)
    base = base[: -len(LAST_LINE)].rstrip("\n")
    lines = [base, "", "Here is a solution to this task:", f"```{FENCE[lang]}", code.rstrip("\n"), "```", "",
             "We ran this function against a test double of the API. These tests failed:"]
    for i, (sc, obs, exp) in enumerate(fails, 1):
        lines.append(f"{i}. {STUB[sc].format(req=FAULTED[task])} Observed: {obs}. Expected: {exp}.")
    lines += ["", "Fix the function so that these tests pass and it still works when the API behaves normally.", LAST_LINE]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="main")
    ap.add_argument("--run", default="repair")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--arm", choices=["R0", "R1"], default="R0", help="R0: test report (B); R1: review request without report (D39)")
    a = ap.parse_args()
    per = defaultdict(list)
    for line in open(REPO / "analysis" / "out" / a.src / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r["limit_s"] == 90 and r["cond"] == "C0":
            per[tuple(str(r[k]) for k in KEYS)].append(r)
    outdir = REPO / "data" / a.run / "prompts"
    sel, chars = [], []
    r0 = None
    if a.arm == "R1":  # D39: exactly the solutions selected for R0 (data/<run>/prompts/selection.csv)
        r0 = {tuple(r[c] for c in KEYS) for r in csv.DictReader(open(outdir / "selection.csv"))}
    for k in sorted(per):
        fails = failures(k[2], per[k])
        if r0 is not None:
            if k not in r0:
                continue
        elif not fails:
            continue
        code = (REPO / "data" / a.src / "generations" / Path(*k) / f"solution.{EXT[k[3]]}").read_text()
        p = render(k[2], k[3], code, fails) if a.arm == "R0" else render_review(k[2], k[3], code)
        chars.append(len(p))
        for sc, obs, exp in fails:
            sel.append({**dict(zip(KEYS, k)), "scenario": sc, "observed": obs, "expected": exp})
        if not a.dry_run:
            f = outdir / a.arm / k[1] / k[2] / k[3] / f"{k[4]}.txt"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(p)
    if not a.dry_run and a.arm == "R0":
        with open(outdir / "selection.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, list(KEYS) + ["scenario", "observed", "expected"])
            w.writeheader()
            w.writerows(sel)
    n = len(chars)
    by_model = defaultdict(int)
    for k in {tuple(s[x] for x in KEYS) for s in sel}:
        by_model[k[1]] += 1
    print(json.dumps({"solutions": n, "failed_tests": len(sel), "mean_prompt_chars": round(sum(chars) / n),
                      "max_prompt_chars": max(chars), "by_model": dict(sorted(by_model.items()))}, indent=1))


if __name__ == "__main__":
    main()
