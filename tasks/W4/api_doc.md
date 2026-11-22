# API documentation excerpt shown to the models

## python

```
API: DELETE {base_url}/v1/subscriptions/{subscription_id}
  200: canceled, JSON {id, status}. 404: subscription not found or already canceled.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: DELETE {baseUrl}/v1/subscriptions/{subscriptionId}
  200: canceled, JSON {id, status}. 404: subscription not found or already canceled.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: DELETE {baseUrl}/v1/subscriptions/{subscriptionId}
  200: canceled, JSON {id, status}. 404: subscription not found or already canceled.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: DELETE {baseURL}/v1/subscriptions/{subscriptionID}
  200: canceled, JSON {id, status}. 404: subscription not found or already canceled.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
