#!/usr/bin/env python3
"""One real Bailian short-task run through the production OpenStoryline entry."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
PREP = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04"
SOURCE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05/input/source.mp4"
REPAIR = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
IMAGE = "openstoryline-task:arm64-native-confirm-flow-03"
IMAGE_ID = "sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0"
_SECRET_FOR_REDACTION: str | None = None
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
sys.path.insert(0, str(ROOT / "src"))
import openstoryline_pilot_entry as entry  # noqa: E402
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime  # noqa: E402
from short_task_budget import begin_deadline  # noqa: E402


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


def scrub(value: object, secret: str | None) -> str:
    text = str(value)
    return text.replace(secret, "[REDACTED]") if secret else text


def main() -> int:
    reserved = ("input", "output", "project", "request.json", "run-start.json",
                "container-run.json", "validation-report.json", "failure-report.json",
                "evidence-manifest.json")
    if any((PREP / name).exists() for name in reserved):
        raise RuntimeError(f"refusing to reuse preparation evidence: {PREP}")
    if (PREP.parent / "native-agent-gate.json").exists():
        raise RuntimeError("native-agent-gate.json already exists; refusing to overwrite")
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    inspected = __import__("subprocess").run(
        ["docker", "--host", "unix:///var/run/docker.sock", "image", "inspect", IMAGE,
         "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
        capture_output=True, text=True, check=True).stdout.strip()
    if inspected != f"{IMAGE_ID} linux/arm64":
        raise RuntimeError("candidate image identity/platform changed")

    # Start the sole short-task clock after local identity/source checks and
    # before writing any run files, reading the credential, or starting a container.
    window = begin_deadline(1800)
    started = window.started_monotonic
    deadline = window.deadline_monotonic
    cleanup_reserve_s = 60
    execution_deadline = window.execution_deadline(cleanup_reserve_s)
    PREP.mkdir(parents=True, exist_ok=True)
    input_dir, output_dir, project_dir = PREP / "input", PREP / "output", PREP / "project"
    input_dir.mkdir()
    output_dir.mkdir()
    project_dir.mkdir()
    source = input_dir / "source.mp4"
    shutil.copy2(SOURCE, source)
    budget = {"max_logical_requests": 40,
              "max_observed_tokens_soft_threshold": 500_000,
              "max_output_tokens_per_request": 8192}
    route = {"protocol": "Chat Completions", "model": "qwen3.7-plus",
             "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "sdk_retries": 0, "application_retries": 0}
    frozen = {"schema": "openstoryline-real-short-identity-v1",
              "run_id": f"bailian-short-{uuid.uuid4().hex}", "budget": budget,
              "model_route": route,
              "image": {"tag": IMAGE, "id": IMAGE_ID},
              "source_sha256": digest(source)["sha256"]}
    frozen["identity_sha256"] = entry.identity_hash(frozen)
    request = {
        "output_dir": "/workspace/output",
        "instruction": (
            "请处理输入目录中的短英文访谈视频。使用原生工具链读取媒体、执行真实本地ASR，"
            "依据ASR结果调用speech_rough_cut保留有意义的语句，然后运行PlanTimelinePro与RenderVideo。"
            "请通过工具结果和history确认前序产物，保持输入视频的分辨率、帧率和原声，"
            "渲染后正常结束并导出output.mp4与cuts.json。不要添加字幕、音乐、动画、调色或额外转场。"
        ),
        "lang": "zh",
        "recursion_limit": 26,
        "max_plan_confirmations": 2,
        "budget": budget,
        "frozen_identity": frozen,
    }
    request_path = PREP / "request.json"
    with request_path.open("x", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
    (PREP / "run-start.json").write_text(json.dumps({
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "started_monotonic_ns": int(started * 1e9),
        "deadline_monotonic_ns": int(deadline * 1e9),
        "deadline_origin": "this real-native-short-04 process; no previous run timestamp read",
        "cleanup_reserve_s": cleanup_reserve_s,
        "source": {"path": str(source), **digest(source)},
        "image": {"tag": IMAGE, "id": IMAGE_ID, "platform": "linux/arm64"},
        "budget": budget,
        "model_route": route,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Read the already registered key only after all local, no-network setup passes.
    secret = entry.safe_credential()
    global _SECRET_FOR_REDACTION
    _SECRET_FOR_REDACTION = secret
    spec = entry.build_container_spec(
        run_id=frozen["run_id"], output_dir=output_dir, request_path=request_path,
        api_key=secret, run_deadline=execution_deadline, input_dir=input_dir,
        network="bridge", offline_fake_model=False)
    if spec.image != IMAGE or spec.network != "bridge":
        raise RuntimeError("container spec does not match the registered real-model run")
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-REAL-NATIVE-SHORT-04")
    handle = None
    record = {
        "image": {"tag": IMAGE, "id": IMAGE_ID},
        "container_spec": {"network": spec.network, "cpus": spec.cpu_limit,
                           "memory": spec.mem_limit, "mounts": spec.mounts,
                           "env_names": sorted(spec.env)},
        "source": digest(source),
        "credential_value_recorded": False,
        "wall_deadline_monotonic_ns": int(deadline * 1e9),
        "execution_deadline_monotonic_ns": int(execution_deadline * 1e9),
    }
    try:
        handle = runtime.start(spec, deadline=execution_deadline)
        record["container_id"] = handle.container_id
        record["cgroup_version"] = handle.cgroup_version
        command = "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json"
        remaining_execution = execution_deadline - time.monotonic()
        if remaining_execution <= 0:
            raise TimeoutError("short-task execution window expired before Agent entry")
        result = runtime.execute(handle, command,
                                 timeout_s=max(1, int(remaining_execution)),
                                 output_limit=1_000_000)
        record["entry_result"] = {k: v for k, v in result.items()
                                  if k not in {"output"}}
        record["entry_output_tail"] = scrub(result.get("output", ""), secret)[-12000:]
    except BaseException as exc:
        record["error"] = {"type": type(exc).__name__,
                           "message": scrub(exc, secret)[:1200]}
    finally:
        if handle:
            try:
                runtime.stop(handle, timeout_s=20)
                record["container_removal"] = runtime.verify_removal(handle, timeout_s=20)
            except Exception as exc:
                record["container_removal"] = f"check_failed:{type(exc).__name__}"
        if runtime.pending_names:
            try:
                record["pending_start_cleanup"] = runtime.cleanup_pending(timeout_s=20)
            except Exception as exc:
                record["pending_start_cleanup"] = {
                    "status": "check_failed", "error": type(exc).__name__}
        record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record["wall_s"] = time.monotonic() - started
        (PREP / "container-run.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8")

    result_file = output_dir / "agent-result.json"
    if not result_file.is_file():
        raise RuntimeError("production entry did not persist agent-result.json")
    agent_result = json.loads(result_file.read_text(encoding="utf-8"))
    if record.get("entry_result", {}).get("returncode") != 0 or agent_result.get("status") != "executing":
        raise RuntimeError("real native Agent session failed; preserving evidence and stopping")
    if record.get("container_removal") != "removed":
        raise RuntimeError("real short-task container removal was not confirmed")
    if time.monotonic() > deadline:
        raise RuntimeError("real short-task total wall deadline expired during cleanup")

    requests = read_jsonl(output_dir / "model-requests.jsonl")
    starts = [row for row in requests if row.get("event") == "request_started"]
    finishes = [row for row in requests if row.get("event") == "request_finished"]
    by_request = {row["request_id"]: [] for row in starts}
    for row in requests:
        if row.get("request_id") in by_request:
            by_request[row["request_id"]].append(row)
    if not starts or len(starts) > 40 or len(starts) != len(finishes):
        raise RuntimeError("real logical request ledger is missing, duplicated, or over budget")
    if any(not 0 < row.get("max_output_tokens_per_request", 0) <= 8192
           for row in starts):
        raise RuntimeError("real short-task request exceeded its output-token cap")
    if any(sum(x.get("event") == "request_started" for x in group) != 1
           or sum(x.get("event") == "request_finished" for x in group) != 1
           for group in by_request.values()):
        raise RuntimeError("real request IDs do not have one start and one finish")

    session_id = json.loads((output_dir / "agent-context.json").read_text())["session_id"]
    actual_base_url = ctx_base_url(output_dir)
    if actual_base_url != route["base_url"]:
        raise RuntimeError("session used a different registered Chat Completions route")
    store = output_dir / session_id
    metas = json.loads((store / "meta.json").read_text(encoding="utf-8"))
    required_nodes = {"load_media", "split_shots", "local_asr", "speech_rough_cut",
                      "plan_timeline_pro", "render_video"}
    node_metas = [row for row in metas if row.get("node_id") in required_nodes]
    if not required_nodes.issubset({row.get("node_id") for row in node_metas}):
        raise RuntimeError("real short task did not execute the required native node chain")
    tools = read_jsonl(output_dir / "mcp-tool-events.jsonl")
    tool_starts = [row for row in tools if row.get("event") == "tool_call_started"]
    tool_finishes = [row for row in tools if row.get("event") == "tool_call_finished"]
    for node in required_nodes:
        if not any(row.get("node_id") == node for row in tool_starts):
            raise RuntimeError(f"real MCP call missing for {node}")
        if not any(row.get("node_id") == node and not row.get("is_error")
                   for row in tool_finishes):
            raise RuntimeError(f"real MCP result failed for {node}")
    if not any(row.get("phase") == "agent" for row in starts):
        raise RuntimeError("no real top-level Agent request was recorded")
    if not any(row.get("phase") == "mcp_sampling"
               and row.get("association", {}).get("node_id") == "speech_rough_cut"
               for row in finishes):
        raise RuntimeError("no real speech_rough_cut node request was recorded")
    observed_tokens = sum((row.get("usage") or {}).get(
        "total_tokens", (row.get("usage") or {}).get("input_tokens", 0)
        + (row.get("usage") or {}).get("output_tokens", 0)) for row in finishes)
    if observed_tokens > 500_000:
        raise RuntimeError("returned usage crossed the observed-token soft threshold")
    phase = json.loads((output_dir / "phase-times.json").read_text())
    if phase.get("mcp_cleanup_status") != "stopped":
        raise RuntimeError("MCP child process cleanup failed")

    # Prove the actual producer payload was handed to each next native node.
    # History is an on-demand tool, so requiring an explicit history lookup
    # for every artifact incorrectly rejects valid runs where the Agent
    # already has the preceding tool result in its transcript.
    artifacts = {}
    for row in node_metas:
        path = store / row["node_id"] / f"{row['artifact_id']}.json"
        artifacts[row["node_id"]] = json.loads(path.read_text(encoding="utf-8"))
    calls_by_node = {row.get("node_id"): row.get("arguments", {})
                     for row in tool_starts if row.get("node_id") in required_nodes}
    links = (("load_media", "split_shots", "load_media"),
             ("split_shots", "local_asr", "split_shots"),
             ("local_asr", "speech_rough_cut", "asr"),
             ("speech_rough_cut", "plan_timeline_pro", "speech_rough_cut"),
             ("plan_timeline_pro", "render_video", "plan_timeline"))
    for producer, consumer, argument in links:
        if calls_by_node.get(consumer, {}).get(argument) != artifacts[producer].get("payload"):
            raise RuntimeError(f"{consumer} did not consume the real {producer} artifact payload")
    history_starts = [row for row in tool_starts if row.get("node_id") == "read_node_history"]
    history_finishes = [row for row in tool_finishes if row.get("node_id") == "read_node_history"
                        and not row.get("is_error")]
    history_queries = {row.get("arguments", {}).get("query_artifact_id")
                       for row in history_starts}
    returned_history = set()
    for row in history_finishes:
        history = (row.get("returned_payload") or {}).get("history") or {}
        meta = history.get("meta") or {}
        data = history.get("node_data") or {}
        if (meta.get("session_id") == session_id == data.get("session_id")
                and meta.get("artifact_id") == data.get("artifact_id")):
            returned_history.add(meta.get("artifact_id"))
    if (not history_starts or len(history_starts) != len(history_finishes)
            or not history_queries.issubset(returned_history)):
        raise RuntimeError("same-session history queries lack matching successful artifact results")
    if not any(row.get("artifact_id") in returned_history
               for row in node_metas if row.get("node_id") == "render_video"):
        raise RuntimeError("Agent did not retrieve the final RenderVideo artifact through history")
    local_asr = next(row for row in node_metas if row.get("node_id") == "local_asr")
    asr_artifact = json.loads((store / "local_asr" / f"{local_asr['artifact_id']}.json").read_text())
    asr_infos = asr_artifact.get("payload", {}).get("asr_infos", [])
    if not asr_infos or not asr_infos[0].get("asr_text", "").strip() or not asr_infos[0].get("asr_sentence_info"):
        raise RuntimeError("real LocalASR artifact lacks text or sentence timestamps")
    asr_sentence_count = len(asr_infos[0]["asr_sentence_info"])
    if not asr_sentence_count:
        raise RuntimeError("real LocalASR produced no sentence-level segments")

    export = entry.export_rendered_video(output_dir, source)
    decode = __import__("subprocess").run(
        ["ffmpeg", "-v", "error", "-i", str(output_dir / "output.mp4"),
         "-f", "null", "-"], capture_output=True, text=True, timeout=90)
    if decode.returncode != 0:
        raise RuntimeError("exported output.mp4 did not fully decode")
    export["full_decode"] = "PASS"
    cuts = entry.export_cuts_from_final_timeline(output_dir, source)
    if export.get("status") != "exported_and_verified" or cuts.get("status") != "derived_from_final_timeline":
        raise RuntimeError("real short-task submission export contract failed")
    agent_result.update({"status": "completed", "submission_export_verified": True,
                         "output_sha256": export["submission"]["sha256"],
                         "cuts_status": cuts["status"]})
    (output_dir / "agent-result.json").write_text(
        json.dumps(agent_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    session_status = json.loads((output_dir / "session-status.json").read_text())
    session_status.update({"status": "completed", "submission_export_verified": True,
                           "completed_monotonic_ns": time.monotonic_ns()})
    (output_dir / "session-status.json").write_text(
        json.dumps(session_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gate_path = PREP.parent / "native-agent-gate.json"
    if gate_path.exists():
        raise RuntimeError("native-agent-gate.json already exists; refusing to overwrite")
    if time.monotonic() > deadline:
        raise RuntimeError("real short-task total wall deadline expired during submission verification")
    historical = []
    for name in ("real-native-short-01", "real-native-short-02", "real-native-short-03"):
        ledger_path = PREP.parent / name / "output/model-requests.jsonl"
        if not ledger_path.is_file():
            continue
        rows = read_jsonl(ledger_path)
        historical.append({
            "session_record": str((PREP.parent / name).relative_to(ROOT)),
            "logical_requests_started": sum(r.get("event") == "request_started" for r in rows),
            "observed_returned_tokens": sum((r.get("usage") or {}).get("total_tokens", 0)
                                             for r in rows if r.get("event") == "request_finished"),
            "included_in_current_budget": False,
        })
    record["total_wall_s"] = time.monotonic() - started
    record["total_wall_limit_s"] = 1800
    record["cleanup_reserve_s"] = cleanup_reserve_s
    record["wall_deadline_met"] = record["total_wall_s"] <= 1800
    with (PREP / "container-run.json").open("w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n"); stream.flush()
    if not record["wall_deadline_met"]:
        raise RuntimeError("real short-task total wall limit exceeded")
    report = {
        "schema": "openstoryline-real-native-short-gate-v1", "status": "PASS",
        "session_id": session_id, "image": {"tag": IMAGE, "id": IMAGE_ID},
        "source": {"path": str(source), **digest(source)},
        "agent": {"status": "completed",
                  "returncode": record["entry_result"]["returncode"],
                  "wall_s": record["total_wall_s"], "container_removal": record["container_removal"],
                  "mcp_cleanup": phase.get("mcp_cleanup_status"),
                  "confirmations_sent": agent_result.get("confirmations_sent")},
        "model": {"requested": "qwen3.7-plus", "base_url": actual_base_url,
                  "response_models": sorted({row.get("response_metadata", {}).get("model_name")
                                             for row in finishes if row.get("response_metadata", {}).get("model_name")}),
                  "logical_requests": len(starts), "http_requests": "unknown",
                  "request_cap": 40, "max_output_tokens": 8192,
                  "observed_tokens": observed_tokens,
                  "observed_tokens_soft_threshold": 500000,
                  "initial_logical_request_count": 0},
        "historical_sessions": historical,
        "asr_sentence_count": asr_sentence_count,
        "wall_budget": {"started_monotonic_ns": int(started * 1e9),
                        "deadline_monotonic_ns": int(deadline * 1e9),
                        "cleanup_reserve_s": cleanup_reserve_s,
                        "total_wall_s": record["total_wall_s"],
                        "limit_s": 1800},
        "tools": {"calls": len(tool_starts), "nodes": sorted(required_nodes),
                  "artifact_count": len(node_metas),
                  "history_queries": len(history_queries)},
        "render_export": export, "cuts_export": cuts,
    }
    (PREP / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    gate = {
        "schema": "openstoryline-native-agent-gate-v1", "status": "PASS",
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "native_langchain_agent_verified": True,
        "real_model_requests_agent": sum(row.get("phase") == "agent" for row in finishes),
        "real_model_requests_node": sum(row.get("phase") == "mcp_sampling" for row in finishes),
        "tool_names": sorted({row.get("tool_name") for row in tool_starts}),
        "local_asr_real": True, "audio_video_contract": "PASS",
        "container_cleanup": "PASS", "logical_requests": len(starts),
        "response_models": report["model"]["response_models"],
        "source_sha256": digest(source)["sha256"],
        "image": {"tag": IMAGE, "id": IMAGE_ID},
        "session_id": session_id,
        "report": str((PREP / "validation-report.json").relative_to(ROOT)),
        "evidence_manifest": str((PREP / "evidence-manifest.json").relative_to(ROOT)),
    }
    with gate_path.open("x", encoding="utf-8") as stream:
        json.dump(gate, stream, ensure_ascii=False, indent=2)
        stream.write("\n"); stream.flush()
    manifest_rows = []
    for path in sorted(PREP.rglob("*")):
        if not path.is_file() or path.name == "evidence-manifest.json" or path.suffix == ".pyc":
            continue
        manifest_rows.append({"path": str(path.relative_to(PREP)), **digest(path)})
    with (PREP / "evidence-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-real-native-short-evidence-v1",
                   "self_hash": "omitted", "files": manifest_rows}, stream,
                  ensure_ascii=False, indent=2)
        stream.write("\n"); stream.flush()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def ctx_base_url(output: Path) -> str:
    return json.loads((output / "agent-context.json").read_text(encoding="utf-8")).get("base_url", "")


def _write_failure_evidence(exc: BaseException) -> None:
    PREP.mkdir(parents=True, exist_ok=True)
    report_path = PREP / "failure-report.json"
    if not report_path.exists():
        start_path = PREP / "run-start.json"
        start = json.loads(start_path.read_text(encoding="utf-8")) if start_path.is_file() else {}
        monotonic_start = start.get("started_monotonic_ns")
        elapsed = (max(0.0, (time.monotonic_ns() - int(monotonic_start)) / 1e9)
                   if monotonic_start is not None else None)
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump({"schema": "openstoryline-real-native-short-failure-v1",
                       "status": "FAIL", "error_type": type(exc).__name__,
                       "error": scrub(exc, _SECRET_FOR_REDACTION)[:2000],
                       "run_id": (json.loads((PREP / "request.json").read_text(
                           encoding="utf-8")).get("frozen_identity", {}).get("run_id")
                                  if (PREP / "request.json").is_file() else None),
                       "started_monotonic_ns": monotonic_start,
                       "elapsed_wall_s_at_failure": elapsed,
                       "wall_limit_s": 1800,
                       "container_run_evidence": str(PREP / "container-run.json"),
                       "previous_session_preserved": str(
                           PREP.parent / "real-native-short-03"),
                       "observed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                      stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
    manifest_path = PREP / "evidence-manifest.json"
    if not manifest_path.exists():
        rows = []
        for path in sorted(PREP.rglob("*")):
            if not path.is_file() or path == manifest_path or path.suffix == ".pyc":
                continue
            rows.append({"path": str(path.relative_to(PREP)), **digest(path)})
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump({"schema": "openstoryline-real-native-short-evidence-v1",
                       "status": "partial_failure_preserved", "self_hash": "omitted",
                       "files": rows}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code in (0, None):
            raise
        _write_failure_evidence(exc)
        raise
