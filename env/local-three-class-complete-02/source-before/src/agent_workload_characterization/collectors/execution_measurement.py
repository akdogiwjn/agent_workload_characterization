"""Mandatory real-run observation contract; no experiments or external probes.

Reuse SemanticRecorder for spans. This module only snapshots local metadata,
wraps the existing async LLM call, and checks saved observation coverage.
"""
from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

CONTRACT_VERSION = "real-run-measurement-v3"
CONTRACT = {
    "version": CONTRACT_VERSION,
    "required": ["identity_and_configuration", "environment_snapshot",
                 "lifecycle_and_cleanup", "logical_requests_and_usage",
                 "tool_and_bootstrap_spans", "resource_scope_and_boundaries",
                 "sampling_quality_and_read_cost", "independent_outcomes",
                 "archive_hashes_and_coverage", "network_namespace_counters",
                 "task_output_footprint_boundaries"],
    "explicit_unavailable": ["actual_transport_attempts_without_transport_hook",
                             "remote_cpu_memory", "task_exclusive_network_bytes",
                             "http_application_bytes",
                             "exclusive_tool_cpu", "pmu_and_function_hotspots",
                             "uncontrolled_cache_state"],
    "timing": "same-host system_monotonic; client logical call includes retries",
    "io": "cgroup block service bytes are not application/filesystem bytes",
    "network": "process network namespace interface counters are shared scope; not PID, HTTP payload, or TLS-inclusive bytes",
    "disk_footprint": "explicit host-output and task-container directory boundaries use apparent file sizes; shared caches remain unavailable; ToolSandbox scenario state is in-memory",
    "missing": "null plus reason; observed zero is preserved",
}


def counter_rate_intervals(rows: list[dict], counters: dict[str, dict], *,
                           timestamp_field: str = "t_monotonic_ns") -> list[dict]:
    """Project raw cumulative counters into adjacent, gap-preserving intervals.

    A counter spec contains ``path``, ``unit``, stable ``identity_paths``,
    and optionally ``status_paths`` (alternative status locations),
    ``accepted_status_prefixes``, ``divisor`` or ``divisor_path``. Both
    endpoints must have valid reads and the same non-missing identity. Gaps
    are per metric; one counter's failure does not invalidate its neighbors.
    """
    def get(row, path):
        value = row
        for key in (path if isinstance(path, (list, tuple)) else (path,)):
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    intervals = []
    for left, right in zip(rows, rows[1:]):
        t0, t1 = left.get(timestamp_field), right.get(timestamp_field)
        dt = ((t1 - t0) / 1e9 if type(t0) is int and type(t1) is int
              and t0 >= 0 and t1 > t0 else None)
        row = {"t_start_ns": t0 if type(t0) is int else None,
               "t_end_ns": t1 if type(t1) is int else None,
               "delta_wall_s": dt, "metrics": {}}
        for name, spec in counters.items():
            a, b = get(left, spec["path"]), get(right, spec["path"])
            reason = None
            if dt is None:
                reason = "nonpositive_or_invalid_time_delta"
            identity_paths = spec.get("identity_paths")
            if identity_paths is None and spec.get("scope_path"):
                identity_paths = [spec["scope_path"]]
            if reason is None and identity_paths:
                left_identity = [get(left, path) for path in identity_paths]
                right_identity = [get(right, path) for path in identity_paths]
                if any(value is None or isinstance(value, bool) for value in left_identity + right_identity):
                    reason = "scope_identity_missing"
                elif left_identity != right_identity:
                    reason = "scope_identity_changed"
            elif reason is None:
                reason = "scope_identity_not_configured"
            if reason is None and (type(a) is not int or type(b) is not int):
                reason = "counter_missing_or_invalid"
            elif reason is None and (a < 0 or b < 0):
                reason = "negative_counter"
            elif reason is None and b < a:
                reason = "counter_decreased"
            divisor = spec.get("divisor", 1)
            if reason is None and spec.get("divisor_path"):
                divisor_left = get(left, spec["divisor_path"])
                divisor_right = get(right, spec["divisor_path"])
                if (isinstance(divisor_left, bool) or not isinstance(divisor_left, (int, float))
                        or isinstance(divisor_right, bool) or not isinstance(divisor_right, (int, float))):
                    reason = "unit_conversion_unavailable"
                elif divisor_left != divisor_right:
                    reason = "unit_conversion_changed"
                else:
                    divisor = divisor_left
            if reason is None and (isinstance(divisor, bool) or
                    not isinstance(divisor, (int, float)) or
                    not math.isfinite(divisor) or divisor <= 0):
                reason = "unit_conversion_unavailable"
            status_paths = spec.get("status_paths") or ([spec["status_path"]]
                                                           if spec.get("status_path") else [])
            if reason is None and not status_paths:
                reason = "reader_status_not_configured"
            if reason is None:
                accepted = spec.get("accepted_status_prefixes", ("ok",))
                for endpoint, sample in (("left", left), ("right", right)):
                    statuses = [get(sample, path) for path in status_paths]
                    if not any(isinstance(status, str) and
                               any(status.startswith(prefix) for prefix in accepted)
                               for status in statuses):
                        reason = f"reader_status_{endpoint}:" + ",".join(
                            str(status) if status is not None else "missing" for status in statuses)
                        break
            delta = None if reason else b - a
            scaled = None if reason else delta / float(divisor)
            rate = None if reason else scaled / dt
            row["metrics"][name] = {
                "delta": scaled, "rate_per_s": rate, "unit": spec["unit"],
                "rate_unit": spec.get("rate_unit", spec["unit"] + "_per_s"),
                "status": "valid" if reason is None else "gap",
                "reason": reason,
            }
        intervals.append(row)
    return intervals


def office_resource_rate_intervals(samples: list[dict], *,
                                   container_id: str | None) -> dict:
    """Project DocOps' saved nested sample shape without flattening statuses.

    Container identity comes from the run's container_identified event; the
    host process identity is PID plus starttime. CLK_TCK is taken per sample.
    """
    rows = []
    for original in samples:
        row = dict(original)
        container = dict(row.get("container") or {})
        if not container.get("container_id"):
            container["container_id"] = container_id
        row["container"] = container
        rows.append(row)
    container_identity = [("container", "container_id")]
    host_identity = [("host_agent", "pid"), ("host_agent", "starttime_ticks")]
    container_status_cpu = [("container", "read_status", "cpu.stat"),
                            ("container", "read_status", "cpuacct.usage")]
    container_status_io = [("container", "read_status", "io.stat"),
                           ("container", "read_status", "io")]
    return {
        "container": counter_rate_intervals(rows, {
            "cpu": {"path": ("container", "cpu_usage_usec"), "divisor": 1_000_000,
                    "unit": "cpu_seconds", "rate_unit": "average_core",
                    "identity_paths": container_identity,
                    "status_paths": container_status_cpu},
            "io_read": {"path": ("container", "io_read_bytes"), "unit": "bytes",
                        "rate_unit": "bytes_per_second", "identity_paths": container_identity,
                        "status_paths": container_status_io},
            "io_write": {"path": ("container", "io_write_bytes"), "unit": "bytes",
                         "rate_unit": "bytes_per_second", "identity_paths": container_identity,
                         "status_paths": container_status_io}}),
        "host_agent_process": counter_rate_intervals(rows, {
            "cpu": {"path": ("host_agent", "cpu_ticks"),
                    "divisor_path": ("host_agent", "clk_tck"),
                    "unit": "cpu_seconds", "rate_unit": "average_core",
                    "identity_paths": host_identity,
                    "status_paths": [("host_agent", "read_status", "stat")]},
            "proc_rchar": {"path": ("host_agent", "process_io", "rchar"), "unit": "bytes",
                           "rate_unit": "bytes_per_second", "identity_paths": host_identity,
                           "status_paths": [("host_agent", "read_status", "io")]},
            "proc_wchar": {"path": ("host_agent", "process_io", "wchar"), "unit": "bytes",
                           "rate_unit": "bytes_per_second", "identity_paths": host_identity,
                           "status_paths": [("host_agent", "read_status", "io")]},
            "proc_read_bytes": {"path": ("host_agent", "process_io", "read_bytes"), "unit": "bytes",
                                "rate_unit": "bytes_per_second", "identity_paths": host_identity,
                                "status_paths": [("host_agent", "read_status", "io")]},
            "proc_write_bytes": {"path": ("host_agent", "process_io", "write_bytes"), "unit": "bytes",
                                 "rate_unit": "bytes_per_second", "identity_paths": host_identity,
                                 "status_paths": [("host_agent", "read_status", "io")]}}),
    }


def read_network_namespace(proc_root: Path = Path("/proc"), *,
                           t_monotonic_ns: int | None = None) -> dict:
    """Read interface counters for this process's network namespace.

    These are namespace-wide counters, not PID-exclusive or application-layer
    bytes. No socket inspection, packet capture, or credential access occurs.
    """
    stamp = time.monotonic_ns() if t_monotonic_ns is None else t_monotonic_ns
    ns_path = proc_root / "self" / "ns" / "net"
    dev_path = proc_root / "self" / "net" / "dev"
    try:
        namespace_id = os.readlink(ns_path)
    except OSError as exc:
        namespace_id = None
        namespace_status = type(exc).__name__
    else:
        namespace_status = "observed"
    interfaces = {}
    try:
        lines = dev_path.read_text(encoding="ascii", errors="replace").splitlines()[2:]
        for line in lines:
            name, sep, counters = line.partition(":")
            values = counters.split()
            if not sep or len(values) < 9:
                continue
            interfaces[name.strip()] = {"rx_bytes": int(values[0]),
                                        "tx_bytes": int(values[8])}
        read_status = "observed" if interfaces else "no_interfaces"
    except OSError as exc:
        read_status = type(exc).__name__
    except ValueError:
        read_status = "unparseable"
    return {"scope": "current_process_network_namespace",
            "scope_kind": "network_namespace_shared",
            "namespace_id": namespace_id,
            "namespace_status": namespace_status,
            "t_monotonic_ns": stamp,
            "interfaces": interfaces,
            "read_status": read_status,
            "counter_basis": "kernel interface tx/rx bytes; namespace-wide, not PID or HTTP payload bytes"}


def network_rate_intervals(rows: list[dict]) -> list[dict]:
    """Compute per-interface namespace byte rates; preserve invalid intervals."""
    specs = {
        "rx_bytes": {"path": ("interfaces", "{interface}", "rx_bytes"), "unit": "bytes"},
        "tx_bytes": {"path": ("interfaces", "{interface}", "tx_bytes"), "unit": "bytes"},
    }
    output = []
    for left, right in zip(rows, rows[1:]):
        t0, t1 = left.get("t_monotonic_ns"), right.get("t_monotonic_ns")
        dt = ((t1 - t0) / 1e9 if type(t0) is int and type(t1) is int
              and t0 >= 0 and t1 > t0 else None)
        interfaces = sorted(set(left.get("interfaces", {})) | set(right.get("interfaces", {})))
        for interface in interfaces:
            item = {"interface": interface, "t_start_ns": t0 if type(t0) is int else None,
                    "t_end_ns": t1 if type(t1) is int else None, "delta_wall_s": dt,
                    "metrics": {}}
            for metric in specs:
                a = left.get("interfaces", {}).get(interface, {}).get(metric)
                b = right.get("interfaces", {}).get(interface, {}).get(metric)
                reason = None
                if dt is None:
                    reason = "nonpositive_or_invalid_time_delta"
                elif (not left.get("namespace_id") or
                      left.get("namespace_id") != right.get("namespace_id")):
                    reason = "network_namespace_identity_missing_or_changed"
                elif left.get("namespace_status") != "observed" or right.get("namespace_status") != "observed":
                    reason = "network_namespace_identity_unreadable"
                elif left.get("read_status") != "observed" or right.get("read_status") != "observed":
                    reason = "network_counter_read_unavailable"
                elif type(a) is not int or type(b) is not int:
                    reason = "interface_or_counter_missing"
                elif a < 0 or b < 0:
                    reason = "negative_counter"
                elif b < a:
                    reason = "counter_decreased"
                delta = None if reason else b - a
                item["metrics"][metric] = {"delta_bytes": delta,
                    "bytes_per_s": None if reason else delta / dt,
                    "status": "valid" if reason is None else "gap", "reason": reason}
            output.append(item)
    return output


class NetworkNamespaceSampler:
    """0.5-second-by-default sampler for this process's shared net namespace."""

    def __init__(self, interval_s: float = 0.5, *, reader=read_network_namespace):
        self.interval_s = interval_s
        self.reader = reader
        self.rows: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.read_wall_ns = 0

    def sample_once(self) -> dict:
        started = time.monotonic_ns()
        try:
            row = self.reader(t_monotonic_ns=time.monotonic_ns())
        except Exception as exc:  # measurement failure is retained, never breaks cleanup
            row = {"scope": "current_process_network_namespace",
                   "scope_kind": "network_namespace_shared", "namespace_id": None,
                   "t_monotonic_ns": time.monotonic_ns(), "interfaces": {},
                   "read_status": type(exc).__name__,
                   "counter_basis": "kernel interface bytes; namespace-wide"}
        self.read_wall_ns += time.monotonic_ns() - started
        self.rows.append(row)
        return row

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("network sampler already started")
        self._stop.clear()
        self.sample_once()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        deadline = time.monotonic()
        while not self._stop.is_set():
            deadline += self.interval_s
            delay = deadline - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            if not self._stop.is_set():
                self.sample_once()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_s * 4))
            alive = self._thread.is_alive()
        else:
            alive = False
        if not alive:
            self.sample_once()
        intervals = network_rate_intervals(self.rows)
        metric_intervals = [item for interval in intervals for item in interval.get("metrics", {}).values()]
        valid_intervals = sum(item.get("status") == "valid" for item in metric_intervals)
        gap_counts = dict(Counter(item.get("reason") for item in metric_intervals
                                  if item.get("status") != "valid"))
        return {"status": "partial" if alive or any(r.get("read_status") != "observed"
                                                       or r.get("namespace_status") != "observed"
                                                       for r in self.rows)
                or any(item.get("status") != "valid" for item in metric_intervals) else "observed",
                "scope": "current process network namespace; shared by all processes in namespace",
                "scope_kind": "network_namespace_shared",
                "counter_basis": "kernel interface tx/rx bytes; not HTTP payload, TLS bytes, or PID-exclusive traffic",
                "interval_target_s": self.interval_s, "sample_count": len(self.rows),
                "valid_metric_interval_count": valid_intervals,
                "metric_gap_count": len(metric_intervals) - valid_intervals,
                "metric_gap_reasons": gap_counts,
                "read_wall_ns": self.read_wall_ns, "sampler_stopped": not alive,
                "samples": self.rows, "intervals": intervals,
                "unsupported": {"container_netns": "not observed by this host process sampler",
                                "per_pid_bytes": "not available from /proc/net/dev",
                                "http_application_bytes": "not instrumented"}}


def directory_footprint_snapshot(specs: list[dict], *, timeout_s: float = 5.0) -> dict:
    """Boundary-scan explicit directories using non-following apparent size.

    Nested/duplicate roots are excluded after the first parent root to avoid
    double counting. Symlinks are counted as skipped entries, never followed.
    A partial walk exposes only an observed subtotal, not a complete size.
    """
    scan_start = time.monotonic_ns()
    deadline_ns = scan_start + max(0, int(timeout_s * 1e9))
    ordered = sorted(specs, key=lambda s: (len(Path(s["path"]).parts) if s.get("path") else 10**6,
                                           str(s.get("path") or ""), str(s.get("role"))))
    accepted: list[tuple[Path, str]] = []
    entries = []
    for spec in ordered:
        path_text = spec.get("path")
        row = {"role": spec.get("role"), "scope": spec.get("scope"),
               "ownership": spec.get("ownership", "unknown"), "path": path_text,
               "size_basis": "apparent_file_size_bytes", "status": None,
               "bytes": None, "observed_subtotal_bytes": 0,
               "files_seen": 0, "symlinks_skipped": 0,
               "scan_started_monotonic_ns": time.monotonic_ns(),
               "scan_wall_ns": None}
        if not path_text:
            row.update(status=spec.get("unavailable_status", "unsupported"),
                       reason=spec.get("reason", "path_not_host_visible"))
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        path = Path(os.path.abspath(os.fspath(path_text)))
        parent = next((p for p, _ in accepted if path == p or p in path.parents), None)
        if parent is not None:
            row.update(status="overlapping_path_excluded", reason="already_counted_in_parent_scope",
                       overlap_parent=str(parent))
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        try:
            root_stat = path.lstat()
        except FileNotFoundError:
            row["status"] = "path_missing"
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        except PermissionError:
            row["status"] = "permission_denied"
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        except OSError as exc:
            row["status"] = type(exc).__name__
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        if path.is_symlink():
            row.update(status="symlink_not_followed", reason="root_is_symlink")
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        if not path.is_dir():
            row.update(status="not_directory", reason="explicit_scope_is_not_directory")
            row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
            entries.append(row)
            continue
        accepted.append((path, str(spec.get("role"))))
        total = 0
        errors = []
        stack = [path]
        while stack:
            if time.monotonic_ns() >= deadline_ns:
                errors.append("scan_timeout")
                stack.clear()
                break
            current = stack.pop()
            try:
                children = list(os.scandir(current))
            except OSError as exc:
                errors.append(type(exc).__name__)
                continue
            for child in children:
                if time.monotonic_ns() >= deadline_ns:
                    errors.append("scan_timeout")
                    stack.clear()
                    break
                try:
                    if child.is_symlink():
                        row["symlinks_skipped"] += 1
                    elif child.is_dir(follow_symlinks=False):
                        stack.append(Path(child.path))
                    elif child.is_file(follow_symlinks=False):
                        size = child.stat(follow_symlinks=False).st_size
                        total += size
                        row["files_seen"] += 1
                except FileNotFoundError:
                    errors.append("file_disappeared_during_scan")
                except PermissionError:
                    errors.append("permission_denied_during_scan")
                except OSError as exc:
                    errors.append(type(exc).__name__)
        row["observed_subtotal_bytes"] = total
        row["bytes"] = None if errors else total
        row["status"] = "partial" if errors else "complete"
        if errors:
            row["errors"] = sorted(set(errors))
        row["scan_wall_ns"] = time.monotonic_ns() - row["scan_started_monotonic_ns"]
        entries.append(row)
    return {"t_monotonic_ns": time.monotonic_ns(),
            "scan_wall_ns": time.monotonic_ns() - scan_start,
            "size_basis": "apparent_file_size_bytes; allocated blocks not measured",
            "entries": entries}


_CONTAINER_DISK_SCAN = r'''import json, os, sys, time
specs=json.loads(sys.argv[1]); limit=time.monotonic_ns()+int(float(sys.argv[2])*1e9)
accepted=[]; rows=[]
for spec in sorted(specs,key=lambda s:(len(s["path"].split("/")),s["path"])):
 start=time.monotonic_ns(); path=spec["path"]
 row={"role":spec["role"],"scope":spec["scope"],"ownership":spec.get("ownership","task_scoped"),"path":path,
      "size_basis":"apparent_file_size_bytes","status":None,"bytes":None,"observed_subtotal_bytes":0,
      "files_seen":0,"symlinks_skipped":0,"scan_started_monotonic_ns":start,"scan_wall_ns":None}
 parent=next((p for p in accepted if path==p or path.startswith(p.rstrip("/")+"/")),None)
 if parent:
  row.update(status="overlapping_path_excluded",reason="already_counted_in_parent_scope",overlap_parent=parent)
 else:
  try: st=os.lstat(path)
  except FileNotFoundError: row["status"]="path_missing"
  except PermissionError: row["status"]="permission_denied"
  except OSError as e: row["status"]=type(e).__name__
  else:
   if os.path.islink(path): row.update(status="symlink_not_followed",reason="root_is_symlink")
   elif not os.path.isdir(path): row.update(status="not_directory",reason="explicit_scope_is_not_directory")
   else:
    accepted.append(path); stack=[path]; total=0; errors=[]
    while stack:
     if time.monotonic_ns()>=limit: errors.append("scan_timeout"); break
     current=stack.pop()
     try: children=list(os.scandir(current))
     except PermissionError: errors.append("permission_denied_during_scan"); continue
     except FileNotFoundError: errors.append("directory_disappeared_during_scan"); continue
     except OSError as e: errors.append(type(e).__name__); continue
     for child in children:
      if time.monotonic_ns()>=limit: errors.append("scan_timeout"); break
      try:
       if child.is_symlink(): row["symlinks_skipped"]+=1
       elif child.is_dir(follow_symlinks=False): stack.append(child.path)
       elif child.is_file(follow_symlinks=False): total+=child.stat(follow_symlinks=False).st_size; row["files_seen"]+=1
      except PermissionError: errors.append("permission_denied_during_scan")
      except FileNotFoundError: errors.append("file_disappeared_during_scan")
      except OSError as e: errors.append(type(e).__name__)
    row["observed_subtotal_bytes"]=total
    row["bytes"]=None if errors else total
    row["status"]="partial" if errors else "complete"
    if errors: row["errors"]=sorted(set(errors))
 row["scan_wall_ns"]=time.monotonic_ns()-start
 rows.append(row)
print(json.dumps({"clock_domain":"container_kernel_monotonic","t_monotonic_ns":time.monotonic_ns(),
 "size_basis":"apparent_file_size_bytes; allocated blocks not measured","entries":rows},separators=(",",":")))
'''


def container_directory_footprint_snapshot(runtime, handle, specs: list[dict], *,
                                            timeout_s: float) -> dict:
    """Measure only explicitly named container directories via existing exec.

    The container must provide python3; lack of that helper is recorded as an
    unavailable scan. No directory is recursively scanned by the host.
    """
    import shlex
    import re
    started = time.monotonic_ns()
    timeout_s = max(0.0, float(timeout_s))
    diagnostics = {'returncode': None, 'timed_out': None,
                   'cwd': getattr(getattr(handle, 'spec', None), 'cwd', None),
                   'error_summary': None}
    def unavailable_entries(status: str, reason: str) -> list[dict]:
        return [{"role": spec.get("role"), "scope": spec.get("scope"),
                 "ownership": spec.get("ownership", "task_scoped"),
                 "path": spec.get("path"), "size_basis": "apparent_file_size_bytes",
                 "status": status, "reason": reason, "bytes": None,
                 "observed_subtotal_bytes": None, "files_seen": None,
                 "symlinks_skipped": None, "scan_started_monotonic_ns": started,
                 "scan_wall_ns": 0} for spec in specs]
    if timeout_s <= 0:
        return {"status": "partial", "reason": "not_started_no_budget",
                "entries": unavailable_entries("not_started_no_budget", "no_remaining_budget"),
                "clock_domain": "container_kernel_monotonic", "read_wall_ns": 0}
    payload = json.dumps(specs, separators=(",", ":"))
    command = "# AWC_TASK_DIRECTORY_SCAN\npython3 -c " + shlex.quote(_CONTAINER_DISK_SCAN) + " " + shlex.quote(payload) + " " + repr(timeout_s)
    try:
        result = runtime.execute(handle, command, timeout_s=timeout_s, output_limit=100_000)
        output = result.get("output", "")
        diagnostics.update(returncode=result.get('returncode'),
                           timed_out=bool(result.get('timed_out', False)))
        if result.get("returncode") != 0 or result.get("timed_out"):
            # The scan has no credentials or model payload. Still redact common
            # credential/header forms before retaining a bounded stderr excerpt.
            excerpt = re.sub(r'(?i)(authorization\s*:\s*(?:bearer\s+)?|(?:api[_-]?key|token|password)\s*[=:]\s*)[^\s,;]+',
                             r'\1[REDACTED]', str(output))
            excerpt = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', excerpt)
            diagnostics['error_summary'] = ' '.join(excerpt.split())[:512]
            reason = "scan_timeout" if result.get("timed_out") else "container_scan_command_failed"
            return {"status": "partial", "reason": reason,
                    'diagnostics': diagnostics,
                    "error_type": "TimeoutError" if result.get("timed_out") else "ContainerScanError",
                    "entries": unavailable_entries("partial", reason),
                    "clock_domain": "container_kernel_monotonic",
                    "read_wall_ns": time.monotonic_ns() - started}
        data = json.loads(output)
        data['diagnostics'] = diagnostics
        data["status"] = "complete" if data.get("entries") and all(e.get("status") in ("complete", "overlapping_path_excluded")
                                             for e in data.get("entries", [])) else "partial"
        data["read_wall_ns"] = time.monotonic_ns() - started
        return data
    except Exception as exc:
        return {"status": "partial", "reason": "container_scan_unavailable",
                'diagnostics': diagnostics,
                "error_type": type(exc).__name__,
                "entries": unavailable_entries("partial", type(exc).__name__),
                "clock_domain": "container_kernel_monotonic",
                "read_wall_ns": time.monotonic_ns() - started}


def disk_footprint_report(before: dict, after: dict) -> dict:
    before_by_role = {(r.get("role"), r.get("scope")): r for r in before.get("entries", [])}
    after_by_role = {(r.get("role"), r.get("scope")): r for r in after.get("entries", [])}
    rows = []
    for key in sorted(set(before_by_role) | set(after_by_role), key=str):
        a, b = before_by_role.get(key), after_by_role.get(key)
        delta = (b["bytes"] - a["bytes"] if a and b
                 and a.get("status") == b.get("status") == "complete"
                 and type(a.get("bytes")) is int and type(b.get("bytes")) is int else None)
        rows.append({"role": key[0], "scope": key[1], "before": a, "after": b,
                     "delta_bytes": delta,
                     "delta_status": "observed" if delta is not None else "unavailable_or_partial"})
    return {"status": "complete" if rows and all(r["delta_status"] == "observed" for r in rows) else "partial",
            "size_basis": "apparent_file_size_bytes; allocated size not measured",
            "before": before, "after": after, "paths": rows,
            "limitations": ["shared caches are not inferred as task-owned",
                            "directory scans are boundary-only, not periodic",
                            "the stop scan precedes later archive/report writes; measured size is not the final manifest byte total"]}


class RunSupplement:
    """Small shared boundary/network collector consumed by the three runners."""

    def __init__(self, output_dir: Path, *, interval_s: float = 0.5,
                 disk_specs: list[dict] | None = None, network_reader=read_network_namespace,
                 task_workspace_status: dict | None = None):
        self.output_dir = Path(output_dir)
        self.disk_specs = disk_specs or [{"path": str(output_dir), "role": "attempt_output",
            "scope": "host_visible_runner_output", "ownership": "run_scoped"}]
        self.network = NetworkNamespaceSampler(interval_s, reader=network_reader)
        self.before = None
        self._stopped = False
        self.failures: list[str] = []
        self.container_disk: dict[str, dict] = {}
        self.task_workspace_status = task_workspace_status or {
            "status": "unsupported", "reason": "no_task_workspace_boundary_registered"}

    def start(self, *, disk_timeout_s: float = 5.0) -> None:
        try:
            self.before = directory_footprint_snapshot(self.disk_specs,
                                                       timeout_s=disk_timeout_s)
        except Exception as exc:
            self.failures.append("disk_before:" + type(exc).__name__)
        try:
            self.network.start()
        except Exception as exc:
            self.failures.append("network_start:" + type(exc).__name__)

    def record_container_disk_boundary(self, scope: str, boundary: str,
                                       snapshot: dict) -> None:
        if boundary not in ("before_agent", "after_agent",
                            "before_verifier", "after_verifier"):
            raise ValueError("unknown disk boundary")
        self.container_disk.setdefault(scope, {})[boundary] = snapshot

    def stop(self, *, disk_timeout_s: float = 5.0) -> dict:
        if self._stopped:
            raise RuntimeError("run supplement may be stopped only once")
        self._stopped = True
        try:
            network = self.network.stop()
        except Exception as exc:
            self.failures.append("network_stop:" + type(exc).__name__)
            network = {"status": "partial", "scope_kind": "network_namespace_shared",
                       "samples": [], "intervals": [], "failure": type(exc).__name__}
        try:
            after = directory_footprint_snapshot(self.disk_specs,
                                                 timeout_s=disk_timeout_s)
            disk = disk_footprint_report(self.before or {"entries": []}, after)
        except Exception as exc:
            self.failures.append("disk_after:" + type(exc).__name__)
            disk = {"status": "partial", "size_basis": "apparent_file_size_bytes",
                    "before": self.before, "after": None, "paths": [],
                    "failure": type(exc).__name__}
        container_disk = {}
        for scope, boundaries in self.container_disk.items():
            phase = "verifier" if "verifier" in scope else "agent"
            before = boundaries.get(f"before_{phase}", {"entries": []})
            after = boundaries.get(f"after_{phase}", {"entries": []})
            container_disk[scope] = {f"before_{phase}": before, f"after_{phase}": after,
                                     "footprint": disk_footprint_report(before, after),
                                     "scope": "explicit task paths inside container; apparent size; not layer size"}
        task_workspace = ({"status": "partial" if any(
            item["footprint"]["status"] != "complete" for item in container_disk.values()) else "observed",
            "scopes": container_disk} if container_disk else dict(self.task_workspace_status))
        return {"schema": "run-supplement-v1",
                "measurement_contract_version": CONTRACT_VERSION,
                "status": "partial" if self.failures or network.get("status") != "observed"
                or disk.get("status") != "complete"
                or task_workspace.get("status") not in ("observed", "not_applicable") else "observed",
                "failures": self.failures, "network": network, "disk_footprint": disk,
                "task_workspace": task_workspace,
                "container_disk_footprints": container_disk,
                "api_transport_bytes": {"status": "unsupported",
                    "reason": "no transparent request-and-stream-response byte hook is shared by all three production clients",
                    "scope": None, "value": None,
                    "explicitly_excludes": ["no payload inferred from tokens/content characters",
                                             "no HTTP headers/TLS/link-layer bytes recorded"]}}


def environment_snapshot() -> dict:
    """Only whitelist local platform/package metadata; no env, key or command."""
    def read(path):
        try:
            return {"value": Path(path).read_text().strip(), "status": "observed"}
        except OSError as exc:
            return {"value": None, "status": type(exc).__name__}

    cpu = read("/proc/cpuinfo")
    fields = defaultdict(set)
    if cpu["value"] is not None:
        for line in cpu["value"].splitlines():
            key, _, value = line.partition(":")
            if key.strip() in ("model name", "CPU implementer", "CPU part", "microcode"):
                fields[key.strip()].add(value.strip())
    packages = sorted({(d.metadata.get("Name", "unknown"), d.version)
                       for d in importlib.metadata.distributions()})
    return {
        "schema": CONTRACT_VERSION, "machine": platform.machine(),
        "kernel": platform.release(), "logical_cpus": os.cpu_count(),
        "cpu_fields": {k: sorted(v) for k, v in fields.items()},
        "cpu_field_status": {k: ('observed' if k in fields else 'not_exposed')
                             for k in ('model name', 'CPU implementer', 'CPU part', 'microcode')},
        "cpuinfo_status": cpu["status"],
        "boot_id": read('/proc/sys/kernel/random/boot_id'),
        "governor_cpu0": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "smt_active": read("/sys/devices/system/cpu/smt/active"),
        "numa_online": read("/sys/devices/system/node/online"),
        "python": {"executable": sys.executable, "version": platform.python_version()},
        "packages": [{"name": n, "version": v} for n, v in packages],
        "filesystem": {"value": None, "reason": "not_observed"},
        "cache_initial_state": {"value": None, "reason": "not_controlled"},
        "runtime_and_container_packages": "use registered image/preflight/freeze; host snapshot is not container evidence",
        "perf": {"value": None, "reason": "not_requested; no perf command run"},
    }


class MeasuredLLM:
    """Time the actual existing call, including its internal retries.

    Parsing happens later: a returned response is not necessarily a valid action.
    No prompt, content, reasoning, headers or credential fingerprints are saved.
    """

    def __init__(self, inner, recorder, agent):
        self.inner, self.recorder, self.agent = inner, recorder, agent
        self.count = 0

    async def call(self, *, prompt, message_history, **kw):
        self.count += 1
        event_id = self.recorder.begin("llm_request", {
            "request_id": f"request-{self.count}", "step_index": self.count,
            "model": self.agent.model_name,
            "context_message_count": len(message_history),
            "context_characters": sum(len(m.get("content", "")) for m in message_history) + len(prompt),
            "transport_attempt_count": None,
            "retry_scope": "logical_call_includes_inner_retries",
        })
        self.agent.request_event_id = event_id
        self.agent.request_count = self.count
        try:
            response = await self.inner.call(prompt=prompt, message_history=message_history, **kw)
        except BaseException as exc:
            self.recorder.end(event_id, attrs={"ok": False}, error=type(exc).__name__)
            raise
        usage = response.usage
        tokens = (None if usage is None else {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cached_tokens": usage.cache_tokens,
        })
        self.recorder.end(event_id, attrs={
            "ok": True, "usage": tokens, "response_model": response.model_name,
            "response_id": response.response_id, "cost_status": "unknown_not_billing_evidence",
            "timing_source": "native_event",
        })
        return response


def span_coverage(path: Path, *, native_tool_hook: bool = False) -> dict:
    """Check exact ID pairs and actual clock boundaries, not receipt time.

    Native Coding tool hook has its own fixed source format; it is checked
    directly, not positionally joined to the semantic recorder.
    """
    if not path.is_file():
        return {"status": "unavailable", "reason": "not_recorded", "spans": {}, "errors": []}
    groups = defaultdict(list)
    errors = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except ValueError:
            errors.append("invalid_json")
            continue
        kind = "tool_call" if native_tool_hook else e.get("kind")
        if kind not in ("llm_request", "tool_call"):
            continue
        if not e.get("event_id"):
            errors.append("missing_event_id")
            continue
        groups[e["event_id"]].append((kind, e))
    counts = defaultdict(Counter)
    for event_id, rows in groups.items():
        kinds = {k for k, _ in rows}
        if len(kinds) != 1:
            errors.append("event_id_kind_conflict")
            continue
        kind = next(iter(kinds))
        opening = [e for _, e in rows if e.get("event" if native_tool_hook else "status") == "open"]
        terminal = [e for _, e in rows if e.get("event" if native_tool_hook else "status") in ("closed", "error", "unclosed")]
        counts[kind]["started"] += len(opening)
        if len(opening) != 1 or len(terminal) != 1 or len(rows) != 2:
            errors.append("invalid_pair")
            continue
        a, b = opening[0], terminal[0]
        state = b.get("event" if native_tool_hook else "status")
        if state == "unclosed":
            counts[kind]["censored"] += 1
            continue
        if native_tool_hook:
            start, end = a.get("t_start_ns"), b.get("t_end_ns")
            if b.get("t_start_ns") != start:
                errors.append("tool_start_mismatch")
                continue
        else:
            if a.get("clock_domain") != b.get("clock_domain") or not a.get("clock_domain"):
                errors.append("clock_domain_mismatch")
                continue
            attrs = b.get("attrs", {})
            if attrs.get('timing_source') in ('unknown', 'log_receipt'):
                errors.append('execution_time_unavailable')
                continue
            if attrs.get("timing_source") == "child_status":
                start, end = attrs.get("t_start_ns"), attrs.get("t_end_ns")
            else:
                start, end = a.get("t_monotonic_ns"), b.get("t_monotonic_ns")
        if type(start) is not int or type(end) is not int or end < start:
            errors.append("invalid_or_missing_time")
            continue
        counts[kind]["timed"] += 1
        counts[kind]["error_terminal"] += int(state == "error")
        counts[kind]["usage_observed"] += int(kind == "llm_request" and b.get("attrs", {}).get("usage") is not None)
        if not native_tool_hook and kind == "tool_call":
            counts[kind]["bootstrap"] += int(a.get("attrs", {}).get("role") == "bootstrap")
    return {"status": "partial" if errors or any(v["censored"] for v in counts.values()) else "verified",
            "spans": {k: dict(v) for k, v in counts.items()}, "errors": errors,
            "scope": "saved events; must also compare expected runtime/trajectory counts"}


def measurement_report(events_path: Path, *, expected_requests: int | None,
                       expected_tools: int | None, tool_path: Path | None = None) -> dict:
    semantic = span_coverage(events_path)
    tools = span_coverage(tool_path, native_tool_hook=True) if tool_path else semantic
    requests = semantic["spans"].get("llm_request", {})
    calls = tools["spans"].get("tool_call", {})
    gaps = []
    for name, found, expected in (("requests", requests, expected_requests),
                                   ("tools", calls, expected_tools)):
        if expected is None:
            gaps.append(name + ":expected_count_unknown")
        elif found.get("started", 0) != expected or found.get("timed", 0) != expected:
            gaps.append(name + ":count_or_timing_incomplete")
    if semantic["errors"] or tools["errors"]:
        gaps.append("invalid_event_pairs")
    for name, report in (("requests", semantic), ("tools", tools)):
        if report["status"] != "verified":
            gaps.append(name + ":" + report["status"])
    return {"contract": CONTRACT, "call_timing_status": "complete" if not gaps else "partial",
            "request_usage_observed": requests.get('usage_observed', 0),
            "request_usage_missing_or_unreturned": (None if expected_requests is None else
                max(0, expected_requests - requests.get('usage_observed', 0))),
            "expected_requests": expected_requests, "expected_tools_including_bootstrap": expected_tools,
            "semantic_spans": semantic, "tool_spans": tools, "gaps": gaps,
            "transport_attempts": {"value": None, "reason": "transport_hook_not_installed"},
            "exclusive_tool_cpu": {"value": None, "reason": "shared_scope_window_only"},
            "billing": {"value": None, "reason": "no_bill_evidence"}}


def sample_quality(rows: list[dict], interval_s: float) -> dict:
    """Describe recorded sampling, without silently zeroing unreadable data."""
    gaps = []
    resets = Counter()
    missing = Counter()
    previous = None
    for row in rows:
        t = row.get('t_monotonic_ns')
        valid_time = type(t) is int
        if not valid_time:
            missing['timestamp'] += 1
        if previous is not None and valid_time and type(previous.get('t_monotonic_ns')) is int:
            gap = t - previous['t_monotonic_ns']
            gaps.append(gap)
        current = row.get('container', {})
        for field in ('cpu_usage_usec', 'mem_current_bytes', 'io_read_bytes', 'io_write_bytes'):
            value = current.get(field)
            if value is None:
                missing[field] += 1
            if field != 'mem_current_bytes' and previous is not None:
                old = previous.get('container', {}).get(field)
                if value is not None and old is not None and value < old:
                    resets[field] += 1
        previous = row
    boundaries = [row.get('role') for row in rows if row.get('role') != 'sample']
    cpu_complete = bool(rows) and not missing['cpu_usage_usec'] and not resets['cpu_usage_usec']
    clock_ok = bool(rows) and not missing['timestamp'] and all(g > 0 for g in gaps)
    boundary_ok = boundaries == ['boundary_start', 'boundary_end']
    return {
        'status': 'complete' if cpu_complete and clock_ok and boundary_ok and not missing['mem_current_bytes'] else 'partial',
        'rows': len(rows), 'interval_target_s': interval_s,
        'boundaries': boundaries, 'missing': dict(missing), 'counter_regressions': dict(resets),
        'gaps_ns': gaps, 'nonpositive_gaps': sum(g <= 0 for g in gaps),
        'max_gap_ns': max(gaps, default=None),
        'read_statuses': [r.get('container', {}).get('read_status', {}) for r in rows],
        'scope': 'shared container; optional I/O availability reported separately',
    }
