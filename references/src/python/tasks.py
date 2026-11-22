# Task bodies of the Python reference solutions. references/build.py writes
# references/<ID>/python/solution.py = prelude + the body of that task.
# Budgets: 9.5 s for tasks without a time limit (draft: 10 s per call),
# 28 s for the 30 s background tasks, limit - 0.2 s for handler tasks.

BODIES = {}

BODIES["R1"] = '''
from urllib.parse import quote


class ProfileError(Exception):
    pass


def get_user_profile(base_url: str, user_id: str) -> dict:
    dl = deadline_in(9.5)
    try:
        r = call("GET", f"{base_url}/v1/users/{quote(user_id, safe='')}", dl, idempotent=True)
    except _GiveUp as e:
        raise ProfileError(str(e)) from e
    if r.status != 200:
        raise ProfileError(f"HTTP {r.status}")
    return r.json()
'''

BODIES["R2"] = '''
class SearchError(Exception):
    pass


def search_products(base_url: str, query: str, category: str, max_price: float) -> list[dict]:
    dl = deadline_in(9.5)
    params = {"q": query, "category": category, "max_price": str(max_price)}
    try:
        r = call("GET", f"{base_url}/v1/products", dl, idempotent=True, params=params)
    except _GiveUp as e:
        raise SearchError(str(e)) from e
    if r.status != 200:
        raise SearchError(f"HTTP {r.status}")
    return r.json()["items"]
'''

BODIES["R3"] = '''
import os
from urllib.parse import quote


class DownloadError(Exception):
    pass


def download_report(base_url: str, report_id: str, dest_path: str) -> int:
    """Streams into a per-attempt temporary file; only a complete download is
    moved to dest_path (urllib3 verifies the length against Content-Length)."""
    dl = deadline_in(9.5)
    parts = []

    def sink_factory(attempt):
        path = f"{dest_path}.part{attempt}"
        f = open(path, "wb")
        parts.append((path, f))
        return f.write

    try:
        r = call("GET", f"{base_url}/v1/reports/{quote(report_id, safe='')}/download", dl, idempotent=True,
                 sink_factory=sink_factory)
        if r.status != 200:
            raise DownloadError(f"HTTP {r.status}")
        path, f = parts[r.attempts - 1]
        f.close()
        size = os.path.getsize(path)
        os.replace(path, dest_path)
        return size
    except _GiveUp as e:
        raise DownloadError(str(e)) from e
    finally:
        for path, f in parts:
            f.close()
            if os.path.exists(path):
                os.remove(path)
'''

BODIES["R4"] = '''
from urllib.parse import quote


class OrdersError(Exception):
    pass


def list_all_orders(base_url: str, customer_id: str) -> list[dict]:
    dl = deadline_in(9.5)
    url = f"{base_url}/v1/customers/{quote(customer_id, safe='')}/orders"
    orders, cursor = [], None
    while True:
        params = {"cursor": cursor} if cursor else None
        try:
            r = call("GET", url, dl, idempotent=True, params=params)
        except _GiveUp as e:
            raise OrdersError(str(e)) from e
        if r.status != 200:
            raise OrdersError(f"HTTP {r.status}")
        page = r.json()
        orders.extend(page["orders"])
        cursor = page.get("next_cursor")
        if not cursor:
            return orders
'''

BODIES["R5"] = '''
from urllib.parse import quote


def is_feature_enabled(base_url: str, flag_key: str) -> bool:
    dl = deadline_in(9.5)
    try:
        r = call("GET", f"{base_url}/v1/flags/{quote(flag_key, safe='')}", dl, idempotent=True)
        if r.status != 200:
            return False
        return r.json().get("enabled") is True
    except Exception:  # noqa: BLE001 - the documented default for every failure
        return False
'''

BODIES["W1"] = '''
import uuid


class PaymentError(Exception):
    pass


def create_payment(base_url: str, order_id: str, amount: str, currency: str) -> dict:
    dl = deadline_in(9.5)
    key = str(uuid.uuid4())  # one key per payment: every retry reuses it

    def headers(attempt):
        k = str(uuid.uuid4()) if MUTANT == "UNSAFE_POST_RETRY" else key
        return {"Idempotency-Key": k}

    body = {"order_id": order_id, "amount": amount, "currency": currency}
    try:
        r = call("POST", f"{base_url}/v1/payments", dl, idempotent=True, headers_fn=headers, json=body)
    except _GiveUp as e:
        raise PaymentError(str(e)) from e
    if r.status != 201:
        raise PaymentError(f"HTTP {r.status}: {r.body[:200]!r}")
    return r.json()
'''

BODIES["W2"] = '''
class SmsError(Exception):
    pass


def send_sms(base_url: str, to: str, body: str) -> str:
    """No idempotency support: retried only when the request certainly was
    not processed (connection refused or not established, 429, 503)."""
    dl = deadline_in(9.5)
    try:
        r = call("POST", f"{base_url}/v1/messages", dl, idempotent=False, json={"to": to, "body": body})
    except _GiveUp as e:
        raise SmsError(str(e)) from e
    if r.status != 202:
        raise SmsError(f"HTTP {r.status}")
    return r.json()["id"]
'''

BODIES["W3"] = '''
from urllib.parse import quote


class UploadError(Exception):
    pass


def upload_document(base_url: str, doc_id: str, content: str) -> dict:
    dl = deadline_in(9.5)
    try:
        r = call("PUT", f"{base_url}/v1/documents/{quote(doc_id, safe='')}", dl, idempotent=True,
                 data=content.encode("utf-8"), headers={"Content-Type": "text/plain; charset=utf-8"})
    except _GiveUp as e:
        raise UploadError(str(e)) from e
    if r.status != 200:
        raise UploadError(f"HTTP {r.status}")
    return r.json()
'''

BODIES["W4"] = '''
from urllib.parse import quote


class SubscriptionError(Exception):
    pass


def cancel_subscription(base_url: str, subscription_id: str) -> None:
    dl = deadline_in(9.5)
    try:
        r = call("DELETE", f"{base_url}/v1/subscriptions/{quote(subscription_id, safe='')}", dl, idempotent=True)
    except _GiveUp as e:
        raise SubscriptionError(str(e)) from e
    if r.status == 200:
        return None
    if r.status == 404 and r.attempts > 1:
        return None  # an earlier attempt may have canceled it
    raise SubscriptionError(f"HTTP {r.status}")
'''

BODIES["B1"] = '''
from urllib.parse import quote


class SyncError(Exception):
    pass


def sync_records(base_url: str, records: list[dict]) -> int:
    dl = deadline_in(28.0)
    written = 0
    for rec in records:
        try:
            r = call("PUT", f"{base_url}/v1/records/{quote(str(rec['id']), safe='')}", dl, idempotent=True, json=rec)
        except _GiveUp as e:
            raise SyncError(f"record {rec['id']}: {e}") from e
        if r.status != 200:
            raise SyncError(f"record {rec['id']}: HTTP {r.status}")
        written += 1
    return written
'''

BODIES["B2"] = '''
import time
from urllib.parse import quote


class ExportError(Exception):
    pass


POLL_INTERVAL_S = 1.0


def wait_for_export(base_url: str, export_id: str) -> str:
    dl = deadline_in(28.0)
    url = f"{base_url}/v1/exports/{quote(export_id, safe='')}"
    while True:
        try:
            r = call("GET", url, dl, idempotent=True)
        except _GiveUp as e:
            raise ExportError(str(e)) from e
        if r.status != 200:
            raise ExportError(f"HTTP {r.status}")
        st = r.json()
        if st.get("status") == "completed" and st.get("result_url"):
            return st["result_url"]
        if st.get("status") == "failed":
            raise ExportError("export failed")
        if time.monotonic() + POLL_INTERVAL_S >= dl:
            raise ExportError("export did not complete in time")
        time.sleep(POLL_INTERVAL_S)
'''

BODIES["B3"] = '''
from urllib.parse import quote


class BalanceError(Exception):
    pass


def get_account_balance(auth_url: str, api_url: str, client_id: str, client_secret: str, account_id: str) -> dict:
    dl = deadline_in(28.0)
    form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    try:
        for _ in range(2):  # a second token only if the first is rejected
            t = call("POST", f"{auth_url}/oauth/token", dl, idempotent=True, data=form)
            if t.status != 200:
                raise BalanceError(f"token: HTTP {t.status}")
            token = t.json()["access_token"]
            r = call("GET", f"{api_url}/v1/accounts/{quote(account_id, safe='')}/balance", dl, idempotent=True,
                     headers={"Authorization": f"Bearer {token}"})
            if r.status != 401:
                break
    except _GiveUp as e:
        raise BalanceError(str(e)) from e
    if r.status != 200:
        raise BalanceError(f"HTTP {r.status}")
    return r.json()
'''

BODIES["B4"] = '''
class DeliveryError(Exception):
    pass


def deliver_webhook(endpoint_url: str, event: dict) -> None:
    """The receiver deduplicates by event id, so resending the same event is safe."""
    dl = deadline_in(28.0)
    try:
        r = call("POST", endpoint_url, dl, idempotent=True, json=event)
    except _GiveUp as e:
        raise DeliveryError(str(e)) from e
    if not 200 <= r.status < 300:
        raise DeliveryError(f"rejected: HTTP {r.status}")
'''

BODIES["H1"] = '''
from urllib.parse import quote


class ProfilePageError(Exception):
    pass


def get_profile_page(profile_url: str, recommendations_url: str, user_id: str) -> dict:
    dl = deadline_in(1.8)
    uid = quote(user_id, safe="")
    try:
        p = call("GET", f"{profile_url}/v1/users/{uid}", dl, idempotent=True)
    except _GiveUp as e:
        raise ProfilePageError(str(e)) from e
    if p.status != 200:
        raise ProfilePageError(f"profile: HTTP {p.status}")
    recs = None
    try:
        r = call("GET", f"{recommendations_url}/v1/users/{uid}/recommendations", dl, idempotent=True)
        if r.status == 200:
            recs = r.json()["items"]
    except Exception:  # noqa: BLE001 - degrade: profile without recommendations
        recs = None
    return {"profile": p.json(), "recommendations": recs}
'''

BODIES["H2"] = '''
def is_dependency_ready(dependency_url: str) -> bool:
    dl = deadline_in(0.8)
    try:
        r = call("GET", f"{dependency_url}/healthz", dl, idempotent=True)
        return r.status == 200 and r.json().get("status") == "ok"
    except Exception:  # noqa: BLE001 - not ready
        return False
'''

BODIES["H3"] = '''
import threading
from urllib.parse import quote


class NoQuoteError(Exception):
    pass


def best_price(supplier_urls: list[str], sku: str) -> dict:
    dl = deadline_in(2.8)
    quotes = []
    lock = threading.Lock()

    def ask(url):
        try:
            r = call("GET", f"{url}/v1/quotes", dl, idempotent=True, params={"sku": sku})
            if r.status == 200:
                q = r.json()
                with lock:
                    quotes.append(q)
        except Exception:  # noqa: BLE001 - this supplier is ignored
            pass

    ts = [threading.Thread(target=ask, args=(u,), daemon=True) for u in supplier_urls]
    for t in ts:
        t.start()
    for t in ts:
        t.join(max(0.0, dl - time.monotonic()) if MUTANT != "NO_TIMEOUT" else None)
    with lock:
        got = list(quotes)
    if not got:
        raise NoQuoteError("no supplier returned a quote")
    return min(got, key=lambda q: float(q["price"]))
'''
