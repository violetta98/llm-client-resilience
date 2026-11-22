"""D53: S4 on JDK 26 for the Java solutions of the held-out set (confirm-jdk26) and the repair revisions (repair-jdk26).

  python3 analysis/jdk26_heldout_repair.py   -> analysis/out/jdk26b/summary.json
Compares S4 no_return_90 with the JDK 25 runs, and recomputes the repair fix rate in Java with S4 taken from JDK 26
for both the originals (main-jdk26) and the revisions; other scenarios unchanged.
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair_analysis import tests_failed, s0_correct  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out" / "jdk26b"
KEYS = ("cond", "model", "task", "lang", "sample")


def load(run, scen=None):
    per = defaultdict(dict)
    for l in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(l)
        if r.get("usable") and r["limit_s"] == 90 and r["lang"] == "java" and (scen is None or r["scenario"] == scen):
            per[tuple(str(r[k]) for k in KEYS)][r["scenario"]] = r
    return per


def wcd(feat):
    return feat.get("whole_call_deadline") in ("1", "True", "true")


def main():
    res = {}
    # held-out
    c25, c26 = load("confirm", "S4"), load("confirm-jdk26", "S4")
    feats = {}
    fp = REPO / "data" / "confirm" / "classify" / "features.csv"
    if fp.exists():
        feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(fp))}
    h = defaultdict(lambda: [0, 0, 0])
    for k, v in c26.items():
        if k not in c25:
            continue
        a, b = c25[k]["S4"], v["S4"]
        g = h[k[0]]
        g[0] += 1; g[1] += bool(a["no_return_90"]); g[2] += bool(b["no_return_90"])
    res["heldout_S4"] = {c: {"n": g[0], "hang_jdk25": g[1], "hang_jdk26": g[2]} for c, g in h.items()}
    ret = [v["S4"] for k, v in c26.items() if k in c25 and c25[k]["S4"]["no_return_90"] and not v["S4"]["no_return_90"]]
    res["heldout_returned"] = {"n": len(ret), "after_10.25s": sum(max(x for x in r["durations_s"] if x is not None) > 10.25 for r in ret),
                               "max_s": round(max(max(x for x in r["durations_s"] if x is not None) for r in ret), 1) if ret else None,
                               "outcomes": dict(defaultdict(int, {o: sum(r["outcome"] == o for r in ret) for o in {r["outcome"] for r in ret}}))}
    # repair
    src25 = load("main"); src26 = load("main-jdk26", "S4")
    rep25 = load("repair"); rep26 = load("repair-jdk26", "S4")
    sel = sorted({tuple(r[k] for k in KEYS) for r in csv.DictReader(open(REPO / "data" / "repair" / "prompts" / "selection.csv")) if r["lang"] == "java"})
    progs = {tuple(p[k] for k in KEYS): p for p in csv.DictReader(open(REPO / "analysis" / "out" / "repair" / "programs.csv"))}
    out = {}
    for arm in ("R0", "R1"):
        n25 = f25 = n26 = f26 = 0
        h25 = h26 = nrev = 0
        for k in sel:
            rk = (arm,) + k[1:]
            runnable = rk in rep25 and progs.get(rk, {}).get("category") == "ok"
            o25 = tests_failed(src25[k].values())
            s26 = dict(src25[k]); 
            if k in src26: s26["S4"] = src26[k]["S4"]
            o26 = tests_failed(s26.values())
            if runnable:
                r25 = rep25[rk]; r26 = dict(r25)
                if rk in rep26: r26["S4"] = rep26[rk]["S4"]
                if "S4" in r25 and rk in rep26:
                    nrev += 1; h25 += bool(r25["S4"]["no_return_90"]); h26 += bool(rep26[rk]["S4"]["no_return_90"])
            if o25:
                n25 += 1; f25 += int(runnable and not (o25 & tests_failed(r25.values())))
            if o26:
                n26 += 1; f26 += int(runnable and not (o26 & tests_failed(r26.values())))
        out[arm] = {"failing_jdk25": n25, "fixed_jdk25": f25, "failing_jdk26": n26, "fixed_jdk26": f26,
                    "revisions_with_S4": nrev, "rev_hang_jdk25": h25, "rev_hang_jdk26": h26}
    res["repair_java"] = out
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
