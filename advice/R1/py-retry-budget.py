# Advice check (D55, revised D56): retries with backoff and jitter under one deadline for the whole call, body included
# (10 s, or less if the caller passes deadline_s). Each attempt gets min(own timeout, time left); Retry-After is honored
# in both forms, a date relative to the server's Date header; a Retry-After that does not fit the time left fails at
# once; the body is requested uncompressed so that the deadline is checked after every raw read; urllib3 errors raised
# while reading r.raw are caught; TLS errors are not retried. The connect and header phases are bounded per socket
# operation only (2 s each), and DNS resolution is not bounded at all.
import email.utils
import json
import random
import time

import requests
import urllib3

class ProfileError(Exception):
    pass


RETRY_STATUS = {429, 502, 503, 504}
TRANSIENT = (requests.ConnectionError, requests.Timeout, urllib3.exceptions.HTTPError)


def _retry_after(value: str, date: str) -> float | None:
    value = value.strip()
    if value.isascii() and value.isdigit():  # ASCII digits only; anything else is a date or invalid
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None
    try:  # a date is server time: measure it from the server's Date header, not from the local clock
        now = email.utils.parsedate_to_datetime(date).timestamp() if date else time.time()
    except (TypeError, ValueError):
        now = time.time()
    return max(0.0, when - now)


def _once(url: str, deadline: float):
    left = deadline - time.monotonic()
    if left <= 0:
        raise ProfileError("deadline exceeded")
    with requests.get(url, timeout=(min(2.0, left), min(2.0, left)), stream=True,
                      headers={"Accept-Encoding": "identity"}) as r:
        if r.status_code in RETRY_STATUS:
            return r.status_code, (r.headers.get("Retry-After", ""), r.headers.get("Date", ""))
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
        try:
            return 200, json.loads(bytes(buf))
        except ValueError as e:
            raise ProfileError(f"bad body: {e}") from e


def get_user_profile(base_url: str, user_id: str, deadline_s: float = 10.0) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    deadline = time.monotonic() + min(deadline_s, 10.0)
    delay = 0.2
    for attempt in range(4):
        server_wait = None
        try:
            status, res = _once(url, deadline)
            if status == 200:
                return res
            server_wait = _retry_after(*res) if res[0] else None
            last = f"status {status}"
        except requests.exceptions.SSLError as e:
            raise ProfileError(f"TLS error: {e}") from e
        except TRANSIENT as e:
            last = f"{type(e).__name__}: {e}"
        except requests.RequestException as e:
            raise ProfileError(str(e)) from e
        if attempt == 3:
            raise ProfileError(f"retries exhausted ({last})")
        wait = server_wait if server_wait is not None else delay * random.uniform(0.5, 1.0)
        if time.monotonic() + wait > deadline:
            raise ProfileError(f"no time left for the next attempt ({last})")
        time.sleep(wait)
        delay = min(delay * 2, 2.0)
    raise ProfileError("retries exhausted")
