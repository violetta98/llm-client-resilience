# H4 — Show notification preferences; return the documented default if unavailable

Status: **confirmatory replication task (added after the protocol-v1 freeze; tasks/CONFIRM_TASKS.md).** Generated from `tasks/confirm_catalog.py` (tasks/generate_confirm.py).

- Group: handler; method: GET; context: Handler, 2 s limit
- Time limit: 2 s
- Dependencies: A = preference service (port 9001)
- Faulted dependency: A; faulted request (S3–S8): GET /v1/users/{user_id}/notification-preferences (the only request)
- Logical-call key: user_id

## Prompt body (Python, C0)

```
Write a Python function:
  def get_notification_preferences(preferences_url: str, user_id: str) -> dict
It returns the user's notification preferences {"email": <bool>, "sms": <bool>, "push": <bool>} for
the settings page. It runs inside a web request handler and must return within 2 s. If the
preferences cannot be obtained in time, it returns the documented default {"email": true, "sms":
false, "push": false}.
API (preference service): GET {preferences_url}/v1/users/{user_id}/notification-preferences
  200: JSON {user_id, email, sms, push, updated_at}. 404: user not found.
  429: rate limited, see Retry-After. 503: temporarily unavailable.
  Typical latency 150 ms, p99 800 ms.
Available: Python 3.13 standard library, requests, httpx, aiohttp, urllib3, tenacity, backoff.
Respond with the complete code in a single code block.
```

## Signatures

- python: `def get_notification_preferences(preferences_url: str, user_id: str) -> dict`
- typescript: `export async function getNotificationPreferences(preferencesUrl: string, userId: string): Promise<Record<string, unknown>>`
- java: `public static Map<String, Object> getNotificationPreferences(String preferencesUrl, String userId)` (class `NotificationPreferences`)
- go: `func GetNotificationPreferences(preferencesURL, userID string) map[string]any`

## Mock behavior (normal, S0)

- Every user u-NNN → 200 {user_id, email: false, sms: true, push: true, updated_at: "2026-02-20T08:00:00Z"} (the opposite of the default in every field, so the default is distinguishable); any other id → 404.

## Correct behavior (draft Table IV)

The documented default within 2 s; recovering the real preferences is also correct.

- Correct result (S0, single call): {"value": {"email": false, "sms": true, "push": true}}
- Degraded result: {"value": {"email": true, "sms": false, "push": false}}
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
