"""D61: mutant PER_READ_ONLY for the 16 main tasks in Python, requested in pre-submission AI review: the reference solution
with its whole-call bound removed (the worker thread is joined without a timeout), so that only requests' own
connect and read timeouts remain (read timeout = the attempt budget). The references themselves are not changed.

  python3 tools/make_perread_mutants_d61.py
  python3 runner/run_generated.py --run mutants-d61 --scenarios S4 --no-rerun --slots 3
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TASKS = ["R1", "R2", "R3", "R4", "R5", "W1", "W2", "W3", "W4", "B1", "B2", "B3", "B4", "H1", "H2", "H3"]
n = 0
for t in TASKS:
    src = (REPO / "references" / t / "python" / "solution.py").read_text()
    assert src.count("th.join(timeout_s)") == 1, t
    mut = src.replace("th.join(timeout_s)", "th.join()  # D61 mutant PER_READ_ONLY: no whole-call bound")
    mut = mut.replace("MUTANT=NONE", "MUTANT=PER_READ_ONLY (D61, derived from the reference)", 1)
    d = REPO / "data" / "mutants-d61" / "generations" / "MUT" / "PER_READ_ONLY" / t / "python" / "1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "solution.py").write_text(mut)
    (d / "meta.json").write_text(json.dumps({"status": "ok", "model_id": "PER_READ_ONLY", "note": "D61 mutant",
                                             "extraction": {"status": "fenced", "n_blocks": 1, "n_target_blocks": 1}}, indent=1))
    n += 1
print(n, "mutants written")
