# API documentation excerpt shown to the models

## python

```
API: POST {base_url}/v1/tickets/{ticket_id}/comments, JSON body {text}
  201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## typescript

```
API: POST {baseUrl}/v1/tickets/{ticketId}/comments, JSON body {text}
  201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## java

```
API: POST {baseUrl}/v1/tickets/{ticketId}/comments, JSON body {text}
  201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## go

```
API: POST {baseURL}/v1/tickets/{ticketID}/comments, JSON body {text}
  201: comment added, JSON {id, ticket_id, created_at}. 400: empty text. 404: ticket not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```
