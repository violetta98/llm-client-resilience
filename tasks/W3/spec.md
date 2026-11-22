# W3 — Upload a document to a fixed path

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: write; method: PUT; context: Standalone function
- Time limit: none stated
- Dependencies: A = document store (port 9001)
- Faulted dependency: A; faulted request (S3–S8): PUT /v1/documents/{doc_id}
- Logical-call key: doc_id

## Prompt body (Python, C0)

```
Write a Python function:
  def upload_document(base_url: str, doc_id: str, content: str) -> dict
It uploads the text content as the document doc_id (UTF-8) and returns the document metadata from
the response. Raise UploadError if the document cannot be uploaded.
API: PUT {base_url}/v1/documents/{doc_id}, body: the content (Content-Type: text/plain; charset=utf-8)
  200: stored, JSON {id, size, sha256, version}; uploading to the same path replaces the document.
  400: empty body.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def upload_document(base_url: str, doc_id: str, content: str) -> dict`
- typescript: `export async function uploadDocument(baseUrl: string, docId: string, content: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> uploadDocument(String baseUrl, String docId, String content) throws UploadException` (class `DocumentClient`)
- go: `func UploadDocument(baseURL, docID, content string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Stores the body as the new version (version increments on every PUT); effect document_written; response 200 {id, size, sha256, version}.

## Correct behavior (draft Table IV)

Success or an error; retries are safe.

- Correct result (S0, single call): {"value": "metadata with size and sha256 of the UTF-8 content"}
- Degraded result: — (none allowed)
- Effects constraint: the final stored content equals the given content if the function returned

| Scenario | Allowed outcomes |
|---|---|
| S0 | correct |
| S1 | correct, error |
| S2 | correct, error |
| S3 | correct, error |
| S4 | correct, error |
| S5a | correct, error |
| S5b | correct, error |
| S6a | correct, error |
| S6b | correct, error |
| S7 | correct, error |
| S8 | correct, error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
