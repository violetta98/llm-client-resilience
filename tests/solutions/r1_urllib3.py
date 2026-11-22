# Harness test solution: urllib3 with defaults.
import urllib3

def get_user_profile(base_url: str, user_id: str) -> dict:
    r = urllib3.request("GET", f"{base_url}/v1/users/{user_id}")
    if r.status != 200:
        raise RuntimeError(r.status)
    return r.json()
