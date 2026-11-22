"""Print one run as a readable timeline next to the measures computed from it (for a manual audit).

  python3 tools/show_run.py data/main/runs/C0/gpt-6.1-sol/R5/python/2/S4

Shows: the call(s) and their result, every request to the faulted dependency (time since the call started, method,
path, logical key, response status / fault), raw SYNs under connection-level faults, and then every measure that
analysis/measures.py computes for this run. Times are seconds since the start of the (first) measured call.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402
import checkers_confirm  # noqa: E402  (R6, W5, B5, H4 of the confirmatory run; other tasks unchanged)
checkers_confirm.install()
import yaml  # noqa: E402


def main():
    d = Path(sys.argv[1]).resolve()
    run = M.load_run(d)
    orch = run["orch"] or {}
    task, sc = orch.get("task"), orch.get("scenario")
    calls = (run["result"] or {}).get("calls") or []
    t0 = min((c["t_start"] for c in calls if c.get("t_start")), default=0)

    def t(ns):
        return f"{(ns - t0) / 1e9:8.3f}s" if ns else "       ?"
    print(f"run {d.relative_to(REPO)}\ntask {task}  scenario {sc}  lang {orch.get('lang')}")
    print("\n-- calls")
    for c in calls:
        print(f"  #{c.get('index')} start {t(c.get('t_start'))} end {t(c.get('t_end'))} status {c.get('status')} "
              f"duration {c.get('duration_s')} value {str(c.get('value') or c.get('error'))[:120]}")
    resp = {r.get("req_id"): r for r in run["responses"]}
    print("\n-- requests (all dependencies)")
    for q in sorted(run["requests"], key=lambda q: q.get("t_first_byte") or 0):
        if q.get("role") != "dep":
            continue
        r = resp.get(q.get("req_id"), {})
        print(f"  {t(q.get('t_first_byte'))} port {q.get('port')} {q.get('method')} {q.get('path')} "
              f"key={q.get('logical_key')} -> {r.get('status')} fault={r.get('fault')} outcome={r.get('outcome')}")
    if run["syns"]:
        print("\n-- SYNs (connection attempts seen by packet capture)")
        for s in sorted(run["syns"], key=lambda s: s["t"]):
            print(f"  {t(s['t'])} dst_port {s['dst_port']} src_port {s.get('src_port')} retransmission={s['retransmission']}")
    print("\n-- effects (state changes)")
    for e in run["effects"]:
        print(f"  {t(e.get('t'))} {json.dumps({k: v for k, v in e.items() if k not in ('t',)})[:160]}")
    exp = yaml.safe_load((M.task_dir(task) / "expected.yaml").read_text())
    row = M.compute(run, exp, cond=d.parts[-6] if len(d.parts) > 6 else "C0")
    print("\n-- measures (analysis/measures.py)")
    for k in ("status", "durations_s", "no_return", "no_return_90", "time_limit_s", "overrun", "outcome", "outcome_allowed",
              "silent_failure", "attempts_per_logical_call", "rapid_retries", "excessive_retries", "attempts_within_30s",
              "attempts_during_outage", "retry_after_violation", "retry_after_gaps_s", "sync_retries", "sync_shares",
              "unsafe_write_retry", "late_requests", "harness_ok"):
        if k in row:
            print(f"  {k}: {row[k]}")


if __name__ == "__main__":
    main()
