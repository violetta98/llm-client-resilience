# Task bodies of the Python references for the CONFIRMATORY tasks R6, W5, B5, H4
# (tasks/CONFIRM_TASKS.md). Loaded by references/build_confirm.py into the namespace of
# tasks.py (as pilot_tasks.py is by build.py --pilot); same prelude, same budgets:
# 9.5 s without a stated limit, 28 s for the 30 s job, limit - 0.2 s for the handler.

BODIES["R6"] = '''
from urllib.parse import quote


class StockError(Exception):
    pass


def get_stock_levels(base_url: str, product_id: str) -> dict:
    dl = deadline_in(9.5)
    try:
        r = call("GET", f"{base_url}/v1/products/{quote(product_id, safe='')}/stock", dl, idempotent=True)
    except _GiveUp as e:
        raise StockError(str(e)) from e
    if r.status != 200:
        raise StockError(f"HTTP {r.status}")
    return r.json()
'''

BODIES["W5"] = '''
import uuid


class TicketError(Exception):
    pass


def create_ticket(base_url: str, customer_id: str, subject: str, message: str) -> dict:
    dl = deadline_in(9.5)
    key = str(uuid.uuid4())  # one key per ticket: every retry reuses it

    def headers(attempt):
        k = str(uuid.uuid4()) if MUTANT == "UNSAFE_POST_RETRY" else key
        return {"Idempotency-Key": k}

    body = {"customer_id": customer_id, "subject": subject, "message": message}
    try:
        r = call("POST", f"{base_url}/v1/tickets", dl, idempotent=True, headers_fn=headers, json=body)
    except _GiveUp as e:
        raise TicketError(str(e)) from e
    if r.status != 201:
        raise TicketError(f"HTTP {r.status}: {r.body[:200]!r}")
    return r.json()
'''

BODIES["B5"] = '''
from urllib.parse import quote


class ShipmentUpdatesError(Exception):
    pass


def fetch_shipment_updates(base_url: str, carrier_id: str, since: str) -> list[dict]:
    dl = deadline_in(28.0)
    try:
        r = call("GET", f"{base_url}/v1/carriers/{quote(carrier_id, safe='')}/shipment-updates", dl, idempotent=True,
                 params={"since": since})
    except _GiveUp as e:
        raise ShipmentUpdatesError(str(e)) from e
    if r.status != 200:
        raise ShipmentUpdatesError(f"HTTP {r.status}")
    return r.json()["updates"]
'''

BODIES["H4"] = '''
from urllib.parse import quote

DEFAULT_PREFERENCES = {"email": True, "sms": False, "push": False}


def get_notification_preferences(preferences_url: str, user_id: str) -> dict:
    dl = deadline_in(1.8)
    try:
        r = call("GET", f"{preferences_url}/v1/users/{quote(user_id, safe='')}/notification-preferences", dl, idempotent=True)
        if r.status != 200:
            return dict(DEFAULT_PREFERENCES)
        p = r.json()
        if not all(isinstance(p.get(k), bool) for k in DEFAULT_PREFERENCES):
            return dict(DEFAULT_PREFERENCES)
        return {k: p[k] for k in DEFAULT_PREFERENCES}
    except Exception:  # noqa: BLE001 - the documented default
        return dict(DEFAULT_PREFERENCES)
'''
