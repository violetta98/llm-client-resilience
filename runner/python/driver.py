"""Python driver: imports a solution, warms it up against normal endpoints,
times the measured call(s) with CLOCK_MONOTONIC, and reports a result.

Protocol (stdout carries only driver markers; anything the solution prints
goes to stderr):
    @@LCR <nonce> READY <mono_ns>      runtime up, solution imported, warm-up done
    @@LCR <nonce> START <mono_ns>      immediately before the measured call(s)
    @@LCR <nonce> END <mono_ns>        all measured calls returned/raised (absent on no_return)
    @@LCR <nonce> RESULT <json>        result document (schema result/1)
    @@LCR <nonce> EXIT <mono_ns>       just before os._exit

The plan is read from /plan/plan.json (see runner/README.md).
"""

import asyncio
import importlib.util
import inspect
import json
import os
import platform
import sys
import threading
import time
import traceback

PLAN_PATH = os.environ.get("LCR_PLAN", "/plan/plan.json")
MAX_VALUE = 64 * 1024
SYSCTLS = [
    "net/ipv4/tcp_syn_retries", "net/ipv4/tcp_synack_retries", "net/ipv4/tcp_retries1",
    "net/ipv4/tcp_retries2", "net/ipv4/tcp_keepalive_time", "net/ipv4/tcp_keepalive_intvl",
    "net/ipv4/tcp_keepalive_probes", "net/ipv4/tcp_fin_timeout", "net/ipv4/ip_local_port_range",
    "net/ipv4/tcp_tw_reuse", "net/core/somaxconn",
]

mono = time.monotonic_ns  # CLOCK_MONOTONIC on Linux


def main():
    plan = json.load(open(PLAN_PATH))
    nonce = plan["nonce"]
    # Keep the real stdout for markers; route fd 1 to stderr for the solution.
    marker = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    lock = threading.Lock()

    def emit(kind, payload):
        with lock:
            marker.write(f"@@LCR {nonce} {kind} {payload}\n")
            marker.flush()

    res = {
        "schema": "result/1",
        "lang": "python",
        "runtime": {"python": sys.version, "implementation": platform.python_implementation()},
        "function": plan["function"],
        "mode": plan["mode"],
        "limit_s": plan["limit_s"],
        "env": environment(),
        "import": None,
        "warmup": None,
        "calls": [],
        "t_ready": None,
        "t_start": None,
        "t_end": None,
        "status": None,
    }
    done = threading.Event()
    finished = threading.Event()  # result emitted

    def finish(status, exit_after_s=0.0):
        with lock:
            if finished.is_set():
                return
            finished.set()
        res["status"] = status
        res["files"] = inspect_files(plan.get("inspect_paths") or [])
        emit("RESULT", json.dumps(res, default=repr))
        if exit_after_s > 0:
            time.sleep(exit_after_s)
        emit("EXIT", mono())
        os._exit(0)

    # --- import --------------------------------------------------------------
    t0 = mono()
    try:
        spec = importlib.util.spec_from_file_location("solution", plan["solution"])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["solution"] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, plan["function"])
        res["import"] = {"ok": True, "t": t0, "duration_s": (mono() - t0) / 1e9,
                         "is_coroutine_function": inspect.iscoroutinefunction(fn)}
    except BaseException as e:  # noqa: BLE001 - everything is data here
        res["import"] = {"ok": False, "t": t0, "error": describe(e)}
        finish("import_error")
        return

    # --- warm-up (normal endpoints on separate ports; not measured) -----------
    wd = threading.Thread(target=watchdog, args=(done, plan.get("warmup_limit_s", 60), lambda: finish("warmup_no_return")),
                          daemon=True)
    wd.start()
    w = run_one(fn, plan["warmup_args"])
    res["warmup"] = w
    done.set()
    wd.join()

    # --- measured call(s) ----------------------------------------------------
    done = threading.Event()
    calls = [None] * len(plan["calls"])
    res["calls"] = calls

    def on_timeout():
        for i, c in enumerate(calls):
            if c is None or c.get("status") is None:
                calls[i] = {"index": i, "status": "no_return", "t_start": (c or {}).get("t_start", res["t_start"]),
                            "t_end": None}
        res["t_end"] = None
        finish("no_return")

    res["t_ready"] = mono()
    emit("READY", res["t_ready"])
    res["t_start"] = mono()
    emit("START", res["t_start"])
    wd = threading.Thread(target=watchdog, args=(done, plan["limit_s"], on_timeout), daemon=True,
                          kwargs={"t0": res["t_start"]})
    wd.start()
    if plan["mode"] == "single":
        calls[0] = {"index": 0, "t_start": res["t_start"]}
        calls[0] = run_one(fn, plan["calls"][0]["args"], index=0, t_start=res["t_start"])
    else:
        run_concurrent(fn, plan["calls"], calls)
    res["t_end"] = mono()
    if finished.is_set():  # watchdog already reported no_return
        return
    done.set()
    emit("END", res["t_end"])
    statuses = {c["status"] for c in calls}
    status = "returned" if statuses == {"returned"} else ("raised" if statuses == {"raised"} else "mixed")
    # Stay alive so that late requests (background retries) are observed:
    # linger_s after the return, and at least until observe_s after the start
    # (S7: the ten invocations are observed for 90 s).
    linger = plan.get("linger_s", 5)
    observe = plan.get("observe_s", 0) - (mono() - res["t_start"]) / 1e9
    res["linger_s"] = max(linger, observe)
    finish(status, exit_after_s=res["linger_s"])


def watchdog(done, limit_s, on_timeout, t0=None):
    t0 = t0 or mono()
    remaining = limit_s - (mono() - t0) / 1e9
    if not done.wait(max(0.0, remaining)):
        on_timeout()


def call_fn(fn, args):
    r = fn(*args)
    if inspect.isawaitable(r):
        r = asyncio.run(_await(r))
    return r


async def _await(a):
    return await a


def run_one(fn, args, index=0, t_start=None):
    t_start = t_start or mono()
    try:
        v = call_fn(fn, args)
        t_end = mono()
        return {"index": index, "status": "returned", "t_start": t_start, "t_end": t_end,
                "duration_s": (t_end - t_start) / 1e9, "value": encode_value(v)}
    except BaseException as e:  # noqa: BLE001
        t_end = mono()
        return {"index": index, "status": "raised", "t_start": t_start, "t_end": t_end,
                "duration_s": (t_end - t_start) / 1e9, "error": describe(e)}


def run_concurrent(fn, plan_calls, calls):
    """Ten concurrent invocations with distinct arguments: threads for sync
    functions, one event loop with gather() for coroutine functions."""
    if inspect.iscoroutinefunction(fn):
        async def one(i, args):
            t_start = mono()
            calls[i] = {"index": i, "t_start": t_start}
            try:
                v = await fn(*args)
                t_end = mono()
                calls[i] = {"index": i, "status": "returned", "t_start": t_start, "t_end": t_end,
                            "duration_s": (t_end - t_start) / 1e9, "value": encode_value(v)}
            except BaseException as e:  # noqa: BLE001
                t_end = mono()
                calls[i] = {"index": i, "status": "raised", "t_start": t_start, "t_end": t_end,
                            "duration_s": (t_end - t_start) / 1e9, "error": describe(e)}

        async def all_():
            await asyncio.gather(*(one(i, c["args"]) for i, c in enumerate(plan_calls)), return_exceptions=True)

        asyncio.run(all_())
        return
    barrier = threading.Barrier(len(plan_calls))

    def worker(i, args):
        barrier.wait()
        calls[i] = {"index": i, "t_start": mono()}
        calls[i] = run_one(fn, args, index=i, t_start=calls[i]["t_start"])

    ts = [threading.Thread(target=worker, args=(i, c["args"]), daemon=True) for i, c in enumerate(plan_calls)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def encode_value(v):
    try:
        s = json.dumps(v)
        enc = "json"
    except (TypeError, ValueError):
        s = repr(v)
        enc = "repr"
    out = {"enc": enc, "type": type(v).__module__ + "." + type(v).__qualname__, "len": len(s)}
    if len(s) > MAX_VALUE:
        out["data"], out["truncated"] = s[:MAX_VALUE], True
    else:
        out["data"] = s
    return out


def describe(e, depth=0):
    d = {
        "type": type(e).__module__ + "." + type(e).__qualname__,
        "mro": [c.__module__ + "." + c.__qualname__ for c in type(e).__mro__[1:-1]][:12],
        "message": str(e)[:4000],
        "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__))[-8000:],
    }
    nxt = e.__cause__ or e.__context__
    if nxt is not None and depth < 5:
        d["chain"] = describe(nxt, depth + 1)
        d["chain"].pop("traceback", None)
    return d


def inspect_files(paths):
    """Size and SHA-256 of files the task writes (R3), after the call."""
    import hashlib
    out = []
    for p in paths:
        d = {"path": p, "exists": os.path.isfile(p)}
        if d["exists"]:
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            d["size"], d["sha256"] = os.path.getsize(p), h.hexdigest()
        out.append(d)
    return out


def environment():
    sc = {}
    for p in SYSCTLS:
        try:
            sc[p.replace("/", ".")] = open("/proc/sys/" + p).read().strip()
        except OSError as e:
            sc[p.replace("/", ".")] = f"unreadable: {e}"
    u = os.uname()
    try:
        aff = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        aff = None
    return {"sysctl": sc, "kernel": u.release, "uname": " ".join(u), "cpu_affinity": aff,
            "uid": os.getuid(), "hostname": u.nodename}


if __name__ == "__main__":
    main()
