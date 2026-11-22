# API documentation excerpt shown to the models

## python

```
API: GET {base_url}/v1/reports/{report_id}/download
  200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: GET {baseUrl}/v1/reports/{reportId}/download
  200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: GET {baseUrl}/v1/reports/{reportId}/download
  200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: GET {baseURL}/v1/reports/{reportID}/download
  200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
