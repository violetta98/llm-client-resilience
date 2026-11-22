"""D54: free analyses requested by the round-10 reviewers (existing data only).

  python3 analysis/review_round10.py   -> analysis/out/review10/summary.json
1. S7 delay growth: among solutions flagged for excessive retries, is the gap between attempts growing?
   For the logical call with the most attempts during the outage: growing if the median of the last three gaps
   exceeds the first gap. Main run, both conditions, with and without B2.
2. AP10: S5a/S5b failures that the task does not allow (outcome not allowed or no return), main run, C0.
3. Held-out H1 and H2 with the Java S4 runs taken from JDK 26 (confirm-jdk26).
4. Ablation: risk differences with a bootstrap over models (2,000 resamples) and marginal odds ratios for P1-P3.
5. Main run, C2, R and W tasks: share over 10.25 s in any scenario with Java S4 from JDK 26.
6. Ablation S4 in R6/W5 with the Java S4 runs from JDK 26 (confirm-jdk26, ablation-jdk26), per condition and P2.
"""
import ast, csv, json, random, statistics, sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from confirm_analysis import WHOLE  # noqa: E402

OUT = REPO / "analysis" / "out" / "review10"
KEYS = ("cond", "model", "task", "lang", "sample")


def rows(run):
    for l in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(l)
        if r.get("usable") and r.get("limit_s") == 90:
            yield r


def key(r):
    return tuple(str(r[k]) for k in KEYS)


def growth():
    res = {}
    for drop_b2 in (False, True):
        for cond in ("C0", "C2"):
            n = grow = 0
            for r in rows("main"):
                if r["scenario"] != "S7" or r["cond"] != cond or not r.get("excessive_retries"):
                    continue
                if drop_b2 and r["task"] == "B2":
                    continue
                t = r.get("attempt_times_s7")
                t = ast.literal_eval(t) if isinstance(t, str) else t
                if not t:
                    continue
                call = max(t, key=len)
                g = [(b - a) / 1e9 for a, b in zip(call, call[1:])]
                if len(g) < 4:
                    continue
                n += 1
                grow += statistics.median(g[-3:]) > g[0]
            res[f"{cond}{'_noB2' if drop_b2 else ''}"] = {"flagged": n, "growing": grow}
    return res


def ap10():
    res = {}
    for sc in ("S5a", "S5b"):
        for cond in ("C0", "C2"):
            rs = [r for r in rows("main") if r["scenario"] == sc and r["cond"] == cond]
            res[f"{sc}_{cond}"] = {"n": len(rs), "not_correct": sum(r["outcome"] != "correct" for r in rs),
                                   "not_allowed": sum((not r.get("outcome_allowed")) or bool(r.get("no_return")) for r in rs)}
    return res


def heldout_jdk26():
    feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(REPO / "data" / "confirm" / "classify" / "features.csv"))}
    s4 = {key(r): r for r in rows("confirm") if r["scenario"] == "S4"}
    s26 = {key(r): r for r in rows("confirm-jdk26") if r["scenario"] == "S4"}
    progs = {tuple(p[k] for k in KEYS): p for p in csv.DictReader(open(REPO / "analysis" / "out" / "confirm" / "programs.csv"))}
    out = {}
    for jdk in ("25", "26"):
        h1 = defaultdict(lambda: [0, 0]); h2 = defaultdict(lambda: [0, 0])
        for k, r in s4.items():
            if progs.get(k, {}).get("category") != "ok":
                continue
            rr = s26.get(k, r) if jdk == "26" and k[3] == "java" else r
            y = int(bool(rr["no_return_90"]))
            cons = {c.strip() for c in (feats.get(k, {}).get("timeout_constructs") or "").split(";") if c.strip()}
            g = h1["with" if cons & WHOLE else "without"]; g[0] += y; g[1] += 1
            if k[2] in ("R6", "W5"):
                g = h2[k[0]]; g[0] += y; g[1] += 1
        out["jdk" + jdk] = {"H1": dict(h1), "H2": dict(h2)}
    return out


def ablation():
    d = list(csv.DictReader(open(REPO / "analysis" / "out" / "ablation" / "ablation_p.csv")))
    rng = random.Random(20261120)
    out = {}
    for h in ("P1", "P2", "P3"):
        dh = [r for r in d if r["hyp"] == h]
        by = defaultdict(list)
        for r in dh:
            by[r["model"]].append(r)
        models = sorted(by)

        def rd(rs):
            a = [int(r["y"]) for r in rs if r["c"] == "1"]; b = [int(r["y"]) for r in rs if r["c"] == "0"]
            return (sum(a) / len(a) - sum(b) / len(b)) if a and b else None
        est = sorted(e for e in (rd([r for m in (rng.choice(models) for _ in models) for r in by[m]]) for _ in range(2000)) if e is not None)
        a1 = sum(int(r["y"]) for r in dh if r["c"] == "1"); n1 = sum(r["c"] == "1" for r in dh)
        a0 = sum(int(r["y"]) for r in dh if r["c"] == "0"); n0 = sum(r["c"] == "0" for r in dh)
        mor = ((a1 + .5) / (n1 - a1 + .5)) / ((a0 + .5) / (n0 - a0 + .5))
        out[h] = {"c1": f"{a1}/{n1}", "c0": f"{a0}/{n0}", "rd_pp": round(100 * rd(dh), 1),
                  "rd_lo": round(100 * est[int(.025 * len(est))], 1), "rd_hi": round(100 * est[int(.975 * len(est)) - 1], 1),
                  "marginal_or_haldane": round(mor, 3)}
    return out


def c2_over10_jdk26():
    s26 = {key(r): r for r in rows("main-jdk26") if r["scenario"] == "S4"}
    per = defaultdict(dict)
    for r in rows("main"):
        if r["cond"] == "C2" and r["task"][0] in "RW":
            per[key(r)][r["scenario"]] = r
    res = {}
    for jdk in ("25", "26"):
        n = over = 0
        for k, v in per.items():
            vv = dict(v)
            if jdk == "26" and k[3] == "java" and k in s26 and "S4" in vv:
                vv["S4"] = s26[k]
            n += 1
            over += any(bool(x.get("no_return")) or max([t for t in (x.get("durations_s") or []) if t is not None] or [0]) > 10.25 for x in vv.values())
        res["jdk" + jdk] = {"n": n, "over_10s": over, "pct": round(100 * over / n, 1)}
    return res


def ablation_jdk26():
    base = {key(r): r for run in ("confirm", "ablation") for r in rows(run) if r["scenario"] == "S4"}
    j26 = {key(r): r for run in ("confirm-jdk26", "ablation-jdk26") for r in rows(run) if r["scenario"] == "S4"}
    d = [r for r in csv.DictReader(open(REPO / "analysis" / "out" / "ablation" / "ablation_p.csv")) if r["hyp"] == "P2"]
    out = {}
    for cond in ("C0", "C0b", "C2", "C2c"):
        ks = [k for k in base if k[0] == cond and k[2] in ("R6", "W5")]
        y26 = [bool((j26.get(k, base[k]) if k[3] == "java" else base[k])["no_return_90"]) for k in ks]
        out[cond] = {"n": len(ks), "hang_jdk25": sum(bool(base[k]["no_return_90"]) for k in ks), "hang_jdk26": sum(y26)}
    rng = random.Random(20261120)
    by = defaultdict(list)
    for r in d:
        k = (r["cond"], r["model"], r["task"], r["lang"], r["sample"])
        y = bool((j26.get(k, base[k]) if k[3] == "java" else base[k])["no_return_90"])
        by[r["model"]].append((int(r["c"]), int(y)))
    models = sorted(by)

    def rd(rs):
        a = [y for c, y in rs if c == 1]; b = [y for c, y in rs if c == 0]
        return sum(a) / len(a) - sum(b) / len(b) if a and b else None
    allr = [x for m in models for x in by[m]]
    est = sorted(e for e in (rd([x for m in (rng.choice(models) for _ in models) for x in by[m]]) for _ in range(2000)) if e is not None)
    out["P2_jdk26"] = {"rd_pp": round(100 * rd(allr), 1), "lo": round(100 * est[int(.025 * len(est))], 1),
                       "hi": round(100 * est[int(.975 * len(est)) - 1], 1)}
    return out


def main():
    res = {"s7_growth": growth(), "ap10": ap10(), "heldout_jdk26": heldout_jdk26(), "ablation": ablation(),
           "c2_rw_over10_jdk26": c2_over10_jdk26(), "ablation_jdk26": ablation_jdk26()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
