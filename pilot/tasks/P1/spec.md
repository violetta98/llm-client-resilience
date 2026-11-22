# P1 — Fetch an exchange rate

Status: **PILOT task (outside the benchmark; brief E5).** Generated from `tasks/pilot_catalog.py`.

- Group: read; method: GET; context: Standalone function
- Time limit: none stated
- Dependencies: A = rates service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/rates/{base}/{quote} (the only request)
- Logical-call key: currency pair

## Prompt body (Python, C0)

```
Write a Python function:
  def get_exchange_rate(base_url: str, base_currency: str, quote_currency: str) -> dict
It fetches the current exchange rate for the currency pair from the rates service and returns the
rate object from the response. Raise RateError if the rate cannot be fetched.
API: GET {base_url}/v1/rates/{base_currency}/{quote_currency}
  200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_exchange_rate(base_url: str, base_currency: str, quote_currency: str) -> dict`
- typescript: `export async function getExchangeRate(baseUrl: string, baseCurrency: string, quoteCurrency: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getExchangeRate(String baseUrl, String baseCurrency, String quoteCurrency) throws RateException` (class `ExchangeRateClient`)
- go: `func GetExchangeRate(baseURL, baseCurrency, quoteCurrency string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Every pair of codes matching [A-Z]{3} exists: rate = 0.5 + int(sha1("BASE/QUOTE")[:4], 16) / 65536 rounded to 4 decimals (1.0 if base = quote), as_of "2026-03-01T12:00:00Z"; anything else → 404.

## Correct behavior (draft Table IV)

Correct result, or an error.

- Correct result (S0, single call): {"value": "{base: EUR, quote: USD, rate: <mock rate>, as_of}"}
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
