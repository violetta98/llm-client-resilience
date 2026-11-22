"""Classification of generated solutions (E9, RQ3): HTTP library, explicit timeouts, retry mechanism.

  python3 classify/features.py --run main        -> data/<run>/classify/features.csv
  python3 classify/features.py --manual-sample   -> data/<run>/classify/manual_check.csv (100 programs, seed 20261106)

Python: syntax tree (ast). TypeScript, Java, Go: lexical rules on the source with comments removed
(imports, call names, option keys; loop bodies by brace matching). The code is only read, never run.

Columns
  library            HTTP client(s) used, ';'-joined (e.g. requests, httpx, fetch, java.net.http, net/http)
  timeout_explicit   1 if any explicit timeout construct is present
  timeout_constructs constructs found, ';'-joined (e.g. timeout=, httpx.Timeout, AbortSignal.timeout,
                     HttpRequest.Builder.timeout, connectTimeout, http.Client.Timeout, context.WithTimeout)
  timeout_total      1 if a construct bounds the whole request/attempt (not only connect)
  retry_mechanism    none | hand_loop | retry_library | library_builtin (';'-joined if several)
  retry_constructs   what was matched
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
KEYS = ("cond", "model", "task", "lang", "sample")
EXT = {"python": "py", "typescript": "ts", "java": "java", "go": "go"}
SEED = 20261106
COLS = list(KEYS) + ["library", "timeout_explicit", "timeout_constructs", "timeout_total", "retry_mechanism",
                     "retry_constructs"]


# ---------------------------------------------------------------- Python (AST)
PY_LIBS = {"requests": "requests", "httpx": "httpx", "aiohttp": "aiohttp", "urllib3": "urllib3",
           "urllib.request": "urllib.request", "http.client": "http.client"}
PY_RETRY_LIBS = {"tenacity", "backoff", "retrying", "retry", "stamina"}
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "request", "send", "urlopen", "stream",
                "fetch", "getresponse"}
PY_SLEEP = {"sleep", "wait"}


def _is_sleep(name):
    last = name.rsplit(".", 1)[-1].lower()
    return "sleep" in last or last in PY_SLEEP


def _dotted(n):
    parts = []
    while isinstance(n, ast.Attribute):
        parts.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name):
        parts.append(n.id)
    return ".".join(reversed(parts))


def classify_python(src, depth=0):
    f = {"library": set(), "tc": set(), "total": False, "retry": set(), "rc": set()}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return f
    # Code embedded as a string and run in a child interpreter (python -c ...): classified as well.
    if depth == 0:
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) > 200 and "import" in n.value:
                try:
                    ast.parse(n.value)
                except SyntaxError:
                    continue
                g = classify_python(n.value, depth=1)
                if g["library"]:
                    for k in ("library", "tc", "retry", "rc"):
                        f[k] |= g[k]
                    f["total"] |= g["total"]
                    f["rc"].add("code run in a child interpreter")
    alias = {}  # local name -> module/object
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                for m, lib in PY_LIBS.items():
                    if a.name == m or a.name.startswith(m + "."):
                        f["library"].add(lib)
                if a.name.split(".")[0] in PY_RETRY_LIBS:
                    f["retry"].add("retry_library"), f["rc"].add(a.name)
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                alias[a.asname or a.name] = f"{n.module}.{a.name}"
            for m, lib in PY_LIBS.items():
                if n.module == m or n.module.startswith(m + "."):
                    f["library"].add(lib)
            if n.module == "urllib" and any(a.name == "request" for a in n.names):
                f["library"].add("urllib.request")
            if n.module.split(".")[0] in PY_RETRY_LIBS:
                f["retry"].add("retry_library"), f["rc"].add(n.module)

    def full(func):
        d = _dotted(func)
        head, _, rest = d.partition(".")
        return (alias.get(head, head) + ("." + rest if rest else "")) if d else ""

    def is_http_call(c):
        if not isinstance(c, ast.Call):
            return False
        name = full(c.func)
        last = name.rsplit(".", 1)[-1]
        if any(name.startswith(m + ".") for m in ("requests", "httpx", "aiohttp", "urllib3", "urllib.request", "http.client")):
            return last in HTTP_METHODS or last in ("Request",)
        # method on a session/client object: obj.get(url, ...) with a positional or url argument
        return isinstance(c.func, ast.Attribute) and last in HTTP_METHODS and bool(c.args or any(k.arg == "url" for k in c.keywords))

    # functions that (transitively) make HTTP calls
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    httpf = set()
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name in httpf:
                continue
            for c in ast.walk(fn):
                if is_http_call(c) or (isinstance(c, ast.Call) and _dotted(c.func).rsplit(".", 1)[-1] in httpf):
                    httpf.add(name)
                    changed = True
                    break

    for c in ast.walk(tree):
        if not isinstance(c, ast.Call):
            continue
        name = full(c.func)
        last = name.rsplit(".", 1)[-1]
        for k in c.keywords:
            if k.arg == "timeout" and not (isinstance(k.value, ast.Constant) and k.value.value is None):
                if is_http_call(c) or last in ("Client", "AsyncClient", "Session", "ClientSession", "PoolManager",
                                               "HTTPConnection", "HTTPSConnection", "HTTPConnectionPool",
                                               "HTTPSConnectionPool", "Request"):
                    f["tc"].add("timeout="), _total(f, k.value)
            if k.arg in ("max_retries",) and last == "HTTPAdapter":
                f["retry"].add("library_builtin"), f["rc"].add("HTTPAdapter(max_retries)")
            if k.arg == "retries" and last in ("HTTPTransport", "AsyncHTTPTransport", "PoolManager", "urlopen", "request"):
                if not (isinstance(k.value, ast.Constant) and k.value.value in (0, False, None)):
                    f["retry"].add("library_builtin"), f["rc"].add(f"{last}(retries)")
        if last == "urlopen" and len(c.args) >= 3:
            f["tc"].add("timeout="), _total(f, c.args[2])
        if name in ("httpx.Timeout", "aiohttp.ClientTimeout", "urllib3.Timeout", "urllib3.util.Timeout",
                    "urllib3.util.timeout.Timeout"):
            f["tc"].add(name)
            if name == "aiohttp.ClientTimeout":  # D38: only a non-None `total` bounds the whole call
                tot = [k.value for k in c.keywords if k.arg == "total"] or c.args[:1]
                if tot and not (isinstance(tot[0], ast.Constant) and tot[0].value is None):
                    f["tc"].add("aiohttp.ClientTimeout(total)")
            if name.startswith("aiohttp"):
                if any(k.arg in ("total", "sock_read") for k in c.keywords) or c.args:
                    f["total"] = True
            elif name.startswith("httpx") and (c.args or any(k.arg in ("timeout", "read") for k in c.keywords)):
                f["total"] = True
            elif any(k.arg in ("total", "read") for k in c.keywords) or c.args:
                f["total"] = True
        if name in ("socket.setdefaulttimeout",):
            f["tc"].add(name), setattr_total(f)
        if name in ("asyncio.wait_for", "asyncio.timeout", "asyncio.timeout_at", "async_timeout.timeout"):
            f["tc"].add(name), setattr_total(f)
        # concurrent.futures deadlines (D34): fut.result(timeout=...), wait(fs, timeout=...), as_completed(fs, timeout=...)
        if (last == "result" and isinstance(c.func, ast.Attribute)
                and (any(k.arg == "timeout" for k in c.keywords) or len(c.args) == 1)) \
                or (last in ("wait", "as_completed") and "asyncio" not in name and any(k.arg == "timeout" for k in c.keywords)):
            f["tc"].add("Future.result(timeout)"), setattr_total(f)
        if name in ("urllib3.Retry", "urllib3.util.Retry", "urllib3.util.retry.Retry", "requests.adapters.Retry",
                    "requests.packages.urllib3.util.retry.Retry"):
            f["retry"].add("library_builtin"), f["rc"].add("urllib3.Retry")
    if "urllib3" in f["library"] and not any("retries" in r for r in f["rc"]):
        # urllib3 retries 3 times by default (PoolManager/urlopen), unless retries= is given
        f["retry"].add("library_builtin"), f["rc"].add("urllib3 default retries")

    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.AsyncFor, ast.While)):
            continue
        body = [x for s in loop.body + loop.orelse for x in ast.walk(s)]
        http = any(is_http_call(x) or (isinstance(x, ast.Call) and _dotted(x.func).rsplit(".", 1)[-1] in httpf) for x in body)
        if not http:
            continue
        sleep = any(isinstance(x, ast.Call) and _is_sleep(_dotted(x.func)) for x in body)
        cont = any(isinstance(x, ast.Continue) for x in body)
        attempts = isinstance(loop, (ast.For, ast.AsyncFor)) and isinstance(loop.iter, ast.Call) and _dotted(loop.iter.func) == "range"
        if sleep or (cont and (attempts or isinstance(loop, ast.While))):
            f["retry"].add("hand_loop"), f["rc"].add("loop+sleep" if sleep else "loop+continue")
    for loop in ast.walk(tree):
        if "hand_loop" in f["retry"] or not isinstance(loop, (ast.For, ast.AsyncFor, ast.While)):
            continue
        body = [x for s in loop.body + loop.orelse for x in ast.walk(s)]
        sleep = any(isinstance(x, ast.Call) and _is_sleep(_dotted(x.func)) for x in body)
        words = any(isinstance(x, ast.Name) and RETRY_WORDS.search(x.id) for x in body)
        if sleep and words:  # generic wrapper: the loop calls a callback and backs off
            f["retry"].add("hand_loop"), f["rc"].add("retry wrapper loop")
    return f


def _total(f, v):
    # timeout=5 / timeout=(3, 10) / timeout=httpx.Timeout(...) all bound the read phase of an attempt
    f["total"] = True


def setattr_total(f):
    f["total"] = True


# ---------------------------------------------------------------- lexical (TS, Java, Go)
def strip_comments(src, lang):
    """Removes comments; keeps string literals (imports and option names live in them)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def loop_bodies(code, lang):
    pat = {"typescript": r"\b(?:for|while)\s*\(|\bdo\s*\{", "java": r"\b(?:for|while)\s*\(|\bdo\s*\{",
           "go": r"\bfor\b[^{\n]*\{"}[lang]
    for m in re.finditer(pat, code):
        i = code.find("{", m.end() - 1)
        if i < 0:
            continue
        if lang != "go":  # skip the (...) header
            if code[m.end() - 1] == "(":
                depth, j = 1, m.end()
                while j < len(code) and depth:
                    depth += {"(": 1, ")": -1}.get(code[j], 0)
                    j += 1
                i = code.find("{", j)
                if i < 0 or code[j:i].strip():
                    continue  # single-statement loop body
        depth, j = 1, i + 1
        while j < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[j], 0)
            j += 1
        yield code[i:j]


def http_funcs(code, lang, direct):
    """Names of functions whose body makes an HTTP call (transitively), by brace matching."""
    pat = {"typescript": r"(?:function\s+(\w+)\s*\(|(\w+)\s*=\s*async\s*\(|async\s+(\w+)\s*\(|(\w+)\s*\([^)]*\)\s*(?::[^{]+)?\{)",
           "java": r"(\w+)\s*\([^)]*\)\s*(?:throws[^{]+)?\{",
           "go": r"func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("}[lang]
    bodies = {}
    for m in re.finditer(pat, code):
        name = next(g for g in m.groups() if g)
        if name in ("if", "for", "while", "switch", "catch", "return"):
            continue
        i = code.find("{", m.end() - 1)
        if i < 0:
            continue
        depth, j = 1, i + 1
        while j < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[j], 0)
            j += 1
        bodies.setdefault(name, code[i:j])
    names = set()
    changed = True
    while changed:
        changed = False
        for k, b in bodies.items():
            if k not in names and (re.search(direct, b) or any(re.search(rf"\b{re.escape(x)}\s*\(", b) for x in names)):
                names.add(k)
                changed = True
    return names


LEX = {
    "typescript": {
        "libs": [("ky", r"from\s+['\"]ky['\"]|require\(['\"]ky['\"]\)"), ("got", r"from\s+['\"]got['\"]|require\(['\"]got['\"]\)"),
                 ("axios", r"from\s+['\"]axios['\"]|require\(['\"]axios['\"]\)"),
                 ("undici", r"from\s+['\"]undici['\"]|require\(['\"]undici['\"]\)"),
                 ("node:http", r"['\"](?:node:)?https?['\"]"), ("fetch", r"(?<![.\w])fetch\s*\(")],
        "http": r"(?<![\w])(?:fetch|ky(?:\.\w+)?|got(?:\.\w+)?|axios(?:\.\w+)?|request)\s*\(",
        "timeouts": [("AbortSignal.timeout", r"AbortSignal\.timeout\s*\(", True),
                     ("AbortController+setTimeout", r"setTimeout\s*\([^;]*?\.abort\s*\(", True),
                     ("timeout option", r"\btimeout\s*:\s*(?!0\b|false\b|undefined\b|null\b)", True),
                     ("setTimeout(timeout)", r"\.setTimeout\s*\(", True),
                     # D38: a timer raced against the call returns on time but does not abort the request
                     ("Promise.race+setTimeout", r"Promise\.race\s*\([^;]*?setTimeout\s*\(|setTimeout\s*\([^;]*?reject", True)],
        "retry_libs": [("p-retry", r"['\"]p-retry['\"]"), ("async-retry", r"['\"]async-retry['\"]"),
                       ("exponential-backoff", r"['\"]exponential-backoff['\"]")],
        "builtin": [("ky default retry", "ky", r"retry\s*:\s*(?:0|\{\s*limit\s*:\s*0)"),
                    ("got default retry", "got", r"retry\s*:\s*(?:0|\{\s*limit\s*:\s*0)")],
        "sleep": r"setTimeout\s*\(|\b\w*[sS]leep\w*\s*\(|\bdelay\s*\(|\bwait\s*\(|timers/promises",
    },
    "java": {
        "libs": [("java.net.http", r"java\.net\.http"), ("HttpURLConnection", r"HttpURLConnection"),
                 ("okhttp", r"okhttp3"), ("apache-httpclient5", r"org\.apache\.hc"), ("apache-httpclient4", r"org\.apache\.http\.")],
        "http": r"\.(?:send|sendAsync|execute|newCall|getInputStream|getResponseCode|connect)\s*\(",
        "timeouts": [("HttpRequest.Builder.timeout", r"\.timeout\s*\(", True),
                     ("connectTimeout", r"\.connectTimeout\s*\(|setConnectTimeout\s*\(", False),
                     ("setReadTimeout", r"setReadTimeout\s*\(|\.readTimeout\s*\(", True),
                     ("callTimeout", r"\.callTimeout\s*\(", True),
                     ("orTimeout", r"\.orTimeout\s*\(|completeOnTimeout\s*\(", True),
                     ("Future.get(timeout)", r"\.get\s*\([^;]*TimeUnit\.", True),
                     ("setResponseTimeout", r"setResponseTimeout\s*\(|setSocketTimeout\s*\(", True)],
        "retry_libs": [("resilience4j", r"io\.github\.resilience4j"), ("failsafe", r"dev\.failsafe|net\.jodah\.failsafe"),
                       ("spring-retry", r"org\.springframework\.retry")],
        "builtin": [],
        "sleep": r"Thread\.sleep\s*\(|TimeUnit\.\w+\.sleep\s*\(|LockSupport\.park|\b\w*[sS]leep\w*\s*\(|delayedExecutor|\.schedule\s*\(",
    },
    "go": {
        "libs": [("resty", r"go-resty/resty|resty\.dev"), ("go-retryablehttp", r"hashicorp/go-retryablehttp"),
                 ("net/http", r"\"net/http\"")],
        "http": r"\.(?:Do|Get|Post|Head|PostForm)\s*\(|http\.(?:Get|Post|Head|PostForm)\s*\(|\.R\(\)",
        "timeouts": [("http.Client.Timeout", r"http\.Client\s*\{[^}]*\bTimeout\s*:|\.Timeout\s*=", True),
                     ("context.WithTimeout", r"context\.WithTimeout\s*\(|context\.WithDeadline\s*\(|context\.WithTimeoutCause\s*\(", True),
                     ("Transport timeouts", r"ResponseHeaderTimeout\s*:|IdleConnTimeout\s*:|TLSHandshakeTimeout\s*:|ExpectContinueTimeout\s*:", False),
                     ("Dialer.Timeout", r"net\.Dialer\s*\{[^}]*\bTimeout\s*:|DialTimeout\s*\(", False),
                     ("resty SetTimeout", r"\.SetTimeout\s*\(", True),
                     ("SetDeadline", r"\.Set(?:Read)?Deadline\s*\(", True)],
        "retry_libs": [("go-retryablehttp", r"hashicorp/go-retryablehttp"), ("cenkalti/backoff", r"cenkalti/backoff")],
        "builtin": [],
        "sleep": r"time\.Sleep\s*\(|time\.After\s*\(|time\.NewTimer\s*\(|\b\w*[sS]leep\w*\s*\(",
    },
}


RETRY_WORDS = re.compile(r"attempt|retr(?:y|ies)|backoff", re.I)


def classify_lexical(src, lang):
    L = LEX[lang]
    code = strip_comments(src, lang)
    f = {"library": set(), "tc": set(), "total": False, "retry": set(), "rc": set()}
    for name, rx in L["libs"]:
        if re.search(rx, code, re.M):
            f["library"].add(name)
    if lang == "go" and {"resty", "go-retryablehttp"} & f["library"] and not re.search(r"http\.(?:NewRequest|Get|Post|Client\b|DefaultClient)", code):
        f["library"].discard("net/http")
    for name, rx, total in L["timeouts"]:
        if re.search(rx, code, re.S if lang == "go" else 0):
            f["tc"].add(name)
            f["total"] |= total
    # D44: the generic TypeScript "timeout option" means different things per library: ky's `timeout` and got's
    # `timeout: {request: ...}` bound the whole request, body included; axios' `timeout` is a socket idle timer.
    if lang == "typescript" and "timeout option" in f["tc"]:
        if "ky" in f["library"]:
            f["tc"].add("ky timeout")
        if "got" in f["library"] and re.search(r"timeout\s*:\s*\{[^}]*\brequest\s*:", code):
            f["tc"].add("got timeout.request")
    if lang == "go" and "Transport timeouts" in f["tc"] and re.search(r"ResponseHeaderTimeout\s*:", code):
        f["total"] = True  # bounds the wait for headers of each attempt
    for name, rx in L["retry_libs"]:
        if re.search(rx, code):
            f["retry"].add("retry_library"), f["rc"].add(name)
    for name, lib, off in L["builtin"]:
        if lib in f["library"] and not re.search(off, code):
            f["retry"].add("library_builtin"), f["rc"].add(name)
    if lang == "go" and "resty" in f["library"] and re.search(r"\.SetRetryCount\s*\(\s*[1-9]", code):
        f["retry"].add("library_builtin"), f["rc"].add("resty SetRetryCount")
    names = http_funcs(code, lang, L["http"])
    call_names = rf"\b(?:{'|'.join(map(re.escape, names))})\s*\(" if names else None
    for body in loop_bodies(code, lang):
        sleep = re.search(L["sleep"], body)
        if re.search(L["http"], body) or (call_names and re.search(call_names, body)):
            cont = re.search(r"\bcontinue\b", body)
            if sleep or cont:
                f["retry"].add("hand_loop"), f["rc"].add("loop+sleep" if sleep else "loop+continue")
                break
        elif sleep and RETRY_WORDS.search(body):
            # generic wrapper: the loop invokes a callback (executeWithRetry(() -> ...)) and backs off
            f["retry"].add("hand_loop"), f["rc"].add("retry wrapper loop")
            break
    return f


def classify(src, lang):
    f = classify_python(src) if lang == "python" else classify_lexical(src, lang)
    return {"library": ";".join(sorted(f["library"])) or "none",
            "timeout_explicit": int(bool(f["tc"])), "timeout_constructs": ";".join(sorted(f["tc"])),
            "timeout_total": int(f["total"]),
            "retry_mechanism": ";".join(sorted(f["retry"])) or "none", "retry_constructs": ";".join(sorted(f["rc"]))}


def rel(p):
    return "/".join(str(p[k]) for k in KEYS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    ap.add_argument("--manual-sample", action="store_true", help="also draw the 100 programs for the author's check")
    a = ap.parse_args()
    progs = [json.loads(l) for l in open(DATA / a.run / "programs.jsonl")]
    progs = [p for p in progs if p["category"] == "ok"]
    out = DATA / a.run / "classify"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in progs:
        src = (DATA / a.run / "generations" / rel(p) / f"solution.{EXT[p['lang']]}").read_text()
        rows.append({k: p[k] for k in KEYS} | classify(src, p["lang"]))
    with open(out / "features.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} programs -> {out / 'features.csv'}")
    if a.manual_sample:
        mc = out / "manual_check.csv"
        if mc.exists():
            raise SystemExit(f"{mc} exists (the author's answers are never overwritten)")
        pick = random.Random(SEED).sample(sorted(rows, key=rel), 100)
        with open(mc, "w", newline="") as fh:
            # Blind: the automatic labels are not shown; agreement is computed by classify/agreement.py.
            w = csv.DictWriter(fh, ["id", *KEYS, "solution_path", "author_library", "author_timeout_explicit",
                                    "author_timeout_total", "author_retry_mechanism", "author_note"])
            w.writeheader()
            for i, r in enumerate(pick, 1):
                w.writerow({"id": i, **{k: r[k] for k in KEYS},
                            "solution_path": f"data/{a.run}/generations/{rel(r)}/solution.{EXT[r['lang']]}"})
        print(f"100 programs for the manual check -> {mc}")


if __name__ == "__main__":
    main()
