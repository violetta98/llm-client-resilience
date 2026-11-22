"""D61: which failing Python solutions fall within the scope of Bandit B113 and Ruff S113 at all (post hoc).

  python3 analysis/linter_scope_d61.py   -> analysis/out/deadline_v2/linter_scope.json

Scope (checked against the rules' documentation and the pre-submission AI review of 2026-11-21): both rules look at module-level
calls of `requests` (`requests.get/post/put/patch/delete/head/options`; Ruff also `requests.request`) and of `httpx`
(where they flag only `timeout=None`); neither looks at `Session` methods, urllib3, aiohttp or urllib.request.
Lexical check on comment-free source; a solution is in scope if it makes at least one such call.
"""
import csv, json, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
from deadline_check_v2 import strip_comments, solutions  # noqa: E402

REQ = re.compile(r"\brequests\.(get|post|put|patch|delete|head|options)\(")
REQ_R = re.compile(r"\brequests\.request\(")
HTTPX = re.compile(r"\bhttpx\.(get|post|put|patch|delete|head|options|request)\(")
SESSION = re.compile(r"\b(Session\(\)|httpx\.(Async)?Client\(|aiohttp\.|urllib3\.|urllib\.request)")

def main():
    out = {}
    for run in ("main", "confirm"):
        sol = solutions(run, run)
        c = {"failing": 0, "bandit_scope": 0, "ruff_scope": 0, "only_out_of_scope_clients": 0}
        for k, v in sol.items():
            if k[3] != "python" or not v["fail"]:
                continue
            code = strip_comments((REPO / "data" / run / "generations" / k[0] / k[1] / k[2] / k[3] / k[4] / "solution.py").read_text(errors="replace"), "python")
            c["failing"] += 1
            b = bool(REQ.search(code))
            r = b or bool(REQ_R.search(code))
            c["bandit_scope"] += b
            c["ruff_scope"] += r
            c["only_out_of_scope_clients"] += int(not r and not HTTPX.search(code))
        out[run] = c
    p = REPO / "analysis" / "out" / "deadline_v2" / "linter_scope.json"
    p.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
