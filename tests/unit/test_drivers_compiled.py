"""Unit tests of the TypeScript, Java and Go drivers (prepare + run in the
runner images, no network). Mirrors tests/unit/test_driver_python.py."""
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runner"))
from orchestrator import ENTRY, ENTRYPOINT, RUNNER_IMAGES  # noqa: E402
from prepare import prepare  # noqa: E402

FN = {"typescript": "f", "java": "f", "go": "F"}
TASK = {"go": {"function": "F"}}

SRC = {
    "typescript": {
        "ret": 'export async function f(x: string) { console.log("to stderr"); await new Promise((r) => setTimeout(r, 300)); return { x }; }',
        "raise": 'class PaymentError extends Error {}\nexport async function f(x: string) { if (x === "w") return 1; throw new PaymentError("outer", { cause: new Error("inner") }); }',
        "hang": 'export async function f(x: string) { if (x === "w") return 1; await new Promise(() => {}); }',
        "conc": 'export async function f(x: string) { await new Promise((r) => setTimeout(r, 500)); return x; }',
        "fast": 'export function f(x: string) { return x; }',
        "bg_reject": 'export async function f(x: string) { Promise.reject(new Error("background")); return x; }',
    },
    "java": {
        "ret": 'public class Sol { public static java.util.Map<String,String> f(String x) throws Exception { System.out.println("to stderr"); Thread.sleep(300); return java.util.Map.of("x", x); } }',
        "raise": 'public class Sol { static class PaymentError extends RuntimeException { PaymentError(String m, Throwable c) { super(m, c); } }\n public static Object f(String x) { if (x.equals("w")) return 1; throw new PaymentError("outer", new java.io.IOException("inner")); } }',
        "hang": 'public class Sol { public static Object f(String x) throws Exception { if (x.equals("w")) return 1; Thread.sleep(1000000); return null; } }',
        "conc": 'public class Sol { public static String f(String x) throws Exception { Thread.sleep(500); return x; } }',
        "fast": 'public class Sol { public static java.util.concurrent.CompletableFuture<String> f(String x) { return java.util.concurrent.CompletableFuture.completedFuture(x); } }',
    },
    "go": {
        "ret": 'package main\nimport ("fmt"; "time")\nfunc F(x string) (map[string]string, error) { fmt.Println("to stderr"); time.Sleep(300 * time.Millisecond); return map[string]string{"x": x}, nil }',
        "raise": 'package main\nimport ("errors"; "fmt")\nfunc F(x string) (any, error) { if x == "w" { return 1, nil }; return nil, fmt.Errorf("outer: %w", errors.New("inner")) }',
        "hang": 'package main\nimport "time"\nfunc F(x string) (any, error) { if x == "w" { return 1, nil }; time.Sleep(time.Hour); return nil, nil }',
        "conc": 'package main\nimport "time"\nfunc F(x string) (string, error) { time.Sleep(500 * time.Millisecond); return x, nil }',
        "fast": 'package main\nfunc F(x string) (string, error) { return x, nil }',
        "panic": 'package main\nfunc F(x string) (string, error) { if x == "w" { return x, nil }; panic("boom") }',
    },
}
EXT = {"typescript": "ts", "java": "java", "go": "go"}
_prepared = {}


def prepared(lang, key):
    if (lang, key) not in _prepared:
        tmp = Path(tempfile.mkdtemp(prefix="lcr-ut-"))
        src = tmp / f"s.{EXT[lang]}"
        src.write_text(textwrap.dedent(SRC[lang][key]))
        info = prepare(lang, src, tmp / "out", task=TASK)
        assert info["category"] == "ok", info
        _prepared[(lang, key)] = tmp / "out"
    return _prepared[(lang, key)]


def run(lang, key, calls=1, limit=5, linger=0.5, observe=0):
    d = prepared(lang, key)
    plan_dir = Path(tempfile.mkdtemp(prefix="lcr-plan-"))
    plan = {"nonce": "n0", "function": FN[lang], "solution": ENTRY[lang], "mode": "single" if calls == 1 else "concurrent",
            "warmup_args": ["w"], "calls": [{"args": [f"c{i}"]} for i in range(calls)],
            "limit_s": limit, "linger_s": linger, "warmup_limit_s": 30, "observe_s": observe}
    (plan_dir / "plan.json").write_text(json.dumps(plan))
    plan_dir.chmod(0o755)
    (plan_dir / "plan.json").chmod(0o644)
    ep = ["--entrypoint", ENTRYPOINT[lang]] if lang in ENTRYPOINT else []
    t0 = time.monotonic()
    p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp", "--user", "65534:65534",
                        "-v", f"{plan_dir}:/plan:ro", "-v", f"{d}:/solution:ro", *ep, RUNNER_IMAGES[lang]],
                       capture_output=True, text=True, timeout=180)
    wall = time.monotonic() - t0
    shutil.rmtree(plan_dir, ignore_errors=True)
    marks = {}
    for line in p.stdout.splitlines():
        assert line.startswith("@@LCR n0 "), f"non-marker on stdout: {line!r}"
        k, _, v = line[len("@@LCR n0 "):].partition(" ")
        if k in ("RESULT", "EVENT"):
            marks.setdefault(k, json.loads(v)) if k == "RESULT" else marks.setdefault("EVENTS", []).append(json.loads(v))
        else:
            marks[k] = int(v)
    return marks, p.stderr, wall


def chain_types(e):
    out = []
    while e:
        out.append(e["type"])
        e = e.get("chain")
    return out


class CompiledDrivers(unittest.TestCase):
    def for_langs(self, fn, langs=("typescript", "java", "go")):
        for lang in langs:
            with self.subTest(lang=lang):
                fn(lang)

    def test_return_value_and_markers(self):
        def t(lang):
            m, err, _ = run(lang, "ret")
            r = m["RESULT"]
            self.assertEqual(r["status"], "returned", r)
            c = r["calls"][0]
            self.assertEqual(json.loads(c["value"]["data"]), {"x": "c0"})
            self.assertAlmostEqual(c["duration_s"], 0.3, delta=0.08)
            self.assertIn("to stderr", err)
            self.assertTrue(m["READY"] <= m["START"] <= c["t_start"] < c["t_end"] <= m["END"] < m["EXIT"])
            self.assertGreaterEqual((m["EXIT"] - m["END"]) / 1e9, 0.5)
        self.for_langs(t)

    def test_exception_chain(self):
        want = {"typescript": ["PaymentError", "Error"], "java": ["Sol$PaymentError", "java.io.IOException"],
                "go": ["*fmt.wrapError", "*errors.errorString"]}

        def t(lang):
            c = run(lang, "raise")[0]["RESULT"]["calls"][0]
            self.assertEqual(c["status"], "raised")
            self.assertEqual(chain_types(c["error"])[:2], want[lang])
        self.for_langs(t)

    def test_no_return_watchdog(self):
        def t(lang):
            m, _, wall = run(lang, "hang", limit=2)
            self.assertEqual(m["RESULT"]["status"], "no_return")
            self.assertEqual(m["RESULT"]["calls"][0]["status"], "no_return")
            self.assertNotIn("END", m)
            self.assertLess(wall, 40)
        self.for_langs(t)

    def test_concurrent(self):
        def t(lang):
            m, _, _ = run(lang, "conc", calls=10)
            cs = m["RESULT"]["calls"]
            self.assertEqual({json.loads(c["value"]["data"]) for c in cs}, {f"c{i}" for i in range(10)})
            starts = [c["t_start"] for c in cs]
            self.assertLess((max(starts) - min(starts)) / 1e9, 0.05)
            self.assertLess((m["END"] - m["START"]) / 1e9, 0.9)
        self.for_langs(t)

    def test_observe_window(self):
        def t(lang):
            m, _, _ = run(lang, "fast", calls=10, observe=3)
            self.assertEqual(m["RESULT"]["status"], "returned")
            self.assertGreaterEqual((m["EXIT"] - m["START"]) / 1e9, 3.0)
            self.assertLess((m["EXIT"] - m["START"]) / 1e9, 3.6)
        self.for_langs(t)

    def test_go_panic_is_recorded(self):
        c = run("go", "panic")[0]["RESULT"]["calls"][0]
        self.assertEqual(c["status"], "raised")
        self.assertTrue(c["error"]["panic"])

    def test_ts_background_rejection_does_not_kill_driver(self):
        m, _, _ = run("typescript", "bg_reject", linger=1)
        self.assertEqual(m["RESULT"]["status"], "returned")
        self.assertIn("EXIT", m)


if __name__ == "__main__":
    unittest.main()
