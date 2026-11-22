# B1 — Sync 20 records to a rate-limited API

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: background; method: PUT per record; context: Batch job, 30 s limit
- Time limit: 30 s
- Dependencies: A = records API (port 9001)
- Faulted dependency: A; faulted request (S3–S8): the PUT of the fifth record (rec-*-05); S1, S2, S9 affect every request
- Logical-call key: record id

## Prompt body (Python, C0)

```
Write a Python function:
  def sync_records(base_url: str, records: list[dict]) -> int
It writes every record to the records API (one PUT per record, in any order) and returns the number
of records written. The function runs as a batch job with a time limit of 30 s: it must return or
raise within 30 s. Raise SyncError if not all records can be written.
API: PUT {base_url}/v1/records/{id}, JSON body: the record
  200: stored, JSON {id, version}; writing the same record again replaces it. 400: invalid record.
  The API allows 10 requests per second per client.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def sync_records(base_url: str, records: list[dict]) -> int`
- typescript: `export async function syncRecords(baseUrl: string, records: Array<Record<string, unknown>>): Promise<number>`
- java: `public static int syncRecords(String baseUrl, List<Map<String, Object>> records) throws SyncException` (class `RecordSync`)
- go: `func SyncRecords(baseURL string, records []map[string]any) (int, error)`

## Mock behavior (normal, S0)

- Stores each record (effect record_written; last write wins). Rate limit: token bucket of 10 requests/s with a burst of 10 per record-id prefix (one invocation); excess requests → 429 with Retry-After: 1 (in every scenario, including S0).

## Correct behavior (draft Table IV)

All records, or an error, within 30 s; no record skipped silently.

- Correct result (S0, single call): {"value": 20, "state": "all 20 records stored"}
- Degraded result: — (none allowed)
- Effects constraint: if the function returned, all 20 records are stored

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
| S8 | correct, error |
| S9 | correct, error |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
