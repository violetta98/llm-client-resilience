# API documentation excerpt shown to the models

## python

```
API (each supplier): GET {supplier_url}/v1/quotes?sku={sku}
  200: JSON {supplier, sku, price, currency}. 404: unknown SKU.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (each supplier): GET {supplier_url}/v1/quotes?sku={sku}
  200: JSON {supplier, sku, price, currency}. 404: unknown SKU.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (each supplier): GET {supplier_url}/v1/quotes?sku={sku}
  200: JSON {supplier, sku, price, currency}. 404: unknown SKU.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (each supplier): GET {supplier_url}/v1/quotes?sku={sku}
  200: JSON {supplier, sku, price, currency}. 404: unknown SKU.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
