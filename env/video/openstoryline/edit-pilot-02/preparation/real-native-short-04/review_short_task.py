#!/usr/bin/env python3
"""Offline evidence review for real-native-short-04; never starts a model/session."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path("/home/lcq/agent_workload_characterization")
PREP = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04"
OUT = PREP / "output"
REVIEW = PREP / "postflight-review.json"
MANIFEST = PREP / "evidence-manifest-review.json"
REQUIRED = {"load_media", "split_shots", "local_asr", "speech_rough_cut",
            "plan_timeline_pro", "render_video"}


def digest(path: Path) -> dict:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main() -> int:
    if REVIEW.exists() or MANIFEST.exists():
        raise RuntimeError("refusing to overwrite postflight review evidence")
    run = json.loads((PREP / "container-run.json").read_text(encoding="utf-8"))
    context = json.loads((OUT / "agent-context.json").read_text(encoding="utf-8"))
    session_id = context["session_id"]
    store = OUT / session_id
    meta = json.loads((store / "meta.json").read_text(encoding="utf-8"))
    node_meta = {row["node_id"]: row for row in meta if row.get("node_id") in REQUIRED}
    artifacts = {}
    for node in REQUIRED:
        row = node_meta.get(node)
        if not row:
            raise RuntimeError(f"required native artifact missing: {node}")
        artifact_path = store / node / f"{row['artifact_id']}.json"
        artifacts[node] = json.loads(artifact_path.read_text(encoding="utf-8"))

    tools = jsonl(OUT / "mcp-tool-events.jsonl")
    starts = [row for row in tools if row.get("event") == "tool_call_started"]
    finishes = [row for row in tools if row.get("event") == "tool_call_finished"]
    starts_by_node = {row.get("node_id"): row for row in starts}
    success_nodes = {row.get("node_id") for row in finishes
                     if not row.get("is_error")}
    links = [
        ("load_media", "split_shots", "load_media"),
        ("split_shots", "local_asr", "split_shots"),
        ("local_asr", "speech_rough_cut", "asr"),
        ("speech_rough_cut", "plan_timeline_pro", "speech_rough_cut"),
        ("plan_timeline_pro", "render_video", "plan_timeline"),
    ]
    link_checks = []
    for producer, consumer, argument in links:
        observed = starts_by_node.get(consumer, {}).get("arguments", {}).get(argument)
        expected = artifacts[producer].get("payload")
        link_checks.append({"producer": producer, "consumer": consumer,
                            "argument": argument, "payload_matches_artifact": observed == expected})

    history_starts = [row for row in starts if row.get("node_id") == "read_node_history"]
    history_finishes = [row for row in finishes if row.get("node_id") == "read_node_history"
                        and not row.get("is_error")]
    requested_history_ids = {row.get("arguments", {}).get("query_artifact_id")
                             for row in history_starts}
    returned_history_ids = set()
    for row in history_finishes:
        history = (row.get("returned_payload") or {}).get("history") or {}
        history_meta, data = history.get("meta") or {}, history.get("node_data") or {}
        if (history_meta.get("session_id") == session_id == data.get("session_id")
                and history_meta.get("artifact_id") == data.get("artifact_id")):
            returned_history_ids.add(history_meta.get("artifact_id"))

    request_events = jsonl(OUT / "model-requests.jsonl")
    request_starts = [row for row in request_events if row.get("event") == "request_started"]
    request_finishes = [row for row in request_events if row.get("event") == "request_finished"]
    usage_tokens = sum(int((row.get("usage") or {}).get(
        "total_tokens", (row.get("usage") or {}).get("input_tokens", 0)
        + (row.get("usage") or {}).get("output_tokens", 0)) or 0)
                       for row in request_finishes)
    output_cap_ok = all(0 < row.get("max_output_tokens_per_request", 0) <= 8192
                        for row in request_starts)

    asr_payload = artifacts["local_asr"].get("payload", {}).get("asr_infos", [])
    asr_sentences = len(asr_payload[0].get("asr_sentence_info", [])) if asr_payload else 0
    timeline = artifacts["plan_timeline_pro"].get("payload", {}).get("tracks", {})
    subtitles = timeline.get("subtitles", []) or []
    render_args = starts_by_node.get("render_video", {}).get("arguments", {})
    render_path = (OUT / artifacts["render_video"].get("payload", {})
                   .get("output_path", "").removeprefix("/workspace/output/")).resolve()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(render_path)],
                           capture_output=True, text=True, check=True, timeout=30)
    media = json.loads(probe.stdout)
    stream_facts = [{key: stream.get(key) for key in
                     ("codec_type", "codec_name", "width", "height", "avg_frame_rate",
                      "start_time", "duration")}
                    for stream in media.get("streams", [])]
    phase = json.loads((OUT / "phase-times.json").read_text(encoding="utf-8"))
    start_ns = json.loads((PREP / "run-start.json").read_text(encoding="utf-8"))[
        "started_monotonic_ns"]
    elapsed = (time.monotonic_ns() - start_ns) / 1e9
    native_chain_ok = (REQUIRED.issubset(success_nodes)
                       and all(item["payload_matches_artifact"] for item in link_checks))
    requests_ok = (len(request_starts) == len(request_finishes) <= 40
                   and len({row.get("request_id") for row in request_starts})
                   == len(request_starts) and output_cap_ok and usage_tokens <= 500_000)
    history_ok = (bool(history_starts)
                  and len(history_starts) == len(history_finishes)
                  and requested_history_ids.issubset(returned_history_ids)
                  and node_meta["render_video"]["artifact_id"] in returned_history_ids)
    audio_requested = (render_args.get("include_video_audio") is True
                       and float(render_args.get("video_volume_scale", 0)) == 1.0)
    submission_absent = not (OUT / "output.mp4").exists() and not (OUT / "cuts.json").exists()
    checks = {
        "fresh_budget_wall_under_1800s": elapsed <= 1800 and run.get("wall_s", 999999) <= 1800,
        "request_budget_and_ledger": requests_ok,
        "all_required_native_tools_succeeded": REQUIRED.issubset(success_nodes),
        "real_predecessor_payloads_consumed": all(x["payload_matches_artifact"] for x in link_checks),
        "same_session_history_queries_succeeded": history_ok,
        "real_local_asr_sentence_segments": asr_sentences > 0,
        "real_agent_and_speech_node_requests": (
            any(row.get("phase") == "agent" for row in request_starts)
            and any(row.get("phase") == "mcp_sampling"
                    and row.get("association", {}).get("node_id") == "speech_rough_cut"
                    for row in request_finishes)),
        "audio_preservation_requested": audio_requested,
        "render_artifact_probe_has_h264_and_aac": (
            any(s.get("codec_type") == "video" and s.get("codec_name") == "h264"
                for s in stream_facts)
            and any(s.get("codec_type") == "audio" and s.get("codec_name") == "aac"
                    for s in stream_facts)),
        "no_subtitles_requirement": len(subtitles) == 0,
        "submission_export_completed": not submission_absent,
        "container_and_mcp_cleanup": (run.get("container_removal") == "removed"
                                       and phase.get("mcp_cleanup_status") == "stopped"),
    }
    blockers = []
    if not checks["no_subtitles_requirement"]:
        blockers.append("plan_timeline_contains_subtitle_track_render_video_composites_subtitle_items")
    if submission_absent:
        blockers.append("submission_export_and_cuts_validation_not_reached_after_initial_postflight_assertion")
    if not history_ok:
        blockers.append("same_session_history_result_or_artifact_link_incomplete")
    if any(not value for key, value in checks.items()
           if key not in {"no_subtitles_requirement", "submission_export_completed"}):
        blockers.append("one_or_more_execution_or_budget_checks_failed")
    result = {
        "schema": "openstoryline-real-native-short-postflight-review-v1",
        "status": "FAIL_GATE", "record_kind": "read_only_review_of_one_consumed_session",
        "run_id": json.loads((PREP / "request.json").read_text())["frozen_identity"]["run_id"],
        "session_id": session_id,
        "initial_runner_error": "history did not retrieve every required same-session artifact",
        "initial_history_assertion_assessment": (
            "too strict: it required explicit history queries for every artifact; actual downstream "
            "MCP arguments match the preceding artifact payloads, and each issued history query "
            "returned the requested artifact from this session"),
        "checks": checks, "blockers": blockers,
        "budget": {"wall_limit_s": 1800, "observed_wall_s": run.get("wall_s"),
                   "request_limit": 40, "requests_started": len(request_starts),
                   "requests_finished": len(request_finishes),
                   "observed_tokens": usage_tokens, "observed_tokens_soft_threshold": 500000,
                   "max_output_tokens_per_request": 8192,
                   "http_requests": "unknown"},
        "model": {"requested": "qwen3.7-plus", "base_url": context.get("base_url"),
                  "response_models": sorted({(row.get("response_metadata") or {}).get("model_name")
                                              for row in request_finishes
                                              if (row.get("response_metadata") or {}).get("model_name")})},
        "native_chain": {"successful_nodes": sorted(REQUIRED & success_nodes),
                         "artifact_payload_links": link_checks,
                         "history_queries": len(history_starts),
                         "history_returned_artifact_ids": sorted(returned_history_ids),
                         "asr_sentence_count": asr_sentences},
        "render": {"artifact_id": node_meta["render_video"]["artifact_id"],
                   "path": str(render_path), **digest(render_path),
                   "streams": stream_facts, "timeline_subtitle_count": len(subtitles),
                   "timeline_subtitle_texts": [row.get("text") for row in subtitles],
                   "include_video_audio": render_args.get("include_video_audio"),
                   "video_volume_scale": render_args.get("video_volume_scale")},
        "submission": {"output_mp4": "not exported", "cuts_json": "not exported",
                       "reason": blockers[-1] if submission_absent else None},
        "cleanup": {"container_removal": run.get("container_removal"),
                    "mcp_cleanup": phase.get("mcp_cleanup_status"),
                    "image_retained": True, "model_cache_retained": True},
        "formal": {"identity": False, "approval": False, "attempt": False,
                   "judge": False, "reward": None},
        "evidence": {"failure_report": str((PREP / "failure-report.json").relative_to(ROOT)),
                     "original_partial_manifest": str((PREP / "evidence-manifest.json").relative_to(ROOT)),
                     "corrected_entry_validator": str((PREP / "run_short_task.py").relative_to(ROOT))},
    }
    with REVIEW.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()

    files = []
    for path in sorted(PREP.rglob("*")):
        if not path.is_file() or path == MANIFEST or path.suffix == ".pyc":
            continue
        files.append({"path": str(path.relative_to(PREP)), **digest(path)})
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-real-native-short-evidence-review-v1",
                   "self_hash": "omitted", "files": files}, stream, ensure_ascii=False,
                  indent=2)
        stream.write("\n")
        stream.flush()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
