# Advice check (D52, empty-body case revised D56): requests, stream=True, a timer calls r.raw.shutdown() at the deadline (urllib3 >= 2.3).
import threading
import time

import requests


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    deadline = time.monotonic() + 10.0
    try:
        r = requests.get(f"{base_url.rstrip('/')}/v1/users/{user_id}", timeout=(2.0, 5.0), stream=True)
    except requests.RequestException as e:
        raise ProfileError(str(e)) from e
    t = threading.Timer(max(0.0, deadline - time.monotonic()), r.raw.shutdown)
    t.start()
    try:
        body = r.content
        if time.monotonic() > deadline:
            raise ProfileError("deadline exceeded")
        if r.status_code != 200:
            raise ProfileError(f"status {r.status_code}")
        return r.json()
    except (requests.RequestException, ValueError, OSError) as e:
        raise ProfileError(str(e)) from e
    finally:
        t.cancel()
        r.close()
