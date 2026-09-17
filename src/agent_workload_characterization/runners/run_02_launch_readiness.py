"""READY-01 launch-readiness plan and separately gated read-only check.

The plan is side-effect free.  ``--check`` is a later, separately approved
operation: it reads the selected credential reference in memory, validates the
fixed local Docker endpoint/digest, and starts one short synthetic child only
to verify restricted environment propagation.  It never calls smoke/model
code or a benchmark.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import smoke_launcher
from .run_02_entry import (CATALOG_SHA256, RECORD_SHA256, TARGET_IMAGE,
                           CODE_IDENTITY_PATHS)
from .report_writer import guard

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COLLECTION = "READY-01"
DEFAULT_CONFIG = smoke_launcher.DEFAULT_CONFIG
CHECK_ROOT = PROJECT_ROOT / "reports/preparation/READY-01"
READ_ONLY_CHECK_APPROVAL = "pending"
CHECK_WALL_S = 60.0
CHILD_WALL_S = 5.0


class ReadinessError(RuntimeError):
    pass


def _safe_category(exc: BaseException) -> str:
    if isinstance(exc, smoke_launcher.LauncherError):
        return str(exc)
    if isinstance(exc, ReadinessError):
        return str(exc)
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError):
        return "tool_unavailable"
    return "unknown"


def _identity() -> dict:
    code = {name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in CODE_IDENTITY_PATHS.items()}
    code["runners/run_02_launch_readiness.py"] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    code["runners/smoke_launcher.py"] = hashlib.sha256(
        Path(smoke_launcher.__file__).read_bytes()).hexdigest()
    return {
        "check_collection": COLLECTION,
        "parent_collection": "RUN-02",
        "parent_attempt": "RUN-02-R1",
        "task_instance_id": "django__django-16485",
        "record_sha256": RECORD_SHA256,
        "catalog_sha256": CATALOG_SHA256,
        "image": TARGET_IMAGE,
        "model_route": "openai/deepseek-v4-flash",
        "interpreters": {
            "evaluator": str(PROJECT_ROOT / ".venvs/swebench-eval-02e7a74/bin/python"),
            "mini": str(PROJECT_ROOT / ".venvs/mini-swe-agent-2.4.6-env01/bin/python"),
        },
        "credential_route": {
            "source": str(DEFAULT_CONFIG),
            "provider": smoke_launcher.PROVIDER_NAME,
            "model_key": smoke_launcher.MODEL_KEY,
            "reference": "{env:VOLCANO_API_KEY}",
            "parent_setter": "operator sets VOLCANO_API_KEY in the approved check process environment",
            "child_mapping": ["PILOT_API_BASE", "PILOT_API_KEY"],
            "in_memory_only": True,
        },
        "docker_endpoint": "unix:///var/run/docker.sock",
        "output_root": "reports/preparation/READY-01/<check_id>",
        "budget": {
            "check_wall_s": CHECK_WALL_S,
            "child_wall_s": CHILD_WALL_S,
            "report_threshold_bytes": 1_048_576,
            "docker": "read_only_context_daemon_digest_inspect_only",
            "api": False,
            "containers": False,
        },
        "read_only_check_approval": READ_ONLY_CHECK_APPROVAL,
        "code_sha256": code,
    }


def build_plan() -> dict:
    return {
        "mode": "offline_plan",
        "identity": _identity(),
        "entry": {
            "module": __name__,
            "interpreter": str(PROJECT_ROOT / ".venvs/swebench-eval-02e7a74/bin/python"),
            "plan_command": (
                "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python "
                "-m agent_workload_characterization.runners.run_02_launch_readiness"),
            "check_command": (
                "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python "
                "-m agent_workload_characterization.runners.run_02_launch_readiness "
                "--check"),
        },
        "authorization": {
            "read_only_check_approval": READ_ONLY_CHECK_APPROVAL,
            "tool_execution_permission": "pending",
            "task_execution": False,
        },
        "side_effects": {
            "docker": False, "network": False, "api": False,
            "credentials_read": False, "runner": False,
            "r2_created": False,
        },
    }


def _validate_parent_environment() -> dict:
    docker_host = os.environ.get("DOCKER_HOST")
    docker_context = os.environ.get("DOCKER_CONTEXT")
    proxy_vars = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
                  "https_proxy", "all_proxy", "SMOKE_APPROVED_PROXY")
    return {
        "docker_host_fixed_or_unset": docker_host in (None, "unix:///var/run/docker.sock"),
        "docker_context_local_or_unset": docker_context in (None, "", "default"),
        "proxy_unset": not any(os.environ.get(v) for v in proxy_vars),
    }


def _child_probe_env(env: dict[str, str], deadline: float) -> dict:
    remaining = max(0.0, min(CHILD_WALL_S, deadline - time.monotonic()))
    if remaining <= 0:
        raise subprocess.TimeoutExpired("readiness-child", CHILD_WALL_S)
    code = (
        "import json, os; "
        "print(json.dumps({" 
        "'base_present': bool(os.environ.get('PILOT_API_BASE')), "
        "'key_present': bool(os.environ.get('PILOT_API_KEY')), "
        "'proxy_absent': not any(os.environ.get(k) for k in "
        "('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')), "
        "'docker_host_absent': not os.environ.get('DOCKER_HOST'), "
        "'argv_safe': True}))")
    proc = subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=remaining,
                          cwd=str(PROJECT_ROOT))
    if proc.returncode != 0:
        raise ReadinessError("child_probe_failed")
    try:
        result = json.loads(proc.stdout)
    except (ValueError, TypeError):
        raise ReadinessError("child_probe_invalid_result")
    if not isinstance(result, dict):
        raise ReadinessError("child_probe_invalid_result")
    keys = ("base_present", "key_present", "proxy_absent",
            "docker_host_absent", "argv_safe")
    if any(type(result.get(key)) is not bool for key in keys):
        raise ReadinessError("child_probe_invalid_result")
    return {key: result[key] for key in keys}


def _selected_credential_reference(config_path: Path) -> bool:
    """Check the selected field without resolving or exposing its value."""
    try:
        raw = config_path.read_bytes()
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError:
            cfg = json.loads(smoke_launcher._strip_jsonc(raw.decode("utf-8")))
        provider = cfg["provider"][smoke_launcher.PROVIDER_NAME]
        model = provider["models"][smoke_launcher.MODEL_KEY]
        if not isinstance(model, dict):
            return False
        reference = provider["options"]["apiKey"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        raise ReadinessError("credential_config_invalid")
    return reference == "{env:VOLCANO_API_KEY}"


def _write_report(project_root: Path, payload: dict, check_id: str) -> Path:
    destination = guard(project_root, Path("reports/preparation/READY-01") / check_id)
    destination.mkdir(parents=True, exist_ok=False)
    safe = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(safe.encode("utf-8")) > 1_048_576:
        raise ReadinessError("report_threshold_exceeded")
    (destination / "summary.json").write_text(safe, encoding="utf-8")
    manifest = {"files": {"summary.json": hashlib.sha256(
        (destination / "summary.json").read_bytes()).hexdigest()},
                "check_id": check_id, "kind": "READY-01-read-only-check"}
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return destination


def run_check() -> dict:
    """Run only the later-approved read-only check; never call this in A."""
    started = time.monotonic()
    check_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    payload = {"check_id": check_id, "status": "NOT_READY",
               "kind": "READY-01-read-only-check", "api_called": False,
               "task_started": False, "container_started": False,
               "categories": [], "checks": {
                   "task_identity": {"status": "registered_not_checked",
                                     "sha256": RECORD_SHA256},
                   "catalog_identity": {"status": "registered_not_checked",
                                         "sha256": CATALOG_SHA256},
               }, "identity": _identity()}
    try:
        parent = _validate_parent_environment()
        payload["checks"]["parent_environment"] = parent
        if not all(parent.values()):
            payload["categories"].append("unapproved_parent_environment")
            raise ReadinessError("unapproved_parent_environment")
        if not _selected_credential_reference(DEFAULT_CONFIG):
            raise ReadinessError("credential_route_not_selected")
        api_base, api_key = smoke_launcher.load_credentials(DEFAULT_CONFIG)
        env = smoke_launcher.build_restricted_env(api_base, api_key)
        if any(env.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                                    "http_proxy", "https_proxy", "all_proxy")):
            raise ReadinessError("proxy_not_approved")
        payload["checks"]["credential_config_parsed"] = True
        payload["checks"]["credential_route"] = "env_reference_to_memory_to_child_env"
        child = _child_probe_env(env, started + CHECK_WALL_S)
        payload["checks"]["child_environment"] = child
        if any(type(value) is not bool or not value
               for value in child.values()):
            raise ReadinessError("child_environment_not_ready")
        from . import run_02_entry
        preflight = run_02_entry._docker_preflight(
            max(0.1, CHECK_WALL_S - (time.monotonic() - started)))
        docker_checks = {
            "context": preflight.get("context") == "default",
            "endpoint_fixed": preflight.get("endpoint") == "unix:///var/run/docker.sock",
            "image_architecture": preflight.get("architecture") in ("arm64", "aarch64"),
            "image_os": preflight.get("os") == "linux",
        }
        if any(type(value) is not bool or not value
               for value in docker_checks.values()):
            raise ReadinessError("docker_preflight_not_ready")
        payload["checks"]["docker_read_only_preflight"] = docker_checks
        payload["checks"]["task_identity"] = {
            "status": "registered_not_checked",
            "sha256": RECORD_SHA256,
        }
        payload["checks"]["catalog_identity"] = {
            "status": "registered_not_checked",
            "sha256": CATALOG_SHA256,
        }
        payload["status"] = "READY_FOR_APPROVAL"
    except Exception as exc:  # noqa: BLE001 — fixed safe category only
        category = _safe_category(exc)
        payload["categories"].append(category)
        payload["status"] = "NOT_READY"
    payload["elapsed_s"] = round(time.monotonic() - started, 6)
    destination = _write_report(PROJECT_ROOT, payload, check_id)
    payload["report_dir"] = str(destination)
    return payload


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.check:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    result = run_check()
    print(json.dumps({key: value for key, value in result.items()
                      if key != "identity"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "READY_FOR_APPROVAL" else 4


if __name__ == "__main__":
    raise SystemExit(main())
