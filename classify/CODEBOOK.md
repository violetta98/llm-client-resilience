# Codebook for the manual check (E9)

The file `data/main/classify/manual_check.csv` lists 100 programs drawn at random (seed 20261106) from the `ok` programs.
Open each `solution_path`. Fill in the four `author_*` columns without consulting `features.csv`, so that the check stays blind.
Leave a cell empty if you cannot decide, and explain in `author_note`.
When all rows are filled, run `python3 classify/agreement.py`.

| Column | Values | Meaning |
|---|---|---|
| `author_library` | `requests`, `httpx`, `aiohttp`, `urllib3`, `urllib.request`, `http.client`; `fetch`, `ky`, `got`, `axios`, `undici`, `node:http`; `java.net.http`, `HttpURLConnection`, `okhttp`, `apache-httpclient5`; `net/http`, `resty`, `go-retryablehttp`. Separate several with `;` | The HTTP client(s) the solution uses to call the service. `go-retryablehttp` on top of `net/http` is written `go-retryablehttp;net/http`. Count code run in a child interpreter (`python -c`). |
| `author_timeout_explicit` | `1` / `0` | `1` if the code sets any timeout or deadline on HTTP work. This includes `timeout=`, `httpx.Timeout`, `ClientTimeout`, `AbortSignal.timeout`, `AbortController` with `setTimeout`, `HttpRequest.Builder.timeout`, `connectTimeout`, `http.Client{Timeout}`, `context.WithTimeout`, `asyncio.wait_for`, and `Future.get(t, unit)`. `timeout=None` does not count. |
| `author_timeout_total` | `1` / `0` | `1` if at least one such timeout limits waiting for the response of an attempt, not only the connect phase. A `connectTimeout` alone means `0`. |
| `author_retry_mechanism` | `none`, `hand_loop`, `retry_library`, `library_builtin`. Separate several with `;` | `hand_loop` means a loop written in the code that sends the request again. Generic wrappers such as `executeWithRetry(() -> ...)` count. `retry_library` means a retry library is used: tenacity, backoff, p-retry, async-retry, go-retryablehttp, cenkalti/backoff, resilience4j or failsafe. `library_builtin` means the HTTP client's own retries are enabled: urllib3 `Retry` or `HTTPAdapter(max_retries)`, httpx `retries=`, resty `SetRetryCount`, or ky or got with their default retry left on. A loop that only polls or pages through results, and never repeats a failed request, is not a retry. |
| `author_whole_call` | `1` / `0` | Added 2026-11-17 (DEVIATIONS D41), optional. `1` if some deadline bounds the whole function call, the response body included: for example `asyncio.timeout` / `asyncio.wait_for` around the call, aiohttp `ClientTimeout(total=...)`, `AbortSignal.timeout` or an `AbortController` timer passed to `fetch`, `Promise.race` with a timer, `Future.get(t, unit)` or `orTimeout` in Java, `context.WithTimeout` or `http.Client{Timeout}` in Go, OkHttp `callTimeout`. A per-read timeout (`timeout=(c, r)` in requests, `httpx.Timeout(read=...)`, `HttpRequest.Builder.timeout`) alone means `0`. |

## Notes after the manual check (D59, 2026-11-21; the labels were not changed)

The author's notes and the ten disagreements with the rules (`analysis/out/classify_agreement.csv`) show where this
codebook is ambiguous or where the rules fall short. For a future check:
- A retry made by recursion or by rescheduling (`schedule`, `thenCompose`) is a `hand_loop`; the rules do not detect it.
- Waiting for a worker thread with a timeout (`Future.result(t)`, `concurrent.futures.wait(t)`, `queue.get(timeout=t)`,
  `thread.join(t)`) is a whole-call deadline only if the caller then returns without waiting for the worker; a
  `with ThreadPoolExecutor(...)` block waits for it on exit, so the deadline has no effect. The rules miss
  `queue.get` and `thread.join` and count `Future.result(t)` even inside such a block.
- ky's `timeout` bounds the body only with its shortcut methods; the rules count it in every form.
- `go-retryablehttp` stays a `retry_library` and `HTTPAdapter(max_retries)` stays `library_builtin`, as above; in
  three programs the author labeled them differently.
