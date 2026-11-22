"""Result checks for the confirmatory tasks R6, W5, B5, H4 (tasks/CONFIRM_TASKS.md).

analysis/checkers.py is frozen with protocol v1 and raises KeyError for a task it does
not know. This module adds the four checks WITHOUT changing it: install() wraps
checkers.check so that R6/W5/B5/H4 are checked here and every other task is passed
to the original function unchanged. measures.compute() imports `check` from the
`checkers` module at call time, so the wrapper is used by every measure.

The data rules mirror mock/tasks_confirm.go (through tasks/confirm_catalog.py) and are
unit-tested in tests/unit/test_confirm_tasks.py against the same literal values as
mock/tasks_confirm_test.go.

Used by the entry points runner/run_confirm.py and tests/integration/e3_confirm.py.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tasks"))
import checkers as K  # noqa: E402
import confirm_catalog as CC  # noqa: E402

TASKS = {"R6", "W5", "B5", "H4"}


def check_confirm(task, args, call, effects, files=None):
    v = K.decode(call)
    t = task
    if t == "R6":
        return "correct" if K.contains(v, CC.r6_stock(args[1])) else "silent_failure"
    if t == "W5":
        ids = {e["key"] for e in K.eff(effects, "ticket_created", lambda e: e["detail"]["customer_id"] == args[1])}
        return "correct" if isinstance(v, dict) and v.get("customer_id") == args[1] and v.get("id") in ids \
            and v.get("status") == "open" and v.get("subject") == args[2] else "silent_failure"
    if t == "B5":
        exp = CC.b5_updates(args[1], args[2])
        return "correct" if isinstance(v, list) and len(v) == len(exp) and all(K.contains(a, b) for a, b in zip(v, exp)) \
            else "silent_failure"
    if t == "H4":
        if K.contains(v, CC.H4_REAL):
            return "correct"
        if K.contains(v, CC.H4_DEFAULT):
            return "degraded"
        return "silent_failure"
    raise KeyError(t)


_original = K.check


def check(task, args, call, effects, files=None):
    if task in TASKS:
        return check_confirm(task, args, call, effects, files)
    return _original(task, args, call, effects, files)


def install():
    """Makes checkers.check (as imported by measures.compute) know the confirmatory tasks."""
    if K.check is not check:
        K.check = check
    return K
