# Baseline: urllib3, all defaults (GET; top-level urllib3.request uses the default PoolManager).
import urllib3

def get_user_profile(base_url: str, user_id: str) -> dict:
    r = urllib3.request("GET", f"{base_url}/v1/users/{user_id}")
    if r.status >= 400:
        raise RuntimeError(f"HTTP {r.status}")
    return r.json()
