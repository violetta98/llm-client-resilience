"""Builds the protocol bundle for deposit (brief E6): dist/protocol-v1.zip + .sha256.

  python3 protocol/build_bundle.py            # refuses a dirty working tree
  python3 protocol/build_bundle.py --allow-dirty   # draft for review only

Contents: PROTOCOL.md, ANALYSIS_PLAN.md, thresholds.json, the generation config (models, parameters,
seeds, budget rule), all task specs and prompt templates, the mock and scenario code, the runner,
drivers and image definitions, the extraction rule, the measures and checkers, references and
mutants, DEVIATIONS.md, reports E0-E5, and environment.json (image IDs, installed library versions).
MANIFEST.json lists every file with its SHA-256 and the git commit.

The bundle is NOT uploaded by this script (no external actions); the author deposits it, then runs
  python3 protocol/freeze.py --doi <DOI>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INCLUDE = ["protocol/PROTOCOL.md", "protocol/ANALYSIS_PLAN.md", "protocol/thresholds.json", "gen", "tasks", "mock",
           "runner", "analysis/measures.py", "analysis/checkers.py", "references", "mutants", "baselines", "classify",
           "Makefile", "DEVIATIONS.md", "README.md", "RUNBOOK.md", "reports", "analysis/out/table_ix.md",
           "analysis/out/table_ix.csv", "analysis/out/price_snapshot.json", "analysis/out/pilot_summary.json", "tests"]
SKIP_PARTS = {"__pycache__", ".DS_Store", "node_modules"}
IMAGES = ["lcr-mock:dev", "lcr-run-python:dev", "lcr-run-node:dev", "lcr-run-java:dev", "lcr-build-java:dev",
          "lcr-build-go:dev", "lcr-run-go:dev", "lcr-probe:dev"]
INSIDE = {"lcr-run-python:dev": ["--entrypoint", "cat", "{img}", "/etc/lcr-pip-freeze.txt"]}


def sh(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tracked_files():
    out = sh("git", "-C", str(REPO), "ls-files") or ""
    files = set(out.splitlines())
    sel = []
    for f in sorted(files):
        if any(part in SKIP_PARTS for part in Path(f).parts):
            continue
        if any(f == inc or f.startswith(inc.rstrip("/") + "/") for inc in INCLUDE):
            sel.append(f)
    return sel


def environment():
    env = {"images": {}, "host": sh("uname", "-a"), "docker": sh("docker", "version", "--format", "{{.Server.Version}}")}
    for img in IMAGES:
        env["images"][img] = {"id": sh("docker", "image", "inspect", "--format", "{{.Id}}", img)}
        if img in INSIDE:
            env["images"][img]["libraries"] = (sh("docker", "run", "--rm", "--network", "none",
                                                   *[x.format(img=img) for x in INSIDE[img]]) or "").splitlines()
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--name", default="protocol-v1")
    a = ap.parse_args()
    dirty = sh("git", "-C", str(REPO), "status", "--porcelain")
    if dirty and not a.allow_dirty:
        sys.exit("working tree is dirty: commit first (or --allow-dirty for a review draft)")
    commit = sh("git", "-C", str(REPO), "rev-parse", "HEAD") + ("-dirty" if dirty else "")
    files = tracked_files()
    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    env = environment()
    manifest = {"name": a.name, "commit": commit, "files": {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest() for f in files},
                "environment_sha256": hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()}
    zp = dist / f"{a.name}{'-DRAFT' if dirty else ''}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(REPO / f, f"{a.name}/{f}")
        z.writestr(f"{a.name}/environment.json", json.dumps(env, indent=1))
        z.writestr(f"{a.name}/MANIFEST.json", json.dumps(manifest, indent=1))
    digest = hashlib.sha256(zp.read_bytes()).hexdigest()
    (zp.parent / (zp.name + ".sha256")).write_text(f"{digest}  {zp.name}\n")
    print(json.dumps({"bundle": str(zp.relative_to(REPO)), "sha256": digest, "files": len(files), "commit": commit,
                      "bytes": zp.stat().st_size}, indent=1))


if __name__ == "__main__":
    main()
