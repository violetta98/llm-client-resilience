# Documentation example (HTTPX, Timeouts > fine tuning): timeout = httpx.Timeout(10.0, connect=60.0);
# client = httpx.Client(timeout=timeout), placed in the minimal R1 function of the D61 check.
import httpx


class ProfileError(Exception):
    pass


timeout = httpx.Timeout(10.0, connect=60.0)
client = httpx.Client(timeout=timeout)


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        raise ProfileError(str(e)) from e
    if r.status_code != 200:
        raise ProfileError(f"status {r.status_code}")
    return r.json()
