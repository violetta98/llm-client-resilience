"""E0 verification: network isolation, TLS trust, and every scenario end to end
through the real containers (mock + Python driver), with packet capture.

Usage: python3 tests/integration/e0_verify.py [--quick] [--slots N]
Writes raw runs to data/dev/e0/<stamp>/ and summary.json there; exits non-zero
if any check fails.
"""

import argparse
import concurrent.futures as cf
import json
import queue
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runner"))
import orchestrator as o  # noqa: E402

SOL = REPO / "tests" / "solutions"
R1 = dict(task="R1", function="get_user_profile", warmup_args=["{A}", "u-000"])
ONE = [{"args": ["{A}", "u-042"]}]
TEN = [{"args": ["{A}", f"u-{100 + i:03d}"]} for i in range(10)]


def jl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def call0(r):
    return (r["result"] or {}).get("calls", [{}])[0]


def err_type(c):
    e = c.get("error") or {}
    return e.get("type", "")


def dur(c):
    return c.get("duration_s")


# (name, solution, scenario, calls, limit, check(run, out_dir) -> (ok, note))
def checks(quick):
    nt, t5 = "r1_requests_notimeout.py", "r1_requests_timeout5.py"
    C = []

    def add(name, sol, sc, check, calls=ONE, limit=o.LIMIT_S):
        C.append((name, sol, sc, calls, limit, check))

    for lib in ["r1_urllib_request.py", "r1_requests_notimeout.py", "r1_urllib3.py", "r1_httpx.py", "r1_aiohttp.py"]:
        add(f"tls_trust:{lib}", lib, "S0",
            lambda r, d: (call0(r).get("status") == "returned" and '"u-042"' in call0(r)["value"]["data"], call0(r).get("status")))

    def no_return(r, d):
        c = call0(r)
        return c.get("status") == "no_return" and r["result"]["status"] == "no_return", f"status={c.get('status')}"

    def raised_near(lo, hi, typ=None):
        def f(r, d):
            c = call0(r)
            ok = c.get("status") == "raised" and lo <= (dur(c) or -1) <= hi and (typ is None or typ in err_type(c))
            return ok, f"{c.get('status')} {err_type(c)} after {dur(c)}"
        return f

    add("S0 requests no timeout", nt, "S0", lambda r, d: (call0(r).get("status") == "returned" and dur(call0(r)) < 1, f"{dur(call0(r))}"))

    def s1_syns(r, d):
        ok, note = no_return(r, d)
        syns = jl(Path(d) / "syns.jsonl")
        meas = [s for s in syns if s["dst_port"] == 9001]
        ports = {s["src_port"] for s in meas}
        retx = sum(s["retransmission"] for s in meas)
        no_reply = all(s["server_reply"] == "none" for s in meas)
        return ok and len(meas) >= 5 and retx >= 4 and no_reply, f"{note}; SYNs={len(meas)} src_ports={len(ports)} retx={retx} no_reply={no_reply}"
    add("S1 requests no timeout -> 90 s; SYNs dropped (kernel retransmits)", nt, "S1", s1_syns)
    add("S1 requests timeout=5 -> ConnectTimeout ~5 s", t5, "S1", raised_near(4.9, 6.0, "ConnectTimeout"))

    def s2(r, d):
        ok, note = no_return(r, d)
        ev = jl(Path(d) / "conns.jsonl")
        hello = [e for e in ev if e["ev"] == "raw_bytes" and e["port"] == 9001 and e.get("bytes", 0) > 0]
        return ok and len(hello) >= 1, f"{note}; ClientHello logged={len(hello) > 0}"
    add("S2 requests no timeout -> 90 s", nt, "S2", s2)
    add("S2 requests timeout=5 -> ~5 s", t5, "S2", raised_near(4.9, 6.0))
    add("S3 requests no timeout -> 90 s (E0 criterion)", nt, "S3", no_return)
    add("S3 requests timeout=5 -> ReadTimeout ~5 s (E0 criterion)", t5, "S3", raised_near(4.9, 5.6, "ReadTimeout"))

    def s4(r, d):
        ok, note = no_return(r, d)
        segs = json.load(open(Path(d) / "run.json")).get("s4_server_data_segments") or []
        resp = [x for x in jl(Path(d) / "responses.jsonl") if x.get("fault") == "trickle" and x.get("trickle_write_times")]
        tw = resp[-1]["trickle_write_times"] if resp else []
        gaps_app = [(b - a) / 1e9 for a, b in zip(tw, tw[1:])]
        # On the wire: one TLS record per body byte -> data segments after the headers.
        ts = [s["t"] for s in segs]
        gaps_wire = [(b - a) / 1e9 for a, b in zip(ts, ts[1:])]
        body_gaps = [g for g in gaps_wire if g > 1.0]
        good = ok and len(body_gaps) >= 40 and all(1.95 <= g <= 2.05 for g in body_gaps) and all(1.98 <= g <= 2.02 for g in gaps_app)
        return good, (f"{note}; wire gaps n={len(body_gaps)} min={min(body_gaps, default=0):.4f} max={max(body_gaps, default=0):.4f}; "
                      f"app gaps n={len(gaps_app)} min={min(gaps_app, default=0):.4f} max={max(gaps_app, default=0):.4f}")
    add("S4 requests no timeout -> 90 s; byte gaps 2 s on the wire", nt, "S4", s4)
    add("S4 requests timeout=5 -> still 90 s (read timeout bounds gaps only)", t5, "S4", no_return)

    def status_err(code):
        def f(r, d):
            c = call0(r)
            return c.get("status") == "raised" and str(code) in (c.get("error") or {}).get("message", ""), f"{err_type(c)}: {(c.get('error') or {}).get('message', '')[:60]}"
        return f
    for sc, code in [("S5a", 503), ("S5b", 503), ("S6a", 429), ("S6b", 429)]:
        add(f"{sc} requests (no retries) -> HTTPError {code}", nt, sc, status_err(code))

    def s6b_header(r, d):
        ok, note = status_err(429)(r, d)
        rs = [x for x in jl(Path(d) / "responses.jsonl") if x.get("status") == 429]
        h = {x["name"]: x["value"] for x in rs[0]["headers"]} if rs else {}
        return ok and "GMT" in h.get("Retry-After", ""), f"{note}; Retry-After={h.get('Retry-After')}"
    C[-1] = C[-1][:5] + (s6b_header,)

    def s7(r, d):
        calls = r["result"]["calls"]
        reqs = [q for q in jl(Path(d) / "requests.jsonl") if q["port"] == 9001]
        keys = {q["logical_key"] for q in reqs}
        all503 = all(q.get("fault") == "503_outage" for q in reqs)
        return (len(calls) == 10 and all(c["status"] == "raised" for c in calls) and len(keys) == 10 and all503,
                f"{len(calls)} calls, statuses={sorted({c['status'] for c in calls})}, distinct keys={len(keys)}, all 503={all503}")
    add("S7 ten concurrent invocations, distinct args", nt, "S7", s7, calls=TEN)

    def s8(r, d):
        c = call0(r)
        rs = jl(Path(d) / "responses.jsonl")
        return c.get("status") == "raised" and any(x.get("outcome") == "reset" for x in rs), f"{err_type(c)}: {(c.get('error') or {}).get('message', '')[:80]}"
    add("S8 mechanics (commit then RST) on R1", nt, "S8", s8)

    def s9(r, d):
        c = call0(r)
        syns = [s for s in jl(Path(d) / "syns.jsonl") if s["dst_port"] == 9001]
        return (c.get("status") == "raised" and (dur(c) or 9) < 0.5 and syns and all(s["server_reply"] == "rst" for s in syns),
                f"{err_type(c)} after {dur(c)}; SYNs={len(syns)} replies={sorted({s['server_reply'] for s in syns})}")
    add("S9 refused -> immediate ConnectionError; SYN answered by RST", nt, "S9", s9)

    if not quick:
        def s1_long(r, d):
            c = call0(r)
            syns = [s for s in jl(Path(d) / "syns.jsonl") if s["dst_port"] == 9001]
            return (c.get("status") == "raised" and 125 <= (dur(c) or 0) <= 135,
                    f"{c.get('status')} {err_type(c)} after {dur(c)}; SYNs={len(syns)}, src ports={len({s['src_port'] for s in syns})}")
        add("S1 requests no timeout, 330 s limit -> OS connect limit ~127-131 s", nt, "S1", s1_long, limit=o.LIMIT_LONG_S)
        add("S3 requests no timeout, 330 s limit -> not bounded", nt, "S3", no_return, limit=o.LIMIT_LONG_S)
    return C


_prepared = {}


def prepared_dir(sol):
    """Prepares each harness test solution once per verification run."""
    import threading
    from prepare import prepare
    with _prep_lock:
        if sol not in _prepared:
            d = o.DATA / "dev" / "prepared" / o.new_run_id() / Path(sol).stem
            info = prepare("python", SOL / sol, d)
            if info["category"] != "ok":
                raise RuntimeError(f"prepare {sol}: {info}")
            _prepared[sol] = d
        return _prepared[sol]


import threading as _threading  # noqa: E402
_prep_lock = _threading.Lock()


def isolation(slot):
    """Runs a probe container with the solution's network attachment and
    restrictions; returns (ok, details)."""
    s0 = slot.ctl("POST", "/v1/run/start", {"run_id": "iso-" + o.new_run_id(), "task": "R1", "scenario": "S0",
                                            "out_dir": f"dev/e0/isolation/{o.new_run_id()}", "capture": False})
    script = f"""
set +e
echo "== routes"; ip route
echo "== mock S0 (TLS verified)"; curl -sS --cacert /ca.pem -m 5 -o /dev/null -w '%{{http_code}} alpn=%{{http_version}}\\n' https://{slot.mock_ip}:9001/v1/users/u-001
echo "== control port via int ip"; curl -sS -m 3 http://{slot.mock_ip}:9900/v1/health; echo " rc=$?"
echo "== control port via ctl ip"; curl -sS -m 3 http://{slot.ctl_ip}:9900/v1/health; echo " rc=$?"
echo "== internet 1.1.1.1:443"; curl -sS -m 3 https://1.1.1.1/; echo " rc=$?"
echo "== host.docker.internal"; curl -sS -m 3 http://host.docker.internal:{slot.ctl_port}/v1/health; echo " rc=$?"
echo "== docker bridge 10.77.{slot.k}.1 (must be unreachable, not refused)"; for p in 22 80 2375 {slot.ctl_port}; do nc -vz -w 2 10.77.{slot.k}.1 $p 2>&1; done
echo "== dns example.com"; getent hosts example.com; echo " rc=$?"
"""
    r = subprocess.run(["docker", "run", "--rm", "--network", slot.int_net, "--ip", slot.sol_ip,
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only", "--user", "65534:65534",
                        "lcr-probe:dev", "sh", "-c", script], capture_output=True, text=True, timeout=120)
    slot.ctl("POST", "/v1/run/finish")
    out = r.stdout + r.stderr
    sec = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("== "):
            cur = line[3:]
            sec[cur] = ""
        elif cur:
            sec[cur] += line + "\n"
    # Docker always installs a default route; with an internal network whose
    # bridge has no IPv4 address, the gateway does not exist (ARP fails), so
    # the criterion is reachability, checked below, not the route table.
    ok = (sec.get("mock S0 (TLS verified)", "").startswith("200")
          and all(" rc=0" not in sec.get(k, " rc=0") for k in sec if k.startswith(("control", "internet", "host")))
          and " rc=0" not in sec.get("dns example.com", " rc=0")
          and not any(w in sec.get(f"docker bridge 10.77.{slot.k}.1 (must be unreachable, not refused)", "refused") for w in ("refused", "succeeded")))
    return ok, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    stamp = o.new_run_id()
    base = f"dev/e0/{stamp}"
    slots = [o.Slot(k, mock_cpus=str(2 * k), sol_cpus=str(2 * k + 1)) for k in range(a.slots)]
    for s in slots:
        s.up()
    summary = {"stamp": stamp, "checks": []}
    iso_ok, iso_out = isolation(slots[0])
    summary["isolation"] = {"ok": iso_ok, "output": iso_out}
    print(f"[{'PASS' if iso_ok else 'FAIL'}] network isolation\n{iso_out}", flush=True)

    todo = [c for c in checks(a.quick) if a.only in c[0]]
    free = queue.Queue()
    for s in slots:
        free.put(s)

    def job(i, c):
        name, sol, sc, calls, limit, check = c
        s = free.get()
        try:
            out_rel = f"{base}/{i:02d}-{sc}-{Path(sol).stem}-{limit}"
            r = s.run(lang="python", scenario=sc, prepared=prepared_dir(sol), calls=calls, out_rel=out_rel, limit_s=limit, **R1)
            ok, note = check(r, r["out_dir"])
            t = r["timing"]
            ok_t = t.get("comparable") and not t.get("flag_disagreement")
            cap = r["mock"].get("capture") or {}
            ok_cap = not r["mock"].get("errors") and cap.get("packets_captured") == cap.get("packets_received_by_filter")
            note += f"; capture {cap.get('packets_captured')}/{cap.get('packets_received_by_filter')}"
            return {"name": name, "ok": bool(ok and ok_t and ok_cap), "note": note, "out": out_rel,
                    "driver_s": t.get("driver_s"), "external_s": t.get("external_s"), "clock_diff_s": t.get("diff_s"),
                    "mock_errors": r["mock"].get("errors"), "packets_dropped": (r["mock"].get("capture") or {}).get("packets_dropped_by_kernel")}
        except Exception as e:  # noqa: BLE001
            return {"name": name, "ok": False, "note": f"harness error: {e!r}"}
        finally:
            free.put(s)

    t0 = time.time()
    with cf.ThreadPoolExecutor(len(slots)) as ex:
        futs = [ex.submit(job, i, c) for i, c in enumerate(todo)]
        for f in cf.as_completed(futs):
            x = f.result()
            summary["checks"].append(x)
            print(f"[{'PASS' if x['ok'] else 'FAIL'}] {x['name']}: {x['note']} | driver={x.get('driver_s')} ext={x.get('external_s')} diff={x.get('clock_diff_s')}", flush=True)
    summary["checks"].sort(key=lambda x: x.get("out", ""))
    summary["elapsed_s"] = time.time() - t0
    summary["all_ok"] = iso_ok and all(x["ok"] for x in summary["checks"])
    (o.DATA / base).mkdir(parents=True, exist_ok=True)
    (o.DATA / base / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\n{'ALL PASS' if summary['all_ok'] else 'FAILURES'} ({len(summary['checks'])} checks, {summary['elapsed_s']:.0f} s) -> data/{base}/summary.json")
    sys.exit(0 if summary["all_ok"] else 1)


if __name__ == "__main__":
    main()
