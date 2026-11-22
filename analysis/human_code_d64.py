"""D64 (post hoc): timeout constructs in human-written Python HTTP client code (protocol/HUMAN_CODE_ADDENDUM.md).

  python3 analysis/human_code_d64.py fetch --cache <dir>   # downloads; writes data/human-pypi/{top.json,packages.csv}
  python3 analysis/human_code_d64.py extract --cache <dir> # writes <dir>/units.jsonl, modules.jsonl
  python3 analysis/human_code_d64.py analyze --cache <dir> # writes analysis/out/human-pypi/summary.json, units.csv

The downloaded code is untrusted: archives are read in memory with tarfile/zipfile and parsed with ast; nothing is
extracted to disk, imported or run. Downloads go to --cache (outside the repository); the repository keeps the package
list (name, version, URL, SHA-256) and the labels per function (analysis/out/human-pypi/units.csv); the extracted
sources are third-party code under their own licences and stay in --cache, from which `extract` rebuilds them.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import random
import re
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "classify"))
sys.path.insert(0, str(REPO / "analysis"))
from features import classify_python  # noqa: E402
from s4_mechanism import WHOLE  # noqa: E402

OUT_DATA = REPO / "data" / "human-pypi"
OUT = REPO / "analysis" / "out" / "human-pypi"
TOP_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"
N_TOP = 500
EXCLUDE_PKG = {"requests", "httpx", "httpcore", "aiohttp", "urllib3"}
EXCLUDE_DIRS = {"tests", "test", "testing", "docs", "doc", "examples", "example", "benchmarks", "vendor", "_vendor",
                "vendored"}
HTTP_LIBS = ("requests", "httpx", "aiohttp")
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "send", "stream"}
RECV = re.compile(r"(session|client|http)", re.I)
SEED = 20261106
UA = {"User-Agent": "research-script/1.0 (python urllib)"}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


# ------------------------------------------------------------------ fetch
def fetch(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    raw = get(TOP_URL)
    (OUT_DATA / "top.json").write_bytes(raw)
    top = json.loads(raw)
    rows = [r["project"] for r in top["rows"]][:N_TOP]
    out = []
    for i, name in enumerate(rows):
        rec = {"rank": i + 1, "project": name, "version": "", "file": "", "url": "", "sha256": "", "status": ""}
        if norm(name) in EXCLUDE_PKG:
            rec["status"] = "excluded_http_library"
            out.append(rec)
            continue
        try:
            meta = json.loads(get(f"https://pypi.org/pypi/{name}/json"))
            files = meta.get("urls", [])
            pick = next((f for f in files if f["packagetype"] == "sdist" and f["filename"].endswith(".tar.gz")), None)
            if pick is None:
                pick = next((f for f in files if f["filename"].endswith("py3-none-any.whl")), None)
            if pick is None:
                rec["status"] = "no_source"
                out.append(rec)
                continue
            rec.update(version=meta["info"]["version"], file=pick["filename"], url=pick["url"],
                       sha256=pick["digests"]["sha256"])
            dst = cache / pick["filename"]
            if not dst.exists():
                data = get(pick["url"], timeout=300)
                if hashlib.sha256(data).hexdigest() != rec["sha256"]:
                    rec["status"] = "hash_mismatch"
                    out.append(rec)
                    continue
                dst.write_bytes(data)
            rec["status"] = "ok"
        except Exception as e:  # noqa: BLE001 - network errors are recorded, not fatal
            rec["status"] = f"error: {type(e).__name__}"
        out.append(rec)
        if i % 50 == 0:
            print(f"{i}/{len(rows)}", flush=True)
        time.sleep(0.05)
    with open(OUT_DATA / "packages.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(out[0]))
        w.writeheader()
        w.writerows(out)
    print({s: sum(r["status"] == s for r in out) for s in {r["status"] for r in out}})


# ------------------------------------------------------------------ extract
def py_members(path: Path):
    """(name, bytes) of the .py files in an archive, outside excluded directories."""
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as t:
            for m in t.getmembers():
                if m.isfile() and m.name.endswith(".py") and m.size < 2_000_000:
                    parts = set(Path(m.name).parts[1:-1])
                    if parts & EXCLUDE_DIRS:
                        continue
                    f = t.extractfile(m)
                    if f is not None:
                        yield m.name, f.read()
    else:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith(".py") and not (set(Path(n).parts[:-1]) & EXCLUDE_DIRS):
                    yield n, z.read(n)


def dotted(n):
    parts = []
    while isinstance(n, ast.Attribute):
        parts.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name):
        parts.append(n.id)
    return ".".join(reversed(parts))


def http_call(c: ast.Call):
    if not isinstance(c.func, ast.Attribute) or c.func.attr not in METHODS:
        return False
    recv = dotted(c.func.value)
    if recv in HTTP_LIBS:
        return True
    last = recv.rsplit(".", 1)[-1] if recv else ""
    return bool(last) and bool(RECV.search(last))


def imports_http(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] in HTTP_LIBS for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in HTTP_LIBS:
            return True
    return False


def extract(cache: Path):
    pkgs = list(csv.DictReader(open(OUT_DATA / "packages.csv")))
    units, modules = [], []
    for p in pkgs:
        if p["status"] != "ok":
            continue
        for name, data in py_members(cache / p["file"]):
            try:
                src = data.decode("utf-8")
                tree = ast.parse(src)
            except (UnicodeDecodeError, SyntaxError, ValueError):
                continue
            if not imports_http(tree):
                continue
            imps = "\n".join(ast.get_source_segment(src, n) or "" for n in tree.body
                             if isinstance(n, (ast.Import, ast.ImportFrom)))
            found = False
            parents = {}
            for n in ast.walk(tree):
                for ch in ast.iter_child_nodes(n):
                    parents[ch] = n
            seen = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and http_call(n):
                    f = n
                    while f in parents and not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        f = parents[f]
                    if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) or id(f) in seen:
                        continue
                    seen.add(id(f))
                    calls = [c for c in ast.walk(f) if isinstance(c, ast.Call) and http_call(c)]
                    units.append({"project": p["project"], "version": p["version"], "file": name, "function": f.name,
                                  "lineno": f.lineno, "imports": imps, "source": ast.get_source_segment(src, f) or "",
                                  "timeout_arg": int(any(k.arg == "timeout" for c in calls for k in c.keywords))})
                    found = True
            if found:
                modules.append({"project": p["project"], "file": name, "source": src})
    with open(cache / "units.jsonl", "w") as fh:
        for u in units:
            fh.write(json.dumps(u) + "\n")
    with open(cache / "modules.jsonl", "w") as fh:
        for m in modules:
            fh.write(json.dumps(m) + "\n")
    print(len(units), "units in", len({u["project"] for u in units}), "packages;", len(modules), "modules")


# ------------------------------------------------------------------ analyze
def group(src):
    f = classify_python(src)
    cons = set(f["tc"])
    return "whole" if cons & WHOLE else "perread" if cons else "none"


def shares(items, key="project"):
    """items: list of (project, group). Shares with bootstrap over projects."""
    by = defaultdict(list)
    for pr, g in items:
        by[pr].append(g)
    projs = sorted(by)
    def sh(sample):
        allg = [g for pr in sample for g in by[pr]]
        n = len(allg)
        return {g: 100 * sum(x == g for x in allg) / n for g in ("whole", "perread", "none")} if n else None
    point = sh(projs)
    rnd = random.Random(SEED)
    boots = [sh([rnd.choice(projs) for _ in projs]) for _ in range(2000)]
    ci = {g: (round(sorted(b[g] for b in boots)[49], 1), round(sorted(b[g] for b in boots)[1949], 1))
          for g in ("whole", "perread", "none")}
    return {"units": len(items), "packages": len(projs),
            "share": {g: round(v, 1) for g, v in point.items()}, "ci": ci,
            "packages_with": {g: sum(any(x == g for x in by[pr]) for pr in projs) for g in ("whole", "perread", "none")}}


def analyze(cache: Path):
    units = [json.loads(l) for l in open(cache / "units.jsonl")]
    mods = [json.loads(l) for l in open(cache / "modules.jsonl")]
    fu = [(u["project"], group(u["imports"] + "\n" + u["source"])) for u in units]
    fm = [(m["project"], group(m["source"])) for m in mods]
    res = {"functions": shares(fu), "modules": shares(fm),
           "functions_timeout_arg": round(100 * sum(u["timeout_arg"] for u in units) / len(units), 1),
           }
    # sensitivity (not in the addendum): one package (litellm) holds most units
    res["functions_without_litellm"] = shares([x for x in fu if x[0] != "litellm"])
    byp = defaultdict(list)
    for pr, g in fu:
        byp[pr].append(g)
    res["functions_package_weighted"] = {g: round(100 * sum(sum(x == g for x in v) / len(v) for v in byp.values())
                                                  / len(byp), 1) for g in ("whole", "perread", "none")}
    # LLM comparison: runnable Python solutions (features.csv joined with programs.csv)
    ok = {tuple(r[k] for k in ("cond", "model", "task", "lang", "sample"))
          for r in csv.DictReader(open(REPO / "analysis" / "out" / "main" / "programs.csv")) if r["category"] == "ok"}
    llm = defaultdict(lambda: defaultdict(int))
    for r in csv.DictReader(open(REPO / "data" / "main" / "classify" / "features.csv")):
        k = tuple(r[x] for x in ("cond", "model", "task", "lang", "sample"))
        if k in ok and k[3] == "python":
            cons = {c for c in r["timeout_constructs"].split(";") if c}
            g = "whole" if cons & WHOLE else "perread" if cons else "none"
            llm["both"][g] += 1
            llm[k[0]][g] += 1
    res["llm_python"] = {c: {"n": sum(v.values()), **{g: round(100 * v[g] / sum(v.values()), 1) for g in v}}
                         for c, v in llm.items()}
    # by library of the unit
    lib = defaultdict(lambda: defaultdict(int))
    for u, (_, g) in zip(units, fu):
        f = classify_python(u["imports"] + "\n" + u["source"])
        for l in (f["library"] or {"other"}):
            lib[l][g] += 1
    res["functions_by_library"] = {l: dict(v) for l, v in lib.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1) + "\n")
    with open(OUT / "units.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project", "version", "file", "function", "lineno", "group", "timeout_arg"])
        for u, (_, g) in zip(units, fu):
            w.writerow([u["project"], u["version"], u["file"], u["function"], u["lineno"], g, u["timeout_arg"]])
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("fetch", "extract", "analyze"))
    ap.add_argument("--cache", type=Path)
    a = ap.parse_args()
    if a.step == "fetch":
        fetch(a.cache)
    elif a.step == "extract":
        extract(a.cache)
    else:
        analyze(a.cache)


if __name__ == "__main__":
    main()
