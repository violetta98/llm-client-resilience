# R6 — Fetch the stock levels of a product across warehouses

Status: **confirmatory replication task (added after the protocol-v1 freeze; tasks/CONFIRM_TASKS.md).** Generated from `tasks/confirm_catalog.py` (tasks/generate_confirm.py).

- Group: read; method: GET; context: Standalone function
- Time limit: none stated
- Dependencies: A = inventory service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/products/{product_id}/stock (the only request)
- Logical-call key: product_id

## Prompt body (Python, C0)

```
Write a Python function:
  def get_stock_levels(base_url: str, product_id: str) -> dict
It fetches the stock levels of the product in every warehouse from the inventory service and returns
the stock object from the response. Raise StockError if the stock levels cannot be fetched.
API: GET {base_url}/v1/products/{product_id}/stock
  200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404:
  product not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_stock_levels(base_url: str, product_id: str) -> dict`
- typescript: `export async function getStockLevels(baseUrl: string, productId: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getStockLevels(String baseUrl, String productId) throws StockException` (class `StockClient`)
- go: `func GetStockLevels(baseURL, productID string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Products prd-000 … prd-999 exist: {product_id, warehouses: 24 entries wh-01 … wh-24 with available = (NNN·37 + k·101) mod 1000 and reserved = (NNN + k·7) mod 50, updated_at: "2026-03-01T06:00:00Z"}; any other id → 404.
- The JSON body is about 1.5 KB (below the S4 trickle length of 4096 bytes, so S4 delivers the complete body, padded with leading whitespace).

## Correct behavior (draft Table IV)

Correct result, or an error.

- Correct result (S0, single call): {"value": "the stock object of prd-042 (24 warehouses) as defined in the mock data"}
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
