# W5 — Create a support ticket; the API accepts Idempotency-Key

Status: **confirmatory replication task (added after the protocol-v1 freeze; tasks/CONFIRM_TASKS.md).** Generated from `tasks/confirm_catalog.py` (tasks/generate_confirm.py).

- Group: write; method: POST; context: Standalone function
- Time limit: none stated
- Dependencies: A = helpdesk API (port 9001)
- Faulted dependency: A; faulted request (S3–S8): POST /v1/tickets
- Logical-call key: customer_id (body)

## Prompt body (Python, C0)

```
Write a Python function:
  def create_ticket(base_url: str, customer_id: str, subject: str, message: str) -> dict
It opens a support ticket for the customer in the helpdesk and returns the ticket object from the
response. Raise TicketError if the ticket cannot be created.
API: POST {base_url}/v1/tickets, JSON body {customer_id, subject, message}
  201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request.
  422: the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one ticket.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def create_ticket(base_url: str, customer_id: str, subject: str, message: str) -> dict`
- typescript: `export async function createTicket(baseUrl: string, customerId: string, subject: string, message: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> createTicket(String baseUrl, String customerId, String subject, String message) throws TicketException` (class `SupportTicketClient`)
- go: `func CreateTicket(baseURL, customerID, subject, message string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Creates ticket tkt_<n> {id, customer_id, subject, status: "open", created_at: "2026-03-01T12:00:00Z"}; effect ticket_created. customer_id must match ^cus-[0-9]{3}$, subject and message must be non-empty, else 400.
- With an Idempotency-Key seen before (same body): no new ticket, the stored response is replayed (201, same id; effect ticket_replayed). Same key, different body → 422.
- Without a key every request creates a ticket.

## Correct behavior (draft Table IV)

At most one ticket; every retry reuses the same Idempotency-Key.

- Correct result (S0, single call): {"value": "the ticket object for cus-042 (status open)"}
- Degraded result: — (none allowed)
- Effects constraint: at most one ticket_created per customer_id; all attempts of one ticket carry the same Idempotency-Key (or there is a single attempt)

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
