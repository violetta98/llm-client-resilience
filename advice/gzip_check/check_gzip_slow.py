"""Round 11: does the deadline of the Python advice loops hold when a gzip body trickles one byte every 2 s?

check_gzip.py showed that the decoding loops return a gzip body; it trickled 8 parts in 0.8 s, below the deadline.
Here a local server (127.0.0.1, inside a container without network) sends a level-9 gzip body of about 3 KB (large
enough for a dynamic Huffman block) one byte every 2 s, as S4 does with the plain body, when the request accepts gzip;
it sends the plain body the same way when the request asks for identity. Every program runs in its own thread; a
program that has not returned after 60 s is reported as such. The 10 s deadline of every program should end the call
after at most about 12 s.
  docker run --rm --network none -v "$PWD/advice:/adv:ro" --entrypoint python3 lcr-run-python:dev /adv/gzip_check/check_gzip_slow.py
"""
import gzip
import importlib.util
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLAIN = json.dumps({"id": "u-001", "name": "User 001", "email": "user001@example.com",
                    "created_at": "2024-01-15T09:30:00Z",
                    "notes": [f"note {i}: {i * 7919 % 104729:x} {'abcdefghij'[i % 10] * (i % 13)}" for i in range(150)]}).encode()
GZ = gzip.compress(PLAIN, compresslevel=9)
GAP_S = 2.0
LIMIT_S = 60.0


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        gz = "gzip" in self.headers.get("Accept-Encoding", "") and "identity" not in self.headers.get("Accept-Encoding", "")
        body = GZ if gz else PLAIN
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.flush()
        try:
            for i in range(len(body)):
                self.wfile.write(body[i:i + 1]); self.wfile.flush(); time.sleep(GAP_S)
        except OSError:
            pass


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


PROGS = {"py-read1-decode (read1, decode_content=True)": "/adv/R1/py-read1-decode.py",
         "py-httpx-iterbytes (iter_bytes)": "/adv/R1/py-httpx-iterbytes.py",
         "py-retry-deadline (read1, decode_content=True)": "/adv/R1/py-retry-deadline.py",
         "py-read1-identity (Accept-Encoding: identity)": "/adv/R1/py-read1-identity.py",
         "py-retry-budget (Accept-Encoding: identity)": "/adv/R1/py-retry-budget.py",
         "py-shutdown (raw.shutdown timer)": "/adv/R1/py-shutdown.py",
         "py-asyncio-timeout (asyncio.timeout)": "/adv/R1/py-asyncio-timeout.py"}


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    out = {}

    def run(name, path):
        t0 = time.monotonic()
        try:
            r = load(path, "m" + str(abs(hash(name)))).get_user_profile(base, "u-001")
            res = "returned a result" if isinstance(r, dict) else f"returned {r!r}"
        except Exception as e:  # noqa: BLE001
            res = f"error {type(e).__name__}: {str(e)[:70]}"
        out[name] = f"{res} after {time.monotonic() - t0:.1f} s"

    threads = {n: threading.Thread(target=run, args=(n, p), daemon=True) for n, p in PROGS.items()}
    for t in threads.values():
        t.start()
    t_end = time.monotonic() + LIMIT_S
    for t in threads.values():
        t.join(max(0.0, t_end - time.monotonic()))
    print(f"gzip body {len(GZ)} bytes (plain {len(PLAIN)}), one byte every {GAP_S:.0f} s, limit {LIMIT_S:.0f} s")
    for n in PROGS:
        print(f"{n}: {out.get(n, f'no return within {LIMIT_S:.0f} s')}")
    os._exit(0)


if __name__ == "__main__":
    main()
