# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/exports/{export_id}
  200: JSON {id, status, result_url}; status is "running", "completed" or "failed"; result_url is
  set when completed. 404: export not found. Exports usually complete within 5 s.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/exports/{exportId}
  200: JSON {id, status, result_url}; status is "running", "completed" or "failed"; result_url is
  set when completed. 404: export not found. Exports usually complete within 5 s.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/exports/{exportId}
  200: JSON {id, status, result_url}; status is "running", "completed" or "failed"; result_url is
  set when completed. 404: export not found. Exports usually complete within 5 s.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/exports/{exportID}
  200: JSON {id, status, result_url}; status is "running", "completed" or "failed"; result_url is
  set when completed. 404: export not found. Exports usually complete within 5 s.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
