# R4 — List all orders across pages

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: read; method: GET (paginated); context: Standalone function
- Time limit: none stated
- Dependencies: A = order service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): the request for the second page (cursor of page 2)
- Logical-call key: customer_id + cursor (one page)

## Prompt body (Python, C0)

```
Write a Python function:
  def list_all_orders(base_url: str, customer_id: str) -> list[dict]
It returns all orders of the customer, following the pagination until the last page. Raise
OrdersError if the orders cannot be listed.
API: GET {base_url}/v1/customers/{customer_id}/orders?cursor={cursor}
  200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor
  for the first page; next_cursor is null on the last page. 404: customer not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def list_all_orders(base_url: str, customer_id: str) -> list[dict]`
- typescript: `export async function listAllOrders(baseUrl: string, customerId: string): Promise<Array<Record<string, unknown>>>`
- java: `public static List<Map<String, Object>> listAllOrders(String baseUrl, String customerId) throws OrdersException` (class `OrderClient`)
- go: `func ListAllOrders(baseURL, customerID string) ([]map[string]any, error)`

## Mock behavior (normal, S0)

- Every customer c-NNN has 120 orders o-NNN-001 … o-NNN-120 (pages of 50, 50, 20); cursors are opaque strings ("pg2.<hash>", "pg3.<hash>"); an unknown cursor → 400.

## Correct behavior (draft Table IV)

All orders, or an error; never a partial list returned as complete.

- Correct result (S0, single call): {"value": "the 120 orders in order"}
- Degraded result: — (none allowed)
- Effects constraint: —

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
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
