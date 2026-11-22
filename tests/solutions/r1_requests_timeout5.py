# Harness test solution (NOT a reference): requests with timeout=5.
import requests

def get_user_profile(base_url: str, user_id: str) -> dict:
    r = requests.get(f"{base_url}/v1/users/{user_id}", timeout=5)
    r.raise_for_status()
    return r.json()
