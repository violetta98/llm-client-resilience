# API documentation excerpt shown to the models

## python

```
API (authorization server): POST {auth_url}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…
  200: JSON {access_token, token_type: "Bearer", expires_in}. 401: invalid client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (accounts API): GET {api_url}/v1/accounts/{account_id}/balance, header Authorization: Bearer <access_token>
  200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API (authorization server): POST {authUrl}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…
  200: JSON {access_token, token_type: "Bearer", expires_in}. 401: invalid client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (accounts API): GET {apiUrl}/v1/accounts/{accountId}/balance, header Authorization: Bearer <access_token>
  200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API (authorization server): POST {authUrl}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…
  200: JSON {access_token, token_type: "Bearer", expires_in}. 401: invalid client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (accounts API): GET {apiUrl}/v1/accounts/{accountId}/balance, header Authorization: Bearer <access_token>
  200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API (authorization server): POST {authURL}/oauth/token, form body grant_type=client_credentials&client_id=…&client_secret=…
  200: JSON {access_token, token_type: "Bearer", expires_in}. 401: invalid client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (accounts API): GET {apiURL}/v1/accounts/{accountID}/balance, header Authorization: Bearer <access_token>
  200: JSON {account_id, balance, currency}. 401: missing, invalid or expired token. 404: account
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
