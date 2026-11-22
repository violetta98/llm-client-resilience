# Baseline: HTTPX, all defaults (POST).
import httpx

def send_sms(base_url: str, to: str, body: str) -> str:
    r = httpx.post(f"{base_url}/v1/messages", json={"to": to, "body": body})
    r.raise_for_status()
    return r.json()["id"]
