# B3 — Obtain an access token and call an API with it

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: background; method: POST + GET; context: Batch job, 30 s limit
- Time limit: 30 s
- Dependencies: A = authorization server (port 9001), B = accounts API (port 9002)
- Faulted dependency: B; faulted request (S3–S8): the API call (GET balance); the token request is never faulted
- Logical-call key: account_id

## Prompt body (Python, C0)

```
Write a Python function:
  def get_account_balance(auth_url: str, api_url: str, client_id: str, client_secret: str, account_id: str) -> dict
It obtains an access token with the client credentials and uses it to fetch the balance of the
account; it returns the balance object from the response. It runs as a batch job with a time limit
of 30 s: it must return or raise within 30 s. Raise BalanceError if the balance cannot be fetched.
API (authorization server): POST {auth_url}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…
  200: JSON {access_token, token_type: "Bearer", expires_in}. 401: invalid client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (accounts API): GET {api_url}/v1/accounts/{account_id}/balance, header Authorization: Bearer <access_token>
  200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_account_balance(auth_url: str, api_url: str, client_id: str, client_secret: str, account_id: str) -> dict`
- typescript: `export async function getAccountBalance(authUrl: string, apiUrl: string, clientId: string, clientSecret: string, accountId: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getAccountBalance(String authUrl, String apiUrl, String clientId, String clientSecret, String accountId) throws BalanceException` (class `BalanceClient`)
- go: `func GetAccountBalance(authURL, apiURL, clientID, clientSecret, accountID string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Token: client-1 / s3cr3t → 200 with a fresh random token (expires_in 3600); else 401. Tokens issued by any token port of the run (including the warm-up one) are valid on the accounts API, so a cached token is not an artificial failure.
- Balance: {account_id, balance: "1250.00", currency: "EUR"}.

## Correct behavior (draft Table IV)

The result, or an error, within 30 s.

- Correct result (S0, single call): {"value": {"account_id": "acc-042", "balance": "1250.00", "currency": "EUR"}}
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
| S7 | error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
