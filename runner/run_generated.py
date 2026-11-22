"""Runs generated solutions (E5 pilot, E8 main) through every applicable scenario.

Usage: python3 runner/run_generated.py --run pilot [--slots 5] [--no-rerun]
       python3 runner/run_generated.py --run main-rep --rep-of main   # 5 % repeatability sample

Reads   data/<run>/generations/<cond>/<model>/<task>/<lang>/<sample>/
Writes  data/<run>/prepared/<cond>/<model>/<task>/<lang>/<sample>/   prepare.json + artifact
        data/<run>/runs/<cond>/<model>/<task>/<lang>/<sample>/<scenario>/
        data/<run>/rerun330/<cond>/<model>/<task>/<lang>/<sample>/<scenario>/
        data/<run>/measures.jsonl  (one row per program x scenario, incl. 330 s rows)
        data/<run>/programs.jsonl  (one row per generation: extraction, prepare category)
        data/<run>/run_summary.json

Categories per program: no_code (no extractable code, or an unfenced candidate
that does not compile), compile_error, missing_dependency, api_error, ok (run).
A run directory that already holds result.json is not run again (resumable);
a re-run of a whole program for repeatability goes to a new --run directory.
330 s repetitions: every run without return in 90 s in S1-S3; in S4 the aiohttp programs and
a deterministic 10 % sample (brief E8; --s4-rerun all repeats every S4 run, as in the pilot).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import queue
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "runner"))
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402
import orchestrator as o  # noqa: E402
from prepare import prepare  # noqa: E402

EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
RERUN_SCEN = {"S1", "S2", "S3", "S4"}
S4_SAMPLE_SHARE = 0.10  # brief E8: S4 330 s repetitions for aiohttp programs + a random 10 %
REP_SHARE = 0.05  # protocol 3: repeatability sample of ok programs, re-run in all scenarios under a new run ID
VARIANT_SHARE = 0.25  # D38: S4 variants on a deterministic 25 % sample of the source run's programs
# D38 (review): variants of S4 run as scenario S4 with other mock parameters; the run directory carries the variant name
VARIANTS = {"S4g05": ("S4", {"trickle_interval_ms": 500}),     # one byte every 0.5 s
            "S4g025": ("S4", {"trickle_interval_ms": 250}),   # D61: one byte every 0.25 s (only when named)
            "S4g5": ("S4", {"trickle_interval_ms": 5000}),     # one byte every 5 s
            "S4h": ("S4", {"trickle_interval_ms": 3600000}),   # headers, then no body byte within the run
            # D45: normal behaviour, but every response takes 750 ms, inside the documented p99 of 800 ms; a solution
            # whose timeouts are shorter than the contract allows fails here
            "S0slow": ("S0", {"latency_ms": 750}),
            # round 11 (advice checks only): S6a with a Retry-After longer than a 10 s budget
            "S6a30": ("S6a", {"retry_after_s": 30})}


def _u(key):
    """Deterministic uniform [0, 1] from SHA-256 of a key (reproducible, not tuned)."""
    import hashlib
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def pkey(p):
    return f"{p['cond']}/{p['model']}/{p['task']}/{p['lang']}/{p['sample']}"


def rep_selected(p):
    return _u("rep:" + pkey(p)) < REP_SHARE


def variant_selected(p):
    return _u("variant:" + pkey(p)) < VARIANT_SHARE


def s4_rerun_selected(p):
    """Deterministic 10 % sample by SHA-256 of the program key, plus every Python program that imports aiohttp."""
    if _u(pkey(p)) < S4_SAMPLE_SHARE:
        return True
    if p["lang"] == "python":
        f = p["gen_dir"] / "solution.py"
        src = f.read_text() if f.exists() else ""
        return "import aiohttp" in src or "from aiohttp" in src
    return False


def programs(run):
    base = o.DATA / run / "generations"
    for meta_p in sorted(base.glob("*/*/*/*/*/meta.json")):
        d = meta_p.parent
        cond, model, task, lang, sample = d.parts[-5:]
        yield {"cond": cond, "model": model, "task": task, "lang": lang, "sample": int(sample), "gen_dir": d,
               "meta": json.loads(meta_p.read_text())}


def rel(p):
    return f"{p['cond']}/{p['model']}/{p['task']}/{p['lang']}/{p['sample']}"


def prep(run, p, sig):
    meta = p["meta"]
    row = {k: p[k] for k in ("cond", "model", "task", "lang", "sample")}
    if meta.get("status") != "ok":
        return {**row, "category": "api_error"}
    ex = meta["extraction"]["status"]
    if ex == "no_code":
        return {**row, "category": "no_code", "extraction": ex}
    d = o.DATA / run / "prepared" / rel(p)
    pj = d / "prepare.json"
    info = json.loads(pj.read_text()) if pj.exists() else prepare(p["lang"], p["gen_dir"] / f"solution.{EXT[p['lang']]}", d, task=sig)
    cat = info["category"]
    if ex == "unfenced" and cat == "compile_error":
        cat = "no_code"  # extraction rule: an unfenced response that does not parse is not code
    return {**row, "category": cat, "extraction": ex, "prepared": str(d), "prepare_info": {**{k: info.get(k) for k in ("category", "errors", "missing")}, "build_log": (info.get("build_log") or "")[:2000] or None}}


def docker_up() -> bool:
    import subprocess
    try:
        # `docker info` exits 0 even when the daemon is unreachable; `docker version` does not.
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


_docker_lock = __import__("threading").Lock()


def wait_for_docker(slot):
    """Blocks while the Docker engine is unreachable (D28); re-creates the slot's mock after an outage."""
    with _docker_lock:
        waited = False
        while not docker_up():
            if not waited:
                print("  docker engine unreachable: waiting", flush=True)
            waited = True
            time.sleep(30)
    if waited or getattr(slot, "need_up", False):
        slot.up()
        slot.need_up = False


def set_aside(out_rel: str):
    import shutil
    src = o.DATA / out_rel
    if src.exists():
        dst = o.DATA / out_rel.split("/")[0] / "aborted" / f"docker-down-{time.strftime('%Y%m%dT%H%M%S')}" / out_rel.split("/", 1)[1]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--no-rerun", action="store_true")
    ap.add_argument("--scenarios", default="", help="D43: run only these scenarios (comma-separated); default all")
    ap.add_argument("--s4-rerun", choices=["brief", "all"], default="brief",
                    help="brief: aiohttp + 10%% sample (E8); all: every S4 run without return (pilot)")
    ap.add_argument("--rep-of", default="", help="repeatability: re-run the 5 %% sample of this run's ok programs "
                                                  "(its generations and prepared artifacts) into --run")
    ap.add_argument("--select-file", default="", help="D39: with --variants-of, run only the programs listed in this file "
                                                       "(one cond/model/task/lang/sample per line) instead of the 25 %% sample")
    ap.add_argument("--variants", default="S4g05,S4g5,S4h,S0slow", help="which variants to run (comma-separated); "
                                                                         "S6a30 only when named")
    ap.add_argument("--variants-of", default="", help="D38: run the S4 variants (VARIANTS) on a deterministic 25 %% "
                                                       "sample of this run's ok programs into --run (no 330 s repetitions)")
    a = ap.parse_args()
    run = a.run
    src = a.rep_of or a.variants_of or run
    if a.rep_of or a.variants_of:
        if run == src:
            sys.exit("--run must be a new run ID for a repeatability or variant run")
        (o.DATA / run).mkdir(parents=True, exist_ok=True)
    if a.variants_of:
        a.no_rerun = True
    exp, sig = {}, {}
    chosen = set(Path(a.select_file).read_text().split()) if a.select_file else None
    progs = [p for p in programs(src) if (not a.rep_of or rep_selected(p))
             and (not a.variants_of or (pkey(p) in chosen if chosen is not None else variant_selected(p)))]
    rows_prog, jobs = [], []
    t_prep = time.time()
    for p in progs:
        t = p["task"]
        exp.setdefault(t, yaml.safe_load((M.task_dir(t) / "expected.yaml").read_text()))
        sig.setdefault(t, json.loads((M.task_dir(t) / "signature.json").read_text()))
        r = prep(src, p, sig[t])
        rows_prog.append(r)
        if r["category"] == "ok":
            for sc in (a.variants.split(",") if a.variants_of else [s for s in exp[t]["scenarios"] if not a.scenarios or s in a.scenarios.split(",")]):
                jobs.append((p, Path(r["prepared"]), sc))
    t_prep = time.time() - t_prep
    with open(o.DATA / run / "programs.jsonl", "w") as f:
        for r in rows_prog:
            f.write(json.dumps(r, default=str) + "\n")
    print(f"{len(progs)} generations; categories: "
          f"{ {c: sum(1 for r in rows_prog if r['category'] == c) for c in sorted({r['category'] for r in rows_prog})} }; "
          f"{len(jobs)} runs (prepare {t_prep:.0f} s)", flush=True)

    slots = [o.Slot(k, mock_cpus=str(2 * k), sol_cpus=str(2 * k + 1)) for k in range(a.slots)]
    for s in slots:
        s.up()
    free = queue.Queue()
    for s in slots:
        free.put(s)

    def job(p, d, sc, limit=o.LIMIT_S):
        t, lang = p["task"], p["lang"]
        top = "runs" if limit == o.LIMIT_S else "rerun330"
        out_rel = f"{run}/{top}/{rel(p)}/{sc}"
        key = {k: p[k] for k in ("cond", "model", "task", "lang", "sample")}
        if (o.DATA / out_rel / "result.json").exists():
            row = M.compute(M.load_run(o.DATA / out_rel), exp[t], cond=p["cond"])
            return {**row, **key, "dir": out_rel, "limit_s": limit, "slot_s": None, "_job": (p, d, sc), "resumed": True}
        s = free.get()
        t0 = time.time()
        try:
            for attempt in range(4):
                wait_for_docker(s)
                t0 = time.time()
                try:
                    sg = sig[t]
                    calls = [{"args": x} for x in sg["s7_args"]] if sc == "S7" else [{"args": sg["single_args"]}]
                    inspect = [c["args"][2] for c in calls] if t == "R3" else None
                    base_sc, overrides = VARIANTS.get(sc, (sc, None))
                    s.run(lang=lang, task=t, scenario=base_sc, prepared=d, function=sg[lang]["function"],
                          warmup_args=sg["warmup_args"], calls=calls, out_rel=out_rel, inspect_paths=inspect, limit_s=limit,
                          mock_overrides=overrides)
                    row = M.compute(M.load_run(o.DATA / out_rel), exp[t], cond=p["cond"])
                    return {**row, **key, "dir": out_rel, "limit_s": limit, "slot_s": time.time() - t0, "_job": (p, d, sc)}
                except Exception as e:  # noqa: BLE001
                    infra = "Connection refused" in repr(e) or "Cannot connect to the Docker daemon" in repr(e)
                    if attempt == 3 or (docker_up() and not infra):
                        return {**key, "scenario": sc, "limit_s": limit, "harness_error": repr(e), "slot_s": time.time() - t0}
                    # Docker engine went away mid-run: the partial run is moved aside (never overwritten) and repeated.
                    print(f"  docker/slot failure during {out_rel}: {e!r}; moving partial run aside and waiting", flush=True)
                    time.sleep(10)
                    set_aside(out_rel)
                    s.need_up = True
        finally:
            free.put(s)

    t0 = time.time()
    rows = []
    order = sorted(jobs, key=lambda j: j[2] not in ("S7", "S1", "S2", "S3", "S4"))
    with cf.ThreadPoolExecutor(len(slots)) as ex:
        futs = [ex.submit(job, *j) for j in order]
        for i, f in enumerate(cf.as_completed(futs)):
            r = f.result()
            rows.append(r)
            if "harness_error" in r or not r.get("harness_ok", True):
                print(f"  [{i + 1}/{len(futs)}] HARNESS {r.get('model')} {r.get('task')} {r.get('lang')} {r.get('sample')} "
                      f"{r.get('scenario')}: {r.get('harness_error') or 'harness_ok=false'}", flush=True)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(futs)} runs, {time.time() - t0:.0f} s", flush=True)
        t_main = time.time() - t0
        t1 = time.time()
        if not a.no_rerun:
            again = [r["_job"] for r in rows if r.get("no_return_90") and r.get("_job") and r["_job"][2] in RERUN_SCEN
                     and (r["_job"][2] != "S4" or a.s4_rerun == "all" or s4_rerun_selected(r["_job"][0]))]
            print(f"{len(again)} runs without return in 90 s in S1-S4: repeating with {o.LIMIT_LONG_S} s", flush=True)
            for f in cf.as_completed([ex.submit(job, *j, limit=o.LIMIT_LONG_S) for j in again]):
                rows.append(f.result())
        t_rerun = time.time() - t1
    for r in rows:
        r.pop("_job", None)
    # D47: keep rows of earlier invocations on the same run ID (other variants or scenarios) instead of replacing them
    mf, new_dirs = o.DATA / run / "measures.jsonl", {r.get("dir") for r in rows}
    kept = [json.loads(x) for x in mf.read_text().splitlines() if x.strip()] if mf.exists() else []
    kept = [r for r in kept if r.get("dir") not in new_dirs]
    with open(mf, "w") as f:
        for r in kept + rows:
            f.write(json.dumps(r, default=str) + "\n")
    timed = [r for r in rows if r.get("slot_s") is not None]
    summ = {"generations": len(progs), "runs": len(jobs), "reruns_330": sum(1 for r in rows if r.get("limit_s") == o.LIMIT_LONG_S),
            "slots": a.slots, "wall_s": {"prepare": t_prep, "runs": t_main, "reruns_330": t_rerun},
            "slot_seconds": {"runs_90": sum(r["slot_s"] for r in timed if r["limit_s"] == o.LIMIT_S),
                             "reruns_330": sum(r["slot_s"] for r in timed if r["limit_s"] == o.LIMIT_LONG_S)},
            "harness_errors": sum(1 for r in rows if "harness_error" in r),
            "harness_not_ok": sum(1 for r in rows if "harness_error" not in r and not r.get("harness_ok", True))}
    (o.DATA / run / "run_summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
