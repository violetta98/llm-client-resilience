# H3 — Return the best price from three suppliers queried in parallel

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: handler; method: GET × 3; context: Handler, 3 s limit
- Time limit: 3 s
- Dependencies: A = supplier 1 (port 9001), B = supplier 2 (port 9002), C = supplier 3 (port 9003)
- Faulted dependency: A; faulted request (S3–S8): the request to supplier 1 (the cheapest)
- Logical-call key: supplier + sku

## Prompt body (Python, C0)

```
Write a Python function:
  def best_price(supplier_urls: list[str], sku: str) -> dict
It asks every supplier for a quote, in parallel, and returns the quote with the lowest price. It
runs inside a web request handler and must return within 3 s. Suppliers that fail or do not answer
in time are ignored. Raise NoQuoteError if no supplier returns a quote.
API (each supplier): GET {supplier_url}/v1/quotes?sku={sku}
  200: JSON {supplier, sku, price, currency}. 404: unknown SKU.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def best_price(supplier_urls: list[str], sku: str) -> dict`
- typescript: `export async function bestPrice(supplierUrls: string[], sku: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> bestPrice(List<String> supplierUrls, String sku) throws NoQuoteException` (class `PriceComparison`)
- go: `func BestPrice(supplierURLs []string, sku string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Quotes for any sku: supplier 1 (port A) 9.40, supplier 2 (B) 10.10, supplier 3 (C) 11.25 EUR; {supplier: "s1"|"s2"|"s3", sku, price, currency}. The faulted supplier is the cheapest, so ignoring it changes the answer.

## Correct behavior (draft Table IV)

The best price of the other two within 3 s.

- Correct result (S0, single call): {"value": {"supplier": "s1", "sku": "sku-042", "price": 9.4, "currency": "EUR"}}
- Degraded result: {"value": {"supplier": "s2", "sku": "sku-042", "price": 10.1, "currency": "EUR"}}
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
