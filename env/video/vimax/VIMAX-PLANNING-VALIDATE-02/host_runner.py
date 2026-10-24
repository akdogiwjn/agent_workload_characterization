#!/usr/bin/env python3
"""One-attempt host lifecycle for planning-only ViMax validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))
from agent_workload_characterization.collectors.resource_sampler import (  # noqa:E402
    CgroupV1FileReader, ResourceSampler)

IMAGE = "vimax-task-bailian:arm64-v6-planning-fixes-02"
IMAGE_ID = "sha256:c2223fb39aa74b3b59bb572e1bab05ce53250885b71111bd931ca77603016670"
TASK_JSON = REPO / "references/repos/ViMax/vimax_benchmark/photographer_urban_timelapses_typeA.json"
REGISTERED_SCRIPT = REPO / "env/video/vimax/VIMAX-PLANNING-VALIDATE-01/execution-01/workspace/registered-script.txt"
REGISTERED_SCRIPT_SHA256 = "447e4d88ccd76f9cb4a206f799993620a3c832238dd873c9ae9e905c2452b59a"
CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
LLM_MODEL = "qwen3.7-plus"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
WORK_S = 1800.0
CLOSEOUT_S = 120.0
CGROUP_PERIOD_S = 0.5
NETNS_PERIOD_S = 2.0


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dir_measure(path: Path) -> dict:
    result = {"path": str(path), "apparent_bytes": 0, "files": 0,
              "unreadable": 0, "exists": path.exists()}
    if not path.exists():
        return result
    for item in path.rglob("*"):
        if item.is_file():
            try:
                result["apparent_bytes"] += item.stat().st_size
                result["files"] += 1
            except OSError:
                result["unreadable"] += 1
    return result


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p)
            for p in sorted(root.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def build_registered_script(source: Path) -> str:
    data = json.loads(source.read_text(encoding="utf-8"))
    shots = [(scene["scene_num"], shot) for scene in data["scenes"]
             for shot in scene["shots"]]
    if len(shots) != 8 or [s["shot_id"] for _, s in shots] != list(range(1, 9)):
        raise RuntimeError("registered source is not the expected ordered eight-shot story")
    lines = []
    for scene_num, shot in shots:
        lines.extend((f"Shot {shot['shot_id']} (Scene {scene_num}):",
                      f"First frame: {shot['first_frame']}",
                      f"Shot action: {shot['video_prompt']}", ""))
    return "\n".join(lines)


TASK_REQUIREMENTS = "\n".join((
        "Preserve the same adult woman photographer, facial features, crescent scar, clothing, camera and red strap as described in the script.",
        "Keep exactly eight shots in the same order and preserve each supplied location and principal action; do not merge, remove, duplicate, reorder, or add shots.",
        "Plan for landscape 16:9, approximately five seconds per shot and approximately forty seconds total. Add no dialogue, narration, or music.",
        "Keep each shot compatible with a first-frame-only video adapter: do not require an unsupported last-frame or variation input; prefer small within-shot changes while preserving the supplied action.",
        "Use independent cameras where possible and no more than four transitions.",
        "This is planning validation only. Do not generate images, videos, keyframes, or a rendered file."))
TASK_STYLE = "Documentary photography, natural light, cinematic framing, 16:9."
SESSION_ID = "planning-validation-02"


def build_task_text() -> str:
    return (
        "Use the native vimax_narrative_planning tool with the active frozen script session. "
        f"Call it with session_id={SESSION_ID!r} and do not pass idea, script, or replacement requirements. "
        "Do not call media-generation, rendering, or shell tools. The tool registry excludes them. "
        "Return after native planning; do not create or repair artifacts manually."
    )


def run(argv, timeout=30, env=None):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(argv, 124, exc.stdout or "",
                                           f"TIMEOUT after {timeout}s")


def image_identity() -> dict:
    result = run(["docker", "--host", "unix:///var/run/docker.sock",
                  "image", "inspect", IMAGE, "--format",
                  "{{.Id}} {{.Os}} {{.Architecture}}"])
    if result.returncode:
        raise RuntimeError("registered image inspect failed")
    image_id, os_name, arch = result.stdout.split()
    actual = {"id": image_id, "platform": f"{os_name}/{arch}"}
    if actual != {"id": IMAGE_ID, "platform": "linux/arm64"}:
        raise RuntimeError("registered image ID/platform mismatch")
    return actual


def in_image_hashes(entry: Path, work: Path) -> dict[str, str]:
    code = (
        "import hashlib,json,pathlib; r=pathlib.Path('/opt/vimax/src'); "
        "print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() "
        "for p in sorted(r.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}))")
    result = run(["docker", "--host", "unix:///var/run/docker.sock", "run",
                  "--rm", "--network", "none", "--read-only", "--tmpfs",
                  "/tmp:rw,nosuid,nodev,size=128m", "--mount",
                  f"type=bind,source={entry},target=/opt/validation/planning_entry.py,readonly",
                  "-e", "PYTHONPATH=/opt/vimax/src:/opt/validation",
                  "--entrypoint", "python3", IMAGE, "-c", code], timeout=60)
    if result.returncode:
        raise RuntimeError("in-image source hash command failed")
    return json.loads(result.stdout)


def container_lifecycle_check() -> dict:
    name = "vimax-plan-preflight-" + uuid.uuid4().hex[:8]
    base = ["docker", "--host", "unix:///var/run/docker.sock"]
    started = run([*base, "run", "-d", "--name", name, "--network", "none",
                   "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
                   "--entrypoint", "python3", IMAGE, "-c",
                   "import time; time.sleep(60)"], timeout=20)
    if started.returncode:
        raise RuntimeError("isolated lifecycle container could not start")
    cid = started.stdout.strip()
    result = {"started": True, "network": "none", "sent_model_requests": 0}
    try:
        killed = run([*base, "kill", cid], timeout=8)
        result["parent_kill_returncode"] = killed.returncode
        waited = run([*base, "wait", cid], timeout=8)
        result["wait_returncode"] = waited.returncode
        result["container_returncode"] = waited.stdout.strip() if waited.returncode == 0 else None
        removed = run([*base, "rm", cid], timeout=8)
        result["remove_returncode"] = removed.returncode
        check = run([*base, "inspect", cid], timeout=5)
        result["removal_verified"] = check.returncode != 0
        if (killed.returncode or waited.returncode or removed.returncode
                or not result["removal_verified"]):
            raise RuntimeError("isolated container kill/wait/removal check failed")
        return result
    finally:
        run([*base, "rm", "-f", cid], timeout=8)


def preflight(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    workspace = out / "workspace"
    attempt = workspace / "attempt"
    attempt.mkdir(parents=True, exist_ok=True)
    if not os.access(CREDENTIAL_FILE, os.R_OK) or not CREDENTIAL_FILE.is_file():
        raise RuntimeError("registered credential source is unavailable to the runtime host")
    source_hash = sha(TASK_JSON)
    if source_hash != "aaf6545c1ef8a4a3ffef4e690b5f304fc67062dae42bbaf433a47d09da49719e":
        raise RuntimeError("registered task JSON hash differs from the prior task record")
    registered_script = build_registered_script(TASK_JSON)
    if hashlib.sha256(registered_script.encode("utf-8")).hexdigest() != REGISTERED_SCRIPT_SHA256:
        raise RuntimeError("source JSON conversion differs from the previously registered script")
    if sha(REGISTERED_SCRIPT) != REGISTERED_SCRIPT_SHA256:
        raise RuntimeError("previously registered script evidence hash mismatch")
    if REGISTERED_SCRIPT.read_bytes() != registered_script.encode("utf-8"):
        raise RuntimeError("source JSON does not reproduce the prior registered script bytes")
    task_text = build_task_text()
    task_path = workspace / "task-input.txt"
    if task_path.exists():
        if task_path.read_text(encoding="utf-8") != task_text:
            raise RuntimeError("existing preflight task input differs; refusing overwrite")
    else:
        task_path.write_text(task_text, encoding="utf-8")
    entry = Path(__file__).with_name("planning_entry.py").resolve()
    verifier = Path(__file__).with_name("plan_verifier.py").resolve()
    script_path = workspace / "registered-script.txt"
    if script_path.exists():
        if script_path.read_bytes() != registered_script.encode("utf-8"):
            raise RuntimeError("existing frozen script differs; refusing overwrite")
    else:
        script_path.write_bytes(registered_script.encode("utf-8"))
    requirements_path = workspace / "task-requirements.txt"
    requirements_path.write_text(TASK_REQUIREMENTS, encoding="utf-8")
    (workspace / "task-style.txt").write_text(TASK_STYLE, encoding="utf-8")
    image = image_identity()
    host_hashes = tree_hashes(REPO / "env/video/vimax/adapter-src")
    image_hashes = in_image_hashes(entry, workspace)
    if host_hashes != image_hashes:
        raise RuntimeError("registered image source does not match adapter-src")
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": "/opt/vimax/src:/opt/validation",
        "VIMAX_LLM_API_KEY": "offline-fake-key-never-sent",
        "VIMAX_LLM_MODEL": LLM_MODEL,
        "VIMAX_LLM_MODEL_PROVIDER": "openai",
        "VIMAX_LLM_BASE_URL": LLM_BASE_URL,
        "VIMAX_BAILIAN_EVENT_LOG": "/tmp/policy-check.jsonl",
        "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
        "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
        "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192",
        "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
        "VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS": "0",
        "VIMAX_BAILIAN_BUDGET_VIDEO_CREATES": "0",
        "VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS": "250000",
        "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS": "1800",
    })
    check = run(["docker", "--host", "unix:///var/run/docker.sock", "run",
                 "--rm", "--network", "none", "--read-only", "--tmpfs",
                 "/tmp:rw,nosuid,nodev,size=128m", "--tmpfs",
                 "/workspace:rw,nosuid,nodev,size=128m", "--user", "0:0", "--mount",
                 f"type=bind,source={entry},target=/opt/validation/planning_entry.py,readonly",
                 "--mount", f"type=bind,source={verifier},target=/opt/validation/plan_verifier.py,readonly",
                 "-e", "PYTHONPATH=/opt/vimax/src:/opt/validation",
                 "-e", "VIMAX_LLM_API_KEY=offline-fake-key-never-sent",
                 "-e", f"VIMAX_LLM_MODEL={LLM_MODEL}", "-e",
                 "VIMAX_LLM_MODEL_PROVIDER=openai", "-e",
                 f"VIMAX_LLM_BASE_URL={LLM_BASE_URL}", "-e",
                 "VIMAX_BAILIAN_EVENT_LOG=/tmp/policy-check.jsonl", "-e",
                 "VIMAX_BAILIAN_BUDGET_LLM_CALLS=40", "-e",
                 "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS=40", "-e",
                 "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS=8192", "-e",
                 "VIMAX_NARRATIVE_MAX_TOKENS=8192", "-e",
                 "VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS=0", "-e",
                 "VIMAX_BAILIAN_BUDGET_VIDEO_CREATES=0", "-e",
                 "VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS=250000",
                 "-e", "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS=1800",
                 "--entrypoint", "python3", IMAGE,
                 "/opt/validation/planning_entry.py", "--self-check"], timeout=90)
    if check.returncode:
        raise RuntimeError(f"planning entry offline self-check failed: {check.stderr[-500:]}")
    lifecycle = container_lifecycle_check()
    task_hash = sha(task_path)
    return {
        "ok": True, "image": image, "adapter_source_files": len(host_hashes),
        "adapter_source_hashes_match": True,
        "host_runner_sha256": sha(Path(__file__).resolve()),
        "entry_sha256": sha(entry), "task_json_sha256": source_hash,
        "verifier_sha256": sha(verifier),
        "task_input_sha256": task_hash, "registered_script_sha256": sha(script_path),
        "task_requirements_sha256": sha(requirements_path),
        "task_style_sha256": sha(workspace / "task-style.txt"),
        "task_shot_ids": list(range(1, 9)),
        "credential_source_readable": True, "credential_values_read": False,
        "route": {"model": LLM_MODEL, "base_url": LLM_BASE_URL,
                  "provider": "openai-compatible", "credential_env": "DASHSCOPE_API_KEY -> VIMAX_LLM_API_KEY"},
        "model_config": {"model": LLM_MODEL, "base_url": LLM_BASE_URL,
                         "protocol": "OpenAI-compatible Chat Completions",
                         "extra_body": {"enable_thinking": False},
                         "outer_max_tokens": 8192,
                         "internal_max_completion_tokens": 8192,
                         "sdk_max_retries": 0},
        "budget": {"logical_request_cap": 40,
                   "request_attempt_cap": 40,
                   "single_request_output_tokens": 8192,
                   "narrative_node_output_tokens": 8192,
                   "observed_total_tokens_soft_threshold": 250000,
                   "shared_work_deadline_s": WORK_S,
                   "closeout_reserve_s": CLOSEOUT_S,
                   "image_generations": 0, "video_creates": 0,
                   "sdk_retries": 0},
        "planning_entry_self_check": check.stdout.strip(),
        "parent_timeout_cleanup_check": lifecycle,
        "network_preflight": "not run; no separate network/API probe authorized or needed",
    }


def read_registered_key() -> str:
    # Values are used only in this process and Docker runtime environment.
    values = {}
    for raw in CREDENTIAL_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "DASHSCOPE_API_KEY":
            values["DASHSCOPE_API_KEY"] = value.strip().strip("\"'")
    key = values.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError("registered language-model credential is missing")
    return key


def netdev_snapshot(container_id: str) -> dict:
    result = run(["docker", "--host", "unix:///var/run/docker.sock", "exec",
                  container_id, "cat", "/proc/net/dev"], timeout=5)
    t_ns = time.monotonic_ns()
    if result.returncode:
        return {"t_monotonic_ns": t_ns, "read_status": "error",
                "error": result.stderr[-200:]}
    interfaces = {}
    for line in result.stdout.splitlines()[2:]:
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        nums = values.split()
        if len(nums) >= 9:
            interfaces[name.strip()] = {"rx_bytes": int(nums[0]),
                                        "tx_bytes": int(nums[8])}
    return {"t_monotonic_ns": t_ns, "read_status": "ok",
            "scope": "container_netns_interfaces", "interfaces": interfaces}


def validate_approval(out: Path, approval_path: Path) -> dict:
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    identity_path = approval_path.with_name("identity-01.json")
    if not identity_path.is_file() or sha(identity_path) != approval.get("identity_sha256"):
        raise RuntimeError("frozen identity is absent or does not match approval")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    entry = Path(__file__).with_name("planning_entry.py").resolve()
    task = out / "workspace" / "task-input.txt"
    image = image_identity()
    expected = {
        "task_namespace": "VIMAX-PLANNING-VALIDATE-02",
        "image": image,
        "host_runner_sha256": sha(Path(__file__).resolve()),
        "entry_sha256": sha(entry),
        "verifier_sha256": sha(Path(__file__).with_name("plan_verifier.py")),
        "task_input_sha256": sha(task),
        "task_requirements_sha256": sha(out / "workspace" / "task-requirements.txt"),
        "task_style_sha256": sha(out / "workspace" / "task-style.txt"),
        "task_json_sha256": sha(TASK_JSON),
        "registered_script_sha256": sha(out / "workspace" / "registered-script.txt"),
        "model_config": {"model": LLM_MODEL, "base_url": LLM_BASE_URL,
                         "protocol": "OpenAI-compatible Chat Completions",
                         "extra_body": {"enable_thinking": False},
                         "outer_max_tokens": 8192,
                         "internal_max_completion_tokens": 8192,
                         "sdk_max_retries": 0},
        "budget": {"logical_request_cap": 40,
                   "request_attempt_cap": 40,
                   "single_request_output_tokens": 8192,
                   "narrative_node_output_tokens": 8192,
                   "observed_total_tokens_soft_threshold": 250000,
                   "shared_work_deadline_s": WORK_S,
                   "closeout_reserve_s": CLOSEOUT_S,
                   "image_generations": 0, "video_creates": 0,
                   "sdk_retries": 0},
    }
    for key, value in expected.items():
        if approval.get(key) != value:
            raise RuntimeError(f"approval does not match current {key}")
        if identity.get(key) != value:
            raise RuntimeError(f"frozen identity does not match current {key}")
    if approval.get("attempts_authorized") != 1 or approval.get("retry") != 0:
        raise RuntimeError("approval attempt count is invalid")
    if (identity.get("run_id") != approval.get("run_id")
            or identity.get("attempt") != 1 or identity.get("retry") != 0):
        raise RuntimeError("approval and frozen identity run linkage differs")
    for key in ("route", "tools", "resources", "task_source"):
        if approval.get(key) != identity.get(key):
            raise RuntimeError(f"approval and frozen identity differ on {key}")
    if not str(approval.get("run_id", "")).startswith("vimax-planning-validate-02-"):
        raise RuntimeError("approval does not freeze a unique run_id")
    required_tools = ["glob_files", "list_files", "memory_read", "read_file",
                      "read_json", "search_text", "todo_read",
                      "vimax_narrative_planning"]
    if approval.get("allowed_tools") != required_tools:
        raise RuntimeError("approval tool allowlist differs from runtime policy")
    preflight = json.loads((out / "preflight.json").read_text(encoding="utf-8"))
    if not preflight.get("ok") or preflight.get("entry_sha256") != expected["entry_sha256"]:
        raise RuntimeError("current code was not covered by successful preflight")
    return approval


def write_json(path: Path, value: dict):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    temp.replace(path)


def summarize_run(out: Path, record: dict) -> dict:
    attempt = out / "workspace" / "attempt"
    ledger_path = attempt / "model-events.jsonl"
    events_path = attempt / "agent-events.jsonl"
    ledger_rows = []
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    ledger_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    ledger_rows.append({"parse_error": True})
    agent_rows = []
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    agent_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    agent_rows.append({"parse_error": True})
    opens = [row for row in ledger_rows
             if row.get("kind") == "open" and row.get("op") == "llm_chat"]
    requests = {row.get("request_id") for row in opens if row.get("request_id")}
    closed = {row.get("request_id") for row in ledger_rows
              if row.get("kind") in {"close", "error"} and row.get("request_id")}
    terminal_by_id = {row.get("request_id"): row for row in ledger_rows
                      if row.get("kind") in {"close", "error"} and row.get("request_id")}
    request_summaries = []
    for opened in opens:
        terminal = terminal_by_id.get(opened.get("request_id"), {})
        saved_text = terminal.get("structured_response_text")
        request_summaries.append({
            "request_id": opened.get("request_id"),
            "role": opened.get("role"), "stage": opened.get("stage"),
            "request_model": opened.get("model"),
            "response_model": terminal.get("response_model"),
            "status": terminal.get("status", terminal.get("kind", "right_censored")),
            "finish_reason": terminal.get("finish_reason"),
            "usage": terminal.get("usage"),
            "response_text_chars_saved": (
                len(saved_text) if isinstance(saved_text, str) else None),
            "response_text_missing": terminal.get(
                "structured_response_text_missing"),
            "response_text_truncated": terminal.get(
                "structured_response_text_truncated"),
        })
    parse_diagnostics = [{
        "request_id": row.get("request_id"),
        "parse_status": row.get("parse_status"),
        "parse_error_type": row.get("parse_error_type"),
        "finish_reason": row.get("finish_reason"),
        "response_chars": row.get("response_chars"),
    } for row in ledger_rows if row.get("kind") == "diagnostic"
       and ("parse_status" in row or "parse_error_type" in row)]
    usage_rows = [row.get("usage") for row in ledger_rows
                  if row.get("kind") == "close" and row.get("op") == "llm_chat"
                  and isinstance(row.get("usage"), dict)]
    observed_total = (sum(row["total_tokens"] for row in usage_rows
                          if isinstance(row.get("total_tokens"), int))
                      if all(isinstance(row.get("total_tokens"), int)
                             for row in usage_rows) else None)
    result_rows = [row.get("tool_result", {}) for row in agent_rows
                   if row.get("type") == "tool_result"]
    plan_check_path = attempt / "plan-check.json"
    plan_check = None
    if plan_check_path.is_file():
        try:
            plan_check = json.loads(plan_check_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            plan_check = {"ok": False, "state": "corrupt"}
    report = {
        "task": "VIMAX-PLANNING-VALIDATE-02", "run_id": record["run_id"],
        "attempt_count": 1, "retry": 0,
        "result": {"planning_contract":
                   ("pass" if plan_check and plan_check.get("ok") is True
                    else "fail" if plan_check else "unknown"),
                   "plan_check": plan_check,
                   "media_generation_authorized": False,
                   "media_files_created": (plan_check.get("media_files")
                                            if plan_check else None)},
        "requests": {"logical_llm_requests": len(opens),
                     "outer_agent_requests": sum(r.get("role") == "outer_agent" for r in opens),
                     "inner_planning_requests": sum(r.get("role") == "inner_langchain" for r in opens),
                     "project_attempt_records": sum(r.get("kind") == "open" and r.get("op") == "llm_attempt" for r in ledger_rows),
                     "http_exchange_count": "unknown",
                     "usage_records": usage_rows,
                     "request_summaries": request_summaries,
                     "parse_diagnostics": parse_diagnostics,
                     "observed_total_tokens": observed_total,
                     "unclosed_request_ids": sorted(requests - closed),
                     "correlation_missing_count": sum(
                         row.get("kind") == "diagnostic" and
                         row.get("request_id_available") is False for row in ledger_rows),
                     "parse_diagnostic_count": len(parse_diagnostics)},
        "tools": {"calls": len(result_rows),
                  "results": [{"name": r.get("name"), "ok": r.get("ok"),
                               "error_type": (r.get("metadata") or {}).get("error_type"),
                               "request_id": (r.get("metadata") or {}).get("request_id"),
                               "finish_reason": (r.get("metadata") or {}).get("finish_reason"),
                               "session_id": (r.get("metadata") or {}).get("session_id")}
                              for r in result_rows]},
        "agent": {"termination": record.get("termination"),
                  "complete_marker": record.get("agent_complete"),
                  "container_return_code": record.get("container_exit_code"),
                  "done_events": sum(row.get("type") == "done" for row in agent_rows),
                  "error_events": sum(row.get("type") == "error" for row in agent_rows)},
        "time": {"attempt_wall_s": record.get("attempt_wall_s"),
                 "agent_work_phase": record.get("phases", {}).get("agent_work"),
                 "sampling_window": record.get("phases", {}).get("sampling_stopped"),
                 "closeout": record.get("phases", {}).get("closeout")},
        "resources": record.get("resource_summary"),
        "network_scope": record.get("network_observation_scope"),
        "cleanup_errors": record.get("cleanup_errors"),
        "container_removed_verified": record.get("cleanup_absent_verified"),
        "image_retained": True,
    }
    write_json(out / "run-report.json", report)
    return report


def generate_manifest(namespace: Path):
    rows = []
    for path in sorted(namespace.rglob("*")):
        if (not path.is_file() or path.name == "manifest.json"
                or "__pycache__" in path.parts or path.suffix == ".pyc"):
            continue
        rows.append({"path": path.relative_to(namespace).as_posix(),
                     "bytes": path.stat().st_size, "sha256": sha(path)})
    write_json(namespace / "manifest.json", {
        "task": "VIMAX-PLANNING-VALIDATE-02",
        "files": rows,
        "self_hash": "omitted",
    })


def run_attempt(out: Path, approval_path: Path) -> int:
    if not out.is_dir() or not approval_path.is_file():
        raise RuntimeError("preflight output or approval is missing")
    approval = validate_approval(out, approval_path)
    workspace = out / "workspace"
    attempt_dir = workspace / "attempt"
    if (out / "ATTEMPT-STARTED").exists():
        raise RuntimeError("attempt marker already exists; refusing another run")
    t0 = time.monotonic()
    start_utc = now_iso()
    (out / "ATTEMPT-STARTED").write_text(start_utc + "\n", encoding="utf-8")
    run_id = approval["run_id"]
    name = "vimax-plan-" + uuid.uuid4().hex[:10]
    record = {
        "task": "VIMAX-PLANNING-VALIDATE-02", "run_id": run_id,
        "attempt": 1, "retry": 0, "started_utc": start_utc,
        "t0_monotonic": t0, "image": approval["image"],
        "approval_sha256": sha(approval_path),
        "identity_sha256": approval["identity_sha256"],
        "entry_sha256": sha(Path(__file__).with_name("planning_entry.py")),
        "task_json_sha256": sha(TASK_JSON),
        "task_input_sha256": sha(workspace / "task-input.txt"),
        "registered_script_sha256": sha(workspace / "registered-script.txt"),
        "route": approval.get("route"), "budget": approval["budget"],
        "model_config": approval.get("model_config"),
        "container": {"name": name, "network_mode": "bridge",
                       "cpu_limit": 8, "memory_limit_bytes": 8589934592},
        "phases": {}, "cleanup_errors": [], "termination": "running",
        "model_http_exchange_count": "unknown",
    }
    write_json(out / "run-record.json", record)
    before = {"workspace": dir_measure(workspace),
              "attempt_directory": dir_measure(attempt_dir)}
    (out / "directory-before.json").write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8")
    sampler = ResourceSampler(interval_s=CGROUP_PERIOD_S)
    sampler_started = False
    container_id = ""
    net_stop = threading.Event()
    net_thread = None
    net_samples: list[dict] = []
    net_lock = threading.Lock()
    errors: list[str] = record["cleanup_errors"]
    work_deadline = t0 + WORK_S
    total_deadline = work_deadline + CLOSEOUT_S
    try:
        api_key = read_registered_key()
        env_values = {
            "PYTHONPATH": "/opt/vimax/src:/opt/validation",
            "VIMAX_LLM_API_KEY": api_key,
            "VIMAX_LLM_MODEL": LLM_MODEL,
            "VIMAX_LLM_MODEL_PROVIDER": "openai",
            "VIMAX_LLM_BASE_URL": LLM_BASE_URL,
            "VIMAX_AGENT_MAX_TOKENS": "8192",
            "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
            "VIMAX_FROZEN_SCRIPT_SHA256": REGISTERED_SCRIPT_SHA256,
            "VIMAX_BAILIAN_EVENT_LOG": "/workspace/attempt/model-events.jsonl",
            "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
            "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
            "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192",
            "VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS": "0",
            "VIMAX_BAILIAN_BUDGET_VIDEO_CREATES": "0",
            "VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS": "250000",
            "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS": str(WORK_S),
            "VIMAX_ENABLE_RUN_SHELL": "0",
        }
        entry = Path(__file__).with_name("planning_entry.py").resolve()
        docker = ["docker", "--host", "unix:///var/run/docker.sock", "run",
                  "-d", "--name", name,
                  "--label", f"org.agent-workload.task={run_id}",
                  "--network", "bridge", "--read-only",
                  "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
                  "--memory", "8g", "--cpus", "8", "--pids-limit", "512",
                  "--user", f"{os.getuid()}:{os.getgid()}",
                  "--workdir", "/workspace",
                  "--mount", f"type=bind,source={workspace},target=/workspace",
                  "--mount", f"type=bind,source={entry},target=/opt/validation/planning_entry.py,readonly",
                  "--mount", f"type=bind,source={Path(__file__).with_name('plan_verifier.py').resolve()},target=/opt/validation/plan_verifier.py,readonly"]
        for key, value in env_values.items():
            docker.extend(["--env", f"{key}={value}"])
        docker.extend([IMAGE, "python3", "/opt/validation/planning_entry.py"])
        started = run(docker, timeout=30)
        # Do not persist or print the command line, which contains the key.
        api_key = ""
        env_values["VIMAX_LLM_API_KEY"] = "<redacted>"
        if started.returncode:
            raise RuntimeError("docker run failed before native Agent startup; stderr withheld to protect runtime environment")
        container_id = started.stdout.strip()
        record["container"]["id"] = container_id
        record["container"]["argv_redacted"] = [
            "docker run -d", "--network bridge", "--memory 8g", "--cpus 8",
            "--read-only", "registered image", "native planning entry"]
        record["phases"]["container_started"] = {
            "wall_s": time.monotonic() - t0, "network": "bridge",
            "agent_deadline_monotonic": work_deadline}
        write_json(out / "run-record.json", record)

        sampler.register(run_id, "agent_container",
                         CgroupV1FileReader(run_id, "agent_container", container_id))
        sampler.start(run_id)
        sampler.start_background_sampling()
        sampler_started = True

        def sample_net():
            next_at = time.monotonic()
            while not net_stop.is_set():
                sample = netdev_snapshot(container_id)
                with net_lock:
                    net_samples.append(sample)
                next_at += NETNS_PERIOD_S
                net_stop.wait(max(0, next_at - time.monotonic()))

        net_thread = threading.Thread(target=sample_net, daemon=True)
        net_thread.start()
        complete = attempt_dir / "COMPLETE"
        while time.monotonic() < work_deadline:
            if complete.is_file():
                record["termination"] = "agent_completed"
                break
            state = run(["docker", "--host", "unix:///var/run/docker.sock",
                         "inspect", container_id, "--format", "{{.State.Running}}"], timeout=5)
            if state.returncode == 0 and state.stdout.strip() == "false":
                record["termination"] = "container_exited_without_complete"
                break
            time.sleep(0.25)
        else:
            record["termination"] = "work_deadline_1800s"
        record["phases"]["agent_work"] = {
            "wall_s": time.monotonic() - t0,
            "complete_marker_seen": complete.is_file(),
            "deadline_reached": time.monotonic() >= work_deadline}
        if record["termination"] == "work_deadline_1800s":
            killed = run(["docker", "--host", "unix:///var/run/docker.sock",
                          "kill", container_id], timeout=10)
            record["container_kill"] = {"returncode": killed.returncode,
                                        "stderr": killed.stderr[-200:]}
        else:
            final_net = netdev_snapshot(container_id)
            with net_lock:
                net_samples.append(final_net)
        net_stop.set()
        if net_thread is not None:
            net_thread.join(timeout=8)
            if net_thread.is_alive():
                errors.append("netns_sampler_thread_join_timeout")
        if sampler_started:
            sampler.stop_background_sampling()
            sampler.stop(run_id)
        record["phases"]["sampling_stopped"] = {"wall_s": time.monotonic() - t0}
    except BaseException as exc:
        record["termination"] = "runner_exception"
        record["primary_error"] = {"type": type(exc).__name__,
                                   "message": str(exc)[:1000]}
        raise
    finally:
        net_stop.set()
        if net_thread is not None and net_thread.is_alive():
            net_thread.join(timeout=8)
        if sampler_started:
            try:
                sampler.stop_background_sampling()
                sampler.stop(run_id)
            except Exception as exc:
                errors.append(f"sampler_stop:{type(exc).__name__}:{exc}")
        if container_id:
            try:
                info = run(["docker", "--host", "unix:///var/run/docker.sock",
                            "inspect", container_id, "--format",
                            "{{index .Config.Labels \"org.agent-workload.task\"}}"], timeout=5)
                owned = info.returncode == 0 and info.stdout.strip() == run_id
                record["cleanup_owner_verified"] = owned
                if owned:
                    stopped = run(["docker", "--host", "unix:///var/run/docker.sock",
                                   "stop", "--time", "10", container_id], timeout=15)
                    record["cleanup_stop_rc"] = stopped.returncode
                    waited = run(["docker", "--host", "unix:///var/run/docker.sock",
                                  "wait", container_id], timeout=10)
                    record["container_exit_code"] = (
                        waited.stdout.strip() if waited.returncode == 0 else None)
                    removed = run(["docker", "--host", "unix:///var/run/docker.sock",
                                   "rm", "-f", container_id], timeout=15)
                    record["cleanup_rm_rc"] = removed.returncode
                    verify = run(["docker", "--host", "unix:///var/run/docker.sock",
                                  "inspect", container_id], timeout=5)
                    record["cleanup_absent_verified"] = verify.returncode != 0
                    if verify.returncode == 0:
                        errors.append("container_removal_not_verified")
                else:
                    errors.append("container_cleanup_ownership_unverified")
            except Exception as exc:
                errors.append(f"container_cleanup:{type(exc).__name__}:{exc}")
        record["phases"]["closeout"] = {"wall_s": time.monotonic() - t0,
                                         "total_deadline_s": total_deadline - t0}
        if sampler_started:
            try:
                evidence = sampler.all_scope_evidence()
                (out / "resource-evidence.json").write_text(
                    json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                summaries = sampler.all_scope_summaries()
                record["resource_summary"] = summaries
            except Exception as exc:
                errors.append(f"resource_export:{type(exc).__name__}:{exc}")
        (out / "directory-after.json").write_text(json.dumps({
            "workspace": dir_measure(workspace),
            "attempt_directory": dir_measure(attempt_dir)}, indent=2) + "\n",
            encoding="utf-8")
        with net_lock:
            net_rows = list(net_samples)
        (out / "netns-samples.jsonl").write_text("".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in net_rows),
            encoding="utf-8")
        intervals = []
        for left, right in zip(net_rows, net_rows[1:]):
            dt_ns = right.get("t_monotonic_ns", 0) - left.get("t_monotonic_ns", 0)
            row = {"t_start_monotonic_ns": left.get("t_monotonic_ns"),
                   "t_end_monotonic_ns": right.get("t_monotonic_ns"),
                   "interval_s": dt_ns / 1e9 if dt_ns > 0 else None,
                   "read_status": "unknown"}
            if left.get("read_status") == right.get("read_status") == "ok" and dt_ns > 0:
                rates = {}
                before_if = left.get("interfaces", {})
                after_if = right.get("interfaces", {})
                for iface in sorted(set(before_if) | set(after_if)):
                    a, b = before_if.get(iface), after_if.get(iface)
                    if a is None or b is None:
                        rates[iface] = {"rx_bytes_per_s": None,
                                        "tx_bytes_per_s": None,
                                        "reason": "interface_missing_at_boundary"}
                    elif b["rx_bytes"] < a["rx_bytes"] or b["tx_bytes"] < a["tx_bytes"]:
                        rates[iface] = {"rx_bytes_per_s": None,
                                        "tx_bytes_per_s": None,
                                        "reason": "counter_reset"}
                    else:
                        seconds = dt_ns / 1e9
                        rates[iface] = {
                            "rx_bytes_per_s": (b["rx_bytes"] - a["rx_bytes"]) / seconds,
                            "tx_bytes_per_s": (b["tx_bytes"] - a["tx_bytes"]) / seconds}
                row.update({"read_status": "ok", "interfaces": rates,
                            "gap_over_target": dt_ns > int(NETNS_PERIOD_S * 1.5e9)})
            else:
                row["reason"] = "missing_counter_boundary_or_nonpositive_interval"
            intervals.append(row)
        (out / "netns-intervals.jsonl").write_text("".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in intervals),
            encoding="utf-8")
        complete = attempt_dir / "COMPLETE"
        if complete.is_file():
            try:
                record["agent_complete"] = json.loads(complete.read_text())
            except Exception as exc:
                errors.append(f"complete_marker_parse:{type(exc).__name__}")
        if "container_exit_code" not in record:
            record["container_exit_code"] = None
        record["attempt_wall_s"] = time.monotonic() - t0
        record["network_observation_scope"] = "container network namespace per-interface RX/TX"
        record["model_http_exchange_count"] = "unknown: no HTTP transport instrumentation"
        record["cleanup_errors"] = errors
        try:
            record["run_report_status"] = "pending"
            write_json(out / "run-record.json", record)
            summarize_run(out, record)
            record["run_report_status"] = "written"
        except Exception as exc:
            record["run_report_status"] = "failed"
            record["run_report_error"] = {"type": type(exc).__name__,
                                          "message": str(exc)[:500]}
        write_json(out / "run-record.json", record)
        (out / "resource-samples.jsonl").write_text("".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in (sampler.all_scope_evidence().get(run_id, {}).get("samples", [])
                        if sampler_started else [])), encoding="utf-8")
    return 0 if record.get("termination") == "agent_completed" and not errors else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("preflight", "run"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--approval")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if args.mode == "preflight":
        result = preflight(out)
        write_json(out / "preflight.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not args.approval:
        raise SystemExit("--approval is required for run mode")
    try:
        return run_attempt(out, Path(args.approval).resolve())
    finally:
        generate_manifest(out.parent)


if __name__ == "__main__":
    raise SystemExit(main())
