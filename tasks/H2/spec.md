# H2 — Report the readiness of a dependency

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: handler; method: GET; context: Health check, 1 s limit
- Time limit: 1 s
- Dependencies: A = dependency (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET {dependency_url}/healthz (the only request)
- Logical-call key: instance path

## Prompt body (Python, C0)

```
Write a Python function:
  def is_dependency_ready(dependency_url: str) -> bool
It is called by the readiness probe of a service and reports whether the dependency is ready. It
must return within 1 s. It returns False if the dependency is not ready, fails, or does not answer
in time.
API (dependency): GET {dependency_url}/healthz
  200: JSON {status: "ok"}, ready. Any other response: not ready.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def is_dependency_ready(dependency_url: str) -> bool`
- typescript: `export async function isDependencyReady(dependencyUrl: string): Promise<boolean>`
- java: `public static boolean isDependencyReady(String dependencyUrl)` (class `ReadinessCheck`)
- go: `func IsDependencyReady(dependencyURL string) bool`

## Mock behavior (normal, S0)

- GET /instances/<name>/healthz → 200 {status: "ok"}. (The instance path makes the ten S7 invocations distinguishable.)

## Correct behavior (draft Table IV)

"Not ready" (false) within 1 s.

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
| S7 | degraded |
| S9 | correct, degraded |

Anything else returned is a silent failure; no return within 90 s (or past the time limit + 0.25 s) is measured separately.
