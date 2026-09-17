"""Resource scope sampler for the coding pilot (RUN-01, P1-03/04 subset).

Design points (methodology + docs/trace_contract.md §7):
- CPU: boundary cumulative-counter deltas, reported in core-seconds
  (usage_usec delta / 1e6). Counter resets are DETECTED, never reported as
  negative deltas; a reset segment contributes null + reason.
- Memory: cgroup memory.current (gauge), kernel memory.peak (if present)
  and the sampled max are three DIFFERENT numbers and are never summed or
  merged; without memory.peak the sampled max is labeled a lower bound.
- I/O: only reported when the scope exposes io.stat; missing/unsupported
  stays null — never zero. Page-cache effects are noted, not equated with
  application bytes.
- Sampling: fixed interval with actual per-sample timestamps and gaps
  recorded; the boundary counters (not the sample count) carry the CPU
  evidence for short bursts.
- Readers: production reads cgroup v2 files (read-only); tests inject
  scripted fake readers. Reader failures keep null + reason ("unreadable"
  and friends) — a null is never coerced to zero, and a REAL zero is kept
  (never dropped via `value or default`).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .semantic_recorder import Clock, SystemClock

SCOPE_KINDS = ("agent_container", "host_agent_runtime", "verifier_container",
               "collector")


@dataclass
class CounterSnapshot:
    """One scope counter read (all None-able; None = not observable)."""
    scope: str
    scope_kind: str
    t_monotonic_ns: int
    cpu_usage_usec: int | None = None
    mem_current_bytes: int | None = None
    mem_peak_bytes: int | None = None          # kernel peak; None if unsupported
    io_read_bytes: int | None = None
    io_write_bytes: int | None = None
    read_status: dict[str, str] = field(default_factory=dict)  # file -> ok/reason

    def to_dict(self) -> dict:
        """Full evidence serialization for archiving (no value dropped)."""
        return {"scope": self.scope, "scope_kind": self.scope_kind,
                "t_monotonic_ns": self.t_monotonic_ns,
                "cpu_usage_usec": self.cpu_usage_usec,
                "mem_current_bytes": self.mem_current_bytes,
                "mem_peak_bytes": self.mem_peak_bytes,
                "io_read_bytes": self.io_read_bytes,
                "io_write_bytes": self.io_write_bytes,
                "read_status": dict(self.read_status)}


class ScopeReader:
    """Reads counters for one scope. Subclasses may be read-only file
    readers (production) or scripted fakes (tests)."""

    def read(self, t_monotonic_ns: int) -> CounterSnapshot:  # pragma: no cover
        raise NotImplementedError


class CgroupV2FileReader(ScopeReader):
    """Read-only cgroup v2 counter files under a container's cgroup dir."""

    def __init__(self, scope: str, scope_kind: str, cgroup_dir: Path):
        self.scope = scope
        self.scope_kind = scope_kind
        self.cgroup_dir = cgroup_dir
        self.reads = 0  # countable for freeze-evidence assertions

    def _read_int(self, rel: str, status: dict[str, str]) -> int | None:
        path = self.cgroup_dir / rel
        try:
            text = path.read_text(encoding="ascii", errors="replace").strip()
        except FileNotFoundError:
            status[rel] = "not_found"
            return None
        except PermissionError:
            status[rel] = "permission_denied"
            return None
        except OSError as exc:
            status[rel] = f"error:{type(exc).__name__}"
            return None
        try:
            return int(text)
        except ValueError:
            status[rel] = "unparseable"
            return None

    def read(self, t_monotonic_ns: int) -> CounterSnapshot:
        status: dict[str, str] = {}

        cpu_usage_usec = None
        try:
            text = (self.cgroup_dir / "cpu.stat").read_text(
                encoding="ascii", errors="replace")
            for line in text.splitlines():
                key, _, value = line.partition(" ")
                if key == "usage_usec":
                    cpu_usage_usec = int(value.strip())
                    status["cpu.stat"] = "ok"
                    break
            else:
                status["cpu.stat"] = "usage_usec_missing"
        except (OSError, ValueError) as exc:
            status["cpu.stat"] = f"error:{type(exc).__name__}"

        mem_current = self._read_int("memory.current", status)
        mem_peak = self._read_int("memory.peak", status)

        io_read = io_write = None
        try:
            text = (self.cgroup_dir / "io.stat").read_text(
                encoding="ascii", errors="replace")
            read_sum = write_sum = 0
            seen = False
            for line in text.splitlines():
                fields = dict(part.split("=", 1) for part in line.split()
                              if "=" in part)
                if "rbytes" in fields or "wbytes" in fields:
                    seen = True
                    read_sum += int(fields.get("rbytes", 0))
                    write_sum += int(fields.get("wbytes", 0))
            if seen:
                io_read, io_write = read_sum, write_sum
                status["io.stat"] = "ok_summed_devices"
            else:
                status["io.stat"] = "no_device_rows"
        except FileNotFoundError:
            status["io.stat"] = "not_found"
        except (OSError, ValueError) as exc:
            status["io.stat"] = f"error:{type(exc).__name__}"

        return CounterSnapshot(scope=self.scope, scope_kind=self.scope_kind,
                               t_monotonic_ns=t_monotonic_ns,
                               cpu_usage_usec=cpu_usage_usec,
                               mem_current_bytes=mem_current,
                               mem_peak_bytes=mem_peak,
                               io_read_bytes=io_read,
                               io_write_bytes=io_write,
                               read_status=status)


class CgroupV1FileReader(ScopeReader):
    """Read-only cgroup v1 counter files for one docker container.

    Layout (verified on the pilot host: docker 25.0.5, cgroupfs driver,
    cgroup v1): /sys/fs/cgroup/<controller>/docker/<full-container-id>/.

    Mappings into CounterSnapshot:
    - cpuacct.usage (NANOSECONDS) -> cpu_usage_usec (converted /1000; the
      conversion is recorded in read_status)
    - memory.usage_in_bytes       -> mem_current_bytes
    - memory.max_usage_in_bytes   -> mem_peak_bytes (v1 HAS a kernel-tracked
      peak; basis recorded as v1_max_usage_in_bytes)
    - blkio.io_service_bytes(_recursive), summed over devices -> io bytes
    """

    CG_ROOT = Path("/sys/fs/cgroup")

    def __init__(self, scope: str, scope_kind: str, container_id: str,
                 *, cg_root: Path | None = None):
        self.scope = scope
        self.scope_kind = scope_kind
        self.container_id = container_id
        self.cg_root = cg_root or self.CG_ROOT
        self.reads = 0  # countable for freeze-evidence assertions

    def _read_text(self, path: Path, status: dict, key: str) -> str | None:
        try:
            text = path.read_text(encoding="ascii", errors="replace").strip()
            status[key] = "ok"
            return text
        except FileNotFoundError:
            status[key] = "not_found"
        except PermissionError:
            status[key] = "permission_denied"
        except OSError as exc:
            status[key] = f"error:{type(exc).__name__}"
        return None

    def read(self, t_monotonic_ns: int) -> CounterSnapshot:
        self.reads += 1
        status: dict[str, str] = {}
        cid = self.container_id
        cpu_dir = self.cg_root / "cpu,cpuacct" / "docker" / cid
        mem_dir = self.cg_root / "memory" / "docker" / cid
        blkio_dir = self.cg_root / "blkio" / "docker" / cid

        cpu_usage_usec = None
        text = self._read_text(cpu_dir / "cpuacct.usage", status, "cpuacct.usage")
        if text is not None:
            try:
                cpu_usage_usec = int(text) // 1000  # ns -> usec
                status["cpuacct.usage"] = "ok_ns_converted_to_usec"
            except ValueError:
                status["cpuacct.usage"] = "unparseable"

        def _int(path: Path, key: str) -> int | None:
            t = self._read_text(path, status, key)
            if t is None:
                return None
            try:
                return int(t)
            except ValueError:
                status[key] = "unparseable"
                return None

        mem_current = _int(mem_dir / "memory.usage_in_bytes",
                           "memory.usage_in_bytes")
        mem_peak = _int(mem_dir / "memory.max_usage_in_bytes",
                        "memory.max_usage_in_bytes")

        io_read = io_write = None
        # v1 blkio file names differ by kernel/io-scheduler era: the plain
        # names are CFQ-era (removed in newer kernels); throttle.* exists
        # whenever blk-throttle is enabled; bfq.* only when the device uses
        # the BFQ scheduler. An EXISTING file with zero device rows means
        # "supported, nothing counted yet" -> real zero, not missing; a
        # missing file means unsupported -> null.
        io_candidates = ("blkio.io_service_bytes_recursive",
                         "blkio.io_service_bytes",
                         "blkio.throttle.io_service_bytes_recursive",
                         "blkio.throttle.io_service_bytes",
                         "blkio.bfq.io_service_bytes_recursive",
                         "blkio.bfq.io_service_bytes")
        for name in io_candidates:
            text = self._read_text(blkio_dir / name, status, name)
            if text is None:
                continue  # file absent: try next candidate
            read_sum = write_sum = 0
            seen = False
            for line in text.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[1] in ("Read", "Write"):
                    seen = True
                    if parts[1] == "Read":
                        read_sum += int(parts[2])
                    else:
                        write_sum += int(parts[2])
            if seen:
                io_read, io_write = read_sum, write_sum
                status["io"] = f"ok_summed_devices:{name}"
                break
            if text == "" or text == "Total 0":
                # empty file or the v1 "no records yet" marker: supported
                # with nothing counted -> REAL ZERO, not missing
                io_read, io_write = 0, 0
                status["io"] = f"ok_no_records_real_zero:{name}"
                break
            status[name] = "unparseable_content"
        if io_read is None and io_write is None and "io" not in status:
            status["io"] = "io_files_unavailable"

        return CounterSnapshot(scope=self.scope, scope_kind=self.scope_kind,
                               t_monotonic_ns=t_monotonic_ns,
                               cpu_usage_usec=cpu_usage_usec,
                               mem_current_bytes=mem_current,
                               mem_peak_bytes=mem_peak,
                               io_read_bytes=io_read,
                               io_write_bytes=io_write,
                               read_status=status)


class FakeCounterReader(ScopeReader):
    """Scripted snapshots for synthetic tests (reset/missing/zero aware).

    When the scripted list is exhausted the LAST snapshot repeats (with an
    exhausted marker) so boundary reads always observe something."""

    def __init__(self, scope: str, scope_kind: str,
                 snapshots: list[CounterSnapshot]):
        self.scope = scope
        self.scope_kind = scope_kind
        self._snapshots = list(snapshots)
        self.reads = 0

    def read(self, t_monotonic_ns: int) -> CounterSnapshot:
        self.reads += 1
        if not self._snapshots:
            return CounterSnapshot(scope=self.scope, scope_kind=self.scope_kind,
                                   t_monotonic_ns=t_monotonic_ns,
                                   read_status={"all": "exhausted_no_data"})
        snap = self._snapshots[0]
        if len(self._snapshots) > 1:
            snap = self._snapshots.pop(0)
        else:
            snap = CounterSnapshot(
                scope=snap.scope, scope_kind=snap.scope_kind,
                t_monotonic_ns=snap.t_monotonic_ns,
                cpu_usage_usec=snap.cpu_usage_usec,
                mem_current_bytes=snap.mem_current_bytes,
                mem_peak_bytes=snap.mem_peak_bytes,
                io_read_bytes=snap.io_read_bytes,
                io_write_bytes=snap.io_write_bytes,
                read_status={**snap.read_status, "note": "repeated_last"})
        snap.t_monotonic_ns = t_monotonic_ns
        return snap


def cpu_core_seconds(start: CounterSnapshot,
                     end: CounterSnapshot) -> tuple[float | None, str | None]:
    """Boundary-delta CPU in core-seconds; (None, reason) when unusable."""
    if start.cpu_usage_usec is None or end.cpu_usage_usec is None:
        missing = [n for n, v in (("start", start.cpu_usage_usec),
                                  ("end", end.cpu_usage_usec)) if v is None]
        return None, f"cpu_usage_usec_missing:{','.join(missing)}"
    if end.cpu_usage_usec < start.cpu_usage_usec:
        return None, "counter_reset_detected"
    return (end.cpu_usage_usec - start.cpu_usage_usec) / 1_000_000.0, None


def io_interval_bytes(start: CounterSnapshot | None,
                      end: CounterSnapshot | None
                      ) -> tuple[int | None, int | None, str | None]:
    """Boundary-delta I/O in BYTES over the interval (NOT the cumulative
    end value). Read and write are handled independently: a counter that is
    missing at either boundary stays null (with reason), a counter reset
    (end < start) yields null + reason — never a negative delta. Reasons
    for both directions are joined when both are unusable."""
    if start is None or end is None:
        return None, None, "io_boundary_missing"
    reasons: list[str] = []
    read_delta: int | None = None
    write_delta: int | None = None
    if start.io_read_bytes is None or end.io_read_bytes is None:
        reasons.append("io_read_missing_at_boundary")
    elif end.io_read_bytes < start.io_read_bytes:
        reasons.append("io_read_reset_detected")
    else:
        read_delta = end.io_read_bytes - start.io_read_bytes
    if start.io_write_bytes is None or end.io_write_bytes is None:
        reasons.append("io_write_missing_at_boundary")
    elif end.io_write_bytes < start.io_write_bytes:
        reasons.append("io_write_reset_detected")
    else:
        write_delta = end.io_write_bytes - start.io_write_bytes
    return read_delta, write_delta, (";".join(reasons) if reasons else None)


@dataclass
class ScopeSamples:
    """All observations for one scope over one run attempt."""
    scope: str
    scope_kind: str
    interval_target_s: float
    boundary_start: CounterSnapshot | None = None
    boundary_end: CounterSnapshot | None = None
    samples: list[CounterSnapshot] = field(default_factory=list)
    sample_gaps_ns: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Metric summary with evidence/missing reasons, no fake zeros."""
        out: dict[str, Any] = {"scope": self.scope, "scope_kind": self.scope_kind,
                               "interval_target_s": self.interval_target_s,
                               "n_samples": len(self.samples)}
        if self.boundary_start is not None and self.boundary_end is not None:
            core_s, reason = cpu_core_seconds(self.boundary_start,
                                              self.boundary_end)
            out["cpu_core_seconds"] = core_s
            out["cpu_core_seconds_reason"] = reason  # None when observed
            out["cpu_evidence"] = "counter_boundary"
            if (core_s is not None and self.samples
                    and self.boundary_end.t_monotonic_ns
                    > self.boundary_start.t_monotonic_ns):
                wall = ((self.boundary_end.t_monotonic_ns
                         - self.boundary_start.t_monotonic_ns) / 1e9)
                out["wall_s"] = wall
                out["avg_cores"] = core_s / wall if wall > 0 else None
                out["avg_cores_note"] = ("avg cores = cpu/wall; NOT an "
                                         "efficiency metric")
        else:
            out["cpu_core_seconds"] = None
            out["cpu_core_seconds_reason"] = "boundary_missing"

        peak = None
        if self.boundary_end is not None:
            peak = self.boundary_end.mem_peak_bytes
        sampled_max = None
        n_out_of_window = 0
        lo = self.boundary_start.t_monotonic_ns \
            if self.boundary_start else None
        hi = self.boundary_end.t_monotonic_ns if self.boundary_end else None
        for snap in self.samples:
            if lo is not None and hi is not None \
                    and not lo <= snap.t_monotonic_ns <= hi:
                n_out_of_window += 1  # preserved in evidence, excluded
                continue               # from in-window peak/sample metrics
            if snap.mem_current_bytes is not None:
                sampled_max = (snap.mem_current_bytes if sampled_max is None
                               else max(sampled_max, snap.mem_current_bytes))
        out["n_samples_out_of_boundary"] = n_out_of_window
        if n_out_of_window:
            out["out_of_boundary_note"] = (
                "samples with timestamps outside [boundary_start, "
                "boundary_end] are preserved in evidence() but excluded "
                "from in-window metrics (peak, sampled max); they are "
                "listed for the audit view")
        out["memory_current_end_bytes"] = (self.boundary_end.mem_current_bytes
                                           if self.boundary_end else None)
        out["memory_kernel_peak_bytes"] = peak
        if peak is None and sampled_max is not None:
            out["memory_sampled_max_bytes"] = sampled_max
            out["memory_peak_basis"] = "sampled_lower_bound"
        elif peak is not None:
            out["memory_sampled_max_bytes"] = sampled_max
            peak_status = (self.boundary_end.read_status
                           if self.boundary_end else {})
            out["memory_peak_basis"] = (
                "v1_max_usage_in_bytes"
                if peak_status.get("memory.max_usage_in_bytes") == "ok"
                else "kernel_memory.peak")
        else:
            out["memory_sampled_max_bytes"] = None
            out["memory_peak_basis"] = "unavailable"
        out["memory_note"] = ("current/kernel-peak/sampled-max are distinct; "
                              "scope peaks are never summed into a run peak")

        # I/O: INTERVAL delta (end-start), not the cumulative end value.
        read_delta, write_delta, io_reason = io_interval_bytes(
            self.boundary_start, self.boundary_end)
        io: dict[str, Any] = {
            "read_bytes": read_delta,
            "write_bytes": write_delta,
            "evidence": "io.stat_boundary_delta",
            "reason": io_reason,
        }
        if self.boundary_end is not None:
            io["cumulative_end"] = {
                "read_bytes": self.boundary_end.io_read_bytes,
                "write_bytes": self.boundary_end.io_write_bytes,
                "note": "cumulative counter value at final boundary "
                        "(reference only; NOT the interval amount)",
            }
        if read_delta is None and write_delta is None:
            io["note"] = ("interval I/O unavailable (see reason); null kept, "
                          "not zeroed; block I/O != application bytes")
        out["io"] = io
        out["notes"] = list(self.notes)
        return out

    def evidence(self) -> dict[str, Any]:
        """FULL raw evidence for archiving: boundary snapshots, every gauge
        sample with its timestamp, sampling gaps and notes. Summaries are
        derived views; this is what makes them checkable afterwards."""
        return {
            "scope": self.scope,
            "scope_kind": self.scope_kind,
            "interval_target_s": self.interval_target_s,
            "boundary_start": (self.boundary_start.to_dict()
                               if self.boundary_start else None),
            "boundary_end": (self.boundary_end.to_dict()
                             if self.boundary_end else None),
            "samples": [snap.to_dict() for snap in self.samples],
            "sample_gaps_ns": list(self.sample_gaps_ns),
            "notes": list(self.notes),
        }


class ResourceSampler:
    """Samples gauge series + boundary counters for registered scopes.

    The sampler runs OUTSIDE the measured scopes (its own cost is recorded
    under the 'collector' scope by the caller)."""

    def __init__(self, clock: Clock | None = None,
                 interval_s: float = 0.5):
        self.clock = clock or SystemClock()
        self.interval_s = interval_s
        self._readers: dict[str, ScopeReader] = {}
        self._read_gates: dict[str, threading.Lock] = {}
        self._data: dict[str, ScopeSamples] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def register(self, scope: str, scope_kind: str, reader: ScopeReader) -> None:
        if scope_kind not in SCOPE_KINDS:
            raise ValueError(f"unknown scope kind: {scope_kind!r}")
        with self._lock:
            if scope in self._readers:
                raise ValueError(f"scope already registered: {scope!r}")
            self._readers[scope] = reader
            self._data[scope] = ScopeSamples(scope=scope, scope_kind=scope_kind,
                                             interval_target_s=self.interval_s)

    def start(self, scope: str) -> None:
        """Take the boundary-baseline read for a scope."""
        with self._lock:
            if scope not in self._readers:
                raise KeyError(scope)
        snap = self._readers[scope].read(self.clock.monotonic_ns())
        with self._lock:
            self._data[scope].boundary_start = snap
            if snap.read_status.get("cpu.stat") != "ok":
                self._data[scope].notes.append(
                    f"baseline_cpu_unreadable:{snap.read_status.get('cpu.stat')}")

    def stop(self, scope: str) -> None:
        """Take the final boundary read BEFORE any scope teardown.

        RACE-FREE stop: a sampling round may be mid-read for this scope
        when stop() is called. stop() acquires the scope's read gate —
        the same gate the sampling loop holds around each read — so it
        WAITS for any in-flight read to finish, then takes the final
        boundary and returns. The reviewer's repro (pause sampling ->
        stop() -> resume: a read completed after stop returned, with the
        sample not appended) is closed: the in-flight read either
        completes and appends BEFORE the boundary is taken, or is
        excluded by the boundary check in sample_once; either way the
        final boundary is strictly the LAST read that happened."""
        with self._lock:
            if scope not in self._readers:
                raise KeyError(scope)
            gate = self._read_gates.setdefault(scope, threading.Lock())
        with gate:  # wait for any in-flight sampling read on this scope
            with self._lock:
                stopped = self._data[scope].boundary_end is not None
            if stopped:
                return  # idempotent
            snap = self._readers[scope].read(self.clock.monotonic_ns())
            with self._lock:
                self._data[scope].boundary_end = snap

    def start_background_sampling(self) -> None:
        if self._thread is not None:
            raise RuntimeError("sampling thread already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop_background_sampling(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_s * 4))
            self._thread = None

    def sample_once(self) -> None:
        """One sampling round over all registered scopes (also the loop
        body; exposed for deterministic tests).

        A scope whose boundary_end is already taken (stop() was called
        for THAT scope) is SKIPPED — no further reads, no appended
        samples — while other still-active scopes keep sampling. Each
        read is bracketed by the scope's read gate so a concurrent
        stop() waits for the in-flight read instead of racing it."""
        with self._lock:
            readers = list(self._readers.items())
        for scope, reader in readers:
            with self._lock:
                data = self._data[scope]
                stopped = data.boundary_end is not None
                gate = self._read_gates.setdefault(scope,
                                                    threading.Lock())
            if stopped:
                continue  # this scope's final boundary is taken: frozen
            with gate:  # excludes a concurrent stop() boundary read
                with self._lock:
                    if self._data[scope].boundary_end is not None:
                        continue  # stopped while we waited for the gate
                snap = reader.read(self.clock.monotonic_ns())
                with self._lock:
                    data = self._data[scope]
                    if data.boundary_end is not None:
                        continue  # stopped between the read and append
                    if data.samples:
                        gap = snap.t_monotonic_ns - data.samples[-1].t_monotonic_ns
                        data.sample_gaps_ns.append(gap)
                    data.samples.append(snap)

    def _sample_loop(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            self._stop.wait(self.interval_s)

    def samples(self, scope: str) -> ScopeSamples:
        return self._data[scope]

    def all_scope_summaries(self) -> dict[str, dict]:
        return {scope: data.summary() for scope, data in self._data.items()}

    def all_scope_evidence(self) -> dict[str, dict]:
        """Full raw evidence per scope (for the archived samples.json)."""
        return {scope: data.evidence() for scope, data in self._data.items()}

    def collector_self_observation(self) -> dict[str, Any]:
        """Sampler's own cost statement (scope: collector)."""
        with self._lock:
            n = sum(len(d.samples) for d in self._data.values())
        return {"scope": "collector",
                "sampling_interval_s": self.interval_s,
                "total_reads": n,
                "note": ("collector runs outside measured scopes; its own "
                         "CPU/RSS is not included in any measured scope "
                         "and must be stated separately")}
