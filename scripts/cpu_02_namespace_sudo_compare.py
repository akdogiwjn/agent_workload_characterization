#!/usr/bin/env python3
"""Manual, one-container namespace read comparison.

Default mode is a side-effect-free plan.  ``--execute`` is intended for a
human in the approved SSH terminal, not for the model sandbox.  Docker is
always invoked as the ordinary user against the fixed local socket.  sudo is
used only for one non-interactive, read-only ``readlink`` operation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

IMAGE = (
    "swebench/sweb.eval.arm64.django_1776_django-16485@"
    "sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2"
)
SOCKET = "unix:///var/run/docker.sock"
CPU = "1"
MEMORY = "256m"
TOTAL_S = 60.0
CLEANUP_RESERVE_S = 15.0
PREFIX = "awc-cpu-02-ns-compare"


class CheckError(RuntimeError):
    pass


def _remaining(deadline: float, cap: float) -> float:
    value = min(cap, deadline - time.monotonic())
    if value <= 0:
        raise CheckError("budget_exhausted")
    return value


def _argv(*parts: str) -> list[str]:
    return ["docker", "--host", SOCKET, *parts]


def _run(runner, argv: list[str], timeout: float):
    return runner(argv, capture_output=True, text=True, timeout=timeout)


def _safe_error(proc) -> dict:
    rc = getattr(proc, "returncode", None)
    if rc == 124:
        category = "timeout"
    elif rc is None:
        category = "unknown"
    else:
        category = "command_failed"
    return {"returncode": rc, "category": category}


def _inspect_identity(runner, ref: str, expected_label: str, deadline: float) -> dict:
    """Return only ID, label and State.Pid, requiring the expected label."""
    proc = _run(runner, _argv("inspect", "-f",
                              "{{.Id}}|{{index .Config.Labels \"awc.check\"}}|{{.State.Pid}}",
                              ref), _remaining(deadline, 5.0))
    if proc.returncode != 0:
        raise CheckError("identity_inspect_failed")
    fields = (proc.stdout or "").strip().split("|")
    if len(fields) != 3 or not fields[0] or fields[1] != expected_label:
        raise CheckError("container_label_mismatch")
    if not fields[2].isdigit() or int(fields[2]) <= 0:
        raise CheckError("invalid_state_pid")
    return {"container_id": fields[0], "label": fields[1], "state_pid": int(fields[2])}


def _readlink(runner, pid: int, *, sudo: bool, deadline: float, readlinker=os.readlink) -> dict:
    target = f"/proc/{pid}/ns/pid"
    if sudo:
        # This is the complete and only sudo argv.  No shell, Python, Docker,
        # environment, credential, cmdline, or password is passed to sudo.
        argv = ["sudo", "--non-interactive", "--", "/usr/bin/readlink", target]
    else:
        try:
            value = readlinker(target)
        except subprocess.TimeoutExpired:
            return {"status": "unavailable", "category": "timeout", "sudo": False}
        except OSError as exc:
            errno = getattr(exc, "errno", None)
            category = "permission_denied" if errno in (1, 13) else (
                "process_missing_or_not_visible" if errno in (2, 3) else "unknown")
            return {"status": "unavailable", "category": category,
                    "exception_type": type(exc).__name__, "errno": errno, "sudo": False}
        if not value.startswith("pid:[") or not value.endswith("]"):
            return {"status": "unavailable", "category": "invalid_namespace_value", "sudo": False}
        return {"status": "ok", "namespace": value, "sudo": False}
    try:
        proc = _run(runner, argv, _remaining(deadline, 5.0))
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "category": "timeout", "sudo": sudo}
    except OSError as exc:
        category = "permission_denied" if getattr(exc, "errno", None) in (1, 13) else "unknown"
        return {"status": "unavailable", "category": category,
                "exception_type": type(exc).__name__, "sudo": sudo}
    if proc.returncode != 0:
        result = _safe_error(proc)
        result.update(status="unavailable", sudo=sudo)
        return result
    value = (proc.stdout or "").strip()
    if not value.startswith("pid:[") or not value.endswith("]"):
        return {"status": "unavailable", "category": "invalid_namespace_value", "sudo": sudo}
    return {"status": "ok", "namespace": value, "sudo": sudo}


def _pid_starttime(pid: int) -> int:
    text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    fields = text.rsplit(")", 1)[1].split()
    return int(fields[19])


def _find_labeled_id(runner, label: str, deadline: float) -> str | None:
    proc = _run(runner, _argv("ps", "-a", "--filter", f"label=awc.check={label}",
                              "--format", "{{.ID}}"), _remaining(deadline, 5.0))
    if proc.returncode != 0:
        return None
    ids = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    return ids[0] if len(ids) == 1 else None


def _inspect_ownership(runner, ref: str, expected_label: str, deadline: float) -> dict:
    proc = _run(runner, _argv("inspect", "-f",
                              "{{.Id}}|{{index .Config.Labels \"awc.check\"}}", ref),
                _remaining(deadline, 5.0))
    if proc.returncode != 0:
        raise CheckError("ownership_inspect_failed")
    fields = (proc.stdout or "").strip().split("|")
    if len(fields) != 2 or not fields[0] or fields[1] != expected_label:
        raise CheckError("container_label_mismatch")
    return {"container_id": fields[0], "label": fields[1]}


def _cleanup(runner, container: str, label: str, known_id: str | None,
             deadline: float, result: dict) -> None:
    try:
        ref = known_id or _find_labeled_id(runner, label, deadline)
    except Exception:
        result["cleanup_verify"] = "not_checked"
        return
    if ref is None:
        result["cleanup_verify"] = "not_found_or_unconfirmed"
        return
    try:
        identity = _inspect_ownership(runner, ref, label, deadline)
        if known_id is not None and identity["container_id"] != known_id:
            result["cleanup_verify"] = "identity_mismatch"
            return
        ref = identity["container_id"]
        result["cleanup_container_id"] = ref
    except Exception:
        result["cleanup_verify"] = "identity_check_failed"
        return
    try:
        proc = _run(runner, _argv("rm", "-f", ref),
                    _remaining(deadline, CLEANUP_RESERVE_S))
        result["cleanup_stop"] = "ok" if proc.returncode == 0 else "failed"
    except Exception as exc:  # safe category only
        result["cleanup_stop"] = "timeout" if isinstance(exc, CheckError) else "failed"
    try:
        proc = _run(runner, _argv("ps", "-a", "--filter", f"id={ref}",
                                  "--format", "{{.ID}}"),
                    _remaining(deadline, CLEANUP_RESERVE_S))
        if proc.returncode != 0:
            result["cleanup_verify"] = "check_failed"
        else:
            result["cleanup_verify"] = "removed" if not (proc.stdout or "").strip() else "still_exists"
    except Exception:
        result["cleanup_verify"] = "not_checked"


def run_check(*, runner=subprocess.run, clock=time.monotonic, sleep=time.sleep,
              readlinker=os.readlink, container_name: str | None = None) -> dict:
    """Run the bounded comparison; fake ``runner`` is the offline test seam."""
    started = clock()
    deadline = started + TOTAL_S
    name = container_name or f"{PREFIX}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    result = {"container": name, "endpoint": SOCKET, "status": "FAIL",
              "sudo_scope": ["/usr/bin/readlink /proc/<State.Pid>/ns/pid"],
              "errors": [], "cleanup_verify": "not_run"}
    container_created = False
    container_attempted = False
    container_id = None
    try:
        # Refuse a pre-existing identity; never adopt or remove another batch.
        listed = _run(runner, _argv("ps", "-a", "--filter", f"name={name}",
                                    "--format", "{{.ID}}"), _remaining(deadline, 5.0))
        if listed.returncode != 0 or (listed.stdout or "").strip():
            raise CheckError("container_identity_exists_or_check_failed")
        container_attempted = True
        run = _run(runner, _argv("run", "-d", "--name", name, "--network", "none",
                                "--memory", MEMORY, "--cpus", CPU, "--pull", "never",
                                "--platform", "linux/arm64", "--label", "awc.collection=CPU-02",
                                "--label", f"awc.check={name}", IMAGE, "sleep", "2h"),
                     _remaining(deadline, TOTAL_S - CLEANUP_RESERVE_S))
        if run.returncode != 0:
            raise CheckError("container_start_failed")
        container_created = True
        container_id = (run.stdout or "").strip()
        identity = _inspect_identity(runner, name, name, deadline - CLEANUP_RESERVE_S)
        if identity["container_id"] != container_id:
            raise CheckError("container_id_mismatch")
        result["container_id"] = identity["container_id"]
        pid = identity["state_pid"]
        result["state_pid"] = pid
        first_start = _pid_starttime(pid)
        first_user = _readlink(runner, pid, sudo=False, deadline=deadline - CLEANUP_RESERVE_S,
                               readlinker=readlinker)
        result["ordinary"] = first_user
        result["starttime_before"] = first_start
        admin = _readlink(runner, pid, sudo=True, deadline=deadline - CLEANUP_RESERVE_S)
        result["sudo"] = admin
        identity_after = _inspect_identity(runner, identity["container_id"], name,
                                           deadline - CLEANUP_RESERVE_S)
        second_pid = identity_after["state_pid"]
        second_start = _pid_starttime(second_pid)
        result["starttime_after"] = second_start
        result["state_pid_after"] = second_pid
        if (identity_after["container_id"] != identity["container_id"] or
                pid != second_pid or first_start != second_start):
            result["status"] = "inconclusive"
            raise CheckError("target_identity_changed")
        if first_user.get("status") == "ok" and admin.get("status") == "ok":
            result["comparison"] = ("both_success_same" if admin.get("namespace") == first_user.get("namespace")
                                     else "indeterminate")
            result["status"] = "complete" if result["comparison"] == "both_success_same" else "inconclusive"
        elif (first_user.get("status") != "ok" and
              first_user.get("category") == "permission_denied" and admin.get("status") == "ok"):
            result["comparison"] = "ordinary_failed_sudo_success"
            result["status"] = "complete"
        else:
            result["comparison"] = "indeterminate"
            result["status"] = "inconclusive"
    except CheckError as exc:
        result["errors"].append(str(exc))
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["errors"].append(type(exc).__name__)
    finally:
        if container_attempted:
            _cleanup(runner, name, name, container_id, deadline, result)
            if result.get("cleanup_verify") != "removed":
                result["status"] = "FAIL"
    result["wall_s"] = max(0.0, clock() - started)
    result["ssh_user"] = {"uid": os.getuid(), "gid": os.getgid()}
    result["budget_overrun"] = result["wall_s"] > TOTAL_S
    if result["budget_overrun"]:
        result["status"] = "FAIL"
    return result


def plan() -> dict:
    return {"mode": "plan_only", "endpoint": SOCKET, "image": IMAGE,
            "container": {"count": 1, "cpu": CPU, "memory": MEMORY,
                          "network": "none", "pull": "never", "platform": "linux/arm64"},
            "budget": {"total_s": TOTAL_S, "cleanup_reserve_s": CLEANUP_RESERVE_S},
            "sudo_argv": ["sudo", "--non-interactive", "--", "/usr/bin/readlink",
                          "/proc/<State.Pid>/ns/pid"],
            "no": ["perf", "Django", "model", "network", "sudo Docker", "sudo Python"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    result = run_check()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "complete" else 5


if __name__ == "__main__":
    raise SystemExit(main())
