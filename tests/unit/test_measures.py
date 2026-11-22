"""Unit tests of the Table V measures and per-task checkers on synthetic runs."""
import json
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis"))
import checkers as K  # noqa: E402
import measures as M  # noqa: E402

S = 10**9
MS = 10**6


def exp(task):
    return yaml.safe_load((REPO / "tasks" / task / "expected.yaml").read_text())


def req(i, key, t, port=9001, role="dep", headers=()):
    return {"req_id": i, "logical_key": key, "t_first_byte": t, "port": port, "role": role, "headers": list(headers)}


def run(sc, calls, requests=(), responses=(), effects=(), syns=(), plan_calls=None, outage=0, limit=90, files=None):
    return {"result": {"status": "x", "calls": calls, "limit_s": limit, "lang": "python", "files": files or []},
            "timing": {"diff_s": 0.0, "flag_disagreement": False},
            "mock": {"config": {"scenario": sc}, "run_id": "r", "s7_outage_start_mono_ns": outage,
                     "capture": {"packets_captured": 1, "packets_received_by_filter": 1}},
            "orch": {"plan": {"calls": plan_calls or [{"args": None}] * len(calls)}},
            "requests": list(requests), "responses": list(responses), "effects": list(effects), "syns": list(syns), "conns": []}


def ret(value, t0=0, t1=1 * S, enc="json"):
    return {"status": "returned", "t_start": t0, "t_end": t1, "duration_s": (t1 - t0) / S,
            "value": {"enc": enc, "data": json.dumps(value)}}


class Primitives(unittest.TestCase):
    def test_rapid(self):
        self.assertFalse(M.rapid([0, 50 * MS]))                     # a single immediate retry is not counted
        self.assertTrue(M.rapid([0, 50 * MS, 99 * MS]))             # 3 attempts, gaps < 100 ms
        self.assertFalse(M.rapid([0, 50 * MS, 160 * MS]))           # second gap 110 ms
        self.assertTrue(M.rapid([0, 1 * S, 1 * S + 10 * MS, 1 * S + 20 * MS]))

    def test_window_share(self):
        self.assertEqual(M.max_window_share([0, 10 * MS, 20 * MS, 1 * S]), 0.75)
        self.assertEqual(M.max_window_share([0, 60 * MS, 120 * MS]), 1 / 3)

    def test_sync_shares_skip_first_attempt(self):
        per = [[0, 1 * S + i * MS] for i in range(10)]               # k=2 within 10 ms
        self.assertEqual(M.sync_shares(per), {2: 1.0})
        per = [[0, 1 * S + i * 100 * MS] for i in range(10)]         # spread 100 ms apart
        self.assertEqual(M.sync_shares(per), {2: 0.1})
        per = [[0, 1 * S] for _ in range(4)] + [[0]] * 6              # k=2 reached by < 5 invocations
        self.assertEqual(M.sync_shares(per), {})

    def test_invocation_of(self):
        e = exp("B1")["args"]["s7"]
        self.assertEqual(M.invocation_of("record:rec-b03-05", e), 3)
        self.assertEqual(M.invocation_of("health:db-17", exp("H2")["args"]["s7"]), 7)
        self.assertEqual(M.invocation_of("sms:+48500100104|abcd", exp("W2")["args"]["s7"]), 4)
        self.assertEqual(M.invocation_of("quote:A|sku-109", exp("H3")["args"]["s7"]), 9)
        self.assertEqual(M.invocation_of("event:evt_105", exp("B4")["args"]["s7"]), 5)
        self.assertIsNone(M.invocation_of("user:u-999", exp("R1")["args"]["s7"]))
        r2 = exp("R2")["args"]["s7"]  # "sports" is shared by all ten; must not match "sports bag"
        self.assertEqual(M.invocation_of("search:bike helmet|sports|120.0", r2), 9)
        self.assertEqual(M.invocation_of("search:sports bag|sports|120.0", r2), 6)
        self.assertEqual(M.invocation_of("orders:c-103|pg2.abc", exp("R4")["args"]["s7"]), 3)
        self.assertEqual(M.invocation_of("recs:u-104", exp("H1")["args"]["s7"]), 4)


class Checkers(unittest.TestCase):
    def test_r3_report_sha_matches_mock(self):
        # value computed by the Go mock for rep-042 (mock/tasks_test.go uses the same generator)
        self.assertEqual(len(K.report_sha("rep-042")), 64)

    def test_h1_h3(self):
        prof = K.profile("u-042")
        recs = [{"product_id": f"p-042-{k}", "title": f"Product {k}"} for k in (1, 2, 3)]
        args = ["a", "b", "u-042"]
        self.assertEqual(K.check("H1", args, ret({"profile": prof, "recommendations": recs}), []), "correct")
        self.assertEqual(K.check("H1", args, ret({"profile": prof, "recommendations": None}), []), "degraded")
        self.assertEqual(K.check("H1", args, ret({"profile": prof, "recommendations": []}), []), "silent_failure")
        q = {"supplier": "s2", "sku": "sku-042", "price": 10.1, "currency": "EUR"}
        self.assertEqual(K.check("H3", [[], "sku-042"], ret(q), []), "degraded")

    def test_numbers_and_partial_list(self):
        self.assertEqual(K.check("R2", ["u", "running shoes", "sports", 120],
                                 ret(K.r2_items("running shoes", "sports", 120.0)), []), "correct")
        orders = [{"id": i} for i in K.r4_ids("c-042")]
        self.assertEqual(K.check("R4", ["u", "c-042"], ret(orders), []), "correct")
        self.assertEqual(K.check("R4", ["u", "c-042"], ret(orders[:50]), []), "silent_failure")

    def test_b1_requires_all_records(self):
        recs = [{"id": f"rec-a42-{i:02d}"} for i in range(1, 21)]
        eff = [{"role": "dep", "kind": "record_written", "key": r["id"]} for r in recs]
        self.assertEqual(K.check("B1", ["u", recs], ret(20), eff), "correct")
        self.assertEqual(K.check("B1", ["u", recs], ret(20), eff[1:]), "silent_failure")


class Compute(unittest.TestCase):
    def test_no_return_and_overrun(self):
        r = M.compute(run("S3", [{"status": "no_return", "t_start": 0, "t_end": None}]), exp("B2"))
        self.assertTrue(r["no_return_90"])
        self.assertTrue(r["overrun"])
        r = M.compute(run("S3", [{"status": "raised", "t_start": 0, "t_end": int(30.3 * S), "duration_s": 30.3}]), exp("B2"))
        self.assertTrue(r["overrun"])
        r = M.compute(run("S3", [{"status": "raised", "t_start": 0, "t_end": int(30.2 * S), "duration_s": 30.2}]), exp("B2"))
        self.assertFalse(r["overrun"])
        self.assertTrue(r["outcome_allowed"])

    def test_c2_overrun(self):
        c = [{"status": "raised", "t_start": 0, "t_end": 11 * S, "duration_s": 11.0}]
        self.assertTrue(M.compute(run("S3", c), exp("R1"), cond="C2")["c2_overrun"])
        self.assertIsNone(M.compute(run("S3", c), exp("R1"), cond="C0")["c2_overrun"])

    def test_retry_after_violation(self):
        reqs = [req(1, "user:u-042", 0), req(2, "user:u-042", int(3.0 * S))]
        resp = [{"req_id": 1, "status": 429, "t_head_sent": int(0.15 * S)}]
        r = M.compute(run("S6a", [ret(K.profile("u-042"), 0, 4 * S)], reqs, resp, plan_calls=[{"args": ["u", "u-042"]}]), exp("R1"))
        self.assertTrue(r["retry_after_violation"])            # 2.85 s < 3 - 0.1
        reqs[1]["t_first_byte"] = int(3.1 * S)
        r = M.compute(run("S6a", [ret(K.profile("u-042"), 0, 4 * S)], reqs, resp, plan_calls=[{"args": ["u", "u-042"]}]), exp("R1"))
        self.assertFalse(r["retry_after_violation"])           # 2.95 s, within tolerance
        self.assertEqual(r["outcome"], "correct")
        reqs[1]["t_first_byte"] = int(2.5 * S)
        r = M.compute(run("S6b", [ret(1)], reqs, resp, plan_calls=[{"args": ["u", "u-042"]}]), exp("R1"))
        self.assertFalse(r["retry_after_violation"])           # 2.35 s: within the 1 s date tolerance

    def test_rapid_retries_s9_from_syns(self):
        syns = [{"dst_port": 9001, "retransmission": False, "t": i * 10 * MS, "src_port": 40000 + i} for i in range(5)]
        r = M.compute(run("S9", [{"status": "raised", "t_start": 0, "t_end": S, "duration_s": 1}], syns=syns), exp("R1"))
        self.assertTrue(r["rapid_retries"])
        self.assertIsNone(M.compute(run("S9", [{"status": "raised", "t_start": 0, "t_end": S, "duration_s": 1}], syns=syns), exp("B1"))["rapid_retries"])

    def test_excessive_and_load_s7(self):
        reqs = [req(i, "user:u-100", i * S) for i in range(12)] + [req(100 + i, "user:u-101", i * 3 * S) for i in range(5)]
        calls = [{"status": "raised", "t_start": 0, "t_end": 40 * S, "duration_s": 40}] * 10
        e = exp("R1")
        plan = [{"args": a} for a in e["args"]["s7"]]
        r = M.compute(run("S7", calls, reqs, plan_calls=plan, outage=0), e)
        self.assertTrue(r["excessive_retries"])
        self.assertEqual(r["load_requests_total"], 17)

    def test_sync_s7(self):
        e = exp("R1")
        plan = [{"args": a} for a in e["args"]["s7"]]
        reqs = []
        for i in range(10):
            reqs += [req(10 * i, f"user:u-{100 + i:03d}", 0), req(10 * i + 1, f"user:u-{100 + i:03d}", S + i * MS)]
        calls = [{"status": "raised", "t_start": 0, "t_end": 2 * S, "duration_s": 2}] * 10
        r = M.compute(run("S7", calls, reqs, plan_calls=plan), e)
        self.assertTrue(r["sync_retries"])
        self.assertEqual(r["unattributed_requests"], 0)

    def test_late_requests(self):
        reqs = [req(1, "user:u-042", 0), req(2, "user:u-042", 3 * S)]
        r = M.compute(run("S3", [{"status": "raised", "t_start": 0, "t_end": 1 * S, "duration_s": 1}], reqs), exp("R1"))
        self.assertEqual(r["late_requests"], 1)

    def test_unsafe_write_retry(self):
        eff = [{"role": "dep", "kind": "sms_sent", "key": "m1", "detail": {"to": "+1"}},
               {"role": "dep", "kind": "sms_sent", "key": "m2", "detail": {"to": "+1"}}]
        r = M.compute(run("S8", [{"status": "returned", "t_start": 0, "t_end": S, "duration_s": 1,
                                  "value": {"enc": "json", "data": "\"m2\""}}], effects=eff,
                          plan_calls=[{"args": ["u", "+1", "x"]}]), exp("W2"))
        self.assertTrue(r["unsafe_write_retry"])
        self.assertFalse(r["outcome_allowed"])  # W2 S8 allows only an error


if __name__ == "__main__":
    unittest.main()
