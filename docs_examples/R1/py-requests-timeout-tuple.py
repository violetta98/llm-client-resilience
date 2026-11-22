# Documentation example (requests, Advanced Usage > Timeouts): requests.get(url, timeout=(3.05, 27)),
# placed in the minimal R1 function of the D61 check (same wrapper for every example).
import requests


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    try:
        r = requests.get(url, timeout=(3.05, 27))
    except requests.RequestException as e:
        raise ProfileError(str(e)) from e
    if r.status_code != 200:
        raise ProfileError(f"status {r.status_code}")
    return r.json()
