"""The three PILOT tasks (brief E5; draft Section V-E: "The pilot used three
tasks outside the benchmark").

They are rendered with exactly the same templates, operational lines and
offered-library lines as the benchmark tasks (tasks/generate.py --pilot ->
pilot/tasks/<ID>/), so the pilot exercises the real pipeline. They cover one
read, one write without idempotency support (S8) and one handler with a time
limit and a documented default, in domains not used by any benchmark task.
Pilot data stay in data/pilot/ and never enter the main analysis.
"""
from catalog import IDEM_NO

PILOT_TASKS = [
    dict(
        id="P1", title="Fetch an exchange rate", group="read", method="GET", context="Standalone function",
        func="get_exchange_rate", params=[("base_url", "str"), ("base_currency", "str"), ("quote_currency", "str")],
        returns="object", error="Rate", java_class="ExchangeRateClient", time_limit_s=None, deps={"A": "rates service"},
        description=["It fetches the current exchange rate for the currency pair from the rates service and returns the",
                     "rate object from the response. {RAISE:Rate} if the rate cannot be fetched."],
        api=[dict(dep="A", line="GET {base_url}/v1/rates/{base_currency}/{quote_currency}",
                  codes="200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.")],
        warmup=["{A}", "EUR", "PLN"], single=["{A}", "EUR", "USD"],
        s7=[["{A}", "USD", q] for q in ["JPY", "GBP", "CHF", "SEK", "NOK", "DKK", "CZK", "HUF", "CAD", "AUD"]],
        fault_dep="A", faulted_request="GET /v1/rates/{base}/{quote} (the only request)", logical_key="currency pair",
        mock=["Every pair of codes matching [A-Z]{3} exists: rate = 0.5 + int(sha1(\"BASE/QUOTE\")[:4], 16) / 65536 rounded to "
              "4 decimals (1.0 if base = quote), as_of \"2026-03-01T12:00:00Z\"; anything else → 404."],
        correct={"value": "{base: EUR, quote: USD, rate: <mock rate>, as_of}"}, degraded=None,
        table_iv="Correct result, or an error.",
    ),
    dict(
        id="P2", title="Add a comment to a support ticket; the API has no idempotency support", group="write", method="POST",
        context="Standalone function", func="add_ticket_comment", params=[("base_url", "str"), ("ticket_id", "str"), ("text", "str")],
        returns="str", error="Comment", java_class="TicketClient", time_limit_s=None, deps={"A": "helpdesk API"},
        description=["It adds the comment {p:text} to the support ticket and returns the comment ID from the response.",
                     "{RAISE:Comment} if the comment cannot be added."],
        api=[dict(dep="A", line="POST {base_url}/v1/tickets/{ticket_id}/comments, JSON body {text}",
                  codes="201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.",
                  idem=IDEM_NO)],
        warmup=["{A}", "t-000", "warm-up"], single=["{A}", "t-042", "The replacement part was shipped today."],
        s7=[["{A}", f"t-{100 + i:03d}", "The replacement part was shipped today."] for i in range(10)],
        fault_dep="A", faulted_request="POST /v1/tickets/{id}/comments", logical_key="ticket_id",
        mock=["Tickets t-000 … t-999 exist. Every accepted request adds one comment: effect comment_created; "
              "response 201 {id: cmt_<n>, ticket_id, created_at: \"2026-03-01T12:00:00Z\"}. Empty text → 400."],
        correct={"value": "a comment id cmt_<n>"}, degraded=None,
        table_iv="At most one comment; an error when the outcome is unknown (S8).",
        effects="at most one comment_created per ticket",
        s8_error_only=True, unsafe_effect="comment_created",
    ),
    dict(
        id="P3", title="Show a delivery estimate; return the documented default if unavailable", group="handler", method="GET",
        context="Handler, 2 s limit", func="estimate_delivery_days", params=[("shipping_url", "str"), ("postal_code", "str")],
        returns="int", error=None, java_class="DeliveryEstimates", time_limit_s=2, deps={"A": "shipping service"},
        description=["It returns the estimated number of delivery days for the postal code, shown on a checkout page.",
                     "It runs inside a web request handler and must return within 2 s. If the estimate cannot be",
                     "obtained in time, it returns 5, the documented default."],
        api=[dict(dep="A", label="shipping service", line="GET {shipping_url}/v1/estimates?postal_code={postal_code}",
                  codes="200: JSON {postal_code, days}. 404: unknown postal code.")],
        warmup=["{A}", "00-000"], single=["{A}", "30-042"], s7=[["{A}", f"30-{100 + i:03d}"] for i in range(10)],
        fault_dep="A", faulted_request="GET /v1/estimates (the only request)", logical_key="postal_code",
        mock=["Every postal code matching NN-NNN → 200 {postal_code, days: 2} (so the default 5 is distinguishable); else 404."],
        correct={"value": 2}, degraded={"value": 5},
        table_iv="The default (5) within 2 s.",
    ),
]
