"""Unit tests of the confirmatory tasks R6, W5, B5, H4 (tasks/CONFIRM_TASKS.md): generated
task files, result checks (analysis/checkers_confirm.py, same literal values as
mock/tasks_confirm_test.go) and the measures on synthetic runs. No container is started."""
import json
import re
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "tasks"))
import checkers_confirm as KC  # noqa: E402
import checkers as K  # noqa: E402
import measures as M  # noqa: E402
import catalog as C  # noqa: E402
import confirm_catalog as CC  # noqa: E402

KC.install()
NEW = ["R6", "W5", "B5", "H4"]
S = 10**9


def ret(value):
    return {"status": "returned", "t_start": 0, "t_end": S, "duration_s": 1.0, "value": {"enc": "json", "data": json.dumps(value)}}


def sig(t):
    return json.loads((REPO / "tasks" / t / "signature.json").read_text())


def exp(t):
    return yaml.safe_load((REPO / "tasks" / t / "expected.yaml").read_text())


class Files(unittest.TestCase):
    def test_prompts_use_the_frozen_template_lines(self):
        for t in NEW:
            for lang in C.LANGS:
                for cond in ("C0", "C1", "C2"):
                    p = (REPO / "tasks" / t / "prompts" / lang / f"{cond}.txt").read_text()
                    self.assertIn("\n  " + C.OPS[0] + "\n  " + C.OPS[1] + "\n", p)
                    self.assertIn("\nAvailable: " + C.AVAILABLE[lang] + "\n", p)
                    self.assertTrue(p.rstrip().endswith(C.FINAL))
                    self.assertEqual(cond == "C2", C.C2_TEXT in p)
                    self.assertEqual(cond == "C1", C.C1_TEXT in p)
                    self.assertTrue(p.startswith(C.OPENER[lang].split("{")[0]))

    def test_checks_file(self):
        ch = json.loads((REPO / "tasks" / "confirm_checks.json").read_text())
        self.assertEqual(ch, {"ops_lines_identical": True, "c0_neutral": [], "c1_neutral": [], "prompt_counts": 48})

    def test_one_new_task_per_group_with_the_group_conventions(self):
        groups = {exp(t)["group"]: t for t in NEW}
        self.assertEqual(sorted(groups), ["background", "handler", "read", "write"])
        self.assertIsNone(exp("R6")["time_limit_s"])
        self.assertIsNone(exp("W5")["time_limit_s"])
        self.assertEqual(exp("B5")["time_limit_s"], 30)
        self.assertEqual(exp("H4")["time_limit_s"], 2)
        self.assertEqual(exp("B5")["allowed_outcomes"]["S7"], ["error"])
        self.assertEqual(exp("H4")["allowed_outcomes"]["S7"], ["degraded"])
        self.assertEqual(exp("W5")["allowed_outcomes"]["S8"], ["correct", "error"])
        self.assertEqual(exp("W5")["unsafe_effect"], "ticket_created")
        self.assertIn("Idempotency-Key header", (REPO / "tasks" / "W5" / "prompts" / "python" / "C0.txt").read_text())
        self.assertEqual(exp("W5")["scenarios"], exp("W1")["scenarios"])
        for t in ("R6", "B5", "H4"):
            self.assertEqual(exp(t)["scenarios"], exp("R1")["scenarios"])

    def test_s7_invocations_are_attributable(self):
        keys = {"R6": "stock:{1}", "W5": "ticket:{1}", "B5": "updates:{1}|{2}", "H4": "prefs:{1}"}
        for t in NEW:
            s7 = sig(t)["s7_args"]
            for i, a in enumerate(s7):
                self.assertEqual(M.invocation_of(keys[t].format(*a), s7), i, t)

    def test_reference_index(self):
        for lang in C.LANGS:
            idx = json.loads((REPO / "references" / f"index-confirm-{lang}.json").read_text())
            self.assertEqual(len(idx), 21)
            for p in idx:
                self.assertTrue((REPO / p["path"]).exists(), p)
            self.assertEqual({p["task"] for p in idx if p["variant"] == "UNSAFE_POST_RETRY"}, {"W5"})


class Checks(unittest.TestCase):
    def test_r6(self):
        v = CC.r6_stock("prd-042")
        self.assertEqual((v["warehouses"][0]["available"], v["warehouses"][0]["reserved"]), (655, 49))
        self.assertEqual((v["warehouses"][23]["available"], v["warehouses"][23]["reserved"]), (978, 10))
        a = ["{A}", "prd-042"]
        self.assertEqual(K.check("R6", a, ret(v), []), "correct")
        bad = json.loads(json.dumps(v))
        bad["warehouses"] = bad["warehouses"][:23]
        self.assertEqual(K.check("R6", a, ret(bad), []), "silent_failure")
        self.assertEqual(K.check("R6", a, ret({}), []), "silent_failure")
        self.assertEqual(K.check("R6", a, ret(None), []), "silent_failure")

    def test_w5(self):
        a = ["{A}", "cus-042", "Invoice shows the wrong address", "msg"]
        eff = [{"role": "dep", "kind": "ticket_created", "key": "tkt_000001", "detail": {"customer_id": "cus-042"}},
               {"role": "warmup", "kind": "ticket_created", "key": "tkt_w000001", "detail": {"customer_id": "cus-000"}}]
        good = {"id": "tkt_000001", "customer_id": "cus-042", "subject": a[2], "status": "open", "created_at": "2026-03-01T12:00:00Z"}
        self.assertEqual(K.check("W5", a, ret(good), eff), "correct")
        self.assertEqual(K.check("W5", a, ret({**good, "id": "tkt_w000001"}), eff), "silent_failure")
        self.assertEqual(K.check("W5", a, ret({**good, "id": "tkt_000002"}), eff), "silent_failure")
        self.assertEqual(K.check("W5", a, ret("tkt_000001"), eff), "silent_failure")

    def test_b5(self):
        ups = CC.b5_updates("car-042")
        self.assertEqual(len(ups), 25)
        self.assertEqual(ups[0], {"shipment_id": "shp-042-001", "status": "delivered", "updated_at": "2026-03-01T00:17:00Z"})
        self.assertEqual(ups[-1]["updated_at"], "2026-03-01T07:05:00Z")
        self.assertEqual(ups[-1]["status"], "out_for_delivery")
        self.assertEqual(CC.b5_updates("car-042", "2026-03-01T07:05:00Z"), [])
        a = ["{A}", "car-042", CC.CONFIRM_SINCE]
        self.assertEqual(K.check("B5", a, ret(ups), []), "correct")
        self.assertEqual(K.check("B5", a, ret(ups[:-1]), []), "silent_failure")
        self.assertEqual(K.check("B5", a, ret({"updates": ups}), []), "silent_failure")
        self.assertEqual(K.check("B5", a, ret([]), []), "silent_failure")

    def test_h4(self):
        a = ["{A}", "u-042"]
        self.assertEqual(K.check("H4", a, ret({"email": False, "sms": True, "push": True}), []), "correct")
        self.assertEqual(K.check("H4", a, ret({"user_id": "u-042", "email": False, "sms": True, "push": True,
                                                "updated_at": "2026-02-20T08:00:00Z"}), []), "correct")
        self.assertEqual(K.check("H4", a, ret({"email": True, "sms": False, "push": False}), []), "degraded")
        self.assertEqual(K.check("H4", a, ret({"email": True, "sms": True, "push": True}), []), "silent_failure")
        self.assertEqual(K.check("H4", a, ret(None), []), "silent_failure")

    def test_other_tasks_unchanged(self):
        self.assertEqual(K.check("R5", ["{A}", "x"], ret(True), []), "correct")
        with self.assertRaises(KeyError):
            K.check("Z9", [], ret(1), [])


class Measures(unittest.TestCase):
    def _run(self, sc, calls, effects=(), requests=(), plan=None):
        return {"result": {"status": "x", "calls": calls, "limit_s": 90, "lang": "python", "files": []},
                "timing": {"diff_s": 0.0, "flag_disagreement": False},
                "mock": {"config": {"scenario": sc}, "run_id": "r", "s7_outage_start_mono_ns": 0,
                         "capture": {"packets_captured": 1, "packets_received_by_filter": 1}},
                "orch": {"plan": {"calls": plan or [{"args": sig("W5")["single_args"]}]}},
                "requests": list(requests), "responses": [], "effects": list(effects), "syns": [], "conns": []}

    def test_w5_s8_unsafe_retry(self):
        e1 = {"role": "dep", "kind": "ticket_created", "key": "tkt_000001", "detail": {"customer_id": "cus-042"}}
        e2 = {"role": "dep", "kind": "ticket_created", "key": "tkt_000002", "detail": {"customer_id": "cus-042"}}
        rep = {"role": "dep", "kind": "ticket_replayed", "key": "k"}
        good = {"id": "tkt_000001", "customer_id": "cus-042", "subject": sig("W5")["single_args"][2], "status": "open"}
        row = M.compute(self._run("S8", [ret(good)], [e1, rep]), exp("W5"))
        self.assertFalse(row["unsafe_write_retry"])
        self.assertTrue(row["outcome_allowed"])
        row = M.compute(self._run("S8", [ret({**good, "id": "tkt_000002"})], [e1, e2]), exp("W5"))
        self.assertTrue(row["unsafe_write_retry"])

    def test_h4_s7_requires_degraded(self):
        plan = [{"args": a} for a in sig("H4")["s7_args"]]
        row = M.compute(self._run("S7", [ret(CC.H4_DEFAULT)] * 10, plan=plan), exp("H4"))
        self.assertTrue(row["outcome_allowed"])
        row = M.compute(self._run("S7", [ret(CC.H4_REAL)] + [ret(CC.H4_DEFAULT)] * 9, plan=plan), exp("H4"))
        self.assertFalse(row["outcome_allowed"])


if __name__ == "__main__":
    unittest.main()
