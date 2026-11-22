# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/rates/{base_currency}/{quote_currency}
  200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/rates/{baseCurrency}/{quoteCurrency}
  200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/rates/{baseCurrency}/{quoteCurrency}
  200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/rates/{baseCurrency}/{quoteCurrency}
  200: JSON {base, quote, rate, as_of}. 404: unknown currency pair.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
