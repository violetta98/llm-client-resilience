"""Measures of draft Table V for one run (one program in one scenario).

Each measure is a small function of the raw run files; thresholds come from
protocol/thresholds.json. Raw quantities (attempt times, gaps, counts, per-k
shares) are kept in the output row so that other thresholds can be applied
later. Unit tests: tests/unit/test_measures.py.

Conventions (DEVIATIONS.md D14-D16):
- An attempt of a logical call is a request to the faulted dependency with
  that logical key (mock requests.jsonl), ordered by first byte. Under
  connection-level faults (S1, S2, S9) requests never arrive; attempts are
  then the client's connection attempts (new source ports in syns.jsonl),
  attributed to the single logical call the task makes first on that
  dependency. For B1 (20 independent records) that attribution is not
  possible: rapid/excessive retries are reported as None (raw counts kept).
- Synchronized retries consider attempt numbers k >= 2 (k = 1 is the
  initial request of each invocation, simultaneous by design).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
def task_dir(task: str) -> Path:
    """tasks/<ID>/ for benchmark tasks, pilot/tasks/<ID>/ for the pilot tasks P1-P3."""
    return REPO / ("pilot/tasks" if task.startswith("P") else "tasks") / task


TH = json.loads((REPO / "protocol" / "thresholds.json").read_text())
PORT = {"A": 9001, "B": 9002, "C": 9003}
CONN_FAULTS = ("S1", "S2", "S9")
# D36: java.net.http retries a failed connect once, immediately (Table I), so one connect call of the application
# shows up as two SYNs about 1-3 ms apart. Under connection-level faults, attempts are counted per connect call:
# a SYN that follows the previous one by less than CONNECT_RETRY_MERGE_S is merged with it, at most two SYNs per
# attempt. Raw SYN counts stay in n_conn_attempts_faulted_dep.
CONNECT_RETRY_MERGE_S = 0.005


def connect_calls(times, merge=CONNECT_RETRY_MERGE_S):
    out, i = [], 0
    while i < len(times):
        out.append(times[i])
        i += 2 if i + 1 < len(times) and times[i + 1] - times[i] < merge * 1e9 else 1
    return out
STALL = ("S1", "S2", "S3", "S4")


def jl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def load_run(d):
    d = Path(d)
    j = lambda n: json.loads((d / n).read_text()) if (d / n).exists() else None  # noqa: E731
    return {"dir": str(d), "result": j("result.json"), "timing": j("timing.json"), "mock": j("run.json"),
            "orch": j("orchestrator.json"), "requests": jl(d / "requests.jsonl"), "responses": jl(d / "responses.jsonl"),
            "effects": jl(d / "effects.jsonl"), "syns": jl(d / "syns.jsonl"), "conns": jl(d / "conns.jsonl")}


# ---------------------------------------------------------------- primitives
def rapid(times, gap=TH["rapid_gap_s"], k=TH["rapid_min_attempts"]):
    """>= k consecutive attempts with every gap < `gap` (s). times in ns."""
    run = 1
    for a, b in zip(times, times[1:]):
        run = run + 1 if (b - a) / 1e9 < gap else 1
        if run >= k:
            return True
    return False


def max_window_share(times, window=TH["sync_window_s"]):
    ts = sorted(times)
    best = 0
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > window * 1e9:
            j += 1
        best = max(best, i - j + 1)
    return best / len(ts) if ts else 0.0


def sync_shares(per_invocation, min_inv=TH["sync_min_invocations"], k0=TH["sync_from_attempt"]):
    """per_invocation: list of attempt-time lists. Returns {k: share} for k >= k0
    reached by at least min_inv invocations."""
    out = {}
    kmax = max((len(x) for x in per_invocation), default=0)
    for k in range(k0, kmax + 1):
        ts = [x[k - 1] for x in per_invocation if len(x) >= k]
        if len(ts) >= min_inv:
            out[k] = max_window_share(ts)
    return out


def invocation_of(key, s7_args):
    """Maps a logical key to the S7 invocation whose arguments it contains."""
    if not key:
        return None
    comps = set(key.split(":", 1)[-1].split("|"))  # exact components of the logical key
    for i, args in enumerate(s7_args):
        leaves = list(_leaves(args))
        shared = set(leaves)
        for other in s7_args:
            shared &= set(_leaves(other))
        if any(u in comps for u in leaves if u not in shared):
            return i
    return None


def _leaves(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _leaves(v)
    elif isinstance(x, list):
        for v in x:
            yield from _leaves(v)
    elif isinstance(x, str):
        yield x
        if "/instances/" in x:
            yield x.rsplit("/", 1)[-1]


# ---------------------------------------------------------------- the row
def compute(run, exp, cond="C0"):
    """run: load_run(); exp: tasks/<ID>/expected.yaml as dict."""
    from checkers import check  # noqa: E402 (sibling module)

    res = run["result"] or {}
    mock = run["mock"] or {}
    sc = mock.get("config", {}).get("scenario")
    task = exp["task"]
    fault_port = PORT[exp["fault_dependency"]]
    calls = res.get("calls") or []
    plan_calls = (run["orch"] or {}).get("plan", {}).get("calls", [])
    status = res.get("status")
    row = {"task": task, "scenario": sc, "cond": cond, "status": status, "run_id": mock.get("run_id"),
           "lang": res.get("lang"), "n_calls": len(calls)}
    limit = res.get("limit_s")

    # --- time to return / no return / overruns --------------------------------
    durs = [c.get("duration_s") for c in calls]
    row["durations_s"] = durs
    row["no_return"] = any(c.get("status") == "no_return" for c in calls) or status == "no_return"
    row["no_return_90"] = bool(row["no_return"] and sc in STALL)
    tl = exp.get("time_limit_s")
    row["time_limit_s"] = tl
    if tl is not None:
        row["overrun"] = row["no_return"] or any(d is not None and d > tl + TH["overrun_margin_s"] for d in durs)
    else:
        row["overrun"] = None
    if cond == "C2" and tl is None:
        row["c2_overrun"] = row["no_return"] or any(d is not None and d > TH["c2_limit_s"] for d in durs)
    else:
        row["c2_overrun"] = None

    # --- outcome per call -------------------------------------------------------
    outs = []
    for i, c in enumerate(calls):
        st = c.get("status")
        if st == "returned":
            args = plan_calls[i]["args"] if i < len(plan_calls) else None
            o = check(task, args, c, run["effects"], res.get("files"))
        elif st == "raised":
            o = "error"
        elif st == "harness_error":
            o = "harness_error"
        else:
            o = "no_return"
        outs.append(o)
    row["outcomes"] = outs
    allowed = exp["allowed_outcomes"].get(sc, [])
    row["outcome"] = outs[0] if len(outs) == 1 else (outs[0] if len(set(outs)) == 1 else "mixed")
    row["outcome_allowed"] = all(o in allowed for o in outs) if outs else False
    row["silent_failure"] = any(o == "silent_failure" for o in outs)
    if status in ("import_error", "warmup_no_return", None, "bad_result_json"):
        row["outcome"], row["outcome_allowed"] = status or "no_result", False

    # --- attempts per logical call on the faulted dependency --------------------
    reqs = sorted((q for q in run["requests"] if q["role"] == "dep" and q["port"] == fault_port and q.get("logical_key")),
                  key=lambda q: q["t_first_byte"])
    by_key = {}
    for q in reqs:
        by_key.setdefault(q["logical_key"], []).append(q)
    syn = sorted((s for s in run["syns"] if s["dst_port"] == fault_port and not s["retransmission"]), key=lambda s: s["t"])
    syn_times = [s["t"] for s in syn]
    row["n_requests_faulted_dep"] = len(reqs)
    row["n_conn_attempts_faulted_dep"] = len(syn)
    cap = mock.get("capture") or {}
    row["capture_complete"] = cap.get("packets_captured") == cap.get("packets_received_by_filter")
    nft = (mock.get("syn_packets_nft") or {}).get(str(fault_port))
    row["syn_packets_nft"] = nft
    if not row["capture_complete"] and nft is not None:
        # Kernel dropped capture packets (tight loops): the exact nftables SYN count
        # (it includes kernel retransmissions) replaces the sampled count.
        row["n_conn_attempts_faulted_dep"] = nft
        row["attempts_source"] = "nft_counter"
    attributable = not (task == "B1" and sc in CONN_FAULTS)
    if sc in CONN_FAULTS:
        calls_t = connect_calls(syn_times)
        row["n_connect_calls_faulted_dep"] = len(calls_t)
        seqs = {"(connection attempts)": calls_t}
    else:
        seqs = {k: [q["t_first_byte"] for q in v] for k, v in by_key.items()}
    row["attempts_per_logical_call"] = {k: len(v) for k, v in seqs.items()}
    row["rapid_retries"] = any(rapid(v) for v in seqs.values()) if attributable else None

    # --- Retry-After violation (S6) ---------------------------------------------
    row["retry_after_violation"] = None
    if sc in ("S6a", "S6b"):
        resp_by_req = {r["req_id"]: r for r in run["responses"]}
        viol, gaps = False, []
        for k, qs in by_key.items():
            for a, b in zip(qs, qs[1:]):
                r = resp_by_req.get(a["req_id"], {})
                if r.get("status") == 429 and r.get("t_head_sent"):
                    gap = (b["t_first_byte"] - r["t_head_sent"]) / 1e9
                    tol = TH["retry_after_tol_seconds_s"] if sc == "S6a" else TH["retry_after_tol_date_s"]
                    gaps.append(gap)
                    if gap < 3.0 - tol:
                        viol = True
        row["retry_after_violation"] = viol
        row["retry_after_gaps_s"] = gaps

    # --- excessive retries (S7 outage, S9 within 30 s) --------------------------
    row["excessive_retries"] = None
    if sc == "S7":
        start = mock.get("s7_outage_start_mono_ns") or 0
        counts = {}
        for k, qs in by_key.items():
            ts = [q["t_first_byte"] for q in qs if q["t_first_byte"] - start < TH["outage_s"] * 1e9]
            if task == "B2":  # polling requests count only after an error
                ts = ts[1:]
            counts[k] = len(ts)
        row["attempts_during_outage"] = counts
        row["excessive_retries"] = any(n > TH["excessive_attempts"] for n in counts.values())
        row["load_requests_per_logical_call"] = (sum(counts.values()) / len(counts)) if counts else 0.0
        row["load_requests_total"] = sum(counts.values())
    elif sc == "S9":
        ct = connect_calls(syn_times)
        n = len([t for t in ct if t - ct[0] < TH["excessive_window_s"] * 1e9])
        if not row["capture_complete"] and nft is not None:
            n = max(n, nft)  # S9 runs end within the window; retransmissions do not occur after RST
        if task == "B2":
            n = max(0, n - 1)
        row["attempts_within_30s"] = n
        row["excessive_retries"] = (n > TH["excessive_attempts"]) if attributable else None

    # --- late requests (within 5 s after the function returned) -----------------
    late = []
    s7_args = (exp.get("args") or {}).get("s7") or []
    plan_s7 = [c["args"] for c in plan_calls] if sc == "S7" else None
    for q in (q for q in run["requests"] if q["role"] == "dep"):
        if sc == "S7":
            i = invocation_of(q.get("logical_key"), plan_s7 or s7_args)
            c = calls[i] if i is not None and i < len(calls) else None
        else:
            c = calls[0] if calls else None
        te = c.get("t_end") if c else None
        if te is not None and 0 < q["t_first_byte"] - te <= TH["late_window_s"] * 1e9:
            late.append(q["req_id"])
    if sc in CONN_FAULTS and calls and calls[0].get("t_end"):
        te = calls[0]["t_end"]
        tol = TH["late_syn_tolerance_s"] * 1e9
        late += [f"syn@{s['src_port']}" for s in syn if tol < s["t"] - te <= TH["late_window_s"] * 1e9]
    row["late_requests"] = len(late)

    # --- synchronized retries (S7) ----------------------------------------------
    row["sync_retries"] = None
    if sc == "S7":
        per_inv = [[] for _ in calls]
        first_key = {}
        for q in reqs:
            i = invocation_of(q["logical_key"], plan_s7 or s7_args)
            if i is None or i >= len(per_inv):
                continue
            first_key.setdefault(i, q["logical_key"])
            if q["logical_key"] == first_key[i]:
                per_inv[i].append(q["t_first_byte"])
        shares = sync_shares(per_inv)
        row["sync_shares"] = shares
        # Auxiliary (D18): the same share computed on the retry intervals t_k - t_(k-1),
        # which detects missing jitter even when the first attempts are spread out.
        gaps = [[b - a for a, b in zip(x, x[1:])] for x in per_inv]
        row["sync_gap_shares"] = sync_shares([[0] + g for g in gaps]) if gaps else {}  # key k: interval t_k - t_(k-1)
        row["sync_gap_retries"] = any(v > TH["sync_threshold"] for v in row["sync_gap_shares"].values())
        row["attempt_times_s7"] = per_inv
        row["sync_retries"] = any(s > TH["sync_threshold"] for s in shares.values()) if shares else False
        row["unattributed_requests"] = sum(1 for q in reqs if invocation_of(q["logical_key"], plan_s7 or s7_args) is None)

    # --- unsafe write retry (S8) --------------------------------------------------
    row["unsafe_write_retry"] = None
    if sc == "S8":
        e = [x for x in run["effects"] if x.get("role") == "dep"]
        if task == "W1":
            per = {}
            for x in e:
                if x["kind"] == "payment_created":
                    per.setdefault(x["detail"]["order_id"], []).append(x)
            row["unsafe_write_retry"] = any(len(v) > 1 for v in per.values())
            keys = {}
            for q in reqs:
                keys.setdefault(q["logical_key"], set()).add(next((h["value"] for h in q["headers"] if h["name"].lower() == "idempotency-key"), ""))
            row["idempotency_keys_per_order"] = {k: sorted(v) for k, v in keys.items()}
        elif task == "W2":
            row["unsafe_write_retry"] = sum(1 for x in e if x["kind"] == "sms_sent") > 1
        elif exp.get("unsafe_effect"):  # pilot tasks: no idempotency support, any second effect is unsafe
            row["unsafe_write_retry"] = sum(1 for x in e if x["kind"] == exp["unsafe_effect"]) > 1
        elif task == "B4":
            # D59: the mock drops a repeated event ID itself, so a duplicate can only show up as a second accepted
            # delivery under a new event ID. Each S8 run delivers one event (one call), so any second accepted
            # delivery in the run is a duplicate.
            row["unsafe_write_retry"] = sum(1 for x in e if x["kind"] == "delivery_accepted") > 1
            row["deliveries_received"] = sum(1 for x in e if x["kind"] == "delivery_received")
        row["effects_count"] = {k: sum(1 for x in e if x["kind"] == k) for k in {x["kind"] for x in e}}

    # --- timing check -------------------------------------------------------------
    t = run["timing"] or {}
    row["clock_diff_s"] = t.get("diff_s")
    row["clock_flag"] = t.get("flag_disagreement")
    errs = [e for e in (mock.get("errors") or []) if not e.startswith("capture stop:")]
    # Incomplete capture is recorded (capture_complete) but does not invalidate a run
    # when the exact nftables counters are available.
    # D33: an unreadable RESULT line is a harness failure (the driver's report was lost), not a program outcome.
    row["harness_ok"] = bool(not errs and (row["capture_complete"] or nft is not None) and not t.get("flag_disagreement")
                             and status != "bad_result_json")
    return row
