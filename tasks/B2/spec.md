# B2 — Poll an export job until it completes

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: background; method: GET (polling); context: Batch job, 30 s limit
- Time limit: 30 s
- Dependencies: A = export service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): status requests after the first one (S3/S4: from the 2nd on; S5: the 2nd and 3rd → 503; S6: the 2nd → 429; S8 n/a)
- Logical-call key: export_id (one logical call = waiting for the export)

## Prompt body (Python, C0)

```
Write a Python function:
  def wait_for_export(base_url: str, export_id: str) -> str
The export job was already started. The function waits until the export completes and returns its
result_url. It runs as a batch job with a time limit of 30 s: it must return or raise within 30 s.
Raise ExportError if the export fails or does not complete in time.
API: GET {base_url}/v1/exports/{export_id}
  200: JSON {id, status, result_url}; status is "running", "completed" or "failed"; result_url is
  set when completed. 404: export not found. Exports usually complete within 5 s.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def wait_for_export(base_url: str, export_id: str) -> str`
- typescript: `export async function waitForExport(baseUrl: string, exportId: string): Promise<string>`
- java: `public static String waitForExport(String baseUrl, String exportId) throws ExportException` (class `ExportWaiter`)
- go: `func WaitForExport(baseURL, exportID string) (string, error)`

## Mock behavior (normal, S0)

- Status is "running" until 3 s after the first status request of that export, then "completed" with result_url https://files.example.com/exports/<id>.csv.

## Correct behavior (draft Table IV)

The export result, or an error, within 30 s (in S7, an error).

- Correct result (S0, single call): {"value": "https://files.example.com/exports/exp-042.csv"}
- Degraded result: — (none allowed)
- Effects constraint: —

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
| S7 | error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
