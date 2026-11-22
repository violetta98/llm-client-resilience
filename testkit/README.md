# faultkit: fault-injection tests for HTTP client code

A minimal, executable version of the test specification in Table 12 of the article. One file, `faultkit.py`, Python
standard library only; use it from `unittest` or `pytest`. It starts a local HTTP stub that plays one fault, runs the
function under test with a hard limit, and states the specification's assertions.

| Table 12 row | Stub (`FaultStub(...)`) | Assertion |
|---|---|---|
| Body one byte per gap (S4) | `"trickle", gap_s=0.25` | `assert_returns_within(r, deadline_s)` |
| Request read, no response (S3) | `"withhold"` | `assert_returns_within(r, deadline_s)` |
| Headers, then no body | `"headers_only"` | `assert_returns_within(r, deadline_s)` |
| 503 burst, then success (S5a) | `"status_burst", n=2` | the function returns the correct result |
| Responses delayed within the documented p99 | `"normal", delay_s=0.75` | an allowed result within the limit |
| 429 with Retry-After (S6a, S6b) | `"retry_after", ra_s=2[, date_form=True]` | `assert_no_early_retry(stub, 2)` |
| 503 for 30 s (S7) | `"outage", outage_s=30` | `assert_attempts_at_most(stub, 10, 30)` |
| Reset after the write is processed (S8) | `"reset_after_write"` | `assert_at_most_one_effect(stub)` |
| Requests after the call returned | any | `assert_no_request_after(stub, r)` |
| Refused connection (S9) | `closed_port_url()` | at most three connect calls in the first 0.5 s (see `selftest.py`) |

Use a gap of 0.25 s or less in the trickle test: a per-read timeout shorter than the gap passes the test without
bounding the call. Dropped SYNs (S1), a stalled TLS handshake (S2), DNS stalls and HTTP/2 need packet-level tools
such as Toxiproxy or a firewall rule; the article's Online Resource 1, Sect. D, describes them. The stub speaks plain
HTTP/1.1 on 127.0.0.1.

```python
from faultkit import FaultStub, call_with_limit, assert_returns_within

def test_slow_body_is_bounded():
    with FaultStub("trickle", gap_s=0.25) as stub:
        r = call_with_limit(get_user_profile, stub.url, "u-42", limit_s=15)
    assert_returns_within(r, deadline_s=10)
```

`selftest.py` runs four of the tests against the reference solution of task R1 (passes all), four mutants that each
remove one property (each fails the test that targets it), and three documentation examples (each fails the slow-body
test); result in `selftest_result.json`:

    docker run --rm --network none --entrypoint python3 -v "$PWD:/w" -w /w lcr-run-python:dev testkit/selftest.py
