# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/customers/{customer_id}/orders?cursor={cursor}
  200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor
  for the first page; next_cursor is null on the last page. 404: customer not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/customers/{customerId}/orders?cursor={cursor}
  200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor
  for the first page; next_cursor is null on the last page. 404: customer not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/customers/{customerId}/orders?cursor={cursor}
  200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor
  for the first page; next_cursor is null on the last page. 404: customer not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/customers/{customerID}/orders?cursor={cursor}
  200: JSON {orders: [{id, created_at, total}], next_cursor}; up to 50 orders per page; omit cursor
  for the first page; next_cursor is null on the last page. 404: customer not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
