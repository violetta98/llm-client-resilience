# API documentation excerpt shown to the models

## python

```
API (preference service): GET {preferences_url}/v1/users/{user_id}/notification-preferences
  200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (preference service): GET {preferencesUrl}/v1/users/{userId}/notification-preferences
  200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (preference service): GET {preferencesUrl}/v1/users/{userId}/notification-preferences
  200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (preference service): GET {preferencesURL}/v1/users/{userID}/notification-preferences
  200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
