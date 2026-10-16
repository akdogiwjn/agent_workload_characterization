#!/usr/bin/env python3
"""Bounded offline review of the nine TOOLSANDBOX-ASSISTANT-REPEAT-01 runs."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from toolsandbox_resource_pilot_02_review import _duration, _merge, _partition

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "TOOLSANDBOX-ASSISTANT-REPEAT-01"
IDENTITY = "1643e0c8c6158734ce7186d24afd5ce36d5a40718d930e7eea2a507f0b32149b"
REPORT_REL = Path("reports/resource") / COLLECTION
RAW_REL = Path("data/raw/generated") / COLLECTION
ENV_REL = Path("env") / "toolsandbox-assistant-repeat-01"
OUTPUT_REL = Path("reports/analysis") / f"{COLLECTION}-review-v1"
TASKS = {
    "A": "send_message_with_contact_content_cellular_off",
    "B": "add_reminder_content_and_week_delta_and_time",
    "C": "modify_contact_with_message_recency_multiple_user_turn",
}
SCHEDULE = (("A", "B", "C"), ("B", "C", "A"), ("C", "A", "B"))
STATIC_SOURCE_ROOT = Path("env/toolsandbox-resource-pilot-01/source")
STATIC_SOURCES = (
    "tool_sandbox/scenarios/base_scenarios.py",
    "tool_sandbox/scenarios/multiple_tool_call_scenarios.py",
    "tool_sandbox/scenarios/multiple_user_turn_scenarios.py",
    "tool_sandbox/tools/messaging.py",
    "tool_sandbox/tools/setting.py",
    "tool_sandbox/common/evaluation.py",
    "tool_sandbox/roles/execution_environment.py",
)
ANALYSIS_CODE = (
    Path("scripts/toolsandbox_assistant_repeat_01_review.py"),
    Path("scripts/toolsandbox_resource_pilot_02_review.py"),
)
MILESTONE_MEANINGS = {
    "A": [
        "cellular setting enabled",
        "search_contacts tool trace",
        "outgoing message state matches target recipient/content",
        "Agent confirmation message matches target text",
    ],
    "B": [
        "get_current_timestamp tool trace",
        "reminder content and tomorrow-at-17:00 timestamp",
    ],
    "C": [
        "get_current_timestamp tool trace",
        "search_contacts tool trace",
        "search_messages tool trace",
        "contact update derived from most recent sent message",
        "Agent confirmation of the contact update",
    ],
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path, root: Path, label: str | None = None) -> dict:
    data = path.read_bytes()
    return {"path": label or path.relative_to(root).as_posix(),
            "bytes": len(data), "sha256": sha256(data)}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row is not an object: {path}:{line_no}")
        rows.append(row)
    return rows


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _record_matches(root: Path, entry: dict, context: str) -> dict:
    rel = Path(entry["path"])
    require(not rel.is_absolute() and ".." not in rel.parts,
            f"unsafe manifest path in {context}: {entry.get('path')}")
    path = root / rel
    require(path.is_file(), f"manifest file missing ({context}): {entry['path']}")
    rec = file_record(path, root)
    require(rec["bytes"] == entry["bytes"] and rec["sha256"] == entry["sha256"],
            f"manifest hash mismatch ({context}): {entry['path']}")
    return rec


def _expected_positions() -> list[tuple[int, int, str, str]]:
    return [(round_no, pos, label, TASKS[label])
            for round_no, labels in enumerate(SCHEDULE)
            for pos, label in enumerate(labels)]


def verify_inputs(root: Path = ROOT) -> dict:
    report_dir = root / REPORT_REL
    raw_root = root / RAW_REL
    env_dir = root / ENV_REL
    outer_path = report_dir / "manifest.json"
    outer = read_json(outer_path)
    require(outer.get("identity_sha256") == IDENTITY and outer.get("manifest_self_hash") is False,
            "batch manifest identity or self-hash declaration mismatch")

    outer_records = []
    outer_entries: dict[str, dict] = {}
    for group in ("inputs", "outputs"):
        entries = outer.get(group)
        require(isinstance(entries, list), f"batch manifest {group} missing")
        for entry in entries:
            previous = outer_entries.get(entry["path"])
            require(previous is None or previous == entry,
                    f"batch manifest has conflicting records for: {entry['path']}")
            outer_entries[entry["path"]] = entry
            outer_records.append(_record_matches(root, entry, f"batch.{group}"))
    require("reports/resource/TOOLSANDBOX-ASSISTANT-REPEAT-01/batch-summary.json" in outer_entries,
            "batch summary is not registered by the batch manifest")
    summary = read_json(report_dir / "batch-summary.json")
    require(summary.get("collection") == COLLECTION and summary.get("execution_occurred") is True,
            "batch summary collection/execution state mismatch")
    require(summary.get("executed") == 9 and summary.get("not_executed_count") == 0 and
            summary.get("not_executed") == [] and summary.get("stop_reason") is None,
            "batch summary is not a complete nine-run execution")

    plan = read_json(env_dir / "plan-identity.json")
    frozen = read_json(env_dir / "frozen-identity.json")
    require(plan == frozen, "plan and frozen identity structures differ")
    identity_body = frozen.get("identity")
    require(isinstance(identity_body, dict), "frozen identity body missing")
    digest = sha256(json.dumps(identity_body, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8"))
    require(digest == IDENTITY and frozen.get("identity_sha256") == IDENTITY,
            "full frozen identity digest mismatch")
    require(identity_body.get("collection") == COLLECTION, "identity collection mismatch")
    identity_tasks = {item.get("name") for item in identity_body.get("scenario", {}).get("tasks", [])}
    require(identity_tasks == set(TASKS.values()), "frozen identity task set mismatch")
    frozen_rounds = identity_body.get("batch", {}).get("rounds")
    expected_rounds = [[TASKS[label] for label in labels] for labels in SCHEDULE]
    require(identity_body.get("batch", {}).get("run_count") == 9 and frozen_rounds == expected_rounds,
            "frozen identity run count or round schedule mismatch")
    source = identity_body.get("official_source", {})
    require(source.get("origin_commit") == "165848b9a78cead7ca7fe7c89c688b58e6501219",
            "frozen ToolSandbox commit mismatch")

    approval_path = report_dir / "APPROVAL.json"
    approval = read_json(approval_path)
    require(approval.get("collection") == COLLECTION and approval.get("user_approval") == "approved" and
            approval.get("identity_sha256") == IDENTITY and
            approval.get("accept_unknown_cost_no_hard_cap") is True,
            "batch approval identity/scope mismatch")
    started = read_json(report_dir / "BATCH_ATTEMPT_STARTED.json")
    completed = read_json(report_dir / "BATCH_ATTEMPT_COMPLETED.json")
    for marker in (started, completed):
        require(marker.get("collection") == COLLECTION and marker.get("identity_sha256") == IDENTITY,
                "batch marker identity mismatch")
    require(completed.get("executed") == 9 and completed.get("not_executed") == 0 and
            completed.get("stop_reason") is None, "completion marker does not confirm all nine runs")

    schedule = [[entry.get("label") for entry in round_items]
                for round_items in summary.get("schedule", [])]
    require(tuple(tuple(row) for row in schedule) == SCHEDULE, "batch schedule differs from frozen order")
    positions = _expected_positions()
    per_task = summary.get("per_task", {})
    require(set(per_task) == set(TASKS.values()), "batch per-task set mismatch")
    listed_runs = []
    expected_run_files: set[str] = set()
    run_rows = []
    for round_no, pos, label, task in positions:
        task_row = per_task[task]
        matches = [row for row in task_row.get("runs", [])
                   if row.get("round") == round_no and row.get("position_in_round") == pos]
        require(len(matches) == 1, f"missing or duplicate run at round {round_no}, position {pos}")
        row = matches[0]
        run_id = row.get("run_id")
        require(isinstance(run_id, str) and run_id and run_id not in listed_runs,
                "missing or duplicate run_id")
        listed_runs.append(run_id)
        require(row.get("task") == task and row.get("task_label") == label,
                f"task/label mismatch for {run_id}")
        report_path = Path(row["report_path"])
        raw_path = Path(row["raw_path"])
        require(report_path.is_relative_to(REPORT_REL) and raw_path.is_relative_to(RAW_REL),
                f"run paths escape fixed namespace: {run_id}")
        require(report_path.as_posix() in outer_entries and
                report_path.with_suffix(".manifest.json").as_posix() in outer_entries,
                f"run report or its manifest is not registered: {run_id}")
        report = read_json(root / report_path)
        report_manifest = read_json(root / report_path.with_suffix(".manifest.json"))
        require(report.get("identity_sha256") == IDENTITY and report.get("run_id") == run_id,
                f"run report identity mismatch: {run_id}")
        meta = report.get("run_metadata", {})
        require(meta.get("batch_identity_sha256") == IDENTITY and meta.get("round") == round_no and
                meta.get("position_in_round") == pos and meta.get("sequence_index") == len(run_rows) and
                meta.get("task_label") == label,
                f"run report schedule metadata mismatch: {run_id}")
        require(report.get("scenario") == task and report.get("exit_code") == row.get("exit_code") and
                report.get("archive_verification", {}).get("valid") is True,
                f"run report content/exit/archive mismatch: {run_id}")
        require(report_manifest.get("identity_sha256") == IDENTITY and
                report_manifest.get("run_id") == run_id,
                f"run report manifest identity mismatch: {run_id}")
        for group in ("inputs", "outputs"):
            for entry in report_manifest.get(group, []):
                _record_matches(root, entry, f"run-report.{run_id}.{group}")
        raw_dir = root / raw_path
        raw_manifest_path = raw_dir / "manifest.json"
        raw_manifest_record = outer.get("raw_run_manifests", [])
        raw_manifest_rel = (raw_path / "manifest.json").as_posix()
        ref_matches = [ref for ref in raw_manifest_record if ref.get("path") == raw_manifest_rel]
        require(len(ref_matches) == 1, f"raw manifest reference missing/duplicated: {run_id}")
        raw_manifest_ref = ref_matches[0]
        raw_manifest_file = file_record(raw_manifest_path, root, raw_manifest_rel)
        require(raw_manifest_file["bytes"] == raw_manifest_ref["bytes"] and
                raw_manifest_file["sha256"] == raw_manifest_ref["sha256"],
                f"outer raw manifest reference hash mismatch: {run_id}")
        raw_manifest = read_json(raw_manifest_path)
        require(raw_manifest.get("identity_sha256") == IDENTITY and raw_manifest.get("run_id") == run_id,
                f"raw manifest identity mismatch: {run_id}")
        raw_entries = raw_manifest.get("files", [])
        raw_paths = [entry.get("path") for entry in raw_entries]
        require(len(raw_paths) == len(set(raw_paths)), f"duplicate raw manifest file entry: {run_id}")
        actual = {p.relative_to(raw_dir).as_posix() for p in raw_dir.rglob("*")
                  if p.is_file() and p != raw_manifest_path}
        require(actual == set(raw_paths), f"raw file set differs from manifest: {run_id}")
        raw_records = [_record_matches(root, {**entry, "path": (raw_path / entry["path"]).as_posix()},
                                       f"raw.{run_id}") for entry in raw_entries]
        run_start = read_json(raw_dir / "ATTEMPT_STARTED.json")
        run_end = read_json(raw_dir / "ATTEMPT_COMPLETED.json")
        for marker in (run_start, run_end):
            require(marker.get("identity_sha256") == IDENTITY and marker.get("run_id") == run_id,
                    f"raw attempt marker identity mismatch: {run_id}")
        result = read_json(raw_dir / "result.json")
        require(result.get("run_id") == run_id and result.get("scenario_name") == task,
                f"raw result identity/task mismatch: {run_id}")
        worker_result = report.get("worker_result", {})
        require(worker_result.get("run_id") == run_id and
                worker_result.get("scenario_name") == task and
                worker_result.get("evaluation") == result.get("evaluation") and
                worker_result.get("counts") == result.get("counts") and
                worker_result.get("stop") == result.get("stop"),
                f"run report and raw result disagree: {run_id}")
        require(report.get("cleanup", {}).get("wait_reaped") is True and
                report.get("cleanup", {}).get("original_process_gone") is True and
                report.get("cleanup", {}).get("sampler_stopped") is True and
                report.get("within_total_budget") is True and
                report.get("deadline_timeout") is None,
                f"cleanup/deadline evidence incomplete: {run_id}")
        expected_run_files.add(run_id)
        run_rows.append({"task_label": label, "task": task, "round": round_no,
                         "position_in_round": pos, "sequence_index": len(run_rows),
                         "run_id": run_id, "report_path": report_path.as_posix(),
                         "raw_path": raw_path.as_posix(), "summary_row": row,
                         "report": report, "report_manifest": report_manifest,
                         "raw_manifest": raw_manifest, "raw_records": raw_records,
                         "result": result})
    require(len(listed_runs) == 9, "expected exactly nine unique run IDs")
    raw_manifest_refs = outer.get("raw_run_manifests", [])
    require({Path(ref["path"]).parent.name for ref in raw_manifest_refs} == set(listed_runs) and
            len(raw_manifest_refs) == 9, "batch raw manifest references differ from the nine runs")
    raw_children = {p.name for p in raw_root.iterdir()}
    require(raw_children == set(listed_runs), "formal raw namespace contains missing or unlisted run entries")
    per_task_run_ids = {
        row.get("run_id")
        for task_row in per_task.values()
        for row in task_row.get("runs", [])
    }
    require(per_task_run_ids == set(listed_runs), "per-task summary includes unexpected runs")

    # Verify the frozen official source snapshot used for static task/tool interpretation.
    source_manifest_rel = Path(identity_body["official_source"]["source_manifest"])
    source_manifest_path = root / source_manifest_rel
    source_manifest = read_json(source_manifest_path)
    source_manifest_file = file_record(source_manifest_path, root, source_manifest_rel.as_posix())
    require(source_manifest_file["sha256"] == identity_body["official_source"]["source_manifest_sha256"] and
            source_manifest.get("origin_commit") == "165848b9a78cead7ca7fe7c89c688b58e6501219",
            "frozen official source manifest identity mismatch")
    source_files = {entry["path"]: entry for entry in source_manifest.get("files", [])}
    static_records = []
    for rel in STATIC_SOURCES:
        entry = source_files.get(rel)
        require(entry is not None, f"static source not listed in frozen source manifest: {rel}")
        rec = file_record(root / STATIC_SOURCE_ROOT / rel, root, (STATIC_SOURCE_ROOT / rel).as_posix())
        require(rec["bytes"] == entry["bytes"] and rec["sha256"] == entry["sha256"],
                f"frozen source file hash mismatch: {rel}")
        static_records.append(rec)

    # Current execution-code alignment is reported independently of archived identity.
    current_code_checks = []
    current_code_records = []
    for entry in identity_body.get("code_and_runtime_files", []):
        path = root / entry["path"]
        if not path.is_file():
            current_code_checks.append({"path": entry["path"], "matches_frozen": False,
                                        "reason": "missing in current worktree"})
            continue
        rec = file_record(path, root)
        matches = rec["bytes"] == entry.get("bytes") and rec["sha256"] == entry.get("sha256")
        current_code_checks.append({"path": entry["path"], "matches_frozen": matches})
        current_code_records.append(rec)
    current_code_matches = bool(current_code_checks) and all(row["matches_frozen"]
                                                              for row in current_code_checks)

    inputs_by_path = {rec["path"]: rec for rec in outer_records}
    inputs_by_path[outer_path.relative_to(root).as_posix()] = file_record(outer_path, root)
    for row in run_rows:
        raw_manifest_path = root / row["raw_path"] / "manifest.json"
        inputs_by_path[raw_manifest_path.relative_to(root).as_posix()] = file_record(raw_manifest_path, root)
        for rec in row["raw_records"]:
            inputs_by_path[rec["path"]] = rec
    for rec in static_records + [source_manifest_file] + current_code_records:
        inputs_by_path[rec["path"]] = rec
    # These are directly parsed identity/approval records; their hashes are already in the outer manifest,
    # but keeping their explicit records makes the analysis lineage easy to inspect.
    for path in (env_dir / "plan-identity.json", env_dir / "frozen-identity.json",
                 env_dir / "source-manifest.json", env_dir / "preparation-manifest.json",
                 report_dir / "APPROVAL.json", report_dir / "BATCH_ATTEMPT_STARTED.json",
                 report_dir / "BATCH_ATTEMPT_COMPLETED.json", report_dir / "batch-summary.json"):
        if path.is_file():
            rec = file_record(path, root)
            inputs_by_path[rec["path"]] = rec

    return {"report_dir": report_dir, "raw_root": raw_root, "env_dir": env_dir,
            "outer_manifest": outer, "summary": summary, "plan": plan, "frozen": frozen,
            "approval": approval, "started": started, "completed": completed,
            "runs": run_rows, "source_manifest": source_manifest,
            "static_source_records": static_records,
            "current_code_matches_frozen": current_code_matches,
            "current_code_checks": current_code_checks,
            "inputs": sorted(inputs_by_path.values(), key=lambda item: item["path"])}


def _spans(events: list[dict]) -> tuple[list[dict], dict]:
    opens: dict[tuple[str, str], list[dict]] = {}
    terminals: dict[tuple[str, str], list[dict]] = {}
    missing_id = []
    invalid_time = []
    for index, event in enumerate(events):
        kind, status, event_id = event.get("kind"), event.get("status"), event.get("event_id")
        if kind not in ("run", "llm_request", "tool_call", "tool_batch"):
            continue
        if not isinstance(event_id, str) or not event_id:
            if status in ("open", "closed", "error"):
                missing_id.append({"index": index, "kind": kind, "status": status})
            continue
        timestamp = event.get("t_monotonic_ns")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            invalid_time.append({"index": index, "event_id": event_id, "kind": kind})
            continue
        key = (kind, event_id)
        if status == "open":
            opens.setdefault(key, []).append(event)
        elif status in ("closed", "error"):
            terminals.setdefault(key, []).append(event)
    result, duplicate_open, duplicate_terminal, orphan, unclosed = [], [], [], [], []
    for key in sorted(set(opens) | set(terminals)):
        os_, ts_ = opens.get(key, []), terminals.get(key, [])
        if len(os_) > 1:
            duplicate_open.append({"kind": key[0], "event_id": key[1], "count": len(os_)})
        if len(ts_) > 1:
            duplicate_terminal.append({"kind": key[0], "event_id": key[1], "count": len(ts_)})
        if len(os_) == 1 and len(ts_) == 1:
            start, terminal = os_[0], ts_[0]
            if terminal["t_monotonic_ns"] < start["t_monotonic_ns"]:
                invalid_time.append({"event_id": key[1], "kind": key[0], "reason": "terminal_before_open"})
                continue
            result.append({"event_id": key[1], "kind": key[0], "status": terminal["status"],
                           "start_ns": start["t_monotonic_ns"], "end_ns": terminal["t_monotonic_ns"],
                           "duration_s": (terminal["t_monotonic_ns"] - start["t_monotonic_ns"]) / 1e9,
                           "open": start, "terminal": terminal,
                           "attrs": start.get("attrs") if isinstance(start.get("attrs"), dict) else {},
                           "terminal_attrs": terminal.get("attrs") if isinstance(terminal.get("attrs"), dict) else {}})
        elif len(os_) == 1 and not ts_:
            unclosed.append({"kind": key[0], "event_id": key[1]})
        elif len(ts_) and not os_:
            orphan.append({"kind": key[0], "event_id": key[1], "count": len(ts_)})
        elif os_ and ts_:
            # Duplicate IDs are explicitly ambiguous; do not pair by position.
            continue
    quality = {"missing_id_events": missing_id, "duplicate_open_ids": duplicate_open,
               "duplicate_terminal_ids": duplicate_terminal, "orphan_terminals": orphan,
               "unclosed_spans": unclosed, "invalid_times": invalid_time}
    return sorted(result, key=lambda row: (row["start_ns"], row["kind"], row["event_id"])), quality


def _valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _stats(values: list[Any]) -> dict:
    valid = [float(value) for value in values if _valid_number(value)]
    ordered = sorted(valid)
    if not ordered:
        return {"n": 0, "missing": len(values), "raw_points": values,
                "median": None, "q1": None, "q3": None, "iqr": None, "min": None, "max": None,
                "quantile_method": "linear interpolation at (n-1)*p"}

    def quantile(p: float) -> float:
        index = (len(ordered) - 1) * p
        lo, hi = math.floor(index), math.ceil(index)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)

    q1, q3 = quantile(.25), quantile(.75)
    return {"n": len(ordered), "missing": len(values) - len(ordered), "raw_points": values,
            "median": median(ordered), "q1": q1, "q3": q3, "iqr": q3 - q1,
            "min": ordered[0], "max": ordered[-1],
            "quantile_method": "linear interpolation at (n-1)*p"}


def _phase_boundaries(rows: list[dict]) -> tuple[dict, dict]:
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        by_name.setdefault(str(row.get("phase")), []).append(row)
    duplicates = {key: len(value) for key, value in by_name.items() if len(value) != 1}
    return {key: value[0] for key, value in by_name.items() if len(value) == 1}, duplicates


def _counter_delta(left: dict, right: dict, key: str) -> int | None:
    a, b = left.get(key), right.get(key)
    if (not isinstance(a, int) or isinstance(a, bool) or not isinstance(b, int) or isinstance(b, bool)
            or b < a):
        return None
    return b - a


def _phase_metrics(boundary: dict[str, dict], clk_tck: Any) -> dict:
    pairs = {
        "setup": ("worker_start", "play_begin"),
        "imports": ("imports_begin", "imports_end"),
        "play": ("play_begin", "play_end"),
        "play_to_evaluation_gap": ("play_end", "evaluate_begin"),
        "evaluator": ("evaluate_begin", "evaluate_end"),
        "worker_tail": ("evaluate_end", "worker_end"),
    }
    phases = {}
    for name, (start_name, end_name) in pairs.items():
        left, right = boundary.get(start_name), boundary.get(end_name)
        if left is None or right is None:
            phases[name] = {"status": "unavailable", "reason": "missing or duplicate phase boundary"}
            continue
        t0, t1 = left.get("t_monotonic_ns"), right.get("t_monotonic_ns")
        if not isinstance(t0, int) or isinstance(t0, bool) or not isinstance(t1, int) or isinstance(t1, bool) or t1 < t0:
            phases[name] = {"status": "unavailable", "reason": "invalid or reversed monotonic boundary"}
            continue
        valid_read = all((row.get("read_status") or {}).get("stat") == "ok" for row in (left, right))
        ticks = _counter_delta(left, right, "cpu_ticks") if valid_read else None
        user = _counter_delta(left, right, "user_ticks") if valid_read else None
        system = _counter_delta(left, right, "system_ticks") if valid_read else None
        io = {}
        for key in ("rchar", "wchar", "read_bytes", "write_bytes"):
            before = (left.get("process_io") or {}).get(key)
            after = (right.get("process_io") or {}).get(key)
            io[key] = after - before if (isinstance(before, int) and not isinstance(before, bool) and
                                         isinstance(after, int) and not isinstance(after, bool) and after >= before) else None
        seconds = ticks / clk_tck if ticks is not None and _valid_number(clk_tck) and clk_tck > 0 else None
        phases[name] = {"status": "observed" if valid_read else "partial_read_status",
                        "start_ns": t0, "end_ns": t1, "wall_s": (t1 - t0) / 1e9,
                        "cpu_ticks": ticks, "user_ticks": user, "system_ticks": system,
                        "process_cpu_s": seconds, "clk_tck": clk_tck if _valid_number(clk_tck) else None,
                        "process_io_delta_bytes": io,
                        "boundary_rss_start_bytes": left.get("rss_bytes"),
                        "boundary_rss_end_bytes": right.get("rss_bytes")}
    required = ("setup", "play", "play_to_evaluation_gap", "evaluator", "worker_tail")
    worker_ticks = _counter_delta(boundary.get("worker_start", {}), boundary.get("worker_end", {}), "cpu_ticks")
    phase_ticks = [phases[name].get("cpu_ticks") for name in required]
    complete = all(value is not None for value in phase_ticks) and worker_ticks is not None
    worker_wall = None
    if boundary.get("worker_start") and boundary.get("worker_end"):
        worker_wall = (boundary["worker_end"]["t_monotonic_ns"] - boundary["worker_start"]["t_monotonic_ns"]) / 1e9
    return {"phases": phases, "worker_boundary_cpu_ticks": worker_ticks,
            "phase_cpu_ticks_sum": sum(phase_ticks) if complete else None,
            "phase_cpu_conservation_residual_ticks": worker_ticks - sum(phase_ticks) if complete else None,
            "phase_wall_sum_s": sum(phases[name]["wall_s"] for name in required
                                     if isinstance(phases[name].get("wall_s"), (int, float))),
            "worker_boundary_wall_s": worker_wall,
            "phase_wall_conservation_residual_s": (worker_wall - sum(phases[name]["wall_s"] for name in required)
                                                   if worker_wall is not None and
                                                   all(isinstance(phases[name].get("wall_s"), (int, float)) for name in required)
                                                   else None),
            "setup_window_definition": "worker_start to play_begin; includes imports and scenario/client setup",
            "imports_window_is_subwindow_of_setup": True}


def _sample_metrics(samples: list[dict], boundaries: dict[str, dict], spans: list[dict], clk_tck: Any) -> dict:
    times = [row.get("t_monotonic_ns") for row in samples]
    valid_intervals = []
    nonpositive, regressions, invalid_status, invalid_time = [], [], [], []
    status_counts = {key: 0 for key in ("stat", "io", "status")}
    for index, row in enumerate(samples):
        status = row.get("read_status") if isinstance(row.get("read_status"), dict) else {}
        for key in status_counts:
            if status.get(key) != "ok":
                status_counts[key] += 1
    for index in range(1, len(samples)):
        prev, cur = samples[index - 1], samples[index]
        t0, t1 = prev.get("t_monotonic_ns"), cur.get("t_monotonic_ns")
        if not isinstance(t0, int) or isinstance(t0, bool) or not isinstance(t1, int) or isinstance(t1, bool):
            invalid_time.append(index)
            continue
        if t1 <= t0:
            nonpositive.append(index)
            continue
        if ((prev.get("read_status") or {}).get("stat") != "ok" or
                (cur.get("read_status") or {}).get("stat") != "ok"):
            invalid_status.append(index)
            continue
        p, c = prev.get("cpu_ticks"), cur.get("cpu_ticks")
        if not isinstance(p, int) or isinstance(p, bool) or not isinstance(c, int) or isinstance(c, bool):
            invalid_status.append(index)
            continue
        if c < p:
            regressions.append(index)
            continue
        user = _counter_delta(prev, cur, "user_ticks")
        system = _counter_delta(prev, cur, "system_ticks")
        valid_intervals.append({"index": index, "start_ns": t0, "end_ns": t1,
                                "wall_s": (t1 - t0) / 1e9, "cpu_ticks": c - p,
                                "user_ticks": user, "system_ticks": system})
    gaps = [row["wall_s"] for row in valid_intervals]
    stat_ok = [row for row in samples if (row.get("read_status") or {}).get("stat") == "ok"]
    rss_values = [row.get("rss_bytes") for row in stat_ok
                  if isinstance(row.get("rss_bytes"), int) and not isinstance(row.get("rss_bytes"), bool)]
    thread_values = [row.get("threads") for row in stat_ok
                     if isinstance(row.get("threads"), int) and not isinstance(row.get("threads"), bool)]
    pids = sorted({row.get("pid") for row in samples if isinstance(row.get("pid"), int)})
    starts = sorted({row.get("starttime_ticks") for row in samples if isinstance(row.get("starttime_ticks"), int)})

    phase_points = sorted({row.get("t_monotonic_ns") for row in boundaries.values()
                           if isinstance(row.get("t_monotonic_ns"), int)})
    event_edges = [edge for span in spans if span["kind"] in ("llm_request", "tool_batch")
                   for edge in (span["start_ns"], span["end_ns"])]
    play_start = boundaries.get("play_begin", {}).get("phase_start_ns",
                                                       boundaries.get("play_begin", {}).get("t_monotonic_ns"))
    play_end = boundaries.get("play_end", {}).get("phase_end_ns",
                                                   boundaries.get("play_end", {}).get("t_monotonic_ns"))
    categories = {key: {"cpu_ticks": 0, "wall_s": 0.0, "intervals": 0} for key in (
        "request_only", "batch_only", "overlap", "uncovered", "outside_play",
        "mixed_phase_boundary", "mixed_event_boundary")}
    requests = [span for span in spans if span["kind"] == "llm_request"]
    batches = [span for span in spans if span["kind"] == "tool_batch"]
    for interval in valid_intervals:
        lo, hi = interval["start_ns"], interval["end_ns"]
        if not isinstance(play_start, int) or not isinstance(play_end, int) or hi <= play_start or lo >= play_end:
            category = "outside_play"
        elif lo < play_start or hi > play_end or any(lo < point < hi for point in phase_points):
            category = "mixed_phase_boundary"
        elif any(lo < point < hi for point in event_edges):
            category = "mixed_event_boundary"
        else:
            mid = (lo + hi) // 2
            in_request = any(span["start_ns"] <= mid < span["end_ns"] for span in requests)
            in_batch = any(span["start_ns"] <= mid < span["end_ns"] for span in batches)
            category = ("overlap" if in_request and in_batch else "request_only" if in_request
                        else "batch_only" if in_batch else "uncovered")
        categories[category]["cpu_ticks"] += interval["cpu_ticks"]
        categories[category]["wall_s"] += interval["wall_s"]
        categories[category]["intervals"] += 1
    total_ticks = sum(row["cpu_ticks"] for row in valid_intervals)
    categorized_ticks = sum(row["cpu_ticks"] for row in categories.values())
    io = {}
    if samples and all((row.get("read_status") or {}).get("io") == "ok"
                       for row in (samples[0], samples[-1])):
        first, last = samples[0].get("process_io", {}), samples[-1].get("process_io", {})
        for key in ("rchar", "wchar", "read_bytes", "write_bytes"):
            a, b = first.get(key), last.get(key)
            io[key] = b - a if (isinstance(a, int) and not isinstance(a, bool) and
                                isinstance(b, int) and not isinstance(b, bool) and b >= a) else None
    return {"sample_count": len(samples),
            "sample_window_start_ns": times[0] if times else None,
            "sample_window_end_ns": times[-1] if times else None,
            "sample_window_s": (times[-1] - times[0]) / 1e9 if len(times) and
                                isinstance(times[0], int) and not isinstance(times[0], bool) and
                                isinstance(times[-1], int) and not isinstance(times[-1], bool) and
                                times[-1] >= times[0] else None,
            "valid_cpu_intervals": len(valid_intervals),
            "cpu_ticks_delta": total_ticks if valid_intervals else None,
            "user_ticks_delta": sum(row["user_ticks"] for row in valid_intervals)
            if valid_intervals and all(row["user_ticks"] is not None for row in valid_intervals) else None,
            "system_ticks_delta": sum(row["system_ticks"] for row in valid_intervals)
            if valid_intervals and all(row["system_ticks"] is not None for row in valid_intervals) else None,
            "process_cpu_s": total_ticks / clk_tck if valid_intervals and
                            _valid_number(clk_tck) and clk_tck > 0 else None,
            "clk_tck": clk_tck if _valid_number(clk_tck) else None,
            "cpu_seconds_basis": "saved per-run environment.sc_clk_tck; no current-host fallback",
            "rss_sampled_peak_bytes": max(rss_values) if rss_values else None,
            "rss_sample_count": len(rss_values),
            "thread_count_min": min(thread_values) if thread_values else None,
            "thread_count_max": max(thread_values) if thread_values else None,
            "thread_count_frequency": {str(value): count for value, count in sorted(Counter(thread_values).items())},
            "thread_count_observations": len(thread_values),
            "pid_values": pids, "starttime_ticks_values": starts,
            "read_status_non_ok_counts": status_counts,
            "invalid_time_intervals": invalid_time,
            "nonpositive_time_intervals": nonpositive,
            "cpu_counter_regression_intervals": regressions,
            "invalid_cpu_or_status_intervals": invalid_status,
            "sample_gap_s": {"n": len(gaps), "min": min(gaps) if gaps else None,
                             "max": max(gaps) if gaps else None},
            "sample_interval_cpu_partition": categories,
            "sample_interval_cpu_conservation": {"valid_cpu_ticks": total_ticks if valid_intervals else None,
                                                  "categorized_cpu_ticks": categorized_ticks if valid_intervals else None,
                                                  "residual_ticks": total_ticks - categorized_ticks if valid_intervals else None,
                                                  "empty_category_zero_note": "0 CPU ticks in a category with zero eligible intervals means no interval was assigned, not an observed zero-cost activity"},
            "sampled_proc_io_delta_bytes": io,
            "io_scope_note": "process /proc counters; not complete filesystem or application I/O",
            "memory_scope_note": "RSS is sampled process RSS; no kernel memory peak was collected"}


def _event_analysis(events: list[dict], boundaries: list[dict], result: dict,
                    report: dict, sample_rows: list[dict]) -> dict:
    spans, quality = _spans(events)
    requests = [span for span in spans if span["kind"] == "llm_request"]
    calls = [span for span in spans if span["kind"] == "tool_call"]
    batches = [span for span in spans if span["kind"] == "tool_batch"]
    raw_tool_call_opens = sum(1 for event in events if event.get("kind") == "tool_call" and
                              event.get("status") == "open")
    unclosed_tool_calls = [item for item in quality["unclosed_spans"] if item["kind"] == "tool_call"]
    orphan_tool_returns = [item for item in quality["orphan_terminals"] if item["kind"] == "tool_call"]
    duplicate_tool_event_ids = [item for key in ("duplicate_open_ids", "duplicate_terminal_ids")
                                for item in quality[key] if item["kind"] == "tool_call"]
    request_id_counts: dict[str, int] = {}
    for span in requests:
        request_id = span["attrs"].get("request_id")
        if isinstance(request_id, str) and request_id:
            request_id_counts[request_id] = request_id_counts.get(request_id, 0) + 1
    request_id_quality = {
        "missing_request_id_count": sum(
            not isinstance(span["attrs"].get("request_id"), str) or not span["attrs"].get("request_id")
            for span in requests),
        "duplicate_request_ids": sorted(key for key, count in request_id_counts.items() if count > 1),
    }
    request_role_counts = {role: sum(1 for span in requests if span["attrs"].get("role") == role)
                           for role in ("agent", "user")}
    project_attempts = [span["terminal_attrs"].get("transport_attempt_count") for span in requests]
    role_tool_counts = {role: sum(1 for span in calls if span["attrs"].get("role") == role)
                        for role in ("agent", "user")}
    user_end_calls = [span for span in calls if span["attrs"].get("role") == "user" and
                      span["attrs"].get("tool_name") == "end_conversation"]
    calls_by_request: dict[str, list[dict]] = {}
    unmatched_tool_request_ids = []
    for span in calls:
        request_id = span["attrs"].get("request_event_id")
        if not isinstance(request_id, str) or request_id not in request_id_counts or request_id_counts[request_id] != 1:
            unmatched_tool_request_ids.append({"event_id": span["event_id"], "request_event_id": request_id})
        else:
            calls_by_request.setdefault(request_id, []).append(span)
    ordered_calls = sorted(calls, key=lambda span: (span["start_ns"], span["event_id"]))
    paths_by_role = {
        role: [span["attrs"].get("tool_name") for span in ordered_calls if span["attrs"].get("role") == role]
        for role in ("agent", "user")}
    request_details = [{"event_id": span["event_id"], "request_id": span["attrs"].get("request_id"),
                        "role": span["attrs"].get("role"), "start_ns": span["start_ns"],
                        "end_ns": span["end_ns"], "duration_s": span["duration_s"],
                        "request_model": span["attrs"].get("model"),
                        "response_model": span["terminal_attrs"].get("response_model"),
                        "project_layer_attempt_count": span["terminal_attrs"].get("transport_attempt_count"),
                        "usage": span["terminal_attrs"].get("usage"), "status": span["status"]}
                       for span in requests]
    call_details = []
    for span in ordered_calls:
        request_id = span["attrs"].get("request_event_id")
        terminal_error = span["terminal_attrs"].get("error")
        error_class = terminal_error.split(":", 1)[0] if isinstance(terminal_error, str) else None
        call_details.append({"event_id": span["event_id"], "tool_name": span["attrs"].get("tool_name"),
                             "role": span["attrs"].get("role"), "request_id": request_id,
                             "start_ns": span["start_ns"], "end_ns": span["end_ns"],
                             "duration_s": span["duration_s"], "status": span["status"],
                             "ok": span["terminal_attrs"].get("ok"), "error_class": error_class,
                             "argument_sha256": span["attrs"].get("argument_sha256"),
                             "result_bytes": span["terminal_attrs"].get("result_bytes")})
    batch_details = []
    batch_call_id_values = []
    missing_native_call_id_slots = 0
    call_id_name_count_mismatches = []
    batch_ordering_planned = 0
    batch_ordering_executed = 0
    for span in batches:
        call_ids = span["attrs"].get("call_ids")
        call_ids = call_ids if isinstance(call_ids, list) else []
        names = span["attrs"].get("tool_names")
        names = names if isinstance(names, list) else []
        valid_ids = [value for value in call_ids if isinstance(value, str) and value]
        missing_native_call_id_slots += max(0, len(names) - len(valid_ids))
        if len(names) != len(valid_ids):
            call_id_name_count_mismatches.append({"event_id": span["event_id"],
                                                  "tool_name_count": len(names),
                                                  "native_call_id_count": len(valid_ids)})
        batch_call_id_values.extend(valid_ids)
        planned = span["terminal_attrs"].get("planned_orderings")
        executed = span["terminal_attrs"].get("executed_orderings")
        if isinstance(planned, int) and not isinstance(planned, bool):
            batch_ordering_planned += planned
        if isinstance(executed, int) and not isinstance(executed, bool):
            batch_ordering_executed += executed
        batch_details.append({"event_id": span["event_id"], "batch_index": span["attrs"].get("batch_index"),
                              "start_ns": span["start_ns"], "end_ns": span["end_ns"],
                              "duration_s": span["duration_s"],
                              "tool_names": names,
                              "native_call_id_count": len(call_ids),
                              "planned_orderings": planned, "executed_orderings": executed,
                              "status": span["status"],
                              "resource_before": span["terminal_attrs"].get("resource_before"),
                              "resource_after": span["terminal_attrs"].get("resource_after")})
    setup_rows = [row for row in boundaries if row.get("phase") == "system_setup_exec"]
    wrapper_execs = result.get("counts", {}).get("tool_call_executions")
    user_end_close = max((span["end_ns"] for span in user_end_calls), default=None)
    requests_after_end = sum(1 for span in requests if user_end_close is not None and span["start_ns"] > user_end_close)
    all_args_hashes = [span["attrs"].get("argument_sha256") for span in calls]
    batch_call_id_counts: dict[str, int] = {}
    for call_id in batch_call_id_values:
        batch_call_id_counts[call_id] = batch_call_id_counts.get(call_id, 0) + 1
    return {"event_counts": {f"{event.get('kind')}:{event.get('status')}":
                             sum(1 for item in events if item.get("kind") == event.get("kind") and
                                 item.get("status") == event.get("status"))
                             for event in events if event.get("kind") in ("run", "llm_request", "tool_call", "tool_batch")},
            "span_quality": quality,
            "logical_requests": {"agent": request_role_counts["agent"], "user": request_role_counts["user"],
                                 "total": len(requests), "project_layer_attempt_counts": project_attempts,
                                 "project_layer_attempt_total": sum(
                                     (value for value in project_attempts
                                      if isinstance(value, int) and not isinstance(value, bool)), 0),
                                 "actual_http_transmissions": "unknown; no transport-level hook",
                                 "request_models": sorted({span["attrs"].get("model") for span in requests
                                                            if isinstance(span["attrs"].get("model"), str)}),
                                 "response_models": sorted({span["terminal_attrs"].get("response_model")
                                                            for span in requests if isinstance(span["terminal_attrs"].get("response_model"), str)}),
                                 "details": request_details},
            "tool_calls": {"logical_call_spans": len(calls), "by_role": role_tool_counts,
                           "raw_open_call_event_count": raw_tool_call_opens,
                           "missing_return_count": len(unclosed_tool_calls),
                           "orphan_return_count": len(orphan_tool_returns),
                           "duplicate_call_event_ids": duplicate_tool_event_ids,
                           "agent_tool_call_count": role_tool_counts["agent"],
                           "user_end_conversation_count": len(user_end_calls),
                           "system_setup_exec_count": len(setup_rows),
                           "details": call_details, "saved_agent_tool_sequence": paths_by_role["agent"],
                           "saved_user_tool_sequence": paths_by_role["user"],
                           "sequence_note": "ordered by saved monotonic start; does not prove concurrent-call execution order",
                           "tool_request_link_unmatched": unmatched_tool_request_ids,
                           "request_id_quality": request_id_quality,
                           "all_returns_saved": (raw_tool_call_opens == len(calls) and not unclosed_tool_calls and
                                                 not orphan_tool_returns and not duplicate_tool_event_ids),
                           "all_calls_have_ok_boolean": all(isinstance(span["terminal_attrs"].get("ok"), bool) for span in calls),
                           "ok_return_count": sum(span["terminal_attrs"].get("ok") is True for span in calls),
                           "not_ok_return_count": sum(span["terminal_attrs"].get("ok") is False for span in calls),
                           "error_count": sum(span["status"] == "error" for span in calls)},
            "tool_batches": {"count": len(batches), "details": batch_details,
                             "planned_orderings": batch_ordering_planned,
                             "executed_orderings": batch_ordering_executed,
                             "wrapper_execution_count_from_result": wrapper_execs,
                             "system_setup_count": len(setup_rows),
                             "wrapper_execution_crosscheck": wrapper_execs == batch_ordering_executed + len(setup_rows),
                             "native_call_id_occurrences": len(batch_call_id_values),
                             "missing_native_call_id_slots_by_batch_counts": missing_native_call_id_slots,
                             "call_id_name_count_mismatches": call_id_name_count_mismatches,
                             "duplicate_native_call_ids": sorted(key for key, count in batch_call_id_counts.items() if count > 1),
                             "individual_call_to_batch_direct_id_link": "not present in saved event attributes; no positional pairing",
                             "batch_to_call_id_occurrences_are_not_one_to_one_proof": True},
            "termination": {"worker_exit_code": report.get("worker_exit_code"),
                            "entry_exit_code": report.get("exit_code"),
                            "deadline_timeout": report.get("deadline_timeout"),
                            "within_total_budget": report.get("within_total_budget"),
                            "conversation_active": result.get("stop", {}).get("conversation_active"),
                            "user_end_conversation_executed": result.get("stop", {}).get("user_end_conversation_executed"),
                            "conversation_stop_reason": result.get("stop", {}).get("reason"),
                            "requests_after_last_user_end_conversation": requests_after_end,
                            "run_root_open_close": next(({"open_ns": span["start_ns"], "close_ns": span["end_ns"],
                                                           "closed": span["status"] == "closed"}
                                                          for span in spans if span["kind"] == "run"), None)},
            "errors": _error_review(call_details, request_details, result, setup_rows),
            "argument_hashes_include_known_empty_object": sha256(b"{}") in all_args_hashes,
            "raw_call_event_count_matches_result": len(calls) == result.get("counts", {}).get("logical_tool_calls", {}).get("started"),
            "raw_batch_count_matches_result": len(batches) == result.get("counts", {}).get("tool_batches", {}).get("started"),
            "request_count_matches_result": (request_role_counts["agent"] == result.get("counts", {}).get("agent_logical_calls") and
                                              request_role_counts["user"] == result.get("counts", {}).get("user_logical_calls"))}


def _error_review(calls: list[dict], requests: list[dict], result: dict, setup_rows: list[dict]) -> list[dict]:
    errors = [call for call in calls if call["status"] == "error"]
    reviewed = []
    for error in errors:
        next_requests = sorted((request for request in requests if request.get("role") == error.get("role") and
                                request["start_ns"] > error["end_ns"]), key=lambda item: item["start_ns"])
        next_request = next_requests[0] if next_requests else None
        following = [call for call in calls if next_request is not None and
                     call.get("request_id") == next_request.get("request_id")]
        all_later_requests = [request for request in requests if request.get("role") == error.get("role") and
                              request["start_ns"] > error["end_ns"]]
        later_request_ids = {request.get("request_id") for request in all_later_requests}
        later_calls = [call for call in calls if call.get("request_id") in later_request_ids]
        reviewed.append({"event_id": error["event_id"], "tool_name": error["tool_name"],
                         "request_id": error["request_id"], "error_class": error["error_class"],
                         "argument_sha256": error.get("argument_sha256"),
                         "next_same_role_request_id": next_request.get("request_id") if next_request else None,
                         "next_request_tool_calls": [{"tool_name": call["tool_name"], "status": call["status"],
                                                       "ok": call["ok"], "event_id": call["event_id"]}
                                                      for call in following],
                         "all_later_same_role_tool_calls_in_saved_start_order": [
                             {"request_id": call["request_id"], "tool_name": call["tool_name"],
                              "status": call["status"], "ok": call["ok"], "event_id": call["event_id"]}
                             for call in sorted(later_calls, key=lambda item: (item["start_ns"], item["event_id"]))],
                         "evaluation_similarity": result.get("evaluation", {}).get("similarity"),
                         "error_is_tool_result_not_infra_by_event_kind": True})
    return reviewed


def _run_analysis(root: Path, row: dict) -> dict:
    raw_dir = root / row["raw_path"]
    report = row["report"]
    result = row["result"]
    events = read_jsonl(raw_dir / "events.jsonl")
    samples = read_jsonl(raw_dir / "samples.jsonl")
    boundaries_rows = read_jsonl(raw_dir / "boundaries.jsonl")
    environment = read_json(raw_dir / "environment.json")
    boundaries, duplicate_phases = _phase_boundaries(boundaries_rows)
    spans, quality = _spans(events)
    behavior = _event_analysis(events, boundaries_rows, result, report, samples)
    for error in behavior["errors"]:
        error["run_id"] = row["run_id"]
    clk_tck = environment.get("sc_clk_tck")
    phases = _phase_metrics(boundaries, clk_tck)
    resources = _sample_metrics(samples, boundaries, spans, clk_tck)
    play_start = boundaries.get("play_begin", {}).get("phase_start_ns",
                                                       boundaries.get("play_begin", {}).get("t_monotonic_ns"))
    play_end = boundaries.get("play_end", {}).get("phase_end_ns",
                                                   boundaries.get("play_end", {}).get("t_monotonic_ns"))
    request_intervals = [(span["start_ns"], span["end_ns"]) for span in spans if span["kind"] == "llm_request"]
    batch_intervals = [(span["start_ns"], span["end_ns"]) for span in spans if span["kind"] == "tool_batch"]
    partition = None
    if isinstance(play_start, int) and isinstance(play_end, int) and play_end >= play_start:
        partition = _partition((play_start, play_end), request_intervals, batch_intervals)
        partition["request_union_s"] = _duration(_merge(request_intervals))
        partition["agent_request_union_s"] = _duration(_merge([
            (span["start_ns"], span["end_ns"]) for span in spans
            if span["kind"] == "llm_request" and span["attrs"].get("role") == "agent"]))
        partition["user_request_union_s"] = _duration(_merge([
            (span["start_ns"], span["end_ns"]) for span in spans
            if span["kind"] == "llm_request" and span["attrs"].get("role") == "user"]))
        partition["tool_batch_union_s"] = _duration(_merge(batch_intervals))
        partition["window_definition"] = "play_begin to play_end on saved system monotonic clock; request union combines Agent and User"
    tool_sequence = behavior["tool_calls"]["saved_agent_tool_sequence"]
    eval_data = result.get("evaluation", {})
    milestone_mapping = eval_data.get("milestone_mapping", {})
    task_label = row["task_label"]
    milestone_rows = []
    for index, meaning in enumerate(MILESTONE_MEANINGS[task_label]):
        mapping = milestone_mapping.get(str(index))
        milestone_rows.append({"milestone_index": index, "source_based_requirement": meaning,
                               "mapped_snapshot_index": mapping[0] if isinstance(mapping, list) and mapping else None,
                               "score": mapping[1] if isinstance(mapping, list) and len(mapping) > 1 else None})
    cleanup = report.get("cleanup", {})
    stop = result.get("stop", {})
    infra_complete = (report.get("exit_code") == 0 and report.get("worker_exit_code") == 0 and
                      result.get("failure") is None and cleanup.get("wait_reaped") is True and
                      cleanup.get("original_process_gone") is True and
                      cleanup.get("sampler_stopped") is True and
                      report.get("archive_verification", {}).get("valid") is True)
    # Keep the report compact and never copy conversation text or tool arguments/results.
    return {"task_label": task_label, "task": row["task"], "round": row["round"],
            "position_in_round": row["position_in_round"], "sequence_index": row["sequence_index"],
            "run_id": row["run_id"], "report_path": row["report_path"], "raw_path": row["raw_path"],
            "identity_sha256": IDENTITY,
            "run_status": {"exit_code": report.get("exit_code"), "worker_exit_code": report.get("worker_exit_code"),
                           "worker_failure_present": result.get("failure") is not None,
                           "infra_complete_by_saved_exit_cleanup_archive_evidence": infra_complete,
                           "within_total_budget": report.get("within_total_budget"),
                           "deadline_timeout": report.get("deadline_timeout"),
                           "cleanup_wait_reaped": cleanup.get("wait_reaped"),
                           "cleanup_original_process_gone": cleanup.get("original_process_gone"),
                           "sampler_stopped": cleanup.get("sampler_stopped"),
                           "archive_valid": report.get("archive_verification", {}).get("valid")},
            "behavior": behavior,
            "tool_path_saved_start_order": tool_sequence,
            "tool_path_order_caveat": "saved event monotonic order only; not proof of concurrent execution order",
            "time": {"attempt_wall_s": report.get("wall_s"),
                     "worker_window_s": phases["worker_boundary_wall_s"],
                     "sampler_window_s": resources["sample_window_s"],
                     "sampler_point_count": resources["sample_count"],
                     "phases": phases["phases"],
                     "phase_boundary_cpu_conservation_residual_ticks": phases["phase_cpu_conservation_residual_ticks"],
                     "phase_boundary_wall_conservation_residual_s": phases["phase_wall_conservation_residual_s"],
                     "request_batch_partition": partition},
            "resources": resources,
            "environment": {"sc_clk_tck": environment.get("sc_clk_tck"),
                            "sc_page_size": environment.get("sc_page_size"),
                            "online_cpu_count": environment.get("online_cpu_count"),
                            "worker_affinity_cpu_count": environment.get("worker_affinity_cpu_count"),
                            "cgroup_v2_path": environment.get("cgroup_v2_path"),
                            "cgroup_limits": environment.get("cgroup_limits")},
            "evaluation": {"status": report.get("evaluation_status"),
                           "similarity": eval_data.get("similarity"),
                           "milestone_similarity": eval_data.get("milestone_similarity"),
                           "minefield_similarity": eval_data.get("minefield_similarity"),
                           "milestone_mapping": eval_data.get("milestone_mapping"),
                           "minefield_mapping": eval_data.get("minefield_mapping"),
                           "turn_count": eval_data.get("turn_count"),
                           "source_interpretation": milestone_rows,
                           "success_threshold": "not defined or applied"},
            "saved_boundary_quality": {"duplicate_phase_names": duplicate_phases,
                                       "phase_names": sorted(boundaries),
                                       "sample_pid_matches_environment": resources["pid_values"] == [environment.get("pid")],
                                       "sample_starttime_matches_environment": resources["starttime_ticks_values"] ==
                                       [environment.get("starttime_ticks")]}}


def _task_summary(label: str, task: str, rows: list[dict]) -> dict:
    keys = {
        "agent_logical_requests": lambda row: row["behavior"]["logical_requests"]["agent"],
        "user_logical_requests": lambda row: row["behavior"]["logical_requests"]["user"],
        "agent_tool_calls": lambda row: row["behavior"]["tool_calls"]["agent_tool_call_count"],
        "user_end_conversation_calls": lambda row: row["behavior"]["tool_calls"]["user_end_conversation_count"],
        "tool_batches": lambda row: row["behavior"]["tool_batches"]["count"],
        "batch_ordering_executions": lambda row: row["behavior"]["tool_batches"]["executed_orderings"],
        "wrapper_execution_count_including_setup": lambda row: row["behavior"]["tool_batches"]["wrapper_execution_count_from_result"],
        "attempt_wall_s": lambda row: row["time"]["attempt_wall_s"],
        "worker_window_s": lambda row: row["time"]["worker_window_s"],
        "sample_window_s": lambda row: row["time"]["sampler_window_s"],
        "sample_cpu_s": lambda row: row["resources"]["process_cpu_s"],
        "sample_cpu_ticks": lambda row: row["resources"]["cpu_ticks_delta"],
        "rss_sampled_peak_bytes": lambda row: row["resources"]["rss_sampled_peak_bytes"],
        "sample_points": lambda row: row["resources"]["sample_count"],
        "thread_count_max": lambda row: row["resources"]["thread_count_max"],
        "tool_ok_returns": lambda row: row["behavior"]["tool_calls"]["ok_return_count"],
        "tool_not_ok_returns": lambda row: row["behavior"]["tool_calls"]["not_ok_return_count"],
        "proc_rchar_delta_bytes": lambda row: row["resources"]["sampled_proc_io_delta_bytes"].get("rchar"),
        "proc_wchar_delta_bytes": lambda row: row["resources"]["sampled_proc_io_delta_bytes"].get("wchar"),
        "proc_read_bytes_delta": lambda row: row["resources"]["sampled_proc_io_delta_bytes"].get("read_bytes"),
        "proc_write_bytes_delta": lambda row: row["resources"]["sampled_proc_io_delta_bytes"].get("write_bytes"),
        "evaluation_similarity": lambda row: row["evaluation"]["similarity"],
        "evaluation_turn_count": lambda row: row["evaluation"]["turn_count"],
    }
    for phase in ("setup", "imports", "play", "play_to_evaluation_gap", "evaluator", "worker_tail"):
        keys[f"{phase}_wall_s"] = lambda row, p=phase: row["time"]["phases"][p].get("wall_s")
        keys[f"{phase}_process_cpu_s"] = lambda row, p=phase: row["time"]["phases"][p].get("process_cpu_s")
        keys[f"{phase}_cpu_ticks"] = lambda row, p=phase: row["time"]["phases"][p].get("cpu_ticks")
    metrics = {name: _stats([extract(row) for row in rows]) for name, extract in keys.items()}
    paths: dict[str, list[str]] = {}
    for row in rows:
        signature = json.dumps(row["tool_path_saved_start_order"], ensure_ascii=False, separators=(",", ":"))
        paths.setdefault(signature, []).append(row["run_id"])
    transition_counts: dict[str, int] = {}
    for row in rows:
        sequence = row["tool_path_saved_start_order"]
        for left, right in zip(sequence, sequence[1:]):
            if not isinstance(left, str) or not left or not isinstance(right, str) or not right:
                continue
            key = f"{left} → {right}"
            transition_counts[key] = transition_counts.get(key, 0) + 1
    return {"task_label": label, "task": task, "n_runs": len(rows), "metrics": metrics,
            "saved_agent_tool_paths": [{"sequence": json.loads(sequence), "count": len(ids), "run_ids": ids}
                                        for sequence, ids in sorted(paths.items())],
            "saved_order_tool_transitions": transition_counts,
            "tool_order_note": "descriptive saved-start order only; not concurrency proof",
            "run_ids": [row["run_id"] for row in rows]}


def analyze(root: Path = ROOT) -> dict:
    verified = verify_inputs(root)
    per_run = [_run_analysis(root, row) for row in verified["runs"]]
    task_summaries = {label: _task_summary(label, task,
                                          [row for row in per_run if row["task_label"] == label])
                      for label, task in TASKS.items()}
    total_requests = {role: sum(row["behavior"]["logical_requests"][role] for row in per_run)
                      for role in ("agent", "user")}
    total_calls = sum(row["behavior"]["tool_calls"]["logical_call_spans"] for row in per_run)
    total_agent_tools = sum(row["behavior"]["tool_calls"]["agent_tool_call_count"] for row in per_run)
    total_user_end = sum(row["behavior"]["tool_calls"]["user_end_conversation_count"] for row in per_run)
    total_setup = sum(row["behavior"]["tool_calls"]["system_setup_exec_count"] for row in per_run)
    total_batches = sum(row["behavior"]["tool_batches"]["count"] for row in per_run)
    total_batch_orderings = sum(row["behavior"]["tool_batches"]["executed_orderings"] for row in per_run)
    wrapper_points = [row["behavior"]["tool_batches"]["wrapper_execution_count_from_result"]
                      for row in per_run]
    total_wrapper_execs = (sum(wrapper_points) if all(
        isinstance(value, int) and not isinstance(value, bool) for value in wrapper_points) else None)
    total_samples = sum(row["resources"]["sample_count"] for row in per_run)
    total_project_attempts = sum(row["behavior"]["logical_requests"]["project_layer_attempt_total"]
                                 for row in per_run)
    errors = [error for row in per_run for error in row["behavior"]["errors"]]
    start = verified["started"].get("started_at_utc")
    completed = verified["completed"].get("completed_at_utc")
    from datetime import datetime
    batch_wall_s = (datetime.fromisoformat(completed) - datetime.fromisoformat(start)).total_seconds()
    all_integrity_checks = all(
        row["behavior"]["raw_call_event_count_matches_result"] and
        row["behavior"]["raw_batch_count_matches_result"] and
        row["behavior"]["request_count_matches_result"] and
        row["behavior"]["tool_batches"]["wrapper_execution_crosscheck"] and
        row["behavior"]["tool_calls"]["all_returns_saved"] and
        row["behavior"]["termination"]["run_root_open_close"] is not None and
        row["behavior"]["termination"]["run_root_open_close"]["closed"] is True and
        row["behavior"]["termination"]["requests_after_last_user_end_conversation"] == 0 and
        row["run_status"]["cleanup_wait_reaped"] and row["run_status"]["cleanup_original_process_gone"] and
        row["run_status"]["sampler_stopped"] and row["run_status"]["archive_valid"] and
        row["run_status"]["infra_complete_by_saved_exit_cleanup_archive_evidence"]
        for row in per_run)
    summary = {
        "schema": "toolsandbox-assistant-repeat-01-review-v1",
        "scope": {"collection": COLLECTION, "identity_sha256": IDENTITY,
                  "run_count": len(per_run), "tasks": TASKS,
                  "schedule": [[TASKS[label] for label in round_labels] for round_labels in SCHEDULE],
                  "sampling_design": "fixed sequential 3-round rotation; not randomized",
                  "pilot_01_02_included": False},
        "integrity": {"batch_and_raw_manifests_verified": True,
                      "identity_plan_frozen_approval_markers_linked": True,
                      "nine_run_schedule_verified": True,
                      "raw_file_sets_exact": True,
                      "batch_wall_s": batch_wall_s,
                      "batch_executed": verified["completed"].get("executed"),
                      "batch_not_executed": verified["completed"].get("not_executed"),
                      "batch_stop_reason": verified["completed"].get("stop_reason"),
                      "all_run_counter_cleanup_archive_checks_pass": all_integrity_checks,
                      "current_execution_code_matches_frozen_identity": verified["current_code_matches_frozen"],
                      "current_code_checks": verified["current_code_checks"],
                      "current_code_alignment_note": "historical archive validity and present worktree code alignment are separate checks"},
        "behavior": {"logical_requests": {"agent": total_requests["agent"], "user": total_requests["user"],
                                           "total": total_requests["agent"] + total_requests["user"]},
                     "project_layer_attempts": total_project_attempts,
                     "actual_http_transmissions": "unknown; no transport-level hook",
                     "response_models": sorted({model for row in per_run for model in
                                                 row["behavior"]["logical_requests"]["response_models"]}),
                     "agent_tool_calls": total_agent_tools, "user_end_conversation_calls": total_user_end,
                     "logical_tool_call_spans_including_user_end": total_calls,
                     "system_setup_exec": total_setup,
                     "tool_batches": total_batches,
                     "batch_ordering_executions_excluding_system_setup": total_batch_orderings,
                     "wrapper_execution_count_including_system_setup": total_wrapper_execs,
                     "tool_call_error_count": len(errors), "tool_errors": errors,
                     "all_finish_or_user_stop": all(row["behavior"]["termination"]["conversation_stop_reason"] ==
                                                     "user_end_conversation" for row in per_run),
                     "tool_batch_call_linkage": "call IDs are recorded on batch spans but not individual call spans; no positional pairing"},
        "resources": {"sample_count": total_samples,
                      "process_scope": "shared worker; setup, Agent/User, tools, evaluator, imports and recording are not isolated",
                      "cpu_seconds": "converted only using each run's saved environment.sc_clk_tck",
                      "rss": "sampled worker RSS, not kernel peak; not summed with other scopes",
                      "io": "process /proc counters; not complete filesystem I/O",
                      "per_run_quality": {row["run_id"]: row["resources"] for row in per_run}},
        "evaluation": {"completed_runs": sum(row["evaluation"]["status"] == "completed" for row in per_run),
                       "by_task": {label: {"raw_similarity_points": task_summaries[label]["metrics"]["evaluation_similarity"],
                                           "milestones_by_run": [row["evaluation"]["source_interpretation"]
                                                                  for row in per_run if row["task_label"] == label]}
                                   for label in TASKS},
                       "success_threshold": "not defined or applied; no H-EPM threshold used"},
        "infrastructure": {"runs_with_saved_clean_exit_cleanup_and_archive": sum(
                                row["run_status"]["infra_complete_by_saved_exit_cleanup_archive_evidence"]
                                for row in per_run),
                            "tool_errors_are_separate_from_infrastructure_failures": True},
        "per_task": task_summaries,
        "per_run": per_run,
        "limitations": [
            "three fixed tasks and three repeats per task do not represent the Assistant category",
            "task milestone structures differ; similarity is not compared across tasks",
            "logical/project attempts are not actual HTTP transport counts; billing is unknown",
            "worker CPU/RSS and batch windows are shared and do not establish single-tool resource use",
            "saved event start order does not prove concurrency execution order",
            "no function-level profiler evidence; static source only identifies candidate mechanisms",
            "a tool error followed by recovery does not prove the error had no effect",
        ],
    }
    return {"summary": summary, "per_run": per_run, "verification": verified}


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _stats_text(stats: dict, unit: str = "") -> str:
    return (f"n={stats['n']}; median {_fmt(stats['median'])}{unit}; "
            f"Q1–Q3 {_fmt(stats['q1'])}–{_fmt(stats['q3'])}{unit}; "
            f"IQR {_fmt(stats['iqr'])}{unit}; raw={stats['raw_points']}")


def render_markdown(summary: dict) -> str:
    per_run = summary["per_run"]
    lines = [
        "# ToolSandbox Assistant Repeat-01：离线行为—资源特征化",
        "",
        f"范围：3个固定官方任务，各3次顺序重复；完整identity `{IDENTITY}`。这是描述性小样本，不代表Assistant类别总体。PILOT-01/02未计入。",
        "",
        "## 验收与覆盖",
        "",
        f"批次完成 {summary['integrity']['batch_executed']}/9，未执行 {summary['integrity']['batch_not_executed']}；批wall {_fmt(summary['integrity']['batch_wall_s'])} 秒。身份、计划/冻结/批准、批与raw manifest、显式顺序和实际文件集合均已核验。每run结果计数、调用闭合、清理、sampler停止及归档检查：`{summary['integrity']['all_run_counter_cleanup_archive_checks_pass']}`。",
        f"当前工作区执行代码与历史冻结代码逐文件匹配：`{summary['integrity']['current_execution_code_matches_frozen_identity']}`。该项与历史归档完整性分开记录，不改写历史身份。",
        "",
        "## 每次运行",
        "",
        "|任务/round|run_id|Agent/User请求|Agent工具/User结束|batch / batch排列执行|wrapper执行（含setup）|similarity|attempt wall|采样窗|采样CPU-s|RSS峰值 MiB|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in per_run:
        behavior = row["behavior"]
        resources = row["resources"]
        calls = behavior["tool_calls"]
        batches = behavior["tool_batches"]
        lines.append("|{} r{}|`{}`|{}/{}|{}/{}|{} / {}|{}|{}|{}s|{}s|{}|{}|".format(
            row["task_label"], row["round"], row["run_id"],
            behavior["logical_requests"]["agent"], behavior["logical_requests"]["user"],
            calls["agent_tool_call_count"], calls["user_end_conversation_count"],
            batches["count"], batches["executed_orderings"], batches["wrapper_execution_count_from_result"],
            _fmt(row["evaluation"]["similarity"], 6), _fmt(row["time"]["attempt_wall_s"]),
            _fmt(row["time"]["sampler_window_s"]), _fmt(resources["process_cpu_s"], 2),
            _fmt((resources["rss_sampled_peak_bytes"] / 1048576)
                 if resources["rss_sampled_peak_bytes"] is not None else None, 1)))
    lines += [
        "",
        "说明：wrapper执行总数包含system setup；batch排列执行不含setup。批/工具事件没有可用的一一关联ID，不按数量或位置配对。采样CPU-s是共享多线程worker计数差，不能归到单个工具；RSS是采样峰值，无内核memory peak。",
        "",
        "## 按任务的重复统计",
        "",
        "分位数为 `(n−1)×p` 线性插值。每任务n=3；没有跨任务汇总或显著性检验。",
        "",
    ]
    for label, task in TASKS.items():
        block = summary["per_task"][label]
        lines += [f"### {label} — `{task}`", "",
                  f"观察到的Agent工具路径（保存的调用开始顺序，仅描述记录顺序）：{block['saved_agent_tool_paths']}",
                  "",
                  "|指标|n / median / IQR / 原始点|",
                  "|---|---|"]
        for name in ("agent_logical_requests", "user_logical_requests", "agent_tool_calls",
                     "tool_ok_returns", "tool_not_ok_returns", "tool_batches", "batch_ordering_executions",
                     "proc_rchar_delta_bytes", "proc_wchar_delta_bytes", "proc_read_bytes_delta",
                     "proc_write_bytes_delta", "thread_count_max", "attempt_wall_s", "worker_window_s",
                     "setup_wall_s", "imports_wall_s", "play_wall_s", "evaluator_wall_s",
                     "setup_process_cpu_s", "play_process_cpu_s", "evaluator_process_cpu_s",
                     "sample_window_s", "sample_cpu_s", "rss_sampled_peak_bytes", "evaluation_similarity"):
            stats = block["metrics"][name]
            unit = ("s" if name.endswith("_s") else
                    " CPU-s" if "process_cpu" in name or name == "sample_cpu_s" else
                    " bytes" if "bytes" in name or "proc_read" in name or "proc_write" in name else "")
            lines.append(f"|{name}|{_stats_text(stats, unit)}|")
        lines.append("")
    lines += [
        "## Agent/User与工具执行口径",
        "",
        f"合计 {summary['behavior']['logical_requests']['total']} 个逻辑请求（Agent {summary['behavior']['logical_requests']['agent']}、User {summary['behavior']['logical_requests']['user']}）；每个请求对应项目层尝试总数 {summary['behavior']['project_layer_attempts']}。实际HTTP传输数因无transport级hook而unknown。响应model为 `{', '.join(summary['behavior']['response_models'])}`，请求model别名与响应model分别记录。",
        f"保存到 {summary['behavior']['agent_tool_calls']} 个Agent工具调用、{summary['behavior']['user_end_conversation_calls']} 个User `end_conversation`、{summary['behavior']['tool_batches']} 个执行batch、{summary['behavior']['batch_ordering_executions_excluding_system_setup']} 次batch内部排列执行；另有 {summary['behavior']['system_setup_exec']} 次system setup。wrapper执行计数 {summary['behavior']['wrapper_execution_count_including_system_setup']} 包含这些setup执行，不应再与setup重复相加。",
        "工具路径按任务分列；多工具请求的保存时间顺序不证明实际并发次序。一次batch可对应多个排列执行；batch中的native call IDs与逻辑tool-call event之间未保存直接映射。末次返回和User结束工具均已记录；9/9 conversation stop reason为`user_end_conversation`，结束后没有新增请求。",
        "",
        f"## {len(summary['behavior']['tool_errors'])}次工具错误与后续路径",
        "",
    ]
    for error in summary["behavior"]["tool_errors"]:
        lines.append(f"- `{error['run_id']}` / `{error['event_id']}`：`{error['tool_name']}` 返回 `{error['error_class']}`（request `{error['request_id']}`）。下一同角色请求 `{error['next_same_role_request_id']}` 的工具调用为 `{error['next_request_tool_calls']}`。参数正文未复制。")
    lines += [
        "",
        "A/r1：保存返回只保留`ConnectionError`类别；官方`send_message_with_phone_number`在cellular未启用时会抛该异常，冻结任务初态为cellular off。Agent随后调用`set_cellular_service_status`，之后再次调用发送工具并获得ok返回。它是后续新的工具调用，不是transport重试；最终outgoing-message milestone得分为1，但确认消息milestone为部分分。不能据此断言前次错误没有影响。",
        "C/r2：`search_messages`返回`ValueError`类别；参数摘要与空JSON对象的SHA-256一致，冻结官方实现说明未提供任一搜索条件会抛ValueError。该调用发生在包含`search_contacts`和`search_messages`的多工具请求中，batch计划2种顺序但在1次执行后因失败停止。后续请求中保存了两次成功的`search_messages`调用，随后继续联系人搜索、修改与结束。任务mapping中的search_messages milestone得分为0；其与错误、后续恢复以及最终评估之间不能做单一因果归因。",
        "",
        "错误类别由保存的sanitized终态和固定源码支持；没有读取完整参数、返回正文或模型消息正文。工具错误不是模型协议错误、harness/infra失败的同义词。",
        "",
        "## 任务评估与任务内差异",
        "",
        "所有评估均完成，但similarity不是统一成功标签；任务milestone数量和语义不同，不能跨任务排名。官方固定任务语义来自冻结源码中的milestone定义：A检查cellular状态、联系人搜索trace、目标消息状态及确认文本；B检查当前时间trace及明天下午5点的提醒内容/时间；C检查时间、联系人/消息搜索trace、基于最近消息的联系人更新及确认文本。逐run实际mapping、snapshot index、score见summary.json/per_run.jsonl。",
        "",
        "Task C的三点显示波动主要落在 evaluator 阶段：按任务内统计，evaluator wall IQR 大于 setup/play wall IQR；evaluator边界CPU IQR也最大。r2/C同时有更多Agent请求、逻辑工具、batch排列执行，并有一次search_messages错误；这些是共现差异，不能证明导致评估wall/CPU增加。冻结源码显示评估器用带剪枝/记忆的DFS匹配milestones与snapshots；执行环境也会对多工具调用做排列和深拷贝。这仅是静态候选机制，没有profile证明任何函数是热点或解释了大部分CPU。",
        "",
        "## 时间与资源边界",
        "",
        "attempt wall、worker边界窗口、周期采样窗口分别报告。setup定义为`worker_start→play_begin`，包含imports及场景/client初始化；imports另列为setup子窗口。play/evaluator/间隙/tail使用同宿主monotonic阶段边界。请求时长是客户端逻辑调用边界，不是思考时间；tool_batch为共享执行环境窗口，不复制成单工具耗时。",
        "",
        "phase CPU使用各run `environment.json.sc_clk_tck` 从边界user/system/total ticks换算；采样CPU差使用相邻有效样本且使用同一run保存的CLK_TCK。阶段边界与周期样本窗口的端点不同，不强求两者相等。采样间隔若跨阶段或请求/batch事件边界，标为mixed，不插值、不按比例分摊。平均CPU秒可大于wall，因为是多线程共享worker的累计进程CPU。",
        "",
        "RSS只报告采样worker RSS峰值；线程数是观测线程数量，不是核心数/并行度。I/O分`rchar/wchar`与`read_bytes/write_bytes`，来源为worker进程`/proc`计数器，不代表完整文件系统流量。环境记录的在线CPU/affinity数量不等于进程配额；cgroup字段为unknown。usage不是账单，实际费用unknown。",
        "",
        "## 可支持与不可支持",
        "",
        "这批新增了三个固定ToolSandbox任务的真实Agent/User/工具时序、阶段边界、共享worker资源和官方evaluation对应证据，可描述每个任务三次运行内的路径及观测差异。仍不能证明工具独占CPU、函数热点、错误对成绩/时间的因果、实际HTTP传输次数、账单、Assistant类别规律或跨任务能力排名。",
        "",
        "建议的唯一后续方向：先评估是否需要扩展更多固定Assistant任务来提高任务覆盖，而非对这三条路径追加重复；该建议不构成执行授权。",
        "",
        f"来源批manifest SHA-256：`{summary['integrity']['batch_manifest_sha256']}`；批摘要SHA-256：`{summary['integrity']['batch_summary_sha256']}`。本报告manifest另列实际输入与输出哈希，不自哈希。",
        "",
    ]
    return "\n".join(lines)


def run(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or (root / OUTPUT_REL)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis output: {output_dir}")
    analyzed = analyze(root)
    verified = analyzed["verification"]
    summary = analyzed["summary"]
    summary["integrity"]["batch_manifest_sha256"] = file_record(
        verified["report_dir"] / "manifest.json", root)["sha256"]
    summary["integrity"]["batch_summary_sha256"] = file_record(
        verified["report_dir"] / "batch-summary.json", root)["sha256"]
    output_dir.mkdir(parents=True)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    per_run_path = output_dir / "per_run.jsonl"
    per_run_path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
                                   for row in analyzed["per_run"]), encoding="utf-8")
    markdown_path = output_dir / "summary.md"
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    outputs = [file_record(path, root) for path in (summary_path, per_run_path, markdown_path)]
    code_records = [file_record(root / path, root) for path in ANALYSIS_CODE]
    manifest = {"schema": "toolsandbox-assistant-repeat-01-review-manifest-v1",
                "identity_sha256": IDENTITY,
                "inputs": verified["inputs"],
                "analysis_code": code_records,
                "outputs": outputs,
                "manifest_self_hash": False}
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    # Read back all generated outputs and the manifest's referenced entries.
    for entry in outputs:
        _record_matches(root, entry, "analysis output readback")
    loaded_manifest = read_json(manifest_path)
    require(loaded_manifest == manifest, "analysis manifest readback mismatch")
    for entry in loaded_manifest["analysis_code"] + loaded_manifest["inputs"] + loaded_manifest["outputs"]:
        _record_matches(root, entry, "analysis manifest readback")
    return {"summary": summary, "per_run": analyzed["per_run"], "manifest": manifest}


def main() -> int:
    result = run()
    print(json.dumps({"output": OUTPUT_REL.as_posix(), "run_count": len(result["per_run"]),
                      "manifest_inputs": len(result["manifest"]["inputs"]),
                      "manifest_outputs": len(result["manifest"]["outputs"]),
                      "identity_sha256": IDENTITY}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
