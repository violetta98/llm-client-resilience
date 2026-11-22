"""Unit tests of the Python driver (runs it in the runner image, no network)."""
import json
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IMAGE = "lcr-run-python:dev"


def run_driver(src, *, calls=1, limit=5, linger=0.5, fn="f", warm=("w",), cargs=None, observe=0):
    d = Path(tempfile.mkdtemp())
    (d / "sol").mkdir()
    (d / "sol" / "solution.py").write_text(textwrap.dedent(src))
    plan = {"nonce": "n0", "function": fn, "solution": "/solution/solution.py",
            "mode": "single" if calls == 1 else "concurrent", "warmup_args": list(warm),
            "calls": [{"args": cargs[i] if cargs else [f"c{i}"]} for i in range(calls)],
            "limit_s": limit, "linger_s": linger, "warmup_limit_s": 3, "observe_s": observe}
    (d / "plan.json").write_text(json.dumps(plan))
    t0 = time.monotonic()
    p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
                        "-v", f"{d}:/plan:ro", "-v", f"{d / 'sol'}:/solution:ro", IMAGE],
                       capture_output=True, text=True, timeout=120)
    wall = time.monotonic() - t0
    marks = {}
    for line in p.stdout.splitlines():
        assert line.startswith("@@LCR n0 "), f"non-marker on stdout: {line!r}"
        k, _, v = line[len("@@LCR n0 "):].partition(" ")
        marks[k] = json.loads(v) if k == "RESULT" else int(v)
    return marks, p.stderr, wall


class DriverTests(unittest.TestCase):
    def test_return_value_and_markers(self):
        m, err, _ = run_driver("""
            import time
            def f(x):
                print("solution output goes to stderr")
                time.sleep(0.3)
                return {"x": x}
        """)
        r = m["RESULT"]
        self.assertEqual(r["status"], "returned")
        c = r["calls"][0]
        self.assertEqual(json.loads(c["value"]["data"]), {"x": "c0"})
        self.assertAlmostEqual(c["duration_s"], 0.3, delta=0.05)
        self.assertEqual(r["warmup"]["status"], "returned")
        self.assertIn("solution output goes to stderr", err)
        self.assertTrue(m["READY"] <= m["START"] <= c["t_start"] < c["t_end"] <= m["END"] < m["EXIT"])
        self.assertGreaterEqual((m["EXIT"] - m["END"]) / 1e9, 0.5)  # linger

    def test_exception_chain(self):
        m, _, _ = run_driver("""
            class PaymentError(Exception): pass
            def f(x):
                if x == "w": return 1
                try:
                    raise TimeoutError("inner")
                except TimeoutError as e:
                    raise PaymentError("outer") from e
        """)
        c = m["RESULT"]["calls"][0]
        self.assertEqual(c["status"], "raised")
        self.assertEqual(c["error"]["type"], "solution.PaymentError")
        self.assertEqual(c["error"]["chain"]["type"], "builtins.TimeoutError")

    def test_no_return_watchdog(self):
        m, _, wall = run_driver("""
            import time
            def f(x):
                if x == "w": return 1
                time.sleep(1000)
        """, limit=2)
        r = m["RESULT"]
        self.assertEqual(r["status"], "no_return")
        self.assertEqual(r["calls"][0]["status"], "no_return")
        self.assertNotIn("END", m)
        self.assertLess(wall, 15)

    def test_signal_alarm_works_in_main_thread(self):
        m, _, _ = run_driver("""
            import signal, time
            def f(x):
                def h(*a): raise TimeoutError("alarm")
                signal.signal(signal.SIGALRM, h); signal.alarm(1)
                time.sleep(5)
        """)
        self.assertEqual(m["RESULT"]["calls"][0]["error"]["type"], "builtins.TimeoutError")

    def test_async_function_awaited(self):
        m, _, _ = run_driver("""
            import asyncio
            async def f(x):
                await asyncio.sleep(0.2)
                return x
        """)
        c = m["RESULT"]["calls"][0]
        self.assertEqual(c["status"], "returned")
        self.assertEqual(json.loads(c["value"]["data"]), "c0")

    def test_concurrent_threads(self):
        m, _, _ = run_driver("""
            import time
            def f(x):
                time.sleep(0.5); return x
        """, calls=10)
        cs = m["RESULT"]["calls"]
        self.assertEqual(len(cs), 10)
        self.assertEqual({json.loads(c["value"]["data"]) for c in cs}, {f"c{i}" for i in range(10)})
        starts = [c["t_start"] for c in cs]
        self.assertLess((max(starts) - min(starts)) / 1e9, 0.05)  # started together
        self.assertLess((m["END"] - m["START"]) / 1e9, 0.8)        # ran concurrently

    def test_concurrent_async(self):
        m, _, _ = run_driver("""
            import asyncio
            async def f(x):
                await asyncio.sleep(0.5); return x
        """, calls=10)
        cs = m["RESULT"]["calls"]
        self.assertTrue(all(c["status"] == "returned" for c in cs))
        self.assertLess((m["END"] - m["START"]) / 1e9, 0.8)

    def test_concurrent_partial_no_return(self):
        m, _, _ = run_driver("""
            import time
            def f(x):
                if x == "c3": time.sleep(1000)
                return x
        """, calls=10, limit=2)
        cs = m["RESULT"]["calls"]
        self.assertEqual(m["RESULT"]["status"], "no_return")
        self.assertEqual([c["status"] for c in cs].count("no_return"), 1)

    def test_import_error(self):
        m, _, _ = run_driver("import not_installed_pkg\ndef f(x): pass\n")
        self.assertEqual(m["RESULT"]["status"], "import_error")
        self.assertIn("ModuleNotFoundError", m["RESULT"]["import"]["error"]["type"])

    def test_warmup_no_return(self):
        m, _, _ = run_driver("""
            import time
            def f(x):
                time.sleep(1000)
        """)
        self.assertEqual(m["RESULT"]["status"], "warmup_no_return")
        self.assertNotIn("START", m)

    def test_observe_window(self):
        # S7: stay alive until observe_s after START even if the calls return at once
        m, _, _ = run_driver("def f(x): return 1\n", calls=10, observe=3)
        self.assertGreaterEqual((m["EXIT"] - m["START"]) / 1e9, 3.0)
        self.assertLess((m["EXIT"] - m["START"]) / 1e9, 3.5)

    def test_sysctls_recorded(self):
        m, _, _ = run_driver("def f(x): return 1\n")
        self.assertIn("net.ipv4.tcp_syn_retries", m["RESULT"]["env"]["sysctl"])


if __name__ == "__main__":
    unittest.main()
