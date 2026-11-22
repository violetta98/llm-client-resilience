# R2 — Search products with query parameters

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: read; method: GET; context: Standalone function
- Time limit: none stated
- Dependencies: A = catalog service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/products (the only request)
- Logical-call key: query string (q, category, max_price)

## Prompt body (Python, C0)

```
Write a Python function:
  def search_products(base_url: str, query: str, category: str, max_price: float) -> list[dict]
It searches the product catalog and returns the list of matching products (the "items" array of the
response). Raise SearchError if the search cannot be performed.
API: GET {base_url}/v1/products?q={query}&category={category}&max_price={max_price}
  200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def search_products(base_url: str, query: str, category: str, max_price: float) -> list[dict]`
- typescript: `export async function searchProducts(baseUrl: string, query: string, category: string, maxPrice: number): Promise<Array<Record<string, unknown>>>`
- java: `public static List<Map<String, Object>> searchProducts(String baseUrl, String query, String category, double maxPrice) throws SearchException` (class `ProductSearchClient`)
- go: `func SearchProducts(baseURL, query, category string, maxPrice float64) ([]map[string]any, error)`

## Mock behavior (normal, S0)

- Requires q (non-empty), category, max_price (a number); otherwise 400.
- Returns 3 items with ids p-<sha1(q|category)[:6]>-1..3, name "<Q> <n>" (q title-cased), the given category, prices max_price × 0.5, 0.7, 0.9 rounded to 2 decimals; total = 3. Query values must be URL-decoded correctly ("running shoes" with a space).

## Correct behavior (draft Table IV)

Correct result, or an error.

- Correct result (S0, single call): {"value": "3 items as defined in mock data for (\"running shoes\", \"sports\", 120.0)"}
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
