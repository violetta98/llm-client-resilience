# Documentation example (urllib3, User Guide > Using Timeouts): http = urllib3.PoolManager(timeout=3.0),
# placed in the minimal R1 function of the D61 check.
import json

import urllib3


class ProfileError(Exception):
    pass


http = urllib3.PoolManager(timeout=3.0)


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    try:
        resp = http.request("GET", url)
    except urllib3.exceptions.HTTPError as e:
        raise ProfileError(str(e)) from e
    if resp.status != 200:
        raise ProfileError(f"status {resp.status}")
    return json.loads(resp.data)
