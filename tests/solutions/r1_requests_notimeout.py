# Harness test solution (NOT a reference): requests with all defaults.
import requests

def get_user_profile(base_url: str, user_id: str) -> dict:
    r = requests.get(f"{base_url}/v1/users/{user_id}")
    r.raise_for_status()
    return r.json()
