#!/usr/bin/env python3
"""Offline characterization of the nine explicitly registered Office repeat runs."""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docops_word_resource_analysis as shared

COLLECTION = "DOCOPS-OFFICE-REPEAT-01"
IDENTITY = "25da9eeab2600401630ca54aa11f739dbfe08be3a57d6d4808fbc8956d65712a"
REPORT = "reports/resource/DOCOPS-OFFICE-REPEAT-01"
RAW = "data/raw/generated/DOCOPS-OFFICE-REPEAT-01"
ENV = "env/docops-office-repeat-01"
OUT = "reports/analysis/DOCOPS-OFFICE-REPEAT-01-characterization-v1"
TASKS = (
    "atomic__excel_001_budget_bucket_totals_seed",
    "atomic__ppt_008_bullet_editing_seed",
    "atomic__pdf_004_audit_pages_reorder_seed",
)
SHORT = {TASKS[0]: "Excel", TASKS[1]: "PPT", TASKS[2]: "PDF"}
SCHEDULE = (TASKS, (TASKS[1], TASKS[2], TASKS[0]), (TASKS[2], TASKS[0], TASKS[1]))
RUN_RE = re.compile(r"llm_call_(\d+)\.json$")
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
              "cache_read_input_tokens", "cache_creation_input_tokens")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(root: Path, path: Path) -> dict[str, Any]:
    return {"path": path.resolve().relative_to(root.resolve()).as_posix(),
            "bytes": path.stat().st_size, "sha256": sha256(path)}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _verify_record(root: Path, record: dict[str, Any], seen: dict[str, dict[str, Any]]) -> Path:
    rel = Path(record["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe manifest path: {record['path']}")
    path = root / rel
    if not path.is_file():
        raise ValueError(f"manifest file missing: {record['path']}")
    actual = file_record(root, path)
    if actual["bytes"] != record.get("bytes") or actual["sha256"] != record.get("sha256"):
        raise ValueError(f"manifest mismatch: {record['path']}")
    seen[actual["path"]] = actual
    return path


def _verify_batch(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[Path], list[Path], list[dict[str, Any]]]:
    report = root / REPORT
    batch_summary_path = report / "batch-summary.json"
    batch_manifest_path = report / "batch-manifest.json"
    batch_summary = load_json(batch_summary_path)
    batch_manifest = load_json(batch_manifest_path)
    if batch_summary.get("collection") != COLLECTION or batch_summary.get("identity_sha256") != IDENTITY:
        raise ValueError("batch summary collection/identity mismatch")
    if batch_manifest.get("identity_sha256") != IDENTITY:
        raise ValueError("batch manifest identity mismatch")
    verified: dict[str, dict[str, Any]] = {}
    for record in batch_manifest.get("inputs", []):
        _verify_record(root, record, verified)
    for record in batch_manifest.get("outputs", []):
        _verify_record(root, record, verified)

    plan_path = root / ENV / "plan-identity.json"
    frozen_path = root / ENV / "frozen-identity.json"
    approval_path = report / "APPROVAL.json"
    plan, frozen, approval = load_json(plan_path), load_json(frozen_path), load_json(approval_path)
    plan_identity, frozen_identity = plan.get("identity"), frozen.get("identity")
    if not isinstance(plan_identity, dict) or plan_identity != frozen_identity:
        raise ValueError("full plan/frozen identity structures disagree")
    calculated = hashlib.sha256(json.dumps(plan_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    identity_layers = {
        "plan_digest_matches_structure": plan.get("identity_sha256") == calculated,
        "frozen_digest_matches_structure": frozen.get("identity_sha256") == calculated,
        "approval_digest_matches": approval.get("identity_sha256") == calculated,
        "batch_summary_digest_matches": batch_summary.get("identity_sha256") == calculated,
        "batch_manifest_digest_matches": batch_manifest.get("identity_sha256") == calculated,
        "approval_state": approval.get("user_approval"),
        "approval_collection": approval.get("collection"),
        "full_plan_frozen_structure_equal": plan_identity == frozen_identity,
    }
    if not all(identity_layers[k] for k in ("plan_digest_matches_structure", "frozen_digest_matches_structure",
                                             "approval_digest_matches", "batch_summary_digest_matches",
                                             "batch_manifest_digest_matches", "full_plan_frozen_structure_equal")):
        raise ValueError(f"identity chain mismatch: {identity_layers}")
    if approval.get("collection") != COLLECTION or approval.get("user_approval") != "approved":
        raise ValueError("batch approval not bound/approved")

    results = batch_summary.get("results")
    if not isinstance(results, list) or len(results) != 9:
        raise ValueError("batch summary does not contain exactly nine explicit run records")
    expected = [(round_no, task) for round_no, row in enumerate(SCHEDULE) for task in row]
    observed = [(row.get("round"), row.get("task_key")) for row in results]
    if observed != expected:
        raise ValueError(f"batch run order differs from registered 3x3 schedule: {observed}")
    run_ids = [row.get("run_id") for row in results]
    if len(set(run_ids)) != 9 or any(not isinstance(run_id, str) or not run_id for run_id in run_ids):
        raise ValueError("missing or duplicate run_id")
    refs = batch_manifest.get("raw_run_manifests", [])
    if len(refs) != 9 or {Path(r["path"]).parent.name for r in refs} != set(run_ids):
        raise ValueError("batch manifest raw manifest references do not match explicit run set")
    ref_by_run = {Path(item["path"]).parent.name: item for item in refs}
    raw_manifest_paths: list[Path] = []
    raw_run_dirs: list[Path] = []
    for row in results:
        run_id, task = row["run_id"], row["task_key"]
        run_dir = root / RAW / run_id
        manifest_path = run_dir / "manifest.json"
        ref = ref_by_run[run_id]
        actual_manifest = file_record(root, manifest_path)
        if actual_manifest["path"] != ref["path"] or actual_manifest["bytes"] != ref.get("bytes") or actual_manifest["sha256"] != ref.get("sha256"):
            raise ValueError(f"batch/raw manifest reference mismatch for {run_id}")
        verified[actual_manifest["path"]] = actual_manifest
        raw_manifest = load_json(manifest_path)
        if raw_manifest.get("run_id") != run_id or raw_manifest.get("task_key") != task or raw_manifest.get("round") != row["round"]:
            raise ValueError(f"raw manifest run/task/round mismatch for {run_id}")
        if raw_manifest.get("identity_sha256") != calculated or row.get("identity_sha256") != calculated:
            raise ValueError(f"run identity digest mismatch for {run_id}")
        # Raw-manifest inputs are relative to the matching DocOps task directory.
        task_root = root / "references/repos/DocOps/tasks" / task
        for item in raw_manifest.get("inputs", []):
            item_path = item.get("path", "")
            prefix = task + "/"
            if not item_path.startswith(prefix):
                raise ValueError(f"unexpected raw input path for {run_id}: {item_path}")
            source = task_root / item_path[len(prefix):]
            if not source.is_file() or sha256(source) != item.get("sha256"):
                raise ValueError(f"raw manifest input mismatch for {run_id}: {item_path}")
            verified[file_record(root, source)["path"]] = file_record(root, source)
        for item in raw_manifest.get("outputs", []):
            _verify_record(root, {**item, "path": f"{RAW}/{run_id}/{item['path']}"}, verified)
        raw_manifest_paths.append(manifest_path)
        raw_run_dirs.append(run_dir)
    for path in (batch_summary_path, batch_manifest_path, plan_path, frozen_path, approval_path):
        verified[file_record(root, path)["path"]] = file_record(root, path)
    return batch_summary, batch_manifest, raw_manifest_paths, raw_run_dirs, list(verified.values())


def _decode_action(log: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    diagnostic: dict[str, Any] = {"status": "unknown", "reason": None}
    try:
        response = json.loads(log.get("original_response") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, {**diagnostic, "status": "invalid", "reason": "saved_original_response_not_json"}
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None, {**diagnostic, "status": "invalid", "reason": "response_choices_missing_or_invalid",
                      "response_model": response.get("model") if isinstance(response, dict) else None}
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    result_base = {"response_model": response.get("model"), "finish_reason": choices[0].get("finish_reason"),
                   "content_type": type(content).__name__,
                   "content_chars": len(content) if isinstance(content, str) else None,
                   "content_sha256": hashlib.sha256(content.encode()).hexdigest() if isinstance(content, str) else None}
    if not isinstance(content, str):
        return None, {**diagnostic, **result_base, "status": "invalid", "reason": "message_content_missing_or_not_string"}
    parse_method = "strict_json"
    try:
        action = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoder = json.JSONDecoder()
        action = None
        for offset, char in enumerate(content):
            if char != "{":
                continue
            try:
                action, _ = decoder.raw_decode(content[offset:])
                parse_method = "first_embedded_json_object"
                break
            except json.JSONDecodeError:
                continue
        if action is None:
            return None, {**diagnostic, **result_base, "status": "invalid", "reason": "no_json_object_decoded",
                          "parse_method": "strict_and_embedded_object_failed"}
    if not isinstance(action, dict):
        return None, {**diagnostic, **result_base, "status": "invalid", "reason": "action_json_not_object"}
    if isinstance(action.get("parameter"), dict):
        action = action["parameter"]
    if isinstance(action.get("response"), dict):
        action = action["response"]
    if "arguments" not in action:
        action["arguments"] = {}
    action_type = action.get("action")
    if action_type not in {"call_tool", "finish"}:
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "unsupported_action_value",
                        "action_value_type": type(action_type).__name__, "parse_method": parse_method}
    if not isinstance(action.get("thought"), str):
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "required_thought_missing_or_invalid",
                        "parse_method": parse_method}
    if action.get("tool_name") is not None and not isinstance(action.get("tool_name"), str):
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "tool_name_invalid",
                        "parse_method": parse_method}
    if action.get("final_message") is not None and not isinstance(action.get("final_message"), str):
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "final_message_invalid",
                        "parse_method": parse_method}
    if action_type == "call_tool" and (not isinstance(action.get("tool_name"), str) or not isinstance(action.get("arguments"), dict)):
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "call_tool_fields_missing_or_invalid",
                        "parse_method": parse_method}
    if not isinstance(action.get("arguments"), dict):
        return action, {**diagnostic, **result_base, "status": "invalid_or_unknown", "reason": "arguments_invalid",
                        "parse_method": parse_method}
    return action, {**diagnostic, **result_base, "status": action_type, "reason": None, "parse_method": parse_method}


def _safe_args(action: dict[str, Any]) -> dict[str, Any]:
    args = action.get("arguments")
    if not isinstance(args, dict):
        return {"status": "missing_or_non_object", "field_names": []}
    safe: dict[str, Any] = {"field_names": sorted(str(k) for k in args)}
    for key in ("path", "src", "dest"):
        if isinstance(args.get(key), str):
            safe[key + "_basename"] = Path(args[key]).name
    for key in ("sheet_name", "cell", "slide_index", "table_index", "page_numbers", "order"):
        value = args.get(key)
        if isinstance(value, (str, int, float, bool)) and not isinstance(value, float) or isinstance(value, float) and math.isfinite(value):
            safe[key] = value
        elif isinstance(value, list):
            safe[key + "_count"] = len(value)
    for key in ("replacements", "cells", "bullets"):
        if isinstance(args.get(key), list):
            safe[key + "_count"] = len(args[key])
    return safe


def _activity(tool: str | None) -> str:
    if tool == "copy_file":
        return "file_copy"
    if tool in {"inspect_document", "xlsx_read_sheet", "ppt_list_slides", "pdf_extract_text"}:
        return "document_or_content_inspection"
    if tool == "xlsx_set_formula":
        return "spreadsheet_formula_edit"
    if tool in {"xlsx_write_cells", "xlsx_highlight_cells", "xlsx_delete_sheet", "xlsx_reorder_sheets"}:
        return "spreadsheet_other_edit"
    if tool in {"ppt_replace_text", "ppt_set_bullets", "ppt_reorder_slides", "ppt_delete_slides"}:
        return "presentation_edit"
    if tool in {"pdf_reorder_pages", "pdf_delete_pages"}:
        return "pdf_page_edit"
    if tool in {"word_inspect_format", "word_set_format"}:
        return "word_format_tool_not_applicable_to_this_task_set"
    return "unknown_or_other"


def _nested_numeric_usage(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"status": "missing_or_non_object", "fields": {}}
    fields: dict[str, Any] = {}
    def visit(obj: Any, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                name = f"{prefix}.{key}" if prefix else str(key)
                if "token" in str(key).lower() and isinstance(value, (int, float)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value)):
                    fields[name] = value
                elif isinstance(value, (dict, list)):
                    visit(value, name)
    visit(usage)
    return {"status": "present", "fields": fields, "source_field_names": sorted(usage)}


def _saved_invalid_marker_indices(run_dir: Path) -> list[int]:
    path = run_dir / "agent/document-tools-agent.txt"
    if not path.is_file():
        return []
    # The transcript can contain model reasoning; only extract the numbered marker.
    text = path.read_text(encoding="utf-8", errors="replace")
    return [int(match.group(1)) for match in re.finditer(r"(?m)^STEP (\d+) INVALID$", text)]


def _saved_step_indices(run_dir: Path) -> list[int]:
    path = run_dir / "agent/document-tools-agent.txt"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return [int(match.group(1)) for match in re.finditer(r"(?m)^STEP (\d+)(?: INVALID)?$", text)]


def _request_records(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    call_paths = sorted((run_dir / "agent").glob("llm_call_*.json"), key=lambda p: int(RUN_RE.fullmatch(p.name).group(1)))
    if [int(RUN_RE.fullmatch(p.name).group(1)) for p in call_paths] != list(range(1, len(call_paths) + 1)):
        raise ValueError(f"non-contiguous logical request logs in {run_dir.name}")
    requests: list[dict[str, Any]] = []
    for path in call_paths:
        log = load_json(path)
        action, diagnostic = _decode_action(log)
        tool = action.get("tool_name") if action and action.get("action") == "call_tool" else None
        response = {}
        try:
            response = json.loads(log.get("original_response") or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        choices = response.get("choices", []) if isinstance(response, dict) else []
        usage = response.get("usage") if isinstance(response, dict) else None
        request_model = (f"{log.get('custom_llm_provider')}/{log.get('model')}"
                         if log.get("custom_llm_provider") and log.get("model") else log.get("model"))
        requests.append({"logical_request_index": int(RUN_RE.fullmatch(path.name).group(1)),
                         "action": diagnostic["status"], "invalid_reason": diagnostic.get("reason"),
                         "tool_name": tool, "activity": _activity(tool) if tool else ("finish" if diagnostic["status"] == "finish" else "not_applicable"),
                         "safe_arguments": _safe_args(action) if action else None,
                         "_arguments_for_linkage": action.get("arguments") if action and action.get("action") == "call_tool" else None,
                         "request_model": request_model, "response_model": diagnostic.get("response_model"),
                         "response_finish_reason": diagnostic.get("finish_reason"),
                         "action_parse_method": diagnostic.get("parse_method"),
                         "action_parse_reason": diagnostic.get("reason"),
                         "response_content_evidence": {k: diagnostic.get(k) for k in ("content_type", "content_chars", "content_sha256")},
                         "usage": _nested_numeric_usage(usage)})

    # Saved conversation history records each returned tool result immediately after its
    # assistant call. Use that explicit adjacency and ordered payloads; no call/result ID
    # exists in this runtime, so unequal or incomplete sequences remain unlinked.
    history_messages = []
    if call_paths:
        history = load_json(call_paths[-1]).get("messages", [])
        history_messages = history if isinstance(history, list) else []
    history_calls: list[tuple[dict[str, Any], str | None]] = []
    for i, message in enumerate(history_messages):
        if not isinstance(message, dict) or message.get("role") != "assistant" or not isinstance(message.get("content"), str):
            continue
        wrapped = {"original_response": json.dumps({"choices": [{"message": {"content": message["content"]}}]})}
        payload, _ = _decode_action(wrapped)
        if not isinstance(payload, dict) or payload.get("action") != "call_tool":
            continue
        following = history_messages[i + 1] if i + 1 < len(history_messages) else {}
        result_text = following.get("content") if isinstance(following, dict) and following.get("role") == "user" else None
        history_calls.append((payload, result_text if isinstance(result_text, str) else None))
    parsed_calls = [r for r in requests if r["action"] == "call_tool"]
    linked = len(history_calls) == len(parsed_calls)
    if linked:
        for request, (payload, _) in zip(parsed_calls, history_calls):
            if (payload.get("action") != "call_tool" or payload.get("tool_name") != request["tool_name"]
                    or payload.get("arguments") != request.get("_arguments_for_linkage")):
                linked = False
                break
    if linked:
        for request, (_, result_text) in zip(parsed_calls, history_calls):
            request["argument_match_in_history"] = True
            if not isinstance(result_text, str) or not result_text.startswith(f"Tool result for {request['tool_name']}:\n"):
                request["tool_return"] = "missing_or_unlinked"
                continue
            raw = result_text.split("\nDecide the next action.", 1)[0]
            prefix = f"Tool result for {request['tool_name']}:\n"
            try:
                result = json.loads(raw[len(prefix):])
            except (TypeError, ValueError, json.JSONDecodeError):
                request["tool_return"] = "saved_unparsed"
                continue
            if isinstance(result, dict) and result.get("ok") is True:
                request["tool_return"] = "saved_ok_true"
            elif isinstance(result, dict) and result.get("ok") is False:
                request["tool_return"] = "saved_ok_false"
            else:
                request["tool_return"] = "saved_status_unknown"
    if not linked:
        for request in parsed_calls:
            request["tool_return"] = "unknown_history_not_one_to_one"
            request.pop("argument_match_in_history", None)
    for request in parsed_calls:
        request.setdefault("tool_return", "not_persisted_or_unlinked")
    for request in requests:
        request.pop("_arguments_for_linkage", None)
    invalid_markers = _saved_invalid_marker_indices(run_dir)
    transcript_steps = _saved_step_indices(run_dir)
    invalid_request_indices = [r["logical_request_index"] for r in requests if r["action"] in {"invalid", "invalid_or_unknown"}]
    return requests, {"logical_request_count": len(requests),
                      "action_counts": dict(Counter(r["action"] for r in requests)),
                      "tool_call_count": len(parsed_calls),
                      "tool_name_counts": dict(Counter(r["tool_name"] for r in parsed_calls)),
                      "activity_counts": dict(Counter(r["activity"] for r in parsed_calls)),
                      "return_status_counts": dict(Counter(r["tool_return"] for r in parsed_calls)),
                      "request_model_counts": dict(Counter(r["request_model"] for r in requests if r["request_model"])),
                      "response_model_counts": dict(Counter(r["response_model"] for r in requests if r["response_model"])),
                      "history_call_result_linkage": "ordered adjacent saved-message structure; no explicit call IDs",
                      "history_actions_count_matches": linked,
                      "transcript_invalid_step_indices": invalid_markers,
                      "transcript_step_indices": transcript_steps,
                      "invalid_response_transcript_crosscheck": invalid_request_indices == invalid_markers,
                      "transcript_step_count_matches_requests": transcript_steps == list(range(1, len(requests) + 1)),
                      "transcript_accepted_step_count": len(transcript_steps) - len(invalid_markers)}


def _event_phase(events: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = {"harbor_start": ("harbor_start_begin", "harbor_start_done"),
             "agent_setup": ("agent_setup_begin", "agent_setup_done"),
             "agent": ("agent_begin", "agent_end"), "verifier": ("verifier_begin", "verifier_end"),
             "harbor_stop": ("harbor_stop_begin", "harbor_stop_done"),
             "archive": ("archive_begin", "archive_done")}
    times: dict[str, list[int]] = {}
    for event in events:
        timestamp = event.get("t_monotonic_ns")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool):
            times.setdefault(event.get("phase"), []).append(timestamp)
    result = {}
    for name, (begin, end) in pairs.items():
        starts, ends = times.get(begin, []), times.get(end, [])
        start, finish = (starts[0], ends[-1]) if starts and ends else (None, None)
        duration = (finish - start) / 1e9 if start is not None and finish is not None and finish >= start else None
        item = {"start_monotonic_ns": start, "end_monotonic_ns": finish,
                "status": "observed_monotonic_event_interval" if duration is not None else "unavailable"}
        item["event_span_s" if name == "archive" else "wall_s"] = duration
        if name == "archive":
            item["interpretation"] = "recorded archive_begin/archive_done marker span; not asserted to be complete archive duration"
        result[name] = item
    return result


def _resource(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = shared._resource_metrics(summary)
    samples = summary.get("samples", [])
    times = [s.get("t_monotonic_ns") for s in samples]
    if any(not isinstance(t, int) or isinstance(t, bool) for t in times) or any(b < a for a, b in zip(times, times[1:])):
        metrics["container_cpu_core_s"] = None
        metrics["cpu_status"] = "sample_clock_missing_or_nonmonotonic"
        return metrics
    for sample in samples:
        c = sample.get("container", {})
        if c.get("t_monotonic_ns") != sample.get("t_monotonic_ns"):
            metrics["container_cpu_core_s"] = None
            metrics["cpu_status"] = "container_sample_clock_mismatch"
            return metrics
    io_statuses = [sample.get("container", {}).get("read_status", {}).get("io", "missing") for sample in samples]
    io_reads = [sample.get("container", {}).get("io_read_bytes") for sample in samples]
    io_writes = [sample.get("container", {}).get("io_write_bytes") for sample in samples]
    io_valid_statuses = all(isinstance(s, str) and (s.startswith("ok_summed_devices:") or s.startswith("ok_no_records_real_zero:")) for s in io_statuses)
    io_numeric = all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in io_reads + io_writes)
    io_monotonic = (all(b >= a for a, b in zip(io_reads, io_reads[1:]))
                    and all(b >= a for a, b in zip(io_writes, io_writes[1:]))) if io_numeric else False
    if not samples:
        io_status = "no_samples"
        read_delta = write_delta = None
    elif not io_valid_statuses or not io_numeric:
        io_status = "missing_or_unavailable_counter"
        read_delta = write_delta = None
    elif not io_monotonic:
        io_status = "counter_decreased_or_reset"
        read_delta = write_delta = None
    else:
        io_status = "valid_observed_blkio_service_counter_delta"
        read_delta, write_delta = io_reads[-1] - io_reads[0], io_writes[-1] - io_writes[0]
    metrics["io_observed_blkio"] = {"status": io_status, "read_service_bytes_delta": read_delta,
                                    "write_service_bytes_delta": write_delta,
                                    "read_status_counts": dict(Counter(io_statuses)),
                                    "scope_note": "cgroup blkio service-byte counters selected by collector; not all file/document I/O"}
    # Existing pure helper validates every cumulative CPU read and counter monotonicity.
    # Stage deltas are emitted only for wholly contained sample intervals.
    return metrics


def _run(root: Path, row: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    run_id, task, round_no = row["run_id"], row["task_key"], row["round"]
    run_dir = root / RAW / run_id
    raw_manifest = load_json(manifest_path)
    summary = load_json(run_dir / "summary.json")
    if summary.get("run_id") != run_id or summary.get("task_key") != task or summary.get("round") != round_no:
        raise ValueError(f"raw summary identity/schedule mismatch: {run_id}")
    if summary.get("identity_sha256") != IDENTITY or summary.get("within_total_budget") is not True:
        raise ValueError(f"run identity/budget status invalid: {run_id}")
    outcome = summary.get("outcome", {})
    phases = outcome.get("phases", {})
    if row.get("status") != "executed" or row.get("returncode") != 0 or row.get("archive_verified") is not True or row.get("archive_errors"):
        raise ValueError(f"batch row not cleanly executed/archived: {run_id}")
    if row.get("termination") != phases.get("agent", {}).get("status") or row.get("reward") != phases.get("verifier", {}).get("reward"):
        raise ValueError(f"batch/raw termination or reward mismatch: {run_id}")
    events = summary.get("events", [])
    removed = [e.get("result") for e in events if e.get("phase") == "removal_verified"]
    requests, behavior = _request_records(run_dir)
    if len(requests) != row.get("model_requests_logged"):
        raise ValueError(f"logical request count disagrees with batch summary: {run_id}")
    bootstrap = Counter()
    first_log = load_json(run_dir / "agent/llm_call_1.json")
    for message in first_log.get("messages", []):
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            continue
        for name in ("get_task_metadata", "inspect_document"):
            if text.startswith(f"Bootstrap tool result ({name}"):
                bootstrap[name] += 1
    if dict(bootstrap) != row.get("bootstrap_tool_counts_from_first_request_history"):
        raise ValueError(f"bootstrap count mismatch: {run_id}")
    if not removed or any(value != "removed" for value in removed):
        raise ValueError(f"saved cleanup evidence not confirmed removed: {run_id}")
    if outcome.get("infra_failures") != []:
        raise ValueError(f"saved infrastructure status is not clean: {run_id}")
    stop_events = [e for e in events if e.get("phase") == "harbor_stop_done"]
    if not stop_events or any(e.get("stop_error") not in (None, "") for e in stop_events):
        raise ValueError(f"saved stop evidence missing or errored: {run_id}")
    resources = _resource(summary)
    phases_time = _event_phase(events)
    return {"round": round_no, "task_key": task, "task_label": SHORT[task], "run_id": run_id,
            "identity_sha256": summary["identity_sha256"], "attempt_status": row["status"], "returncode": row["returncode"],
            "attempt_wall_s": summary.get("wall_s"), "within_total_budget": summary.get("within_total_budget"),
            "termination": phases.get("agent", {}).get("status"), "reward": phases.get("verifier", {}).get("reward"),
            "infra_failures": outcome.get("infra_failures"), "cleanup": {"removal_verified_events": len(removed), "results": removed},
            "archive": {"batch_archive_verified": row.get("archive_verified"), "batch_archive_errors": row.get("archive_errors"),
                        "raw_manifest_identity_verified": raw_manifest.get("identity_sha256") == IDENTITY,
                        "raw_manifest_inputs_verified": len(raw_manifest.get("inputs", [])),
                        "raw_manifest_outputs_verified": len(raw_manifest.get("outputs", []))},
            "requests": {**behavior, "items": requests,
                         "batch_summary_action_counts": row.get("action_counts", {}),
                         "phase_usage": {k: phases.get("agent", {}).get(k) for k in ("n_input_tokens", "n_output_tokens", "n_cache_tokens")},
                         "phase_usage_semantics": "Agent accumulated usage as stored in summary; per-request usage from response records when present"},
            "bootstrap_tool_counts": dict(bootstrap), "tool_sequence": [r["tool_name"] for r in requests if r["action"] == "call_tool"],
            "activity_sequence": [r["activity"] for r in requests if r["action"] == "call_tool"],
            "phase_time": phases_time, "resources": resources,
            "time_limitations": {"request_intervals": "not calculated; saved call timestamps are not treated as verified same-clock start/end intervals",
                                 "tool_intervals": "not recorded; only call sequence is reported",
                                 "host_monotonic_phase_events_and_samples": "same recorded monotonic field family; aligned as archived timestamps"}}


def _quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def _describe(values: list[Any], points: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
    if not valid:
        return {"n": 0, "points": points, "median": None, "q1": None, "q3": None, "iqr": None, "min": None, "max": None}
    q1, q3 = _quantile(valid, .25), _quantile(valid, .75)
    return {"n": len(valid), "points": points, "median": statistics.median(valid), "q1": q1, "q3": q3,
            "iqr": q3 - q1, "min": min(valid), "max": max(valid)}


METRICS = {
    "logical_requests": lambda r: r["requests"]["logical_request_count"],
    "agent_tool_calls": lambda r: r["requests"]["tool_call_count"],
    "attempt_wall_s": lambda r: r["attempt_wall_s"],
    "sample_window_s": lambda r: r["resources"].get("sample_window_s"),
    "container_cpu_core_s": lambda r: r["resources"].get("container_cpu_core_s"),
    "memory_current_sampled_peak_bytes": lambda r: r["resources"].get("memory_current_sampled_peak_bytes"),
    "kernel_memory_peak_bytes": lambda r: r["resources"].get("kernel_memory_peak_bytes"),
    "host_agent_rss_sampled_peak_bytes": lambda r: r["resources"].get("host_agent_rss_sampled_peak_bytes"),
    "agent_phase_wall_s": lambda r: r["phase_time"]["agent"]["wall_s"],
    "verifier_phase_wall_s": lambda r: r["phase_time"]["verifier"]["wall_s"],
    "agent_phase_sampled_cpu_core_s": lambda r: r["resources"].get("phase_metrics", {}).get("agent", {}).get("sampled_cpu_core_s"),
    "verifier_phase_sampled_cpu_core_s": lambda r: r["resources"].get("phase_metrics", {}).get("verifier", {}).get("sampled_cpu_core_s"),
    "phase_input_tokens": lambda r: r["requests"]["phase_usage"].get("n_input_tokens"),
    "phase_output_tokens": lambda r: r["requests"]["phase_usage"].get("n_output_tokens"),
    "phase_cache_tokens": lambda r: r["requests"]["phase_usage"].get("n_cache_tokens"),
}


def _task_summaries(runs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = {}
    for task in TASKS:
        rows = [r for r in runs if r["task_key"] == task]
        metrics = {}
        for name, getter in METRICS.items():
            points = [{"round": r["round"], "run_id": r["run_id"], "value": getter(r)} for r in rows]
            metrics[name] = _describe([p["value"] for p in points], points)
        grouped[task] = {"task_label": SHORT[task], "n_runs": len(rows), "termination_points": [r["termination"] for r in rows],
                         "reward_points": [r["reward"] for r in rows], "metrics": metrics,
                         "tool_sequences": [{"round": r["round"], "run_id": r["run_id"], "sequence": r["tool_sequence"]} for r in rows],
                         "tool_name_counts": dict(Counter(name for r in rows for name in r["tool_sequence"])),
                         "activity_counts": dict(Counter(activity for r in rows for activity in r["activity_sequence"]))}
    return grouped


def _summary(batch: dict[str, Any], identity: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_reasons = Counter(item["invalid_reason"] or item["action"] for run in runs for item in run["requests"]["items"]
                              if item["action"] in {"invalid", "invalid_or_unknown", "unknown"})
    tool_returns = Counter(item.get("tool_return", "unknown") for run in runs for item in run["requests"]["items"]
                           if item["action"] == "call_tool")
    all_requests = [item for run in runs for item in run["requests"]["items"]]
    usage_keys = sorted({key for item in all_requests for key in item["usage"].get("fields", {})})
    usage_coverage = {key: {"n_total_requests": len(all_requests),
                            "n_valid": sum(key in item["usage"].get("fields", {}) for item in all_requests),
                            "n_missing": sum(key not in item["usage"].get("fields", {}) for item in all_requests),
                            "observed_values": [item["usage"]["fields"][key] for item in all_requests if key in item["usage"].get("fields", {})]}
                      for key in usage_keys}
    phase_usage_coverage = {}
    for key in ("n_input_tokens", "n_output_tokens", "n_cache_tokens"):
        values = [r["requests"]["phase_usage"].get(key) for r in runs]
        phase_usage_coverage[key] = {"n_total_runs": len(runs), "n_valid": sum(v is not None for v in values),
                                     "n_missing": sum(v is None for v in values), "values": values}
    archived_invalid = sum(row.get("action_counts", {}).get("invalid_or_unknown", 0)
                            + row.get("action_counts", {}).get("invalid", 0) for row in batch.get("results", []))
    embedded_accepted = sum(item.get("action_parse_method") == "first_embedded_json_object"
                            and item["action"] in {"call_tool", "finish"} for item in all_requests)
    reconstructed_invalid = sum(item["action"] in {"invalid", "invalid_or_unknown", "unknown"} for item in all_requests)
    def normalized_actions(counts: dict[str, Any]) -> dict[str, int]:
        return {"call_tool": counts.get("call_tool", 0), "finish": counts.get("finish", 0),
                "invalid_or_unknown": counts.get("invalid_or_unknown", 0) + counts.get("invalid", 0)}
    action_count_disagreements = [r["run_id"] for r in runs
                                  if normalized_actions(r["requests"]["batch_summary_action_counts"])
                                  != normalized_actions(r["requests"]["action_counts"])]
    archived_tool_call_count = sum(row.get("action_counts", {}).get("call_tool", 0) for row in batch.get("results", []))
    return {"scope": "仅 batch-summary 显式列出的九个 DOCOPS-OFFICE-REPEAT-01 run；三项固定本地 DocOps 原子任务",
            "identity": identity, "identity_verification": "plan/frozen 完整 identity 结构相等；规范 JSON SHA-256 与批准、批摘要、批 manifest、九次 raw summary/manifest 一致",
            "n_runs": len(runs), "execution_counts": dict(Counter(r["attempt_status"] for r in runs)),
            "termination_counts": dict(Counter(r["termination"] for r in runs)), "reward_counts": dict(Counter(str(r["reward"]) for r in runs)),
            "logical_request_count": sum(r["requests"]["logical_request_count"] for r in runs),
            "agent_tool_call_count": sum(r["requests"]["tool_call_count"] for r in runs),
            "batch_summary_agent_tool_call_count": archived_tool_call_count,
            "archived_batch_invalid_or_unknown_count": archived_invalid,
            "reconstructed_invalid_or_unknown_count": reconstructed_invalid,
            "non_bare_json_actions_accepted_by_harness_parser": embedded_accepted,
            "all_invalid_requests_match_transcript_invalid_markers": all(r["requests"]["invalid_response_transcript_crosscheck"] for r in runs),
            "all_transcript_step_counts_match": all(r["requests"]["transcript_step_count_matches_requests"] for r in runs),
            "batch_summary_action_count_disagreement_run_ids": action_count_disagreements,
            "agent_action_counts": dict(Counter(action for r in runs for action, count in r["requests"]["action_counts"].items() for _ in range(count))),
            "invalid_or_unknown_reasons": dict(invalid_reasons), "tool_return_status_counts": dict(tool_returns),
            "request_models": dict(Counter(model for r in runs for model, count in r["requests"]["request_model_counts"].items() for _ in range(count))),
            "response_models": dict(Counter(model for r in runs for model, count in r["requests"]["response_model_counts"].items() for _ in range(count))),
            "request_usage_field_coverage": usage_coverage,
            "agent_phase_usage_coverage": phase_usage_coverage,
            "bootstrap_totals": dict(Counter(k for r in runs for k, n in r["bootstrap_tool_counts"].items() for _ in range(n))),
            "bootstrap_observed_counts_by_tool": {tool: [r["bootstrap_tool_counts"].get(tool, 0) for r in runs]
                                                   for tool in sorted({name for r in runs for name in r["bootstrap_tool_counts"]})},
            "bootstrap_counted_as_agent_tool_actions": False,
            "task_summaries": _task_summaries(runs),
            "statistics": {"n": "per task, valid observations only", "quantile": "linear interpolation at position (n-1)*p; IQR=Q3-Q1",
                           "unit": "three repeats are within-task repeated runs, not independent tasks"},
            "phase_and_resource_scope": {"attempt_wall": "summary wall_s; whole attempt", "sample_window": "first to last saved monotonic sampler timestamp",
                 "phase_wall": "differences between saved monotonic phase events", "phase_cpu": "sum of cumulative cgroup CPU differences only for adjacent sample pairs wholly inside that phase",
                 "boundary_cpu": "intervals crossing recorded phase boundaries remain mixed; no proportional allocation",
                 "container_cpu_memory": "shared task-container scope; not attributable to one tool", "host_rss": "host Agent/process observation, not inference-only",
                 "memory_current": "sampled maximum; distinct from kernel memory peak", "io": "counters/read status only; not equivalent to complete document/filesystem I/O"},
            "limitations": ["logical request logs do not reveal actual provider/framework transport-attempt count", "cost remains unknown; saved cost_usd=0 is not a bill",
                            "no reliable per-tool start/end intervals; no tool duration or thinking time", "0.5s sampling cannot resolve short tool-level resource attribution",
                            "three tasks are fixed local DocOps samples in ARM64-adapted environments, not Office-category representatives",
                            "reward=1 supports these recorded task outcomes, not a project/G2 pass or official amd64 equivalence"]}


def _markdown(summary: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    lines = ["# DOCOPS-OFFICE-REPEAT-01 离线行为—资源特征化", "",
             "## 范围与核验", "", f"显式分析 {summary['n_runs']} 个 run，identity `{IDENTITY}`。计划与冻结文件的完整 identity 对象相等，规范化 SHA-256 与批准、批摘要、批 manifest 及 raw 记录一致；批 manifest 的 {summary['archive_verification']['batch_manifest_input_records_verified']} 项输入、{summary['archive_verification']['batch_manifest_output_records_verified']} 项输出及九份 raw manifest 的 {summary['archive_verification']['raw_manifest_output_records_verified']} 项输出均逐项哈希核验；分析共登记 {summary['archive_verification']['distinct_input_and_archive_files_hashed']} 个实际输入/归档文件。清理仅依据归档事件 `removal_verified=removed`，未查询当前 Docker。", "",
             "这九次是 Excel/PPT/PDF 三项固定本地 DocOps 原子任务各三次，不是 Office 总体样本。执行环境为 ARM64 适配镜像，不能声称与官方 amd64 环境等价。", "",
             "## 行为与终止", "", "共保存逻辑请求 **%d** 次、Agent 自主工具调用 **%d** 次；bootstrap 每 run 的 `get_task_metadata`、`inspect_document` 分开计数，不纳入 Agent 工具数。" % (summary["logical_request_count"], summary["agent_tool_call_count"]),
             "", "| Task | Round | Run | 逻辑请求 | Agent 工具序列 | invalid/unknown | termination | reward |", "|---|---:|---|---:|---|---:|---|---:|"]
    for run in runs:
        sequence = " → ".join(run["tool_sequence"]) or "—"
        invalid = sum(1 for item in run["requests"]["items"] if item["action"] in {"invalid", "invalid_or_unknown", "unknown"})
        lines.append(f"| {run['task_label']} | {run['round']} | `{run['run_id']}` | {run['requests']['logical_request_count']} | {sequence} | {invalid} | {run['termination']} | {run['reward']} |")
    usage_avail = {key: f"{value['n_valid']}/{value['n_total_requests']}，缺失 {value['n_missing']}"
                    for key, value in summary["request_usage_field_coverage"].items()}
    lines += ["", f"请求模型为 `{summary['request_models']}`，响应记录 model 为 `{summary['response_models']}`；它们是请求别名与服务端返回标识，不证明不可变模型版本。批摘要登记 Agent 工具调用 **{summary['batch_summary_agent_tool_call_count']}** 次；从响应与 transcript 的运行时提取语义重算为 **{summary['agent_tool_call_count']}** 次，差异run `{summary['batch_summary_action_count_disagreement_run_ids']}`。批摘要把 **{summary['archived_batch_invalid_or_unknown_count']}** 条计为 invalid/unknown；复核后 {summary['non_bare_json_actions_accepted_by_harness_parser']} 条非裸 JSON 被接受为有效动作，{summary['reconstructed_invalid_or_unknown_count']} 条实际无效/未知（原因 `{summary['invalid_or_unknown_reasons']}`），且与 transcript 无效标记相符。这属于响应格式/动作协议，不等同 API 或工具执行失败。工具返回状态分布为 `{summary['tool_return_status_counts']}`；按日志内相邻 assistant action / `Tool result for <tool>` 消息及参数核对关联，无独立 call ID。", "",
              f"请求响应中可读取的数值 token 字段（有效/49逻辑请求）为 `{usage_avail}`；Agent 汇总 usage 另见 `summary.json` 与逐 run 数据。usage 不等于账单，保存的 cost=0 不是免费证据；费用 unknown。", "",
              "活动解释按结构化工具名保守分类：copy_file、文档/内容检查、Excel 公式编辑、PPT 文本编辑、PDF 页面编辑；不同工具接口不合并成 shell/Coding 活动类别。完整安全参数摘要与逐请求状态见 `per_run.jsonl`。", "",
              "## 时间与资源", "", "| Task | Run | Attempt wall s | 采样点/窗口 s | Agent wall s | Verifier wall s | 容器 CPU core-s | Agent 阶段 CPU core-s | Verifier 阶段 CPU core-s | memory.current 峰值 B | kernel peak B | 宿主 RSS 峰值 B |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        r, p = run["resources"], run["phase_time"]
        lines.append(f"| {run['task_label']} | `{run['run_id']}` | {run['attempt_wall_s']} | {r.get('sample_count')}/{r.get('sample_window_s')} | {p['agent']['wall_s']} | {p['verifier']['wall_s']} | {r.get('container_cpu_core_s')} | {r.get('phase_metrics',{}).get('agent',{}).get('sampled_cpu_core_s')} | {r.get('phase_metrics',{}).get('verifier',{}).get('sampled_cpu_core_s')} | {r.get('memory_current_sampled_peak_bytes')} | {r.get('kernel_memory_peak_bytes')} | {r.get('host_agent_rss_sampled_peak_bytes')} |")
    lines += ["", "其他已记录阶段 wall（单调事件边界差，秒；archive 为事件标记跨度而非完整归档耗时）：", "",
              "| Run | Harbor start | Agent setup | Agent | Verifier | Harbor stop | Archive event span |", "|---|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        phases = run["phase_time"]
        vals = [phases[name].get("event_span_s" if name == "archive" else "wall_s") for name in
                ("harbor_start", "agent_setup", "agent", "verifier", "harbor_stop", "archive")]
        lines.append(f"| `{run['run_id']}` | " + " | ".join(str(v) for v in vals) + " |")
    lines += ["", "容器 blkio service-byte 观测 delta（读/写 bytes；不是完整文件系统 I/O）：", "",
              "| Run | 状态 | Read bytes | Write bytes |", "|---|---|---:|---:|"]
    for run in runs:
        io = run["resources"].get("io_observed_blkio", {})
        lines.append(f"| `{run['run_id']}` | {io.get('status')} | {io.get('read_service_bytes_delta')} | {io.get('write_service_bytes_delta')} |")
    lines += ["", "采样窗口短于 attempt wall；阶段 wall 按单调事件记录计算。阶段 CPU 仅累加采样区间两端都位于阶段内的累计计数差；跨阶段边界不分摊。请求日志时间字段未被当作已验证的请求区间，工具仅报告顺序。`memory.current` 是采样最大值，kernel peak 与宿主 RSS 分列。采集器使用 cgroup v1 blkio service-bytes 设备计数，状态可区分实际无记录的零与不可用；这些是容器块设备服务计数，不是完整文档/文件系统 I/O。逐 run delta 见 `per_run.jsonl`。", "",
              "## 同任务三次重复", "", "每任务单独列三个原始点及 n、median、IQR（线性插值位置 `(n−1)p`，IQR=Q3−Q1）；有效 n 按指标计算：", ""]
    for task, data in summary["task_summaries"].items():
        lines.append(f"### {data['task_label']} (`{task}`)")
        lines.append("")
        for metric in ("logical_requests", "agent_tool_calls", "phase_input_tokens", "phase_output_tokens", "phase_cache_tokens",
                       "attempt_wall_s", "container_cpu_core_s", "memory_current_sampled_peak_bytes", "kernel_memory_peak_bytes"):
            stat = data["metrics"][metric]
            vals = [p["value"] for p in stat["points"]]
            lines.append(f"- {metric}: 原始点 `{vals}`；n={stat['n']}，median={stat['median']}，IQR={stat['iqr']}。")
        lines.append("")
    lines += ["## 结论边界与下一步", "", "数据支持：在本批登记条件下，三个任务分别呈现上述结构化操作序列、逻辑请求数和共享容器/宿主观测；同任务三次原始值存在可量化差异。reward=1 与 finish 是本批保存的任务/终止事实，资源仍可描述其执行过程。", "", "不能据此推断 Office 类别总体、工具数导致 CPU 差异、单工具独占资源、模型/框架排名、推理时间、真实账单或 ARM64 与 amd64 等价性。三次重复不足以证明稳定趋势；容器资源不区分工具和 verifier 之外的容器活动。", "", "唯一最小下一步建议：若要将结论从三个固定任务扩展为 Office workload 特征，先按同样固定配置为不同 Office 任务类型登记少量重复样本；本轮不启动。"]
    return "\n".join(lines) + "\n"


def analyze(root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_dir = (output_dir or root / OUT).resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output_dir}")
    batch, batch_manifest, raw_manifest_paths, _, verified_inputs = _verify_batch(root)
    rows = batch["results"]
    runs = [_run(root, row, manifest_path) for row, manifest_path in zip(rows, raw_manifest_paths)]
    identity = load_json(root / ENV / "frozen-identity.json")["identity"]
    summary = _summary(batch, identity, runs)
    summary["archive_verification"] = {
        "batch_manifest_input_records_verified": len(batch_manifest.get("inputs", [])),
        "batch_manifest_output_records_verified": len(batch_manifest.get("outputs", [])),
        "raw_run_manifests_verified": len(raw_manifest_paths),
        "raw_manifest_input_records_verified": sum(r["archive"]["raw_manifest_inputs_verified"] for r in runs),
        "raw_manifest_output_records_verified": sum(r["archive"]["raw_manifest_outputs_verified"] for r in runs),
        "distinct_input_and_archive_files_hashed": len(verified_inputs),
        "read_after_write_output_hashes_verified": True,
        "manifest_self_hash": "omitted_by_design",
    }
    output_dir.mkdir(parents=True)
    per_run_path = output_dir / "per_run.jsonl"
    with per_run_path.open("w", encoding="utf-8") as stream:
        for run in runs:
            stream.write(json.dumps(run, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path = output_dir / "summary.md"
    markdown_path.write_text(_markdown(summary, runs), encoding="utf-8")
    code_paths = [root / "scripts/docops_office_repeat_characterization.py",
                  root / "scripts/docops_word_resource_analysis.py"]
    input_paths = {root / record["path"] for record in verified_inputs}
    input_paths.update(p.resolve() for p in code_paths)
    manifest = {"schema": "docops-office-repeat-characterization-manifest-v1",
                "batch_identity_sha256": IDENTITY,
                "identity_verification_scope": "full plan/frozen structure plus canonical digest cross-linked to approval, batch artifacts and raw run records",
                "inputs": [file_record(root, p) for p in sorted(input_paths)],
                "analysis_code": [file_record(root, p) for p in code_paths],
                "outputs": [file_record(root, p) for p in (per_run_path, summary_path, markdown_path)],
                "manifest_self_hash": "omitted_by_design"}
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in manifest["outputs"]:
        path = root / item["path"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise IOError(f"output read-back mismatch: {item['path']}")
    for item in manifest["inputs"]:
        path = root / item["path"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise IOError(f"input changed during analysis: {item['path']}")
    return {"summary": summary, "runs": runs, "manifest": manifest}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = analyze(args.root, args.output)
    print(json.dumps({"output": str((args.output or args.root / OUT).resolve()), "runs": result["summary"]["n_runs"],
                      "identity": IDENTITY, "inputs": len(result["manifest"]["inputs"])}, ensure_ascii=False))
