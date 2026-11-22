# Baseline: urllib3, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
# urllib3.request() goes through urllib3's module-level default PoolManager, so
# consecutive calls share one keep-alive pool; no explicit client is needed.
import urllib3

def send_sms(base_url: str, to: str, body: str) -> str:
    urllib3.request("GET", f"{base_url}/v1/messages")  # warm the pool; 405 ignored, body preloaded so the connection is idle
    r = urllib3.request("POST", f"{base_url}/v1/messages", json={"to": to, "body": body})
    if r.status >= 400:
        raise RuntimeError(f"HTTP {r.status}")
    return r.json()["id"]
