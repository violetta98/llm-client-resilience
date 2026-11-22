# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/products/{product_id}/stock
  200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404:
  product not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/products/{productId}/stock
  200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404:
  product not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/products/{productId}/stock
  200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404:
  product not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/products/{productID}/stock
  200: JSON {product_id, warehouses: [{warehouse_id, available, reserved}], updated_at}. 404:
  product not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
