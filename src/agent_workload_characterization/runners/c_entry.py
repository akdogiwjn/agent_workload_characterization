"""RUN-01 gate C minimal execution entry (offline assembly; run is gated).

This is the single registered entry for the one approved-if-ever C run
(task brief §8.2 registration). It assembles the ALREADY-VALIDATED
components (CodingPilotRunner, MiniSweAgentHarness,
SwebenchVerifierRunner, DockerCliRuntime) with the FIXED identities —
no new framework.

Modes:
- default (no flags): OFFLINE PLAN ONLY. Everything is assembled and
  identity-verified (record hash, catalog hash, budget sanity, venv
  interpreters, bundled mini config) and a SECRET-FREE plan is printed.
  Nothing runs: no containers, no subprocesses, no model requests, no
  verifier.
- --execute --i-approve-the-c-run (BOTH required): the real single
  attempt. The flags are a SOFTWARE GATE ONLY — they do not prove WHO
  typed them. The authorization act is the user's explicit approval on
  the recorded checklist (task brief §8); typing the flags is reserved
  to the user after that approval. A config file can never substitute
  for any of this (a catalog claiming execution_authorized: true is
  REJECTED). The catalog's SHA-256 is pinned in this file: any drift
  from the user-approved configuration identity is refused before
  assembly in BOTH modes. Budget fields are validated for type and
  finiteness (a NaN wall or a tampered request count cannot assemble).
  Credentials are read from PILOT_API_BASE / PILOT_API_KEY in the
  environment AT EXECUTION TIME, exist only in memory, and are injected
  into the mini child's process environment only. Before anything
  starts, the env vars must be present (fail fast — no partial start).

Interpreter: run under the gate-B evaluator venv (it carries the
swebench package used by the verifier's lazy imports AND pydantic):

    PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \\
        -m agent_workload_characterization.runners.c_entry            # plan

Per the task brief, budget values below are PROPOSALS pending user
approval; this entry enforces whatever the catalog carries and reports
it in the plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ---- FIXED identities (registered in the delivery doc §8.2) -----------

RECORD_PATH = (PROJECT_ROOT / "data/raw/public/swebench_verified/"
               "78f471bf655a3137b2e8a75af1501690ec009ec3/"
               "django__django-16485/record.json")
RECORD_SHA256 = ("762de270d1ce06ab23104a35322098178624865c886d7b0ddadf90"
                 "44d8fec46a")
TARGET_IMAGE = ("swebench/sweb.eval.arm64.django_1776_django-16485"
                "@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254"
                "e1de00040e6db3b7d2")
MINI_VENV_PY = (PROJECT_ROOT / ".venvs/mini-swe-agent-2.4.6-env01"
                / "bin/python")
EVAL_VENV_PY = (PROJECT_ROOT / ".venvs/swebench-eval-02e7a74"
                / "bin/python")
CATALOG_PATH = PROJECT_ROOT / "workload_catalog/coding_pilot.yaml"
# The REGISTERED catalog identity (task brief §8.2). The catalog carries
# the user-approved budget; any drift from this hash — a tampered request
# count, a NaN wall, or any other edit — refuses assembly in BOTH modes.
CATALOG_SHA256 = "aee38eaca781df014117c4af14ce6df4fce91e2808dde09b03271b1e94902f83"
COLLECTION = "RUN-01-C"

# credentials: NAMES only here; values come from the environment at
# execution time and are never persisted or printed
USER_API_BASE_ENV = "PILOT_API_BASE"
USER_API_KEY_ENV = "PILOT_API_KEY"
SDK_BASE_ENV = "OPENAI_API_BASE"   # what the mini child's litellm reads
SDK_KEY_ENV = "OPENAI_API_KEY"

MODEL_NAME = "openai/deepseek-v4-flash"
SOURCE_TYPE = "benchmark_real"


class CEntryError(RuntimeError):
    """Assembly/authorization failure (reported without secrets)."""


def _disp(p: Path) -> str:
    """Display helper: project-relative when possible, absolute else."""
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def _load_catalog() -> dict:
    """Load the REGISTERED catalog; verify its pinned identity.

    Two independent refusals: (a) content drift from CATALOG_SHA256 —
    the assembly must only ever run the configuration the user approved;
    (b) execution_authorized not exactly False — config files cannot
    grant execution, only the user's explicit flags can."""
    import hashlib
    import yaml
    raw = CATALOG_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if CATALOG_SHA256 and actual != CATALOG_SHA256:
        raise CEntryError(
            "catalog sha256 mismatch — the registered configuration "
            "identity changed; refusing to assemble (re-register before "
            "any further use; never bypass)")
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise CEntryError("catalog must be a mapping")
    if data.get("execution_authorized") is not False:
        raise CEntryError(
            "catalog execution_authorized must be false; config files "
            "cannot grant execution — only the user's explicit flags can")
    return data


def _require_finite_positive(value, field: str, *, integral: bool) -> float:
    """Budget sanity: type + finite + positive. NaN/inf/zero/negative or
    string-typed values refuse assembly (a NaN wall or a tampered count
    can never reach the runner)."""
    if isinstance(value, bool) or not isinstance(
            value, (int, float)):
        raise CEntryError(
            f"budget field {field!r} must be a "
            f"{'positive integer' if integral else 'positive finite number'}"
            f", got {type(value).__name__}")
    if integral and not isinstance(value, int):
        raise CEntryError(
            f"budget field {field!r} must be an int, got {value!r}")
    v = float(value)
    import math
    if not math.isfinite(v) or v <= 0:
        raise CEntryError(
            f"budget field {field!r} must be finite and positive, "
            f"got {value!r}")
    return v


def budget_limits_from_catalog(catalog: dict):
    from .coding_pilot import BudgetLimits
    b = (catalog.get("budget_proposal_gate_c") or {})
    required = ("model_requests", "steps", "output_tokens_per_request",
                "agent_wall_min", "verifier_wall_min", "total_wall_min",
                "new_artifacts_gib")
    missing = [k for k in required if k not in b]
    if missing:
        raise CEntryError(f"catalog budget missing fields: {missing}")
    for k in ("model_requests", "steps", "output_tokens_per_request",
              "new_artifacts_gib"):
        _require_finite_positive(b[k], k, integral=True)
    for k in ("agent_wall_min", "verifier_wall_min", "total_wall_min"):
        _require_finite_positive(b[k], k, integral=False)
    return BudgetLimits(
        max_model_requests=int(b["model_requests"]),
        max_steps=int(b["steps"]),
        max_output_tokens_per_request=int(b["output_tokens_per_request"]),
        agent_wall_s=float(b["agent_wall_min"]) * 60.0,
        verifier_wall_s=float(b["verifier_wall_min"]) * 60.0,
        total_wall_s=float(b["total_wall_min"]) * 60.0,
        max_new_artifact_bytes=int(b["new_artifacts_gib"]) * 2**30)


def container_limits_from_catalog(catalog: dict) -> dict:
    b = (catalog.get("budget_proposal_gate_c") or {})
    for k in ("agent_container_cpu", "verifier_container_cpu"):
        _require_finite_positive(b.get(k), k, integral=True)
    for k in ("agent_container_memory_gib", "verifier_container_memory_gib"):
        _require_finite_positive(b.get(k), k, integral=False)
    return {
        "agent_container_cpu": str(b["agent_container_cpu"]),
        "agent_container_mem": f"{b['agent_container_memory_gib']}g",
        "verifier_container_cpu": str(b["verifier_container_cpu"]),
        "verifier_container_mem": f"{b['verifier_container_memory_gib']}g",
    }


def _verify_identities() -> dict:
    """Identity checks that must pass in EVERY mode (plan and execute)."""
    checks = {}
    raw = RECORD_PATH.read_bytes()
    checks["record_sha256_match"] = (
        hashlib.sha256(raw).hexdigest() == RECORD_SHA256)
    if not checks["record_sha256_match"]:
        raise CEntryError("record sha256 mismatch — refusing to assemble")
    checks["mini_venv_python"] = MINI_VENV_PY.is_file()
    checks["eval_venv_python"] = EVAL_VENV_PY.is_file()
    for name, ok in checks.items():
        if name.endswith("_python") and not ok:
            raise CEntryError(f"missing venv interpreter: {name}")
    return checks


def load_fixed_record() -> dict:
    raw = RECORD_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECORD_SHA256:
        raise CEntryError("record sha256 mismatch")
    return json.loads(raw)


def build_c_runner(*, authorized: bool, credentials: dict | None = None,
                   clock=None):
    """Assemble the full C runner from the fixed identities.

    `authorized` flips ONLY the component execution switches; in plan
    mode everything is constructed with authorized=False and nothing
    runs. Returns (runner, identity) where identity is the secret-free
    assembly snapshot for the plan/approval material."""
    from .coding_pilot import (CodingPilotRunner, SwebenchVerifierRunner,
                               VerifierSpec)
    from .container_runtime import DockerCliRuntime
    from .mini_agent_adapter import AgentTask, MiniSweAgentHarness

    catalog = _load_catalog()
    limits = budget_limits_from_catalog(catalog)
    container_limits = container_limits_from_catalog(catalog)
    record = load_fixed_record()

    # mini config: bundled swebench templates + the fixed model; budget
    # fields are enforced by _effective_config at run time
    bundled = MiniSweAgentHarness.load_bundled_config(MINI_VENV_PY)
    mini_config = {
        "agent": dict(bundled.get("agent") or {}),
        "model": {"model_name": MODEL_NAME,
                  "model_kwargs": {
                      k: v for k, v in (bundled.get("model", {})
                                        .get("model_kwargs") or {}).items()
                      if k not in ("num_retries", "max_tokens")},
                  "cost_tracking": "ignore_errors"},
        "environment": dict(bundled.get("environment") or {}),
    }
    harness = MiniSweAgentHarness(
        MINI_VENV_PY, authorized=authorized,
        mini_config=mini_config, target_image_ref=TARGET_IMAGE)

    verifier = SwebenchVerifierRunner(authorized=authorized,
                                      model_name="mini-swe-agent-2.4.6")
    runtime = DockerCliRuntime(authorized=authorized)

    task = AgentTask(instance_id=record["instance_id"],
                     problem_statement=record["problem_statement"],
                     image=TARGET_IMAGE, source_type=SOURCE_TYPE)
    verifier_spec = VerifierSpec(
        instance_id=record["instance_id"], image=TARGET_IMAGE,
        eval_script_ref="record.json",
        log_parser=record["log_parser"],
        eval_type=record["eval_type"],
        record_locator=str(RECORD_PATH))

    runner = CodingPilotRunner(
        project_root=PROJECT_ROOT, collection=COLLECTION,
        harness=harness, verifier=verifier, runtime=runtime,
        clock=clock, limits=limits, task=task,
        verifier_spec=verifier_spec, image=TARGET_IMAGE,
        source_type=SOURCE_TYPE, credentials=credentials,
        **container_limits)

    identity = {
        "collection": COLLECTION,
        "task": {"instance_id": record["instance_id"],
                 "record_sha256": RECORD_SHA256,
                 "base_commit": record.get("base_commit")},
        "image": TARGET_IMAGE,
        "model": MODEL_NAME,
        "harness": "mini-SWE-agent 2.4.6 (subprocess via "
                   f"{_disp(MINI_VENV_PY)})",
        "verifier": ("SwebenchVerifierRunner (official chain, fixed "
                     f"02e7a74; runner interpreter {_disp(EVAL_VENV_PY)})"),
        "budget": limits.to_dict(),
        "container_limits": container_limits,
        "credentials_env": {
            "user_api_base_env": USER_API_BASE_ENV,
            "user_api_key_env": USER_API_KEY_ENV,
            "child_sdk_env": [SDK_BASE_ENV, SDK_KEY_ENV],
            "note": "values are read from the environment at execution "
                    "time, kept in memory only, and injected into the "
                    "mini child process environment; never persisted"},
        "known_gaps": [
            "host_agent_runtime scope (the host-side mini child process) "
            "is NOT instrumented this run: no per-process CPU/RSS reader "
            "is wired; the child's wall/timing comes from the status "
            "protocol",
            "io metric degraded (cgroup v1 blkio writeback attribution)",
            "container writable layers have NO quota on this host "
            "(--storage-opt unsupported); 5 GiB is the run_dir detection "
            "threshold only",
        ],
    }
    return runner, identity


# ---------------------------------------------------------------------------
# plan / execution
# ---------------------------------------------------------------------------

def build_plan() -> dict:
    checks = _verify_identities()
    _, identity = build_c_runner(authorized=False)
    return {
        "mode": "offline_plan",
        "entry": {"module": "agent_workload_characterization.runners.c_entry",
                  "interpreter": _disp(EVAL_VENV_PY),
                  "plan_command": (
                      "PYTHONPATH=src "
                      ".venvs/swebench-eval-02e7a74/bin/python -m "
                      "agent_workload_characterization.runners.c_entry"),
                  "execute_command": (
                      "PYTHONPATH=src "
                      ".venvs/swebench-eval-02e7a74/bin/python -m "
                      "agent_workload_characterization.runners.c_entry "
                      "--execute --i-approve-the-c-run"),
                  "note": "the execute command performs nothing until the "
                          "user types both flags AND the credential env "
                          "vars are present; config files cannot "
                          "authorize"},
        "identity_checks": checks,
        "assembly": identity,
        "authorization_state": {
            "g0_decision": "pending",
            "c_user_approval": "pending (budget values are proposals)",
            "c_executed": False,
        },
    }


def _credentials_from_env() -> dict:
    import os
    missing = [n for n in (USER_API_BASE_ENV, USER_API_KEY_ENV)
               if not os.environ.get(n)]
    if missing:
        raise CEntryError(
            f"missing credential env vars at execution time: {missing} "
            "(values are never read into any file; set them in the "
            "shell that runs the entry)")
    # map user-named vars onto the SDK env the mini child's litellm reads
    return {SDK_BASE_ENV: os.environ[USER_API_BASE_ENV],
            SDK_KEY_ENV: os.environ[USER_API_KEY_ENV]}


def execute_c() -> dict:
    """The real single attempt (both flags already verified by main)."""
    _verify_identities()
    credentials = _credentials_from_env()  # fail fast, before any start
    runner, identity = build_c_runner(authorized=True,
                                      credentials=credentials)
    outcome = runner.run()
    return {
        "mode": "executed",
        "run_id": outcome.run_id,
        "execution_status": outcome.execution_status,
        "evaluation_status": outcome.evaluation_status,
        "archive_status": outcome.archive_status,
        "resolved": outcome.resolved,
        "run_dir": outcome.run_dir,
        "budget_usage": outcome.budget_usage,
        "source_type": outcome.source_type,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="c_entry",
        description="RUN-01 gate C minimal execution entry "
                    "(offline plan by default)",
        allow_abbrev=False)
    parser.add_argument("--execute", action="store_true",
                        help="real single attempt (requires "
                             "--i-approve-the-c-run AND credential env)")
    parser.add_argument("--i-approve-the-c-run", action="store_true",
                        help="user authorization act; typed by the user, "
                             "never set by config")
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    if not args.i_approve_the_c_run:
        print("REFUSED: --execute requires --i-approve-the-c-run "
              "(user authorization; a config file cannot grant it)",
              file=sys.stderr)
        return 2
    result = execute_c()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
