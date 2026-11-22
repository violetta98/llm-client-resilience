"""The four tasks of the CONFIRMATORY replication (R6, W5, B5, H4; tasks/CONFIRM_TASKS.md).

One new task per group, written after the protocol-v1 freeze and outside it. They are
rendered with exactly the same templates, operational lines, offered-library lines and
condition texts as the 16 benchmark tasks (tasks/generate_confirm.py reuses the
functions of tasks/generate.py and the constants of tasks/catalog.py, neither of
which is changed) into tasks/<ID>/ next to the benchmark tasks.

Dict schema: identical to tasks/catalog.py (same keys, same meaning).
"""
from catalog import IDEM_YES

STATUS = "confirmatory replication task (added after the protocol-v1 freeze; tasks/CONFIRM_TASKS.md)"

CONFIRM_SINCE = "2026-03-01T00:00:00Z"  # B5: the `since` argument of every invocation


def b5_updates(carrier_id, since=CONFIRM_SINCE):
    """Expected B5 result (mirrors mock/tasks_confirm.go)."""
    n = carrier_id.split("-")[-1]
    st = ["picked_up", "in_transit", "out_for_delivery", "delivered", "exception"]
    out = []
    for k in range(1, 26):
        out.append({"shipment_id": f"shp-{n}-{k:03d}", "status": st[(int(n) + k) % 5],
                    "updated_at": f"2026-03-01T{(k * 17) // 60:02d}:{(k * 17) % 60:02d}:00Z"})
    return [u for u in out if u["updated_at"] > since]


def r6_stock(product_id):
    """Expected R6 result (mirrors mock/tasks_confirm.go)."""
    n = int(product_id.split("-")[-1])
    return {"product_id": product_id,
            "warehouses": [{"warehouse_id": f"wh-{k:02d}", "available": (n * 37 + k * 101) % 1000, "reserved": (n + k * 7) % 50}
                           for k in range(1, 25)],
            "updated_at": "2026-03-01T06:00:00Z"}


H4_REAL = {"email": False, "sms": True, "push": True}
H4_DEFAULT = {"email": True, "sms": False, "push": False}

CONFIRM_TASKS = [
    # ------------------------------------------------------------------ READ
    dict(
        id="R6", title="Fetch the stock levels of a product across warehouses", group="read", method="GET", context="Standalone function",
        func="get_stock_levels", params=[("base_url", "str"), ("product_id", "str")], returns="object",
        error="Stock", java_class="StockClient", time_limit_s=None, deps={"A": "inventory service"},
        description=["It fetches the stock levels of the product in every warehouse from the inventory service and returns",
                     "the stock object from the response. {RAISE:Stock} if the stock levels cannot be fetched."],
        api=[dict(dep="A", line="GET {base_url}/v1/products/{product_id}/stock",
                  codes="200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404: product not found.")],
        warmup=["{A}", "prd-000"], single=["{A}", "prd-042"], s7=[["{A}", f"prd-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/products/{product_id}/stock (the only request)", logical_key="product_id",
        mock=["Products prd-000 … prd-999 exist: {product_id, warehouses: 24 entries wh-01 … wh-24 with available = (NNN·37 + k·101) mod 1000 "
              "and reserved = (NNN + k·7) mod 50, updated_at: \"2026-03-01T06:00:00Z\"}; any other id → 404.",
              "The JSON body is about 1.5 KB (below the S4 trickle length of 4096 bytes, so S4 delivers the complete body, padded with leading whitespace)."],
        correct={"value": "the stock object of prd-042 (24 warehouses) as defined in the mock data"},
        degraded=None,
        table_iv="Correct result, or an error.",
    ),
    # ------------------------------------------------------------------ WRITE
    dict(
        id="W5", title="Create a support ticket; the API accepts Idempotency-Key", group="write", method="POST", context="Standalone function",
        func="create_ticket", params=[("base_url", "str"), ("customer_id", "str"), ("subject", "str"), ("message", "str")],
        returns="object", error="Ticket", java_class="SupportTicketClient", time_limit_s=None, deps={"A": "helpdesk API"},
        description=["It opens a support ticket for the customer in the helpdesk and returns the ticket object from the response.",
                     "{RAISE:Ticket} if the ticket cannot be created."],
        api=[dict(dep="A", line="POST {base_url}/v1/tickets, JSON body {customer_id, subject, message}",
                  codes="201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request. 422: the Idempotency-Key was already used with a different body.",
                  idem=IDEM_YES.format(thing="ticket"))],
        warmup=["{A}", "cus-000", "warm-up", "warm-up"],
        single=["{A}", "cus-042", "Invoice shows the wrong address", "The invoice for order ord-042 lists my old billing address."],
        s7=[["{A}", f"cus-{100 + i:03d}", "Invoice shows the wrong address", "The invoice lists my old billing address."] for i in range(10)],
        fault_dep="A", faulted_request="POST /v1/tickets", logical_key="customer_id (body)",
        mock=["Creates ticket tkt_<n> {id, customer_id, subject, status: \"open\", created_at: \"2026-03-01T12:00:00Z\"}; effect ticket_created. "
              "customer_id must match ^cus-[0-9]{3}$, subject and message must be non-empty, else 400.",
              "With an Idempotency-Key seen before (same body): no new ticket, the stored response is replayed (201, same id; effect ticket_replayed). Same key, different body → 422.",
              "Without a key every request creates a ticket."],
        correct={"value": "the ticket object for cus-042 (status open)"}, degraded=None,
        table_iv="At most one ticket; every retry reuses the same Idempotency-Key.",
        effects="at most one ticket_created per customer_id; all attempts of one ticket carry the same Idempotency-Key (or there is a single attempt)",
        unsafe_effect="ticket_created",
    ),
    # ------------------------------------------------------------- BACKGROUND
    dict(
        id="B5", title="Fetch the shipment status updates of a carrier for a nightly sync", group="background", method="GET",
        context="Batch job, 30 s limit", func="fetch_shipment_updates",
        params=[("base_url", "str"), ("carrier_id", "str"), ("since", "str")], returns="objects",
        error="ShipmentUpdates", java_class="ShipmentUpdatesClient", time_limit_s=30, deps={"A": "carrier API"},
        description=["It fetches the shipment status updates that the carrier reported after {p:since} (an RFC 3339 time) and",
                     "returns the list of updates (the \"updates\" array of the response). It runs as a nightly batch job with",
                     "a time limit of 30 s: it must {ROR} within 30 s. {RAISE:ShipmentUpdates} if the updates cannot be fetched."],
        api=[dict(dep="A", line="GET {base_url}/v1/carriers/{carrier_id}/shipment-updates?since={since}",
                  codes="200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by updated_at, at most 100 per response; next_since is the updated_at of the last update. 400: invalid since. 404: carrier not found.")],
        warmup=["{A}", "car-000", CONFIRM_SINCE], single=["{A}", "car-042", CONFIRM_SINCE],
        s7=[["{A}", f"car-{100 + i:03d}", CONFIRM_SINCE] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/carriers/{carrier_id}/shipment-updates (every request; a request with another since is another logical call)",
        logical_key="carrier_id + since",
        mock=["Every carrier car-NNN has 25 updates shp-NNN-001 … shp-NNN-025 with updated_at 2026-03-01T00:17Z, 00:34Z, … (k·17 minutes) and status "
              "[picked_up, in_transit, out_for_delivery, delivered, exception][(NNN + k) mod 5]; a request returns those with updated_at > since "
              "(so following next_since ends with an empty page). since must be RFC 3339, else 400; any other carrier id → 404.",
              "The JSON body is about 2.3 KB (below the S4 trickle length of 4096 bytes)."],
        correct={"value": "the 25 updates of car-042 in order"}, degraded=None,
        table_iv="All updates, or an error, within 30 s (in S7, an error); never a partial list returned as complete.",
    ),
    # ---------------------------------------------------------------- HANDLER
    dict(
        id="H4", title="Show notification preferences; return the documented default if unavailable", group="handler", method="GET",
        context="Handler, 2 s limit", func="get_notification_preferences", params=[("preferences_url", "str"), ("user_id", "str")],
        returns="object", error=None, java_class="NotificationPreferences", time_limit_s=2, deps={"A": "preference service"},
        description=["It returns the user's notification preferences {\"email\": <bool>, \"sms\": <bool>, \"push\": <bool>} for the",
                     "settings page. It runs inside a web request handler and must return within 2 s. If the preferences",
                     "cannot be obtained in time, it returns the documented default {\"email\": true, \"sms\": false, \"push\": false}."],
        api=[dict(dep="A", label="preference service", line="GET {preferences_url}/v1/users/{user_id}/notification-preferences",
                  codes="200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.")],
        warmup=["{A}", "u-000"], single=["{A}", "u-042"], s7=[["{A}", f"u-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/users/{user_id}/notification-preferences (the only request)", logical_key="user_id",
        mock=["Every user u-NNN → 200 {user_id, email: false, sms: true, push: true, updated_at: \"2026-02-20T08:00:00Z\"} "
              "(the opposite of the default in every field, so the default is distinguishable); any other id → 404."],
        correct={"value": H4_REAL}, degraded={"value": H4_DEFAULT},
        table_iv="The documented default within 2 s; recovering the real preferences is also correct.",
    ),
]
