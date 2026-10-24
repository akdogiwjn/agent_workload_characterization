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
PREP = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-01"
SOURCE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05/input/source.mp4"
REPAIR = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
IMAGE = "openstoryline-task:arm64-native-entry-repair-07"
IMAGE_ID = "sha256:12f06a54bb3d79b375ea271d96e3ea93975feb41d3f0ff1881721d3826fb52de"
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
sys.path.insert(0, str(ROOT / "src"))
import openstoryline_pilot_entry as entry  # noqa: E402
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime  # noqa: E402


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


def main() -> int:
    reserved = ("input", "output", "project", "request.json", "run-start.json",
                "container-run.json", "validation-report.json")
    if any((PREP / name).exists() for name in reserved):
        raise RuntimeError(f"refusing to reuse preparation evidence: {PREP}")
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    inspected = __import__("subprocess").run(
        ["docker", "--host", "unix:///var/run/docker.sock", "image", "inspect", IMAGE,
         "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
        capture_output=True, text=True, check=True).stdout.strip()
    if inspected != f"{IMAGE_ID} linux/arm64":
        raise RuntimeError("candidate image identity/platform changed")

    started = time.monotonic()
    deadline = started + 600
    PREP.mkdir(parents=True, exist_ok=True)
    input_dir, output_dir, project_dir = PREP / "input", PREP / "output", PREP / "project"
    input_dir.mkdir()
    output_dir.mkdir()
    project_dir.mkdir()
    source = input_dir / "source.mp4"
    shutil.copy2(SOURCE, source)
    budget = {"max_logical_requests": 20,
              "max_observed_tokens_soft_threshold": 200_000,
              "max_output_tokens_per_request": 8192}
    frozen = {"schema": "openstoryline-real-short-identity-v1",
              "run_id": f"bailian-short-{uuid.uuid4().hex}", "budget": budget}
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
        "started_monotonic_ns": time.monotonic_ns(),
        "source": {"path": str(source), **digest(source)},
        "image": {"tag": IMAGE, "id": IMAGE_ID, "platform": "linux/arm64"},
        "budget": budget,
        "model_route": {"protocol": "Chat Completions", "model": "qwen3.7-plus",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "sdk_retries": 0, "application_retries": 0},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Read the already registered key only after all local, no-network setup passes.
    secret = entry.safe_credential()
    spec = entry.build_container_spec(
        run_id=frozen["run_id"], output_dir=output_dir, request_path=request_path,
        api_key=secret, run_deadline=deadline, input_dir=input_dir,
        network="bridge", offline_fake_model=False)
    if spec.image != IMAGE or spec.network != "bridge":
        raise RuntimeError("container spec does not match the registered real-model run")
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-REAL-NATIVE-SHORT-01")
    handle = None
    record = {
        "image": {"tag": IMAGE, "id": IMAGE_ID},
        "container_spec": {"network": spec.network, "cpus": spec.cpu_limit,
                           "memory": spec.mem_limit, "mounts": spec.mounts,
                           "env_names": sorted(spec.env)},
        "source": digest(source),
        "credential_value_recorded": False,
    }
    try:
        handle = runtime.start(spec, deadline=deadline)
        record["container_id"] = handle.container_id
        record["cgroup_version"] = handle.cgroup_version
        command = "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json"
        result = runtime.execute(handle, command,
                                 timeout_s=max(1, min(600, int(deadline - time.monotonic()))),
                                 output_limit=1_000_000)
        record["entry_result"] = {k: v for k, v in result.items()
                                  if k not in {"output"}}
        record["entry_output_tail"] = str(result.get("output", ""))[-12000:]
    except BaseException as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:1200]}
    finally:
        if handle:
            try:
                runtime.stop(handle, timeout_s=20)
                record["container_removal"] = runtime.verify_removal(handle, timeout_s=20)
            except Exception as exc:
                record["container_removal"] = f"check_failed:{type(exc).__name__}"
        record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record["wall_s"] = time.monotonic() - started
        (PREP / "container-run.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8")

    result_file = output_dir / "agent-result.json"
    if not result_file.is_file():
        raise RuntimeError("production entry did not persist agent-result.json")
    agent_result = json.loads(result_file.read_text(encoding="utf-8"))
    if record.get("entry_result", {}).get("returncode") != 0 or agent_result.get("status") != "completed":
        raise RuntimeError("real native Agent session failed; preserving evidence and stopping")
    if record.get("container_removal") != "removed":
        raise RuntimeError("real short-task container removal was not confirmed")
    if record.get("wall_s", 10**9) > 600:
        raise RuntimeError("real short-task wall limit exceeded")

    requests = read_jsonl(output_dir / "model-requests.jsonl")
    starts = [row for row in requests if row.get("event") == "request_started"]
    finishes = [row for row in requests if row.get("event") == "request_finished"]
    by_request = {row["request_id"]: [] for row in starts}
    for row in requests:
        if row.get("request_id") in by_request:
            by_request[row["request_id"]].append(row)
    if not starts or len(starts) > 20 or len(starts) != len(finishes):
        raise RuntimeError("real logical request ledger is missing, duplicated, or over budget")
    if any(row.get("max_output_tokens_per_request", 0) > 8192 for row in starts):
        raise RuntimeError("real short-task request exceeded its output-token cap")
    if any(sum(x.get("event") == "request_started" for x in group) != 1
           or sum(x.get("event") == "request_finished" for x in group) != 1
           for group in by_request.values()):
        raise RuntimeError("real request IDs do not have one start and one finish")

    session_id = json.loads((output_dir / "agent-context.json").read_text())["session_id"]
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
    phase = json.loads((output_dir / "phase-times.json").read_text())
    if phase.get("mcp_cleanup_status") != "stopped":
        raise RuntimeError("MCP child process cleanup failed")

    export = entry.export_rendered_video(output_dir, source)
    cuts = entry.export_cuts_from_final_timeline(output_dir, source)
    if export.get("status") != "exported_and_verified" or cuts.get("status") != "derived_from_final_timeline":
        raise RuntimeError("real short-task submission export contract failed")
    report = {
        "schema": "openstoryline-real-native-short-gate-v1", "status": "PASS",
        "session_id": session_id, "image": {"tag": IMAGE, "id": IMAGE_ID},
        "source": {"path": str(source), **digest(source)},
        "agent": {"status": agent_result.get("status"),
                  "returncode": record["entry_result"]["returncode"],
                  "wall_s": record["wall_s"], "container_removal": record["container_removal"],
                  "mcp_cleanup": phase.get("mcp_cleanup_status")},
        "model": {"requested": "qwen3.7-plus", "base_url": ctx_base_url(output_dir),
                  "response_models": sorted({row.get("response_metadata", {}).get("model_name")
                                             for row in finishes if row.get("response_metadata", {}).get("model_name")}),
                  "logical_requests": len(starts), "http_requests": "unknown",
                  "request_cap": 20, "max_output_tokens": 8192,
                  "observed_tokens_soft_threshold": 200000},
        "tools": {"calls": len(tool_starts), "nodes": sorted(required_nodes),
                  "artifact_count": len(node_metas)},
        "render_export": export, "cuts_export": cuts,
    }
    (PREP / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def ctx_base_url(output: Path) -> str:
    return json.loads((output / "agent-context.json").read_text(encoding="utf-8")).get("base_url", "")


if __name__ == "__main__":
    raise SystemExit(main())
