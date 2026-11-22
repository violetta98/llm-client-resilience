"""After the author has deposited the bundle: records the DOI and unlocks benchmark generation.

  python3 protocol/freeze.py --doi 10.5281/zenodo.NNNNNNN [--bundle dist/protocol-v1.zip]

Writes protocol/FREEZE.json (DOI, bundle SHA-256, commit), commits it and creates the local git
tag protocol-v1. Nothing is pushed or uploaded. gen/generate.py and gen/batch.py refuse benchmark
tasks until this file exists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doi", required=True)
    ap.add_argument("--bundle", default="dist/protocol-v1.zip")
    a = ap.parse_args()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", a.doi):
        sys.exit(f"not a DOI: {a.doi}")
    zp = REPO / a.bundle
    if "-DRAFT" in zp.name or not zp.exists():
        sys.exit(f"bundle {zp} missing or a draft")
    man = json.loads(zipfile.ZipFile(zp).read(f"{zp.stem}/MANIFEST.json"))
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if man["commit"] != head:
        sys.exit(f"bundle was built at {man['commit']}, HEAD is {head}: rebuild or check out that commit")
    rec = {"doi": a.doi, "bundle": zp.name, "bundle_sha256": hashlib.sha256(zp.read_bytes()).hexdigest(),
           "commit": head, "frozen": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (REPO / "protocol" / "FREEZE.json").write_text(json.dumps(rec, indent=1) + "\n")
    subprocess.run(["git", "-C", str(REPO), "add", "protocol/FREEZE.json"], check=True)
    subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", f"Protocol frozen: {a.doi}"], check=True)
    subprocess.run(["git", "-C", str(REPO), "tag", "-a", zp.stem, "-m", f"{zp.stem} {a.doi}", head], check=True)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
