# API documentation excerpt shown to the models

## python

```
API: POST {base_url}/v1/messages, JSON body {to, body}
  202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## typescript

```
API: POST {baseUrl}/v1/messages, JSON body {to, body}
  202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## java

```
API: POST {baseUrl}/v1/messages, JSON body {to, body}
  202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```

## go

```
API: POST {baseURL}/v1/messages, JSON body {to, body}
  202: accepted for delivery, JSON {id, status}. 400: invalid phone number or body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
  The endpoint does not support idempotency keys.
```
