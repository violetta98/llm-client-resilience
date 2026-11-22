# Advice check (D54): retries with backoff and jitter under one 10 s deadline for the whole call, including the body.
import json
import random
import time

import requests


class ProfileError(Exception):
    pass


RETRY_STATUS = {429, 502, 503, 504}


def _once(url: str, deadline: float) -> requests.Response | dict:
    left = deadline - time.monotonic()
    if left <= 0:
        raise ProfileError("deadline exceeded")
    with requests.get(url, timeout=(min(2.0, left), min(5.0, left)), stream=True) as r:
        if r.status_code in RETRY_STATUS:
            return r
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


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    deadline = time.monotonic() + 10.0
    delay = 0.2
    for attempt in range(4):
        try:
            res = _once(url, deadline)
            if isinstance(res, dict):
                return res
            wait = delay
            ra = res.headers.get("Retry-After", "")
            if ra.isdigit():
                wait = float(ra)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == 3:
                raise ProfileError(str(e)) from e
            wait = delay
        except (requests.RequestException, ValueError) as e:
            raise ProfileError(str(e)) from e
        if attempt == 3 or time.monotonic() + wait > deadline:
            raise ProfileError("retries exhausted")
        time.sleep(wait * random.uniform(0.5, 1.0) if wait == delay else wait)
        delay = min(delay * 2, 2.0)
    raise ProfileError("retries exhausted")
