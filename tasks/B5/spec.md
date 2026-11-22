# B5 — Fetch the shipment status updates of a carrier for a nightly sync

Status: **confirmatory replication task (added after the protocol-v1 freeze; tasks/CONFIRM_TASKS.md).** Generated from `tasks/confirm_catalog.py` (tasks/generate_confirm.py).

- Group: background; method: GET; context: Batch job, 30 s limit
- Time limit: 30 s
- Dependencies: A = carrier API (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/carriers/{carrier_id}/shipment-updates (every request; a request with another since is another logical call)
- Logical-call key: carrier_id + since

## Prompt body (Python, C0)

```
Write a Python function:
  def fetch_shipment_updates(base_url: str, carrier_id: str, since: str) -> list[dict]
It fetches the shipment status updates that the carrier reported after since (an RFC 3339 time) and
returns the list of updates (the "updates" array of the response). It runs as a nightly batch job
with a time limit of 30 s: it must return or raise within 30 s. Raise ShipmentUpdatesError if the
updates cannot be fetched.
API: GET {base_url}/v1/carriers/{carrier_id}/shipment-updates?since={since}
  200: JSON {updates: [{shipment_id, status, updated_at}], next_since}; updates are ordered by
  updated_at, at most 100 per response; next_since is the updated_at of the last update. 400:
  invalid since. 404: carrier not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def fetch_shipment_updates(base_url: str, carrier_id: str, since: str) -> list[dict]`
- typescript: `export async function fetchShipmentUpdates(baseUrl: string, carrierId: string, since: string): Promise<Array<Record<string, unknown>>>`
- java: `public static List<Map<String, Object>> fetchShipmentUpdates(String baseUrl, String carrierId, String since) throws ShipmentUpdatesException` (class `ShipmentUpdatesClient`)
- go: `func FetchShipmentUpdates(baseURL, carrierID, since string) ([]map[string]any, error)`

## Mock behavior (normal, S0)

- Every carrier car-NNN has 25 updates shp-NNN-001 … shp-NNN-025 with updated_at 2026-03-01T00:17Z, 00:34Z, … (k·17 minutes) and status [picked_up, in_transit, out_for_delivery, delivered, exception][(NNN + k) mod 5]; a request returns those with updated_at > since (so following next_since ends with an empty page). since must be RFC 3339, else 400; any other carrier id → 404.
- The JSON body is about 2.3 KB (below the S4 trickle length of 4096 bytes).

## Correct behavior (draft Table IV)

All updates, or an error, within 30 s (in S7, an error); never a partial list returned as complete.

- Correct result (S0, single call): {"value": "the 25 updates of car-042 in order"}
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
