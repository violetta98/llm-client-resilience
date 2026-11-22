"""Offline tests of gen/batch.py with a fake HTTP function (no network)."""
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "gen"))
import batch as B  # noqa: E402

GO = "```go\npackage lcrsol\n\nfunc F() {}\n```\n"


def cfg(run):
    return {"run": run, "conditions": ["C0"], "tasks": ["P1"], "langs": ["python", "go"], "samples": 2,
            "models": [{"id": "m", "provider": "openai_compat", "model": "vendor/m", "mode": "batch",
                        "api_key_env": "X", "params": {"max_tokens": 64000}, "seed_param": "seed",
                        "price_usd_per_mtok": {"input": 1.0, "output": 5.0}, "max_output_tokens_for_budget": 64000}]}


class Batch(unittest.TestCase):
    def setUp(self):
        self.run = f"dev/unit-batch-{uuid.uuid4().hex[:8]}"
        self.c = cfg(self.run)
        self.base = REPO / "data" / self.run
        os.environ["BUDGET_USD"] = "10"
        self.sent = []

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)
        os.environ.pop("BUDGET_USD", None)

    def fake(self, results):
        def f(method, url, key, body=None):
            self.sent.append((method, url, body))
            if method == "POST":
                return 202, {"id": "batch_1", "status": "validating"}
            return 200, {"id": "batch_1", "status": "completed", "results": results,
                         "usage": {"prompt_tokens": 1, "completion_tokens": 2, "cost": 0.1}}
        return f

    def test_submit_and_collect(self):
        r = B.submit(self.c, self.c["models"][0], ["C0"], 0, False, http_fn=self.fake([]), key="k")
        self.assertEqual(r["submitted"], 4)
        body = self.sent[0][2]
        self.assertEqual(list(body)[-1], "requests")  # other fields must precede requests
        self.assertEqual(body["model"], "vendor/m")
        self.assertEqual({x["body"]["seed"] for x in body["requests"]}, {1001, 2001})
        self.assertNotIn("k", json.dumps(json.loads((self.base / "batches" / "batch_1.json").read_text())))
        # resubmit: nothing pending while submitted
        self.assertEqual(B.submit(self.c, self.c["models"][0], ["C0"], 0, False, http_fn=self.fake([]), key="k"), {"submitted": 0})
        ok = {"choices": [{"message": {"content": GO}, "finish_reason": "stop"}], "model": "vendor/m",
              "usage": {"prompt_tokens": 200, "completion_tokens": 1000}}
        res = [{"id": "i1", "custom_id": "C0_P1_go_1", "response": {"status_code": 200, "body": ok}, "error": None},
               {"id": "i2", "custom_id": "C0_P1_go_2", "response": None, "error": {"message": "boom"}},
               {"id": "i3", "custom_id": "C0_P1_python_1", "response": {"status_code": 200, "body": ok}, "error": None}]
        open_ = B.poll(self.c, False, http_fn=self.fake(res), key="k")
        self.assertEqual(open_, [])
        g = self.base / "generations" / "C0" / "m" / "P1"
        m1 = json.loads((g / "go" / "1" / "meta.json").read_text())
        self.assertEqual((m1["status"], m1["extraction"]["status"]), ("ok", "fenced"))
        self.assertAlmostEqual(m1["usd"], (200 * 1 + 1000 * 5) / 1e6)
        self.assertEqual(json.loads((g / "go" / "2" / "meta.json").read_text())["status"], "api_error")
        self.assertEqual(json.loads((g / "python" / "1" / "meta.json").read_text())["extraction"]["status"], "no_code")
        self.assertIn("missing", json.loads((g / "python" / "2" / "meta.json").read_text())["error"])
        self.assertEqual(len((self.base / "costs.jsonl").read_text().splitlines()), 2)
        # api_error samples are pending again
        self.assertEqual(B.submit(self.c, self.c["models"][0], ["C0"], 0, True, http_fn=self.fake([]), key="k")["dry"], 2)

    def test_budget_abort_and_limit(self):
        os.environ["BUDGET_USD"] = "0.5"  # worst case 4 x 64000 x 5e-6 = 1.28 USD
        with self.assertRaises(SystemExit):
            B.submit(self.c, self.c["models"][0], ["C0"], 0, False, http_fn=self.fake([]), key="k")
        self.assertEqual(self.sent, [])
        r = B.submit(self.c, self.c["models"][0], ["C0"], 1, False, http_fn=self.fake([]), key="k")
        self.assertEqual(r["submitted"], 1)
        # the outstanding batch (worst case 0.32) counts against the cap: a second one is refused
        with self.assertRaises(SystemExit):
            B.submit(self.c, self.c["models"][0], ["C0"], 1, False, http_fn=self.fake([]), key="k")
        self.assertEqual(B.project(self.c)["_total"]["outstanding_worst_usd"], 0.32)

    def test_benchmark_refused_before_freeze(self):
        c = dict(self.c, tasks=["R1"])
        if not (REPO / "protocol" / "FREEZE.json").exists():
            with self.assertRaises(SystemExit):
                B.submit(c, c["models"][0], ["C0"], 0, True, http_fn=self.fake([]), key="k")


if __name__ == "__main__":
    unittest.main()
