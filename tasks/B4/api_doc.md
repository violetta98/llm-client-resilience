# API documentation excerpt shown to the models

## python

```
API (webhook receiver): POST {endpoint_url}, JSON body: the event {id, type, created_at, data}
  2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event
  id.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (webhook receiver): POST {endpointUrl}, JSON body: the event {id, type, created_at, data}
  2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event
  id.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (webhook receiver): POST {endpointUrl}, JSON body: the event {id, type, created_at, data}
  2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event
  id.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (webhook receiver): POST {endpointURL}, JSON body: the event {id, type, created_at, data}
  2xx: delivered. 4xx other than 429: rejected. The receiver deduplicates deliveries by the event
  id.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
