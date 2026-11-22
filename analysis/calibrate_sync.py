"""Calibration of the synchronized-retry threshold (draft Table V: 0.8,
"calibrated on reference solutions before the freeze").

Reads the S7 rows of E3 runs (references and FIXED_BACKOFF mutants), takes
for each program the largest share of k-th attempts (k >= 2) within 50 ms,
and reports both distributions and the interval of thresholds that
separates them. Usage: python3 analysis/calibrate_sync.py data/dev/e3/<dir> ...
Writes analysis/out/sync_calibration.json.
"""
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import measures as M  # noqa: E402


def main(dirs):
    groups = {"REFERENCE": [], "FIXED_BACKOFF": []}
    for base in dirs:
        for d in sorted(Path(base).glob("runs/*/*/*/S7")):
            lang, t, v = d.parts[-4:-1]
            if v not in groups:
                continue
            exp = yaml.safe_load((REPO / "tasks" / t / "expected.yaml").read_text())
            row = M.compute(M.load_run(d), exp)
            shares = row.get("sync_shares") or {}
            groups[v].append({"lang": lang, "task": t, "max_share": max(shares.values()) if shares else None,
                              "shares": shares, "k_reached": sorted(shares)})
    ref = sorted(x["max_share"] for x in groups["REFERENCE"] if x["max_share"] is not None)
    fix = sorted(x["max_share"] for x in groups["FIXED_BACKOFF"] if x["max_share"] is not None)
    out = {
        "n_reference": len(groups["REFERENCE"]), "n_reference_with_k2": len(ref),
        "n_fixed_backoff": len(groups["FIXED_BACKOFF"]), "n_fixed_with_k2": len(fix),
        "reference_max_share": {"max": ref[-1] if ref else None, "values": ref},
        "fixed_backoff_max_share": {"min": fix[0] if fix else None, "values": fix},
        "separating_interval": [ref[-1], fix[0]] if ref and fix and ref[-1] < fix[0] else None,
        "draft_threshold": M.TH["sync_threshold"],
        "programs": groups,
    }
    o = REPO / "analysis" / "out"
    o.mkdir(parents=True, exist_ok=True)
    (o / "sync_calibration.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "programs"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
