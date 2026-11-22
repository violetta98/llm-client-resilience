"""Host-side orchestration of one slot: mock container + solution container on
an internal Docker network, one run per (solution, scenario).

Standard library only (runs on the host Python). See RUNBOOK.md.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

MOCK_IMAGE = "lcr-mock:dev"
RUNNER_IMAGES = {"python": "lcr-run-python:dev", "typescript": "lcr-run-node:dev",
                 "java": "lcr-run-java:dev", "go": "lcr-run-go:dev"}
# Path of the prepared solution inside the container (prepared dir -> /solution).
ENTRY = {"python": "/solution/solution.py", "typescript": "/solution/solution.mjs",
         "java": "/solution/classes", "go": "/solution/solution.bin"}
# Go: the prepared binary is the driver itself.
ENTRYPOINT = {"go": "/solution/solution.bin"}

LIMIT_S = 90          # draft Table V
LIMIT_LONG_S = 330    # repetition of stalled runs
KILL_GRACE_S = 15     # external hard kill at limit + 15 s
LINGER_S = 5          # late-request window after return
S7_OBSERVE_S = 90     # S7: observe the ten invocations for 90 s from the start
CLOCK_FLAG_S = 1.0    # driver vs external disagreement flag
MAX_STDERR = 4 << 20

PORTS = {"A": 9001, "B": 9002, "C": 9003}
WARM_PORTS = {"A": 9101, "B": 9102, "C": 9103}


def sh(*args, check=True, capture=True, timeout=120):
    r = subprocess.run(list(args), capture_output=capture, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {r.returncode}: {r.stderr.strip()}")
    return r


def image_id(img: str) -> str:
    return sh("docker", "image", "inspect", img, "--format", "{{.Id}}").stdout.strip()


@dataclass
class Slot:
    k: int
    mock_cpus: str = ""
    sol_cpus: str = ""
    sol_cpu_quota: float = 1.0
    sol_memory: str = "1g"

    def __post_init__(self):
        self.int_net = f"lcr-int-{self.k}"
        self.ctl_net = f"lcr-ctl-{self.k}"
        self.mock_name = f"lcr-mock-{self.k}"
        self.mock_ip = f"10.77.{self.k}.2"
        self.sol_ip = f"10.77.{self.k}.3"
        self.ctl_ip = f"10.78.{self.k}.2"
        self.ctl_port = 19000 + self.k
        self.ctl_url = f"http://127.0.0.1:{self.ctl_port}"

    # --- lifecycle ---------------------------------------------------------
    def up(self):
        nets = sh("docker", "network", "ls", "--format", "{{.Name}}").stdout.split()
        if self.int_net in nets:
            opts = sh("docker", "network", "inspect", self.int_net, "--format", "{{json .Options}}").stdout
            if "inhibit_ipv4" not in opts:  # created by an older harness version
                sh("docker", "rm", "-f", self.mock_name, check=False)
                sh("docker", "network", "rm", self.int_net)
                nets.remove(self.int_net)
        if self.int_net not in nets:
            # internal: no gateway routing; inhibit_ipv4: the bridge itself has no
            # address, so the Docker VM is unreachable from the solution (ARP fails).
            sh("docker", "network", "create", "--internal", "--subnet", f"10.77.{self.k}.0/24",
               "--opt", "com.docker.network.bridge.enable_icc=true",
               "--opt", "com.docker.network.bridge.inhibit_ipv4=true", self.int_net)
        if self.ctl_net not in nets:
            sh("docker", "network", "create", "--subnet", f"10.78.{self.k}.0/24", self.ctl_net)
        sh("docker", "rm", "-f", self.mock_name, check=False)
        cpus = ["--cpuset-cpus", self.mock_cpus] if self.mock_cpus else []
        sh("docker", "create", "--name", self.mock_name, "--network", self.ctl_net, "--ip", self.ctl_ip,
           "-p", f"127.0.0.1:{self.ctl_port}:9900",
           "--cap-drop", "ALL", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", "--cap-add", "SETUID", "--cap-add", "SETGID",
           *cpus, "--memory", "512m",
           "-v", f"{DATA}:/data", MOCK_IMAGE,
           "--int-ip", self.mock_ip, "--ctl", f"{self.ctl_ip}:9900", "--data", "/data")
        sh("docker", "network", "connect", "--ip", self.mock_ip, self.int_net, self.mock_name)
        sh("docker", "start", self.mock_name)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                return self.ctl("GET", "/v1/health")
            except OSError:
                time.sleep(0.2)
        logs = sh("docker", "logs", self.mock_name, check=False)
        raise RuntimeError(f"mock did not come up: {logs.stdout}{logs.stderr}")

    def down(self):
        sh("docker", "rm", "-f", self.mock_name, check=False)

    def ctl(self, method, path, body=None, timeout=30):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.ctl_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"control {path}: {e.code} {e.read().decode()}") from None

    def dep_url(self, dep, warm=False):
        return f"https://{self.mock_ip}:{(WARM_PORTS if warm else PORTS)[dep]}"

    # --- one run ------------------------------------------------------------
    def run(self, *, lang, task, scenario, prepared: Path, function, warmup_args, calls,
            out_rel: str, limit_s=LIMIT_S, fault_dep=None, mock_overrides=None, run_id=None,
            extra_meta=None, inspect_paths=None) -> dict:
        """Runs one solution in one scenario. `warmup_args` and each `calls[i]["args"]`
        may contain "{A}", "{B}", "{C}" placeholders for dependency base URLs."""
        run_id = run_id or new_run_id()
        out_dir = DATA / out_rel
        if out_dir.exists() and any(out_dir.iterdir()):
            raise RuntimeError(f"{out_dir} exists (raw data is never overwritten)")
        cfg = {"run_id": run_id, "task": task, "scenario": scenario, "out_dir": out_rel}
        if fault_dep:
            cfg["fault_dep"] = fault_dep
        cfg.update(mock_overrides or {})
        start = self.ctl("POST", "/v1/run/start", cfg)

        sub = lambda v, warm: subst(v, {d: self.dep_url(d, warm) for d in PORTS})
        nonce = secrets.token_hex(8)
        plan = {
            "nonce": nonce, "function": function, "solution": ENTRY[lang],
            "mode": "single" if len(calls) == 1 else "concurrent",
            "warmup_args": sub(warmup_args, True), "calls": [{"args": sub(c["args"], False)} for c in calls],
            "limit_s": limit_s, "linger_s": LINGER_S, "warmup_limit_s": 60,
            "observe_s": S7_OBSERVE_S if scenario == "S7" else 0,
            "inspect_paths": inspect_paths or [],
        }
        tmp = Path(tempfile.mkdtemp(prefix="lcr-plan-"))
        try:
            (tmp / "plan.json").write_text(json.dumps(plan))
            os.chmod(tmp, 0o755)
            os.chmod(tmp / "plan.json", 0o644)
            outcome = self._run_container(lang, run_id, tmp, Path(prepared).resolve(), nonce, limit_s, plan)
        finally:
            fin = self.ctl("POST", "/v1/run/finish", timeout=60)
            shutil.rmtree(tmp, ignore_errors=True)

        out_dir.mkdir(parents=True, exist_ok=True)
        result = outcome.pop("result")
        (out_dir / "result.json").write_text(json.dumps(result, indent=1) if result is not None else "null")
        (out_dir / "stderr.txt").write_bytes(outcome.pop("stderr"))
        (out_dir / "stdout_markers.txt").write_text(outcome.pop("stdout"))
        timing = timing_check(result, outcome)
        (out_dir / "timing.json").write_text(json.dumps(timing, indent=1))
        meta = {
            "schema": "orchestrator-run/1", "run_id": run_id, "task": task, "scenario": scenario, "lang": lang,
            "fault_dep": fin.get("config", {}).get("fault_dep"), "limit_s": limit_s, "slot": self.k,
            "prepared_dir": str(prepared), "plan": plan, "mock_start": start, "container": outcome,
            "images": {"mock": image_id(MOCK_IMAGE), "runner": image_id(RUNNER_IMAGES[lang])},
            "host_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(), **(extra_meta or {}),
        }
        (out_dir / "orchestrator.json").write_text(json.dumps(meta, indent=1))
        return {"run_id": run_id, "out_dir": str(out_dir), "result": result, "timing": timing, "mock": fin}

    def _run_container(self, lang, run_id, plan_dir, sol_dir, nonce, limit_s, plan):
        name = f"lcr-sol-{self.k}-{run_id}"
        cpus = ["--cpuset-cpus", self.sol_cpus] if self.sol_cpus else []
        args = ["docker", "run", "--name", name, "--network", self.int_net, "--ip", self.sol_ip,
                "--hostname", "solution", "--read-only", "--tmpfs", "/tmp:rw,size=64m,mode=1777",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
                "--cpus", str(self.sol_cpu_quota), *cpus, "--memory", self.sol_memory, "--memory-swap", self.sol_memory,
                "--pids-limit", "512", "--ulimit", "nofile=4096:4096",
                "-v", f"{plan_dir}:/plan:ro", "-v", f"{sol_dir}:/solution:ro",
                *(["--entrypoint", ENTRYPOINT[lang]] if lang in ENTRYPOINT else []),
                RUNNER_IMAGES[lang]]
        sh("docker", "rm", "-f", name, check=False)
        t_spawn = time.monotonic_ns()
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        marks, lines = {}, []
        err_buf = bytearray()
        err_dropped = [0]

        def read_err():
            for chunk in iter(lambda: p.stderr.read(65536), b""):
                room = MAX_STDERR - len(err_buf)
                err_buf.extend(chunk[:max(room, 0)])
                err_dropped[0] += max(0, len(chunk) - max(room, 0))

        te = threading.Thread(target=read_err, daemon=True)
        te.start()
        killed = {"by": None, "t": None}
        kill_at = [t_spawn + 180 * 10**9]  # until START is seen: start-up/warm-up cap

        def killer():
            while p.poll() is None:
                if time.monotonic_ns() > kill_at[0]:
                    killed["by"], killed["t"] = "external_timer", time.monotonic_ns()
                    sh("docker", "kill", name, check=False)
                    return
                time.sleep(0.05)

        tk = threading.Thread(target=killer, daemon=True)
        tk.start()
        prefix = f"@@LCR {nonce} "
        result = None
        for raw in iter(p.stdout.readline, b""):
            now = time.monotonic_ns()
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if not line.startswith(prefix):
                lines.append(f"{now} [non-marker] {line[:500]}")
                continue
            kind, _, payload = line[len(prefix):].partition(" ")
            lines.append(f"{now} {kind} {payload[:200] if kind == 'RESULT' else payload}")
            marks.setdefault(kind, now)
            if kind == "START":
                kill_at[0] = now + (max(limit_s, plan.get("observe_s", 0) + LINGER_S) + KILL_GRACE_S) * 10**9
            elif kind == "RESULT":
                try:
                    result = json.loads(payload)
                except ValueError:
                    result = {"status": "bad_result_json"}
        p.wait()
        t_exit = time.monotonic_ns()
        te.join(5)
        insp = sh("docker", "inspect", name, "--format", "{{json .State}}", check=False).stdout.strip()
        sh("docker", "rm", "-f", name, check=False)
        stderr = bytes(err_buf)
        if err_dropped[0]:
            stderr += f"\n[orchestrator: {err_dropped[0]} further bytes of stderr dropped]\n".encode()
        return {"result": result, "stdout": "\n".join(lines) + "\n", "stderr": stderr, "exit_code": p.returncode,
                "host_mono_ns": {"spawn": t_spawn, **{k.lower(): v for k, v in marks.items()}, "process_exit": t_exit},
                "killed": killed, "state": json.loads(insp) if insp else None, "container": name}


def timing_check(result, outcome):
    """Driver (in-container CLOCK_MONOTONIC) vs external (host monotonic clock on
    marker arrival). For runs that did not return, the external time is the
    arrival of the RESULT marker emitted by the driver's watchdog."""
    h = outcome["host_mono_ns"]
    out = {"schema": "timing/1", "host_mono_ns": h}
    if not result or result.get("t_start") is None:
        out["comparable"] = False
        return out
    drv_end = result.get("t_end")
    if drv_end is not None:
        out["driver_s"] = (drv_end - result["t_start"]) / 1e9
        ext_end = h.get("end")
    else:
        out["driver_s"] = None
        out["driver_watchdog_s"] = result["limit_s"]
        ext_end = h.get("result")
    if "start" in h and ext_end:
        out["external_s"] = (ext_end - h["start"]) / 1e9
    ref = out["driver_s"] if out["driver_s"] is not None else out.get("driver_watchdog_s")
    if ref is not None and "external_s" in out:
        out["diff_s"] = out["external_s"] - ref
        out["flag_disagreement"] = abs(out["diff_s"]) > CLOCK_FLAG_S
        out["comparable"] = True
    if "spawn" in h and "ready" in h:
        out["startup_s"] = (h["ready"] - h["spawn"]) / 1e9
    if "spawn" in h:
        out["container_lifetime_s"] = (h["process_exit"] - h["spawn"]) / 1e9
    return out


def subst(v, urls):
    if isinstance(v, str):
        for d, u in urls.items():
            v = v.replace("{" + d + "}", u)
        return v
    if isinstance(v, list):
        return [subst(x, urls) for x in v]
    if isinstance(v, dict):
        return {k: subst(x, urls) for k, x in v.items()}
    return v


def new_run_id():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)
