"""Single source of truth for the 16 benchmark tasks (draft Tables II and IV).

`python3 tasks/generate.py` renders, per task: spec.md, api_doc.md (the excerpt
shown to models, per language), signature.json, expected.yaml, and the prompts
for C0/C1/C2 x 4 languages. The operational lines are module constants, so
they are worded identically in every task.

Status: frozen with protocol v1 (E6).
"""

# --- operational lines (identical in every task; draft Section IV-B) ---------
OPS = ["429: rate limited, see Retry-After. 503: temporarily unavailable.",
       "Typical latency 150 ms, p99 800 ms."]
IDEM_YES = "The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at most one {thing}."
IDEM_NO = "The endpoint does not support idempotency keys."

LANGS = ["python", "typescript", "java", "go"]

# Offered libraries per language (draft Section IV-B; Java JSON libraries: DEVIATIONS D10).
AVAILABLE = {
    "python": "Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.",
    "typescript": "Node.js 26 (built-in fetch), axios, got, ky, p-retry.",
    "java": "Java 25 standard library (java.net.http.HttpClient), OkHttp, Apache HttpClient 5, Resilience4j, Jackson, Gson.",
    "go": "Go 1.27 standard library (net/http), resty, go-retryablehttp, cenkalti/backoff.",
}
OPENER = {
    "python": "Write a Python function:",
    "typescript": "Write a TypeScript function (Node.js 26, ES module):",
    "java": "Write a Java method in a public class {cls}:",
    "go": "Write a Go function:",
}

# Condition texts (draft Table VII). Inserted after "Available: ..." and before the final line.
C1_TEXT = "The code will run in production; make it robust."
C2_TEXT = ("Requirements:\n"
           "- Every call of the function finishes within the stated time limit, or within 10 s if none is stated.\n"
           "- Transient failures are retried with capped exponential backoff and jitter.\n"
           "- Retry-After is respected.\n"
           "- A request that may already have been processed is repeated only if it is idempotent (GET, PUT, DELETE) or carries an idempotency key; "
           "429, 503 and a refused connection mean it was not processed.")
FINAL = "Respond with the complete code in a single code block."

SCEN_ALL = ["S0", "S1", "S2", "S3", "S4", "S5a", "S5b", "S6a", "S6b", "S7", "S9"]
SCEN_WRITE = SCEN_ALL[:10] + ["S8", "S9"]
FAULTS = [s for s in SCEN_ALL if s != "S0"] + ["S8"]

# Value types: str, float, list[str], event (JSON object), records (list of JSON objects)
# Return types: object, objects, bool, str, int, none


def recs(prefix):
    return [{"id": f"rec-{prefix}-{i:02d}", "name": f"Record {i}", "value": i * 10} for i in range(1, 21)]


def event(eid):
    return {"id": eid, "type": "invoice.paid", "created_at": "2026-03-01T12:00:00Z",
            "data": {"invoice_id": "inv_" + eid.split("_")[-1], "amount": "120.00", "currency": "EUR"}}


TASKS = [
    # ------------------------------------------------------------------ READ
    dict(
        id="R1", title="Fetch a user profile", group="read", method="GET", context="Standalone function",
        func="get_user_profile", params=[("base_url", "str"), ("user_id", "str")], returns="object",
        error="Profile", java_class="UserProfileClient", time_limit_s=None, deps={"A": "user service"},
        description=["It fetches the profile of the user with the given ID from the user service and returns",
                     "the profile object from the response. {RAISE:Profile} if the profile cannot be fetched."],
        api=[dict(dep="A", line="GET {base_url}/v1/users/{user_id}",
                  codes="200: the profile, JSON {id, name, email, created_at}. 404: user not found.")],
        warmup=["{A}", "u-000"], single=["{A}", "u-042"], s7=[["{A}", f"u-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/users/{user_id} (the only request)", logical_key="user_id",
        mock=["Users u-000 … u-999 exist: {id, name: \"User NNN\", email: \"userNNN@example.com\", created_at: \"2024-01-15T09:30:00Z\"}; any other id → 404."],
        correct={"value": {"id": "u-042", "name": "User 042", "email": "user042@example.com", "created_at": "2024-01-15T09:30:00Z"}},
        degraded=None,
        table_iv="Correct result, or an error.",
    ),
    dict(
        id="R2", title="Search products with query parameters", group="read", method="GET", context="Standalone function",
        func="search_products", params=[("base_url", "str"), ("query", "str"), ("category", "str"), ("max_price", "float")],
        returns="objects", error="Search", java_class="ProductSearchClient", time_limit_s=None, deps={"A": "catalog service"},
        description=["It searches the product catalog and returns the list of matching products (the \"items\" array",
                     "of the response). {RAISE:Search} if the search cannot be performed."],
        api=[dict(dep="A", line="GET {base_url}/v1/products?q={query}&category={category}&max_price={max_price}",
                  codes="200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.")],
        warmup=["{A}", "desk lamp", "home", 50.0], single=["{A}", "running shoes", "sports", 120.0],
        s7=[["{A}", q, "sports", 120.0] for q in ["trail shoes", "road shoes", "tennis shoes", "hiking boots", "rain jacket",
                                                  "wool socks", "sports bag", "water bottle", "yoga mat", "bike helmet"]],
        fault_dep="A", faulted_request="GET /v1/products (the only request)", logical_key="query string (q, category, max_price)",
        mock=["Requires q (non-empty), category, max_price (a number); otherwise 400.",
              "Returns 3 items with ids p-<sha1(q|category)[:6]>-1..3, name \"<Q> <n>\" (q title-cased), the given category, "
              "prices max_price × 0.5, 0.7, 0.9 rounded to 2 decimals; total = 3. Query values must be URL-decoded correctly "
              "(\"running shoes\" with a space)."],
        correct={"value": "3 items as defined in mock data for (\"running shoes\", \"sports\", 120.0)"},
        degraded=None, table_iv="Correct result, or an error.",
    ),
    dict(
        id="R3", title="Download a report file and save it", group="read", method="GET (streamed body)", context="Standalone function",
        func="download_report", params=[("base_url", "str"), ("report_id", "str"), ("dest_path", "str")], returns="int",
        error="Download", java_class="ReportDownloader", time_limit_s=None, deps={"A": "reporting service"},
        description=["It downloads the report file and saves it to {p:dest_path}, and returns the number of bytes written.",
                     "{RAISE:Download} if the report cannot be downloaded."],
        api=[dict(dep="A", line="GET {base_url}/v1/reports/{report_id}/download",
                  codes="200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report not found.")],
        warmup=["{A}", "rep-000", "/tmp/rep-000.bin"], single=["{A}", "rep-042", "/tmp/rep-042.bin"],
        s7=[["{A}", f"rep-{100 + i:03d}", f"/tmp/rep-{100 + i:03d}.bin"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/reports/{id}/download (the only request)", logical_key="report_id",
        mock=["Reports rep-000 … rep-999 exist; content: 65,536 bytes, deterministic (SHA-256 counter stream seeded with the id); "
              "Content-Type application/octet-stream; Content-Length set.",
              "In S4 the trickled body has Content-Length 4096 (draft Table III)."],
        correct={"value": 65536, "file": "dest_path contains exactly the 65,536-byte content"},
        degraded=None,
        table_iv="Correct result, or an error; never a partial file reported as complete (a returned value with a missing, short or wrong file is a silent failure).",
        notes=["The driver records size and SHA-256 of dest_path after the function returns (implemented in E3)."],
    ),
    dict(
        id="R4", title="List all orders across pages", group="read", method="GET (paginated)", context="Standalone function",
        func="list_all_orders", params=[("base_url", "str"), ("customer_id", "str")], returns="objects",
        error="Orders", java_class="OrderClient", time_limit_s=None, deps={"A": "order service"},
        description=["It returns all orders of the customer, following the pagination until the last page.",
                     "{RAISE:Orders} if the orders cannot be listed."],
        api=[dict(dep="A", line="GET {base_url}/v1/customers/{customer_id}/orders?cursor={cursor}",
                  codes="200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor for the first page; next_cursor is null on the last page. 404: customer not found.")],
        warmup=["{A}", "c-000"], single=["{A}", "c-042"], s7=[["{A}", f"c-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="the request for the second page (cursor of page 2)", logical_key="customer_id + cursor (one page)",
        mock=["Every customer c-NNN has 120 orders o-NNN-001 … o-NNN-120 (pages of 50, 50, 20); cursors are opaque strings "
              "(\"pg2.<hash>\", \"pg3.<hash>\"); an unknown cursor → 400."],
        correct={"value": "the 120 orders in order"},
        degraded=None, table_iv="All orders, or an error; never a partial list returned as complete.",
    ),
    dict(
        id="R5", title="Read a feature flag; return the documented default if the service fails", group="read", method="GET",
        context="Standalone function", func="is_feature_enabled", params=[("base_url", "str"), ("flag_key", "str")],
        returns="bool", error=None, java_class="FeatureFlags", time_limit_s=None, deps={"A": "feature-flag service"},
        description=["It returns whether the feature flag is enabled. If the flag service fails or cannot be reached,",
                     "it returns {FALSE}, the documented default for every flag."],
        api=[dict(dep="A", line="GET {base_url}/v1/flags/{flag_key}",
                  codes="200: JSON {key, enabled}. 404: unknown flag.")],
        warmup=["{A}", "flag-warmup"], single=["{A}", "new-checkout"], s7=[["{A}", f"flag-{i:02d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/flags/{key} (the only request)", logical_key="flag_key",
        mock=["Every flag key matching [a-z0-9-]+ exists and is enabled (enabled: true), so the default (false) is distinguishable from a real value."],
        correct={"value": True}, degraded={"value": False},
        table_iv="The documented default value (false); recovering the real value (true) is also correct.",
    ),
    # ------------------------------------------------------------------ WRITE
    dict(
        id="W1", title="Create a payment; the API accepts Idempotency-Key", group="write", method="POST", context="Standalone function",
        func="create_payment", params=[("base_url", "str"), ("order_id", "str"), ("amount", "str"), ("currency", "str")],
        returns="object", error="Payment", java_class="PaymentClient", time_limit_s=None, deps={"A": "payment provider"},
        description=["It creates a payment with the payment provider and returns the payment object from the response.",
                     "{RAISE:Payment} if the payment cannot be created."],
        api=[dict(dep="A", line="POST {base_url}/v1/payments, JSON body {order_id, amount, currency}",
                  codes="201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422: the Idempotency-Key was already used with a different body.",
                  idem=IDEM_YES.format(thing="payment"))],
        warmup=["{A}", "ord-000", "10.00", "EUR"], single=["{A}", "ord-042", "49.90", "EUR"],
        s7=[["{A}", f"ord-{100 + i:03d}", "49.90", "EUR"] for i in range(10)],
        fault_dep="A", faulted_request="POST /v1/payments", logical_key="order_id (body)",
        mock=["Creates payment pay_<n> {id, order_id, amount, currency, status: \"succeeded\"}; effect payment_created.",
              "With an Idempotency-Key seen before (same body): no new payment, the stored response is replayed (201, same id). Same key, different body → 422.",
              "Without a key every request creates a payment."],
        correct={"value": "the payment object for ord-042 (status succeeded)"}, degraded=None,
        table_iv="At most one payment; every retry reuses the same Idempotency-Key.",
        effects="at most one payment_created per order_id; all attempts of one order carry the same Idempotency-Key (or there is a single attempt)",
    ),
    dict(
        id="W2", title="Send an SMS; the API has no idempotency support", group="write", method="POST", context="Standalone function",
        func="send_sms", params=[("base_url", "str"), ("to", "str"), ("body", "str")], returns="str",
        error="Sms", java_class="SmsClient", time_limit_s=None, deps={"A": "SMS gateway"},
        description=["It sends an SMS through the SMS gateway and returns the message ID from the response.",
                     "{RAISE:Sms} if the message cannot be sent."],
        api=[dict(dep="A", line="POST {base_url}/v1/messages, JSON body {to, body}",
                  codes="202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.",
                  idem=IDEM_NO)],
        warmup=["{A}", "+48500000000", "warm-up"], single=["{A}", "+48500100042", "Your code is 421337"],
        s7=[["{A}", f"+48500100{100 + i:03d}", "Your code is 421337"] for i in range(10)],
        fault_dep="A", faulted_request="POST /v1/messages", logical_key="(to, body)",
        mock=["Every accepted request sends one SMS: effect sms_sent; response 202 {id: msg_<n>, status: \"queued\"}. "
              "`to` must match ^\\+[0-9]{8,15}$ and body must be non-empty, else 400."],
        correct={"value": "a message id msg_<n>"}, degraded=None,
        table_iv="At most one SMS; an error when the outcome is unknown (S8).",
        effects="at most one sms_sent per (to, body)",
    ),
    dict(
        id="W3", title="Upload a document to a fixed path", group="write", method="PUT", context="Standalone function",
        func="upload_document", params=[("base_url", "str"), ("doc_id", "str"), ("content", "str")], returns="object",
        error="Upload", java_class="DocumentClient", time_limit_s=None, deps={"A": "document store"},
        description=["It uploads the text {p:content} as the document {p:doc_id} (UTF-8) and returns the document metadata",
                     "from the response. {RAISE:Upload} if the document cannot be uploaded."],
        api=[dict(dep="A", line="PUT {base_url}/v1/documents/{doc_id}, body: the content (Content-Type: text/plain; charset=utf-8)",
                  codes="200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document. 400: empty body.")],
        warmup=["{A}", "doc-000", "warm-up"], single=["{A}", "doc-042", "Quarterly summary\n" + "Revenue grew in every region.\n" * 64],
        s7=[["{A}", f"doc-{100 + i:03d}", f"Document {i}\n" + "Line of text.\n" * 64] for i in range(10)],
        fault_dep="A", faulted_request="PUT /v1/documents/{doc_id}", logical_key="doc_id",
        mock=["Stores the body as the new version (version increments on every PUT); effect document_written; response 200 {id, size, sha256, version}."],
        correct={"value": "metadata with size and sha256 of the UTF-8 content"}, degraded=None,
        table_iv="Success or an error; retries are safe.",
        effects="the final stored content equals the given content if the function returned",
    ),
    dict(
        id="W4", title="Cancel a subscription", group="write", method="DELETE", context="Standalone function",
        func="cancel_subscription", params=[("base_url", "str"), ("subscription_id", "str")], returns="none",
        error="Subscription", java_class="SubscriptionClient", time_limit_s=None, deps={"A": "billing service"},
        description=["It cancels the subscription. {RAISE:Subscription} if the subscription cannot be canceled."],
        api=[dict(dep="A", line="DELETE {base_url}/v1/subscriptions/{subscription_id}",
                  codes="200: canceled, JSON {id, status}. 404: subscription not found or already canceled.")],
        warmup=["{A}", "sub-000"], single=["{A}", "sub-042"], s7=[["{A}", f"sub-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="DELETE /v1/subscriptions/{id}", logical_key="subscription_id",
        mock=["Every sub-NNN is active at the start of the run; the first DELETE cancels it (effect subscription_canceled, 200); later DELETEs → 404."],
        correct={"value": "returns normally; subscription canceled"}, degraded=None,
        table_iv="Success or an error; retries are safe, and a 404 after a retried DELETE counts as success.",
        effects="the subscription is canceled if the function returned",
    ),
    # ------------------------------------------------------------- BACKGROUND
    dict(
        id="B1", title="Sync 20 records to a rate-limited API", group="background", method="PUT per record", context="Batch job, 30 s limit",
        func="sync_records", params=[("base_url", "str"), ("records", "records")], returns="int",
        error="Sync", java_class="RecordSync", time_limit_s=30, deps={"A": "records API"},
        description=["It writes every record to the records API (one PUT per record, in any order) and returns the",
                     "number of records written. The function runs as a batch job with a time limit of 30 s: it must",
                     "{ROR} within 30 s. {RAISE:Sync} if not all records can be written."],
        api=[dict(dep="A", line="PUT {base_url}/v1/records/{id}, JSON body: the record",
                  codes="200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record. The API allows 10 requests per second per client.")],
        warmup=["{A}", recs("w00")[:3]], single=["{A}", recs("a42")], s7=[["{A}", recs(f"b{i:02d}")] for i in range(10)],
        fault_dep="A", faulted_request="the PUT of the fifth record (rec-*-05); S1, S2, S9 affect every request",
        logical_key="record id",
        mock=["Stores each record (effect record_written; last write wins). Rate limit: token bucket of 10 requests/s with a burst of 10 per record-id prefix "
              "(one invocation); excess requests → 429 with Retry-After: 1 (in every scenario, including S0)."],
        correct={"value": 20, "state": "all 20 records stored"}, degraded=None,
        table_iv="All records, or an error, within 30 s; no record skipped silently.",
        effects="if the function returned, all 20 records are stored",
    ),
    dict(
        id="B2", title="Poll an export job until it completes", group="background", method="GET (polling)", context="Batch job, 30 s limit",
        func="wait_for_export", params=[("base_url", "str"), ("export_id", "str")], returns="str",
        error="Export", java_class="ExportWaiter", time_limit_s=30, deps={"A": "export service"},
        description=["The export job was already started. The function waits until the export completes and returns its",
                     "result_url. It runs as a batch job with a time limit of 30 s: it must {ROR} within 30 s.",
                     "{RAISE:Export} if the export fails or does not complete in time."],
        api=[dict(dep="A", line="GET {base_url}/v1/exports/{export_id}",
                  codes="200: JSON {id, status, result_url}; status is \"running\", \"completed\" or \"failed\"; result_url is set when completed. 404: export not found. Exports usually complete within 5 s.")],
        warmup=["{A}", "exp-000"], single=["{A}", "exp-042"], s7=[["{A}", f"exp-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="status requests after the first one (S3/S4: from the 2nd on; S5: the 2nd and 3rd → 503; S6: the 2nd → 429; S8 n/a)",
        logical_key="export_id (one logical call = waiting for the export)",
        mock=["Status is \"running\" until 3 s after the first status request of that export, then \"completed\" with result_url "
              "https://files.example.com/exports/<id>.csv."],
        correct={"value": "https://files.example.com/exports/exp-042.csv"}, degraded=None,
        table_iv="The export result, or an error, within 30 s (in S7, an error).",
    ),
    dict(
        id="B3", title="Obtain an access token and call an API with it", group="background", method="POST + GET", context="Batch job, 30 s limit",
        func="get_account_balance",
        params=[("auth_url", "str"), ("api_url", "str"), ("client_id", "str"), ("client_secret", "str"), ("account_id", "str")],
        returns="object", error="Balance", java_class="BalanceClient", time_limit_s=30, deps={"A": "authorization server", "B": "accounts API"},
        description=["It obtains an access token with the client credentials and uses it to fetch the balance of the account;",
                     "it returns the balance object from the response. It runs as a batch job with a time limit of 30 s:",
                     "it must {ROR} within 30 s. {RAISE:Balance} if the balance cannot be fetched."],
        api=[dict(dep="A", label="authorization server", line="POST {auth_url}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…",
                  codes="200: JSON {access_token, token_type: \"Bearer\", expires_in}. 401: invalid client."),
             dict(dep="B", label="accounts API", line="GET {api_url}/v1/accounts/{account_id}/balance, header Authorization: Bearer <access_token>",
                  codes="200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account not found.")],
        warmup=["{A}", "{B}", "client-1", "s3cr3t", "acc-000"], single=["{A}", "{B}", "client-1", "s3cr3t", "acc-042"],
        s7=[["{A}", "{B}", "client-1", "s3cr3t", f"acc-{100 + i:03d}"] for i in range(10)],
        fault_dep="B", faulted_request="the API call (GET balance); the token request is never faulted", logical_key="account_id",
        mock=["Token: client-1 / s3cr3t → 200 with a fresh random token (expires_in 3600); else 401. Tokens issued by any token port of the run "
              "(including the warm-up one) are valid on the accounts API, so a cached token is not an artificial failure.",
              "Balance: {account_id, balance: \"1250.00\", currency: \"EUR\"}."],
        correct={"value": {"account_id": "acc-042", "balance": "1250.00", "currency": "EUR"}}, degraded=None,
        table_iv="The result, or an error, within 30 s.",
    ),
    dict(
        id="B4", title="Deliver a webhook for a given event; the receiver deduplicates by event ID", group="background", method="POST",
        context="Worker, 30 s limit", func="deliver_webhook", params=[("endpoint_url", "str"), ("event", "event")], returns="none",
        error="Delivery", java_class="WebhookDeliverer", time_limit_s=30, deps={"A": "webhook receiver"},
        description=["It delivers the event to the customer's webhook endpoint (POST of the event as JSON). It runs in a",
                     "worker with a time limit of 30 s per event: it must {ROR} within 30 s.",
                     "{RAISE:Delivery} if the event cannot be delivered."],
        api=[dict(dep="A", label="webhook receiver", line="POST {endpoint_url}, JSON body: the event {id, type, created_at, data}",
                  codes="2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event id.")],
        warmup=["{A}/hooks/acme", event("evt_000")], single=["{A}/hooks/acme", event("evt_042")],
        s7=[["{A}/hooks/acme", event(f"evt_{100 + i:03d}")] for i in range(10)],
        fault_dep="A", faulted_request="the webhook POST", logical_key="event id (body)",
        mock=["POST /hooks/acme: 200 {received: true}; effect delivery_received on every POST, delivery_accepted once per event id "
              "(duplicates: 200 {received: true, duplicate: true}). Body must be JSON with an id, else 400."],
        correct={"value": "returns normally; event accepted once"}, degraded=None,
        table_iv="At most one delivery per event ID, or an error, within 30 s.",
        effects="at most one delivery_accepted per event id",
    ),
    # ---------------------------------------------------------------- HANDLER
    dict(
        id="H1", title="Show a profile with recommendations; omit recommendations if slow", group="handler", method="GET × 2",
        context="Handler, 2 s limit", func="get_profile_page",
        params=[("profile_url", "str"), ("recommendations_url", "str"), ("user_id", "str")], returns="object",
        error="ProfilePage", java_class="ProfilePageHandler", time_limit_s=2, deps={"A": "profile service", "B": "recommendation service"},
        description=["It builds the data for a profile page: {\"profile\": <profile>, \"recommendations\": <items>}. It runs",
                     "inside a web request handler and must return within 2 s. If the recommendations cannot be",
                     "obtained in time, it returns the profile with \"recommendations\" set to {NULL}.",
                     "{RAISE:ProfilePage} if the profile cannot be fetched."],
        api=[dict(dep="A", label="profile service", line="GET {profile_url}/v1/users/{user_id}",
                  codes="200: JSON {id, name, email, created_at}. 404: user not found."),
             dict(dep="B", label="recommendation service", line="GET {recommendations_url}/v1/users/{user_id}/recommendations",
                  codes="200: JSON {items: [{product_id, title}]}.")],
        warmup=["{A}", "{B}", "u-000"], single=["{A}", "{B}", "u-042"], s7=[["{A}", "{B}", f"u-{100 + i:03d}"] for i in range(10)],
        fault_dep="B", faulted_request="the recommendations request", logical_key="user_id (recommendations)",
        mock=["Profile as in R1. Recommendations: 3 items {product_id: p-NNN-k, title: \"Product k\"}."],
        correct={"value": "profile of u-042 and its 3 recommendations"},
        degraded={"value": "profile of u-042 with recommendations null"},
        table_iv="The profile without recommendations within 2 s.",
    ),
    dict(
        id="H2", title="Report the readiness of a dependency", group="handler", method="GET", context="Health check, 1 s limit",
        func="is_dependency_ready", params=[("dependency_url", "str")], returns="bool", error=None,
        java_class="ReadinessCheck", time_limit_s=1, deps={"A": "dependency"},
        description=["It is called by the readiness probe of a service and reports whether the dependency is ready.",
                     "It must return within 1 s. It returns {FALSE} if the dependency is not ready, fails, or does",
                     "not answer in time."],
        api=[dict(dep="A", label="dependency", line="GET {dependency_url}/healthz",
                  codes="200: JSON {status: \"ok\"}, ready. Any other response: not ready.")],
        warmup=["{A}/instances/db-00"], single=["{A}/instances/db-42"], s7=[[f"{{A}}/instances/db-{10 + i:02d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET {dependency_url}/healthz (the only request)", logical_key="instance path",
        mock=["GET /instances/<name>/healthz → 200 {status: \"ok\"}. (The instance path makes the ten S7 invocations distinguishable.)"],
        correct={"value": True}, degraded={"value": False},
        table_iv="\"Not ready\" (false) within 1 s.",
    ),
    dict(
        id="H3", title="Return the best price from three suppliers queried in parallel", group="handler", method="GET × 3",
        context="Handler, 3 s limit", func="best_price", params=[("supplier_urls", "list[str]"), ("sku", "str")], returns="object",
        error="NoQuote", java_class="PriceComparison", time_limit_s=3,
        deps={"A": "supplier 1", "B": "supplier 2", "C": "supplier 3"},
        description=["It asks every supplier for a quote, in parallel, and returns the quote with the lowest price. It runs",
                     "inside a web request handler and must return within 3 s. Suppliers that fail or do not answer",
                     "in time are ignored. {RAISE:NoQuote} if no supplier returns a quote."],
        api=[dict(dep="A", label="each supplier", line="GET {supplier_url}/v1/quotes?sku={sku}",
                  codes="200: JSON {supplier, sku, price, currency}. 404: unknown SKU.")],
        warmup=[["{A}", "{B}", "{C}"], "sku-000"], single=[["{A}", "{B}", "{C}"], "sku-042"],
        s7=[[["{A}", "{B}", "{C}"], f"sku-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="the request to supplier 1 (the cheapest)", logical_key="supplier + sku",
        mock=["Quotes for any sku: supplier 1 (port A) 9.40, supplier 2 (B) 10.10, supplier 3 (C) 11.25 EUR; {supplier: \"s1\"|\"s2\"|\"s3\", sku, price, currency}. "
              "The faulted supplier is the cheapest, so ignoring it changes the answer."],
        correct={"value": {"supplier": "s1", "sku": "sku-042", "price": 9.40, "currency": "EUR"}},
        degraded={"value": {"supplier": "s2", "sku": "sku-042", "price": 10.10, "currency": "EUR"}},
        table_iv="The best price of the other two within 3 s.",
    ),
]
