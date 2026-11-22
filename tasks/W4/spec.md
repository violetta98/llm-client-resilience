# W4 — Cancel a subscription

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: write; method: DELETE; context: Standalone function
- Time limit: none stated
- Dependencies: A = billing service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): DELETE /v1/subscriptions/{id}
- Logical-call key: subscription_id

## Prompt body (Python, C0)

```
Write a Python function:
  def cancel_subscription(base_url: str, subscription_id: str) -> None
It cancels the subscription. Raise SubscriptionError if the subscription cannot be canceled.
API: DELETE {base_url}/v1/subscriptions/{subscription_id}
  200: canceled, JSON {id, status}. 404: subscription not found or already canceled.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def cancel_subscription(base_url: str, subscription_id: str) -> None`
- typescript: `export async function cancelSubscription(baseUrl: string, subscriptionId: string): Promise<void>`
- java: `public static void cancelSubscription(String baseUrl, String subscriptionId) throws SubscriptionException` (class `SubscriptionClient`)
- go: `func CancelSubscription(baseURL, subscriptionID string) error`

## Mock behavior (normal, S0)

- Every sub-NNN is active at the start of the run; the first DELETE cancels it (effect subscription_canceled, 200); later DELETEs → 404.

## Correct behavior (draft Table IV)

Success or an error; retries are safe, and a 404 after a retried DELETE counts as success.

- Correct result (S0, single call): {"value": "returns normally; subscription canceled"}
- Degraded result: — (none allowed)
- Effects constraint: the subscription is canceled if the function returned

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
