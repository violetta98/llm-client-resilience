# B4 — Deliver a webhook for a given event; the receiver deduplicates by event ID

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: background; method: POST; context: Worker, 30 s limit
- Time limit: 30 s
- Dependencies: A = webhook receiver (port 9001)
- Faulted dependency: A; faulted request (S3–S8): the webhook POST
- Logical-call key: event id (body)

## Prompt body (Python, C0)

```
Write a Python function:
  def deliver_webhook(endpoint_url: str, event: dict) -> None
It delivers the event to the customer's webhook endpoint (POST of the event as JSON). It runs in a
worker with a time limit of 30 s per event: it must return or raise within 30 s. Raise DeliveryError
if the event cannot be delivered.
API (webhook receiver): POST {endpoint_url}, JSON body: the event {id, type, created_at, data}
  2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event
  id.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def deliver_webhook(endpoint_url: str, event: dict) -> None`
- typescript: `export async function deliverWebhook(endpointUrl: string, event: Record<string, unknown>): Promise<void>`
- java: `public static void deliverWebhook(String endpointUrl, Map<String, Object> event) throws DeliveryException` (class `WebhookDeliverer`)
- go: `func DeliverWebhook(endpointURL string, event map[string]any) error`

## Mock behavior (normal, S0)

- POST /hooks/acme: 200 {received: true}; effect delivery_received on every POST, delivery_accepted once per event id (duplicates: 200 {received: true, duplicate: true}). Body must be JSON with an id, else 400.

## Correct behavior (draft Table IV)

At most one delivery per event ID, or an error, within 30 s.

- Correct result (S0, single call): {"value": "returns normally; event accepted once"}
- Degraded result: — (none allowed)
- Effects constraint: at most one delivery_accepted per event id

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
| S7 | error |
| S8 | correct, error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
