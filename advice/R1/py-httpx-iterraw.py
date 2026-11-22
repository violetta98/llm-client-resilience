# Advice check (D52): HTTPX stream with iter_raw() and a monotonic deadline.
import json
import time

import httpx


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    deadline = time.monotonic() + 10.0
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as c:
            with c.stream("GET", f"{base_url.rstrip('/')}/v1/users/{user_id}") as r:
                buf = bytearray()
                for chunk in r.iter_raw():
                    buf += chunk
                    if time.monotonic() > deadline:
                        raise ProfileError("deadline exceeded")
                if r.status_code != 200:
                    raise ProfileError(f"status {r.status_code}")
                return json.loads(bytes(buf))
    except (httpx.HTTPError, ValueError) as e:
        raise ProfileError(str(e)) from e
