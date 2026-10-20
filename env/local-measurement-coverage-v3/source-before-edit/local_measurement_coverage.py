#!/usr/bin/env python3
"""Offline inventory of the three accepted local measurement batches."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent_workload_characterization.collectors.execution_measurement import counter_rate_intervals


ROOT = Path(__file__).resolve().parents[1]
OUT = Path("reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v2")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _record_input(root: Path, path: Path, inputs: dict[str, dict]) -> dict:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    record = _hash(path)
    previous = inputs.setdefault(rel, record)
    if previous != record:
        raise ValueError(f"input changed while analyzing: {rel}")
    return record


def _verify_raw(root: Path, run_dir: Path, inputs: dict[str, dict],
                registered_manifest: dict | None = None) -> tuple[dict, list[str]]:
    manifest_path = run_dir / "manifest.json"
    manifest_hash = _record_input(root, manifest_path, inputs)
    if registered_manifest and any(manifest_hash.get(k) != registered_manifest.get(k)
                                   for k in ("bytes", "sha256")):
        raise ValueError(f"batch manifest/raw manifest mismatch: {manifest_path}")
    manifest = _read_json(manifest_path)
    records = manifest.get("outputs", manifest.get("files"))
    if isinstance(records, dict):
        records = [{"path": name, "sha256": digest} for name, digest in records.items()]
    if not isinstance(records, list):
        raise ValueError(f"unsupported raw manifest shape: {manifest_path}")
    expected = set()
    mismatches = []
    for item in records:
        rel = item["path"]
        expected.add(rel)
        path = run_dir / rel
        actual = _record_input(root, path, inputs) if path.is_file() else None
        if actual is None or actual["sha256"] != item.get("sha256") or (
                item.get("bytes") is not None and actual["bytes"] != item["bytes"]):
            mismatches.append(rel)
    actual_names = {p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*")
                    if p.is_file() and p.name != "manifest.json"}
    if actual_names != expected:
        mismatches.append("raw_file_set_mismatch")
    if mismatches:
        raise ValueError(f"raw manifest verification failed for {run_dir}: {mismatches[:8]}")
    return manifest, sorted(expected)


def _stats(rows: list[dict], field_path: tuple[str, ...]) -> dict:
    values = []
    missing = 0
    for row in rows:
        value = row
        for part in field_path:
            value = value.get(part) if isinstance(value, dict) else None
        if type(value) is int:
            values.append(value)
        else:
            missing += 1
    return {"valid_points": len(values), "missing_or_invalid_points": missing,
            "observed_zero_points": sum(v == 0 for v in values)}


def _observed_keys(value) -> set[str]:
    found = set()
    if isinstance(value, dict):
        found.update(str(k).lower() for k in value)
        for child in value.values():
            found.update(_observed_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_observed_keys(child))
    return found


def _unified_metric_key_hits(*values) -> dict:
    keys = set().union(*(_observed_keys(value) for value in values))
    network_keys = {"rx_bytes", "tx_bytes", "network_rx_bytes", "network_tx_bytes",
                    "bytes_recv", "bytes_sent", "received_bytes", "sent_bytes",
                    "network_bytes_rx", "network_bytes_tx"}
    footprint_keys = {"disk_footprint", "workspace_bytes_before", "workspace_bytes_after",
                      "directory_size_before", "directory_size_after", "allocated_bytes_before",
                      "allocated_bytes_after"}
    return {"network_counter_keys": sorted(keys & network_keys),
            "directory_footprint_keys": sorted(keys & footprint_keys)}


def _interval_count(rows: list[dict], counters: dict) -> dict:
    intervals = counter_rate_intervals(rows, counters)
    result = {}
    for name in counters:
        result[name] = {"pairs": len(intervals),
                        "valid": sum(i["metrics"][name]["status"] == "valid" for i in intervals),
                        "gaps": sum(i["metrics"][name]["status"] == "gap" for i in intervals)}
    return result


def _unique_office_container_id(summary: dict) -> str | None:
    ids = {event.get("container_id") for event in summary.get("events", [])
           if event.get("phase") == "container_identified" and event.get("container_id")}
    return next(iter(ids)) if len(ids) == 1 else None


def _rate_coverage(runs: list[dict], path: tuple[str, ...]) -> dict:
    valid = gaps = pairs = 0
    def visit(value):
        nonlocal valid, gaps, pairs
        if isinstance(value, dict):
            if all(key in value for key in ("pairs", "valid", "gaps")):
                pairs += value["pairs"]
                valid += value["valid"]
                gaps += value["gaps"]
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for run in runs:
        value = run
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        visit(value)
    status = "derivable_with_gaps" if valid and gaps else ("derivable" if valid else "no_valid_intervals")
    return {"pairs": pairs, "valid_intervals": valid, "gap_intervals": gaps, "status": status}


def _coding_run(root: Path, rel_dir: str, run_summary: dict, inputs: dict,
                registered_manifest: dict | None) -> dict:
    run_dir = root / rel_dir
    manifest, file_names = _verify_raw(root, run_dir, inputs, registered_manifest)
    samples = _read_json(run_dir / "samples.json")
    metadata = _read_json(run_dir / "metadata.json")
    host = _read_json(run_dir / "host_process.jsonl")
    scope_rows = {}
    for scope_id, evidence in samples.get("evidence", {}).items():
        rows = [evidence.get("boundary_start"), *evidence.get("samples", []),
                evidence.get("boundary_end")]
        rows = [row for row in rows if isinstance(row, dict)]
        for row in rows:
            row.setdefault("scope_id", scope_id)
        scope_rows[scope_id] = rows
    scopes = {}
    for scope_id, rows in scope_rows.items():
        scopes[scope_id] = {
            "scope_kind": samples["evidence"][scope_id].get("scope_kind"),
            "saved_samples": len(samples["evidence"][scope_id].get("samples", [])),
            "cpu_usage_usec": _stats(rows, ("cpu_usage_usec",)),
            "memory_current_bytes": _stats(rows, ("mem_current_bytes",)),
            "kernel_memory_peak_bytes": _stats(rows, ("mem_peak_bytes",)),
            "cgroup_io_read_bytes": _stats(rows, ("io_read_bytes",)),
            "cgroup_io_write_bytes": _stats(rows, ("io_write_bytes",)),
            "derivable_adjacent_rates": _interval_count(rows, {
                "cpu": {"path": "cpu_usage_usec", "divisor": 1_000_000,
                        "unit": "cpu_seconds", "rate_unit": "average_core",
                        "identity_paths": ["scope_id", "scope_kind"],
                        "status_paths": [("read_status", "cpu.stat"),
                                         ("read_status", "cpuacct.usage")]},
                "io_read": {"path": "io_read_bytes", "unit": "bytes",
                            "rate_unit": "bytes_per_second",
                            "identity_paths": ["scope_id", "scope_kind"],
                            "status_paths": [("read_status", "io.stat"),
                                             ("read_status", "io")]},
                "io_write": {"path": "io_write_bytes", "unit": "bytes",
                             "rate_unit": "bytes_per_second",
                             "identity_paths": ["scope_id", "scope_kind"],
                             "status_paths": [("read_status", "io.stat"),
                                              ("read_status", "io")]}}),
        }
    host_identity = host.get("identity", {})
    host_records = [{**row, "pid": host_identity.get("pid"),
                     "starttime_ticks": host_identity.get("starttime_ticks")}
                    for row in host.get("records", [])]
    host_clk_tck = host.get("summary", {}).get("clk_tck")
    host_rates = _interval_count(host_records, {
        "cpu": {"path": "cpu_ticks", "divisor": host_clk_tck, "unit": "cpu_seconds",
                "rate_unit": "average_core", "identity_paths": ["pid", "starttime_ticks"],
                "status_path": "stat"}})
    key_scan = _unified_metric_key_hits(samples, host, metadata)
    return {"collection": "P1-12-CODING-REPEAT-01", "run_id": run_summary["run_id"],
            "task": run_summary.get("task"), "path": rel_dir,
            "raw_manifest_verified": True, "manifest_files": len(file_names),
            "attempt_wall_s": run_summary.get("attempt_wall_s"), "scopes": scopes,
            "host_process": {"pid_starttime_identity": host.get("identity"),
                "records": len(host_records),
                "cpu_ticks": _stats(host_records, ("cpu_ticks",)),
                "rss_bytes": _stats(host_records, ("rss_bytes",)),
                "proc_rchar": _stats(host_records, ("process_io", "rchar")),
                "proc_wchar": _stats(host_records, ("process_io", "wchar")),
                "proc_read_bytes": _stats(host_records, ("process_io", "read_bytes")),
                "proc_write_bytes": _stats(host_records, ("process_io", "write_bytes")),
                "clk_tck": host_clk_tck, "cpu_and_proc_io_rate_intervals": host_rates,
                "proc_io_fields_saved": False,
                "scope": "host process recorded by PID/starttime; shared runner/collector scope"},
            "identity_association": run_summary.get("identity_association"),
            "historical_network_counters": ("candidate_keys_found" if key_scan["network_counter_keys"]
                                             else "not_found_in_selected_resource_files"),
            "historical_disk_footprint_boundaries": ("candidate_keys_found" if key_scan["directory_footprint_keys"]
                                                       else "not_found_in_selected_resource_files"),
            "selected_resource_key_scan": key_scan,
            "phase_and_behavior_sources": [n for n in file_names if n in
                {"metadata.json", "events.jsonl", "mini_tool_events.jsonl", "mini_trajectory.json"}]}


def _docops_run(root: Path, run_info: dict, inputs: dict,
                registered_manifest: dict | None) -> dict:
    run_dir = root / "data/raw/generated/DOCOPS-OFFICE-REPEAT-02" / run_info["run_id"]
    manifest, file_names = _verify_raw(root, run_dir, inputs, registered_manifest)
    summary = _read_json(run_dir / "summary.json")
    env = _read_json(run_dir / "environment.json")
    measurement = _read_json(run_dir / "measurement.json")
    rows = summary.get("samples", [])
    container_id = _unique_office_container_id(summary)
    scopes = {}
    for role in ("agent_container", "verifier_container"):
        scoped = [r for r in rows if r.get("container", {}).get("scope_kind") == role]
        container_rows = [{**r.get("container", {}), "t_monotonic_ns": r.get("t_monotonic_ns"),
                           "container_id": container_id}
                          for r in scoped]
        host_rows = [{**r.get("host_agent", {}), "t_monotonic_ns": r.get("t_monotonic_ns")}
                     for r in scoped]
        scopes[role] = {"saved_samples": len(scoped),
            "cpu_usage_usec": _stats(container_rows, ("cpu_usage_usec",)),
            "memory_current_bytes": _stats(container_rows, ("mem_current_bytes",)),
            "kernel_memory_peak_bytes": _stats(container_rows, ("mem_peak_bytes",)),
            "cgroup_io_read_bytes": _stats(container_rows, ("io_read_bytes",)),
            "cgroup_io_write_bytes": _stats(container_rows, ("io_write_bytes",)),
            "host_process_cpu_ticks": _stats(host_rows, ("cpu_ticks",)),
            "host_process_rss_bytes": _stats(host_rows, ("rss_bytes",)),
            "proc_io_fields": {key: _stats(host_rows, ("process_io", key)) for key in
                               ("rchar", "wchar", "read_bytes", "write_bytes")}}
        scopes[role]["derivable_cgroup_rates"] = _interval_count(container_rows, {
            "cpu": {"path": "cpu_usage_usec", "divisor": 1_000_000,
                    "unit": "cpu_seconds", "rate_unit": "average_core",
                    "identity_paths": ["container_id"],
                    "status_paths": [("read_status", "cpu.stat"),
                                     ("read_status", "cpuacct.usage")]},
            "io_read": {"path": "io_read_bytes", "unit": "bytes",
                        "rate_unit": "bytes_per_second",
                        "identity_paths": ["container_id"],
                        "status_paths": [("read_status", "io.stat"),
                                         ("read_status", "io")]},
            "io_write": {"path": "io_write_bytes", "unit": "bytes",
                         "rate_unit": "bytes_per_second",
                         "identity_paths": ["container_id"],
                         "status_paths": [("read_status", "io.stat"),
                                          ("read_status", "io")]}})
        scopes[role]["derivable_host_process_rates"] = _interval_count(host_rows, {
            "cpu": {"path": "cpu_ticks", "divisor_path": "clk_tck",
                    "unit": "cpu_seconds", "rate_unit": "average_core",
                    "identity_paths": [("pid",), ("starttime_ticks",)],
                    "status_path": ("read_status", "stat")},
            **{name: {"path": ("process_io", field), "unit": "bytes",
                      "rate_unit": "bytes_per_second",
                      "identity_paths": [("pid",), ("starttime_ticks",)],
                      "status_path": ("read_status", "io")}
               for name, field in (("proc_rchar", "rchar"), ("proc_wchar", "wchar"),
                                   ("proc_read_bytes", "read_bytes"),
                                   ("proc_write_bytes", "write_bytes"))}})
    if summary.get("identity_sha256") != run_info.get("identity_sha256"):
        raise ValueError(f"DocOps batch/run identity mismatch: {run_info['run_id']}")
    if manifest.get("identity_sha256") != run_info.get("identity_sha256"):
        raise ValueError(f"DocOps raw/run identity mismatch: {run_info['run_id']}")
    key_scan = _unified_metric_key_hits(summary, measurement, env)
    return {"collection": "DOCOPS-OFFICE-REPEAT-02", "run_id": run_info["run_id"],
        "task": run_info.get("task_key"), "round": run_info.get("round"),
        "path": run_info["run_id"], "identity_sha256": manifest.get("identity_sha256"),
        "raw_manifest_verified": True, "manifest_files": len(file_names),
        "attempt_wall_s": summary.get("wall_s"), "sample_points": len(rows),
        "scopes": scopes, "clk_tck": env.get("clk_tck"),
        "historical_network_counters": ("candidate_keys_found" if key_scan["network_counter_keys"]
                                         else "not_found_in_selected_resource_files"),
        "historical_disk_footprint_boundaries": ("candidate_keys_found" if key_scan["directory_footprint_keys"]
                                                   else "not_found_in_selected_resource_files"),
        "selected_resource_key_scan": key_scan,
        "phase_and_behavior_sources": [n for n in file_names if n in
            {"summary.json", "measurement.json", "environment.json", "agent/events.jsonl"}]}


def _assistant_run(root: Path, run_info: dict, task: str,
                   inputs: dict, registered_manifest: dict | None,
                   batch_identity: str) -> dict:
    run_id = run_info["run_id"]
    run_dir = root / "data/raw/generated/TOOLSANDBOX-ASSISTANT-REPEAT-01" / run_id
    manifest, file_names = _verify_raw(root, run_dir, inputs, registered_manifest)
    if manifest.get("identity_sha256") != batch_identity:
        raise ValueError(f"Assistant batch/run identity mismatch: {run_id}")
    result = _read_json(run_dir / "result.json")
    env = _read_json(run_dir / "environment.json")
    rows = [json.loads(line) for line in (run_dir / "samples.jsonl").read_text().splitlines()
            if line.strip()]
    key_scan = _unified_metric_key_hits(result, env, rows)
    clk_tck = env.get("sc_clk_tck")
    intervals = _interval_count(rows, {
        "cpu": {"path": "cpu_ticks", "divisor": clk_tck, "unit": "cpu_seconds",
                "rate_unit": "average_core", "identity_paths": ["pid", "starttime_ticks"],
                "status_path": ("read_status", "stat")},
        **{name: {"path": ("process_io", field), "unit": "bytes",
                  "rate_unit": "bytes_per_second",
                  "identity_paths": ["pid", "starttime_ticks"],
                  "status_path": ("read_status", "io")}
           for name, field in (("proc_rchar", "rchar"), ("proc_wchar", "wchar"),
                               ("proc_read_bytes", "read_bytes"),
                               ("proc_write_bytes", "write_bytes"))}})
    return {"collection": "TOOLSANDBOX-ASSISTANT-REPEAT-01", "run_id": run_id,
        "task": task, "round": run_info.get("round"),
        "path": run_id, "identity_sha256": manifest.get("identity_sha256"),
        "raw_manifest_verified": True, "manifest_files": len(file_names),
        "attempt_wall_s": run_info.get("wall_s"), "worker_window_wall_s": run_info.get("worker_window_wall_s"),
        "sample_points": len(rows),
        "scope": "one shared worker process (Agent/User/tools/evaluator)",
        "cpu_ticks": _stats(rows, ("cpu_ticks",)), "rss_bytes": _stats(rows, ("rss_bytes",)),
        "thread_points": _stats(rows, ("threads",)), "clk_tck": clk_tck,
        "proc_io": {key: _stats(rows, ("process_io", key)) for key in
                    ("rchar", "wchar", "read_bytes", "write_bytes")},
        "derivable_adjacent_rates": intervals,
        "historical_network_counters": ("candidate_keys_found" if key_scan["network_counter_keys"]
                                         else "not_found_in_selected_resource_files"),
        "historical_disk_footprint_boundaries": ("candidate_keys_found" if key_scan["directory_footprint_keys"]
                                                   else "not_found_in_selected_resource_files"),
        "selected_resource_key_scan": key_scan,
        "phase_and_behavior_sources": [n for n in file_names if n in
            {"result.json", "boundaries.jsonl", "events.jsonl", "execution_context.json"}]}


def build_coverage(root: Path = ROOT) -> tuple[dict, dict[str, dict]]:
    inputs: dict[str, dict] = {}
    coding_summary_path = root / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.json"
    coding_manifest_path = coding_summary_path.with_name("manifest.json")
    docops_summary_path = root / "reports/resource/DOCOPS-OFFICE-REPEAT-02/batch-summary.json"
    docops_manifest_path = root / "reports/resource/DOCOPS-OFFICE-REPEAT-02/batch-manifest.json"
    assistant_summary_path = root / "reports/resource/TOOLSANDBOX-ASSISTANT-REPEAT-01/batch-summary.json"
    assistant_manifest_path = root / "reports/resource/TOOLSANDBOX-ASSISTANT-REPEAT-01/manifest.json"
    for path in (coding_summary_path, coding_manifest_path, docops_summary_path,
                 docops_manifest_path, assistant_summary_path, assistant_manifest_path):
        _record_input(root, path, inputs)
    coding_summary = _read_json(coding_summary_path)
    coding_manifest = _read_json(coding_manifest_path)
    docops_summary = _read_json(docops_summary_path)
    docops_manifest = _read_json(docops_manifest_path)
    assistant_summary = _read_json(assistant_summary_path)
    assistant_manifest = _read_json(assistant_manifest_path)
    coding_registered = coding_manifest.get("inputs", {})
    docops_registered = {row["path"]: row for row in docops_manifest.get("raw_run_manifests", [])}
    assistant_registered = {row["path"]: row for row in assistant_manifest.get("raw_run_manifests", [])}
    if coding_summary.get("identity_check", {}).get("approval_equals_batch") is not True or \
            coding_summary.get("identity_check", {}).get("attempt_equals_batch") is not True:
        raise ValueError("Coding accepted report does not establish its saved identity association")
    expected_docops = {f"data/raw/generated/DOCOPS-OFFICE-REPEAT-02/{r['run_id']}/manifest.json"
                       for r in docops_summary["results"]}
    expected_assistant = {f"data/raw/generated/TOOLSANDBOX-ASSISTANT-REPEAT-01/{r['run_id']}/manifest.json"
                          for task in assistant_summary["per_task"].values() for r in task["runs"]}
    if set(docops_registered) != expected_docops or set(assistant_registered) != expected_assistant:
        raise ValueError("batch manifest and explicit run summary enumerate different raw runs")
    if docops_manifest.get("identity_sha256") != docops_summary.get("identity_sha256"):
        raise ValueError("DocOps batch summary/manifest identity mismatch")
    if assistant_summary.get("executed") != 9 or assistant_summary.get("not_executed_count") != 0:
        raise ValueError("Assistant summary does not confirm the expected nine completed records")
    if set(coding_summary.get("selected_run_ids", [])) != {r["run_id"] for r in coding_summary["runs"]}:
        raise ValueError("Coding selected-run list and run rows differ")
    coding_runs = [_coding_run(root, row["run_dir"], row, inputs,
                               coding_registered.get(row["run_dir"].rstrip("/") + "/manifest.json"))
                   for row in coding_summary["runs"]]
    docops_runs = [_docops_run(root, row, inputs,
                               docops_registered[f"data/raw/generated/DOCOPS-OFFICE-REPEAT-02/{row['run_id']}/manifest.json"])
                   for row in docops_summary["results"]]
    assistant_runs = []
    for task, item in assistant_summary["per_task"].items():
        for run in item["runs"]:
            assistant_runs.append(_assistant_run(root, run, task, inputs,
                assistant_registered[f"data/raw/generated/TOOLSANDBOX-ASSISTANT-REPEAT-01/{run['run_id']}/manifest.json"],
                assistant_manifest["identity_sha256"]))
    if not (len(coding_runs) == len(docops_runs) == len(assistant_runs) == 9):
        raise ValueError("expected exactly the three explicitly registered 9-run batches")
    rows = coding_runs + docops_runs + assistant_runs
    for collection in ("P1-12-CODING-REPEAT-01", "DOCOPS-OFFICE-REPEAT-02",
                       "TOOLSANDBOX-ASSISTANT-REPEAT-01"):
        selected = [r for r in rows if r["collection"] == collection]
        if len({r["run_id"] for r in selected}) != 9:
            raise ValueError(f"run identity duplication in {collection}")
    report = {
        "schema": "local-measurement-coverage-v2",
        "scope": "exactly the nine run IDs selected by each accepted report/batch summary; no directory discovery",
        "collections": {
            "P1-12-CODING-REPEAT-01": {"runs": len(coding_runs), "run_ids": [r["run_id"] for r in coding_runs],
                "sources": ["cgroup v1/v2 evidence in samples.json", "host_process.jsonl records"]},
            "DOCOPS-OFFICE-REPEAT-02": {"runs": len(docops_runs), "run_ids": [r["run_id"] for r in docops_runs],
                "sources": ["summary.json samples and phase events", "environment.json", "measurement.json"]},
            "TOOLSANDBOX-ASSISTANT-REPEAT-01": {"runs": len(assistant_runs), "run_ids": [r["run_id"] for r in assistant_runs],
                "sources": ["samples.jsonl", "boundaries.jsonl", "environment.json", "result.json"]},
        },
        "historical_metric_classification": [
            {"metric": "CPU cumulative and timestamps", "coding": "A", "office": "A", "assistant": "A",
             "basis": "cgroup CPU usec for Coding/Office; shared worker process ticks for Assistant; raw monotonic samples/boundaries"},
            {"metric": "CPU interval average core", "coding": "B", "office": "B", "assistant": "B",
             "basis": "derivable from adjacent valid cumulative values, monotonic timestamps, and CLK_TCK where process ticks are used; gaps remain gaps"},
            {"metric": "memory.current", "coding": "A", "office": "A", "assistant": "E",
             "basis": "container cgroup current values in Coding/Office; ToolSandbox has process RSS instead"},
            {"metric": "process RSS", "coding": "A", "office": "A", "assistant": "A",
             "basis": "host process observations; shared runner/collector scope, not container kernel peak"},
            {"metric": "kernel memory peak", "coding": "A", "office": "A", "assistant": "D",
             "basis": "cgroup peak counters in Coding/Office; no historical worker-process kernel peak for Assistant"},
            {"metric": "disk I/O cumulative counters", "coding": "A", "office": "A", "assistant": "A",
             "basis": "cgroup block-service counters in Coding/Office; /proc/PID/io rchar/wchar/read_bytes/write_bytes in Assistant"},
            {"metric": "disk I/O rates", "coding": "B", "office": "B", "assistant": "B",
             "basis": "adjacent counter differences and actual sample times support offline rates; units/scopes differ and are not combined"},
            {"metric": "network tx/rx bytes", "coding": "D", "office": "D", "assistant": "D",
             "basis": "none of the selected historical run manifests contains saved network-interface or HTTP byte counters"},
            {"metric": "task directory disk footprint before/after", "coding": "D", "office": "D", "assistant": "D",
             "basis": "no historical boundary scans; current directory size cannot reconstruct prior occupancy"},
            {"metric": "attempt and lifecycle phase time", "coding": "A", "office": "A", "assistant": "A",
             "basis": "saved attempt wall and source-specific lifecycle/phase events; scope windows remain distinct"},
            {"metric": "requests/tools/returns/bootstrap", "coding": "A", "office": "A", "assistant": "A",
             "basis": "saved source-native events and transcripts; transport attempts are only reported when independently observable"},
            {"metric": "machine/runtime/limits", "coding": "C", "office": "C", "assistant": "C",
             "basis": "partial, source-specific environment, image and limit metadata; no single identical host/container snapshot across all runs"},
        ],
        "historical_rate_interval_coverage": {
            collection: _rate_coverage([r for r in rows if r["collection"] == collection], ())
            for collection in ("P1-12-CODING-REPEAT-01", "DOCOPS-OFFICE-REPEAT-02",
                               "TOOLSANDBOX-ASSISTANT-REPEAT-01")},
        "historical_disk_and_network_key_scan": {
            collection: {
                "selected_runs": sum(r["collection"] == collection for r in rows),
                "runs_with_candidate_network_keys": sum(
                    r["collection"] == collection and
                    bool(r["selected_resource_key_scan"]["network_counter_keys"]) for r in rows),
                "runs_with_candidate_directory_footprint_keys": sum(
                    r["collection"] == collection and
                    bool(r["selected_resource_key_scan"]["directory_footprint_keys"]) for r in rows),
            } for collection in ("P1-12-CODING-REPEAT-01", "DOCOPS-OFFICE-REPEAT-02",
                                 "TOOLSANDBOX-ASSISTANT-REPEAT-01")},
        "runs": rows,
        "limitations": ["Historical data are not rewritten.",
            "A means present as saved raw observation; B means derivable offline, not a newly measured value.",
            "cgroup block-service bytes, /proc I/O bytes, process RSS, memory.current and kernel peak are distinct scopes/semantics.",
            "No task-exclusive network byte or HTTP/TLS application payload measurement exists historically.",
            "Disk footprint history is absent; no current-size backfill is valid.",
            "Current collection code is not evidence that historical runs used these fields."]
    }
    return report, inputs


def write_report(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or (root / OUT)
    report, inputs = build_coverage(root)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to replace existing report: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "coverage.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 本地历史测量字段覆盖盘点 v2", "",
        f"范围：三个已登记批次各自显式选择的run，共{len(report['runs'])}个；未扫描或混入其他run。",
        "本报告只读历史记录，不回填或改写raw。", "",
        "状态：A=已有原始观测；B=可从有效原始相邻计数离线补算；C=部分可用；D=无历史观测、需新采；E=该scope不适用。", "",
        "| 指标 | Coding（9） | Office（9） | Assistant（9） | 本轮接入/限制 | 新运行？ |",
        "|---|---|---|---|---|---|"]
    descriptions = [
        ("CPU累计/时间/scope", "A", "A", "A", "保留cgroup usec与进程ticks两种scope，记录monotonic原始值", "否"),
        ("CPU区间平均core", "B", "B", "B", "从相邻有效计数差分；缺读/回退/无效时间为gap", "否，历史可补算"),
        ("memory.current", "A", "A", "E", "与RSS、内核peak分列；Assistant为进程RSS而非容器memory.current", "否"),
        ("进程RSS", "A", "A", "A", "宿主共享进程scope，不等同容器峰值", "否"),
        ("内核memory peak", "A", "A", "D", "Coding/Office cgroup；Assistant历史无进程内核peak", "Assistant需新采"),
        ("磁盘I/O累计/速率", "A/B", "A/B", "A/B", "cgroup块服务字节与/proc rchar/wchar/read_bytes/write_bytes分列", "否，速率可补算"),
        ("网络tx/rx", "D", "D", "D", "新接口仅为共享network namespace网卡累计计数；不是PID、HTTP正文或TLS精确字节", "是"),
        ("工作目录/输出/缓存占用", "D", "D", "D", "本轮边界扫描只量可见run输出目录表观大小；私有workspace/共享cache未知", "是"),
        ("attempt/阶段时间", "A", "A", "A", "原始阶段事件保留；观测窗口不混称attempt wall", "否"),
        ("请求/工具/返回/bootstrap", "A", "A", "A", "按各自原生事件；没有transport hook时HTTP尝试数仍unknown", "否"),
        ("机器/软件/限制/采样质量", "C", "C", "C", "字段按链路分散；环境/镜像、limits、PID与采样缺口不强行同口径", "部分"),
    ]
    for metric, c, d, a, note, rerun in descriptions:
        lines.append(f"| {metric} | {c} | {d} | {a} | {note} | {rerun} |")
    lines += ["", "## 历史累计计数的实际区间覆盖", "",
        "计数来自上述逐run实际记录。区间分母按每个相邻采样对×指标计；一个采样对中CPU有效而I/O无效时分别计数。",
        "| 批次 | 指标区间候选数 | 有效指标区间 | gap指标区间 |", "|---|---:|---:|---:|"]
    for collection, result in report["historical_rate_interval_coverage"].items():
        lines.append(f"| {collection} | {result['pairs']} | {result['valid_intervals']} | {result['gap_intervals']} |")
    lines += ["", "## 历史网络/磁盘边界候选字段扫描", "",
        "计数是含候选字段的run数，不把字段名本身当作确认的语义测量。", "",
        "| 批次 | 已选run | 含网络候选键run | 含目录占用候选键run |", "|---|---:|---:|---:|"]
    for collection, result in report["historical_disk_and_network_key_scan"].items():
        lines.append(f"| {collection} | {result['selected_runs']} | {result['runs_with_candidate_network_keys']} | {result['runs_with_candidate_directory_footprint_keys']} |")
    lines += ["", "## 当前实现的接线边界", "",
        "共享实现位于 `collectors/execution_measurement.py`：monotonic网络命名空间rx/tx累计采样、边界目录表观大小前后扫描、通用累计计数器相邻差分。Coding、DocOps/Office、ToolSandbox/Assistant生产入口均消费该实现；采集失败记录partial，不替代原清理/归档。",
        "Coding测量容器中的 `/testbed`；Office测量容器中的 `/root/submission`；Assistant情景状态为内存态（not_applicable），其宿主run输出目录另测。宿主日志/归档目录与容器任务目录分列；共享缓存仍unsupported。容器内依赖 `python3`，离线fake已验证调用边界，真实容器工具可用性尚未验证。",
        "历史记录没有这些磁盘边界；本轮接线不回填历史。历史网络字段候选计数按实际选定run生成，字段名本身不代替语义确认。", "",
        "## 当前采集能力与限制", "",
        "新网络读数来自采集进程所在network namespace的接口累计计数。它包含该namespace其他进程流量，不是PID/API专属；未实现透明且覆盖三条模型客户端路径的HTTP请求/流式响应正文计数，TLS/链路开销也不在可测范围。",
        "宿主输出目录按表观大小扫描，不量allocated blocks。容器私有workspace现仅限上述明确任务路径；共享缓存、镜像大小、宿主剩余空间不由其替代。扫描失败/超时为partial/null，不填0。",
        "历史报告v1保持原字节。其manifest记录的分析源码哈希与本轮修改前工作区该源码哈希已不同；本轮未声称重建v1所用源码，v2 manifest记录本轮实际分析代码。",
        "真实运行验收尚未进行。建议后续按Coding、Office、Assistant各授权一条小样本生产链，核实实际容器 `python3`、目录范围、网络scope、清理及归档；此建议不是执行授权。", ""]
    md_path = output_dir / "summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    code_paths = ["scripts/local_measurement_coverage.py",
        "src/agent_workload_characterization/collectors/execution_measurement.py",
        "src/agent_workload_characterization/collectors/resource_sampler.py",
        "src/agent_workload_characterization/runners/coding_pilot.py",
        "scripts/docops_word_resource_01_entry.py",
        "scripts/docops_office_repeat_02_entry.py",
        "scripts/toolsandbox_resource_pilot_01_entry.py",
        "scripts/toolsandbox_assistant_repeat_01_entry.py",
        "src/agent_workload_characterization/runners/run_02_entry.py"]
    manifest = {"schema": "local-measurement-coverage-manifest-v2",
        "inputs": [{"path": p, **record} for p, record in sorted(inputs.items())],
        "analysis_code": [{"path": p, **_hash(root / p)} for p in code_paths],
        "outputs": [{"path": (output_dir / name).relative_to(root).as_posix(),
                     **_hash(output_dir / name)} for name in ("summary.md", "coverage.json")],
        "manifest_self_hash": False,
        "interpretation": "the report was generated from the selected historic records; no historical field was backfilled into raw"}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    for item in manifest["outputs"]:
        actual = _hash(root / item["path"])
        if actual != {"bytes": item["bytes"], "sha256": item["sha256"]}:
            raise ValueError(f"output readback mismatch: {item['path']}")
    return report


if __name__ == "__main__":
    result = write_report()
    print(json.dumps({"runs": len(result["runs"]), "output": str(OUT)}, indent=2))
