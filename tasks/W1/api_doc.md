# API documentation excerpt shown to the models

## python

```
API: POST {base_url}/v1/payments, JSON body {order_id, amount, currency}
  201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422:
  the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one payment.
```

## typescript

```
API: POST {baseUrl}/v1/payments, JSON body {order_id, amount, currency}
  201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422:
  the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one payment.
```

## java

```
API: POST {baseUrl}/v1/payments, JSON body {order_id, amount, currency}
  201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422:
  the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one payment.
```

## go

```
API: POST {baseURL}/v1/payments, JSON body {order_id, amount, currency}
  201: payment created, JSON {id, order_id, amount, currency, status}. 400: invalid request. 422:
  the Idempotency-Key was already used with a different body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint accepts an Idempotency-Key header; requests with the same key within 24 h create at
  most one payment.
```
