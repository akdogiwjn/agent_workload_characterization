"""RUN-02 A/B entry for one independent SWE-bench attempt.

The default mode is a side-effect-free plan.  The execution branch is
implemented and identity-bound for a later, separate user approval, but A
does not create an approval record or call Docker/model code.  The runner
components are the existing CodingPilotRunner/MiniSweAgentHarness and the
existing hook, host collector, resource sampler, and cleanup state machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COLLECTION = "RUN-02"
CATALOG_PATH = PROJECT_ROOT / "workload_catalog/run_02.yaml"
CATALOG_SHA256 = "fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656"
RECORD_PATH = (PROJECT_ROOT / "data/raw/public/swebench_verified/"
               "78f471bf655a3137b2e8a75af1501690ec009ec3/"
               "django__django-16485/record.json")
RECORD_SHA256 = "762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a"
TARGET_IMAGE = ("swebench/sweb.eval.arm64.django_1776_django-16485"
                "@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254"
                "e1de00040e6db3b7d2")
MINI_VENV_PY = PROJECT_ROOT / ".venvs/mini-swe-agent-2.4.6-env01/bin/python"
EVAL_VENV_PY = PROJECT_ROOT / ".venvs/swebench-eval-02e7a74/bin/python"
APPROVAL_PATH = PROJECT_ROOT / "reports/resource/RUN-02/APPROVAL.txt"
ATTEMPT_MARKER_PATH = PROJECT_ROOT / "reports/resource/RUN-02/ATTEMPT_STARTED.json"
PREFLIGHT_EVIDENCE_PATH = None
IDENTITY_EXTRAS = {}
API_BASE_ENV = "PILOT_API_BASE"
API_KEY_ENV = "PILOT_API_KEY"
SDK_BASE_ENV = "OPENAI_API_BASE"
SDK_KEY_ENV = "OPENAI_API_KEY"
MODEL_NAME = "openai/deepseek-v4-flash"


class Run02EntryError(RuntimeError):
    pass


class Run02PreflightError(Run02EntryError):
    pass


class Run02ExecutionError(Run02EntryError):
    pass


def _read_catalog() -> dict:
    import yaml
    raw = CATALOG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise Run02EntryError("RUN-02 catalog SHA-256 mismatch")
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("collection_id") != COLLECTION:
        raise Run02EntryError("RUN-02 catalog identity is invalid")
    if data.get("execution_authorized") is not False:
        raise Run02EntryError("catalog cannot authorize execution")
    return data


def _record() -> dict:
    raw = RECORD_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECORD_SHA256:
        raise Run02EntryError("task record SHA-256 mismatch")
    return json.loads(raw)


def _positive(value, name: str, integral: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Run02EntryError(f"budget {name} has invalid type")
    if integral and not isinstance(value, int):
        raise Run02EntryError(f"budget {name} must be an integer")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise Run02EntryError(f"budget {name} must be finite and positive")
    return result


def _limits(catalog: dict):
    from .coding_pilot import BudgetLimits
    b = catalog["budget_proposal"]
    for k in ("model_requests", "steps", "output_tokens_per_request"):
        _positive(b[k], k, integral=True)
    for k in ("agent_wall_min", "verifier_wall_min", "total_wall_min",
              "run_dir_threshold_gib"):
        _positive(b[k], k)
    return BudgetLimits(
        max_model_requests=b["model_requests"], max_steps=b["steps"],
        max_output_tokens_per_request=b["output_tokens_per_request"],
        agent_wall_s=b["agent_wall_min"] * 60.0,
        verifier_wall_s=b["verifier_wall_min"] * 60.0,
        total_wall_s=b["total_wall_min"] * 60.0,
        max_new_artifact_bytes=int(b["run_dir_threshold_gib"] * 2**30),
    )


CODE_IDENTITY_PATHS = {
    "runners/run_02_entry.py": Path(__file__).resolve(),
    "runners/coding_pilot.py": Path(__file__).with_name("coding_pilot.py").resolve(),
    "runners/mini_agent_adapter.py": Path(__file__).with_name("mini_agent_adapter.py").resolve(),
    "runners/container_runtime.py": Path(__file__).with_name("container_runtime.py").resolve(),
    "runners/tool_event_env.py": Path(__file__).with_name("tool_event_env.py").resolve(),
    "collectors/host_process.py": (Path(__file__).resolve().parents[1]
                                    / "collectors/host_process.py").resolve(),
    "collectors/resource_sampler.py": (Path(__file__).resolve().parents[1]
                                       / "collectors/resource_sampler.py").resolve(),
    "analyzers/run_02_analysis.py": (Path(__file__).resolve().parents[1]
                                      / "analyzers/run_02_analysis.py").resolve(),
}


def _code_hashes() -> dict[str, str]:
    return {name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in CODE_IDENTITY_PATHS.items()}


def _claim_attempt(identity: dict, project_root: Path | None = None) -> int:
    """Atomically consume the one-attempt execution slot.

    The marker is intentionally retained on every outcome, including
    preflight or infrastructure failure: a failed attempt is not silently
    retryable.  A later call can only read the marker and deliver it.
    """
    from .report_writer import guard_resource_namespace
    state_dir = guard_resource_namespace(
        project_root or PROJECT_ROOT, ATTEMPT_MARKER_PATH.parent, COLLECTION)
    if ATTEMPT_MARKER_PATH.parent.resolve() != state_dir:
        raise Run02EntryError("RUN-02 attempt marker path is outside guarded root")
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"status": "started", "started_at_utc": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "identity": identity}
    try:
        fd = os.open(str(ATTEMPT_MARKER_PATH),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise Run02EntryError(
            "RUN-02 already has an attempt registration; deliver it read-only"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return 0


def _update_attempt_marker(**fields) -> None:
    if not ATTEMPT_MARKER_PATH.is_file():
        return
    try:
        data = json.loads(ATTEMPT_MARKER_PATH.read_text(encoding="utf-8"))
        data.update(fields)
        tmp = ATTEMPT_MARKER_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(ATTEMPT_MARKER_PATH)
    except (OSError, ValueError):
        # The original marker remains evidence even if final status update fails.
        return


def _docker_preflight(timeout_s: float = 60.0) -> dict:
    """Verify only the fixed local endpoint and already-present digest.

    This is called only after B approval and attempt claim.  It never pulls,
    builds, or starts a container.
    """
    deadline = time.monotonic() + timeout_s
    env = dict(os.environ)
    env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    env.pop("DOCKER_CONTEXT", None)

    def classify(stage: str, stderr: str = "") -> str:
        text = (stderr or "").lower()
        if "timed out" in text or "timeout" in text:
            return "timeout"
        if stage == "inspect" and any(token in text for token in
                                      ("no such image", "manifest unknown",
                                       "image not found")):
            return "image_not_found"
        if any(token in text for token in
               ("permission denied", "operation not permitted",
                "access denied")):
            return "socket_access_denied"
        if any(token in text for token in
               ("cannot connect", "connection refused", "no such file or directory",
                "is the docker daemon running")):
            return "daemon_unavailable"
        return "unknown"

    def run(argv, stage):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Run02PreflightError("RUN-02 Docker preflight exceeded 60s")
        try:
            return subprocess.run(argv, env=env, capture_output=True,
                                  text=True, timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise Run02PreflightError(
                "RUN-02 preflight category=timeout") from exc
        except PermissionError as exc:
            raise Run02PreflightError(
                "RUN-02 preflight category=socket_access_denied") from exc
        except FileNotFoundError as exc:
            raise Run02PreflightError(
                "RUN-02 preflight category=unknown") from exc
        except OSError as exc:
            raise Run02PreflightError(
                "RUN-02 preflight category=unknown") from exc

    ctx = run(["docker", "context", "show"], "context")
    if ctx.returncode != 0 or ctx.stdout.strip() != "default":
        category = classify("context", getattr(ctx, "stderr", ""))
        raise Run02PreflightError(
            f"RUN-02 preflight category={category}: local context unavailable")
    image = run(["docker", "image", "inspect", TARGET_IMAGE,
                 "--format", "{{.Id}} {{.Architecture}} {{.Os}}"], "inspect")
    if image.returncode != 0:
        category = classify("inspect", getattr(image, "stderr", ""))
        raise Run02PreflightError(
            f"RUN-02 preflight category={category}: fixed digest inspect failed")
    fields = image.stdout.strip().split()
    if len(fields) < 3 or fields[1] not in ("arm64", "aarch64") \
            or fields[2] != "linux":
        raise Run02PreflightError(
            "RUN-02 preflight category=unknown: image architecture/OS mismatch")
    os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    os.environ.pop("DOCKER_CONTEXT", None)
    return {"context": "default", "endpoint": "unix:///var/run/docker.sock",
            "image": TARGET_IMAGE, "architecture": fields[1], "os": fields[2]}


def build_run02_runner(*, authorized: bool, credentials: dict | None = None,
                       runtime=None, harness=None, verifier=None,
                       project_root: Path | None = None):
    """Assemble the existing runner chain under the independent RUN-02 id."""
    from .coding_pilot import (CodingPilotRunner, VerifierSpec,
                               SwebenchVerifierRunner)
    from .container_runtime import DockerCliRuntime
    from .mini_agent_adapter import AgentTask, MiniSweAgentHarness

    catalog = _read_catalog()
    record = _record()
    if not MINI_VENV_PY.is_file() or not EVAL_VENV_PY.is_file():
        raise Run02EntryError("registered venv interpreter is missing")
    bundled = MiniSweAgentHarness.load_bundled_config(MINI_VENV_PY)
    mini_config = {
        "agent": dict(bundled.get("agent") or {}),
        "model": {"model_name": MODEL_NAME, "model_kwargs": {
            k: v for k, v in (bundled.get("model", {}).get("model_kwargs")
                              or {}).items()
            if k not in ("num_retries", "max_tokens")}},
        "environment": dict(bundled.get("environment") or {}),
    }
    harness = harness or MiniSweAgentHarness(
        MINI_VENV_PY, authorized=authorized, mini_config=mini_config,
        target_image_ref=TARGET_IMAGE, poll_interval_s=0.2)
    runner = CodingPilotRunner(
        project_root=project_root or PROJECT_ROOT, collection=COLLECTION,
        harness=harness, verifier=verifier or SwebenchVerifierRunner(
            authorized=authorized, model_name="mini-SWE-agent-2.4.6"),
        runtime=runtime or DockerCliRuntime(authorized=authorized,
                                            collection=COLLECTION),
        limits=_limits(catalog),
        task=AgentTask(instance_id=record["instance_id"],
                       problem_statement=record["problem_statement"],
                       image=TARGET_IMAGE, source_type="benchmark_real"),
        verifier_spec=VerifierSpec(
            instance_id=record["instance_id"], image=TARGET_IMAGE,
            eval_script_ref="record.json", log_parser=record["log_parser"],
            eval_type=record["eval_type"], record_locator=str(RECORD_PATH)),
        image=TARGET_IMAGE, source_type="benchmark_real",
        credentials=credentials,
        agent_container_cpu="4", agent_container_mem="8g",
        verifier_container_cpu="4", verifier_container_mem="8g")
    identity = {
        "collection": COLLECTION,
        "task": {"instance_id": record["instance_id"],
                 "record_locator": str(RECORD_PATH),
                 "record_sha256": RECORD_SHA256,
                 "base_commit": record.get("base_commit")},
        "image": TARGET_IMAGE,
        "catalog_sha256": CATALOG_SHA256,
        "code_sha256": _code_hashes(),
        "model": MODEL_NAME,
        "harness": "mini-SWE-agent 2.4.6",
        "interpreters": {"mini": str(MINI_VENV_PY),
                         "evaluator": str(EVAL_VENV_PY)},
        "budget": _limits(catalog).to_dict(),
        "container_limits": {"cpu": 4, "memory": "8g", "network": "none",
                             "pull": "never"},
        "sampling": {"mini_host_process_s": 0.2,
                     "resource_s": 0.5, "artifact_monitor_s": 0.25},
        "credentials_env": {"base": API_BASE_ENV, "key": API_KEY_ENV,
                            "child_base": SDK_BASE_ENV,
                            "child_key": SDK_KEY_ENV},
        "output": {"raw": "data/raw/generated/RUN-02/<run_id>",
                   "report": "reports/resource/RUN-02/<run_id>"},
        "approval": "reports/resource/RUN-02/APPROVAL.txt",
        "proxy": "not required by static plan; any proxy must be approved",
    }
    identity.update(IDENTITY_EXTRAS)
    return runner, identity


def build_plan() -> dict:
    catalog = _read_catalog()
    record = _record()
    _, identity = build_run02_runner(authorized=False)
    return {"mode": "offline_plan", "collection": COLLECTION,
            "entry": {"module": __name__, "interpreter": str(EVAL_VENV_PY),
                      "plan_command": "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.run_02_entry",
                      "execute_command": "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.run_02_entry --execute --i-approve-the-run-02"},
            "identity": identity,
            "catalog_sha256": hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
            "record_instance_id": record["instance_id"],
        "authorization": {"user_approval": "pending", "execution": False,
                           "tool_execution_permission": "pending"},
            "side_effects": {"docker": False, "network": False,
                              "model": False, "credentials_read": False}}


def _credentials() -> dict:
    if not os.environ.get(API_BASE_ENV) or not os.environ.get(API_KEY_ENV):
        raise Run02EntryError("RUN-02 credentials are required only at execution time")
    return {SDK_BASE_ENV: os.environ[API_BASE_ENV], SDK_KEY_ENV: os.environ[API_KEY_ENV]}


def execute_run02() -> dict:
    if not APPROVAL_PATH.is_file():
        raise Run02EntryError("RUN-02 approval record is missing")
    runner, identity = build_run02_runner(authorized=True, credentials=None)
    try:
        approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Run02EntryError("RUN-02 approval record is not valid JSON") from exc
    if approval.get("checklist_identity") != identity:
        raise Run02EntryError("RUN-02 approval identity mismatch")
    if not approval.get("approved_by") or not approval.get("approved_at_utc"):
        raise Run02EntryError("RUN-02 approval record lacks approver/time")
    _claim_attempt(identity, runner.project_root)
    try:
        preflight = _docker_preflight(60.0)
    except Run02PreflightError as exc:
        if PREFLIGHT_EVIDENCE_PATH is not None:
            from .report_writer import guard_resource_namespace
            evidence_path = Path(PREFLIGHT_EVIDENCE_PATH)
            guard_resource_namespace(runner.project_root, evidence_path.parent,
                                     COLLECTION)
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({
                "status": "failed",
                "error": str(exc),
                "raw_error_persisted": False,
                "attempt_label": IDENTITY_EXTRAS.get("attempt_label", COLLECTION),
            }, ensure_ascii=False, indent=2) + "\n"
            fd = os.open(str(evidence_path), os.O_WRONLY | os.O_CREAT |
                         os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
        _update_attempt_marker(status="failed", error=str(exc))
        raise
    try:
        credentials = _credentials()
    except Exception as exc:  # noqa: BLE001 — fixed category only
        # Credential failures happen after the one-shot claim and must consume
        # the slot just like preflight failures.  Never persist exception text
        # because it could contain a provider value.
        _update_attempt_marker(
            status="failed", error=f"credentials:{type(exc).__name__}")
        raise
    runner.credentials = credentials
    try:
        outcome = runner.run()
        from ..analyzers.run_02_analysis import write_run_02_report
        report_dir = (Path(outcome.run_dir).parents[4] / "reports" / "resource"
                      / COLLECTION / outcome.run_id)
        try:
            report = write_run_02_report(report_dir, Path(outcome.run_dir),
                                         identity=identity)
        except Exception as exc:  # noqa: BLE001 — sanitized marker evidence
            _update_attempt_marker(status="failed",
                                   error=f"report_generation:{type(exc).__name__}")
            raise Run02ExecutionError("RUN-02 report generation failed") from exc
        result = {"mode": "executed", "identity": identity,
                  "preflight": preflight, "run_id": outcome.run_id,
                  "run_dir": outcome.run_dir,
                  "report_dir": str(report_dir),
                  "execution_status": outcome.execution_status,
                  "evaluation_status": outcome.evaluation_status,
                  "archive_status": outcome.archive_status,
                  "cleanup_status": outcome.cleanup_status,
                  "cleanup_errors": outcome.cleanup_errors,
                  "report_status": report["status"],
                  "resolved": outcome.resolved,
                  "budget_usage": outcome.budget_usage}
        _update_attempt_marker(status="finished", result=result)
        return result
    except Exception as exc:
        _update_attempt_marker(status="failed", error=type(exc).__name__)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-approve-the-run-02", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    if not args.i_approve_the_run_02:
        print("REFUSED: --execute requires the RUN-02 approval flag", file=sys.stderr)
        return 2
    try:
        result = execute_run02()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        failed = (result.get("execution_status") in
                   {"infra_failure", "agent_error", "budget_exceeded",
                    "watchdog_timeout", "no_candidate"}
                   or result.get("evaluation_status") in
                   {"infra_failure", "verifier_timeout"}
                   or result.get("cleanup_status") != "ok"
                   or result.get("archive_status") != "ok"
                   or result.get("report_status") != "complete")
        return 5 if failed else 0
    except Run02PreflightError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    except Run02ExecutionError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 5
    except Run02EntryError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
