"""D53: re-run S4 for the Java solutions of the held-out run (confirm) on JDK 26, as D52 did for the main run.
Installs the held-out result checks (as runner/run_confirm.py does) and the JDK 26 image (as runner/run_jdk26.py does).

  python3 runner/run_confirm_jdk26.py --run confirm-jdk26 --variants-of confirm \
      --select-file data/confirm_java_select.txt --variants S4 --slots 3
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "runner"))
import checkers_confirm  # noqa: E402

checkers_confirm.install()
import orchestrator as o  # noqa: E402

o.RUNNER_IMAGES["java"] = "lcr-run-java:jdk26"
import run_generated  # noqa: E402

if __name__ == "__main__":
    run_generated.main()
