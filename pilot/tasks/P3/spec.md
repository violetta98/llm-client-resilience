# P3 — Show a delivery estimate; return the documented default if unavailable

Status: **PILOT task (outside the benchmark; brief E5).** Generated from `tasks/pilot_catalog.py`.

- Group: handler; method: GET; context: Handler, 2 s limit
- Time limit: 2 s
- Dependencies: A = shipping service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/estimates (the only request)
- Logical-call key: postal_code

## Prompt body (Python, C0)

```
Write a Python function:
  def estimate_delivery_days(shipping_url: str, postal_code: str) -> int
It returns the estimated number of delivery days for the postal code, shown on a checkout page. It
runs inside a web request handler and must return within 2 s. If the estimate cannot be obtained in
time, it returns 5, the documented default.
API (shipping service): GET {shipping_url}/v1/estimates?postal_code={postal_code}
  200: JSON {postal_code, days}. 404: unknown postal code.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def estimate_delivery_days(shipping_url: str, postal_code: str) -> int`
- typescript: `export async function estimateDeliveryDays(shippingUrl: string, postalCode: string): Promise<number>`
- java: `public static int estimateDeliveryDays(String shippingUrl, String postalCode)` (class `DeliveryEstimates`)
- go: `func EstimateDeliveryDays(shippingURL, postalCode string) int`

## Mock behavior (normal, S0)

- Every postal code matching NN-NNN → 200 {postal_code, days: 2} (so the default 5 is distinguishable); else 404.

## Correct behavior (draft Table IV)

The default (5) within 2 s.

- Correct result (S0, single call): {"value": 2}
- Degraded result: {"value": 5}
- Effects constraint: —

| Scenario | Allowed outcomes |
|---|---|
| S0 | correct |
| S1 | correct, degraded |
| S2 | correct, degraded |
| S3 | correct, degraded |
| S4 | correct, degraded |
| S5a | correct, degraded |
| S5b | correct, degraded |
| S6a | correct, degraded |
| S6b | correct, degraded |
| S7 | degraded |
| S9 | correct, degraded |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
