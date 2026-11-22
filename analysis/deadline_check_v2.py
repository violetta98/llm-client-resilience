"""D61: a revised static check for a whole-call deadline, post hoc (the frozen classifier is not changed).

  python3 analysis/deadline_check_v2.py   -> analysis/out/deadline_v2/{scores.csv,summary.json,per_solution.csv}

The frozen check (Sect. 6.4.1 of the paper; WHOLE in s4_mechanism.py) flags a solution when the classifier finds no
whole-call deadline construct. The revised rules come from the author's manual checks (D59, D60) and the external
review of 2026-11-21; each is a lexical heuristic on comment-free source:
  Python  + a worker thread awaited with a timeout: queue `.get(timeout=...)`, `.join(t)` of a Thread, `Event.wait(t)`;
          - `Future.result(t)` / `concurrent.futures.wait(t)` inside `with ...ThreadPoolExecutor(...)` without
            `shutdown(wait=False)`: the block waits for the worker on exit, so the deadline has no effect.
  TS      - an AbortController timer cleared (`clearTimeout`) before the body is read: the first `clearTimeout` after
            the first `fetch(` precedes the first body read (`.json(`, `.text(`, `.arrayBuffer(`, `.blob(`);
          - a `setTimeout` imported from `timers/promises` (its callback never runs);
          - ky `timeout` without a shortcut body method chained to the ky call, or `timeout: false`;
          + got `timeout: {read}`, which bounds the body (checked by the pre-submission AI reviewer).
  Java    + `CountDownLatch.await(t, unit)` or `awaitTermination(t, unit)` around the call.
Scored like the linters (Table 10 of the paper): failing = no return within 90 s in some scenario or a time-limit
overrun; and against the author's blind whole-call labels (100 programs) and the held-out H1 split. Because the rules
were written after reading these cases, the agreement with the author's labels is optimistic.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from s4_mechanism import WHOLE  # noqa: E402

KEYS = ("cond", "model", "task", "lang", "sample")
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
OUT = REPO / "analysis" / "out" / "deadline_v2"


def strip_comments(code, lang):
    if lang == "python":
        code = re.sub(r"(?m)#.*$", "", code)
        return re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '""', code)
    code = re.sub(r"/\*(?:.|\n)*?\*/", "", code)
    return re.sub(r"(?m)//.*$", "", code)


def first(pat, code, start=0):
    m = re.compile(pat).search(code, start)
    return m.start() if m else None


def v2_whole(cons, code, lang):
    whole = set(cons) & WHOLE
    notes = []
    if lang == "python":
        thread = bool(re.search(r"threading\.Thread\(|Thread\(target", code))
        if re.search(r"\.get\([^)]*timeout\s*=", code) and re.search(r"[Qq]ueue\(", code):
            whole.add("queue.get(timeout)"); notes.append("+queue.get")
        if thread and re.search(r"\.join\(\s*(timeout\s*=)?\s*[\w.]+[^)]*\)", code):
            whole.add("Thread.join(t)"); notes.append("+thread.join")
        if re.search(r"Event\(\)", code) and re.search(r"\.wait\(\s*(timeout\s*=)?\s*[\w.]+", code):
            whole.add("Event.wait(t)"); notes.append("+event.wait")
        if "Future.result(timeout)" in whole and re.search(r"with\s+(concurrent\.futures\.)?ThreadPoolExecutor\(", code) \
                and "shutdown(wait=False" not in code:
            whole.discard("Future.result(timeout)"); notes.append("-future in with-block")
    elif lang == "typescript":
        if "AbortController+setTimeout" in whole:
            if re.search(r"import\s*\{[^}]*\bsetTimeout\b(?!\s+as\b)[^}]*\}\s*from\s*['\"](node:)?timers/promises", code):
                whole.discard("AbortController+setTimeout"); notes.append("-timers/promises")
            else:
                f = first(r"\bfetch\(", code)
                if f is not None:
                    c = first(r"\bclearTimeout\(", code, f)
                    b = first(r"\.(json|text|arrayBuffer|blob)\(\s*\)", code, f)
                    if c is not None and b is not None and c < b:
                        whole.discard("AbortController+setTimeout"); notes.append("-timer cleared before body")
        if "ky timeout" in whole:
            shortcut = re.search(r"\bky(\.\w+)?\((?:[^()]|\([^()]*\))*\)\s*\.(json|text|arrayBuffer|blob)\(", code)
            if re.search(r"timeout\s*:\s*false", code) or not shortcut:
                whole.discard("ky timeout"); notes.append("-ky without shortcut")
        if re.search(r"timeout\s*:\s*\{[^}]*\bread\s*:", code) and re.search(r"from\s+['\"]got['\"]|require\(['\"]got['\"]\)", code):
            whole.add("got timeout.read"); notes.append("+got read")
    elif lang == "java":
        if re.search(r"\.await\(\s*[\w.]+\s*,\s*TimeUnit\.", code) or re.search(r"awaitTermination\(", code):
            whole.add("await(t, unit)"); notes.append("+await")
    return whole, notes


def pct(a, n):
    return round(100 * a / n, 1) if n else None


def score(flag, truth, ks):
    pos = [k for k in ks if truth[k]]
    neg = [k for k in ks if not truth[k]]
    tp = sum(flag[k] for k in pos)
    fp = sum(flag[k] for k in neg)
    return {"solutions": len(ks), "failing": len(pos), "flagged_failing": tp, "recall": pct(tp, len(pos)),
            "precision": pct(tp, tp + fp), "false_alarms": fp, "false_alarm_rate": pct(fp, len(neg))}


def solutions(run, gen_root):
    feats = {tuple(f[k] for k in KEYS): f for f in csv.DictReader(open(REPO / "data" / run / "classify" / "features.csv"))}
    per = defaultdict(list)
    for line in open(REPO / "analysis" / "out" / run / "runs.jsonl"):
        r = json.loads(line)
        if r.get("usable") and r["limit_s"] == 90:
            per[tuple(str(r[k]) for k in KEYS)].append(r)
    rows = {}
    for k, rs in per.items():
        if k not in feats:
            continue
        p = REPO / "data" / gen_root / "generations" / k[0] / k[1] / k[2] / k[3] / k[4] / f"solution.{EXT[k[3]]}"
        code = strip_comments(p.read_text(errors="replace"), k[3]) if p.exists() else ""
        cons = {x for x in feats[k]["timeout_constructs"].split(";") if x}
        w2, notes = v2_whole(cons, code, k[3])
        rows[k] = {"v1": bool(cons & WHOLE), "v2": bool(w2), "notes": ";".join(notes),
                   "fail": any(bool(r.get("no_return")) or bool(r.get("overrun")) for r in rs),
                   "s4": any(bool(r.get("no_return_90")) for r in rs if r["scenario"] == "S4"),
                   "has_s4": any(r["scenario"] == "S4" for r in rs)}
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res, table = {}, []
    for run in ("main", "confirm"):
        sol = solutions(run, run)
        res[run] = {"changed_v1_to_v2": sum(v["v1"] != v["v2"] for v in sol.values()),
                    "changes_by_note": {}}
        cnt = defaultdict(int)
        for v in sol.values():
            if v["v1"] != v["v2"]:
                cnt[v["notes"]] += 1
        res[run]["changes_by_note"] = dict(cnt)
        for ver in ("v1", "v2"):
            flag = {k: not v[ver] for k, v in sol.items()}
            for target in ("fail", "s4"):
                truth = {k: v[target] for k, v in sol.items()}
                for lang in ("python", "typescript", "java", "go", "all"):
                    ks = [k for k in sol if (lang == "all" or k[3] == lang) and (target != "s4" or sol[k]["has_s4"])]
                    table.append({"run": run, "check": ver, "target": target, "lang": lang, **score(flag, truth, ks)})
            # S4 construct split under this version
            ks = [k for k, v in sol.items() if v["has_s4"]]
            a = {True: [0, 0], False: [0, 0]}
            for k in ks:
                a[sol[k][ver]][0] += 1
                a[sol[k][ver]][1] += sol[k]["s4"]
            res[run][f"s4_split_{ver}"] = {"with_deadline": f"{a[True][1]}/{a[True][0]} ({pct(a[True][1], a[True][0])} %)",
                                           "without": f"{a[False][1]}/{a[False][0]} ({pct(a[False][1], a[False][0])} %)"}
        if run == "main":
            man = list(csv.DictReader(open(REPO / "data" / "main" / "classify" / "manual_check.csv")))
            for ver in ("v1", "v2"):
                pairs = []
                for m in man:
                    k = tuple(m[x] for x in KEYS)
                    if k in sol and (m.get("author_whole_call") or "").strip():
                        pairs.append((int(sol[k][ver]), int(m["author_whole_call"])))
                po = sum(a == b for a, b in pairs) / len(pairs)
                pa, pb = sum(a for a, _ in pairs) / len(pairs), sum(b for _, b in pairs) / len(pairs)
                pe = pa * pb + (1 - pa) * (1 - pb)
                res["main"][f"author_labels_{ver}"] = {"n": len(pairs), "agree": round(100 * po, 1),
                                                       "kappa": round((po - pe) / (1 - pe), 3)}
        with open(OUT / f"per_solution_{run}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(list(KEYS) + ["v1_whole", "v2_whole", "notes", "fail", "s4_hang"])
            for k, v in sorted(sol.items()):
                w.writerow(list(k) + [int(v["v1"]), int(v["v2"]), v["notes"], int(v["fail"]), int(v["s4"])])
    with open(OUT / "scores.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(table[0]))
        w.writeheader()
        w.writerows(table)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    for r in table:
        if r["target"] == "fail":
            print(r["run"], r["check"], r["lang"], r["failing"], r["flagged_failing"], "recall", r["recall"],
                  "prec", r["precision"], "FA", r["false_alarms"], "of", r["solutions"] - r["failing"])


if __name__ == "__main__":
    main()
