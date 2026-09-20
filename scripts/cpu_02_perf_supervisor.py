#!/usr/bin/env python3
"""Narrow CPU-02 perf supervisor.

This source is an offline implementation artifact.  It is not root-owned in
the repository and is never invoked with sudo by the test suite.  An
administrator may install a reviewed, fixed-hash copy at the documented path.
It has no shell or command-dispatch interface: it can only start the fixed
/usr/bin/perf record invocation below and reap that one child.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time

PERF = "/usr/bin/perf"
EVENT = "cycles"
FREQUENCY = 99
MAX_WATCHDOG_S = 60.0
ALLOWED_ROOT = Path("/home/lcq/agent_workload_characterization/reports/cpu/CPU-02/permission-confirmation")


def _fail(category):
    print(json.dumps({"status": "rejected", "category": category},
                     separators=(",", ":")), flush=True)
    return 3


def _safe_path(value, *, allow_missing=False):
    path = Path(value)
    if not path.is_absolute() or not path.is_relative_to(ALLOWED_ROOT):
        raise ValueError("path_outside_allowed_root")
    current = ALLOWED_ROOT
    # Every existing parent is checked; a symlink at any level is rejected.
    for part in path.relative_to(ALLOWED_ROOT).parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError("path_symlink")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("path_not_regular")
    if not allow_missing and not path.exists():
        raise ValueError("path_missing")
    return path


def _safe_fifo(value):
    path = _safe_path(value, allow_missing=False)
    if not stat.S_ISFIFO(path.stat().st_mode):
        raise ValueError("path_not_fifo")
    return path


def _starttime(pid):
    text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return int(text.rsplit(")", 1)[1].split()[19])


def _target_identity(pid, expected_start, expected_pgid):
    if pid <= 0 or expected_start <= 0 or expected_pgid <= 0:
        raise ValueError("invalid_target_identity")
    actual_start = _starttime(pid)
    actual_pgid = os.getpgid(pid)
    if actual_start != expected_start or actual_pgid != expected_pgid:
        raise ValueError("target_identity_changed")
    # Holding a pidfd prevents the supervisor from confusing a later process
    # with the checked target while this supervisor is alive (where supported).
    return os.pidfd_open(pid) if hasattr(os, "pidfd_open") else None


def _stop_and_reap(proc, deadline):
    events = []
    if proc.poll() is not None:
        return events + ["perf_already_exited", f"perf_exit:{proc.returncode}"]
    for sig in (signal.SIGINT, signal.SIGKILL):
        if time.monotonic() >= deadline:
            events.append("watchdog_deadline_exhausted")
            break
        try:
            os.killpg(proc.pid, sig)
            events.append(f"sent:{sig.name}")
        except (OSError, ProcessLookupError) as exc:
            events.append(f"signal_error:{type(exc).__name__}")
        try:
            proc.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            events.append("wait_timeout")
            continue
        events.append(f"perf_exit:{proc.returncode}")
        return events
    return events + (["reap_failed"] if proc.poll() is None else [f"perf_exit:{proc.returncode}"])


def run(args, *, popen=subprocess.Popen, clock=time.monotonic):
    if args.event != EVENT or args.frequency != FREQUENCY:
        return _fail("fixed_perf_parameters_required")
    if args.deadline <= clock() or args.deadline - clock() > MAX_WATCHDOG_S:
        return _fail("invalid_watchdog_deadline")
    try:
        output = _safe_path(args.output, allow_missing=False)
        output_stat = output.stat()
        if output_stat.st_uid != args.owner_uid or (output_stat.st_mode & 0o077):
            raise ValueError("output_ownership_or_mode_invalid")
        ctl = _safe_fifo(args.control)
        ack = _safe_fifo(args.ack)
        pidfd = _target_identity(args.target_pid, args.target_starttime,
                                 args.target_pgid)
    except (OSError, ValueError) as exc:
        return _fail(str(exc) if str(exc) in {
            "path_outside_allowed_root", "path_symlink", "path_not_regular",
            "path_missing", "path_not_fifo", "invalid_target_identity",
            "target_identity_changed", "output_ownership_or_mode_invalid"
        } else "identity_unavailable")
    argv = [PERF, "record", "-D", "-1", "-F", str(FREQUENCY), "-e", EVENT,
            "-p", str(args.target_pid), "-o", str(output),
            "--control", f"fifo:{ctl},{ack}"]
    proc = None
    try:
        proc = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      start_new_session=True, text=True)
        print(json.dumps({"status": "started", "perf_pid": proc.pid,
                          "deadline_monotonic": args.deadline},
                         separators=(",", ":")), flush=True)
        # stdin is the liveness channel.  EOF means the ordinary user
        # orchestrator disconnected; it is not a request to run any command.
        while proc.poll() is None and clock() < args.deadline:
            ready, _, _ = select.select([sys.stdin], [], [],
                                        max(0.001, args.deadline - clock()))
            if ready and not sys.stdin.readline():
                events = ["client_eof"] + _stop_and_reap(proc, args.deadline)
                print(json.dumps({"status": "recovered", "events": events},
                                 separators=(",", ":")), flush=True)
                return 0 if proc.poll() is not None else 4
        events = ["watchdog_deadline"] if proc.poll() is None else ["perf_exit_observed"]
        events += _stop_and_reap(proc, args.deadline)
        print(json.dumps({"status": "recovered" if proc.poll() is not None else "unconfirmed",
                          "events": events, "perf_exit": proc.poll()},
                         separators=(",", ":")), flush=True)
        return 0 if proc.poll() is not None else 4
    except (OSError, ValueError) as exc:
        if proc is not None and proc.poll() is None:
            _stop_and_reap(proc, args.deadline)
        return _fail("supervisor_runtime_error")
    finally:
        if pidfd is not None:
            try:
                os.close(pidfd)
            except OSError:
                pass


def parser():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument("--target-pid", type=int, required=True)
    p.add_argument("--target-starttime", type=int, required=True)
    p.add_argument("--target-pgid", type=int, required=True)
    p.add_argument("--event", required=True)
    p.add_argument("--frequency", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--owner-uid", type=int, required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--ack", required=True)
    p.add_argument("--deadline-monotonic", type=float, required=True)
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
