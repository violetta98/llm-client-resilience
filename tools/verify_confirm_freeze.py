"""Compare the files frozen for the confirmatory run (protocol/CONFIRM_FREEZE.json) with their current content.

  python3 tools/verify_confirm_freeze.py

Prints every file whose SHA-256 differs from the frozen value. Expected differences after the run: runner/run_generated.py
(D47, changed after the confirmatory analysis; the run itself used the frozen version) and analysis/measures.py (D59,
two measure corrections applied to all runs).
"""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
d = json.loads((REPO / "protocol" / "CONFIRM_FREEZE.json").read_text())
bad = [k for k, v in d["sha256"].items()
       if not (REPO / k).exists() or hashlib.sha256((REPO / k).read_bytes()).hexdigest() != v]
print(f"frozen {d['frozen_at']}: {len(d['sha256'])} files, {len(d['sha256']) - len(bad)} unchanged")
for k in bad:
    print("  changed:", k)
