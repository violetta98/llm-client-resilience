"""E1 verification: a trivial solution (default HTTP client of each language)
runs through every scenario variant (S0-S9, incl. S8) in all four languages.

Checks are harness-level: a valid result, an agreeing external clock, a
complete packet capture, no mock errors, S7 shape. The observed behavior is
recorded (it is not the library-baseline study, which is E4).

Usage: python3 tests/integration/e1_verify.py [--slots N] [--langs python,go]
"""
import argparse
import concurrent.futures as cf
import json
import queue
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runner"))
import orchestrator as o  # noqa: E402
from prepare import prepare  # noqa: E402

TASK = json.loads((REPO / "tasks/R1/signature.json").read_text())
SOLUTIONS = {
    "python": ("tests/solutions/r1_requests_notimeout.py", TASK["python"]["function"]),
    "typescript": ("tests/solutions/ts/r1_fetch.ts", TASK["typescript"]["function"]),
    "java": ("tests/solutions/java/r1_httpclient.java", TASK["java"]["function"]),
    "go": ("tests/solutions/go/r1_nethttp.go", TASK["go"]["function"]),
}
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5a", "S5b", "S6a", "S6b", "S7", "S8", "S9"]
VALID = {"returned", "raised", "no_return", "mixed"}


def jl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def check(lang, sc, r):
    res = r["result"] or {}
    problems = []
    if res.get("status") not in VALID:
        problems.append(f"status={res.get('status')}")
    t = r["timing"]
    if not t.get("comparable") or t.get("flag_disagreement"):
        problems.append(f"clock {t.get('diff_s')}")
    m = r["mock"]
    cap = m.get("capture") or {}
    if m.get("errors") or cap.get("packets_captured") != cap.get("packets_received_by_filter"):
        problems.append(f"mock errors={m.get('errors')} capture={cap.get('packets_captured')}/{cap.get('packets_received_by_filter')}")
    calls = res.get("calls") or []
    d = Path(r["out_dir"])
    if sc == "S7":
        keys = {q["logical_key"] for q in jl(d / "requests.jsonl") if q["port"] == 9001}
        h = t["host_mono_ns"]
        observed = (h.get("exit", h.get("process_exit")) - h["start"]) / 1e9
        if len(calls) != 10 or len(keys) != 10 or (res.get("status") != "no_return" and observed < 89.9):
            problems.append(f"S7: calls={len(calls)} keys={len(keys)} observed={observed:.1f}s")
    if sc in ("S1", "S9"):
        syns = [s for s in jl(d / "syns.jsonl") if s["dst_port"] == 9001]
        want = "none" if sc == "S1" else "rst"
        if not syns or any(s["server_reply"] != want for s in syns):
            problems.append(f"{sc}: SYN replies {sorted({s['server_reply'] for s in syns})}")
    c = calls[0] if calls else {}
    err = c.get("error") or {}
    chain = []
    e = err
    while e:
        chain.append(e.get("type"))
        e = e.get("chain")
    behavior = {"status": res.get("status"), "duration_s": c.get("duration_s"),
                "error": " <- ".join(x for x in chain if x)[:160], "message": (err.get("message") or "")[:120],
                "n_requests_faulted": sum(1 for q in jl(d / "requests.jsonl") if q["port"] == 9001),
                "n_syn_attempts": len({s["src_port"] for s in jl(d / "syns.jsonl") if s["dst_port"] == 9001})}
    return problems, behavior, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--langs", default="python,typescript,java,go")
    a = ap.parse_args()
    langs = a.langs.split(",")
    stamp = o.new_run_id()
    base = f"dev/e1/{stamp}"
    prepared = {}
    for lang in langs:
        src, fn = SOLUTIONS[lang]
        d = o.DATA / base / "prepared" / lang
        info = prepare(lang, REPO / src, d, task=TASK)
        print(f"prepare {lang}: {info['category']} in {info.get('duration_s', 0):.2f} s", flush=True)
        if info["category"] != "ok":
            sys.exit(f"prepare failed: {info}")
        prepared[lang] = (d, fn)
    slots = [o.Slot(k, mock_cpus=str(2 * k), sol_cpus=str(2 * k + 1)) for k in range(a.slots)]
    for s in slots:
        s.up()
    free = queue.Queue()
    for s in slots:
        free.put(s)
    calls1 = [{"args": TASK["single_args"]}]
    calls10 = [{"args": x} for x in TASK["s7_args"]]

    def job(lang, sc):
        s = free.get()
        try:
            d, fn = prepared[lang]
            r = s.run(lang=lang, task="R1", scenario=sc, prepared=d, function=fn, warmup_args=TASK["warmup_args"],
                      calls=calls10 if sc == "S7" else calls1, out_rel=f"{base}/runs/{lang}/{sc}")
            problems, behavior, t = check(lang, sc, r)
            return {"lang": lang, "scenario": sc, "ok": not problems, "problems": problems, "behavior": behavior,
                    "clock_diff_s": t.get("diff_s"), "startup_s": t.get("startup_s"), "lifetime_s": t.get("container_lifetime_s")}
        except Exception as e:  # noqa: BLE001
            return {"lang": lang, "scenario": sc, "ok": False, "problems": [f"harness error: {e!r}"]}
        finally:
            free.put(s)

    t0 = time.time()
    rows = []
    # long runs first so that the slots stay busy
    order = sorted(((l, sc) for l in langs for sc in SCENARIOS), key=lambda x: x[1] not in ("S1", "S2", "S3", "S4", "S7"))
    with cf.ThreadPoolExecutor(len(slots)) as ex:
        for f in cf.as_completed([ex.submit(job, l, sc) for l, sc in order]):
            x = f.result()
            rows.append(x)
            b = x.get("behavior", {})
            print(f"[{'PASS' if x['ok'] else 'FAIL'}] {x['lang']:10s} {x['scenario']:4s} {b.get('status')} "
                  f"{b.get('duration_s')} {b.get('error', '')} | clock={x.get('clock_diff_s')} start={x.get('startup_s')} {x['problems']}", flush=True)
    rows.sort(key=lambda x: (x["lang"], SCENARIOS.index(x["scenario"])))
    out = {"stamp": stamp, "elapsed_s": time.time() - t0, "all_ok": all(x["ok"] for x in rows), "rows": rows}
    (o.DATA / base / "summary.json").write_text(json.dumps(out, indent=1))
    print(f"\n{'ALL PASS' if out['all_ok'] else 'FAILURES'} ({len(rows)} runs, {out['elapsed_s']:.0f} s) -> data/{base}/summary.json")
    sys.exit(0 if out["all_ok"] else 1)


if __name__ == "__main__":
    main()
