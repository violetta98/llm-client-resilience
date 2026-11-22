# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/carriers/{carrier_id}/shipment-updates?since={since}
  200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by
  updated_at, at most 100 per response; next_since is the updated_at of the last update. 400:
  invalid since. 404: carrier not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/carriers/{carrierId}/shipment-updates?since={since}
  200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by
  updated_at, at most 100 per response; next_since is the updated_at of the last update. 400:
  invalid since. 404: carrier not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/carriers/{carrierId}/shipment-updates?since={since}
  200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by
  updated_at, at most 100 per response; next_since is the updated_at of the last update. 400:
  invalid since. 404: carrier not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/carriers/{carrierID}/shipment-updates?since={since}
  200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by
  updated_at, at most 100 per response; next_since is the updated_at of the last update. 400:
  invalid since. 404: carrier not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
