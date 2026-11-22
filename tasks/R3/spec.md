# R3 — Download a report file and save it

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: read; method: GET (streamed body); context: Standalone function
- Time limit: none stated
- Dependencies: A = reporting service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/reports/{id}/download (the only request)
- Logical-call key: report_id

## Prompt body (Python, C0)

```
Write a Python function:
  def download_report(base_url: str, report_id: str, dest_path: str) -> int
It downloads the report file and saves it to dest_path, and returns the number of bytes written.
Raise DownloadError if the report cannot be downloaded.
API: GET {base_url}/v1/reports/{report_id}/download
  200: the file (application/octet-stream, with Content-Length; reports are under 1 MB). 404: report
  not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def download_report(base_url: str, report_id: str, dest_path: str) -> int`
- typescript: `export async function downloadReport(baseUrl: string, reportId: string, destPath: string): Promise<number>`
- java: `public static int downloadReport(String baseUrl, String reportId, String destPath) throws DownloadException` (class `ReportDownloader`)
- go: `func DownloadReport(baseURL, reportID, destPath string) (int, error)`

## Mock behavior (normal, S0)

- Reports rep-000 … rep-999 exist; content: 65,536 bytes, deterministic (SHA-256 counter stream seeded with the id); Content-Type application/octet-stream; Content-Length set.
- In S4 the trickled body has Content-Length 4096 (draft Table III).

## Correct behavior (draft Table IV)

Correct result, or an error; never a partial file reported as complete (a returned value with a missing, short or wrong file is a silent failure).

- Correct result (S0, single call): {"value": 65536, "file": "dest_path contains exactly the 65,536-byte content"}
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
| S7 | correct, error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.

## Notes
- The driver records size and SHA-256 of dest_path after the function returns (implemented in E3).
