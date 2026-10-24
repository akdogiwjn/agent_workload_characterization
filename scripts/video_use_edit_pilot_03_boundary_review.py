"""Offline, Agent-side diagnostics for a saved video-use PILOT-03 run.

This module deliberately accepts only the Agent transcript, EDL, cuts manifest,
and native rollout events. It has no verifier/oracle input path.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens",
              "reasoning_output_tokens", "total_tokens")


def _payload_args(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("arguments", {})
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
    return value if isinstance(value, dict) else {}


def _command_class(command: str) -> str:
    if "timeline_view.py" in command:
        return "timeline_view"
    if "render.py" in command:
        return "render"
    if "ffmpeg" in command and "astats" in command:
        return "whole_source_audio_level_scan"
    if "ffprobe" in command:
        return "ffprobe"
    return "other"


def _process_exit(output: Any) -> int | None:
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    match = re.search(r"Process exited with code (-?\d+)", text)
    return int(match.group(1)) if match else None


def analyze_rollout_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Count protocol events, command outcomes, recovery, and deduplicated usage."""
    event_counts: Counter[str] = Counter()
    calls: list[dict[str, Any]] = []
    returns: list[dict[str, Any]] = []
    protocol_errors = 0
    usage_records: list[dict[str, Any]] = []

    for index, event in enumerate(events):
        event_type = str(event.get("type", "unknown"))
        event_counts[event_type] += 1
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if event_type == "response_item":
            item_type = payload.get("type")
            event_counts[f"response_item:{item_type}"] += 1
            if item_type == "function_call":
                args = _payload_args(payload)
                command = args.get("cmd", "") if isinstance(args.get("cmd", ""), str) else ""
                name = payload.get("name")
                calls.append({
                    "index": index,
                    "call_id": payload.get("call_id"),
                    "name": name,
                    "command": command,
                    "command_class": _command_class(command) if name == "exec_command" else None,
                    "arguments": args,
                })
            elif item_type == "function_call_output":
                returns.append({"index": index, "call_id": payload.get("call_id"),
                                "output": payload.get("output")})
            elif item_type in ("function_call_error", "error"):
                protocol_errors += 1
        elif event_type == "token_usage_record":
            usage = payload.get("usage") or {}
            if isinstance(usage, dict):
                usage_records.append({"response_id": payload.get("response_id"),
                                      "usage": usage, "turn_token_usage": payload.get("turn_token_usage"),
                                      "thread_token_usage": payload.get("thread_token_usage")})

    return_by_id = {item.get("call_id"): item for item in returns if item.get("call_id")}
    call_by_id = {item.get("call_id"): item for item in calls if item.get("call_id")}
    command_outcomes = []
    for call_id, call in call_by_id.items():
        result = return_by_id.get(call_id)
        if not result or call.get("name") != "exec_command":
            continue
        exit_code = _process_exit(result.get("output"))
        command = call.get("command", "")
        command_class = call.get("command_class")
        if command_class == "timeline_view":
            summary = ("invalid_named_time_flags" if any(flag in command for flag in
                       ("--start", "--end", "--interval")) else "positional_time_arguments")
        else:
            summary = command_class
        command_outcomes.append({"call_id": call_id, "index": call["index"],
                                 "command_class": command_class, "command_summary": summary,
                                 "exit_code": exit_code, "return_index": result["index"]})

    nonzero_commands = []
    for outcome in command_outcomes:
        if outcome.get("exit_code") in (None, 0):
            continue
        recovery = next((later for later in command_outcomes
                         if later["index"] > outcome["return_index"]
                         and later.get("command_class") == outcome.get("command_class")
                         and later.get("exit_code") == 0), None)
        viewed_image_after = any(
            call.get("name") == "view_image" and call["index"] > (recovery or {}).get("return_index", 10**18)
            and "timeline" in str(_payload_args(call).get("path", "")).lower()
            for call in calls
        ) if recovery else False
        nonzero_commands.append({**outcome,
                                 "recovered_by_later_same_class_success": recovery is not None,
                                 "recovery_call_id": recovery.get("call_id") if recovery else None,
                                 "recovery_image_viewed": viewed_image_after})

    image_views = []
    for call in calls:
        if call.get("name") == "view_image":
            path = _payload_args(call).get("path")
            image_views.append({"index": call["index"],
                                "basename": Path(path).name if isinstance(path, str) else None})

    render_calls = []
    for call in calls:
        if call.get("command_class") != "render":
            continue
        command = call["command"]
        render_calls.append({"index": call["index"], "call_id": call["call_id"],
                             "exit_code": next((o["exit_code"] for o in command_outcomes
                                                if o["call_id"] == call["call_id"]), None),
                             "preserve_source_spec": "--preserve-source-spec" in command,
                             "no_grade": "--no-grade" in command,
                             "no_audio_fades": "--no-audio-fades" in command,
                             "no_loudnorm": "--no-loudnorm" in command,
                             "no_subtitles": "--no-subtitles" in command})

    # A response_id is the dedupe key. `turn_token_usage` and
    # `thread_token_usage` are cumulative snapshots; never sum those fields.
    usage_by_response: dict[str, dict[str, Any]] = {}
    missing_response_ids = 0
    duplicate_response_ids = 0
    for record in usage_records:
        response_id = record.get("response_id")
        if not isinstance(response_id, str) or not response_id:
            missing_response_ids += 1
            continue
        if response_id in usage_by_response:
            duplicate_response_ids += 1
        usage_by_response[response_id] = record
    usage_totals = {key: sum((record["usage"].get(key, 0) or 0)
                             for record in usage_by_response.values()) for key in TOKEN_KEYS}
    last_cumulative = next(reversed(usage_by_response.values()), None) if usage_by_response else None
    cumulative = (last_cumulative or {}).get("turn_token_usage") or {}

    return {
        "tool_call_events": len(calls),
        "tool_return_events": len(returns),
        "protocol_error_events": protocol_errors,
        "calls_without_return": sum(call.get("call_id") not in return_by_id for call in calls),
        "exec_command_events": sum(call.get("name") == "exec_command" for call in calls),
        "view_image_events": len(image_views),
        "image_view_basenames": [item["basename"] for item in image_views],
        "command_outcomes": command_outcomes,
        "nonzero_command_events": nonzero_commands,
        "render_calls": render_calls,
        "timeline_view_calls": [item for item in command_outcomes
                                 if item.get("command_class") == "timeline_view"],
        "native_response_records": len(usage_records),
        "unique_response_ids": len(usage_by_response),
        "duplicate_response_id_records": duplicate_response_ids,
        "usage_records_missing_response_id": missing_response_ids,
        "per_response_usage_totals": usage_totals,
        "last_turn_usage_snapshot": {key: cumulative.get(key) for key in TOKEN_KEYS
                                     if key in cumulative},
        "http_attempts": "unknown; native rollout does not provide a reliable transport-attempt ledger",
    }


def analyze_boundaries(cuts: dict[str, Any], edl: dict[str, Any],
                       transcript_words: list[dict[str, Any]], fps: float = 25.0) -> dict[str, Any]:
    """Compare Agent-authored boundaries to its own EDL/transcript, not a scorer."""
    cut_items = cuts.get("cuts") or []
    ranges = edl.get("ranges") or []
    if len(cut_items) != 1 or len(ranges) != 2:
        return {"supported": False, "reason": "expected_one_cut_and_two_retained_ranges"}
    cut = cut_items[0]
    start_s = int(cut["start_ms"]) / 1000.0
    end_s = int(cut["end_ms"]) / 1000.0
    left, right = ranges
    start_matches = float(left.get("end", -1)) == start_s
    end_matches = float(right.get("start", -1)) == end_s
    exact_start_words = [w for w in transcript_words
                         if w.get("type") == "word" and float(w.get("start", -2)) == start_s]
    exact_end_words = [w for w in transcript_words
                       if w.get("type") == "word" and float(w.get("start", -2)) == end_s]
    removed_words = [w.get("text", "") for w in transcript_words
                     if w.get("type") == "word"
                     and float(w.get("start", 10**9)) >= start_s
                     and float(w.get("end", -1)) <= end_s]
    kept_duration = sum(float(r["end"]) - float(r["start"]) for r in ranges)
    return {
        "supported": True,
        "agent_cut_ms": {"start": int(cut["start_ms"]), "end": int(cut["end_ms"])},
        "agent_cut_seconds": {"start": start_s, "end": end_s},
        "edl_matches_cuts_json": start_matches and end_matches,
        "edl_start_matches_cut_ms": start_matches,
        "edl_end_matches_cut_ms": end_matches,
        "edl_kept_duration_s": kept_duration,
        "removed_word_tokens": removed_words,
        "start_boundary_word_tokens": [w.get("text") for w in exact_start_words],
        "end_boundary_word_tokens": [w.get("text") for w in exact_end_words],
        "start_frame_aligned_at_source_fps": abs(start_s * fps - round(start_s * fps)) < 1e-8,
        "end_frame_aligned_at_source_fps": abs(end_s * fps - round(end_s * fps)) < 1e-8,
        "score_range_pass": "not read here; this function uses Agent-side evidence only",
    }


def load_agent_evidence(raw_root: Path) -> dict[str, Any]:
    """Load only task/instruction/transcript/cuts/EDL/native rollout Agent artifacts."""
    raw_root = Path(raw_root)
    workspace = raw_root / "workspace"
    edit = workspace / "project/edit"
    cuts = json.loads((workspace / "output/cuts.json").read_text())
    edl = json.loads((edit / "edl.json").read_text())
    transcript = json.loads((edit / "transcripts/source.json").read_text())
    rollout_path = next((workspace / "export/rollouts").rglob("rollout-*.jsonl"))
    events = [json.loads(line) for line in rollout_path.read_text(errors="replace").splitlines()
              if line.strip()]
    return {
        "cuts": cuts,
        "edl": edl,
        "transcript": transcript,
        "boundary": analyze_boundaries(cuts, edl, transcript.get("words", [])),
        "rollout": analyze_rollout_events(events),
        "rollout_path": rollout_path,
    }

