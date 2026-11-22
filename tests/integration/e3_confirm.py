"""E3 for the confirmatory tasks R6, W5, B5, H4: tests/integration/e3_run.py, unchanged,
with the result checks of analysis/checkers_confirm.py installed first.

e3_run.py is frozen with protocol v1 and its checker (analysis/checkers.py) raises
KeyError for tasks it does not know, which e3_run.py reports as a harness error.
This entry point only installs the additional checks and then runs e3_run.main()
with the same command-line arguments, e.g.

  python3 tests/integration/e3_confirm.py --langs python --index references/index-confirm-python.json \
      --slots 3 --out dev/e3/confirm-python
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkers_confirm  # noqa: E402

checkers_confirm.install()
import e3_run  # noqa: E402

if __name__ == "__main__":
    e3_run.main()
