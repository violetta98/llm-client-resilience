# H1 — Show a profile with recommendations; omit recommendations if slow

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: handler; method: GET × 2; context: Handler, 2 s limit
- Time limit: 2 s
- Dependencies: A = profile service (port 9001), B = recommendation service (port 9002)
- Faulted dependency: B; faulted request (S3–S8): the recommendations request
- Logical-call key: user_id (recommendations)

## Prompt body (Python, C0)

```
Write a Python function:
  def get_profile_page(profile_url: str, recommendations_url: str, user_id: str) -> dict
It builds the data for a profile page: {"profile": <profile>, "recommendations": <items>}. It runs
inside a web request handler and must return within 2 s. If the recommendations cannot be obtained
in time, it returns the profile with "recommendations" set to None. Raise ProfilePageError if the
profile cannot be fetched.
API (profile service): GET {profile_url}/v1/users/{user_id}
  200: JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
API (recommendation service): GET {recommendations_url}/v1/users/{user_id}/recommendations
  200: JSON {items: [{product_id, title}]}.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_profile_page(profile_url: str, recommendations_url: str, user_id: str) -> dict`
- typescript: `export async function getProfilePage(profileUrl: string, recommendationsUrl: string, userId: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getProfilePage(String profileUrl, String recommendationsUrl, String userId) throws ProfilePageException` (class `ProfilePageHandler`)
- go: `func GetProfilePage(profileURL, recommendationsURL, userID string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Profile as in R1. Recommendations: 3 items {product_id: p-NNN-k, title: "Product k"}.

## Correct behavior (draft Table IV)

The profile without recommendations within 2 s.

- Correct result (S0, single call): {"value": "profile of u-042 and its 3 recommendations"}
- Degraded result: {"value": "profile of u-042 with recommendations null"}
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
