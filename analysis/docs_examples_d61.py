"""D61: fault-injection results of the documentation examples (docs_examples/), from data/docs/measures.jsonl.

  python3 analysis/docs_examples_d61.py   -> analysis/out/docs/summary.csv, summary.json
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "out" / "docs"


def main():
    per = defaultdict(dict)
    for line in open(REPO / "data" / "docs" / "measures.jsonl"):
        r = json.loads(line)
        if r.get("limit_s", 90) != 90 or not r.get("harness_ok", True):
            continue
        per[(r["model"], r["lang"])][r["scenario"]] = r
    rows = []
    for (name, lang), sc in sorted(per.items()):
        def nr(s):
            x = sc.get(s)
            return None if x is None else int(bool(x.get("no_return_90") or x.get("no_return")))
        def dur(s):
            x = sc.get(s) or {}
            d = [t for t in (x.get("durations_s") or []) if t is not None]
            return round(max(d), 1) if d else None
        def flag(s, f):
            x = sc.get(s)
            return None if x is None or x.get(f) is None else int(bool(x.get(f)))
        rows.append({"example": name, "lang": lang,
                     "S1_hang": nr("S1"), "S1_s": dur("S1"), "S2_hang": nr("S2"), "S3_hang": nr("S3"), "S3_s": dur("S3"),
                     "S4_hang": nr("S4"), "S4_s": dur("S4"),
                     "S0_outcome": (sc.get("S0") or {}).get("outcome"),
                     "S5a_outcome": (sc.get("S5a") or {}).get("outcome"),
                     "S7_excessive": flag("S7", "excessive_retries"), "S9_excessive": flag("S9", "excessive_retries"),
                     "S9_rapid": flag("S9", "rapid_retries"),
                     "S6a_ra_violation": flag("S6a", "retry_after_violation"),
                     "S6b_ra_violation": flag("S6b", "retry_after_violation")})
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    agg = {"examples": len(rows), "S0_correct": sum(r["S0_outcome"] == "correct" for r in rows),
           "S4_hang": sum(r["S4_hang"] or 0 for r in rows), "S3_hang": sum(r["S3_hang"] or 0 for r in rows),
           "S1_hang": sum(r["S1_hang"] or 0 for r in rows)}
    (OUT / "summary.json").write_text(json.dumps({"aggregate": agg, "rows": rows}, indent=1) + "\n")
    print(json.dumps(agg))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
