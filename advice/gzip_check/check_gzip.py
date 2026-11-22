"""D54: do the Python deadline loops of the advice appendix decode a gzip-encoded body?

The mock never compresses, so this runs the advice functions against a local server (127.0.0.1, inside a container
without network) that answers with Content-Encoding: gzip, once in one piece and once trickled in 8 parts.
  docker run --rm --network none -v "$PWD/advice:/adv:ro" --entrypoint python3 lcr-run-python:dev /adv/gzip_check/check_gzip.py
"""
import gzip
import importlib.util
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BODY = gzip.compress(json.dumps({"id": "u-001", "name": "User 001", "email": "user001@example.com",
                                 "created_at": "2024-01-15T09:30:00Z"}).encode())
MODE = {"trickle": False}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        if MODE["trickle"]:
            step = -(-len(BODY) // 8)
            for i in range(0, len(BODY), step):
                self.wfile.write(BODY[i:i + step]); self.wfile.flush(); time.sleep(0.1)
        else:
            self.wfile.write(BODY)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


IT_BYTES = '''
import json, time, httpx
class ProfileError(Exception): pass
def get_user_profile(base_url, user_id):
    deadline = time.monotonic() + 10.0
    with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as c:
        with c.stream("GET", f"{base_url.rstrip('/')}/v1/users/{user_id}") as r:
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if time.monotonic() > deadline:
                    raise ProfileError("deadline exceeded")
            return json.loads(bytes(buf))
'''


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    open("/tmp/itbytes.py", "w").write(IT_BYTES)
    progs = {"py-read1 (read1)": "/adv/R1/py-read1.py", "py-httpx-iterraw (iter_raw)": "/adv/R1/py-httpx-iterraw.py",
             "py-retry-deadline (read1, decode_content=True)": "/adv/R1/py-retry-deadline.py",
             "httpx iter_bytes": "/adv/R1/py-httpx-iterbytes.py", "py-read1-decode": "/adv/R1/py-read1-decode.py", "py-shutdown": "/adv/R1/py-shutdown.py",
             "py-asyncio-timeout": "/adv/R1/py-asyncio-timeout.py"}
    out = {}
    for trickle in (False, True):
        MODE["trickle"] = trickle
        for name, path in progs.items():
            m = load(path, "m" + str(abs(hash(name))))
            try:
                r = m.get_user_profile(base, "u-001")
                res = "ok" if isinstance(r, dict) and r.get("id") == "u-001" else f"wrong result {r!r}"
            except Exception as e:
                res = f"error {type(e).__name__}: {str(e)[:80]}"
            out[f"{'trickled' if trickle else 'whole'} | {name}"] = res
    for k, v in out.items():
        print(f"{k}: {v}")
    json.dump(out, sys.stdout if False else open("/dev/null", "w"))


if __name__ == "__main__":
    main()
