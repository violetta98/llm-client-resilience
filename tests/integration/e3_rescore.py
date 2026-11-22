"""Recomputes measures and verdicts of an E3 run directory from its raw data
(no new runs). Usage: python3 tests/integration/e3_rescore.py data/dev/e3/<stamp>"""
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "tests" / "integration"))
import measures as M  # noqa: E402
from e3_run import NOT_APPLICABLE, TARGET, flags_of  # noqa: E402

base = Path(sys.argv[1])
rows = []
for d in sorted(base.glob("runs/*/*/*/*")):
    lang, t, v, sc = d.parts[-4:]
    exp = yaml.safe_load((M.task_dir(t) / "expected.yaml").read_text())
    row = M.compute(M.load_run(d), exp, cond="C2")
    row.update(variant=v, lang=lang, dir=str(d))
    rows.append(row)
with open(base / "measures.rescored.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r, default=str) + "\n")
by = {}
for r in rows:
    by.setdefault((r["lang"], r["task"], r["variant"]), []).append(r)
ref_ok = mut_ok = nref = nmut = 0
for (lang, t, v), rs in sorted(by.items()):
    if v.startswith("BASELINE"):
        continue
    if v == "REFERENCE":
        nref += 1
        bad = {r["scenario"]: flags_of(r) for r in rs if flags_of(r)}
        ref_ok += not bad
        if bad:
            print(f"REFERENCE FAIL {lang}/{t}: {bad}")
    else:
        nmut += 1
        scs, meas = TARGET[v]
        if v == "TIGHT_LOOP" and t == "B1":
            scs, meas = ["S7"], "excessive_retries"
        hit = any(r.get(meas) for r in rs if r["scenario"] in scs)
        if (t, v) in NOT_APPLICABLE:
            print(f"n/a {lang}/{t}/{v} (flagged: {hit})")
            nmut -= 1
            continue
        mut_ok += hit
        if not hit:
            print(f"MUTANT NOT FLAGGED {lang}/{t}/{v}: {[(r['scenario'], flags_of(r)) for r in rs if flags_of(r)]}")
print(f"references {ref_ok}/{nref} pass; mutants {mut_ok}/{nmut} flagged by target")
