# R5 — Read a feature flag; return the documented default if the service fails

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: read; method: GET; context: Standalone function
- Time limit: none stated
- Dependencies: A = feature-flag service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/flags/{key} (the only request)
- Logical-call key: flag_key

## Prompt body (Python, C0)

```
Write a Python function:
  def is_feature_enabled(base_url: str, flag_key: str) -> bool
It returns whether the feature flag is enabled. If the flag service fails or cannot be reached, it
returns False, the documented default for every flag.
API: GET {base_url}/v1/flags/{flag_key}
  200: JSON {key, enabled}. 404: unknown flag.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def is_feature_enabled(base_url: str, flag_key: str) -> bool`
- typescript: `export async function isFeatureEnabled(baseUrl: string, flagKey: string): Promise<boolean>`
- java: `public static boolean isFeatureEnabled(String baseUrl, String flagKey)` (class `FeatureFlags`)
- go: `func IsFeatureEnabled(baseURL, flagKey string) bool`

## Mock behavior (normal, S0)

- Every flag key matching [a-z0-9-]+ exists and is enabled (enabled: true), so the default (false) is distinguishable from a real value.

## Correct behavior (draft Table IV)

The documented default value (false); recovering the real value (true) is also correct.

- Correct result (S0, single call): {"value": true}
- Degraded result: {"value": false}
- Effects constraint: —

| Scenario | Allowed outcomes |
|---|---|
| S0 | correct |
| S1 | correct, degraded |
| S2 | correct, degraded |
| S3 | correct, degraded |
| S4 | correct, degraded |
| S5a | correct, degraded |
| S5b | correct, degraded |
| S6a | correct, degraded |
| S6b | correct, degraded |
| S7 | correct, degraded |
| S9 | correct, degraded |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
