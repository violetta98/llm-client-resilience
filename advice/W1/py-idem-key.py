# Advice check (D56, revised D57): a payment POST retried under one 10 s deadline with an Idempotency-Key. The key
# identifies one payment intent: the caller passes it (and stores it with the intent, so a restarted job sends the same
# key), or it is derived from the whole request (order, amount, currency), so a corrected payment gets a new key. The
# body is identical in every attempt, so a 422 (key reused with another body) is a bug and is not retried; a 409 (the
# first request with this key is still being processed) is retried later like a 503. Attempts:
# at most four, min(own timeout, time left) each, body included (uncompressed, deadline checked after every read);
# 429/502-504 and connection errors are retried with backoff and jitter; Retry-After in both forms, a date measured
# from the server's Date header; a Retry-After that does not fit the time left fails at once; TLS errors not retried.
import email.utils
import hashlib
import json
import random
import time

import requests
import urllib3


class PaymentError(Exception):
    pass


RETRY_STATUS = {409, 429, 502, 503, 504}
TRANSIENT = (requests.ConnectionError, requests.Timeout, urllib3.exceptions.HTTPError)


def _retry_after(value: str, date: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.isascii() and value.isdigit():  # ASCII digits only; anything else is a date or invalid
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value).timestamp()
        now = email.utils.parsedate_to_datetime(date).timestamp() if date else time.time()
    except (TypeError, ValueError):
        return None
    return max(0.0, when - now)


def _once(url: str, body: bytes, key: str, deadline: float):
    left = deadline - time.monotonic()
    if left <= 0:
        raise PaymentError("deadline exceeded")
    headers = {"Content-Type": "application/json", "Idempotency-Key": key, "Accept-Encoding": "identity"}
    with requests.post(url, data=body, headers=headers, timeout=(min(2.0, left), min(2.0, left)), stream=True) as r:
        if r.status_code in RETRY_STATUS:
            return r.status_code, (r.headers.get("Retry-After", ""), r.headers.get("Date", ""))
        buf = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise PaymentError("deadline exceeded")
            chunk = r.raw.read1(65536)
            if not chunk:
                break
            buf += chunk
        if r.status_code == 422:
            raise PaymentError("Idempotency-Key reused with a different body")
        if r.status_code not in (200, 201):
            raise PaymentError(f"status {r.status_code}")
        try:
            return 201, json.loads(bytes(buf))
        except ValueError as e:
            raise PaymentError(f"bad body: {e}") from e


def create_payment(base_url: str, order_id: str, amount: str, currency: str, deadline_s: float = 10.0,
                   idempotency_key: str | None = None) -> dict:
    url = f"{base_url.rstrip('/')}/v1/payments"
    body = json.dumps({"order_id": order_id, "amount": amount, "currency": currency}).encode()
    key = idempotency_key or "payment-" + hashlib.sha256(body).hexdigest()[:32]
    deadline = time.monotonic() + min(deadline_s, 10.0)
    delay = 0.2
    for attempt in range(4):
        server_wait = None
        try:
            status, res = _once(url, body, key, deadline)
            if status == 201:
                return res
            server_wait = _retry_after(*res)
            last = f"status {status}"
        except requests.exceptions.SSLError as e:
            raise PaymentError(f"TLS error: {e}") from e
        except TRANSIENT as e:  # safe to repeat: the same key makes the server apply the payment at most once
            last = f"{type(e).__name__}: {e}"
        except requests.RequestException as e:
            raise PaymentError(str(e)) from e
        if attempt == 3:
            raise PaymentError(f"retries exhausted ({last})")
        wait = server_wait if server_wait is not None else delay * random.uniform(0.5, 1.0)
        if time.monotonic() + wait > deadline:
            raise PaymentError(f"no time left for the next attempt ({last})")
        time.sleep(wait)
        delay = min(delay * 2, 2.0)
    raise PaymentError("retries exhausted")
