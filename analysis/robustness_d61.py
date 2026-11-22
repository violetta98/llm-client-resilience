"""D61: robustness of the main exploratory findings, post hoc, on existing data only (no new runs).

  python3 analysis/robustness_d61.py   -> analysis/out/robustness/summary.json, loo.csv

1. Construct split in S4 (whole-call deadline vs per-read or until-headers only, both conditions): pooled, without
   Java, per language, leaving out one model and one task at a time (min and max over the left-out units).
2. Requirements effect (C2 - C0, percentage points) in tasks without a stated limit (R and W): S4 hang; and over all
   tasks: excessive retries in S7 or S9. Same leave-one-out, plus the count of models and tasks with the effect in the
   predicted direction.
3. Intention to treat: every generation counts, a non-runnable one as a failure (primary outcomes: S3 hang,
   time-limit overrun in B/H tasks, duplicate write in W1/W2/B4; and the S4 hang), C0 vs C2, pooled and for Qwen and
   Granite, whose runnable shares are lowest.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402

KEYS = ("cond", "model", "task", "lang", "sample")
OUT = REPO / "analysis" / "out" / "robustness"


def pct(a, n):
    return round(100 * a / n, 1) if n else None


def load():
    feats = {tuple(r[k] for k in KEYS): r for r in csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv"))}
    sol = defaultdict(dict)
    for line in open(REPO / "analysis" / "out" / "main" / "runs.jsonl"):
        r = json.loads(line)
        if r["limit_s"] == 90 and r.get("usable"):
            sol[tuple(str(r[k]) for k in KEYS)][r["scenario"]] = r
    progs = list(csv.DictReader(open(REPO / "analysis" / "out" / "main" / "programs.csv")))
    return feats, sol, progs


def group(f):
    t = {x for x in f["timeout_constructs"].split(";") if x}
    return "whole" if t & WHOLE else "perread" if t else "none"


def split(rows):
    """rows: list of (key, group, hang). Returns hang % per-read, whole, difference."""
    a = {g: [0, 0] for g in ("whole", "perread")}
    for _, g, h in rows:
        if g in a:
            a[g][0] += 1
            a[g][1] += h
    p, w = pct(a["perread"][1], a["perread"][0]), pct(a["whole"][1], a["whole"][0])
    return {"perread": p, "whole": w, "n_perread": a["perread"][0], "n_whole": a["whole"][0],
            "diff": round(p - w, 1) if p is not None and w is not None else None}


def effect(rows):
    """rows: list of (key, y). Returns C2 - C0 in percentage points."""
    a = {c: [0, 0] for c in ("C0", "C2")}
    for k, y in rows:
        a[k[0]][0] += 1
        a[k[0]][1] += y
    p0, p2 = pct(a["C0"][1], a["C0"][0]), pct(a["C2"][1], a["C2"][0])
    return {"C0": p0, "C2": p2, "diff": round(p2 - p0, 1) if p0 is not None and p2 is not None else None}


def loo(rows, fn, field, idx):
    vals = {}
    for u in sorted({r[0][idx] for r in rows}):
        vals[u] = fn([r for r in rows if r[0][idx] != u])[field]
    v = [x for x in vals.values() if x is not None]
    return {"min": min(v), "max": max(v), "by_left_out": vals}


def direction(rows, idx):
    """units (models or tasks) whose C2 - C0 difference is negative, zero, positive."""
    by = defaultdict(list)
    for r in rows:
        by[r[0][idx]].append(r)
    out = {"lower": 0, "equal": 0, "higher": 0}
    for u, rs in by.items():
        d = effect(rs)["diff"]
        if d is None:
            continue
        out["lower" if d < 0 else "higher" if d > 0 else "equal"] += 1
    return out


def main():
    feats, sol, progs = load()
    res, csvrows = {}, []

    # 1. construct split in S4
    s4 = [(k, group(feats[k]), int(bool(v["S4"].get("no_return_90")))) for k, v in sol.items() if "S4" in v and k in feats]
    sp = {"all": split(s4), "without_java": split([r for r in s4 if r[0][3] != "java"])}
    for lang in ("python", "typescript", "java", "go"):
        sp[lang] = split([r for r in s4 if r[0][3] == lang])
    sp["loo_model_diff"] = loo(s4, split, "diff", 1)
    sp["loo_task_diff"] = loo(s4, split, "diff", 2)
    sp["loo_model_diff_without_java"] = loo([r for r in s4 if r[0][3] != "java"], split, "diff", 1)
    sp["loo_task_diff_without_java"] = loo([r for r in s4 if r[0][3] != "java"], split, "diff", 2)
    res["construct_split_s4"] = sp

    # 2. requirements effect
    nolimit = [(k, int(bool(v["S4"].get("no_return_90")))) for k, v in sol.items() if "S4" in v and k[2][0] in "RW"]
    exc = []
    for k, v in sol.items():
        ys = [v[s].get("excessive_retries") for s in ("S7", "S9") if s in v and v[s].get("excessive_retries") is not None]
        if ys:
            exc.append((k, int(any(ys))))
    eff = {}
    for name, rows in (("s4_hang_no_limit", nolimit), ("excessive_s7_s9", exc),
                       ("s4_hang_no_limit_without_java", [r for r in nolimit if r[0][3] != "java"])):
        e = effect(rows)
        e["loo_model"] = loo(rows, effect, "diff", 1)
        e["loo_task"] = loo(rows, effect, "diff", 2)
        e["direction_models"] = direction(rows, 1)
        e["direction_tasks"] = direction(rows, 2)
        e["direction_languages"] = direction(rows, 3)
        eff[name] = e
    res["requirements_effect"] = eff

    # 3. intention to treat
    gen = [tuple(p[k] for k in KEYS) for p in progs]
    def itt(outcome, scen, task_ok):
        rows = []
        for k in gen:
            if not task_ok(k[2]):
                continue
            v = sol.get(k)
            if v is None:  # not runnable or no usable run: failure
                rows.append((k, 1))
                continue
            if outcome == "overrun":
                rows.append((k, int(any(bool(x.get("overrun")) for x in v.values()))))
            elif scen in v:
                rows.append((k, int(bool(v[scen].get(outcome)))))
        return rows
    defs = {"s3_hang": ("no_return_90", "S3", lambda t: True), "overrun": ("overrun", None, lambda t: t[0] in "BH"),
            "duplicate_write": ("unsafe_write_retry", "S8", lambda t: t in ("W1", "W2", "B4")),
            "s4_hang": ("no_return_90", "S4", lambda t: True)}
    it = {}
    for name, (o, s, tk) in defs.items():
        rows = itt(o, s, tk)
        it[name] = {"all": effect(rows)}
        for m in ("qwen3-coder-next", "granite-4.2-8b"):
            it[name][m] = effect([r for r in rows if r[0][1] == m])
        it[name]["without_qwen_granite"] = effect([r for r in rows if r[0][1] not in ("qwen3-coder-next", "granite-4.2-8b")])
    res["intention_to_treat"] = it

    # 4. retry mechanism (exploratory): hand-written loop vs retry library vs the client's built-in retries
    mech = {}
    for name in ("hand_loop", "retry_library", "library_builtin", "none"):
        ks = [k for k in sol if k in feats and name in (feats[k]["retry_mechanism"] or "none").split(";")
              and (name != "none" or (feats[k]["retry_mechanism"] or "none") == "none")]
        def share(scen, field):
            v = [int(bool(sol[k][scen].get(field))) for k in ks if scen in sol[k] and sol[k][scen].get(field) is not None]
            return f"{sum(v)}/{len(v)} ({pct(sum(v), len(v))} %)"
        mech[name] = {"solutions": len(ks), "S7_excessive": share("S7", "excessive_retries"),
                      "S6a_ra_violation": share("S6a", "retry_after_violation"),
                      "S6b_ra_violation": share("S6b", "retry_after_violation"),
                      "S8_duplicate_write": share("S8", "unsafe_write_retry")}
    res["retry_mechanism"] = mech

    # 5. attempts per call during the S7 outage against common client policies (exploratory): AWS SDK standard
    #    retry mode (3 attempts) and the gRPC retry policy (at most 5 attempts); polling task B2 left out
    pol = {}
    for cond in ("C0", "C2"):
        mx = [max(v["S7"]["attempts_per_logical_call"].values()) for k, v in sol.items()
              if k[0] == cond and k[2] != "B2" and "S7" in v and isinstance(v["S7"].get("attempts_per_logical_call"), dict)
              and v["S7"]["attempts_per_logical_call"]]
        pol[cond] = {"solutions": len(mx), **{f"over_{t}": pct(sum(m > t for m in mx), len(mx)) for t in (3, 5, 10)}}
    res["s7_attempts_vs_policies"] = pol

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    for sect, d in (("construct_split_s4", sp), ("requirements_effect", eff)):
        for key, v in d.items():
            if isinstance(v, dict) and "by_left_out" in v:
                for u, x in v["by_left_out"].items():
                    csvrows.append({"section": sect, "measure": key, "left_out": u, "value": x})
            elif isinstance(v, dict):
                for kk in ("loo_model", "loo_task"):
                    if kk in v:
                        for u, x in v[kk]["by_left_out"].items():
                            csvrows.append({"section": sect, "measure": f"{key}:{kk}", "left_out": u, "value": x})
    with open(OUT / "loo.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["section", "measure", "left_out", "value"])
        w.writeheader()
        w.writerows(csvrows)
    short = json.loads(json.dumps(res))
    for d in (short["construct_split_s4"], *short["requirements_effect"].values()):
        for v in d.values():
            if isinstance(v, dict):
                v.pop("by_left_out", None)
    print(json.dumps(short, indent=1))


if __name__ == "__main__":
    main()
