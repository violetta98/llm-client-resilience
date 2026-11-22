"""Build the deposit archives without changing anything on disk.

  python3 tools/package_zenodo.py [--out dist/zenodo] [--version v1]

Writes
  <out>/llm-client-resilience-data-<version>.tar.gz   data/ (main, main-rep, dev, pilot, probe, logs, SCHEMA.md)
                                                     (compiled Go binaries excluded; SHA-256 listed)
  <out>/llm-client-resilience-code-<version>.tar.gz   the public copy (run tools/build_public.py first), the development
                                                     documents in DEV_DOCS, and analysis/out
  <out>/SHA256SUMS                                     checksums of the two archives
Inside the data archive, data/SHA256SUMS lists the checksums of the files as packed.

Every file is read and, before it is added, the absolute path of this checkout on the build machine is replaced by the
literal `<repo>`, the home directory in any other form (plain, URL-encoded, JSON-escaped) by `<home>`, and the
machine's host name by `<host>`; all of them contain the local user name. Nothing else is changed. The on-disk data/SHA256SUMS describes the
unchanged files and is therefore not packed; the packed data/SHA256SUMS is recomputed over the packed bytes.
The author's working notes are not released: data/main/classify/manual_check.csv is packed without its author_note
column (as in the public copy), and the build stops if any text file it packs contains Cyrillic (stage reports, check
pages and notes of the author were written in Russian). Raw model responses are exempt: they are data, packed as
returned.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import platform
import re
import socket
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKEN = b"<repo>"
PREFIXES = sorted({str(REPO).encode(), str(REPO.resolve()).encode()}, key=len, reverse=True)
TOP = "llm-client-resilience"
PUBLIC = REPO.parent / "llm-client-resilience"
# development documents kept out of the public copy but archived (English only)
DEV_DOCS = ("RUNBOOK.md", "reports/RUNLOG.md", "reports/TESTBED.md", "reports/DEVIATIONS_full.md",
            "reports/audit_numbers/REPORT.md")
NOTES_STRIPPED = {"data/main/classify/manual_check.csv": "author_note"}
CYRILLIC = re.compile("[\u0400-\u04ff]")


def check_language(rel: str, b: bytes):
    """Stop the build if a text file other than a raw model response contains Cyrillic."""
    if rel.endswith("/response.json") or b"\0" in b:
        return
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        return
    if CYRILLIC.search(t):
        raise SystemExit(f"Cyrillic text in {rel}: author notes are not released")


def strip_column(b: bytes, col: str) -> bytes:
    rows = list(csv.DictReader(io.StringIO(b.decode("utf-8"))))
    buf = io.StringIO()
    w = csv.DictWriter(buf, [c for c in rows[0] if c != col], extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


HOSTS = sorted({h for n in (platform.node(), socket.gethostname()) if n for h in (n, n.split(".")[0])}, key=len,
               reverse=True)  # the build machine's name (e.g. in `uname -a` snapshots) identifies the author
HOME = str(Path.home())
HOME_FORMS = [(HOME.encode(), b"<home>"), (HOME.replace("/", "%2F").encode(), b"%2F<home>"),
              (HOME.replace("/", "%2f").encode(), b"%2f<home>"), (HOME.replace("/", "\\/").encode(), b"\\/<home>")]


def clean(b: bytes) -> bytes:
    for p in PREFIXES:
        b = b.replace(p, TOKEN)
    for p, t in HOME_FORMS:  # the home directory in any other form (e.g. URL-encoded Docker socket path in build logs)
        b = b.replace(p, t)
    for h in HOSTS:
        b = b.replace(h.encode(), b"<host>")
    return b


def add(tar: tarfile.TarFile, rel: str, data: bytes, mtime: float):
    ti = tarfile.TarInfo(f"{TOP}/{rel}")
    ti.size, ti.mtime, ti.mode = len(data), int(mtime), 0o644
    ti.uname = ti.gname = ""
    tar.addfile(ti, io.BytesIO(data))


def files_under(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file())


def build_data(path: Path) -> dict:
    all_files = [p for p in files_under(REPO / "data") if p.relative_to(REPO).as_posix() != "data/SHA256SUMS"]
    # compiled Go binaries (prepared/**/solution.bin, about 12.7 GB) are rebuilt from solution.go by the runner's
    # pinned Go image; they are not packed, and their SHA-256 are listed in data/EXCLUDED_BINARIES.sha256
    binaries = [p for p in all_files if p.name == "solution.bin"]
    data_files = [p for p in all_files if p.name != "solution.bin"]
    sums, changed, t0 = [], 0, time.time()
    with tarfile.open(path, "w:gz", compresslevel=6) as tar:
        excl = "".join(f"{hashlib.sha256(b.read_bytes()).hexdigest()}  {b.relative_to(REPO / 'data').as_posix()}\n"
                       for b in binaries)
        add(tar, "data/EXCLUDED_BINARIES.sha256", excl.encode(), time.time())
        for i, p in enumerate(data_files):
            rel = p.relative_to(REPO).as_posix()
            raw = p.read_bytes()
            if rel in NOTES_STRIPPED:
                raw = strip_column(raw, NOTES_STRIPPED[rel])
            b = clean(raw)
            check_language(rel, b)
            changed += b != raw
            add(tar, rel, b, p.stat().st_mtime)
            sums.append(f"{hashlib.sha256(b).hexdigest()}  {rel[len('data/'):]}\n")
            if i % 50000 == 0:
                print(f"  data {i}/{len(data_files)} files, {time.time() - t0:.0f} s", flush=True)
        add(tar, "data/SHA256SUMS", "".join(sorted(sums, key=lambda s: s.split("  ", 1)[1])).encode(), time.time())
    return {"files": len(data_files), "binaries_excluded": len(binaries), "files_with_path_replaced": changed}


def build_code(path: Path) -> dict:
    if not (PUBLIC / "README.md").is_file():
        raise SystemExit(f"{PUBLIC} not found: run python3 tools/build_public.py first")
    src = {p.relative_to(PUBLIC).as_posix(): p for p in files_under(PUBLIC)
           if ".git" not in p.parts and "__pycache__" not in p.parts}
    for rel in DEV_DOCS:
        src[rel] = REPO / rel
    for p in files_under(REPO / "analysis" / "out"):
        src.setdefault(p.relative_to(REPO).as_posix(), p)
    changed = 0
    with tarfile.open(path, "w:gz", compresslevel=6) as tar:
        for rel in sorted(src):
            raw = src[rel].read_bytes()
            b = clean(raw)
            check_language(rel, b)
            changed += b != raw
            add(tar, rel, b, src[rel].stat().st_mtime)
    return {"files": len(src), "files_with_path_replaced": changed}


def sha256_file(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/zenodo")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--only", choices=("data", "code"), default="", help="rebuild one archive and keep the other")
    a = ap.parse_args()
    out = REPO / a.out
    out.mkdir(parents=True, exist_ok=True)
    paths = {"data": out / f"{TOP}-data-{a.version}.tar.gz", "code": out / f"{TOP}-code-{a.version}.tar.gz"}
    stats = {}
    if a.only != "code":
        stats["data"] = build_data(paths["data"])
    if a.only != "data":
        stats["code"] = build_code(paths["code"])
    lines = "".join(f"{sha256_file(p)}  {p.name}\n" for p in paths.values() if p.exists())
    (out / "SHA256SUMS").write_text(lines)
    print(stats)
    print(lines, end="")


if __name__ == "__main__":
    main()
