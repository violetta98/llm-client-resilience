# Baseline: urllib.request, all defaults (POST).
import json
import urllib.request

def send_sms(base_url: str, to: str, body: str) -> str:
    req = urllib.request.Request(f"{base_url}/v1/messages", data=json.dumps({"to": to, "body": body}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["id"]
