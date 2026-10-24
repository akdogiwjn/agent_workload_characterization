from __future__ import annotations

import hashlib
import json
import os
from pathlib import PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path("/home/lcq/agent_workload_characterization")
ENV_ROOT = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01"
TASK = "OPENSTORYLINE-EDIT-PILOT-02"
TASK_ROOT = ROOT / "references/repos/agentic-vbench/tasks/agentic_vbench_repair/exp-disfluency-interview-3-task01"
INPUT_DIR = ROOT / "data/workloads/video/editing/avb-disfluency-interview-3-v1/input"
INPUT = INPUT_DIR / "source.mp4"
PLAN_ROOT = ROOT / "env/video/openstoryline/OPENSTORYLINE-EDIT-PILOT-02/formal"
IDENTITY_PATH = PLAN_ROOT / "frozen-identity.json"
APPROVAL_PATH = PLAN_ROOT / "APPROVAL.json"
RAW_PARENT = ROOT / "data/raw/generated" / TASK
REPORT_ROOT = ROOT / "reports/resource" / TASK
IMAGE = "openstoryline-task:arm64-native-confirm-flow-03"
IMAGE_ID = "sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0"
PLATFORM = "linux/arm64"
UPSTREAM_COMMIT = "c9e945215586f45c12a61c1951ee9a8e9c43a027"
TASK_COMMIT = "b2764ed4b2a4b5a1737026b63887b50bba62f793"
CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
PREPARATION_GATE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-agent-gate.json"
PREPARATION_RENDER = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-06/output/render-audio-result.json"
VERIFIER_DIR = ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier"
VERIFIER_PYTHON = Path("/home/lcq/.venvs/video-use-pilot03-verifier/bin/python")
TOTAL_BUDGET_S = 2700
AGENT_BUDGET_S = 1800
VERIFIER_BUDGET_S = 600
CLEANUP_RESERVE_S = 300

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    ContainerSpec, DockerCliRuntime,
)
from asr_cache_runtime import docker_asr_args, validate_host_cache  # noqa: E402


def digest(path: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def atomic_write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    """Durably publish a host-owned JSON record without touching container files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            raise FileExistsError(path)
        os.replace(temporary, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def persist_agent_execution(raw: Path, result: dict[str, Any] | None = None,
                            error: BaseException | None = None,
                            started_monotonic_ns: int | None = None) -> dict[str, Any]:
    """Persist execute() outcome immediately in a host-owned file."""
    record: dict[str, Any] = {"recorded_monotonic_ns": time.monotonic_ns()}
    record["started_monotonic_ns"] = started_monotonic_ns
    record["wall_s"] = ((record["recorded_monotonic_ns"] - started_monotonic_ns) / 1e9
                        if isinstance(started_monotonic_ns, int) else None)
    if result is not None:
        record.update({key: result.get(key) for key in
                       ("returncode", "timed_out", "termination", "output")})
        record["output"] = str(record.get("output") or "")[-8000:]
        record["status"] = "returned"
    if error is not None:
        record["status"] = "raised"
        record["error_type"] = type(error).__name__
        record["error"] = str(error)[:2000]
    atomic_write_json(raw / "agent-execution.json", record, exclusive=True)
    return record


def execute_and_persist(runtime: Any, handle: Any, command: str, *, timeout_s: int,
                        output_limit: int, raw: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the bounded container command and immediately archive its process result."""
    started_ns = time.monotonic_ns()
    try:
        result = runtime.execute(handle, command, timeout_s=timeout_s,
                                 output_limit=output_limit)
    except BaseException as exc:
        persist_agent_execution(raw, error=exc, started_monotonic_ns=started_ns)
        raise
    record = persist_agent_execution(raw, result=result, started_monotonic_ns=started_ns)
    return result, record


def gibibytes(byte_count: int | float | None) -> float | None:
    """Convert bytes to GiB (base 1024), preserving missing measurements."""
    return None if byte_count is None else float(byte_count) / (1024 ** 3)


def _directory_measurement(path: Path) -> dict[str, Any]:
    try:
        value = _du(path)
        return {"path": str(path), "bytes": value,
                "scan_status": "complete" if value is not None else "unavailable"}
    except Exception as exc:
        return {"path": str(path), "bytes": None, "scan_status": "error",
                "error_type": type(exc).__name__, "error": str(exc)[:1000]}


def finalize_host_attempt(*, raw: Path, output: Path, project: Path,
                          boundaries_before: dict[str, Any], report: dict[str, Any],
                          runtime: Any, handle: Any, sampler: Any,
                          primary_error: BaseException | None = None,
                          input_dir: Path = INPUT_DIR,
                          postprocess: Any = None, verifier: Any = None,
                          report_writer: Any = atomic_write_json,
                          manifest_writer: Any = None) -> dict[str, Any]:
    """Stop sampling/work, then independently postprocess and archive host records.

    Container-owned agent-result/session-status are read-only inputs. Every cleanup
    operation is attempted even when another cleanup or report operation fails.
    """
    cleanup_errors: list[dict[str, str]] = []
    sample_status = "not_started"
    if sampler is not None:
        try:
            sampler.stop_event.set()
            sampler.join(timeout=10)
            is_alive = getattr(sampler, "is_alive", None)
            if callable(is_alive) and is_alive():
                raise TimeoutError("resource sampler thread remained alive after join timeout")
            report["sampler_rows"] = list(getattr(sampler, "rows", []))
            _save_samples(raw, report["sampler_rows"])
            sample_status = "stopped_and_archived"
            try:
                import video_use_edit_pilot_01 as resource_runtime
                rows = report["sampler_rows"]
                cgroup_rows = resource_runtime.resource_rows(
                    rows, getattr(handle, "container_id", None))
                report["resource_metrics"] = resource_runtime.resource_metrics(rows)
                report["resource_metrics"]["max_sampled_memory_current_gib"] = gibibytes(
                    report["resource_metrics"].get("max_sampled_memory_current_bytes"))
                report["resource_metrics"]["max_kernel_memory_peak_gib"] = gibibytes(
                    report["resource_metrics"].get("max_kernel_memory_peak_bytes"))
                report["resource_summary"] = {
                    "cgroup_rows": len(cgroup_rows),
                    "cgroup_version": getattr(handle, "cgroup_version", None),
                    "mem_current_unit": "bytes",
                    "mem_current_source": "cgroup memory.current (or cgroup v1 memory.usage_in_bytes as exposed by sampler)",
                    "mem_peak_unit": "bytes",
                    "netns_scope": "per-interface container namespace counters; not API-specific",
                }
            except Exception as exc:
                cleanup_errors.append({"scope": "resource_summary", "type": type(exc).__name__,
                                       "error": str(exc)[:1000]})
        except Exception as exc:
            sample_status = "stop_or_archive_error"
            cleanup_errors.append({"scope": "sampler_stop_or_archive", "type": type(exc).__name__,
                                   "error": str(exc)[:1000]})

    removal = "not_started"
    if handle is not None:
        try:
            runtime.stop(handle, timeout_s=20)
        except Exception as exc:
            cleanup_errors.append({"scope": "container_stop", "type": type(exc).__name__,
                                   "error": str(exc)[:1000]})
        try:
            removal = runtime.verify_removal(handle, timeout_s=20)
        except Exception as exc:
            removal = "verification_error"
            cleanup_errors.append({"scope": "container_removal_verification",
                                   "type": type(exc).__name__, "error": str(exc)[:1000]})

    if primary_error is not None:
        report["termination_reason"] = {"type": type(primary_error).__name__,
                                        "message": str(primary_error)[:2000]}
    report["cleanup_errors"] = cleanup_errors
    report["container_removal"] = removal
    report["sampling_status"] = sample_status
    report["directory_boundaries"] = {}
    for name, path in (("input", input_dir), ("project", project), ("submission", output)):
        report["directory_boundaries"][name] = {
            "before": boundaries_before.get(name, {"bytes": None, "scan_status": "not_persisted"}),
            "after": _directory_measurement(path),
        }

    host_record = {
        "schema": "openstoryline-host-finalization-v1",
        "run_id": report.get("run_id"),
        "attempt_start_monotonic_ns": report.get("start_monotonic_ns"),
        "agent_execution": report.get("agent_execution", {"status": "not_returned"}),
        "primary_error": report.get("termination_reason"),
        "sampling_status": sample_status,
        "container_removal": removal,
        "cleanup_errors": list(cleanup_errors),
        "directory_boundaries": report["directory_boundaries"],
        "report_generation_status": "pending",
        "manifest_generation_status": "pending",
    }
    if manifest_writer is None:
        manifest_writer = _write_manifest
    try:
        report_writer(raw / "host-finalization.json", host_record)
    except Exception as exc:
        cleanup_errors.append({"scope": "host_finalization_record", "type": type(exc).__name__,
                               "error": str(exc)[:1000]})
        report["cleanup_errors"] = cleanup_errors

    result_path = output / "agent-result.json"
    result_status: dict[str, Any] | None = None
    if result_path.is_file():
        try:
            result_status = json.loads(result_path.read_text(encoding="utf-8"))
            # Never write this container-owned file from the host.
            report["container_agent_result"] = result_status
        except Exception as exc:
            report["container_agent_result_read_error"] = {
                "type": type(exc).__name__, "error": str(exc)[:1000]}
    report["agent_terminal_status"] = (result_status or {}).get("status", "unknown")
    execution = report.get("agent_execution") or {}
    report["submission_status"] = "not_verified"
    if postprocess is not None:
        try:
            report.update(postprocess())
            if (report.get("render_export", {}).get("status") == "exported_and_verified"
                    and report.get("cuts_export", {}).get("status") == "derived_from_final_timeline"):
                report["submission_status"] = "exported_and_verified"
        except Exception as exc:
            report["postprocess_error"] = {"type": type(exc).__name__, "error": str(exc)[:2000]}
    has_submission = ((output / "output.mp4").is_file() and (output / "cuts.json").is_file()
                      and report["submission_status"] == "exported_and_verified")
    report["verifier"] = {"status": "not_run_no_submission", "reward": None,
                          "evaluation_complete": False}
    if has_submission and execution.get("returncode") == 0 and not execution.get("timed_out", False):
        try:
            if verifier is not None:
                report["verifier"] = verifier(report)
        except Exception as exc:
            report["verifier"] = {"status": "error", "evaluation_complete": False,
                                  "reward": None, "error_type": type(exc).__name__,
                                  "error": str(exc)[:2000]}

    report["pre_archive_end_monotonic_ns"] = time.monotonic_ns()
    start_ns = report.get("start_monotonic_ns")
    report["pre_archive_wall_s"] = ((report["pre_archive_end_monotonic_ns"] - start_ns) / 1e9
                                   if isinstance(start_ns, int) else None)
    # Keep the hashed report immutable after archiving. The already-excluded
    # host control record publishes the final observation, including archive
    # work, without invalidating the report's manifest entry.
    report["end_monotonic_ns"] = None
    report["total_wall_s"] = None
    report["total_wall_source"] = "host-finalization.json"
    report["logical_requests"] = _count_event(output / "model-requests.jsonl", "request_started")
    report["request_events"] = str(output / "model-requests.jsonl")
    generation = {"schema": "openstoryline-report-generation-v1", "run_id": report.get("run_id"),
                  "report_status": "pending", "manifest_status": "pending", "errors": []}
    try:
        report_writer(raw / "run-report.json", report, exclusive=True)
        generation["report_status"] = "complete"
    except Exception as exc:
        generation["report_status"] = "error"
        generation["errors"].append({"scope": "run_report", "type": type(exc).__name__,
                                     "error": str(exc)[:2000]})
    try:
        generation["manifest_status"] = "pending"
        report_writer(raw / "report-generation-status.json", generation)
        manifest_writer(raw)
        generation["manifest_status"] = "complete"
        report_writer(raw / "report-generation-status.json", generation)
    except Exception as exc:
        generation["manifest_status"] = "error"
        generation["errors"].append({"scope": "manifest", "type": type(exc).__name__,
                                     "error": str(exc)[:2000]})
        try:
            report_writer(raw / "report-generation-status.json", generation)
        except Exception:
            pass
    host_record["report_generation_status"] = generation["report_status"]
    host_record["manifest_generation_status"] = generation["manifest_status"]
    host_record["report_generation_errors"] = generation["errors"]
    end_ns = time.monotonic_ns()
    total_wall_s = ((end_ns - start_ns) / 1e9 if isinstance(start_ns, int) else None)
    host_record.update({
        "end_monotonic_ns": end_ns,
        "total_wall_s": total_wall_s,
        "wall_end_event": "archive_attempts_finished_before_final_control_record_write",
    })
    try:
        report_writer(raw / "host-finalization.json", host_record)
    except Exception as exc:
        report["host_finalization_update_error"] = {"type": type(exc).__name__,
                                                     "error": str(exc)[:1000]}
    report["end_monotonic_ns"] = end_ns
    report["total_wall_s"] = total_wall_s
    report["report_generation"] = generation
    return report


def identity_hash(identity: dict[str, Any]) -> str:
    body = {k: v for k, v in identity.items() if k != "identity_sha256"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_mount_and_env() -> tuple[list[str], dict[str, str]]:
    args = docker_asr_args()
    mounts: list[str] = []
    env: dict[str, str] = {}
    i = 0
    while i < len(args):
        flag, value = args[i], args[i + 1]
        if flag == "--mount":
            mounts.append(value)
        elif flag == "--env":
            name, _, setting = value.partition("=")
            env[name] = setting
        else:
            raise ValueError(f"unexpected ASR cache argument {flag}")
        i += 2
    return mounts, env


def build_container_spec(*, run_id: str, output_dir: Path, request_path: Path,
                         api_key: str | None, run_deadline: float,
                         input_dir: Path = INPUT_DIR,
                         network: str = "bridge",
                         offline_fake_model: bool = False) -> ContainerSpec:
    cache_files = validate_host_cache()
    if len(cache_files) != 16 or not all(row["readable"] for row in cache_files):
        raise RuntimeError("registered ASR cache preflight failed")
    cache_mounts, cache_env = cache_mount_and_env()
    mounts = [
        f"type=bind,src={input_dir.resolve()},dst=/workspace/input,readonly",
        f"type=bind,src={output_dir.resolve()},dst=/workspace/output",
        f"type=bind,src={request_path.resolve()},dst=/workspace/request.json,readonly",
        f"type=bind,src={(output_dir.parent / 'project').resolve()},dst=/workspace/project",
        *cache_mounts,
    ]
    env = {**cache_env, "OPENSTORYLINE_CONFIG": "/opt/openstoryline/config.toml"}
    if offline_fake_model:
        if api_key is not None or network != "none":
            raise ValueError("offline fake-model containers require no key and network=none")
        env["OPENSTORYLINE_ENABLE_OFFLINE_FAKE_MODEL"] = "1"
    elif api_key:
        env["DASHSCOPE_API_KEY"] = api_key
    return ContainerSpec(
        run_id=run_id, scope="openstoryline_agent", image=IMAGE,
        cwd="/workspace", env=env, timeout_s=max(1, int(run_deadline - time.monotonic())),
        mem_limit="8g", cpu_limit="4", network=network, platform=PLATFORM,
        mounts=mounts, pull="never",
    )


def namespace_state() -> dict[str, Any]:
    raw_children = sorted(p.name for p in RAW_PARENT.iterdir()) if RAW_PARENT.is_dir() else []
    return {
        "formal_plan_exists": PLAN_ROOT.exists(),
        "identity_exists": IDENTITY_PATH.is_file(),
        "approval_exists": APPROVAL_PATH.is_file(),
        "raw_attempts": raw_children,
        "namespace_clean": not raw_children,
    }


def preparation_readiness() -> dict[str, Any]:
    blockers = []
    if not INPUT.is_file():
        blockers.append("registered_input_missing")
    if not (TASK_ROOT / "steps/solve/instruction.md").is_file():
        blockers.append("official_instruction_missing")
    if not VERIFIER_PYTHON.is_file() or not all((VERIFIER_DIR / name).is_file()
                                                 for name in ("entry.py", "judge.py",
                                                              "requirements.lock",
                                                              "verifier-environment.json")):
        blockers.append("verified_verifier_environment_missing")
    try:
        cache = validate_host_cache()
    except Exception as exc:
        cache = []
        blockers.append(f"asr_cache_preflight:{type(exc).__name__}")
    if not PREPARATION_RENDER.is_file():
        blockers.append("offline_audio_render_evidence_missing")
    else:
        try:
            if json.loads(PREPARATION_RENDER.read_text()).get("status") != "PASS":
                blockers.append("offline_audio_render_failed")
        except (OSError, json.JSONDecodeError):
            blockers.append("offline_audio_render_record_invalid")
    if not PREPARATION_GATE.is_file():
        blockers.append("real_native_agent_gate_not_passed_or_recorded")
    else:
        try:
            gate = json.loads(PREPARATION_GATE.read_text())
            expected_tools = {"load_media", "split_shots", "local_asr", "speech_rough_cut",
                              "plan_timeline_pro", "render_video"}
            gate_tools = set(gate.get("tool_names", []))
            if (gate.get("status") != "PASS"
                    or gate.get("native_langchain_agent_verified") is not True
                    or int(gate.get("real_model_requests_agent", 0)) < 1
                    or int(gate.get("real_model_requests_node", 0)) < 1
                    or not expected_tools.issubset(gate_tools)
                    or gate.get("local_asr_real") is not True
                    or gate.get("audio_video_contract") != "PASS"
                    or gate.get("container_cleanup") != "PASS"):
                blockers.append("real_native_agent_gate_not_passed")
        except (OSError, json.JSONDecodeError):
            blockers.append("real_native_agent_gate_record_invalid")
    state = namespace_state()
    if not state["namespace_clean"]:
        blockers.append("formal_attempt_namespace_occupied")
    return {"formal_ready": not blockers, "blockers": blockers,
            "namespace": state, "cache_files_readable": len(cache),
            "input": digest(INPUT) if INPUT.is_file() else None,
            "task_instruction": digest(TASK_ROOT / "steps/solve/instruction.md")
            if (TASK_ROOT / "steps/solve/instruction.md").is_file() else None}


def write_preflight_record() -> dict[str, Any]:
    run_root = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/formal-entry-02"
    run_root.mkdir(parents=True, exist_ok=False)
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    inspect = subprocess.run(docker + ["image", "inspect", IMAGE, "--format",
                                       "{{.Id}} {{.Os}}/{{.Architecture}}"],
                             capture_output=True, text=True)
    ready = preparation_readiness()
    ready["image"] = {"tag": IMAGE, "expected_id": IMAGE_ID,
                      "inspect": inspect.stdout.strip() if inspect.returncode == 0 else None,
                      "matches": inspect.returncode == 0
                      and inspect.stdout.strip() == f"{IMAGE_ID} linux/arm64"}
    if not ready["image"]["matches"]:
        ready["formal_ready"] = False
        ready["blockers"].append("formal_image_identity_mismatch")
    record = {"schema": "openstoryline-formal-entry-preflight-v1",
              "checked_monotonic_ns": time.monotonic_ns(), **ready,
              "approval_created": False, "attempt_created": False,
              "credential_read": False}
    (run_root / "preflight.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def freeze_identity() -> dict[str, Any]:
    readiness = preparation_readiness()
    if not readiness["formal_ready"]:
        raise RuntimeError(f"formal identity cannot freeze before all gates pass: {readiness['blockers']}")
    if PLAN_ROOT.exists() or (RAW_PARENT.exists() and any(RAW_PARENT.iterdir())):
        raise RuntimeError("formal namespace already exists; refusing to freeze or rename it")
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    inspect = subprocess.run(docker + ["image", "inspect", IMAGE, "--format",
                                       "{{.Id}} {{.Os}}/{{.Architecture}}"],
                             capture_output=True, text=True, check=True).stdout.strip()
    if inspect != f"{IMAGE_ID} linux/arm64":
        raise RuntimeError("candidate image identity/platform mismatch")
    upstream = subprocess.run(["git", "-C", str(ROOT / "references/repos/FireRed-OpenStoryline"),
                               "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    task_commit = subprocess.run(["git", "-C", str(ROOT / "references/repos/agentic-vbench"),
                                  "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if upstream != UPSTREAM_COMMIT or not task_commit.startswith(TASK_COMMIT):
        raise RuntimeError("upstream source or registered task commit mismatch")
    budget = {"max_logical_requests": 60,
              "max_observed_tokens_soft_threshold": 1_000_000,
              "max_output_tokens_per_request": 32768}
    route = {"protocol": "Chat Completions", "model": "qwen3.7-plus",
             "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "credential_env": "DASHSCOPE_API_KEY", "sdk_retries": 0,
             "application_retries": 0}
    source_paths = [
        ROOT / "env/video/openstoryline/edit-pilot-02/runtime/openstoryline_pilot_entry.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/runtime/asr_cache_runtime.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/openstoryline_task_entry.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/config.toml",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/resource/fonts/font_info.json",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/.storyline/skills/speech_rough_cut_skill/SKILL.md",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/confirmation_flow.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.confirm-flow-03",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/offline_fake_model.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/openstoryline_mcp_server.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/agent.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/nodes/node_manager.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/nodes/core_nodes/render_video.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/nodes/core_nodes/split_shots.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/nodes/core_nodes/speech_rough_cut.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/request_ledger.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/sampling_handler.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/register_tools.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/hooks/node_interceptors.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/tests/test_native_entry_repair.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/tests/test_confirmation_flow.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/asr_adapter/cache_preflight.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/asr-cache-contract.json",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source-manifest.json",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.formal-entry",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.formal-entry-v13",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-02",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-03",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-04",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-05",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-06",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-07",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-06",
        ROOT / "src/agent_workload_characterization/runners/container_runtime.py",
        ROOT / "scripts/video_use_edit_pilot_01.py",
        TASK_ROOT / "steps/solve/instruction.md", INPUT,
        ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/run_offline_validation.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/continue_offline_validation.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04/run_short_task.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04/review_short_task.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04/recover_short_task_postflight.py",
        ROOT / "env/video/openstoryline/edit-pilot-02/runtime/short_task_budget.py",
        ROOT / "tests/test_openstoryline_short_budget.py",
        ROOT / "tests/test_openstoryline_parent_deadline_cleanup.py",
        VERIFIER_DIR / "entry.py", VERIFIER_DIR / "judge.py",
        VERIFIER_DIR / "requirements.lock", VERIFIER_DIR / "verifier-environment.json",
    ]
    cache_records = validate_host_cache()
    cache_manifest = [{"path": row["path"], "bytes": row["bytes"],
                       "sha256": digest(Path(row["path"]))["sha256"]}
                      for row in cache_records]
    identity = {
        "schema": "openstoryline-edit-pilot-02-identity-v1",
        "namespace": TASK,
        "run_id": time.strftime("%Y%m%dT%H%M%SZ-openstoryline-edit-02", time.gmtime()),
        "attempt": 1,
        "upstream_commit": upstream,
        "task_commit": task_commit,
        "input": {"path": str(INPUT.relative_to(ROOT)), **digest(INPUT)},
        "files": {str(path.relative_to(ROOT)): digest(path) for path in source_paths},
        "image": {"tag": IMAGE, "id": IMAGE_ID, "platform": PLATFORM},
        "model_route": route,
        "budget": budget,
        "budget_semantics": {
            "logical_requests": "hard per-run pre-send count gate",
            "observed_tokens": "post-response soft threshold; current in-flight response may cross it",
            "output_tokens": "hard per-request generation limit sent with every model call",
            "ledger": "new unique output/model-requests.jsonl per run; prior prep ledger retained",
        },
        "wall_limits_s": {"total": TOTAL_BUDGET_S, "agent": AGENT_BUDGET_S,
                          "verifier": VERIFIER_BUDGET_S,
                          "cleanup_reserve": CLEANUP_RESERVE_S},
        "resources": {"cpus": 4, "memory_bytes": 8 * 1024**3,
                      "sample_interval_target_s": 0.5,
                      "scope": "whole Agent container cgroup including MCP/ASR/FFmpeg children",
                      "network": "container netns per interface; not API-specific"},
        "asr_cache": {"contract": str((ENV_ROOT / "asr-cache-contract.json").relative_to(ROOT)),
                      "host_root": str((ENV_ROOT / "models").relative_to(ROOT)),
                      "container_mount": "/root/.cache/modelscope:ro",
                      "files": cache_manifest},
        "verifier": {"python": str(VERIFIER_PYTHON),
                     "environment": str(VERIFIER_DIR / "verifier-environment.json"),
                     "judge_sha256": digest(VERIFIER_DIR / "judge.py")["sha256"]},
        "preparation_gate": {"path": str(PREPARATION_GATE.relative_to(ROOT)),
                              "sha256": digest(PREPARATION_GATE)["sha256"]},
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_at_monotonic_ns": time.monotonic_ns(),
        "formal_gate_status": "PASS",
    }
    identity["identity_sha256"] = identity_hash(identity)
    PLAN_ROOT.mkdir(parents=True, exist_ok=False)
    plan = {"schema": "openstoryline-edit-pilot-02-plan-v1",
            "identity_sha256": identity["identity_sha256"],
            "single_attempt": True, "model_route": route, "budget": budget,
            "resources": identity["resources"], "wall_limits_s": identity["wall_limits_s"],
            "approval": "created only by --execute after matching identity and explicit flag"}
    for path, value in ((PLAN_ROOT / "environment-plan.json", plan), (IDENTITY_PATH, identity)):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {"status": "FROZEN", "identity_sha256": identity["identity_sha256"],
            "run_id": identity["run_id"], "approval_created": False,
            "attempt_created": False}


def load_runtime_approval() -> tuple[dict[str, Any], dict[str, Any]]:
    if not IDENTITY_PATH.is_file():
        raise RuntimeError("frozen identity is required")
    identity = json.loads(IDENTITY_PATH.read_text())
    if identity.get("identity_sha256") != identity_hash(identity):
        raise RuntimeError("frozen identity content hash mismatch")
    if identity.get("namespace") != TASK or identity.get("formal_gate_status") != "PASS":
        raise RuntimeError("frozen identity is not bound to a passed preparation gate")
    if not preparation_readiness()["formal_ready"]:
        raise RuntimeError("current preparation gates are not ready")
    if not namespace_state()["namespace_clean"]:
        raise RuntimeError("formal namespace already contains an attempt")
    return identity, {}


def safe_credential() -> str:
    for line in CREDENTIAL_FILE.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith("export "):
            text = text[7:]
        if not text or text.startswith("#"):
            continue
        key, sep, value = text.partition("=")
        if sep and key.strip() == "DASHSCOPE_API_KEY":
            secret = value.strip().strip("\"'")
            if secret:
                return secret
    raise RuntimeError("registered DASHSCOPE_API_KEY missing")


def execute_once() -> dict[str, Any]:
    identity, approval = load_runtime_approval()
    run_id = str(identity["run_id"])
    if APPROVAL_PATH.exists():
        approval = json.loads(APPROVAL_PATH.read_text())
        frozen_sha = hashlib.sha256(IDENTITY_PATH.read_bytes()).hexdigest()
        if approval.get("frozen_identity_sha256") != frozen_sha:
            raise RuntimeError("existing APPROVAL does not match frozen identity")
    else:
        approval = {"schema": "openstoryline-edit-pilot-02-approval-v1",
                    "approval_id": uuid.uuid4().hex,
                    "namespace": TASK, "run_id": run_id,
                    "frozen_identity_sha256": hashlib.sha256(IDENTITY_PATH.read_bytes()).hexdigest(),
                    "approved_by": "explicit user instruction in this session",
                    "approved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with APPROVAL_PATH.open("x", encoding="utf-8") as stream:
            json.dump(approval, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    secret = safe_credential()
    raw = RAW_PARENT / run_id
    raw.mkdir(parents=True, exist_ok=False)
    output = raw / "workspace/output"
    project = raw / "workspace/project"
    output.mkdir(parents=True)
    project.mkdir(parents=True)
    request_path = raw / "request.json"
    task_instruction = (TASK_ROOT / "steps/solve/instruction.md").read_text(encoding="utf-8")
    budget = identity["budget"]
    container_identity = dict(identity)
    container_identity["identity_sha256"] = identity_hash(identity)
    request = {
        "output_dir": "/workspace/output",
        "instruction": (task_instruction + "\n\nUse the native OpenStoryline LangChain agent and registered MCP tools. "
                        "Perform actual local ASR, decide the edit autonomously, render the native timeline, "
                        "include the original audio with include_video_audio=true and video_volume_scale=1.0, "
                        "preserve the registered source size and frame rate, and export cuts.json from the "
                        "final rendered source intervals. Do not use golden "
                        "ranges, prior agent selections, or score feedback."),
        "recursion_limit": 32,
        "budget": budget,
        "frozen_identity": container_identity,
    }
    with request_path.open("x", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())

    start_mono = time.monotonic()
    start_ns = int(start_mono * 1e9)
    total_deadline = start_mono + TOTAL_BUDGET_S
    agent_deadline = min(start_mono + AGENT_BUDGET_S,
                         total_deadline - VERIFIER_BUDGET_S - CLEANUP_RESERVE_S)
    report: dict[str, Any] = {
        "schema": "openstoryline-edit-pilot-02-run-v1", "namespace": TASK,
        "run_id": run_id, "attempt": 1, "approval_id": approval.get("approval_id"),
        "frozen_identity_sha256": hashlib.sha256(IDENTITY_PATH.read_bytes()).hexdigest(),
        "start_monotonic_ns": start_ns, "budget": budget,
        "image": {"tag": IMAGE, "id": IMAGE_ID, "platform": PLATFORM},
        "source": digest(INPUT), "phases": [], "sampler_rows": [],
        "resource_scope": "Agent container cgroup, including MCP/ASR/FFmpeg children",
    }
    atomic_write_json(raw / "run-start.json", {
        "schema": "openstoryline-run-start-v1", "run_id": run_id,
        "attempt_start_monotonic_ns": start_ns,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_deadline_monotonic_ns": int(total_deadline * 1e9),
        "agent_deadline_monotonic_ns": int(agent_deadline * 1e9),
        "wall_limits_s": {"total": TOTAL_BUDGET_S, "agent": AGENT_BUDGET_S,
                          "verifier": VERIFIER_BUDGET_S,
                          "cleanup_reserve": CLEANUP_RESERVE_S},
        "budget": budget, "phase": "pre_container_start",
    }, exclusive=True)
    sys.path.insert(0, str(ROOT / "scripts"))
    import video_use_edit_pilot_01 as resource_runtime
    resource_runtime.SAMPLE_S = 0.5
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    runtime = DockerCliRuntime(authorized=True, collection=TASK)
    handle = None
    sampler = None
    boundaries_before = {"input": _directory_measurement(INPUT_DIR),
                         "project": _directory_measurement(project),
                         "submission": _directory_measurement(output)}
    atomic_write_json(raw / "directory-boundaries-before.json", {
        "schema": "openstoryline-directory-boundaries-before-v1",
        "measured_monotonic_ns": time.monotonic_ns(), "directories": boundaries_before,
    }, exclusive=True)
    primary_error: BaseException | None = None
    execution_start_ns: int | None = None
    try:
        spec = build_container_spec(run_id=run_id, output_dir=output,
                                    request_path=request_path, api_key=secret,
                                    run_deadline=agent_deadline)
        handle = runtime.start(spec, deadline=agent_deadline)
        report["container"] = {"id": handle.container_id, "cgroup_version": handle.cgroup_version,
                               "cpus": 4, "memory_bytes": 8589934592,
                               "network_scope": "container netns interfaces; not API-exclusive"}
        sampler = resource_runtime.Sampler(runtime, handle)
        sampler.start()
        command = "python3 /opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json"
        timeout = max(1, min(AGENT_BUDGET_S, int(agent_deadline - time.monotonic())))
        result, execution_record = execute_and_persist(
            runtime, handle, command, timeout_s=timeout,
            output_limit=2_000_000, raw=raw)
        execution_start_ns = execution_record["started_monotonic_ns"]
        report["agent_execution"] = execution_record
        report["agent_returncode"] = result.get("returncode")
        report["phases"].append({"phase": "agent", "start_monotonic_ns": execution_start_ns,
                                 "end_monotonic_ns": report["agent_execution"]["recorded_monotonic_ns"],
                                 "returncode": result.get("returncode"),
                                 "timed_out": result.get("timed_out", False),
                                 "termination": result.get("termination"),
                                 "output_tail": result.get("output", "")[-8000:]})
    except BaseException as exc:
        primary_error = exc
        if (raw / "agent-execution.json").is_file():
            try:
                report["agent_execution"] = json.loads(
                    (raw / "agent-execution.json").read_text(encoding="utf-8"))
            except Exception:
                pass
        else:
            try:
                report["agent_execution"] = persist_agent_execution(
                    raw, error=exc, started_monotonic_ns=execution_start_ns)
            except Exception as persist_exc:
                report["agent_execution_persistence_error"] = {
                    "type": type(persist_exc).__name__, "error": str(persist_exc)[:1000]}

    def postprocess_saved_output() -> dict[str, Any]:
        result: dict[str, Any] = {"cuts_export": {"status": "not_run_no_agent_context"}}
        if not (output / "agent-context.json").is_file():
            return result
        try:
            result["render_export"] = export_rendered_video(output, INPUT)
            result["cuts_export"] = export_cuts_from_final_timeline(
                output, INPUT,
                timeline_artifact_id=result["render_export"]["timeline_artifact_id"])
        except Exception as exc:
            result.setdefault("render_export", {"status": "error"})
            result["cuts_export"] = {"status": "error", "error_type": type(exc).__name__,
                                     "error": str(exc)[:1500],
                                     "reason": "cuts export requires the selected RenderVideo timeline provenance"}
        return result

    def verify_saved_submission(current_report: dict[str, Any]) -> dict[str, Any]:
        remaining = min(VERIFIER_BUDGET_S,
                        max(0, int(total_deadline - time.monotonic() - CLEANUP_RESERVE_S)))
        if remaining <= 0:
            return {"status": "not_run_deadline", "reward": None,
                    "evaluation_complete": False}
        import video_use_edit_pilot_03 as isolated_verifier
        isolated_verifier.runner.RAW_ROOT = raw
        isolated_verifier.runner.INPUT = INPUT
        return isolated_verifier.isolated_run_verifier(current_report, remaining=remaining)

    return finalize_host_attempt(
        raw=raw, output=output, project=project, boundaries_before=boundaries_before,
        report=report, runtime=runtime, handle=handle, sampler=sampler,
        primary_error=primary_error, input_dir=INPUT_DIR,
        postprocess=postprocess_saved_output,
        verifier=verify_saved_submission,
    )


def _du(path: Path) -> int | None:
    result = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True)
    if result.returncode:
        return None
    try:
        return int(result.stdout.split()[0])
    except (ValueError, IndexError):
        return None


def _latest_artifact(directory: Path, node_id: str) -> dict[str, Any]:
    candidates = []
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("node_id") == node_id and isinstance(record.get("payload"), dict):
            candidates.append(record)
    if not candidates:
        raise RuntimeError(f"missing final {node_id} artifact")
    return max(candidates, key=lambda record: float(record.get("create_time", 0)))


def _select_render_artifact(output: Path) -> dict[str, Any]:
    """Select the render named by the container's final status, then verify provenance."""
    context = json.loads((output / "agent-context.json").read_text(encoding="utf-8"))
    session_id = str(context["session_id"])
    agent_result = json.loads((output / "agent-result.json").read_text(encoding="utf-8"))
    status_path = output / "session-status.json"
    session_status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
    selected_ids = {str(value) for value in
                    (agent_result.get("render_artifact_id"), session_status.get("render_artifact_id"))
                    if value}
    if len(selected_ids) != 1:
        raise RuntimeError(f"final render artifact is missing or ambiguous across container status: {selected_ids}")
    artifact_id = selected_ids.pop()
    artifact_path = output / session_id / "render_video" / f"{artifact_id}.json"
    if not artifact_path.is_file():
        raise RuntimeError(f"container status names missing RenderVideo artifact: {artifact_id}")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if (artifact.get("artifact_id") != artifact_id or artifact.get("node_id") != "render_video"
            or artifact.get("session_id") != session_id or not isinstance(artifact.get("payload"), dict)):
        raise RuntimeError("selected RenderVideo artifact identity/session mismatch")

    events_path = output / "mcp-tool-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()
              if line.strip()] if events_path.is_file() else []
    starts = [row for row in events if row.get("event") == "tool_call_started"
              and row.get("node_id") == "render_video" and row.get("artifact_id") == artifact_id
              and row.get("session_id") == session_id]
    if len(starts) != 1:
        raise RuntimeError(f"selected RenderVideo artifact has {len(starts)} matching tool starts")
    call_id = starts[0].get("tool_call_id")
    finishes = [row for row in events if row.get("event") == "tool_call_finished"
                and row.get("tool_call_id") == call_id and not row.get("is_error")]
    if len(finishes) != 1:
        raise RuntimeError("selected RenderVideo artifact lacks one successful matching tool result")
    render_args = starts[0].get("arguments") or {}
    timeline_value = render_args.get("plan_timeline")
    timeline_dir = output / session_id / "plan_timeline_pro"
    matching_timelines = []
    for path in timeline_dir.glob("*.json"):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (candidate.get("node_id") == "plan_timeline_pro"
                and candidate.get("session_id") == session_id
                and candidate.get("payload") == timeline_value):
            matching_timelines.append(candidate)
    if not isinstance(timeline_value, dict) or not matching_timelines:
        raise RuntimeError("selected render has no same-session PlanTimelinePro payload provenance")
    # The MCP schema passes the payload, not its artifact ID. Identical payloads
    # are semantically equivalent; record the newest matching artifact explicitly.
    latest_timeline = max(matching_timelines,
                          key=lambda row: float(row.get("create_time", 0)))
    timeline_sha = hashlib.sha256(json.dumps(
        timeline_value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"artifact": artifact, "artifact_path": artifact_path, "session_id": session_id,
            "tool_call_id": call_id, "timeline_artifact_id": latest_timeline.get("artifact_id"),
            "timeline_payload_sha256": timeline_sha,
            "selection_basis": "render_artifact_id jointly recorded by raw agent-result and session-status; successful same-session MCP call consumes latest saved timeline"}


def export_rendered_video(output: Path, expected_source: Path) -> dict[str, Any]:
    """Export the explicitly selected current-session RenderVideo artifact."""
    copied = copy_selected_render_artifact(output)
    selection = copied["selection"]
    artifact = selection["artifact"]
    session_id = selection["session_id"]
    artifact_id = str(artifact["artifact_id"])
    source = Path(copied["source"]["path"])
    target = Path(copied["submission"]["path"])
    source_hash = {k: copied["source"][k] for k in ("bytes", "sha256")}
    target_hash = {k: copied["submission"][k] for k in ("bytes", "sha256")}

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    media = json.loads(probe.stdout)
    streams = media.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"), None)
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    if not video or video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise RuntimeError("exported submission is missing H.264/yuv420p video")
    if not audio or audio.get("codec_name") != "aac":
        raise RuntimeError("exported submission is missing AAC source audio")
    source_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate", "-of", "json", str(expected_source)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    source_video = json.loads(source_probe.stdout)["streams"][0]
    if (int(video.get("width", 0)), int(video.get("height", 0))) != (
            int(source_video["width"]), int(source_video["height"])):
        raise RuntimeError("exported submission dimensions do not match the registered input")
    fps = str(video.get("avg_frame_rate", "0/1"))
    if fps != str(source_video.get("avg_frame_rate", "0/1")):
        raise RuntimeError(f"exported submission frame rate differs from input: {fps}")
    video_start = float(video.get("start_time", 0) or 0)
    audio_start = float(audio.get("start_time", 0) or 0)
    video_duration = float(video.get("duration", media.get("format", {}).get("duration", 0)) or 0)
    audio_duration = float(audio.get("duration", 0) or 0)
    if abs(video_start - audio_start) > 0.1 or abs(video_duration - audio_duration) > 0.1:
        raise RuntimeError("exported video and audio are not synchronized within 100 ms")
    volume = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(target), "-vn", "-af", "volumedetect",
         "-f", "null", "-"], capture_output=True, text=True, timeout=60,
    )
    audio_log = volume.stderr or ""
    if volume.returncode != 0 or "mean_volume: -inf dB" in audio_log:
        raise RuntimeError("exported AAC audio is silent or could not be decoded")
    return {"status": "exported_and_verified", "session_id": session_id,
            "render_artifact_id": artifact_id, "render_artifact_path": str(source),
            "source": {"path": str(source), **source_hash},
            "submission": {"path": str(target), **target_hash},
            "selection_basis": selection["selection_basis"],
            "tool_call_id": selection["tool_call_id"],
            "timeline_artifact_id": selection["timeline_artifact_id"],
            "timeline_payload_sha256": selection["timeline_payload_sha256"],
            "video": {"codec": video.get("codec_name"), "pixel_format": video.get("pix_fmt"),
                      "width": video.get("width"), "height": video.get("height"),
                      "fps": fps, "start_time": video_start, "duration_s": video_duration},
            "audio": {"codec": audio.get("codec_name"), "sample_rate": audio.get("sample_rate"),
                      "start_time": audio_start, "duration_s": audio_duration,
                      "non_silent": "mean_volume: -inf dB" not in audio_log}}


def resolve_selected_render_media(output: Path, selection: dict[str, Any] | None = None) -> Path:
    """Resolve only the selected artifact's mounted path and enforce its store boundary."""
    selection = selection or _select_render_artifact(output)
    artifact_id = str(selection["artifact"]["artifact_id"])
    container_source = PurePosixPath(str(selection["artifact"]["payload"].get("output_path", "")))
    container_root = PurePosixPath("/workspace/output")
    try:
        relative_source = container_source.relative_to(container_root)
    except ValueError as exc:
        raise RuntimeError(f"selected RenderVideo path is outside output mount: {container_source}") from exc
    source = (output / Path(*relative_source.parts)).resolve()
    expected_parent = (output / ".server_cache" / selection["session_id"] / artifact_id).resolve()
    if source.parent != expected_parent or not source.is_file():
        raise RuntimeError(f"selected RenderVideo media missing/outside artifact directory: {source}")
    if source.stat().st_size <= 0:
        raise RuntimeError(f"selected RenderVideo media is empty: {source}")
    return source


def copy_selected_render_artifact(output: Path, *, copy_fn: Any = shutil.copy2) -> dict[str, Any]:
    """Copy one status-selected artifact and bind source/target hashes; no media probing."""
    selection = _select_render_artifact(output)
    source = resolve_selected_render_media(output, selection)
    target = output / "output.mp4"
    if target.exists():
        raise RuntimeError(f"refusing to overwrite existing submission: {target}")
    source_hash = digest(source)
    copy_fn(source, target)
    target_hash = digest(target)
    if source_hash != target_hash:
        raise RuntimeError("submission hash differs from the explicitly selected RenderVideo artifact")
    return {"selection": selection, "source": {"path": str(source), **source_hash},
            "submission": {"path": str(target), **target_hash}}


def export_cuts_from_final_timeline(output: Path, source: Path,
                                    timeline_artifact_id: str | None = None) -> dict[str, Any]:
    context = json.loads((output / "agent-context.json").read_text(encoding="utf-8"))
    session_id = context["session_id"]
    store = output / session_id
    rough = _latest_artifact(store / "speech_rough_cut", "speech_rough_cut")["payload"]
    if timeline_artifact_id is None:
        plan_record = _latest_artifact(store / "plan_timeline_pro", "plan_timeline_pro")
    else:
        plan_record = json.loads((store / "plan_timeline_pro" /
                                  f"{timeline_artifact_id}.json").read_text(encoding="utf-8"))
        if plan_record.get("session_id") != session_id or plan_record.get("node_id") != "plan_timeline_pro":
            raise RuntimeError("selected timeline artifact identity/session mismatch")
    plan = plan_record["payload"]
    clip_by_path = {os.path.normpath(str(clip["path"])): clip
                    for clip in rough.get("clips", []) if clip.get("path")}
    retained = []
    for item in plan.get("tracks", {}).get("video", []):
        path = os.path.normpath(str(item["source_path"]))
        clip = clip_by_path.get(path)
        if clip is None:
            raise RuntimeError(f"timeline source has no speech_rough_cut provenance: {path}")
        source_ref = clip.get("source_ref") or {}
        window = item.get("source_window") or {}
        start = int(source_ref["start"]) + int(window["start"])
        end = int(source_ref["start"]) + int(window["end"])
        if end <= start:
            raise RuntimeError("final timeline contains a non-positive source interval")
        retained.append([start, end])
    if not retained:
        raise RuntimeError("final timeline has no source-retained video intervals")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "json", str(source)],
                           capture_output=True, text=True, check=True)
    duration_ms = round(float(json.loads(probe.stdout)["format"]["duration"]) * 1000)
    retained.sort()
    union = []
    for start, end in retained:
        start = max(0, min(duration_ms, start))
        end = max(0, min(duration_ms, end))
        if end <= start:
            continue
        if union and start <= union[-1][1]:
            union[-1][1] = max(union[-1][1], end)
        else:
            union.append([start, end])
    cuts, cursor = [], 0
    for start, end in union:
        if start > cursor:
            cuts.append({"start_ms": cursor, "end_ms": start,
                         "reason": "outside_final_rendered_source_intervals"})
        cursor = max(cursor, end)
    if cursor < duration_ms:
        cuts.append({"start_ms": cursor, "end_ms": duration_ms,
                     "reason": "outside_final_rendered_source_intervals"})
    target = output / "cuts.json"
    proposed = output / "cuts-agent-proposed.json"
    if target.is_file() and not proposed.exists():
        shutil.copy2(target, proposed)
    with target.open("w", encoding="utf-8") as stream:
        json.dump({"cuts": cuts}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "derived_from_final_timeline", "session_id": session_id,
            "timeline_artifact_id": plan_record["artifact_id"],
            "rough_cut_artifact_id": _latest_artifact(store / "speech_rough_cut",
                                                        "speech_rough_cut")["artifact_id"],
            "source_duration_ms": duration_ms, "rendered_source_intervals_ms": union,
            "cuts_json": str(target), "agent_proposal_preserved": proposed.is_file()}


def _save_samples(raw: Path, rows: list[dict[str, Any]]) -> None:
    import csv
    jsonl = raw / "resource-samples.jsonl"
    with jsonl.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    csv_path = raw / "resource-samples.csv"
    with csv_path.open("x", encoding="utf-8", newline="") as stream:
        fields = ["t_monotonic_ns", "role", "container_id", "cgroup_version",
                  "cpu_usage_usec", "mem_current_bytes", "mem_peak_bytes",
                  "io_read_bytes", "io_write_bytes", "netns_interfaces_json"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            cg = row.get("cgroup") or {}
            writer.writerow({"t_monotonic_ns": row.get("t_monotonic_ns"),
                             "role": row.get("role"), "container_id": cg.get("container_id"),
                             "cgroup_version": cg.get("cgroup_version"),
                             "cpu_usage_usec": cg.get("cpu_usage_usec"),
                             "mem_current_bytes": cg.get("mem_current_bytes"),
                             "mem_peak_bytes": cg.get("mem_peak_bytes"),
                             "io_read_bytes": cg.get("io_read_bytes"),
                             "io_write_bytes": cg.get("io_write_bytes"),
                             "netns_interfaces_json": json.dumps(row.get("netns_proc_net_dev"),
                                                                  ensure_ascii=False)})
        stream.flush()
        os.fsync(stream.fileno())


def _count_event(path: Path, event: str) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            count += json.loads(line).get("event") == event
        except json.JSONDecodeError:
            pass
    return count


def _write_manifest(root: Path) -> None:
    files = []
    excluded_control_files = {"manifest.json", "host-finalization.json",
                              "report-generation-status.json"}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in excluded_control_files:
            files.append({"path": str(path.relative_to(root)), **digest(path)})
    atomic_write_json(root / "manifest.json", {
        "schema": "openstoryline-attempt-manifest-v1",
        "excluded_mutable_control_files": sorted(excluded_control_files),
        "self_hash": "omitted", "files": files,
    }, exclusive=True)


def exit_code_for(report: dict[str, Any]) -> int:
    """Keep task score separate from failed infrastructure or finalization."""
    generation = report.get("report_generation") or {}
    if (report.get("cleanup_errors") or report.get("postprocess_error")
            or report.get("host_finalization_update_error")
            or report.get("container_agent_result_read_error")
            or report.get("container_removal") not in {"removed", "not_started"}
            or report.get("sampling_status") == "stop_or_archive_error"
            or generation.get("report_status") != "complete"
            or generation.get("manifest_status") != "complete"
            or generation.get("errors")
            or (report.get("render_export") or {}).get("status") == "error"
            or (report.get("cuts_export") or {}).get("status") == "error"
            or (report.get("verifier") or {}).get("status") == "error"):
        return 7
    return 0 if report.get("agent_returncode") == 0 else 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--preflight":
        result = write_preflight_record()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["formal_ready"] else 2
    if len(sys.argv) == 2 and sys.argv[1] == "--execute":
        report = execute_once()
        return exit_code_for(report)
    raise SystemExit("use --preflight or --execute with matching frozen identity and APPROVAL")


if __name__ == "__main__":
    raise SystemExit(main())
