# W1 — Create a payment; the API accepts Idempotency-Key

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: write; method: POST; context: Standalone function
- Time limit: none stated
- Dependencies: A = payment provider (port 9001)
- Faulted dependency: A; faulted request (S3–S8): POST /v1/payments
- Logical-call key: order_id (body)

## Prompt body (Python, C0)

```
Write a Python function:
  def create_payment(base_url: str, order_id: str, amount: str, currency: str) -> dict
It creates a payment with the payment provider and returns the payment object from the response.
Raise PaymentError if the payment cannot be created.
API: POST {base_url}/v1/payments, JSON body {order_id, amount, currency}
  201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422:
  the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one payment.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def create_payment(base_url: str, order_id: str, amount: str, currency: str) -> dict`
- typescript: `export async function createPayment(baseUrl: string, orderId: string, amount: string, currency: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> createPayment(String baseUrl, String orderId, String amount, String currency) throws PaymentException` (class `PaymentClient`)
- go: `func CreatePayment(baseURL, orderID, amount, currency string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Creates payment pay_<n> {id, order_id, amount, currency, status: "succeeded"}; effect payment_created.
- With an Idempotency-Key seen before (same body): no new payment, the stored response is replayed (201, same id). Same key, different body → 422.
- Without a key every request creates a payment.

## Correct behavior (draft Table IV)

At most one payment; every retry reuses the same Idempotency-Key.

- Correct result (S0, single call): {"value": "the payment object for ord-042 (status succeeded)"}
- Degraded result: — (none allowed)
- Effects constraint: at most one payment_created per order_id; all attempts of one order carry the same Idempotency-Key (or there is a single attempt)

| Scenario | Allowed outcomes |
|---|---|
| S0 | correct |
| S1 | correct, error |
| S2 | correct, error |
| S3 | correct, error |
| S4 | correct, error |
| S5a | correct, error |
| S5b | correct, error |
| S6a | correct, error |
| S6b | correct, error |
| S7 | correct, error |
| S8 | correct, error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
