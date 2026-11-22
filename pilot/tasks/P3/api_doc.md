# API documentation excerpt shown to the models

## python

```
API (shipping service): GET {shipping_url}/v1/estimates?postal_code={postal_code}
  200: JSON {postal_code, days}. 404: unknown postal code.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (shipping service): GET {shippingUrl}/v1/estimates?postal_code={postalCode}
  200: JSON {postal_code, days}. 404: unknown postal code.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (shipping service): GET {shippingUrl}/v1/estimates?postal_code={postalCode}
  200: JSON {postal_code, days}. 404: unknown postal code.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (shipping service): GET {shippingURL}/v1/estimates?postal_code={postalCode}
  200: JSON {postal_code, days}. 404: unknown postal code.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
