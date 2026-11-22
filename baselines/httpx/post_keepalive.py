# Baseline: HTTPX, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
import httpx

_c = httpx.Client()  # shared Client (connection pool), created once

def send_sms(base_url: str, to: str, body: str) -> str:
    _c.get(f"{base_url}/v1/messages").read()  # warm the pool; 405 ignored, body read so the connection is idle
    r = _c.post(f"{base_url}/v1/messages", json={"to": to, "body": body})
    r.raise_for_status()
    return r.json()["id"]
