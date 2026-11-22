# W2 — Send an SMS; the API has no idempotency support

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: write; method: POST; context: Standalone function
- Time limit: none stated
- Dependencies: A = SMS gateway (port 9001)
- Faulted dependency: A; faulted request (S3–S8): POST /v1/messages
- Logical-call key: (to, body)

## Prompt body (Python, C0)

```
Write a Python function:
  def send_sms(base_url: str, to: str, body: str) -> str
It sends an SMS through the SMS gateway and returns the message ID from the response. Raise SmsError
if the message cannot be sent.
API: POST {base_url}/v1/messages, JSON body {to, body}
  202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def send_sms(base_url: str, to: str, body: str) -> str`
- typescript: `export async function sendSms(baseUrl: string, to: string, body: string): Promise<string>`
- java: `public static String sendSms(String baseUrl, String to, String body) throws SmsException` (class `SmsClient`)
- go: `func SendSms(baseURL, to, body string) (string, error)`

## Mock behavior (normal, S0)

- Every accepted request sends one SMS: effect sms_sent; response 202 {id: msg_<n>, status: "queued"}. `to` must match ^\+[0-9]{8,15}$ and body must be non-empty, else 400.

## Correct behavior (draft Table IV)

At most one SMS; an error when the outcome is unknown (S8).

- Correct result (S0, single call): {"value": "a message id msg_<n>"}
- Degraded result: — (none allowed)
- Effects constraint: at most one sms_sent per (to, body)

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
| S8 | error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
