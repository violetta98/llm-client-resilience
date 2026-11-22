"""analysis/collect.py for run `confirm` (D43): installs the result checks of the four new tasks, then runs
collect.main() unchanged.   python3 analysis/collect_confirm.py --run confirm --jobs 4"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkers_confirm  # noqa: E402
checkers_confirm.install()
import collect  # noqa: E402
if __name__ == "__main__":
    collect.main()
