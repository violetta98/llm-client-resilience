# API documentation excerpt shown to the models

## python

```
API: POST {base_url}/v1/tickets, JSON body {customer_id, subject, message}
  201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request.
  422: the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one ticket.
```

## typescript

```
API: POST {baseUrl}/v1/tickets, JSON body {customer_id, subject, message}
  201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request.
  422: the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one ticket.
```

## java

```
API: POST {baseUrl}/v1/tickets, JSON body {customer_id, subject, message}
  201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request.
  422: the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one ticket.
```

## go

```
API: POST {baseURL}/v1/tickets, JSON body {customer_id, subject, message}
  201: ticket created, JSON {id, customer_id, subject, status, created_at}. 400: invalid request.
  422: the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one ticket.
```
