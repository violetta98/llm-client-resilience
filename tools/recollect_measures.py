"""Rebuild data/<run>/measures.jsonl from the run directories (D47).

  python3 tools/recollect_measures.py --run main-variants

runner/run_generated.py wrote measures.jsonl from the rows of its own invocation only, so a later invocation on the
same run ID (the S0slow run of D45 on main-variants and repair-variants) replaced the rows of the earlier variants.
The raw run directories were never touched. This script recomputes every row with analysis/measures.py exactly as the
runner does (M.compute on M.load_run, per-task expected.yaml), for runs/ (90 s) and rerun330/ (330 s). The replaced
file is kept as measures.jsonl.before-D47.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "runner"))
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402

DATA = REPO / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    base = DATA / a.run
    exp, rows, errors = {}, [], 0
    for top, limit in (("runs", 90), ("rerun330", 330)):
        for res in sorted((base / top).glob("*/*/*/*/*/*/result.json")):
            d = res.parent
            cond, model, task, lang, sample, _ = d.relative_to(base / top).parts
            exp.setdefault(task, yaml.safe_load((M.task_dir(task) / "expected.yaml").read_text()))
            key = {"cond": cond, "model": model, "task": task, "lang": lang, "sample": int(sample)}
            out_rel = str(d.relative_to(DATA))
            try:
                row = M.compute(M.load_run(d), exp[task], cond=cond)
                rows.append({**row, **key, "dir": out_rel, "limit_s": limit, "slot_s": None, "recollected": True})
            except Exception as e:  # noqa: BLE001
                errors += 1
                rows.append({**key, "scenario": d.name, "dir": out_rel, "limit_s": limit, "harness_error": repr(e)})
    mf = base / "measures.jsonl"
    if mf.exists() and not (base / "measures.jsonl.before-D47").exists():
        shutil.copy2(mf, base / "measures.jsonl.before-D47")
    with open(mf, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    by = {}
    for r in rows:
        by[Path(r["dir"]).name] = by.get(Path(r["dir"]).name, 0) + 1
    print(json.dumps({"run": a.run, "rows": len(rows), "errors": errors, "by_variant": by}, indent=1))


if __name__ == "__main__":
    main()
