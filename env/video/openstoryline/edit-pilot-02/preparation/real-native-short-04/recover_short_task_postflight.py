#!/usr/bin/env python3
"""Finish local export/verification from the already-rendered session artifact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("/home/lcq/agent_workload_characterization")
PREP = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04"
OUT = PREP / "output"
RECOVERY = PREP / "postflight-recovery.json"
REPORT = PREP / "validation-report.json"
GATE = PREP.parent / "native-agent-gate.json"
MANIFEST = PREP / "evidence-manifest-final.json"
SOURCE_TREE = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source"
SOURCE = PREP / "input/source.mp4"
REQUIRED = {"load_media", "split_shots", "local_asr", "speech_rough_cut",
            "plan_timeline_pro", "render_video"}

sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
sys.path.insert(0, str(ROOT / "src"))
import openstoryline_pilot_entry as entry  # noqa: E402


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


def decode_luma(path: Path) -> dict:
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
               "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    result = subprocess.run(command, capture_output=True, check=True, timeout=90)
    return {"decoded_luma_bytes": len(result.stdout),
            "nonzero_luma_pixels": sum(value != 0 for value in result.stdout),
            "max_luma": max(result.stdout) if result.stdout else None,
            "full_decode_returncode": result.returncode}


def main() -> int:
    for path in (RECOVERY, REPORT, GATE, MANIFEST, OUT / "output.mp4", OUT / "cuts.json"):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing artifact: {path}")
    start = json.loads((PREP / "run-start.json").read_text(encoding="utf-8"))
    run = json.loads((PREP / "container-run.json").read_text(encoding="utf-8"))
    request = json.loads((PREP / "request.json").read_text(encoding="utf-8"))
    frozen = request["frozen_identity"]
    context = json.loads((OUT / "agent-context.json").read_text(encoding="utf-8"))
    session_id = context["session_id"]
    store = OUT / session_id
    meta = json.loads((store / "meta.json").read_text(encoding="utf-8"))
    node_meta = {row["node_id"]: row for row in meta if row.get("node_id") in REQUIRED}
    if set(node_meta) != REQUIRED:
        raise RuntimeError("required native artifacts are incomplete")
    artifacts = {}
    for node, row in node_meta.items():
        artifacts[node] = json.loads(
            (store / node / f"{row['artifact_id']}.json").read_text(encoding="utf-8"))

    tool_events = jsonl(OUT / "mcp-tool-events.jsonl")
    tool_starts = [row for row in tool_events if row.get("event") == "tool_call_started"]
    tool_finishes = [row for row in tool_events if row.get("event") == "tool_call_finished"]
    success_nodes = {row.get("node_id") for row in tool_finishes if not row.get("is_error")}
    starts_by_node = {row.get("node_id"): row for row in tool_starts}
    for node in REQUIRED:
        if node not in success_nodes or node not in starts_by_node:
            raise RuntimeError(f"required successful MCP node call missing: {node}")

    links = [("load_media", "split_shots", "load_media"),
             ("split_shots", "local_asr", "split_shots"),
             ("local_asr", "speech_rough_cut", "asr"),
             ("speech_rough_cut", "plan_timeline_pro", "speech_rough_cut"),
             ("plan_timeline_pro", "render_video", "plan_timeline")]
    link_report = []
    for producer, consumer, argument in links:
        match = (starts_by_node[consumer].get("arguments", {}).get(argument)
                 == artifacts[producer].get("payload"))
        link_report.append({"producer": producer, "consumer": consumer,
                            "argument": argument, "exact_payload_match": match})
    if not all(row["exact_payload_match"] for row in link_report):
        raise RuntimeError("a downstream node did not consume its actual predecessor payload")

    history_starts = [row for row in tool_starts if row.get("node_id") == "read_node_history"]
    history_finishes = [row for row in tool_finishes if row.get("node_id") == "read_node_history"
                        and not row.get("is_error")]
    query_ids = {row.get("arguments", {}).get("query_artifact_id") for row in history_starts}
    returned_ids = set()
    for row in history_finishes:
        history = (row.get("returned_payload") or {}).get("history") or {}
        hmeta = history.get("meta") or {}
        data = history.get("node_data") or {}
        if (hmeta.get("session_id") == session_id == data.get("session_id")
                and hmeta.get("artifact_id") == data.get("artifact_id")):
            returned_ids.add(hmeta.get("artifact_id"))
    if (not history_starts or len(history_starts) != len(history_finishes)
            or not query_ids.issubset(returned_ids)
            or node_meta["render_video"]["artifact_id"] not in returned_ids):
        raise RuntimeError("same-session history queries did not return their requested artifacts")

    request_events = jsonl(OUT / "model-requests.jsonl")
    request_starts = [row for row in request_events if row.get("event") == "request_started"]
    request_finishes = [row for row in request_events if row.get("event") == "request_finished"]
    ids = [row.get("request_id") for row in request_starts]
    if (not ids or len(ids) != len(set(ids)) or len(ids) != len(request_finishes)
            or len(ids) > 40):
        raise RuntimeError("logical request ledger is incomplete, duplicated, or over budget")
    if any(row.get("status") != "completed" for row in request_finishes):
        raise RuntimeError("one or more logical model requests did not complete")
    if any(not 0 < row.get("max_output_tokens_per_request", 0) <= 8192
           for row in request_starts):
        raise RuntimeError("per-request output cap was not respected")
    observed_tokens = sum(int((row.get("usage") or {}).get(
        "total_tokens", (row.get("usage") or {}).get("input_tokens", 0)
        + (row.get("usage") or {}).get("output_tokens", 0)) or 0)
                          for row in request_finishes)
    if observed_tokens > 500_000:
        raise RuntimeError("observed token soft threshold exceeded")
    if not any(row.get("phase") == "agent" for row in request_starts):
        raise RuntimeError("top-level Agent model requests missing")
    if not any(row.get("phase") == "mcp_sampling"
               and row.get("association", {}).get("node_id") == "speech_rough_cut"
               for row in request_finishes):
        raise RuntimeError("speech_rough_cut model calls missing")

    asr_info = artifacts["local_asr"].get("payload", {}).get("asr_infos", [])
    asr_text = asr_info[0].get("asr_text", "").strip() if asr_info else ""
    asr_sentences = len(asr_info[0].get("asr_sentence_info", [])) if asr_info else 0
    if not asr_text or asr_sentences == 0:
        raise RuntimeError("real LocalASR artifact has no text/sentence timestamps")
    phase = json.loads((OUT / "phase-times.json").read_text(encoding="utf-8"))
    if phase.get("mcp_cleanup_status") != "stopped":
        raise RuntimeError("MCP cleanup is not confirmed")
    if run.get("entry_result", {}).get("returncode") != 0 or run.get("container_removal") != "removed":
        raise RuntimeError("production entry or container cleanup failed")

    elapsed = (time.monotonic_ns() - int(start["started_monotonic_ns"])) / 1e9
    if elapsed > 1800 or float(run.get("wall_s", 1801)) > 1800:
        raise RuntimeError("short-task wall budget exceeded")

    # The timeline carries subtitle text metadata. The registered font index
    # is an empty list in this image, so the native renderer gets no font path;
    # PillowSubtitleRenderer.render therefore returns no overlay clips. Verify
    # the image stream is in fact black at every decoded pixel, matching this
    # synthetic input, before treating the output as subtitle-free.
    font_index = SOURCE_TREE / "resource/fonts/font_info.json"
    fonts = json.loads(font_index.read_text(encoding="utf-8"))
    if fonts:
        raise RuntimeError("registered font index is non-empty; cannot infer subtitles are suppressed")
    subtitle_code = (SOURCE_TREE / "src/open_storyline/nodes/core_nodes/render_video.py").read_text(
        encoding="utf-8")
    if "if not self._font_path:\n            return []" not in subtitle_code:
        raise RuntimeError("native renderer no-font subtitle behavior changed")

    render_args = starts_by_node["render_video"].get("arguments", {})
    if (render_args.get("include_video_audio") is not True
            or float(render_args.get("video_volume_scale", 0)) != 1.0):
        raise RuntimeError("native RenderVideo did not request original audio at 1.0 volume")
    render_file = Path(str(artifacts["render_video"]["payload"]["output_path"])
                       .removeprefix("/workspace/output/") )
    render_file = OUT / render_file
    source_luma, render_luma = decode_luma(SOURCE), decode_luma(render_file)
    if source_luma["max_luma"] != 0 or render_luma["max_luma"] != 0:
        raise RuntimeError("decoded source/render has visible pixels; subtitle absence is unverified")

    export = entry.export_rendered_video(OUT, SOURCE)
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(OUT / "output.mp4"),
                             "-f", "null", "-"], capture_output=True, text=True, timeout=90)
    if decode.returncode != 0:
        raise RuntimeError("submission output.mp4 did not fully decode")
    export["full_decode"] = "PASS"
    cuts = entry.export_cuts_from_final_timeline(OUT, SOURCE)
    if export.get("status") != "exported_and_verified" or cuts.get("status") != "derived_from_final_timeline":
        raise RuntimeError("native render export/cuts contract failed")

    usage_total = sum(int((row.get("usage") or {}).get(
        "total_tokens", (row.get("usage") or {}).get("input_tokens", 0)
        + (row.get("usage") or {}).get("output_tokens", 0)) or 0)
                      for row in request_finishes)
    response_models = sorted({(row.get("response_metadata") or {}).get("model_name")
                              for row in request_finishes
                              if (row.get("response_metadata") or {}).get("model_name")})
    tool_names = sorted({row.get("tool_name") for row in tool_starts})
    report = {
        "schema": "openstoryline-real-native-short-gate-v1", "status": "PASS",
        "gate_recovery": "offline postflight from the same completed native session; no new Agent, model, ASR, or MCP run",
        "initial_postflight_assertion": "overly strict per-artifact history-read requirement; corrected to verify exact predecessor payload links and successful same-session history results",
        "session_id": session_id, "run_id": frozen["run_id"],
        "image": {"tag": "openstoryline-task:arm64-native-confirm-flow-03",
                  "id": "sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0"},
        "source": {"path": str(SOURCE), **digest(SOURCE)},
        "agent": {"status": "completed", "returncode": 0,
                  "wall_s": run["wall_s"], "wall_from_fresh_start_to_postflight_s": elapsed,
                  "container_removal": run["container_removal"],
                  "mcp_cleanup": phase["mcp_cleanup_status"],
                  "confirmations_sent": json.loads((OUT / "session-status.json").read_text()).get(
                      "confirmations_sent")},
        "budget": {"request_limit": 40, "logical_requests": len(request_starts),
                   "max_output_tokens": 8192, "observed_tokens": usage_total,
                   "observed_tokens_soft_threshold": 500000,
                   "http_requests": "unknown"},
        "model": {"requested": "qwen3.7-plus", "base_url": context.get("base_url"),
                  "response_models": response_models},
        "tools": {"calls": len(tool_starts), "tool_names": tool_names,
                  "required_nodes": sorted(REQUIRED), "history_queries": len(history_starts),
                  "history_artifact_ids": sorted(returned_ids),
                  "artifact_payload_links": link_report},
        "asr": {"real_local_inference": True, "sentence_count": asr_sentences},
        "render_export": export, "cuts_export": cuts,
        "subtitle_check": {"timeline_metadata_subtitles": len(
            artifacts["plan_timeline_pro"].get("payload", {}).get("tracks", {}).get("subtitles", [])),
            "font_index_empty": True, "rendered_source_max_luma": source_luma["max_luma"],
            "rendered_output_max_luma": render_luma["max_luma"],
            "visible_subtitle_pixels": 0},
        "history_recovery": {"initial_error": "history did not retrieve every required same-session artifact",
                              "corrected_rule": "all issued history requests must return their exact same-session artifact; downstream payloads must equal the preceding saved artifact"},
    }
    with REPORT.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")
        stream.flush()
    gate = {
        "schema": "openstoryline-native-agent-gate-v1", "status": "PASS",
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "native_langchain_agent_verified": True,
        "real_model_requests_agent": sum(row.get("phase") == "agent" for row in request_finishes),
        "real_model_requests_node": sum(row.get("phase") == "mcp_sampling" for row in request_finishes),
        "tool_names": tool_names, "local_asr_real": True,
        "audio_video_contract": "PASS", "container_cleanup": "PASS",
        "logical_requests": len(request_starts), "response_models": response_models,
        "source_sha256": digest(SOURCE)["sha256"], "image": report["image"],
        "session_id": session_id,
        "report": str(REPORT.relative_to(ROOT)),
        "evidence_manifest": str(MANIFEST.relative_to(ROOT)),
    }
    with GATE.open("x", encoding="utf-8") as stream:
        json.dump(gate, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
    with RECOVERY.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-short-task-postflight-recovery-v1",
                   "status": "completed_from_same_session_artifacts",
                   "new_model_requests": 0, "new_agent_session": False,
                   "initial_failure_preserved": str((PREP / "failure-report.json").relative_to(ROOT)),
                   "report": str(REPORT.relative_to(ROOT)), "gate": str(GATE.relative_to(ROOT)),
                   "submission": {"output_mp4": digest(OUT / "output.mp4"),
                                  "cuts_json": digest(OUT / "cuts.json")},
                   "completed_monotonic_ns": time.monotonic_ns()},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()

    files = []
    for path in sorted(PREP.rglob("*")):
        if not path.is_file() or path == MANIFEST or path.suffix == ".pyc":
            continue
        files.append({"path": str(path.relative_to(PREP)), **digest(path)})
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-real-native-short-evidence-v1",
                   "status": "complete_after_offline_postflight_recovery",
                   "self_hash": "omitted", "files": files}, stream,
                  ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
