"""Self-test of faultkit (D61): the specification's tests against the R1 reference (should pass), its mutants and
the documentation examples (each should fail the test that targets its defect).

  docker run --rm --network none -v "$PWD:/w" -w /w lcr-run-python:dev python3 testkit/selftest.py
Writes testkit/selftest_result.json and prints one line per (program, test).
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import faultkit as fk  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PROGRAMS = {
    "reference": REPO / "references/R1/python/solution.py",
    "mutant NO_TIMEOUT": REPO / "mutants/R1/python/NO_TIMEOUT/solution.py",
    "mutant PER_READ_ONLY": REPO / "data/mutants-d61/generations/MUT/PER_READ_ONLY/R1/python/1/solution.py",
    "mutant IGNORE_RETRY_AFTER": REPO / "mutants/R1/python/IGNORE_RETRY_AFTER/solution.py",
    "mutant TIGHT_LOOP": REPO / "mutants/R1/python/TIGHT_LOOP/solution.py",
    "docs requests timeout=5": REPO / "docs_examples/R1/py-requests-timeout5.py",
    "docs httpx timeout=10.0": REPO / "docs_examples/R1/py-httpx-timeout10.py",
    "docs aiohttp total=60": REPO / "docs_examples/R1/py-aiohttp-total60.py",
}
DEADLINE = 10.0  # R1 states no limit: the specification's default deadline


def load(name, path):
    spec = importlib.util.spec_from_file_location(name.replace(" ", "_").replace("=", "_").replace(".", "_"), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.get_user_profile


def check(fn, test):
    try:
        if test == "S4 trickle 0.25 s: returns by the deadline":
            with fk.FaultStub("trickle", gap_s=0.25) as s:
                fk.assert_returns_within(fk.call_with_limit(fn, s.url, "u-42", limit_s=DEADLINE + 5), DEADLINE)
        elif test == "S3 withheld response: returns by the deadline":
            with fk.FaultStub("withhold") as s:
                fk.assert_returns_within(fk.call_with_limit(fn, s.url, "u-42", limit_s=DEADLINE + 5), DEADLINE)
        elif test == "S6a Retry-After 2 s: no earlier retry":
            with fk.FaultStub("retry_after", ra_s=2) as s:
                fk.call_with_limit(fn, s.url, "u-42", limit_s=DEADLINE + 5)
                fk.assert_no_early_retry(s, 2.0)
        elif test == "S9 refused: at most 3 attempts in the first 0.5 s":
            # no packet capture here: count calls of socket.connect inside the process
            import socket as so
            times, orig = [], so.socket.connect

            def counting(self, addr):
                times.append(time.monotonic())
                return orig(self, addr)
            so.socket.connect = counting
            try:
                fk.call_with_limit(fn, fk.closed_port_url(), "u-42", limit_s=DEADLINE + 5)
            finally:
                so.socket.connect = orig
            early = [t for t in times if t - times[0] < 0.5] if times else []
            assert len(early) <= 3, f"{len(early)} connect calls in the first 0.5 s"
        return "pass", ""
    except AssertionError as e:
        return "FAIL", str(e)


def main():
    tests = ["S4 trickle 0.25 s: returns by the deadline", "S3 withheld response: returns by the deadline",
             "S6a Retry-After 2 s: no earlier retry", "S9 refused: at most 3 attempts in the first 0.5 s"]
    out = []
    for name, path in PROGRAMS.items():
        fn = load(name, path)
        for t in tests:
            v, why = check(fn, t)
            out.append({"program": name, "test": t, "verdict": v, "detail": why})
            print(f"{name:28s} {t:52s} {v} {why}", flush=True)
    (Path(__file__).parent / "selftest_result.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
