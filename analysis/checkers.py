"""Per-task check of a returned value against the approved specification
(tasks/<ID>/spec.md). Mirrors the mock's data rules (mock/task_r1.go,
mock/tasks_all.go); unit-tested against the mock's own outputs in
tests/unit/test_checkers.py.

check(task, args, call, effects) -> "correct" | "degraded" | "silent_failure"
for a call that returned (raised / no_return are classified by measures.py).
"""
import hashlib
import math
import ast
import json
import re

ABS = 1e-6


_DECIMAL = re.compile(r"Decimal\('(-?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)'\)")


def decode(call):
    v = call.get("value") or {}
    data = v.get("data")
    if v.get("enc") == "json":
        try:
            return json.loads(data)
        except (TypeError, ValueError):
            return data
    if v.get("enc") == "repr" and v.get("type") == "builtins.dict" and isinstance(data, str) and "Decimal(" in data:
        # D59: a Python dict with decimal.Decimal values is not JSON-serializable, so the harness stored its repr.
        # Read the Decimal values as numbers; any other non-literal value (e.g. a datetime) keeps the string.
        try:
            return ast.literal_eval(_DECIMAL.sub(r"\1", data))
        except (ValueError, SyntaxError):
            return data
    return data


def num_eq(a, b):
    try:
        return abs(float(a) - float(b)) < ABS
    except (TypeError, ValueError):
        return False


def jeq(a, b):
    """JSON equality with numeric tolerance (Java/Go/TS encode numbers differently)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return num_eq(a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(jeq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(jeq(x, y) for x, y in zip(a, b))
    return a == b


def contains(a, b):
    """a contains every key of b with an equal value (extra keys allowed)."""
    return isinstance(a, dict) and all(k in a and jeq(a[k], v) for k, v in b.items())


def profile(uid):
    n = uid[2:]
    return {"id": uid, "name": f"User {n}", "email": f"user{n}@example.com", "created_at": "2024-01-15T09:30:00Z"}


def r2_items(q, cat, mp):
    h = hashlib.sha1(f"{q}|{cat}".encode()).hexdigest()[:6]
    tq = " ".join(w[:1].upper() + w[1:] for w in q.split())
    return [{"id": f"p-{h}-{k + 1}", "name": f"{tq} {k + 1}", "category": cat, "price": round(mp * f, 2)}
            for k, f in enumerate([0.5, 0.7, 0.9])]


def report_sha(rid):
    out = b""
    i = 0
    while len(out) < 65536:
        out += hashlib.sha256(f"{rid}:{i}".encode()).digest()
        i += 1
    return hashlib.sha256(out[:65536]).hexdigest()


def r4_ids(cust):
    n = cust[2:]
    return [f"o-{n}-{i:03d}" for i in range(1, 121)]


def eff(effects, kind, pred=lambda e: True):
    return [e for e in effects if e.get("role") == "dep" and e["kind"] == kind and pred(e)]


def check(task, args, call, effects, files=None):
    v = decode(call)
    t = task
    if t == "R1":
        return "correct" if contains(v, profile(args[1])) else "silent_failure"
    if t == "R2":
        exp = r2_items(args[1], args[2], float(args[3]))
        return "correct" if isinstance(v, list) and len(v) == 3 and all(contains(a, b) for a, b in zip(v, exp)) else "silent_failure"
    if t == "R3":
        f = next((x for x in (files or []) if x.get("path") == args[2]), None)
        ok_file = bool(f and f.get("exists") and f.get("size") == 65536 and f.get("sha256") == report_sha(args[1]))
        return "correct" if num_eq(v, 65536) and ok_file else "silent_failure"
    if t == "R4":
        ids = [o.get("id") for o in v] if isinstance(v, list) and all(isinstance(o, dict) for o in v) else None
        return "correct" if ids == r4_ids(args[1]) else "silent_failure"
    if t in ("R5", "H2"):
        return "correct" if v is True else ("degraded" if v is False else "silent_failure")
    if t == "W1":
        ids = {e["key"] for e in eff(effects, "payment_created", lambda e: e["detail"]["order_id"] == args[1])}
        return "correct" if isinstance(v, dict) and v.get("order_id") == args[1] and v.get("id") in ids \
            and v.get("status") == "succeeded" else "silent_failure"
    if t == "W2":
        ids = {e["key"] for e in eff(effects, "sms_sent", lambda e: e["detail"]["to"] == args[1])}
        return "correct" if v in ids else "silent_failure"
    if t == "W3":
        body = args[2].encode()
        h = hashlib.sha256(body).hexdigest()
        stored = eff(effects, "document_written", lambda e: e["key"] == args[1])
        ok_store = bool(stored) and stored[-1]["detail"]["sha256"] == h
        return "correct" if contains(v, {"id": args[1], "size": len(body), "sha256": h}) and ok_store else "silent_failure"
    if t == "W4":
        return "correct" if eff(effects, "subscription_canceled", lambda e: e["key"] == args[1]) else "silent_failure"
    if t == "B1":
        want = {r["id"] for r in args[1]}
        got = {e["key"] for e in eff(effects, "record_written", lambda e: e["key"] in want)}
        return "correct" if num_eq(v, len(want)) and got == want else "silent_failure"
    if t == "B2":
        return "correct" if v == f"https://files.example.com/exports/{args[1]}.csv" else "silent_failure"
    if t == "B3":
        return "correct" if contains(v, {"account_id": args[4], "balance": "1250.00", "currency": "EUR"}) else "silent_failure"
    if t == "B4":
        return "correct" if eff(effects, "delivery_accepted", lambda e: e["key"] == args[1]["id"]) else "silent_failure"
    if t == "H1":
        uid = args[2]
        recs = [{"product_id": f"p-{uid[2:]}-{k}", "title": f"Product {k}"} for k in (1, 2, 3)]
        if not isinstance(v, dict) or not contains(v.get("profile"), profile(uid)):
            return "silent_failure"
        r = v.get("recommendations", "missing")
        if r is None:
            return "degraded"
        if isinstance(r, dict) and "items" in r:  # the response object instead of the items: accepted
            r = r["items"]
        return "correct" if isinstance(r, list) and len(r) == 3 and all(contains(a, b) for a, b in zip(r, recs)) else "silent_failure"
    if t == "H3":
        sku = args[1]
        if contains(v, {"supplier": "s1", "sku": sku, "price": 9.40}):
            return "correct"
        if contains(v, {"supplier": "s2", "sku": sku, "price": 10.10}):
            return "degraded"
        return "silent_failure"
    # ---- pilot tasks (pilot/tasks/<ID>/spec.md; outside the benchmark)
    if t == "P1":
        return "correct" if contains(v, {"base": args[1], "quote": args[2], "rate": p1_rate(args[1], args[2])}) else "silent_failure"
    if t == "P2":
        ids = {e["key"] for e in eff(effects, "comment_created", lambda e: e["detail"]["ticket_id"] == args[1])}
        return "correct" if v in ids else "silent_failure"
    if t == "P3":
        return "correct" if num_eq(v, 2) and not isinstance(v, bool) else ("degraded" if num_eq(v, 5) and not isinstance(v, bool) else "silent_failure")
    raise KeyError(t)


def p1_rate(base, quote):
    if base == quote:
        return 1.0
    x = (0.5 + int(hashlib.sha1(f"{base}/{quote}".encode()).hexdigest()[:4], 16) / 65536) * 10000
    return math.floor(x + 0.5) / 10000  # Go math.Round (half away from zero), as in mock/tasks_pilot.go
