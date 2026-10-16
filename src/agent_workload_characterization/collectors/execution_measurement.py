"""Mandatory real-run observation contract; no experiments or external probes.

Reuse SemanticRecorder for spans. This module only snapshots local metadata,
wraps the existing async LLM call, and checks saved observation coverage.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path

CONTRACT_VERSION = "real-run-measurement-v1"
CONTRACT = {
    "version": CONTRACT_VERSION,
    "required": ["identity_and_configuration", "environment_snapshot",
                 "lifecycle_and_cleanup", "logical_requests_and_usage",
                 "tool_and_bootstrap_spans", "resource_scope_and_boundaries",
                 "sampling_quality_and_read_cost", "independent_outcomes",
                 "archive_hashes_and_coverage"],
    "explicit_unavailable": ["actual_transport_attempts_without_transport_hook",
                             "remote_cpu_memory", "network_bytes",
                             "exclusive_tool_cpu", "pmu_and_function_hotspots",
                             "uncontrolled_cache_state"],
    "timing": "same-host system_monotonic; client logical call includes retries",
    "io": "cgroup block service bytes are not application/filesystem bytes",
    "missing": "null plus reason; observed zero is preserved",
}


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
