# API documentation excerpt shown to the models

## python

```
API (profile service): GET {profile_url}/v1/users/{user_id}
  200: JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (recommendation service): GET {recommendations_url}/v1/users/{user_id}/recommendations
  200: JSON {items: [{product_id, title}]}.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (profile service): GET {profileUrl}/v1/users/{userId}
  200: JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (recommendation service): GET {recommendationsUrl}/v1/users/{userId}/recommendations
  200: JSON {items: [{product_id, title}]}.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (profile service): GET {profileUrl}/v1/users/{userId}
  200: JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (recommendation service): GET {recommendationsUrl}/v1/users/{userId}/recommendations
  200: JSON {items: [{product_id, title}]}.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (profile service): GET {profileURL}/v1/users/{userID}
  200: JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (recommendation service): GET {recommendationsURL}/v1/users/{userID}/recommendations
  200: JSON {items: [{product_id, title}]}.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
