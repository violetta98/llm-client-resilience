# Advice check (round 11): as py-read1, but the body is requested uncompressed (header Accept-Encoding set to
# "identity"), so every raw read returns to the deadline check; urllib3 errors raised while reading r.raw are wrapped.
import json
import time

import requests
import urllib3


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    deadline = time.monotonic() + 10.0
    try:
        with requests.get(f"{base_url.rstrip('/')}/v1/users/{user_id}", timeout=(2.0, 2.0), stream=True,
                          headers={"Accept-Encoding": "identity"}) as r:
            buf = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise ProfileError("deadline exceeded")
                chunk = r.raw.read1(65536)
                if not chunk:
                    break
                buf += chunk
            if r.status_code != 200:
                raise ProfileError(f"status {r.status_code}")
            return json.loads(bytes(buf))
    except (requests.RequestException, urllib3.exceptions.HTTPError, ValueError) as e:
        raise ProfileError(str(e)) from e
