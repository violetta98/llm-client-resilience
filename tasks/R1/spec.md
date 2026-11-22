# R1 — Fetch a user profile

Status: **frozen with protocol v1 (E6).** Generated from `tasks/catalog.py`.

- Group: read; method: GET; context: Standalone function
- Time limit: none stated
- Dependencies: A = user service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/users/{user_id} (the only request)
- Logical-call key: user_id

## Prompt body (Python, C0)

```
Write a Python function:
  def get_user_profile(base_url: str, user_id: str) -> dict
It fetches the profile of the user with the given ID from the user service and returns the profile
object from the response. Raise ProfileError if the profile cannot be fetched.
API: GET {base_url}/v1/users/{user_id}
  200: the profile, JSON {id, name, email, created_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_user_profile(base_url: str, user_id: str) -> dict`
- typescript: `export async function getUserProfile(baseUrl: string, userId: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getUserProfile(String baseUrl, String userId) throws ProfileException` (class `UserProfileClient`)
- go: `func GetUserProfile(baseURL, userID string) (map[string]any, error)`

## Mock behavior (normal, S0)

- Users u-000 … u-999 exist: {id, name: "User NNN", email: "userNNN@example.com", created_at: "2024-01-15T09:30:00Z"}; any other id → 404.

## Correct behavior (draft Table IV)

Correct result, or an error.

- Correct result (S0, single call): {"value": {"id": "u-042", "name": "User 042", "email": "user042@example.com", "created_at": "2024-01-15T09:30:00Z"}}
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
