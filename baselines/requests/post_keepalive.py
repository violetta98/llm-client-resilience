# Baseline: requests, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
import requests

_s = requests.Session()  # shared Session (connection pool), created once

def send_sms(base_url: str, to: str, body: str) -> str:
    _s.get(f"{base_url}/v1/messages").content  # warm the pool; 405 ignored, body read so the connection is idle
    r = _s.post(f"{base_url}/v1/messages", json={"to": to, "body": body})
    r.raise_for_status()
    return r.json()["id"]
