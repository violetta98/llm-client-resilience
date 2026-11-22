# Baseline: urllib3, all defaults (POST).
import urllib3

def send_sms(base_url: str, to: str, body: str) -> str:
    r = urllib3.request("POST", f"{base_url}/v1/messages", json={"to": to, "body": body})
    if r.status >= 400:
        raise RuntimeError(f"HTTP {r.status}")
    return r.json()["id"]
