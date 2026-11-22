import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "classify"))
from features import classify  # noqa: E402


def _test_python_requests_timeout_and_loop():
    src = ("import requests, time\n"
           "def f(u):\n"
           "    for attempt in range(3):\n"
           "        try:\n"
           "            return requests.get(u, timeout=5)\n"
           "        except requests.RequestException:\n"
           "            time.sleep(1)\n")
    r = classify(src, "python")
    assert r["library"] == "requests" and r["timeout_explicit"] == 1 and r["timeout_total"] == 1
    assert r["retry_mechanism"] == "hand_loop"


def _test_python_no_timeout_queue_get_ignored():
    src = "import requests, queue\nq = queue.Queue()\nq.get(timeout=1)\nrequests.get('http://x')\n"
    r = classify(src, "python")
    assert r["timeout_explicit"] == 0 and r["retry_mechanism"] == "none"


def _test_python_tenacity_and_adapter():
    src = ("import requests\nfrom tenacity import retry\nfrom requests.adapters import HTTPAdapter\n"
           "from urllib3.util.retry import Retry\ns = requests.Session()\n"
           "s.mount('https://', HTTPAdapter(max_retries=Retry(total=3)))\n")
    r = classify(src, "python")
    assert set(r["retry_mechanism"].split(";")) == {"retry_library", "library_builtin"}


def _test_ts_fetch_abort_signal():
    src = ("export async function f(u: string) {\n"
           "  for (let i = 0; i < 3; i++) {\n"
           "    try { return await fetch(u, { signal: AbortSignal.timeout(5000) }); }\n"
           "    catch (e) { await new Promise(r => setTimeout(r, 100)); }\n"
           "  }\n}\n")
    r = classify(src, "typescript")
    assert r["library"] == "fetch" and r["timeout_total"] == 1 and r["retry_mechanism"] == "hand_loop"


def _test_ts_ky_default_retry():
    r = classify("import ky from 'ky';\nexport const f = (u: string) => ky.get(u, { timeout: 5000 }).json();\n", "typescript")
    assert r["library"] == "ky" and r["retry_mechanism"] == "library_builtin"
    r = classify("import ky from 'ky';\nexport const f = (u: string) => ky.get(u, { retry: 0 }).json();\n", "typescript")
    assert r["retry_mechanism"] == "none" and r["timeout_explicit"] == 0


def _test_java_connect_timeout_only():
    src = ("import java.net.http.*; import java.time.Duration;\nclass A { String f() throws Exception {\n"
           "  HttpClient c = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();\n"
           "  return c.send(HttpRequest.newBuilder(java.net.URI.create(\"x\")).build(), null).body(); } }\n")
    r = classify(src, "java")
    assert r["library"] == "java.net.http" and r["timeout_explicit"] == 1 and r["timeout_total"] == 0


def _test_java_retry_wrapper():
    src = ("import java.net.http.*;\nclass A {\n static <T> T withRetry(java.util.concurrent.Callable<T> op) throws Exception {\n"
           "  int attempt = 0;\n  while (true) { try { return op.call(); } catch (Exception e) { attempt++; Thread.sleep(100L << attempt); } }\n }\n}\n")
    assert classify(src, "java")["retry_mechanism"] == "hand_loop"


def _test_go_client_timeout_and_comment_ignored():
    src = ("package main\nimport (\"net/http\"; \"time\")\n// http.Client{Timeout: 5}\n"
           "func F(u string) { c := &http.Client{Timeout: 5 * time.Second}; for i := 0; i < 3; i++ { if _, err := c.Get(u); err == nil { return }; time.Sleep(time.Second) } }\n")
    r = classify(src, "go")
    assert r["library"] == "net/http" and r["timeout_total"] == 1 and r["retry_mechanism"] == "hand_loop"
    r = classify("package main\nimport \"net/http\"\n// &http.Client{Timeout: 5}\nfunc F(u string) { http.Get(u) }\n", "go")
    assert r["timeout_explicit"] == 0


class TestClassify(unittest.TestCase):
    def test_python_requests_timeout_and_loop(self):
        _test_python_requests_timeout_and_loop()

    def test_python_no_timeout_queue_get_ignored(self):
        _test_python_no_timeout_queue_get_ignored()

    def test_python_tenacity_and_adapter(self):
        _test_python_tenacity_and_adapter()

    def test_ts_fetch_abort_signal(self):
        _test_ts_fetch_abort_signal()

    def test_ts_ky_default_retry(self):
        _test_ts_ky_default_retry()

    def test_java_connect_timeout_only(self):
        _test_java_connect_timeout_only()

    def test_java_retry_wrapper(self):
        _test_java_retry_wrapper()

    def test_go_client_timeout_and_comment_ignored(self):
        _test_go_client_timeout_and_comment_ignored()

