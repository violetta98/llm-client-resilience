# API documentation excerpt shown to the models

## python

```
API: PUT {base_url}/v1/documents/{doc_id}, body: the content (Content-Type: text/plain; charset=utf-8)
  200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document.
  400: empty body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## typescript

```
API: PUT {baseUrl}/v1/documents/{docId}, body: the content (Content-Type: text/plain; charset=utf-8)
  200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document.
  400: empty body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## java

```
API: PUT {baseUrl}/v1/documents/{docId}, body: the content (Content-Type: text/plain; charset=utf-8)
  200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document.
  400: empty body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```

## go

```
API: PUT {baseURL}/v1/documents/{docID}, body: the content (Content-Type: text/plain; charset=utf-8)
  200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document.
  400: empty body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
```
