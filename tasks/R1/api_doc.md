# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/users/{user_id}
  200: the profile, JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/users/{userId}
  200: the profile, JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/users/{userId}
  200: the profile, JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/users/{userID}
  200: the profile, JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
