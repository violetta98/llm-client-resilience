"""E3: run reference solutions and mutants through every applicable scenario
and check that (a) every reference meets every criterion and (b) every mutant
is flagged by the measure it targets (other flags are recorded as side effects).

Usage: python3 tests/integration/e3_run.py --langs python [--variants REFERENCE]
       [--tasks R1,W1] [--slots 5] [--out dev/e3/<stamp>]
"""
import argparse
import concurrent.futures as cf
import json
import queue
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runner"))
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402
import orchestrator as o  # noqa: E402
from prepare import prepare  # noqa: E402

FLAGS = ["no_return_90", "overrun", "c2_overrun", "rapid_retries", "retry_after_violation", "excessive_retries",
         "sync_retries", "unsafe_write_retry", "silent_failure"]
TARGET = {  # mutant -> (scenarios, measure); B1 TIGHT_LOOP: rapid retries are not attributable in S9 (D15)
    "NO_TIMEOUT": (["S3"], "no_return_90"),
    "TIGHT_LOOP": (["S9"], "rapid_retries"),
    "IGNORE_RETRY_AFTER": (["S6a", "S6b"], "retry_after_violation"),
    "UNSAFE_POST_RETRY": (["S8"], "unsafe_write_retry"),
    "FIXED_BACKOFF": (["S7"], "sync_retries"),
}
# Mutants that cannot show their defect by construction (references/README.md):
# the 0.8 s budget of H2 leaves no room for a 3 s Retry-After or a second attempt.
NOT_APPLICABLE = {("H2", "IGNORE_RETRY_AFTER"), ("H2", "FIXED_BACKOFF")}
FN_KEY = {"python": "function", "typescript": "function", "java": "function", "go": "function"}


def flags_of(row):
    f = [k for k in FLAGS if row.get(k)]
    if row.get("late_requests"):
        f.append("late_requests")
    if not row.get("outcome_allowed"):
        f.append(f"outcome={row.get('outcome')}")
    if not row.get("harness_ok"):
        f.append("HARNESS")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="python")
    ap.add_argument("--variants", default="")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--scenarios", default="")
    ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--out", default="")
    ap.add_argument("--index", default="", help="program index file (default: references/index-<lang>.json)")
    ap.add_argument("--long-rerun", action="store_true", help="repeat runs stopped at 90 s in S1-S4 with a 330 s limit")
    a = ap.parse_args()
    stamp = o.new_run_id()
    base = a.out or f"dev/e3/{stamp}"
    progs = []
    for lang in a.langs.split(","):
        idx = json.loads((REPO / (a.index or f"references/index-{lang}.json")).read_text())
        idx = [p for p in idx if p["lang"] == lang]
        progs += [p for p in idx if (not a.variants or p["variant"] in a.variants.split(","))
                  and (not a.tasks or p["task"] in a.tasks.split(","))]
    print(f"{len(progs)} programs", flush=True)

    # prepare (once per program)
    exp, sig = {}, {}
    jobs = []
    for p in progs:
        t = p["task"]
        exp.setdefault(t, yaml.safe_load((M.task_dir(t) / "expected.yaml").read_text()))
        sig.setdefault(t, json.loads((M.task_dir(t) / "signature.json").read_text()))
        d = o.DATA / base / "prepared" / p["lang"] / t / p["variant"]
        info = prepare(p["lang"], REPO / p["path"], d, task=sig[t])
        if info["category"] != "ok":
            print(f"PREPARE FAIL {p}: {info.get('errors') or info.get('build_log') or info}", flush=True)
            continue
        scen = exp[t]["scenarios"]
        if a.scenarios:
            scen = [s for s in scen if s in a.scenarios.split(",")]
        for sc in scen:
            jobs.append((p, d, sc))
    print(f"{len(jobs)} runs", flush=True)

    slots = [o.Slot(k, mock_cpus=str(2 * k), sol_cpus=str(2 * k + 1)) for k in range(a.slots)]
    for s in slots:
        s.up()
    free = queue.Queue()
    for s in slots:
        free.put(s)

    def job(p, d, sc, limit=o.LIMIT_S):
        t, lang = p["task"], p["lang"]
        s = free.get()
        try:
            sg = sig[t]
            calls = [{"args": x} for x in sg["s7_args"]] if sc == "S7" else [{"args": sg["single_args"]}]
            inspect = None
            if t == "R3":
                inspect = [c["args"][2] for c in calls]
            out_rel = f"{base}/runs/{lang}/{t}/{p['variant']}/{sc}" + ("" if limit == o.LIMIT_S else f"-{limit}")
            r = s.run(lang=lang, task=t, scenario=sc, prepared=d, function=sg[lang][FN_KEY[lang]],
                      warmup_args=sg["warmup_args"], calls=calls, out_rel=out_rel, inspect_paths=inspect, limit_s=limit)
            row = M.compute(M.load_run(o.DATA / out_rel), exp[t], cond="C2")
            row.update(variant=p["variant"], lang=lang, dir=out_rel, limit_s=limit, _job=(p, d, sc))
            return row
        except Exception as e:  # noqa: BLE001
            return {"task": t, "lang": lang, "variant": p["variant"], "scenario": sc, "harness_error": repr(e)}
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
            fl = flags_of(r) if "harness_error" not in r else ["HARNESS_ERROR " + r["harness_error"]]
            if r["variant"] == "REFERENCE" and fl or "harness_error" in r:
                print(f"  [{i + 1}/{len(futs)}] {r['lang']} {r['task']} {r['variant']} {r['scenario']}: {fl}", flush=True)
        if a.long_rerun:
            again = [r["_job"] for r in rows if r.get("no_return_90") and r.get("_job")]
            print(f"{len(again)} runs stopped at 90 s in S1-S4: repeating with {o.LIMIT_LONG_S} s", flush=True)
            for f in cf.as_completed([ex.submit(job, *j, limit=o.LIMIT_LONG_S) for j in again]):
                rows.append(f.result())
    for r in rows:
        r.pop("_job", None)
    (o.DATA / base).mkdir(parents=True, exist_ok=True)
    with open(o.DATA / base / "measures.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")

    # --- verdicts -------------------------------------------------------------
    summary = {"references": {}, "mutants": {}, "elapsed_s": time.time() - t0}
    by_prog = {}
    for r in rows:
        if r.get("limit_s", o.LIMIT_S) != o.LIMIT_S:
            continue  # 330 s repetitions are reported separately
        by_prog.setdefault((r["lang"], r["task"], r["variant"]), []).append(r)
    for (lang, t, v), rs in sorted(by_prog.items()):
        if v.startswith("BASELINE"):
            continue
        if v == "REFERENCE":
            bad = {r["scenario"]: flags_of(r) if "harness_error" not in r else ["HARNESS_ERROR"] for r in rs}
            bad = {k: x for k, x in bad.items() if x}
            summary["references"][f"{lang}/{t}"] = {"pass": not bad, "failures": bad}
        else:
            scs, meas = TARGET[v]
            if v == "TIGHT_LOOP" and t == "B1":
                scs, meas = ["S7"], "excessive_retries"
            hit = any(r.get(meas) for r in rs if r.get("scenario") in scs)
            side = {r["scenario"]: flags_of(r) for r in rs if flags_of(r)}
            na = (t, v) in NOT_APPLICABLE
            summary["mutants"][f"{lang}/{t}/{v}"] = {"flagged_by_target": hit or na, "not_applicable": na,
                                                    "target": f"{meas} in {scs}", "all_flags": side}
    summary["all_references_pass"] = all(x["pass"] for x in summary["references"].values())
    summary["all_mutants_flagged"] = all(x["flagged_by_target"] for x in summary["mutants"].values())
    (o.DATA / base / "summary.json").write_text(json.dumps(summary, indent=1))
    nref = len(summary["references"])
    nmut = len(summary["mutants"])
    print(f"\nreferences: {sum(x['pass'] for x in summary['references'].values())}/{nref} pass; "
          f"mutants: {sum(x['flagged_by_target'] for x in summary['mutants'].values())}/{nmut} flagged by target "
          f"({summary['elapsed_s']:.0f} s) -> data/{base}/summary.json")
    for k, x in summary["references"].items():
        if not x["pass"]:
            print(f"  REFERENCE FAIL {k}: {x['failures']}")
    for k, x in summary["mutants"].items():
        if not x["flagged_by_target"]:
            print(f"  MUTANT NOT FLAGGED {k}: target {x['target']}; flags {x['all_flags']}")


if __name__ == "__main__":
    main()
