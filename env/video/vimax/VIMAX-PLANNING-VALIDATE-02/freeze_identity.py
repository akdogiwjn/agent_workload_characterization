from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PREFLIGHT = ROOT / "preflight-03"
EXECUTION = ROOT / "execution-01"
APPROVAL = ROOT / "APPROVAL-01.json"
IDENTITY = ROOT / "identity-01.json"
REGISTERED_SCRIPT_HASH = "447e4d88ccd76f9cb4a206f799993620a3c832238dd873c9ae9e905c2452b59a"
ALLOWED_TOOLS = [
    "glob_files", "list_files", "memory_read", "read_file",
    "read_json", "search_text", "todo_read", "vimax_narrative_planning",
]
BUDGET = {
    "logical_request_cap": 40,
    "request_attempt_cap": 40,
    "single_request_output_tokens": 8192,
    "narrative_node_output_tokens": 8192,
    "observed_total_tokens_soft_threshold": 250000,
    "shared_work_deadline_s": 1800.0,
    "closeout_reserve_s": 120.0,
    "image_generations": 0,
    "video_creates": 0,
    "sdk_retries": 0,
}
MODEL_CONFIG = {
    "model": "qwen3.7-plus",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "protocol": "OpenAI-compatible Chat Completions",
    "extra_body": {"enable_thinking": False},
    "outer_max_tokens": 8192,
    "internal_max_completion_tokens": 8192,
    "sdk_max_retries": 0,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    temp.replace(path)


def main() -> None:
    revise = "--revise-before-request" in sys.argv
    if (IDENTITY.exists() or APPROVAL.exists()) and revise:
        if (EXECUTION / "ATTEMPT-STARTED").exists():
            raise RuntimeError("cannot revise identity after an attempt has started")
        snapshot = ROOT / "freeze-iteration-01"
        snapshot.mkdir(exist_ok=False)
        if IDENTITY.exists():
            shutil.copy2(IDENTITY, snapshot / "identity-01.json")
        if APPROVAL.exists():
            shutil.copy2(APPROVAL, snapshot / "APPROVAL-01.json")
        (snapshot / "status.json").write_text(json.dumps({
            "status": "superseded_before_first_request",
            "reason": "approval omitted duplicated frozen route/tool/scope fields",
            "attempt_started": False, "model_requests": 0,
        }, indent=2) + "\n", encoding="utf-8")
    elif IDENTITY.exists() or APPROVAL.exists() or (EXECUTION / "ATTEMPT-STARTED").exists():
        raise RuntimeError("frozen identity, approval, or attempt marker already exists")
    preflight = json.loads((PREFLIGHT / "preflight.json").read_text())
    if not preflight.get("ok") or preflight.get("credential_values_read") is not False:
        raise RuntimeError("authoritative no-model preflight is absent or failed")
    if preflight["registered_script_sha256"] != REGISTERED_SCRIPT_HASH:
        raise RuntimeError("preflight registered script differs from prior task identity")
    if preflight["budget"] != BUDGET:
        raise RuntimeError("preflight budget differs from requested budget")
    if preflight["model_config"] != MODEL_CONFIG:
        raise RuntimeError("preflight model configuration differs from requested values")
    workspace_src = PREFLIGHT / "workspace"
    if EXECUTION.exists() and not revise:
        raise RuntimeError("execution directory already exists; refusing to overwrite")
    if revise:
        workspace_dst = EXECUTION / "workspace"
        if not workspace_dst.is_dir():
            raise RuntimeError("existing pre-attempt workspace is missing")
        for name in ("task-input.txt", "registered-script.txt",
                     "task-requirements.txt", "task-style.txt"):
            if (workspace_dst / name).read_bytes() != (workspace_src / name).read_bytes():
                raise RuntimeError("pre-attempt workspace differs from successful preflight")
    else:
        EXECUTION.mkdir()
        shutil.copytree(workspace_src, EXECUTION / "workspace")
        shutil.copy2(PREFLIGHT / "preflight.json", EXECUTION / "preflight.json")

    adapter_root = REPO / "env/video/vimax/adapter-src"
    source_files = {
        path.relative_to(adapter_root).as_posix(): sha(path)
        for path in sorted(adapter_root.rglob("*")) if path.is_file()
        and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    tree_bytes = json.dumps(source_files, sort_keys=True,
                            separators=(",", ":")).encode()
    source_tree_hash = hashlib.sha256(tree_bytes).hexdigest()
    run_id = (datetime.now(timezone.utc).strftime(
        "vimax-planning-validate-02-%Y%m%dT%H%M%SZ-")
        + uuid.uuid4().hex[:8])
    task_json = REPO / "references/repos/ViMax/vimax_benchmark/photographer_urban_timelapses_typeA.json"
    base_image_id = "sha256:f079f9479f8587207e1d3167c8ad8d759f81a2b25ad79a6a23f03514ee5c0533"
    image = preflight["image"]
    identity = {
        "task_namespace": "VIMAX-PLANNING-VALIDATE-02",
        "run_id": run_id, "attempt": 1, "retry": 0,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "frozen_before_first_real_request",
        "image": image,
        "base_image": {"id": base_image_id, "platform": "linux/arm64"},
        "image_derivation": "network=none, pull=false, code-only COPY, no dependency changes",
        "adapter_source_file_count": len(source_files),
        "adapter_source_tree_sha256": source_tree_hash,
        "adapter_source_files": source_files,
        "execution_code": {
            "host_runner_sha256": sha(ROOT / "host_runner.py"),
            "planning_entry_sha256": sha(ROOT / "planning_entry.py"),
            "plan_verifier_sha256": sha(ROOT / "plan_verifier.py"),
            "dockerfile_sha256": sha(ROOT / "Dockerfile"),
            "freeze_identity_sha256": sha(ROOT / "freeze_identity.py"),
        },
        "task_source": {
            "path": str(task_json.relative_to(REPO)),
            "sha256": sha(task_json),
            "registered_script_path": "execution-01/workspace/registered-script.txt",
            "registered_script_sha256": REGISTERED_SCRIPT_HASH,
            "task_prompt_sha256": preflight["task_input_sha256"],
            "task_requirements_sha256": preflight["task_requirements_sha256"],
            "task_style_sha256": preflight["task_style_sha256"],
            "shot_ids": list(range(1, 9)),
            "session_id": "planning-validation-02",
            "session_mode": "script",
        },
        "route": {
            "region": "cn-beijing",
            "model": MODEL_CONFIG["model"],
            "protocol": MODEL_CONFIG["protocol"],
            "base_url": MODEL_CONFIG["base_url"],
            "credential_variable": "DASHSCOPE_API_KEY",
            "credential_source": "/home/lcq/.config/agent-workload-characterization/bailian.env",
            "credential_values_persisted": False,
        },
        "model_config": MODEL_CONFIG,
        "budget": BUDGET,
        "tools": {
            "allowed": ALLOWED_TOOLS,
            "blocked": ["run_shell", "write_json", "vimax_render_video",
                        "vimax_novel_planning", "view_image", "memory_write",
                        "todo_write", "sleep"],
            "media_generations": 0,
        },
        "resources": {
            "container_cpu_limit": 8,
            "memory_limit_bytes": 8589934592,
            "cgroup_interval_target_s": 0.5,
            "netns_interval_target_s": 2.0,
            "network_mode": "bridge",
            "network_scope": "container network namespace interfaces",
        },
        "preflight": {
            "path": "preflight-02/preflight.json",
            "sha256": sha(PREFLIGHT / "preflight.json"),
            "source_hashes_match": preflight["adapter_source_hashes_match"],
            "tool_policy_and_kill_cleanup_checked": True,
            "credential_values_read": False,
            "model_requests": 0,
        },
        "validation": {
            "image_offline_test_log": "offline-tests-final-04.log",
            "image_offline_test_log_sha256": sha(ROOT / "offline-tests-final-04.log"),
            "image_offline_test_count": 30,
            "image_offline_test_returncode": 0,
        },
    }
    identity.update({
        "host_runner_sha256": identity["execution_code"]["host_runner_sha256"],
        "entry_sha256": identity["execution_code"]["planning_entry_sha256"],
        "verifier_sha256": identity["execution_code"]["plan_verifier_sha256"],
        "task_input_sha256": identity["task_source"]["task_prompt_sha256"],
        "task_json_sha256": identity["task_source"]["sha256"],
        "registered_script_sha256": REGISTERED_SCRIPT_HASH,
        "task_requirements_sha256": identity["task_source"]["task_requirements_sha256"],
        "task_style_sha256": identity["task_source"]["task_style_sha256"],
    })
    atomic_json(IDENTITY, identity)
    identity_sha = sha(IDENTITY)
    approval = {
        key: identity[key] for key in (
            "task_namespace", "run_id", "image", "model_config", "budget",
        )
    }
    approval.update({
        "identity_sha256": identity_sha,
        "host_runner_sha256": identity["execution_code"]["host_runner_sha256"],
        "entry_sha256": identity["execution_code"]["planning_entry_sha256"],
        "verifier_sha256": identity["execution_code"]["plan_verifier_sha256"],
        "task_input_sha256": identity["task_source"]["task_prompt_sha256"],
        "task_json_sha256": identity["task_source"]["sha256"],
        "registered_script_sha256": REGISTERED_SCRIPT_HASH,
        "task_requirements_sha256": identity["task_source"]["task_requirements_sha256"],
        "task_style_sha256": identity["task_source"]["task_style_sha256"],
        "route": identity["route"],
        "tools": identity["tools"],
        "resources": identity["resources"],
        "task_source": identity["task_source"],
        "attempts_authorized": 1, "retry": 0,
        "allowed_tools": ALLOWED_TOOLS,
        "approved_before_first_real_request": True,
        "api_cost": "unknown; user authorized this limited planning run",
    })
    atomic_json(APPROVAL, approval)
    print(json.dumps({
        "identity_sha256": identity_sha,
        "approval_sha256": sha(APPROVAL),
        "run_id": run_id,
        "image_id": image["id"],
        "adapter_source_tree_sha256": source_tree_hash,
        "first_real_request_not_yet_sent": True,
    }, indent=2))


if __name__ == "__main__":
    main()
