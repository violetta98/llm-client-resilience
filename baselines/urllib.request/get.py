# Baseline: urllib.request, all defaults (GET).
import json
import urllib.request

def get_user_profile(base_url: str, user_id: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/v1/users/{user_id}") as r:
        return json.loads(r.read())
