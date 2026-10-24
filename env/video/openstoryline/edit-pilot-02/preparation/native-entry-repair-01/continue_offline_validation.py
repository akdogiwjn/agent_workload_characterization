#!/usr/bin/env python3
"""Continue the same persisted offline test session without rerunning ASR."""
from __future__ import annotations

import hashlib
import json
import shutil
import shlex
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
REPAIR = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
OUT = REPAIR / "validation-03"
OUTPUT = OUT / "output"
SOURCE = OUT / "input/source.mp4"
IMAGE = "openstoryline-task:arm64-native-entry-repair-07"
IMAGE_ID_FILE = REPAIR / "image-identity-07.json"
sys.path.insert(0, str(REPAIR))
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
sys.path.insert(0, str(ROOT / "src"))
import run_offline_validation as validation  # noqa: E402
import openstoryline_pilot_entry as entry  # noqa: E402
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime  # noqa: E402


def main() -> int:
    continuation = OUTPUT / "continuation-06"
    request_path = OUT / "continuation-request-06.json"
    run_path = OUT / "continuation-run-06.json"
    if continuation.exists() or request_path.exists() or run_path.exists():
        raise RuntimeError("refusing to overwrite existing continuation evidence")
    context = json.loads((OUTPUT / "agent-context.json").read_text(encoding="utf-8"))
    session_id = str(context["session_id"])
    identity = json.loads(IMAGE_ID_FILE.read_text(encoding="utf-8"))
    entry.IMAGE = IMAGE
    entry.IMAGE_ID = identity["id"]
    budget = {"max_logical_requests": 24,
              "max_observed_tokens_soft_threshold": 100000,
              "max_output_tokens_per_request": 8192}
    frozen_identity = {"schema": "offline-native-entry-continuation-v1",
                       "run_id": f"offline-resume-{uuid.uuid4().hex}", "budget": budget}
    frozen_identity["identity_sha256"] = entry.identity_hash(frozen_identity)
    request = {
        "output_dir": "/workspace/output/continuation-06",
        "instruction": "继续使用本会话已保存的ASR和工具历史，完成粗剪、时间线、原生渲染和导出。",
        "lang": "zh", "session_id": session_id, "recursion_limit": 24,
        "budget": budget, "frozen_identity": frozen_identity,
        "offline_fake_model": True, "offline_fake_model_start_at": "speech_rough_cut",
    }
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    deadline = time.monotonic() + 900
    spec = entry.build_container_spec(
        run_id="native-entry-repair-continue-06", output_dir=OUTPUT,
        request_path=request_path, api_key=None, run_deadline=deadline,
        input_dir=OUT / "input", network="none", offline_fake_model=True)
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-NATIVE-ENTRY-REPAIR-01")
    handle = None
    record = {"image": {"tag": IMAGE, "id": identity["id"]},
              "same_session_id": session_id, "asr_reexecuted": False,
              "network": spec.network, "env_names": sorted(spec.env)}
    try:
        handle = runtime.start(spec, deadline=deadline)
        record["container_id"] = handle.container_id
        result = runtime.execute(
            handle,
            "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json",
            timeout_s=max(1, min(720, int(deadline - time.monotonic()))), output_limit=2_000_000)
        record["entry_result"] = result
        if result.get("returncode") != 0:
            raise RuntimeError(f"continuation entry failed: {result.get('output', '')[-5000:]}")
        existing_metas = json.loads((OUTPUT / session_id / "meta.json").read_text(encoding="utf-8"))
        load_artifact = next(row["artifact_id"] for row in existing_metas
                             if row.get("node_id") == "load_media")
        probe_code = (
            "from open_storyline.storage.agent_memory import ArtifactStore; "
            "import sys; store=ArtifactStore('/workspace/output','offline-session-mismatch-probe'); "
            "meta,_=store.load_result(sys.argv[1]); assert meta is None, meta"
        )
        probe_command = ("/opt/openstoryline-venv/bin/python -c " + shlex.quote(probe_code)
                         + " " + shlex.quote(load_artifact))
        probe = runtime.execute(handle, probe_command, timeout_s=30, output_limit=2000)
        record["session_mismatch_probe"] = probe
        if probe.get("returncode") != 0:
            raise RuntimeError(f"cross-session artifact lookup unexpectedly succeeded: {probe}")
    except BaseException as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:1200]}
        raise
    finally:
        if handle:
            try:
                runtime.stop(handle, timeout_s=30)
                record["container_removal"] = runtime.verify_removal(handle, timeout_s=20)
            except Exception as exc:
                record["container_removal"] = f"check_failed:{type(exc).__name__}:{exc}"
        record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        run_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")

    result = json.loads((continuation / "agent-result.json").read_text(encoding="utf-8"))
    validation.assert_true(result.get("status") == "completed", f"continuation agent failed: {result}")
    phase = json.loads((continuation / "phase-times.json").read_text(encoding="utf-8"))
    validation.assert_true(phase.get("mcp_cleanup_status") == "stopped", "continuation MCP did not stop")
    continuation_model_events = validation.read_jsonl(continuation / "model-requests.jsonl")
    initial_messages = json.loads((OUTPUT / "native-messages.json").read_text(encoding="utf-8"))
    system_contents = [str(message.get("content", "")) for message in initial_messages
                       if message.get("type") == "system"]
    validation.assert_true(any("视频剪辑助理" in text for text in system_contents),
                           "official instruction system message missing")
    validation.assert_true(any("User media upload status" in text for text in system_contents),
                           "official media overview system message missing")

    store_dir = OUTPUT / session_id
    metas = json.loads((store_dir / "meta.json").read_text(encoding="utf-8"))
    records = {}
    for meta in metas:
        path = store_dir / meta["node_id"] / f"{meta['artifact_id']}.json"
        if path.is_file():
            records.setdefault(meta["node_id"], []).append(json.loads(path.read_text(encoding="utf-8")))
    for node in ("load_media", "split_shots", "local_asr", "speech_rough_cut",
                 "plan_timeline_pro", "render_video"):
        validation.assert_true(records.get(node), f"final session has no artifact for {node}")
    load_record = records["load_media"][0]
    split_record = records["split_shots"][0]
    asr_record = records["local_asr"][0]
    rough_record = next((row for row in reversed(records["speech_rough_cut"])
                         if row.get("payload", {}).get("clips")), None)
    plan_record = next((row for row in reversed(records["plan_timeline_pro"])
                        if row.get("payload", {}).get("tracks", {}).get("video")), None)
    render_record = next((row for row in reversed(records["render_video"])
                          if row.get("payload", {}).get("output_path")), None)
    validation.assert_true(load_record["payload"].get("media"), "load_media did not index input")
    validation.assert_true(split_record["payload"].get("clips"), "split_shots did not return clips")
    infos = asr_record["payload"].get("asr_infos", [])
    validation.assert_true(infos and infos[0].get("asr_text", "").strip(), "actual local ASR text missing")
    validation.assert_true(infos[0].get("asr_sentence_info"), "actual ASR timestamps missing")
    validation.assert_true(rough_record is not None, "speech_rough_cut did not consume saved ASR")
    validation.assert_true(plan_record is not None, "PlanTimelinePro did not consume rough cut")
    validation.assert_true(render_record is not None, "native RenderVideo did not produce an artifact")

    first_events = validation.read_jsonl(OUTPUT / "mcp-tool-events.jsonl")
    prior_resume_events = validation.read_jsonl(OUTPUT / "continuation-02/mcp-tool-events.jsonl")
    timeline_resume_events = validation.read_jsonl(OUTPUT / "continuation-03/mcp-tool-events.jsonl")
    prior_render_events = validation.read_jsonl(OUTPUT / "continuation-04/mcp-tool-events.jsonl")
    previous_final_events = validation.read_jsonl(OUTPUT / "continuation-05/mcp-tool-events.jsonl")
    resume_events = validation.read_jsonl(continuation / "mcp-tool-events.jsonl")
    all_events = (first_events + prior_resume_events + timeline_resume_events
                  + prior_render_events + previous_final_events + resume_events)
    starts = [row for row in all_events if row.get("event") == "tool_call_started"]
    finishes = [row for row in all_events if row.get("event") == "tool_call_finished"]
    expected_payloads = {
        "load_media": load_record,
        "split_shots": split_record,
        "local_asr": asr_record,
        "speech_rough_cut": rough_record,
        "plan_timeline_pro": plan_record,
        "render_video": render_record,
    }
    for node, artifact in expected_payloads.items():
        validation.assert_true(any(row.get("node_id") == node for row in starts),
                               f"no native MCP invocation recorded for {node}")
        validation.assert_true(any(row.get("node_id") == node and not row.get("is_error")
                                   and row.get("artifact_id") == artifact["artifact_id"]
                                   for row in finishes), f"no successful result for {node}")
    rough_event = next(row for row in starts if row.get("node_id") == "speech_rough_cut"
                       and row.get("arguments", {}).get("asr", {}).get("asr_infos"))
    plan_event = next(row for row in starts if row.get("node_id") == "plan_timeline_pro"
                      and row.get("arguments", {}).get("speech_rough_cut", {}).get("clips"))
    validation.assert_true(rough_event["arguments"]["asr"]["asr_infos"],
                           "same-session persisted ASR payload was not injected")
    validation.assert_true(plan_event["arguments"]["speech_rough_cut"]["clips"],
                           "same-session rough-cut payload was not injected")

    history_queries = {row.get("arguments", {}).get("query_artifact_id") for row in starts
                       if row.get("node_id") == "read_node_history"}
    for artifact in expected_payloads.values():
        validation.assert_true(artifact["artifact_id"] in history_queries,
                               f"read_node_history did not query {artifact['artifact_id']}")
        history_start = next(row for row in starts if row.get("node_id") == "read_node_history"
                             and row.get("arguments", {}).get("query_artifact_id") == artifact["artifact_id"])
        history_result = next(row for row in finishes
                              if row.get("node_id") == "read_node_history"
                              and row.get("tool_call_id") == history_start.get("tool_call_id"))
        history_data = (history_result.get("returned_payload", {}).get("history", {})
                        .get("node_data", {}))
        validation.assert_true(history_data.get("artifact_id") == artifact["artifact_id"]
                               and history_data.get("payload") == artifact["payload"],
                               f"history returned a different payload for {artifact['artifact_id']}")
    render_event = next(row for row in starts if row.get("node_id") == "render_video"
                        and row.get("artifact_id") == render_record["artifact_id"])
    validation.assert_true(render_event.get("arguments", {}).get("include_video_audio") is True,
                           "render did not explicitly include source audio")
    validation.assert_true(render_event.get("arguments", {}).get("video_volume_scale") == 1.0,
                           "render did not explicitly include source audio at unity volume")
    validation.assert_true(render_event.get("arguments", {}).get("output_max_dimension_px") == 320,
                           "render did not explicitly preserve the test source canvas")
    validation.assert_true(record.get("session_mismatch_probe", {}).get("returncode") == 0,
                           "cross-session artifact lookup was not rejected")

    first_requests = validation.read_jsonl(OUTPUT / "model-requests.jsonl")
    prior_resume_requests = validation.read_jsonl(OUTPUT / "continuation-02/model-requests.jsonl")
    timeline_resume_requests = validation.read_jsonl(OUTPUT / "continuation-03/model-requests.jsonl")
    prior_render_requests = validation.read_jsonl(OUTPUT / "continuation-04/model-requests.jsonl")
    previous_final_requests = validation.read_jsonl(OUTPUT / "continuation-05/model-requests.jsonl")
    resume_requests = validation.read_jsonl(continuation / "model-requests.jsonl")
    request_events = (first_requests + prior_resume_requests + timeline_resume_requests
                      + prior_render_requests + previous_final_requests + resume_requests)
    logical = [row for row in request_events if row.get("event") == "request_started"]
    fake = (validation.read_jsonl(OUTPUT / "fake-model-requests.jsonl")
            + validation.read_jsonl(OUTPUT / "continuation-02/fake-model-requests.jsonl")
            + validation.read_jsonl(OUTPUT / "continuation-03/fake-model-requests.jsonl")
            + validation.read_jsonl(OUTPUT / "continuation-04/fake-model-requests.jsonl")
            + validation.read_jsonl(OUTPUT / "continuation-05/fake-model-requests.jsonl")
            + validation.read_jsonl(continuation / "fake-model-requests.jsonl"))
    per_run_logical = [sum(row.get("event") == "request_started"
                           for row in validation.read_jsonl(folder / "model-requests.jsonl"))
                       for folder in (OUTPUT, OUTPUT / "continuation-02", OUTPUT / "continuation-03",
                                      OUTPUT / "continuation-04", OUTPUT / "continuation-05", continuation)]
    validation.assert_true(all(0 < count <= 24 for count in per_run_logical),
                           f"a preparation session exceeded its 24-request cap: {per_run_logical}")
    fresh_fake = validation.read_jsonl(continuation / "fake-model-requests.jsonl")
    fresh_logical = [row for row in resume_requests if row.get("event") == "request_started"]
    validation.assert_true(len(fresh_logical) == len(fresh_fake),
                           f"final continuation logical/fake counts differ: {len(fresh_logical)} vs {len(fresh_fake)}")
    intervals = {}
    for event in resume_requests:
        request_id = event.get("request_id")
        if not request_id:
            continue
        intervals.setdefault(request_id, {})[event.get("event")] = event
    matched_fake_ids = set()
    for exchange in fresh_fake:
        sent_ns = exchange.get("observed_monotonic_ns")
        matches = [request_id for request_id, pair in intervals.items()
                   if pair.get("request_started", {}).get("started_monotonic_ns", 0) <= sent_ns
                   and pair.get("request_finished", {}).get("finished_monotonic_ns", 0) >= sent_ns]
        validation.assert_true(len(matches) == 1,
                               f"fake exchange did not map to one logical request interval: {exchange}")
        matched_fake_ids.add(matches[0])
    sampling = [row for row in request_events
                if row.get("event") == "request_finished" and row.get("phase") == "mcp_sampling"]
    validation.assert_true(sampling and all(
        row.get("association", {}).get("node_id") == "speech_rough_cut"
        and row.get("association", {}).get("session_id") == session_id for row in sampling),
        "speech rough-cut model requests are not associated with node/session")

    # Missing final render bytes must fail instead of fabricating a submission.
    with tempfile.TemporaryDirectory() as tmp:
        fake_output = Path(tmp)
        fake_session = "missing-render-session"
        fake_artifact_id = "render-without-file"
        render_dir = fake_output / fake_session / "render_video"
        render_dir.mkdir(parents=True)
        missing_path = fake_output / ".server_cache" / fake_session / fake_artifact_id / "missing.mp4"
        (fake_output / "agent-context.json").write_text(json.dumps({"session_id": fake_session}))
        (render_dir / f"{fake_artifact_id}.json").write_text(json.dumps({
            "node_id": "render_video", "artifact_id": fake_artifact_id,
            "payload": {"output_path": str(missing_path)}, "create_time": 1,
        }))
        try:
            entry.export_rendered_video(fake_output, SOURCE)
        except RuntimeError as exc:
            validation.assert_true("missing or outside" in str(exc),
                                   f"unexpected missing-render error: {exc}")
        else:
            raise AssertionError("missing final render artifact was accepted")

    exported = entry.export_rendered_video(OUTPUT, SOURCE)
    cuts = entry.export_cuts_from_final_timeline(OUTPUT, SOURCE)
    validation.assert_true(exported["source"] == exported["submission"], "render/export hash mismatch")
    validation.assert_true(exported["video"]["codec"] == "h264"
                           and exported["video"]["pixel_format"] == "yuv420p",
                           "video output codec/pixel format mismatch")
    validation.assert_true(exported["audio"]["codec"] == "aac" and exported["audio"]["non_silent"],
                           "non-silent AAC source audio missing")
    validation.assert_true(exported["status"] == "exported_and_verified", "output export failed")
    validation.assert_true(cuts["status"] == "derived_from_final_timeline", "cuts are not from final timeline")
    validation.assert_true(exported["video"]["width"] == 320 and exported["video"]["height"] == 240
                           and exported["video"]["fps"] == "25/1",
                           "short validation render did not preserve its input canvas/rate")

    report = {
        "status": "PASS_fake_model_real_mcp_local_compute",
        "model_boundary": "container-local fake Chat Completions; no real API/key access",
        "resumption": {"same_session_id": session_id, "asr_executions": 1,
                       "second_entry_reused_saved_asr": True},
        "real_components": ["production openstoryline_task_entry", "native LangChain Agent",
                            "MCP public schema/transport", "native interceptors/ArtifactStore/history",
                            "LocalASRNode", "SpeechRoughCutNode local segment processing",
                            "PlanTimelinePro", "RenderVideo", "submission export"],
        "session_id": session_id,
        "artifacts": {node: artifact["artifact_id"] for node, artifact in expected_payloads.items()},
        "logical_requests": len(logical), "fake_transport_exchanges": len(fake),
        "final_continuation_logical_requests": len(fresh_logical),
        "final_continuation_fake_exchanges": len(fresh_fake),
        "final_continuation_fake_exchanges_matched_to_logical_request_ids": len(matched_fake_ids),
        "historical_ledger_note": "Earlier continuation logs are preserved; before callback-scope repair, MCP sampling also propagated to the Agent recorder and produced duplicate overlapping rows.",
        "mcp_calls": len(starts), "history_queries": len(history_queries),
        "render_export": exported, "cuts_export": cuts,
        "initial_mcp_cleanup": json.loads((OUTPUT / "phase-times.json").read_text()).get("mcp_cleanup_status"),
        "continuation_mcp_cleanup": phase.get("mcp_cleanup_status"),
        "initial_container_removal": json.loads((OUT / "container-run.json").read_text()).get("container_removal"),
        "continuation_container_removal": record.get("container_removal"),
    }
    (OUT / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
