"""G1-01 A3: minimal host-process observation (standard library, /proc).

Reads are restricted to processes THIS run created (the mini child and
its monitor thread's own timing); no unrelated-process command lines or
environ are touched. Semantics:

- identity: PID + starttime (field 22 of /proc/<pid>/stat) — a reused
  PID with a different starttime is detected, not silently accepted;
- CPU: utime+stime ticks converted with the ACTUAL CLK_TCK; the value
  is a cumulative counter (delta between two reads is the interval
  CPU); a read after process exit yields null + reason (the last
  readable value is kept as diagnostic, never as a verified final);
- RSS: resident pages * actual page size; current/sampled-max/kernel
  peak are distinct; RSS values are never summed across processes;
- collector cost: every read's own wall duration is measured and
  accumulated (this is the collector-overhead metric, distinct from
  any workload measurement).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROC = Path("/proc")


@dataclass
class HostSnapshot:
    pid: int
    starttime_ticks: int | None
    t_monotonic_ns: int
    cpu_ticks: int | None          # utime + stime
    rss_bytes: int | None          # resident pages * page size
    read_status: dict[str, str] = field(default_factory=dict)


class HostProcessReader:
    """Reads CPU/RSS for ONE process identity (pid + starttime).

    ``proc_root`` is injectable for fixture tests; production reads
    /proc. ``expected_starttime`` pins the identity: a mismatch (PID
    reuse) is reported, not mistaken for the original process."""

    def __init__(self, pid: int, *, expected_starttime: int | None = None,
                 proc_root: Path | None = None):
        self.pid = pid
        self.expected_starttime = expected_starttime
        self.root = proc_root or _PROC
        self.clk_tck = os.sysconf("SC_CLK_TCK")
        self.page_size = os.sysconf("SC_PAGE_SIZE")
        self.read_count = 0
        self.read_wall_ns_total = 0

    def read(self, t_monotonic_ns: int | None = None) -> HostSnapshot:
        t0 = time.monotonic_ns()
        t = t_monotonic_ns if t_monotonic_ns is not None \
            else time.monotonic_ns()
        status: dict[str, str] = {}
        snap = HostSnapshot(pid=self.pid, starttime_ticks=None,
                            t_monotonic_ns=t, cpu_ticks=None,
                            rss_bytes=None, read_status=status)
        try:
            stat = (self.root / str(self.pid) / "stat").read_text(
                encoding="ascii", errors="replace")
        except FileNotFoundError:
            status["stat"] = "process_exited"
            self._account_read(t0)
            return snap
        except PermissionError:
            status["stat"] = "permission_denied"
            self._account_read(t0)
            return snap
        except OSError as exc:
            status["stat"] = f"error:{type(exc).__name__}"
            self._account_read(t0)
            return snap
        # comm may contain spaces/parens: fields start after the LAST ')'
        try:
            rest = stat.rsplit(")", 1)[1].split()
            # rest[0] = state (field 3); stat fields 14/15/22/24 ->
            # rest indices 11/12/19/21
            utime, stime = int(rest[11]), int(rest[12])
            starttime = int(rest[19])
            rss_pages = int(rest[21])
        except (IndexError, ValueError):
            status["stat"] = "unparseable"
            self._account_read(t0)
            return snap
        if self.expected_starttime is not None \
                and starttime != self.expected_starttime:
            status["stat"] = "pid_reuse_detected"
            snap.starttime_ticks = starttime
            self._account_read(t0)
            return snap
        status["stat"] = "ok"
        snap.starttime_ticks = starttime
        snap.cpu_ticks = utime + stime
        snap.rss_bytes = rss_pages * self.page_size
        self._account_read(t0)
        return snap

    def _account_read(self, t0: int) -> None:
        self.read_count += 1
        self.read_wall_ns_total += time.monotonic_ns() - t0

    # -- derived helpers ----------------------------------------------------

    def cpu_seconds_delta(self, first: HostSnapshot,
                          last: HostSnapshot) -> tuple[float | None,
                                                       str | None]:
        if first.cpu_ticks is None or last.cpu_ticks is None:
            return None, "cpu_ticks_missing_at_boundary"
        if last.cpu_ticks < first.cpu_ticks:
            return None, "counter_reset_detected"
        return (last.cpu_ticks - first.cpu_ticks) / self.clk_tck, None


def read_starttime(pid: int, *, proc_root: Path | None = None) -> int | None:
    """starttime ticks for a pid (identity pin), or None if unreadable."""
    root = proc_root or _PROC
    try:
        stat = (root / str(pid) / "stat").read_text(
            encoding="ascii", errors="replace")
        rest = stat.rsplit(")", 1)[1].split()
        return int(rest[19])
    except (OSError, IndexError, ValueError):
        return None


class HostProcessMonitor:
    """Polls one process identity into a JSONL of snapshots.

    Used by the mini harness parent around its child. Snapshots are
    appended with the parent's monotonic clock; the FINAL read after
    exit typically yields process_exited (null) — the last readable
    value stays a diagnostic, never a verified final."""

    def __init__(self, pid: int, *, expected_starttime: int | None = None,
                 interval_s: float = 0.1, proc_root: Path | None = None):
        self.reader = HostProcessReader(pid,
                                        expected_starttime=expected_starttime,
                                        proc_root=proc_root)
        self.interval_s = interval_s
        self.snapshots: list[HostSnapshot] = []

    def poll_once(self) -> HostSnapshot:
        snap = self.reader.read()
        self.snapshots.append(snap)
        return snap

    def summary(self) -> dict[str, Any]:
        readable = [s for s in self.snapshots
                    if s.read_status.get("stat") == "ok"]
        cpu_s, cpu_reason = (None, "no_two_readable_snapshots")
        if len(readable) >= 2:
            cpu_s, cpu_reason = self.reader.cpu_seconds_delta(
                readable[0], readable[-1])
        rss_max = max((s.rss_bytes for s in readable
                       if s.rss_bytes is not None), default=None)
        last_readable = readable[-1] if readable else None
        return {
            "scope": "host_mini_child",
            "pid": self.reader.pid,
            "starttime_ticks": self.reader.expected_starttime,
            "clk_tck": self.reader.clk_tck,
            "page_size": self.reader.page_size,
            "n_snapshots": len(self.snapshots),
            "n_readable": len(readable),
            "cpu_seconds": cpu_s,
            "cpu_seconds_reason": cpu_reason,
            "cpu_basis": "utime+stime tick delta between first/last "
                         "READABLE snapshots (interval, not lifetime)",
            "rss_current_last_readable": (last_readable.rss_bytes
                                          if last_readable else None),
            "rss_sampled_max": rss_max,
            "rss_note": "current/sampled-max distinct; kernel peak not "
                        "read at process level; RSS never summed across "
                        "processes",
            "final_read_status": (self.snapshots[-1].read_status.get("stat")
                                  if self.snapshots else "no_snapshots"),
            "final_value_note": ("a process_exited final read means the "
                                 "verified final is null; the last "
                                 "readable value is diagnostic only"),
            "collector": {
                "read_count": self.reader.read_count,
                "read_wall_ns_total": self.reader.read_wall_ns_total,
                "read_wall_ns_mean": (
                    self.reader.read_wall_ns_total / self.reader.read_count
                    if self.reader.read_count else None),
                "note": "collector read cost measured separately from any "
                        "workload metric; runner-process CPU/RSS is "
                        "host_runner_process (includes collector), never "
                        "double-counted as exclusive",
            },
            "coverage_gaps": [
                "descendants (docker exec clients) not individually "
                "tracked; short-lived grandchildren may be missed",
                "kernel-peak (VmHWM) not recorded at host scope this batch",
            ],
        }
