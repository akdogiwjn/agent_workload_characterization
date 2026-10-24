from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
RUNTIME = ROOT / "env/video/openstoryline/edit-pilot-02/runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import openstoryline_pilot_entry as formal  # noqa: E402
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime  # noqa: E402

SOURCE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05/input/source.mp4"
RUN_ROOT = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-agent-short-01"
REQUEST_BUDGET = {
    "max_logical_requests": 20,
    "max_observed_tokens_soft_threshold": 200_000,
    "max_output_tokens_per_request": 8192,
}
ROUTE = {
    "provider": "Bailian",
    "protocol": "Chat Completions",
    "model": "qwen3.7-plus",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "credential_file": str(formal.CREDENTIAL_FILE),
    "sdk_retries": 0,
    "application_retries": 0,
}


def file_digest(path: Path) -> dict:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def identity_sha(identity: dict) -> str:
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_exclusive(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def manifest(directory: Path) -> None:
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            rows.append({"path": str(path.relative_to(directory)), **file_digest(path)})
    write_exclusive(directory / "manifest.json", {
        "schema": "openstoryline-native-short-manifest-v1", "files": rows,
    })


def main() -> int:
    if not SOURCE.is_file():
        raise RuntimeError("registered short source is missing")
    cache_files = formal.validate_host_cache()
    if len(cache_files) != 16 or not all(row["readable"] for row in cache_files):
        raise RuntimeError("registered ASR cache preflight failed")
    image = subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", "image", "inspect",
         formal.IMAGE, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if image != f"{formal.IMAGE_ID} linux/arm64":
        raise RuntimeError("registered v13 image identity/platform mismatch")

    instruction = (
        "Edit this single short English example clip using the native OpenStoryline workflow. "
        "Load the media through the registered MCP tools, run local ASR, and use the native "
        "speech rough-cut node with its real configured model call. Preserve the intelligible "
        "speech content. Continue through the actual timeline planning and render nodes. "
        "Use split_shots mode=skip if appropriate. Include the source video audio with "
        "include_video_audio=true and video_volume_scale=1.0. Preserve the source dimensions "
        "and frame rate. Do not add subtitles, music, animation, color effects, or other assets. "
        "Use only /workspace/input/source.mp4 and return when the rendered video is complete."
    )
    if RUN_ROOT.exists():
        input_dir, output = RUN_ROOT / "input", RUN_ROOT / "output"
        project = RUN_ROOT / "project"
        request_path = RUN_ROOT / "request.json"
        identity_path = RUN_ROOT / "short-task-identity.json"
        launch_record = json.loads((RUN_ROOT / "launch-record.json").read_text())
        if launch_record.get("request_sent") or (output / "model-requests.jsonl").exists():
            raise RuntimeError("short task already sent a request; refusing another session")
        if any((output / name).exists() for name in (
                "mcp-server.log", "native-message-events.jsonl", "agent-context.json")):
            raise RuntimeError("short-task container work already began; refusing another session")
        if file_digest(input_dir / "source.mp4")["sha256"] != file_digest(SOURCE)["sha256"]:
            raise RuntimeError("saved short-task input differs from the registered source")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        total_start = int(identity["frozen_at_monotonic_ns"]) / 1e9
        if "startup-identity-before-repair.json" not in {p.name for p in RUN_ROOT.iterdir()}:
            shutil.copy2(identity_path, RUN_ROOT / "startup-identity-before-repair.json")
        if ((output / "short-task-identity.json").exists()
                and not (output / "short-task-identity-before-repair.json").exists()):
            shutil.copy2(output / "short-task-identity.json",
                         output / "short-task-identity-before-repair.json")
        identity.pop("identity_sha256", None)
        identity["route"] = ROUTE
    else:
        RUN_ROOT.mkdir(parents=True, exist_ok=False)
        input_dir = RUN_ROOT / "input"
        output = RUN_ROOT / "output"
        project = RUN_ROOT / "project"
        input_dir.mkdir()
        output.mkdir()
        project.mkdir()
        shutil.copy2(SOURCE, input_dir / "source.mp4")
        request_path = RUN_ROOT / "request.json"
        run_id = "openstoryline-native-short-20261022-01"
        identity = {
            "schema": "openstoryline-native-short-identity-v1",
            "run_id": run_id,
            "image": {"tag": formal.IMAGE, "id": formal.IMAGE_ID,
                      "platform": formal.PLATFORM},
            "input": {"path": str(SOURCE.relative_to(ROOT)), **file_digest(SOURCE)},
            "route": ROUTE,
            "budget": REQUEST_BUDGET,
            "wall_limit_s": 600,
            "container": {"cpus": 4, "memory_bytes": 8 * 1024**3,
                          "network": "bridge", "gpu": False, "qemu": False},
            "cache_files": [{"path": row["path"], "bytes": row["bytes"],
                              "sha256": file_digest(Path(row["path"]))["sha256"]}
                             for row in cache_files],
            "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "frozen_at_monotonic_ns": time.monotonic_ns(),
        }
        total_start = int(identity["frozen_at_monotonic_ns"]) / 1e9
        request = {
            "output_dir": "/workspace/output", "instruction": instruction,
            "recursion_limit": 32, "budget": REQUEST_BUDGET,
            "frozen_identity": identity,
        }
        write_exclusive(request_path, request)
        write_exclusive(RUN_ROOT / "launch-record.json", {
            "schema": "openstoryline-native-short-launch-v1", "run_id": run_id,
            "image": image, "source_sha256": file_digest(SOURCE)["sha256"],
            "budget": REQUEST_BUDGET, "network": "bridge",
            "credential_read": False, "request_sent": False,
        })
    run_id = str(identity["run_id"])
    identity["host_execution_files"] = {}
    for path in (
        Path(__file__), Path(formal.__file__),
        formal.ENV_ROOT / "source/openstoryline_task_entry.py",
        formal.ENV_ROOT / "source/openstoryline_mcp_server.py",
        formal.ENV_ROOT / "source/src/open_storyline/agent.py",
        formal.ENV_ROOT / "source/src/open_storyline/mcp/request_ledger.py",
        formal.ENV_ROOT / "source/src/open_storyline/mcp/sampling_handler.py",
        formal.ENV_ROOT / "source/src/open_storyline/mcp/register_tools.py",
        formal.ENV_ROOT / "source/asr_adapter/cache_preflight.py",
        ROOT / "src/agent_workload_characterization/runners/container_runtime.py",
    ):
        identity["host_execution_files"][str(path.relative_to(ROOT))] = file_digest(path)
    identity["identity_sha256"] = identity_sha(identity)
    request["frozen_identity"] = identity
    with (RUN_ROOT / "short-task-identity.json").open("w", encoding="utf-8") as stream:
        json.dump(identity, stream, ensure_ascii=False, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    with request_path.open("w", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    shutil.copy2(RUN_ROOT / "short-task-identity.json", output / "short-task-identity.json")
    with (RUN_ROOT / "launch-events.jsonl").open("a", encoding="utf-8") as events:
        events.write(json.dumps({"event": "pre_request_startup_repair",
                                 "credential_source": str(formal.CREDENTIAL_FILE),
                                 "request_already_sent": False,
                                 "monotonic_ns": time.monotonic_ns()}) + "\n")
        events.flush(); os.fsync(events.fileno())
    total_deadline = total_start + 600
    agent_deadline = total_deadline - 30
    if time.monotonic() >= agent_deadline:
        raise TimeoutError("short-task budget expired before container launch; no model request sent")

    # Credential access happens only after all local paths, image and cache checks.
    try:
        api_key = formal.safe_credential()
    except Exception as exc:
        with (RUN_ROOT / "startup-errors.jsonl").open("a", encoding="utf-8") as errors:
            errors.write(json.dumps({"phase": "credential_preflight",
                                     "error_type": type(exc).__name__,
                                     "message": str(exc)[:400],
                                     "model_requests_sent": 0,
                                     "monotonic_ns": time.monotonic_ns()}) + "\n")
            errors.flush(); os.fsync(errors.fileno())
        raise
    spec = formal.build_container_spec(
        run_id=run_id, output_dir=output, request_path=request_path,
        api_key=api_key, run_deadline=agent_deadline, input_dir=input_dir,
    )
    runtime = DockerCliRuntime(authorized=True, collection="OPENSTORYLINE-SHORT")
    import video_use_edit_pilot_01 as resource_runtime
    resource_runtime.SAMPLE_S = 0.5
    handle = None
    sampler = None
    started_ns = time.monotonic_ns()
    result = None
    termination_error = None
    try:
        handle = runtime.start(spec, deadline=agent_deadline)
        sampler = resource_runtime.Sampler(runtime, handle)
        sampler.start()
        (RUN_ROOT / "launch-record.json").write_text(json.dumps({
            "schema": "openstoryline-native-short-launch-v1",
            "run_id": run_id, "image": image,
            "source_sha256": file_digest(SOURCE)["sha256"],
            "budget": REQUEST_BUDGET, "network": "bridge",
            "credential_read": True, "request_sent": True,
            "container_id": handle.container_id,
            "started_monotonic_ns": started_ns,
        }, ensure_ascii=False, indent=2) + "\n")
        remaining = max(1, int(agent_deadline - time.monotonic()))
        result = runtime.execute(
            handle,
            "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json",
            timeout_s=remaining, output_limit=2_000_000,
        )
    except BaseException as exc:
        termination_error = {"type": type(exc).__name__, "message": str(exc)[:800]}
    finally:
        if sampler is not None:
            sampler.stop_event.set()
            sampler.join(timeout=10)
            from openstoryline_pilot_entry import _save_samples
            _save_samples(RUN_ROOT, sampler.rows)
        removal = None
        if handle is not None:
            try:
                runtime.stop(handle, timeout_s=20)
                removal = runtime.verify_removal(handle, timeout_s=20)
            except BaseException as exc:
                removal = f"check_failed:{type(exc).__name__}"
        (RUN_ROOT / "launcher-result.json").write_text(json.dumps({
            "schema": "openstoryline-native-short-result-v1",
            "returncode": result.get("returncode") if result else None,
            "timed_out": result.get("timed_out", False) if result else False,
            "termination": result.get("termination") if result else termination_error,
            "output_tail": (result.get("output", "")[-12000:] if result else ""),
            "container_id": handle.container_id if handle else None,
            "container_removal": removal,
            "sampler_rows": len(sampler.rows) if sampler else 0,
            "start_monotonic_ns": started_ns,
            "end_monotonic_ns": time.monotonic_ns(),
            "agent_container_wall_s": (time.monotonic_ns() - started_ns) / 1e9,
            "short_task_total_wall_s": time.monotonic() - total_start,
        }, ensure_ascii=False, indent=2) + "\n")
    event_path = output / "model-requests.jsonl"
    events = []
    if event_path.is_file():
        for line in event_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    def event_usage_tokens(event: dict) -> int:
        usage = event.get("usage") or {}
        total = usage.get("total_tokens")
        if total is not None:
            return int(total or 0)
        return int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)

    report = {
        "schema": "openstoryline-native-short-report-v1",
        "identity_sha256": identity["identity_sha256"],
        "image": {"tag": formal.IMAGE, "id": formal.IMAGE_ID, "platform": formal.PLATFORM},
        "source": {"path": str(SOURCE.relative_to(ROOT)), **file_digest(SOURCE)},
        "route": ROUTE, "budget": REQUEST_BUDGET,
        "logical_requests": sum(e.get("event") == "request_started" for e in events),
        "returned_usage_tokens": sum(event_usage_tokens(e) for e in events
                                      if e.get("event") == "request_finished"),
        "request_ledger": "output/model-requests.jsonl",
        "mcp_log": "output/mcp-server.log",
        "agent_messages": "output/native-message-events.jsonl",
        "agent_result": "output/agent-result.json",
        "launcher_result": "launcher-result.json",
        "credential_material_saved": False,
        "score": "not_applicable_short_task",
    }
    write_exclusive(RUN_ROOT / "run-report.json", report)
    manifest(RUN_ROOT)
    return 0 if result and result.get("returncode") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
