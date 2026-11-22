"""faultkit: a minimal fault-injection test kit for HTTP client functions (Table 12 of the article).

Standard library only (Python 3.9+); usable from unittest or pytest. A FaultStub is a local HTTP/1.1 server that
plays one stub behavior of the test specification; `call_with_limit` runs the function under test in a daemon thread
and reports whether and when it returned; the assert_* helpers state the assertions of the specification.

    from faultkit import FaultStub, call_with_limit, assert_returns_within
    with FaultStub("trickle", gap_s=0.25) as stub:
        r = call_with_limit(get_user_profile, stub.url, "u-42", limit_s=15)
        assert_returns_within(r, deadline_s=10)

Behaviors (stub.behavior):
  normal              200 with a JSON body after `delay_s` (default 0)
  trickle             headers, then the body one byte every `gap_s` (S4); the body is JSON after leading whitespace
  headers_only        headers, then no body byte (S4h)
  withhold            read the request, never respond (S3)
  status_burst        `n` responses with `status` (default 503), then 200 (S5a)
  retry_after         429 with Retry-After `ra_s` seconds (or an HTTP date with date_form=True), then 200 (S6a/S6b)
  outage              503 on every request for `outage_s` seconds from the first request, then 200 (S7)
  reset_after_write   read the request, record a state change, close the connection without a response (S8)
Refused connections (S9) need no stub: `closed_port_url()` returns a URL on a port with no listener.
Dropped SYNs (S1) and stalled TLS (S2) need packet-level tools such as Toxiproxy or a firewall rule.
"""
from __future__ import annotations

import email.utils
import json
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler

BODY = {"id": "u-42", "name": "User 42", "email": "user42@example.com", "created_at": "2024-01-15T09:30:00Z"}


@dataclass
class Request:
    t: float           # monotonic time the request line arrived
    method: str
    path: str
    headers: dict
    body: bytes


@dataclass
class Result:
    returned: bool
    elapsed_s: float
    value: object = None
    error: BaseException | None = None
    t_return: float | None = None


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class FaultStub:
    def __init__(self, behavior="normal", *, gap_s=2.0, delay_s=0.0, n=2, status=503, ra_s=2, date_form=False,
                 outage_s=30.0, body=None, pad=64):
        self.behavior, self.gap_s, self.delay_s, self.n, self.status = behavior, gap_s, delay_s, n, status
        self.ra_s, self.date_form, self.outage_s, self.pad = ra_s, date_form, outage_s, pad
        self.body = json.dumps(body if body is not None else BODY).encode()
        self.requests: list[Request] = []
        self.effects: list[float] = []      # times of state changes (reset_after_write)
        self._lock = threading.Lock()
        self._first: float | None = None
        self._stop = threading.Event()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # quiet
                pass

            def _read_body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _handle(self):
                body = self._read_body()
                now = time.monotonic()
                with stub._lock:
                    stub.requests.append(Request(now, self.command, self.path, dict(self.headers), body))
                    if stub._first is None:
                        stub._first = now
                    k = len(stub.requests)
                stub._respond(self, k, now)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _handle

        self._server = _Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    # --- behaviors -------------------------------------------------------------------------------------------
    def _send(self, h, status, body=b"", headers=()):
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            h.send_header(k, v)
        h.end_headers()
        if body:
            h.wfile.write(body)

    def _ok(self, h):
        self._send(h, 200, self.body)

    def _sleep(self, s):
        return not self._stop.wait(s)

    def _respond(self, h, k, now):
        b = self.behavior
        if b == "normal":
            self._sleep(self.delay_s) and self._ok(h)
        elif b in ("trickle", "headers_only"):
            data = b" " * self.pad + self.body
            h.send_response(200)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            h.wfile.flush()
            if b == "headers_only":
                self._stop.wait()
                return
            for i in range(len(data)):
                if not self._sleep(self.gap_s):
                    return
                try:
                    h.wfile.write(data[i:i + 1])
                    h.wfile.flush()
                except OSError:  # the client closed the connection: the exchange was aborted
                    return
        elif b == "withhold":
            self._stop.wait()
        elif b == "status_burst":
            if k <= self.n:
                self._send(h, self.status, b'{"error":"unavailable"}')
            else:
                self._ok(h)
        elif b == "retry_after":
            if k == 1:
                ra = email.utils.formatdate(time.time() + self.ra_s, usegmt=True) if self.date_form else str(self.ra_s)
                self._send(h, 429, b'{"error":"rate_limited"}', [("Retry-After", ra)])
            else:
                self._ok(h)
        elif b == "outage":
            if now - self._first < self.outage_s:
                self._send(h, 503, b'{"error":"unavailable"}')
            else:
                self._ok(h)
        elif b == "reset_after_write":
            with self._lock:
                self.effects.append(now)
            try:
                h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
            h.close_connection = True
            h.connection.close()
        else:
            raise ValueError(f"unknown behavior {b}")

    # --- context manager ---------------------------------------------------------------------------------------
    def __enter__(self):
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._server.shutdown()
        self._server.server_close()

    # --- observations -----------------------------------------------------------------------------------------
    def attempt_times(self):
        with self._lock:
            return [r.t for r in self.requests]


def closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def call_with_limit(fn, *args, limit_s=90.0, **kw):
    """Run fn(*args, **kw) in a daemon thread; wait at most limit_s. A function that has not returned is abandoned."""
    box = {}

    def work():
        try:
            box["value"] = fn(*args, **kw)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e
        box["t"] = time.monotonic()

    t0 = time.monotonic()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(limit_s)
    if "t" not in box:
        return Result(False, time.monotonic() - t0)
    return Result(True, box["t"] - t0, box.get("value"), box.get("error"), box["t"])


# --- assertions of the test specification --------------------------------------------------------------------
def assert_returns_within(r: Result, deadline_s: float, tolerance_s: float = 0.25):
    assert r.returned, f"did not return within the test limit (deadline {deadline_s} s)"
    assert r.elapsed_s <= deadline_s + tolerance_s, f"returned after {r.elapsed_s:.2f} s, deadline {deadline_s} s"


def assert_attempts_at_most(stub: FaultStub, n: int, window_s: float = 30.0):
    t = stub.attempt_times()
    if t:
        inside = [x for x in t if x - t[0] < window_s]
        assert len(inside) <= n, f"{len(inside)} attempts within {window_s} s (at most {n})"


def assert_no_early_retry(stub: FaultStub, wait_s: float, tolerance_s: float = 0.1):
    t = stub.attempt_times()
    if len(t) >= 2:
        assert t[1] - t[0] >= wait_s - tolerance_s, f"retried after {t[1] - t[0]:.2f} s, Retry-After {wait_s} s"


def assert_at_most_one_effect(stub: FaultStub, key_header="Idempotency-Key"):
    """At most one state change, or every repeat carries the same idempotency key."""
    reqs = [r for r in stub.requests if r.method in ("POST", "PUT", "PATCH", "DELETE")]
    if len(reqs) > 1:
        keys = {r.headers.get(key_header) for r in reqs}
        assert None not in keys and len(keys) == 1, f"{len(reqs)} writes without one shared {key_header}"


def assert_no_request_after(stub: FaultStub, r: Result, grace_s: float = 5.0):
    time.sleep(grace_s)
    late = [x for x in stub.attempt_times() if r.t_return is not None and x > r.t_return]
    assert not late, f"{len(late)} requests after the function returned"
