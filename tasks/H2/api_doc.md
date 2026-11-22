# API documentation excerpt shown to the models

## python

```
API (dependency): GET {dependency_url}/healthz
  200: JSON {status: "ok"}, ready. Any other response: not ready.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (dependency): GET {dependencyUrl}/healthz
  200: JSON {status: "ok"}, ready. Any other response: not ready.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (dependency): GET {dependencyUrl}/healthz
  200: JSON {status: "ok"}, ready. Any other response: not ready.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (dependency): GET {dependencyURL}/healthz
  200: JSON {status: "ok"}, ready. Any other response: not ready.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
