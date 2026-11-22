# Task bodies of the Python references for the PILOT tasks P1-P3 (outside the
# benchmark). Loaded by references/build.py --pilot into the namespace of tasks.py.

BODIES["P1"] = '''
from urllib.parse import quote


class RateError(Exception):
    pass


def get_exchange_rate(base_url: str, base_currency: str, quote_currency: str) -> dict:
    dl = deadline_in(9.5)
    try:
        r = call("GET", f"{base_url}/v1/rates/{quote(base_currency, safe='')}/{quote(quote_currency, safe='')}", dl, idempotent=True)
    except _GiveUp as e:
        raise RateError(str(e)) from e
    if r.status != 200:
        raise RateError(f"HTTP {r.status}")
    return r.json()
'''

BODIES["P2"] = '''
from urllib.parse import quote


class CommentError(Exception):
    pass


def add_ticket_comment(base_url: str, ticket_id: str, text: str) -> str:
    """No idempotency support: retried only when the request certainly was
    not processed (connection refused or not established, 429, 503)."""
    dl = deadline_in(9.5)
    try:
        r = call("POST", f"{base_url}/v1/tickets/{quote(ticket_id, safe='')}/comments", dl, idempotent=False, json={"text": text})
    except _GiveUp as e:
        raise CommentError(str(e)) from e
    if r.status != 201:
        raise CommentError(f"HTTP {r.status}")
    return r.json()["id"]
'''

BODIES["P3"] = '''
from urllib.parse import urlencode


def estimate_delivery_days(shipping_url: str, postal_code: str) -> int:
    dl = deadline_in(1.8)
    try:
        r = call("GET", f"{shipping_url}/v1/estimates?{urlencode({'postal_code': postal_code})}", dl, idempotent=True)
        if r.status != 200:
            return 5
        days = r.json().get("days")
        return days if isinstance(days, int) and not isinstance(days, bool) else 5
    except Exception:  # noqa: BLE001 - the documented default
        return 5
'''
