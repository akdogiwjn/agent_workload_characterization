#!/usr/bin/env python3
"""Offline recovery of the one formal attempt after a host report permission error.

This script never starts or resumes an Agent. It verifies the saved submission,
verifies container removal, runs the authorized verifier once, and writes reports
from sealed attempt evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path("/home/lcq/agent_workload_characterization")
RUN_ID = "20261022T150133Z-openstoryline-edit-02"
RAW = ROOT / "data/raw/generated/OPENSTORYLINE-EDIT-PILOT-02" / RUN_ID
OUT = RAW / "workspace/output"
REPORT_ROOT = ROOT / "reports/resource/OPENSTORYLINE-EDIT-PILOT-02"
REPORT_PATH = REPORT_ROOT / "run-report.json"
SUMMARY_PATH = REPORT_ROOT / "summary.md"
CURVE_PATH = REPORT_ROOT / "resource-curves.svg"
OCCUPANCY_PATH = REPORT_ROOT / "directory-occupancy.csv"
DELIVERABLE_MANIFEST = REPORT_ROOT / "input-code-output-manifest.json"
RAW_MANIFEST = RAW / "manifest.json"
IDENTITY_PATH = ROOT / "env/video/openstoryline/OPENSTORYLINE-EDIT-PILOT-02/formal/frozen-identity.json"
APPROVAL_PATH = ROOT / "env/video/openstoryline/OPENSTORYLINE-EDIT-PILOT-02/formal/APPROVAL.json"
TASK_INPUT = ROOT / "data/workloads/video/editing/avb-disfluency-interview-3-v1/input/source.mp4"
REPORT_RECOVERY = RAW / "postprocess-recovery.json"

for path in (REPORT_PATH, SUMMARY_PATH, CURVE_PATH, OCCUPANCY_PATH,
             DELIVERABLE_MANIFEST, RAW_MANIFEST, REPORT_RECOVERY):
    if path.exists():
        raise RuntimeError(f"refusing to overwrite existing report/recovery file: {path}")

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
import video_use_edit_pilot_01 as resource_runtime  # noqa: E402
import video_use_edit_pilot_03 as verifier_runtime  # noqa: E402
import openstoryline_pilot_entry as entry  # noqa: E402
from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    ContainerHandle, ContainerSpec, DockerCliRuntime,
)


def digest(path: Path) -> dict:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    recovery_start_ns = time.monotonic_ns()
    identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    raw_request = json.loads((RAW / "request.json").read_text(encoding="utf-8"))
    context = json.loads((OUT / "agent-context.json").read_text(encoding="utf-8"))
    session_id = context["session_id"]
    store = OUT / session_id
    meta = json.loads((store / "meta.json").read_text(encoding="utf-8"))
    samples = read_jsonl(RAW / "resource-samples.jsonl")
    request_events = read_jsonl(OUT / "model-requests.jsonl")
    tool_events = read_jsonl(OUT / "mcp-tool-events.jsonl")
    phases = json.loads((OUT / "phase-times.json").read_text(encoding="utf-8"))
    agent_result = json.loads((OUT / "agent-result.json").read_text(encoding="utf-8"))
    session_status = json.loads((OUT / "session-status.json").read_text(encoding="utf-8"))

    if identity.get("run_id") != RUN_ID or identity.get("identity_sha256") != entry.identity_hash(identity):
        raise RuntimeError("frozen identity does not match the single formal attempt")
    if (approval.get("run_id") != RUN_ID
            or approval.get("frozen_identity_sha256") != hashlib.sha256(IDENTITY_PATH.read_bytes()).hexdigest()):
        raise RuntimeError("formal APPROVAL does not match the frozen identity")
    if raw_request.get("frozen_identity", {}).get("identity_sha256") != identity.get("identity_sha256"):
        raise RuntimeError("container request identity differs from frozen identity")
    if not samples:
        raise RuntimeError("cgroup resource samples are missing")

    container_ids = sorted({row.get("cgroup", {}).get("container_id") for row in samples
                            if row.get("cgroup", {}).get("container_id")})
    if len(container_ids) != 1:
        raise RuntimeError(f"expected one Agent container id in saved samples, found {container_ids}")
    container_id = container_ids[0]
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-EDIT-PILOT-02")
    spec = ContainerSpec(run_id=RUN_ID, scope="openstoryline_agent",
                         image=identity["image"]["tag"], network="none")
    handle = ContainerHandle(container_id=container_id, spec=spec)
    removal = runtime.verify_removal(handle, timeout_s=20)
    if removal == "still_exists":
        runtime.stop(handle, timeout_s=20)
        removal = runtime.verify_removal(handle, timeout_s=20)
    mcp_cleanup = json.loads((OUT / "mcp-cleanup.json").read_text(encoding="utf-8"))
    if removal != "removed" or mcp_cleanup.get("pid_alive") is not False:
        raise RuntimeError(f"formal workload cleanup not confirmed: container={removal}, MCP={mcp_cleanup}")

    output_video = OUT / "output.mp4"
    cuts_path = OUT / "cuts.json"
    if not output_video.is_file() or not cuts_path.is_file():
        raise RuntimeError("official submission output.mp4 or cuts.json is missing")
    render_selection = entry._select_render_artifact(OUT)
    render_row = render_selection["artifact"]
    render_path = entry.resolve_selected_render_media(OUT, render_selection)
    if digest(render_path) != digest(output_video):
        raise RuntimeError("submitted output.mp4 does not match final RenderVideo artifact")

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output_video)],
        capture_output=True, text=True, check=True, timeout=60).stdout)
    streams = probe.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"), None)
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    if (not video or video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p"
            or (int(video.get("width", 0)), int(video.get("height", 0))) != (854, 480)
            or video.get("avg_frame_rate") != "25/1" or not audio or audio.get("codec_name") != "aac"):
        raise RuntimeError("output media contract failed H.264/yuv420p/854x480/25fps/AAC validation")
    source_probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate", "-of", "json", str(TASK_INPUT)],
        capture_output=True, text=True, check=True, timeout=60).stdout)["streams"][0]
    if (video["width"], video["height"], video["avg_frame_rate"]) != (
            source_probe["width"], source_probe["height"], source_probe["avg_frame_rate"]):
        raise RuntimeError("output dimensions/fps differ from registered source")
    if (abs(float(video.get("start_time", 0)) - float(audio.get("start_time", 0))) > 0.1
            or abs(float(video.get("duration", 0)) - float(audio.get("duration", 0))) > 0.1):
        raise RuntimeError("output audio/video is not synchronized within 100ms")
    full_decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output_video),
                                  "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    if full_decode.returncode != 0:
        raise RuntimeError("output.mp4 full decode failed")
    volume = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(output_video),
                            "-vn", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=120)
    if volume.returncode != 0 or "mean_volume: -inf dB" in (volume.stderr or ""):
        raise RuntimeError("output AAC is silent or not decodable")

    cuts = json.loads(cuts_path.read_text(encoding="utf-8"))
    if not isinstance(cuts.get("cuts"), list):
        raise RuntimeError("cuts.json does not match the official top-level cuts list")
    node_meta = {row.get("node_id"): row for row in meta}
    rough = json.loads((store / "speech_rough_cut" /
                        f"{node_meta['speech_rough_cut']['artifact_id']}.json").read_text())['payload']
    timeline = json.loads((store / "plan_timeline_pro" /
                           f"{render_selection['timeline_artifact_id']}.json").read_text())['payload']
    clip_by_path = {os.path.normpath(str(row["path"])): row
                    for row in rough.get("clips", []) if row.get("path")}
    retained = []
    for item in timeline.get("tracks", {}).get("video", []):
        clip = clip_by_path.get(os.path.normpath(str(item.get("source_path", ""))))
        if not clip:
            raise RuntimeError("final timeline clip has no speech_rough_cut provenance")
        window = item.get("source_window") or {}
        start_ms = int(clip["source_ref"]["start"]) + int(window["start"])
        end_ms = int(clip["source_ref"]["start"]) + int(window["end"])
        if end_ms <= start_ms:
            raise RuntimeError("non-positive final timeline source interval")
        retained.append([start_ms, end_ms])
    retained.sort()
    union = []
    for start_ms, end_ms in retained:
        if union and start_ms <= union[-1][1]:
            union[-1][1] = max(union[-1][1], end_ms)
        else:
            union.append([start_ms, end_ms])
    source_duration = round(float(json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(TASK_INPUT)],
        capture_output=True, text=True, check=True, timeout=60).stdout)["format"]["duration"]) * 1000)
    expected_cuts, cursor = [], 0
    for start_ms, end_ms in union:
        if start_ms > cursor:
            expected_cuts.append({"start_ms": cursor, "end_ms": start_ms,
                                  "reason": "outside_final_rendered_source_intervals"})
        cursor = max(cursor, end_ms)
    if cursor < source_duration:
        expected_cuts.append({"start_ms": cursor, "end_ms": source_duration,
                              "reason": "outside_final_rendered_source_intervals"})
    if cuts["cuts"] != expected_cuts:
        raise RuntimeError("cuts.json is not the complement of final rendered timeline source intervals")

    request_starts = [row for row in request_events if row.get("event") == "request_started"]
    request_finishes = [row for row in request_events if row.get("event") == "request_finished"]
    request_ids = {row.get("request_id") for row in request_starts}
    finished_ids = {row.get("request_id") for row in request_finishes}
    usage_totals = {}
    for row in request_finishes:
        usage = row.get("usage") or {}
        for key, value in usage.items():
            try:
                usage_totals[key] = usage_totals.get(key, 0) + int(value or 0)
            except (TypeError, ValueError):
                pass
    observed_tokens = usage_totals.get("total_tokens", usage_totals.get("input_tokens", 0)
                                       + usage_totals.get("output_tokens", 0))
    if len(request_starts) > 60 or observed_tokens > 1_000_000:
        raise RuntimeError("formal logical-request or observed-usage budget exceeded")
    if any(not 0 < row.get("max_output_tokens_per_request", 0) <= 32768
           for row in request_starts):
        raise RuntimeError("formal per-request output-token cap exceeded or missing")
    tool_starts = [row for row in tool_events if row.get("event") == "tool_call_started"]
    tool_finishes = [row for row in tool_events if row.get("event") == "tool_call_finished"]
    tool_errors = [row for row in tool_finishes if row.get("is_error")]
    per_tool = {}
    for row in tool_starts:
        per_tool.setdefault(str(row.get("node_id") or row.get("tool_name")), {"started": 0, "finished": 0, "errors": 0})
        per_tool[str(row.get("node_id") or row.get("tool_name"))]["started"] += 1
    for row in tool_finishes:
        per_tool.setdefault(str(row.get("node_id") or row.get("tool_name")), {"started": 0, "finished": 0, "errors": 0})
        per_tool[str(row.get("node_id") or row.get("tool_name"))]["finished"] += 1
        per_tool[str(row.get("node_id") or row.get("tool_name"))]["errors"] += int(bool(row.get("is_error")))
    if request_ids - finished_ids:
        request_completion = "partial; one or more logical requests lack a finish event"
    else:
        request_completion = "all started request IDs have a finish event"
    if len(request_ids) != len(request_starts):
        raise RuntimeError("duplicate logical request IDs")

    sample_start_ns = samples[0]["t_monotonic_ns"]
    sample_end_ns = samples[-1]["t_monotonic_ns"]
    sample_intervals = [(b["t_monotonic_ns"] - a["t_monotonic_ns"]) / 1e9
                        for a, b in zip(samples, samples[1:])]
    cgroup_samples = [row for row in samples if (row.get("cgroup") or {}).get("scope_kind") == "agent_container"]
    resource_metrics = resource_runtime.resource_metrics(samples)
    net_summary = resource_runtime.network_summary(samples)
    resource_roles = {}
    for row in samples:
        resource_roles[row.get("role", "unknown")] = resource_roles.get(row.get("role", "unknown"), 0) + 1
    gaps = []
    for index, interval in enumerate(sample_intervals):
        if interval > 1.5:
            gaps.append({"after_sample_index": index, "duration_s": interval})

    phase_start = int(phases["agent_initialized_monotonic_ns"])
    phase_end = int(phases["agent_finished_monotonic_ns"])
    agent_work_s = (phase_end - phase_start) / 1e9
    if agent_work_s > 1800:
        raise RuntimeError("recorded Agent work phase exceeded 1800s")
    elapsed_from_agent_context_s = (time.monotonic_ns() - int(context["started_monotonic_ns"])) / 1e9
    total_budget_remaining_estimate = max(0, 2700 - elapsed_from_agent_context_s - 300)
    verifier_budget = min(580, total_budget_remaining_estimate)
    if verifier_budget < 1:
        raise RuntimeError("insufficient remaining total budget for the one verifier pass")

    # Exactly one official verifier invocation, isolated from the former Agent container.
    if (RAW / "verifier_private").exists():
        raise RuntimeError("verifier_private already exists; refusing a duplicate judge run")
    verifier_runtime.runner.RAW_ROOT = RAW
    verifier_runtime.runner.INPUT = TASK_INPUT
    judge_resource_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    verifier_begin = time.monotonic()
    verifier = verifier_runtime.isolated_run_verifier(
        {"run_id": RUN_ID, "phases": [{"phase": "agent", "returncode": None,
                                       "timed_out": False,
                                       "start_monotonic_ns": phase_start,
                                       "end_monotonic_ns": phase_end}]},
        remaining=verifier_budget)
    verifier_wall_s = time.monotonic() - verifier_begin
    judge_resource_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    verifier_host_usage = {
        "scope": "host child-process usage for the isolated verifier wrapper; separate from Agent cgroup",
        "cpu_user_s_delta": max(0.0, judge_resource_after.ru_utime - judge_resource_before.ru_utime),
        "cpu_system_s_delta": max(0.0, judge_resource_after.ru_stime - judge_resource_before.ru_stime),
        "maxrss_kib_highwater_after": judge_resource_after.ru_maxrss,
        "memory_sampling_scope": "child high-water, not a periodic RSS trace",
    }

    # The attempt start_ns was held only in the failed host process and was not persisted.
    # Report the exact cgroup boundary window and Agent phase; do not substitute a guessed start.
    boundary_window_s = (sample_end_ns - sample_start_ns) / 1e9
    report = {
        "schema": "openstoryline-edit-pilot-02-run-report-v1",
        "report_recovery": {"status": "offline_reconstructed_after_host_postprocess_permission_error",
                            "agent_rerun": False, "judge_runs": 1,
                            "raw_agent_result_modified": False,
                            "host_error": "PermissionError writing container-owned agent-result.json (uid nobody); report not persisted by original entry",
                            "exact_attempt_start_monotonic_ns": None,
                            "attempt_wall_semantics": "exact host start was not persisted; cgroup boundary and Agent phase windows retained"},
        "namespace": "OPENSTORYLINE-EDIT-PILOT-02", "run_id": RUN_ID, "attempt": 1,
        "approval_id": approval.get("approval_id"),
        "frozen_identity_sha256": identity["identity_sha256"],
        "image": identity["image"], "model_route": identity["model_route"],
        "budget": identity["budget"], "wall_limits_s": identity["wall_limits_s"],
        "source": {"path": str(TASK_INPUT.relative_to(ROOT)), **digest(TASK_INPUT)},
        "task_instruction": identity.get("task_instruction"),
        "agent": {"container_id": container_id, "returncode": "unknown_not_persisted",
                  "native_agent_result_file_status": agent_result.get("status"),
                  "task_entry_phase_end_monotonic_ns": phase_end,
                  "work_s": agent_work_s,
                  "termination_reason": "container execution returned to host; raw exit code lost when postprocess raised PermissionError",
                  "agent_work_limit_s": 1800},
        "task_result": {"submission_exists": True, "output_mp4": digest(output_video),
                        "cuts_json": digest(cuts_path), "render_artifact_id": render_row["artifact_id"],
                        "render_artifact_matches_submission": True,
                        "render_artifact_path": str(render_path.relative_to(OUT)),
                        "render_artifact_sha256": digest(render_path)["sha256"],
                        "render_selection_basis": render_selection["selection_basis"],
                        "render_tool_call_id": render_selection["tool_call_id"],
                        "timeline_artifact_id": render_selection["timeline_artifact_id"],
                        "timeline_payload_sha256": render_selection["timeline_payload_sha256"],
                        "cuts_derived_from_final_timeline": True,
                        "rendered_source_intervals_ms": union,
                        "cut_count": len(cuts["cuts"]),
                        "media": {"video_codec": video.get("codec_name"),
                                  "pixel_format": video.get("pix_fmt"), "width": video.get("width"),
                                  "height": video.get("height"), "fps": video.get("avg_frame_rate"),
                                  "audio_codec": audio.get("codec_name"),
                                  "audio_sample_rate": audio.get("sample_rate"),
                                  "audio_video_start_delta_s": abs(float(video.get("start_time",0))-float(audio.get("start_time",0))),
                                  "audio_video_duration_delta_s": abs(float(video.get("duration",0))-float(audio.get("duration",0))),
                                  "audio_non_silent": True, "full_decode": "PASS"}},
        "verifier": {**verifier, "wall_s": verifier_wall_s,
                     "budget_limit_s": 600, "passed_timeout_s": verifier_budget,
                     "host_resource_usage": verifier_host_usage},
        "measurement": {"scope": "Agent container cgroup including MCP, local ASR, FFmpeg children",
                         "cgroup_version": (cgroup_samples[0].get("cgroup") or {}).get("cgroup_version"),
                         "sample_count_total": len(samples), "sample_roles": resource_roles,
                         "sample_interval_target_s": 0.5,
                         "sample_interval_median_s": sorted(sample_intervals)[len(sample_intervals)//2] if sample_intervals else None,
                         "sample_interval_min_s": min(sample_intervals) if sample_intervals else None,
                         "sample_interval_max_s": max(sample_intervals) if sample_intervals else None,
                         "sample_window_monotonic_ns": [sample_start_ns, sample_end_ns],
                         "long_gaps_over_1_5s": gaps,
                         "resource_metrics": resource_metrics,
                         "network": net_summary,
                         "directory_occupancy": "before exact du values were held in memory and lost; after values recorded in directory-occupancy.csv; no invented baseline"},
        "phases": [{"phase": "mcp_start_to_ready", "start_monotonic_ns": phases.get("mcp_start_monotonic_ns"),
                    "end_monotonic_ns": phases.get("mcp_ready_monotonic_ns"),
                    "wall_s": (phases.get("mcp_ready_monotonic_ns",0)-phases.get("mcp_start_monotonic_ns",0))/1e9},
                   {"phase": "agent_initialization_after_mcp_ready",
                    "start_monotonic_ns": phases.get("mcp_ready_monotonic_ns"),
                    "end_monotonic_ns": phases.get("agent_initialized_monotonic_ns"),
                    "wall_s": (phases.get("agent_initialized_monotonic_ns",0)-phases.get("mcp_ready_monotonic_ns",0))/1e9},
                   {"phase": "agent_work", "start_monotonic_ns": phase_start,
                    "end_monotonic_ns": phase_end, "wall_s": agent_work_s},
                   {"phase": "verifier", "wall_s": verifier_wall_s,
                    "scope": "independent host verifier; not Agent cgroup"}],
        "request_observation": {"logical_requests_started": len(request_starts),
                                "logical_requests_finished": len(request_finishes),
                                "request_completion": request_completion,
                                "unfinished_request_ids": sorted(request_ids-finished_ids),
                                "by_phase": {phase: {
                                    "started": sum(row.get("event")=="request_started" and row.get("phase")==phase for row in request_events),
                                    "finished": sum(row.get("event")=="request_finished" and row.get("phase")==phase for row in request_events)}
                                    for phase in sorted({str(row.get("phase")) for row in request_events if row.get("phase")})},
                                "observed_usage_raw_field_totals": usage_totals,
                                "observed_tokens": observed_tokens,
                                "http_requests": "unknown; no reliable HTTP-layer evidence",
                                "response_models": sorted({(row.get("response_metadata") or {}).get("model_name")
                                                            for row in request_finishes
                                                            if (row.get("response_metadata") or {}).get("model_name")})},
        "tool_observation": {"calls_started": len(tool_starts), "calls_finished": len(tool_finishes),
                             "tool_errors": len(tool_errors), "by_node": per_tool,
                             "artifact_session_id": session_id,
                             "history_calls": sum(row.get("node_id")=="read_node_history" and row.get("event")=="tool_call_started" for row in tool_events)},
        "cleanup": {"container_removal": removal, "mcp_cleanup": phases.get("mcp_cleanup_status"),
                    "mcp_cleanup_record": mcp_cleanup, "image_retained": True,
                    "model_cache_retained": True},
        "assessment_columns": {"measurement_integrity": "raw samples and request/tool events present; exact host attempt start and agent return code missing from failed report write",
                               "official_task_result": {"evaluation_status": verifier.get("evaluation_status"),
                                                        "evaluation_complete": verifier.get("evaluation_complete"),
                                                        "reward": verifier.get("reward")},
                               "agent_termination": "Agent phase ended; exact process returncode unknown; native result file remains unmodified at executing",
                               "infrastructure_and_archive": "container removed, MCP stopped; host postprocess had PermissionError; report/manifest recovered offline"},
    }

    # Compute host-side final directory boundaries without rewriting raw files.
    paths = {"input": ROOT / "data/workloads/video/editing/avb-disfluency-interview-3-v1/input",
             "work": RAW / "workspace/project", "submission": OUT}
    boundaries = []
    for name, path in paths.items():
        result = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True)
        size = int(result.stdout.split()[0]) if result.returncode == 0 and result.stdout.split() else None
        boundaries.append({"directory": name, "path": str(path.relative_to(ROOT)),
                           "before_bytes": None, "before_status": "not persisted by failed host report",
                           "after_bytes": size, "after_status": "measured during offline recovery"})
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    with OCCUPANCY_PATH.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(boundaries[0]))
        writer.writeheader(); writer.writerows(boundaries)

    # Reuse the project's four-panel SVG renderer, then write this task's own Chinese summary.
    resource_runtime.REPORT_ROOT = REPORT_ROOT
    report_for_plot = {"sampler_rows": samples, "net_summary": net_summary,
                       "resource_metrics": resource_metrics,
                       "phases": report["phases"], "verifier": verifier,
                       "removal_verification": removal}
    resource_runtime.write_resource_report(report_for_plot)
    # Replace only the new, task-specific report prose that helper rendered for its own pilot.
    REPORT_ROOT.joinpath("summary.md").write_text(
        "# OPENSTORYLINE-EDIT-PILOT-02 执行与离线恢复报告\n\n"
        f"- run_id：`{RUN_ID}`，唯一attempt；冻结身份 SHA-256 `{identity['identity_sha256']}`。\n"
        f"- 正式模型：`qwen3.7-plus`，Chat Completions；逻辑请求 {len(request_starts)} 次开始、{len(request_finishes)} 次结束；observed tokens {observed_tokens}；HTTP次数和账单 unknown。\n"
        f"- Agent实际工作 {agent_work_s:.2f}s / 1800s；本地ASR、原生工具与最终render完成。原始日志保留首次RenderVideo错误“timeline result has no video track”以及随后Agent查询history、重规划并成功渲染的恢复。\n"
        f"- 提交输出：854×480、25fps、H.264/yuv420p、AAC、音视频同步、非静音，完整解码通过。`output.mp4` 与最终RenderVideo artifact SHA-256一致；`cuts.json`按最终timeline源区间补集生成。\n"
        f"- Judge：状态 `{verifier.get('evaluation_status')}`，完整性 `{verifier.get('evaluation_complete')}`，reward `{verifier.get('reward')}`；进程返回码 `{verifier.get('returncode')}`，wrapper返回码 `{verifier.get('wrapper_returncode')}`。\n"
        f"- 资源scope：Agent容器cgroup v{(cgroup_samples[0].get('cgroup') or {}).get('cgroup_version')}，{len(samples)}点，目标0.5s，实测中位间隔 {report['measurement']['sample_interval_median_s']:.3f}s；netns按接口报告，不归因为API流量。Verifier资源单列。\n"
        f"- 清理：容器 `{removal}`，MCP `{phases.get('mcp_cleanup_status')}`；镜像与模型缓存保留。原入口未能写报告，原因是宿主更新容器uid=nobody文件时PermissionError；未改写原始agent-result、消息、请求或工具日志。\n"
        "- 完整attempt起点和Agent进程返回码未被原入口持久化；报告保留为unknown。目录占用初始精确du值未保存，不回填；见目录占用表。\n\n"
        "图表：`resource-curves.svg`（CPU、内存、磁盘I/O、网络四面板，真实采样，缺口断开）。原始采样：raw `resource-samples.csv`；请求、工具、消息与MCP事件位于raw `workspace/output/`。\n",
        encoding="utf-8")
    report["directory_boundaries"] = boundaries
    report["resource_curve"] = str(CURVE_PATH.relative_to(ROOT))
    report["raw_resource_points_csv"] = str((RAW / "resource-samples.csv").relative_to(ROOT))
    report["deliverables_manifest"] = str(DELIVERABLE_MANIFEST.relative_to(ROOT))
    write_exclusive(REPORT_PATH, report)

    code_files = []
    for rel, value in identity.get("files", {}).items():
        code_files.append({"path": rel, **value})
    deliverables = [
        {"role": "input", "path": str(TASK_INPUT.relative_to(ROOT)), **digest(TASK_INPUT)},
        {"role": "submission_video", "path": str(output_video.relative_to(ROOT)), **digest(output_video)},
        {"role": "cuts", "path": str(cuts_path.relative_to(ROOT)), **digest(cuts_path)},
        {"role": "final_render_artifact", "path": str(render_path.relative_to(ROOT)), **digest(render_path)},
    ]
    with DELIVERABLE_MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-edit-pilot-02-input-code-output-manifest-v1",
                   "identity_sha256": identity["identity_sha256"],
                   "input_and_outputs": deliverables, "frozen_code_files": code_files},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()

    recovery = {"schema": "openstoryline-edit-pilot-02-postprocess-recovery-v1",
                "status": "complete_offline_report_recovery",
                "cause": "PermissionError updating container-owned agent-result.json after output export; original raw file preserved",
                "agent_rerun": False, "judge_invocations_this_recovery": 1,
                "judge_result": verifier.get("evaluation_status"),
                "container_id": container_id, "container_removal": removal,
                "new_files": [str(REPORT_PATH.relative_to(ROOT)), str(SUMMARY_PATH.relative_to(ROOT)),
                              str(CURVE_PATH.relative_to(ROOT)), str(OCCUPANCY_PATH.relative_to(ROOT)),
                              str(DELIVERABLE_MANIFEST.relative_to(ROOT))],
                "recovered_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "recovery_wall_s": (time.monotonic_ns()-recovery_start_ns)/1e9}
    write_exclusive(REPORT_RECOVERY, recovery)

    files = []
    for path in sorted(RAW.rglob("*")):
        if not path.is_file() or path == RAW_MANIFEST or path.suffix == ".pyc":
            continue
        files.append({"path": str(path.relative_to(RAW)), **digest(path)})
    with RAW_MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-attempt-manifest-v1",
                   "recovered_offline": True, "self_hash": "omitted", "files": files},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
    print(json.dumps({"run_id": RUN_ID, "verifier": verifier,
                      "container_removal": removal, "report": str(REPORT_PATH),
                      "summary": str(SUMMARY_PATH), "manifest_files": len(files)},
                     ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
