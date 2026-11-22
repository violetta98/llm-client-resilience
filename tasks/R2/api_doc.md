# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/products?q={query}&category={category}&max_price={max_price}
  200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/products?q={query}&category={category}&max_price={maxPrice}
  200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/products?q={query}&category={category}&max_price={maxPrice}
  200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/products?q={query}&category={category}&max_price={maxPrice}
  200: JSON {items: [{id, name, category, price}], total}. 400: invalid parameters.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
