"""Freeze the confirmatory addendum (D43): SHA-256 of every file it depends on -> protocol/CONFIRM_FREEZE.json."""
import hashlib, json, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
FILES = ["protocol/CONFIRM_ADDENDUM.md", "protocol/thresholds.json", "gen/config/confirm.json",
         "tasks/confirm_catalog.py", "tasks/generate_confirm.py", "tasks/confirm_checks.json", "tasks/CONFIRM_TASKS.md",
         "mock/tasks_confirm.go", "analysis/checkers_confirm.py", "analysis/measures.py", "analysis/s4_mechanism.py",
         "analysis/collect_confirm.py", "analysis/confirm_analysis.py", "analysis/confirm_model.R",
         "classify/features.py", "classify/lint.py", "runner/run_confirm.py", "runner/run_generated.py"]
files = [REPO / f for f in FILES]
for t in ("R6", "W5", "B5", "H4"):
    files += sorted(p for p in (REPO / "tasks" / t).rglob("*") if p.is_file())
files += sorted(p for p in (REPO / "references").rglob("*confirm*") if p.is_file())
import sys
if (REPO / "protocol" / "CONFIRM_FREEZE.json").exists():
    sys.exit("protocol/CONFIRM_FREEZE.json exists; the freeze is never rewritten (check with tools/verify_confirm_freeze.py)")
out = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sha256": {}}
for p in files:
    out["sha256"][str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
(REPO / "protocol" / "CONFIRM_FREEZE.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["sha256"]), "files frozen")
