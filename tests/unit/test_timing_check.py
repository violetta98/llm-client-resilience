"""Unit tests of the driver-vs-external clock agreement check."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runner"))
from orchestrator import timing_check  # noqa: E402

S = 10**9


class TimingCheck(unittest.TestCase):
    def outcome(self, **h):
        base = {"spawn": 0, "ready": 1 * S, "start": 1 * S, "process_exit": 20 * S}
        base.update(h)
        return {"host_mono_ns": base}

    def test_agree(self):
        t = timing_check({"t_start": 100 * S, "t_end": 105 * S, "limit_s": 90}, self.outcome(end=6 * S + 3 * 10**7))
        self.assertAlmostEqual(t["diff_s"], 0.03)
        self.assertFalse(t["flag_disagreement"])

    def test_disagree_flagged(self):
        t = timing_check({"t_start": 100 * S, "t_end": 105 * S, "limit_s": 90}, self.outcome(end=int(7.2 * S)))
        self.assertTrue(t["flag_disagreement"])

    def test_no_return_uses_watchdog_result(self):
        t = timing_check({"t_start": 100 * S, "t_end": None, "limit_s": 90}, self.outcome(result=91 * S + 2 * 10**8))
        self.assertIsNone(t["driver_s"])
        self.assertAlmostEqual(t["diff_s"], 0.2)

    def test_not_comparable_without_start(self):
        self.assertFalse(timing_check({"t_start": None}, self.outcome())["comparable"])
        self.assertFalse(timing_check(None, self.outcome())["comparable"])


if __name__ == "__main__":
    unittest.main()
