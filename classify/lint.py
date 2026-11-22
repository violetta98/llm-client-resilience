"""RQ5 static checks (E9): Bandit B113, Ruff S113 (Python) and noctx in golangci-lint (Go).

  python3 classify/lint.py --run main

Pinned versions in runner/images/lint-py.Dockerfile and lint-go.Dockerfile (bandit 1.9.4, ruff 0.17.4,
golangci-lint v2.15.0). Only the timeout rules are enabled, explicitly; no custom rules. Generated code is
only parsed, never executed, and the linters run in containers without network.

Input: the `ok` programs of data/<run>/programs.jsonl (Python: the extracted solution.py; Go: the exact
source compiled by prepare, build/solution.go).
Output: data/<run>/lint/<tool>/findings.jsonl, one row per (program, tool): flagged, n, findings;
        data/<run>/lint/versions.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
KEYS = ("cond", "model", "task", "lang", "sample")
GOLANGCI_CFG = """version: "2"
linters:
  default: none
  enable: [noctx]
issues:
  max-issues-per-linter: 0
  max-same-issues: 0
  uniq-by-line: false
"""


def rel(p):
    return "/".join(str(p[k]) for k in KEYS)


def flat(p):
    return "__".join(str(p[k]) for k in KEYS).replace(".", "-")


def docker(*args, mounts=()):
    cmd = ["docker", "run", "--rm", "--network", "none", "--memory", "2g", "--cpus", "2"]
    for src, dst in mounts:
        cmd += ["-v", f"{src}:{dst}"]
    return subprocess.run(cmd + list(args), capture_output=True, text=True)


def lint_python(progs, run, work):
    d = work / "py"
    d.mkdir()
    names = {}
    for p in progs:
        n = flat(p) + ".py"
        shutil.copy(DATA / run / "generations" / rel(p) / "solution.py", d / n)
        names[n] = p
    r = docker("lcr-lint-py:dev", "sh", "-c",
               "bandit -q -t B113 -f json -r /w -o /tmp/b.json; cat /tmp/b.json; echo '\n=====RUFF'; "
               "ruff check --no-cache --isolated --select S113 --output-format json /w || true",
               mounts=[(d, "/w:ro")])
    bpart, rpart = r.stdout.split("\n=====RUFF", 1)
    bandit, ruff = json.loads(bpart), json.loads(rpart)
    if bandit.get("errors"):
        print("bandit errors:", len(bandit["errors"]))
    out = {"bandit_B113": {n: [] for n in names}, "ruff_S113": {n: [] for n in names}}
    for x in bandit["results"]:
        if x["test_id"] == "B113":
            out["bandit_B113"][Path(x["filename"]).name].append({"line": x["line_number"], "text": x["issue_text"]})
    berr = {Path(e["filename"]).name: e["reason"] for e in bandit.get("errors", [])}
    for x in ruff:
        if x["code"] == "S113":
            out["ruff_S113"][Path(x["filename"]).name].append({"line": x["location"]["row"], "text": x["message"]})
    return names, out, {"bandit_B113": berr, "ruff_S113": {}}


def lint_go(progs, run, work):
    d = work / "go"
    d.mkdir()
    names = {}
    for p in progs:
        n = flat(p)
        (d / n).mkdir()
        shutil.copy(DATA / run / "prepared" / rel(p) / "build" / "solution.go", d / n / "solution.go")
        names[n] = p
    (work / "golangci.yml").write_text(GOLANGCI_CFG)
    r = docker("--entrypoint", "sh", "lcr-lint-go:dev", "-c",
               "mkdir /tmp/w && cp /opt/lcr-go/libs/go.mod /opt/lcr-go/libs/go.sum /tmp/w/ && cp -r /src/. /tmp/w/ && "
               "cd /tmp/w && golangci-lint run -c /cfg/golangci.yml --output.json.path=/tmp/o.json ./... >/tmp/log 2>&1; "
               "cat /tmp/o.json; echo '\n=====LOG'; tail -c 4000 /tmp/log",
               mounts=[(d, "/src:ro"), (work / "golangci.yml", "/cfg/golangci.yml:ro")])
    js, log = r.stdout.split("\n=====LOG", 1)
    res = json.loads(js)
    out = {"golangci_noctx": {n: [] for n in names}}
    errs = {}
    for x in res.get("Issues") or []:
        n = next((s for s in x["Pos"]["Filename"].split("/") if s in names), None)
        if n is None:
            print("golangci issue outside the solutions:", x["Pos"]["Filename"], x["FromLinter"], x["Text"][:120])
            continue
        if x["FromLinter"] == "noctx":
            out["golangci_noctx"][n].append({"line": x["Pos"]["Line"], "text": x["Text"]})
        else:
            errs.setdefault(n, []).append(x["Text"])
    if errs:
        print("golangci non-noctx issues (typecheck?):", len(errs), log[-500:])
    return names, out, {"golangci_noctx": errs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="main")
    a = ap.parse_args()
    progs = [json.loads(l) for l in open(DATA / a.run / "programs.jsonl")]
    progs = [p for p in progs if p["category"] == "ok"]
    outdir = DATA / a.run / "lint"
    vers = {
        "lcr-lint-py:dev": docker("lcr-lint-py:dev", "sh", "-c", "bandit --version | head -1; ruff --version").stdout.split("\n"),
        "lcr-lint-go:dev": docker("--entrypoint", "cat", "lcr-lint-go:dev", "/etc/lcr-golangci-version.txt").stdout.strip(),
    }
    for img in vers:
        vers[img] = {"version": vers[img], "id": subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", img],
                                                                capture_output=True, text=True).stdout.strip()}
    with tempfile.TemporaryDirectory() as t:
        work = Path(t)
        results = []
        for fn, lang in ((lint_python, "python"), (lint_go, "go")):
            names, out, errs = fn([p for p in progs if p["lang"] == lang], a.run, work)
            results.append((names, out, errs))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "versions.json").write_text(json.dumps(vers, indent=1) + "\n")
    summary = {}
    for names, out, errs in results:
        for tool, per in out.items():
            (outdir / tool).mkdir(exist_ok=True)
            with open(outdir / tool / "findings.jsonl", "w") as f:
                for n, fs in sorted(per.items()):
                    p = names[n]
                    row = {k: p[k] for k in KEYS} | {"tool": tool, "flagged": bool(fs), "n": len(fs), "findings": fs}
                    if n in errs.get(tool, {}):
                        row["tool_error"] = errs[tool][n]
                    f.write(json.dumps(row) + "\n")
            summary[tool] = {"programs": len(per), "flagged": sum(1 for v in per.values() if v),
                             "tool_errors": len(errs.get(tool, {}))}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
