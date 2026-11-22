# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/flags/{flag_key}
  200: JSON {key, enabled}. 404: unknown flag.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/flags/{flagKey}
  200: JSON {key, enabled}. 404: unknown flag.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/flags/{flagKey}
  200: JSON {key, enabled}. 404: unknown flag.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/flags/{flagKey}
  200: JSON {key, enabled}. 404: unknown flag.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
