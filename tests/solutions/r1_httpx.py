# Harness test solution: httpx with defaults.
import httpx

def get_user_profile(base_url: str, user_id: str) -> dict:
    r = httpx.get(f"{base_url}/v1/users/{user_id}")
    r.raise_for_status()
    return r.json()
