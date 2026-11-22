"""runner/run_generated.py, unchanged, for the confirmatory run (tasks R6, W5, B5, H4):
installs the result checks of analysis/checkers_confirm.py, then runs
run_generated.main() with the same command-line arguments, e.g.

  python3 runner/run_confirm.py --run confirm --slots 3

run_generated.py is frozen with protocol v1 and its checker (analysis/checkers.py)
raises KeyError for tasks it does not know. Nothing else is changed: every
scenario of each task's expected.yaml is run (run_generated.py has no scenario
filter; see tasks/CONFIRM_TASKS.md).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "runner"))
import checkers_confirm  # noqa: E402

checkers_confirm.install()
import run_generated  # noqa: E402

if __name__ == "__main__":
    run_generated.main()
