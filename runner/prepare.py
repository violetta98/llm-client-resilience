"""Host side of the per-solution prepare step (transpile/compile and
missing-dependency detection), run once per solution in a container without
network; every scenario run then mounts the prepared directory read-only.

Categories: ok | compile_error | missing_dependency (counted, not run).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# lang -> (image, command, source file name inside /src)
PREPARE = {
    "python": ("lcr-run-python:dev", ["python", "-s", "-P", "/driver/prepare.py"], "solution.py"),
    "typescript": ("lcr-run-node:dev", ["node", "/driver/prepare.mjs"], "solution.ts"),
    "java": ("lcr-build-java:dev", ["/opt/lcr-java/prepare.sh"], "Solution.java"),
    "go": ("lcr-build-go:dev", ["/opt/lcr-go/prepare.sh"], "solution.go"),
}


def prepare(lang: str, source: Path, out_dir: Path, task: dict | None = None, timeout_s: int = 300) -> dict:
    """Prepares `source` into `out_dir` (must not exist). `task` is the task's
    signature.json (Go needs the target function name)."""
    image, cmd, name = PREPARE[lang]
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"{out_dir} exists")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o777)
    src = Path(tempfile.mkdtemp(prefix="lcr-src-"))
    try:
        shutil.copy(source, src / name)
        (src / name).chmod(0o644)
        if task is not None:
            (src / "task.json").write_text(json.dumps(task))
            (src / "task.json").chmod(0o644)
            if lang == "go":
                (src / "target.txt").write_text(task["go"]["function"])
                (src / "target.txt").chmod(0o644)
        if lang == "go":
            ensure_gocache()
        src.chmod(0o755)
        args = ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,exec,size=512m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
                "--cpus", "2", "--memory", "2g", "--pids-limit", "512",
                "-v", f"{src}:/src:ro", "-v", f"{out_dir}:/out", "--entrypoint", cmd[0], image, *cmd[1:]]
        if lang == "go":  # shared, writable Go build cache (compilation only; no solution code runs)
            args[args.index("--entrypoint"):args.index("--entrypoint")] = ["-v", "lcr-gocache:/gocache"]
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        (out_dir / "prepare.log").write_text(r.stdout + r.stderr)
        p = out_dir / "prepare.json"
        if not p.exists():
            info = {"schema": "prepare/1", "lang": lang, "category": "harness_error", "exit": r.returncode,
                    "log": (r.stdout + r.stderr)[-4000:]}
            p.write_text(json.dumps(info, indent=1))
        return json.loads(p.read_text())
    finally:
        shutil.rmtree(src, ignore_errors=True)


_gocache_ok = False


def ensure_gocache():
    """Named volume for the Go build cache, writable by the unprivileged build user."""
    global _gocache_ok
    if _gocache_ok:
        return
    subprocess.run(["docker", "volume", "create", "lcr-gocache"], capture_output=True, check=True)
    subprocess.run(["docker", "run", "--rm", "--user", "0", "--network", "none", "-v", "lcr-gocache:/gocache",
                    "--entrypoint", "chown", "lcr-build-go:dev", "65534:65534", "/gocache"], capture_output=True, check=True)
    _gocache_ok = True
