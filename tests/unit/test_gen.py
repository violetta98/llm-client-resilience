"""Generation harness: extraction rule, freeze guard, budget cap, no secrets in logs."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "gen"))
sys.path.insert(0, str(REPO / "analysis"))
import extract as X  # noqa: E402
import generate as G  # noqa: E402
import providers as PV  # noqa: E402


class Extract(unittest.TestCase):
    def test_last_target_block(self):
        t = "Here:\n```python\nx = 1\n```\nand better:\n```py\nx = 2\n```\n```bash\npip install x\n```\n"
        r = X.extract(t, "python")
        self.assertEqual(r["status"], "fenced")
        self.assertEqual(r["code"], "x = 2\n")
        self.assertEqual((r["n_blocks"], r["n_target_blocks"]), (3, 2))

    def test_other_language_blocks_ignored(self):
        r = X.extract("```go\npackage main\n```\n", "python")
        self.assertEqual(r["status"], "no_code")

    def test_unfenced_python_must_parse(self):
        self.assertEqual(X.extract("def f():\n    return 1\n", "python")["status"], "unfenced")
        self.assertEqual(X.extract("Sorry, I cannot help.", "python")["status"], "no_code")
        self.assertEqual(X.extract("", "go")["status"], "no_code")

    def test_unfenced_go_left_to_prepare(self):
        self.assertEqual(X.extract("package main\nfunc F() {}\n", "go")["status"], "unfenced")

    def test_nested_backticks_and_tilde(self):
        t = "~~~go\ns := \"```\"\n~~~\n"
        self.assertEqual(X.extract(t, "go")["code"], 's := "```"\n')
        t = "````typescript\nconst a = 1;\n```\nnot closed\n````\n"
        self.assertEqual(X.extract(t, "typescript")["code"], "const a = 1;\n```\nnot closed\n")


    def test_empty_target_block_is_no_code(self):
        # pilot north-mini-code-64k/P1/go/4: an empty ```go block with a garbled info string
        r = X.extract("Here:\n\n```go \u0c35\u0c30 ...\n```\n", "go")
        self.assertEqual(r["status"], "no_code")
        r = X.extract("```go\npackage a\n```\n\n```go\n\n```\n", "go")
        self.assertEqual((r["status"], r["code"]), ("fenced", "package a\n"))

class Guards(unittest.TestCase):
    @unittest.skipIf((REPO / "protocol" / "FREEZE.json").exists(), "protocol frozen (FREEZE.json exists)")
    def test_benchmark_tasks_refused_before_freeze(self):
        with self.assertRaises(SystemExit):
            G.check_tasks_allowed(["P1", "R1"])
        G.check_tasks_allowed(["P1", "P2", "P3"])

    def test_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "costs.jsonl"
            p.write_text(json.dumps({"usd": 0.9}) + "\n")
            paid = {"price_usd_per_mtok": {"input": 1.0, "output": 10.0}, "max_output_tokens_for_budget": 20000}
            free = {"price_usd_per_mtok": {"input": 0, "output": 0}}
            old = os.environ.pop("BUDGET_USD", None)
            try:
                self.assertTrue(G.Budget(p).allow(free, "x")[0])
                self.assertFalse(G.Budget(p).allow(paid, "x")[0])  # no cap set
                os.environ["BUDGET_USD"] = "1.0"
                b = G.Budget(p)
                self.assertAlmostEqual(b.spent, 0.9)
                self.assertFalse(b.allow(paid, "x")[0])  # 0.9 + 0.2 > 1.0
                os.environ["BUDGET_USD"] = "2.0"
                self.assertTrue(G.Budget(p).allow(paid, "x")[0])
            finally:
                os.environ.pop("BUDGET_USD", None)
                if old is not None:
                    os.environ["BUDGET_USD"] = old

    def test_no_secret_in_request_record(self):
        os.environ["LCR_TEST_KEY"] = "sk-test-SECRET"
        try:
            for prov in ("openai_compat", "anthropic", "gemini"):
                cfg = {"provider": prov, "model": "m", "base_url": "https://example.invalid", "api_key_env": "LCR_TEST_KEY"}
                url, h, body = PV.build_request(cfg, "hi")
                self.assertIn("sk-test-SECRET", json.dumps(h))
                self.assertNotIn("sk-test-SECRET", json.dumps(PV.request_record(url, h, body)) + url)
        finally:
            del os.environ["LCR_TEST_KEY"]

    def test_pilot_prompts_exist_and_neutral(self):
        cfg = json.loads((REPO / "gen" / "config" / "pilot.json").read_text())
        for t in cfg["tasks"]:
            for lang in cfg["langs"]:
                p = G.prompt_for(t, lang, "C0")
                self.assertTrue(p.rstrip().endswith("Respond with the complete code in a single code block."))
        checks = json.loads((REPO / "pilot" / "tasks" / "checks.json").read_text())
        self.assertEqual((checks["c0_neutral"], checks["c1_neutral"], checks["ops_lines_identical"]), ([], [], True))


if __name__ == "__main__":
    unittest.main()
