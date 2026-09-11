"""Read-only host capability preflight (PREP-01, P1-00 subset).

Every probe is read-only, local, and bounded: per-probe timeout <= 5 s,
whole preflight <= 30 s, single failures do not block other checks.
Statuses: observed / unavailable / permission_denied / not_checked.
This is degradation evidence, never a claim that workloads were measured.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROBE_TIMEOUT_S = 5


def _status(kind: str, detail: str, method: str) -> dict:
    return {"status": kind, "detail": detail, "method": method}


def _timed_read(path: Path) -> tuple[str | None, str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip(), "read"
    except PermissionError:
        return None, "permission_denied"
    except OSError as exc:
        return None, f"error:{type(exc).__name__}"


# ---------------------------------------------------------------------------
# individual probes (pure-ish; filesystem read only)
# ---------------------------------------------------------------------------

def probe_python() -> dict:
    import sys
    return {
        "status": "observed",
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "implementation": sys.implementation.name,
        "method": "sys.version/executable",
    }


def probe_packages(packages: tuple[str, ...] = ("pydantic", "yaml", "litellm", "docker")) -> dict:
    """Package presence via importlib.metadata (metadata only; no import)."""
    import importlib.metadata as md
    found, missing = {}, []
    for name in packages:
        try:
            found[name] = md.version(name)
        except md.PackageNotFoundError:
            missing.append(name)
    return {"status": "observed", "installed": found, "missing": missing,
            "method": "importlib.metadata.version (no import)"}


def probe_cpu_memory_disk(project_root: Path) -> dict:
    out: dict[str, Any] = {"status": "observed", "method": "os/cpu_count; /proc/meminfo; statvfs"}
    out["cpu_count_logical"] = os.cpu_count()
    mem, m = _timed_read(Path("/proc/meminfo"))
    if mem:
        first = {}
        for line in mem.splitlines()[:5]:
            k, _, v = line.partition(":")
            first[k.strip()] = v.strip()
        out["meminfo_head"] = first
    else:
        out["meminfo_head"] = m
    try:
        st = os.statvfs(project_root)
        out["project_free_gib"] = round(st.f_bavail * st.f_frsize / 2**30, 1)
    except OSError as exc:
        out["project_free_gib"] = f"error:{type(exc).__name__}"
    return out


def probe_cgroup() -> dict:
    """Self cgroup membership, controllers, readable counters. Read-only."""
    out: dict[str, Any] = {"method": "/proc/self/cgroup; /sys/fs/cgroup reads"}
    self_cg, m1 = _timed_read(Path("/proc/self/cgroup"))
    if self_cg is None:
        out["status"] = "permission_denied" if m1 == "permission_denied" else "unavailable"
        out["detail"] = f"/proc/self/cgroup: {m1}"
        return out
    out["self_cgroup_lines"] = self_cg.splitlines()[:3]
    unified = Path("/sys/fs/cgroup/cgroup.controllers")
    if unified.exists():
        ctrl, m2 = _timed_read(unified)
        out["cgroup_version"] = "v2-unified"
        out["controllers"] = ctrl.split() if ctrl else m2
        # readable counter files on self path (membership-limited)
        probes = {}
        for rel in ("cpu.stat", "memory.current", "io.stat"):
            p = Path("/sys/fs/cgroup") / rel
            val, mm = _timed_read(p)
            probes[rel] = "readable" if val is not None else mm
        out["root_counters_readable"] = probes
    else:
        out["cgroup_version"] = "v1-or-unknown"
    out["status"] = "observed"
    return out


def probe_process_visibility() -> dict:
    out: dict[str, Any] = {"method": "/proc/self/status; /proc/self/ns"}
    status, m = _timed_read(Path("/proc/self/status"))
    if status is None:
        return {"status": "permission_denied", "detail": f"/proc/self/status: {m}",
                "method": out["method"]}
    keep = {}
    for line in status.splitlines():
        if line.startswith(("Name:", "Pid:", "PPid:", "Uid:", "Gid:")):
            k, _, v = line.partition(":")
            keep[k.strip()] = v.strip()
    out["self_status_head"] = keep
    ns = {}
    for n in ("pid", "mnt", "ipc"):
        p = Path(f"/proc/self/ns/{n}")
        ns[n] = "present" if p.exists() else "absent"
    out["namespaces"] = ns
    # /proc/*/environ is intentionally NOT read (authorization boundary)
    out["environ"] = "not_checked (out of authorized scope)"
    out["status"] = "observed"
    return out


def probe_perf() -> dict:
    out: dict[str, Any] = {"method": "shutil.which; kernel.perf_event_paranoid read"}
    perf = shutil.which("perf")
    if not perf:
        out["status"] = "unavailable"
        out["detail"] = "perf binary not found"
        return out
    out["binary"] = perf
    paranoid, m = _timed_read(Path("/proc/sys/kernel/perf_event_paranoid"))
    if paranoid is None:
        out["paranoid"] = m
        out["status"] = "permission_denied" if m == "permission_denied" else "unavailable"
    else:
        out["paranoid"] = paranoid
        out["status"] = "observed"
    out["claim"] = "binary/permission metadata only; PMU usability NOT verified (no perf run)"
    return out


def probe_docker() -> dict:
    """Local Docker client + local unix socket only.

    Explicitly ignores DOCKER_HOST / docker contexts that may point at remote
    endpoints. If a local endpoint cannot be safely determined, reports
    unknown rather than probing. No image enumeration, no info dump.
    """
    out: dict[str, Any] = {"method": "shutil.which; /var/run/docker.sock stat only"}
    if os.environ.get("DOCKER_HOST"):
        # A remote endpoint is configured: refuse to follow it silently.
        out["status"] = "not_checked"
        out["detail"] = ("DOCKER_HOST is set (may point to a remote endpoint); "
                         "local-socket-only policy refuses to follow it")
        out["docker_host_present"] = True
        return out
    out["docker_host_present"] = False
    client = shutil.which("docker")
    if not client:
        out["status"] = "unavailable"
        out["detail"] = "docker client binary not found"
        return out
    out["client"] = client
    sock = Path("/var/run/docker.sock")
    if not sock.exists():
        out["status"] = "unavailable"
        out["detail"] = "local unix socket /var/run/docker.sock not found"
        return out
    try:
        st = sock.stat()
        out["socket"] = {"present": True,
                         "is_socket": bool(st.st_mode & 0o140000)}
    except PermissionError:
        out["status"] = "permission_denied"
        out["detail"] = "cannot stat docker socket"
        return out
    # One bounded, whitelist-limited version query over the local socket only.
    try:
        r = subprocess.run(
            ["docker", "--config", "/dev/null", "version", "--format", "{{.Client.Version}}"],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
            env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"})
        if r.returncode == 0:
            out["client_version"] = r.stdout.strip()
            out["status"] = "observed"
            out["claim"] = ("client + local socket observed; daemon/container "
                            "runnability NOT verified; no info dump, no image list")
        else:
            out["status"] = "unavailable"
            out["detail"] = f"docker version rc={r.returncode}"
    except subprocess.TimeoutExpired:
        out["status"] = "unavailable"
        out["detail"] = "docker version timed out (5s)"
    except OSError as exc:
        out["status"] = "unavailable"
        out["detail"] = f"error:{type(exc).__name__}"
    return out


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def run_preflight(project_root: Path, *,
                  probes: dict[str, Callable] | None = None,
                  docker: bool = True) -> dict:
    """Run all probes; one failure never blocks the others."""
    from typing import Callable
    default = {
        "python": probe_python,
        "packages": probe_packages,
        "cpu_memory_disk": lambda: probe_cpu_memory_disk(project_root),
        "cgroup": probe_cgroup,
        "process_visibility": probe_process_visibility,
        "perf": probe_perf,
    }
    if docker:
        default["docker"] = probe_docker
    plan = probes if probes is not None else default
    results = {}
    for name, fn in plan.items():
        try:
            results[name] = fn()
        except Exception as exc:  # noqa: BLE001 — bounded probe, report and continue
            results[name] = {"status": "unavailable",
                             "detail": f"probe error: {type(exc).__name__}",
                             "method": fn.__name__}
    for name, res in results.items():
        st = res.get("status")
        if st not in ("observed", "unavailable", "permission_denied", "not_checked"):
            res["status"] = "not_checked"
    results["_meta"] = {
        "scope": "read-only local probes; per-probe timeout 5s; no network; no containers",
        "claim_limits": ("degradation evidence only; nothing here asserts PMU "
                         "usability, container runnability, or workload support"),
    }
    return results
