"""D52: re-run S4 for the Java solutions of the main run on JDK 26 (image lcr-run-java:jdk26, built from
runner/images/java26.Dockerfile), to check how much of the Java S4 result depends on JDK-8208693.
The prepared classes (compiled with JDK 25, --release 25) are run unchanged; only the runtime image differs.

  python3 runner/run_jdk26.py --run main-jdk26 --variants-of main --select-file data/main_java_select.txt \
      --variants S4 --slots 3
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "runner"))
import orchestrator as o  # noqa: E402

o.RUNNER_IMAGES["java"] = "lcr-run-java:jdk26"
import run_generated  # noqa: E402

if __name__ == "__main__":
    run_generated.main()
