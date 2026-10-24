from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
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
IMAGE = "openstoryline-task:arm64-asr-adapted-v13-formal-entry-audio-budget"
IMAGE_ID = "sha256:bb9acb6f997176c28eccf35a74ee26bb3e83d40ff31c8fe809351f5f77f7d52f"
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
                         api_key: str, run_deadline: float,
                         input_dir: Path = INPUT_DIR) -> ContainerSpec:
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
    env = {**cache_env, "DASHSCOPE_API_KEY": api_key,
           "OPENSTORYLINE_CONFIG": "/opt/openstoryline/config.toml"}
    return ContainerSpec(
        run_id=run_id, scope="openstoryline_agent", image=IMAGE,
        cwd="/workspace", env=env, timeout_s=max(1, int(run_deadline - time.monotonic())),
        mem_limit="8g", cpu_limit="4", network="bridge", platform=PLATFORM,
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
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/openstoryline_mcp_server.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/agent.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/request_ledger.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/sampling_handler.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/register_tools.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/asr_adapter/cache_preflight.py",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/asr-cache-contract.json",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source-manifest.json",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.formal-entry",
        ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.formal-entry-v13",
        ROOT / "src/agent_workload_characterization/runners/container_runtime.py",
        ROOT / "scripts/video_use_edit_pilot_01.py",
        TASK_ROOT / "steps/solve/instruction.md", INPUT,
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

    start_ns = time.monotonic_ns()
    total_deadline = time.monotonic() + TOTAL_BUDGET_S
    agent_deadline = min(time.monotonic() + AGENT_BUDGET_S,
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
    sys.path.insert(0, str(ROOT / "scripts"))
    import video_use_edit_pilot_01 as resource_runtime
    resource_runtime.SAMPLE_S = 0.5
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    runtime = DockerCliRuntime(authorized=True, collection=TASK)
    handle = None
    sampler = None
    boundaries_before = {"input": _du(INPUT_DIR), "project": _du(project),
                         "submission": _du(output)}
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
        result = runtime.execute(handle, command, timeout_s=timeout,
                                 output_limit=2_000_000)
        report["phases"].append({"phase": "agent", "start_monotonic_ns": start_ns,
                                 "end_monotonic_ns": time.monotonic_ns(),
                                 "returncode": result.get("returncode"),
                                 "timed_out": result.get("timed_out", False),
                                 "termination": result.get("termination"),
                                 "output_tail": result.get("output", "")[-8000:]})
        report["agent_returncode"] = result.get("returncode")
    except BaseException as exc:
        report["termination_reason"] = {"type": type(exc).__name__, "message": str(exc)[:800]}
    finally:
        if sampler:
            sampler.stop_event.set()
            sampler.join(timeout=10)
            report["sampler_rows"] = sampler.rows
            _save_samples(raw, sampler.rows)
            cgroup_rows = resource_runtime.resource_rows(sampler.rows, handle.container_id if handle else None)
            report["resource_metrics"] = resource_runtime.resource_metrics(sampler.rows)
            report["resource_summary"] = {
                "cgroup_rows": len(cgroup_rows),
                "cgroup_version": handle.cgroup_version if handle else None,
                "netns_scope": "per-interface container namespace counters; not API-specific",
            }
        if handle:
            try:
                runtime.stop(handle, timeout_s=20)
                report["container_removal"] = runtime.verify_removal(handle, timeout_s=20)
            except Exception as exc:
                report["container_removal"] = f"check_failed:{type(exc).__name__}"

    report["directory_boundaries"] = {
        "input": {"path": str(INPUT_DIR), "before_bytes": boundaries_before["input"],
                  "after_bytes": _du(INPUT_DIR)},
        "project": {"path": str(project), "before_bytes": boundaries_before["project"],
                    "after_bytes": _du(project)},
        "submission": {"path": str(output), "before_bytes": boundaries_before["submission"],
                       "after_bytes": _du(output)},
    }
    report["cuts_export"] = {"status": "not_run_no_agent_context"}
    context_file = output / "agent-context.json"
    if context_file.is_file():
        try:
            report["cuts_export"] = export_cuts_from_final_timeline(output, INPUT)
        except Exception as exc:
            report["cuts_export"] = {"status": "error", "error_type": type(exc).__name__,
                                     "error": str(exc)[:600]}
    report["verifier"] = {"status": "not_run_no_submission", "reward": None,
                          "evaluation_complete": False}
    if (report["cuts_export"].get("status") == "derived_from_final_timeline"
            and (output / "output.mp4").is_file() and (output / "cuts.json").is_file()):
        remaining = min(VERIFIER_BUDGET_S,
                        max(0, int(total_deadline - time.monotonic() - CLEANUP_RESERVE_S)))
        if remaining > 0:
            import video_use_edit_pilot_03 as isolated_verifier
            isolated_verifier.runner.RAW_ROOT = raw
            isolated_verifier.runner.INPUT = INPUT
            report["verifier"] = isolated_verifier.isolated_run_verifier(
                {**report, "phases": report["phases"]}, remaining=remaining)
        else:
            report["verifier"] = {"status": "not_run_deadline", "reward": None,
                                  "evaluation_complete": False}
    report["end_monotonic_ns"] = time.monotonic_ns()
    report["total_wall_s"] = (report["end_monotonic_ns"] - start_ns) / 1e9
    report["logical_requests"] = _count_event(output / "model-requests.jsonl", "request_started")
    report["request_events"] = str(output / "model-requests.jsonl")
    with (raw / "run-report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    _write_manifest(raw)
    return report


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


def export_cuts_from_final_timeline(output: Path, source: Path) -> dict[str, Any]:
    context = json.loads((output / "agent-context.json").read_text(encoding="utf-8"))
    session_id = context["session_id"]
    store = output / session_id
    rough = _latest_artifact(store / "speech_rough_cut", "speech_rough_cut")["payload"]
    plan = _latest_artifact(store / "plan_timeline_pro", "plan_timeline_pro")["payload"]
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
            "timeline_artifact_id": _latest_artifact(store / "plan_timeline_pro",
                                                       "plan_timeline_pro")["artifact_id"],
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
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": str(path.relative_to(root)), **digest(path)})
    with (root / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"schema": "openstoryline-attempt-manifest-v1", "files": files},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--preflight":
        result = write_preflight_record()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["formal_ready"] else 2
    if len(sys.argv) == 2 and sys.argv[1] == "--execute":
        report = execute_once()
        return 0 if report.get("agent_returncode") == 0 else 1
    raise SystemExit("use --preflight or --execute with matching frozen identity and APPROVAL")


if __name__ == "__main__":
    raise SystemExit(main())
