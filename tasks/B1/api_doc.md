# API documentation excerpt shown to the models

## python

```
API: PUT {base_url}/v1/records/{id}, JSON body: the record
  200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record.
  The API allows 10 requests per second per client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: PUT {baseUrl}/v1/records/{id}, JSON body: the record
  200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record.
  The API allows 10 requests per second per client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: PUT {baseUrl}/v1/records/{id}, JSON body: the record
  200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record.
  The API allows 10 requests per second per client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: PUT {baseURL}/v1/records/{id}, JSON body: the record
  200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record.
  The API allows 10 requests per second per client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
