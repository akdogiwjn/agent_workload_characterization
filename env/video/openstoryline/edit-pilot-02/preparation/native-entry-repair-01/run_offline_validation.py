#!/usr/bin/env python3
"""Run one isolated fake-model / real-MCP production-entry validation."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
REPAIR = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
OUT = REPAIR / "validation-03"
SHORT_SOURCE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05/input/source.mp4"
IMAGE = "openstoryline-task:arm64-native-entry-repair-03"
IMAGE_ID_FILE = REPAIR / "image-identity-03.json"
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
sys.path.insert(0, str(ROOT / "src"))
import openstoryline_pilot_entry as entry  # noqa: E402
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime  # noqa: E402


def hash_file(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_true(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite validation evidence: {OUT}")
    if not SHORT_SOURCE.is_file():
        raise FileNotFoundError(SHORT_SOURCE)
    identity = json.loads(IMAGE_ID_FILE.read_text(encoding="utf-8"))
    entry.IMAGE = IMAGE
    entry.IMAGE_ID = identity["id"]
    OUT.mkdir(parents=True, exist_ok=False)
    input_dir, output_dir, project_dir = OUT / "input", OUT / "output", OUT / "project"
    input_dir.mkdir()
    output_dir.mkdir()
    project_dir.mkdir()
    source = input_dir / "source.mp4"
    shutil.copy2(SHORT_SOURCE, source)
    source_record = hash_file(source)
    budget = {"max_logical_requests": 30,
              "max_observed_tokens_soft_threshold": 100000,
              "max_output_tokens_per_request": 8192}
    frozen_identity = {"schema": "offline-native-entry-identity-v1",
                       "run_id": f"offline-{uuid.uuid4().hex}", "budget": budget}
    frozen_identity["identity_sha256"] = entry.identity_hash(frozen_identity)
    request = {
        "output_dir": "/workspace/output",
        "instruction": "请处理输入目录中的短英文视频，依次调用原生工具，保留有效语句并渲染时间线。",
        "lang": "zh",
        "recursion_limit": 28,
        "budget": budget,
        "frozen_identity": frozen_identity,
        "offline_fake_model": True,
    }
    request_path = OUT / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    (OUT / "validation-start.json").write_text(
        json.dumps({"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source": {"path": str(source), **source_record},
                    "model_boundary": "container-local fake OpenAI Chat Completions",
                    "mcp_asr_render": "real", "network": "none"},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    deadline = time.monotonic() + 1200
    spec = entry.build_container_spec(
        run_id="native-entry-repair-01", output_dir=output_dir,
        request_path=request_path, api_key=None, run_deadline=deadline,
        input_dir=input_dir, network="none", offline_fake_model=True)
    assert_true(spec.network == "none", "container network must be disabled")
    assert_true("DASHSCOPE_API_KEY" not in spec.env, "offline spec must not contain a model credential")
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-NATIVE-ENTRY-REPAIR-01")
    handle = None
    run_record = {"image": {"tag": IMAGE, "id": identity["id"]},
                  "container_spec": {"network": spec.network, "cpus": spec.cpu_limit,
                                     "memory": spec.mem_limit,
                                     "mounts": spec.mounts, "env_names": sorted(spec.env)},
                  "source": {"path": str(source), **source_record}}
    try:
        handle = runtime.start(spec, deadline=deadline)
        run_record["container_id"] = handle.container_id
        run_record["cgroup_version"] = handle.cgroup_version
        command = "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json"
        result = runtime.execute(handle, command, timeout_s=max(1, min(900, int(deadline - time.monotonic()))),
                                 output_limit=2_000_000)
        run_record["entry_result"] = result
        if result.get("returncode") != 0:
            raise RuntimeError(f"production entry returned {result.get('returncode')}: {result.get('output', '')[-4000:]}")
    except BaseException as exc:
        run_record["error"] = {"type": type(exc).__name__, "message": str(exc)[:1200]}
        raise
    finally:
        if handle:
            try:
                runtime.stop(handle, timeout_s=30)
                run_record["container_removal"] = runtime.verify_removal(handle, timeout_s=20)
            except Exception as exc:
                run_record["container_removal"] = f"check_failed:{type(exc).__name__}:{exc}"
        run_record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (OUT / "container-run.json").write_text(
            json.dumps(run_record, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8")

    result = json.loads((output_dir / "agent-result.json").read_text(encoding="utf-8"))
    assert_true(result.get("status") == "completed", f"agent did not complete: {result}")
    phase = json.loads((output_dir / "phase-times.json").read_text(encoding="utf-8"))
    assert_true(phase.get("mcp_cleanup_status") == "stopped", f"MCP cleanup failed: {phase}")
    native_messages = json.loads((output_dir / "native-messages.json").read_text(encoding="utf-8"))
    assert_true(len(native_messages) > 3, "native Agent messages were not persisted")
    system_contents = [str(message.get("content", "")) for message in native_messages
                       if message.get("type") == "system"]
    assert_true(any(("Role" in text and "video editing assistant" in text.lower())
                    or "视频剪辑助理" in text
                    for text in system_contents), "official instruction system message missing")
    assert_true(any("User media upload status" in text for text in system_contents),
                "official media overview system message missing")

    session_id = json.loads((output_dir / "agent-context.json").read_text())["session_id"]
    store_dir = output_dir / session_id
    metas = json.loads((store_dir / "meta.json").read_text(encoding="utf-8"))
    expected_nodes = {"load_media", "split_shots", "local_asr", "speech_rough_cut",
                      "plan_timeline_pro", "render_video"}
    node_metas = [row for row in metas if row.get("node_id") in expected_nodes]
    by_node = {node: [row for row in node_metas if row["node_id"] == node]
               for node in expected_nodes}
    for node in expected_nodes:
        assert_true(by_node[node], f"automatic artifact save missing {node}")
    artifact_records = {}
    for meta in node_metas:
        artifact_path = store_dir / meta["node_id"] / f"{meta['artifact_id']}.json"
        record = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert_true(record["session_id"] == session_id, f"artifact session mismatch: {meta}")
        assert_true(record["artifact_id"] == meta["artifact_id"], "artifact metadata ID mismatch")
        artifact_records[meta["node_id"]] = record

    load_payload = artifact_records["load_media"]["payload"]
    split_payload = artifact_records["split_shots"]["payload"]
    asr_payload = artifact_records["local_asr"]["payload"]
    rough_payload = artifact_records["speech_rough_cut"]["payload"]
    plan_payload = artifact_records["plan_timeline_pro"]["payload"]
    render_payload = artifact_records["render_video"]["payload"]
    assert_true(len(load_payload.get("media", [])) == 1, "load_media did not index the actual input")
    assert_true(len(split_payload.get("clips", [])) >= 1, "split_shots(mode=skip) returned empty clips")
    infos = asr_payload.get("asr_infos", [])
    assert_true(infos and infos[0].get("asr_text", "").strip(), "local ASR returned no text")
    assert_true(infos[0].get("asr_sentence_info"), "local ASR returned no sentence/timestamp data")
    assert_true(rough_payload.get("clips"), "speech_rough_cut did not consume the ASR result")
    assert_true(plan_payload.get("tracks", {}).get("video"), "PlanTimelinePro did not consume rough-cut clips")
    assert_true(render_payload.get("output_path"), "RenderVideo artifact lacks its actual output path")

    tool_events = read_jsonl(output_dir / "mcp-tool-events.jsonl")
    started = [row for row in tool_events if row.get("event") == "tool_call_started"]
    finished = [row for row in tool_events if row.get("event") == "tool_call_finished"]
    for node in expected_nodes:
        assert_true(any(row.get("node_id") == node for row in started),
                    f"no real MCP start event for {node}")
        assert_true(any(row.get("node_id") == node and not row.get("is_error") for row in finished),
                    f"no successful real MCP result event for {node}")
    rough_event = next(row for row in started if row.get("node_id") == "speech_rough_cut")
    assert_true(rough_event.get("arguments", {}).get("asr", {}).get("asr_infos"),
                "speech_rough_cut did not receive saved same-session ASR payload")
    plan_event = next(row for row in started if row.get("node_id") == "plan_timeline_pro")
    assert_true(plan_event.get("arguments", {}).get("speech_rough_cut", {}).get("clips"),
                "timeline did not receive saved rough-cut payload")
    history_queries = {row.get("arguments", {}).get("query_artifact_id") for row in started
                       if row.get("node_id") == "read_node_history"}
    for row in node_metas:
        assert_true(row["artifact_id"] in history_queries,
                    f"read_node_history did not query returned artifact {row['artifact_id']}")

    request_events = read_jsonl(output_dir / "model-requests.jsonl")
    request_started = [row for row in request_events if row.get("event") == "request_started"]
    request_finished = [row for row in request_events if row.get("event") == "request_finished"]
    assert_true(request_started and len(request_started) <= budget["max_logical_requests"],
                "logical requests missing or exceeded the pre-send cap")
    assert_true(any(row.get("phase") == "llm_validation" for row in request_finished),
                "native LLM initialization validation request was not recorded")
    assert_true(any(row.get("phase") == "vlm_validation" for row in request_finished),
                "native VLM initialization validation request was not recorded")
    sampling = [row for row in request_finished if row.get("phase") == "mcp_sampling"]
    assert_true(sampling and all(row.get("association", {}).get("node_id") == "speech_rough_cut"
                                 and row.get("association", {}).get("session_id") == session_id
                                 for row in sampling),
                "node LLM request records are not associated with speech rough cut/session")
    fake_requests = read_jsonl(output_dir / "fake-model-requests.jsonl")
    assert_true(fake_requests and all(row.get("response_model") == "offline-fake-qwen3.7-plus"
                                      for row in fake_requests), "fake model response identity missing")
    assert_true(len(fake_requests) == len(request_started),
                "fake transport exchanges and logical request records differ")

    export_video = entry.export_rendered_video(output_dir, source)
    export_cuts = entry.export_cuts_from_final_timeline(output_dir, source)
    assert_true(export_video["status"] == "exported_and_verified", "render artifact was not exported")
    assert_true(export_video["source"] == export_video["submission"], "output.mp4 hash mismatch")
    assert_true(export_video["video"]["codec"] == "h264" and
                export_video["video"]["pixel_format"] == "yuv420p", "video codec contract mismatch")
    assert_true(export_video["audio"]["codec"] == "aac" and export_video["audio"]["non_silent"],
                "original AAC audio missing or silent")
    assert_true(export_cuts["status"] == "derived_from_final_timeline", "cuts not derived from final timeline")

    # The persisted exact-session history index must not leak into another session.
    other_meta = (output_dir / "obviously-not-this-session" / "meta.json")
    assert_true(not other_meta.exists(), "unexpected cross-session artifact directory created")
    from open_storyline.storage.agent_memory import ArtifactStore
    isolated_store = ArtifactStore(output_dir, "offline-isolation-probe")
    assert_true(isolated_store.get_latest_meta(node_id="load_media", session_id="offline-isolation-probe") is None,
                "artifact history leaked across sessions")

    report = {
        "status": "PASS_fake_model_real_mcp_local_compute",
        "model_boundary": "container-local fake Chat Completions; no real API and no credentials read",
        "real_components": ["production openstoryline_task_entry", "native LangChain Agent",
                            "MCP transport/public tools", "native interceptors and ArtifactStore",
                            "LocalASRNode", "SpeechRoughCutNode local media processing",
                            "PlanTimelinePro", "RenderVideo", "submission export"],
        "session_id": session_id, "artifact_count": len(metas),
        "node_artifact_ids": {node: [row["artifact_id"] for row in by_node[node]]
                              for node in sorted(expected_nodes)},
        "logical_requests": len(request_started), "fake_http_exchanges": len(fake_requests),
        "mcp_tool_calls": len(started), "history_queries": len(history_queries),
        "render_export": export_video, "cuts_export": export_cuts,
        "mcp_cleanup": phase.get("mcp_cleanup_status"),
        "container_removal": run_record.get("container_removal"),
    }
    (OUT / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
