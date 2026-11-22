# Advice check (D54): as py-read1, with decode_content=True so that a gzip body is decoded.
import json
import time

import requests


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    deadline = time.monotonic() + 10.0
    try:
        with requests.get(f"{base_url.rstrip('/')}/v1/users/{user_id}", timeout=(2.0, 5.0), stream=True) as r:
            buf = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise ProfileError("deadline exceeded")
                chunk = r.raw.read1(65536, decode_content=True)
                if not chunk:
                    break
                buf += chunk
            if r.status_code != 200:
                raise ProfileError(f"status {r.status_code}")
            return json.loads(bytes(buf))
    except (requests.RequestException, ValueError) as e:
        raise ProfileError(str(e)) from e
