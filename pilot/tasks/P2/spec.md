# P2 — Add a comment to a support ticket; the API has no idempotency support

Status: **PILOT task (outside the benchmark; brief E5).** Generated from `tasks/pilot_catalog.py`.

- Group: write; method: POST; context: Standalone function
- Time limit: none stated
- Dependencies: A = helpdesk API (port 9001)
- Faulted dependency: A; faulted request (S3–S8): POST /v1/tickets/{id}/comments
- Logical-call key: ticket_id

## Prompt body (Python, C0)

```
Write a Python function:
  def add_ticket_comment(base_url: str, ticket_id: str, text: str) -> str
It adds the comment text to the support ticket and returns the comment ID from the response. Raise
CommentError if the comment cannot be added.
API: POST {base_url}/v1/tickets/{ticket_id}/comments, JSON body {text}
  201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def add_ticket_comment(base_url: str, ticket_id: str, text: str) -> str`
- typescript: `export async function addTicketComment(baseUrl: string, ticketId: string, text: string): Promise<string>`
- java: `public static String addTicketComment(String baseUrl, String ticketId, String text) throws CommentException` (class `TicketClient`)
- go: `func AddTicketComment(baseURL, ticketID, text string) (string, error)`

## Mock behavior (normal, S0)

- Tickets t-000 … t-999 exist. Every accepted request adds one comment: effect comment_created; response 201 {id: cmt_<n>, ticket_id, created_at: "2026-03-01T12:00:00Z"}. Empty text → 400.

## Correct behavior (draft Table IV)

At most one comment; an error when the outcome is unknown (S8).

- Correct result (S0, single call): {"value": "a comment id cmt_<n>"}
- Degraded result: — (none allowed)
- Effects constraint: at most one comment_created per ticket

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
