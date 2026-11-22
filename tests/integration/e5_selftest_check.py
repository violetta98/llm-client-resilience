"""Checks the result of e5_selftest + run_generated: expected prepare categories,
and every pilot reference meets every criterion in every scenario."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "integration"))
sys.path.insert(0, str(REPO / "runner"))
import orchestrator as o  # noqa: E402
from e3_run import flags_of  # noqa: E402


def main(run):
    base = o.DATA / run
    want = json.loads((base / "selftest_expected.json").read_text())
    progs = {f"{r['model']}/{r['task']}/{r['lang']}/{r['sample']}": r["category"]
             for r in map(json.loads, (base / "programs.jsonl").read_text().splitlines())}
    ok = True
    for k, v in want.items():
        if progs.get(k) != v:
            ok = False
            print(f"CATEGORY {k}: want {v}, got {progs.get(k)}")
    rows = [json.loads(x) for x in (base / "measures.jsonl").read_text().splitlines()]
    n = 0
    for r in rows:
        if r.get("model") != "reference" or r.get("limit_s") != o.LIMIT_S:
            continue
        n += 1
        f = flags_of(r) if "harness_error" not in r else ["HARNESS_ERROR " + r["harness_error"]]
        if f:
            ok = False
            print(f"REFERENCE {r['task']}/{r['lang']} {r['scenario']}: {f}")
    print(f"{n} reference runs checked; categories {len(want)}; {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dev/e5-selftest"))
