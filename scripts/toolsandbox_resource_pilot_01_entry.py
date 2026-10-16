#!/usr/bin/env python3
"""TOOLSANDBOX-RESOURCE-PILOT-01 entry.

Thin lifecycle wrapper for one official ToolSandbox scenario run:

- default plan mode: side-effect free (no credentials, no model client, no
  network, no approval/attempt/raw run); prints identity and readiness;
- --prepare-source: freeze a bytes-identical copy of the official reference
  tree (never modified) plus a venv freeze record;
- --freeze: write candidate plan/frozen identity (never an approval);
- --execute: gated by an explicit collection-specific approval flag; spawns
  the worker subprocess, samples its /proc counters, enforces the hard work
  deadline by killing the worker, and archives everything with hashes.

The worker runs the REAL official chain (roles, Scenario.play, permutation
execution, evaluator); this entry never touches model credentials itself.
"""
from __future__ import annotations

import argparse
from collections import namedtuple
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EntryProfile = namedtuple("EntryProfile", (
    "collection", "env_rel", "report_rel", "raw_rel", "approval_flag",
    "entry_script", "run_suffix", "source_copy_rel", "shared_entry_script",
    "scenario_names", "batch_schedule", "batch_budget"),
    defaults=(None, None, None, None))


PILOT_01_PROFILE = EntryProfile(
    collection="TOOLSANDBOX-RESOURCE-PILOT-01",
    env_rel=Path("env/toolsandbox-resource-pilot-01"),
    report_rel=Path("reports/resource/TOOLSANDBOX-RESOURCE-PILOT-01"),
    raw_rel=Path("data/raw/generated/TOOLSANDBOX-RESOURCE-PILOT-01"),
    approval_flag="--i-approve-the-toolsandbox-resource-pilot-01",
    entry_script="scripts/toolsandbox_resource_pilot_01_entry.py",
    run_suffix="tsbpilot01",
    source_copy_rel=Path("env/toolsandbox-resource-pilot-01/source"),
)
PILOT_02_PROFILE = EntryProfile(
    collection="TOOLSANDBOX-RESOURCE-PILOT-02",
    env_rel=Path("env/toolsandbox-resource-pilot-02"),
    report_rel=Path("reports/resource/TOOLSANDBOX-RESOURCE-PILOT-02"),
    raw_rel=Path("data/raw/generated/TOOLSANDBOX-RESOURCE-PILOT-02"),
    approval_flag="--i-approve-the-toolsandbox-resource-pilot-02",
    entry_script="scripts/toolsandbox_resource_pilot_02_entry.py",
    run_suffix="tsbpilot02",
    source_copy_rel=Path("env/toolsandbox-resource-pilot-01/source"),
    shared_entry_script="scripts/toolsandbox_resource_pilot_01_entry.py",
)
# Existing P01 tests and callers use these names; they remain fixed to P01.
COLLECTION = PILOT_01_PROFILE.collection
ENV_REL = PILOT_01_PROFILE.env_rel
REPORT_REL = PILOT_01_PROFILE.report_rel
RAW_REL = PILOT_01_PROFILE.raw_rel
FLAG = PILOT_01_PROFILE.approval_flag
VENV_PYTHON = ROOT / ".venvs/toolsandbox-pilot-01/bin/python"
SOURCE_ORIGIN = ROOT / "references/repos/ToolSandbox"
SOURCE_COMMIT = "165848b9a78cead7ca7fe7c89c688b58e6501219"
SCENARIO_NAME = "send_message_with_contact_content_cellular_off"
def command_for(profile: EntryProfile) -> str:
    return ("PYTHONPATH=src .venvs/toolsandbox-pilot-01/bin/python -B "
            + profile.entry_script + " --execute " + profile.approval_flag)

# Model route as registered in project_state.json (DocOps model_route entries
# and env/docops-arm64-word001/deepseek-official-smoke-20261010.json). The
# request alias is LiteLLM-specific; the raw openai client model string is the
# alias without the provider prefix. NOT verified with the raw client yet.
ROUTE = {
    "api_base": "https://api.deepseek.com/v1",
    "request_model_alias": "openai/deepseek-v4-flash",
    "request_model_raw_client": "deepseek-v4-flash",
    "request_model_note": "alias is not an immutable version pin; raw-client string is the alias without the provider prefix and is NOT yet verified against the API",
    "historically_observed_response_model": "deepseek-flash",
    "api_key_env": "DEEPSEEK_API_KEY",
    "api_key_handling": "value is never read, logged or hashed by this entry; the worker reads it only in the real-route branch at execute time",
    "real_api_compatibility_verified": False,
}

RETRY = {
    "sdk_max_retries": 0,
    "max_attempts_per_logical_call": 3,
    "retry_on": ["APIConnectionError", "RateLimitError", "InternalServerError"],
    "backoff_base_s": 1.0,
    "backoff_cap_s": 8.0,
    "counting": "logical calls are counted outside the retry loop, per role, before any transport attempt; every attempt inside the loop is counted as transport_attempt_count",
    "official_defaults_and_deviation": (
        "official OpenAIAPIAgent tenacity retries requests.exceptions.HTTPError only — the "
        "httpx-based openai SDK never raises it, so that layer is a no-op; official "
        "OpenAIAPIUser tenacity retries ANY exception; official defaults also stack the SDK's "
        "internal max_retries=2 under tenacity. The pilot replaces both with ONE explicit "
        "counted layer and sdk_max_retries=0, identical for both roles"),
}

BUDGETS = {
    "agent_logical_calls": 20,
    "user_logical_calls": 20,
    "play_s": 300.0,
    "evaluate_s": 60.0,
    "total_wall_s": 480.0,
    "cleanup_reserve_s": 120.0,
    "max_messages": 30,
    "max_messages_note": ("official Scenario.max_messages is a SANDBOX message-index threshold, "
                          "not a strict model-request or tool-call cap; one scheduling round may "
                          "append several messages. The official default 30 is kept and the actual "
                          "message increment is recorded"),
    "max_tokens": "not set (official model_inference omits it; provider default applies). No hard token guarantee is claimed; the budget is enforced by logical-call caps, the shared work deadline and the parent kill",
}

TOPOLOGY = {
    "worker_process": "one subprocess runs agent model client, user-simulator model client, in-process tool execution and the official evaluator",
    "scopes": "A agent/harness+model client, B user simulator, C tool execution, D evaluator, E prepare/cleanup all share the worker process; every resource window is a shared-scope window",
    "per_tool_attribution": "not supported and not claimed; batch windows are shared_scope_window; per-call execution durations stay unknown",
    "network_boundary": "model clients need egress to the route api_base; scenario tools and evaluator are offline (in-memory polars); the process is not network-disabled",
    "hard_deadline": "parent monitors persisted actual phase starts and kills the worker at min(phase_start + phase_budget, common_work_deadline); common work origin is before spawn, including imports/setup; total deadline retains cleanup/archive reserve",
}

KNOWN_NONDETERMINISM = {
    "initial_message_creation_timestamps": "base scenario builds MESSAGING rows with naive local datetime.now(); time-varying initial rows are persisted per run",
    "task_time_targets": {
        "add_reminder_content_and_week_delta_and_time": "instruction says tomorrow at 5PM; official target uses get_tomorrow_datetime() and local naive datetime.timestamp()",
        "modify_contact_with_message_recency_multiple_user_turn": "initial recency messages use local datetime.now(); saved per-run initial state and evaluation target are authoritative for that run",
    },
    "uuid_generation": "official deterministic_uuid uses uuid5 for defined initial records; actual generated IDs are retained in each run scenario_context",
}

# Minimal dependency subset actually imported by the pilot chain (verified by
# import in the pilot venv). NOT the full official environment.
PINNED_FROM_PYPROJECT = ["polars==0.20.31", "openai==1.17.0", "tenacity==8.4.1",
                         "requests==2.32.3", "networkx==3.2.1", "numpy==1.26.4",
                         "scipy==1.13.1", "rouge-score==0.1.2", "rapidfuzz==3.9.3",
                         "StrEnum==0.4.15", "decorator==5.1.1", "dill==0.3.8",
                         "typing_extensions==4.12.2", "geopy==2.4.1", "holidays==0.51",
                         "pint==0.23", "ccy==1.3.1", "phonenumbers==8.13.39",
                         "pydantic==2.7.4", "langchain-core==0.1.17",
                         "tqdm==4.66.4", "attrs==23.2.0"]
NOT_INSTALLED = ["anthropic", "vertexai", "langchain (full)", "transformers",
                 "sentencepiece", "tree-sitter", "tree-sitter-languages",
                 "huggingface_hub", "jsonschema", "pyyaml (pulled transitively only)"]


def file_record(path: Path, rel: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(rel), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def identity_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def tree_records(root: Path, base: Path) -> list[dict]:
    records = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            records.append(file_record(p, p.relative_to(base)))
    return records


def git_commit_and_clean(origin: Path) -> tuple[str, bool]:
    commit = subprocess.run(["git", "-C", str(origin), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    diff = subprocess.run(["git", "-C", str(origin), "diff", "--exit-code", "--quiet"])
    return commit, diff.returncode == 0


def prepare_source(root: Path = ROOT, *, profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    """Freeze a bytes-identical copy of the official reference tree."""
    env_dir = root / profile.env_rel
    dest = root / profile.source_copy_rel
    manifest_path = env_dir / "source-manifest.json"
    freeze_path = env_dir / "venv-freeze.txt"
    if manifest_path.exists() or freeze_path.exists() or (
            profile.shared_entry_script is None and dest.exists()):
        raise ValueError("source preparation already exists; never overwrite")
    env_dir.mkdir(parents=True, exist_ok=True)
    if profile.shared_entry_script is None:
        commit, clean = git_commit_and_clean(SOURCE_ORIGIN)
        if commit != SOURCE_COMMIT or not clean:
            raise ValueError(f"reference tree drift: commit={commit} clean={clean}")
        files = []
        for p in sorted(SOURCE_ORIGIN.rglob("*")):
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts \
                    and p.suffix != ".pyc":
                rel = p.relative_to(SOURCE_ORIGIN)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(p.read_bytes())
                files.append(file_record(p, rel))
        manifest = {"schema": "toolsandbox-pilot-source-manifest-v1",
                    "origin_path": "references/repos/ToolSandbox",
                    "origin_commit": commit, "file_count": len(files), "files": files}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    else:
        source_manifest = root / PILOT_01_PROFILE.env_rel / "source-manifest.json"
        frozen_source = root / profile.source_copy_rel
        if not source_manifest.is_file() or not frozen_source.is_dir():
            raise ValueError("PILOT-01 frozen official source is unavailable")
        manifest_path.write_bytes(source_manifest.read_bytes())
    freeze = subprocess.run([str(VENV_PYTHON), "-m", "pip", "freeze",
                             "--disable-pip-version-check"],
                            check=True, capture_output=True, text=True)
    freeze_path.write_text(freeze.stdout)
    saved_manifest = json.loads(manifest_path.read_text())
    return {"prepared": True, "origin_commit": saved_manifest["origin_commit"],
            "file_count": saved_manifest["file_count"],
            "source_dir": str(dest.relative_to(root)),
            "manifest": str(manifest_path.relative_to(root)),
            "venv_freeze": str(freeze_path.relative_to(root))}


FACTS_PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from tool_sandbox.scenarios import named_scenarios
from tool_sandbox.common.tool_discovery import ToolBackend
s = named_scenarios(ToolBackend.DEFAULT)[sys.argv[2]]
def role_value(value):
    value = getattr(value, "value", value)
    return str(value).lower().rsplit(".", 1)[-1]
rows = s.starting_context.get_database(
    __import__("tool_sandbox.common.execution_context", fromlist=["DatabaseNamespace"]).DatabaseNamespace.SANDBOX,
    drop_sandbox_message_index=False, get_all_history_snapshots=True).to_dicts()
# Lists are sorted for identity stability: the official tool-discovery order
# is not deterministic across processes; execution uses the official order.
print(json.dumps({
    "name": sys.argv[2],
    "task_messages": [{"sender": role_value(r.get("sender")),
                       "recipient": role_value(r.get("recipient")),
                       "content": r.get("content")}
                      for r in rows if isinstance(r.get("content"), str)],
    "max_messages_default": s.max_messages,
    "categories": sorted(str(c) for c in s.categories),
    "tool_allow_list": sorted(s.starting_context.tool_allow_list or []),
    "tool_deny_list": sorted(s.starting_context.tool_deny_list or []),
    "trace_tool": s.starting_context.trace_tool,
    "milestone_count": len(s.evaluation.milestone_matcher.milestones),
    "minefield_count": len(s.evaluation.minefield_matcher.milestones),
}))
"""


def scenario_facts(root: Path, scenario_name: str = SCENARIO_NAME, *,
                   profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    env_dir = root / profile.env_rel
    manifest_path = env_dir / "source-manifest.json"
    if not manifest_path.is_file():
        return {"status": "source_not_prepared"}
    source_dir = root / profile.source_copy_rel
    probe_env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"),
                 "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                 "HOME": os.environ.get("HOME", "")}
    out = subprocess.run([str(VENV_PYTHON), "-B", "-c", FACTS_PROBE, str(source_dir), scenario_name],
                         capture_output=True, text=True, env=probe_env, timeout=120)
    if out.returncode != 0:
        raise ValueError(f"scenario probe failed: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def code_files(root: Path, *, profile: EntryProfile = PILOT_01_PROFILE) -> list[dict]:
    # Code identity always refers to the real project tree, independent of a
    # temporary data root used by tests.
    paths = [ROOT / profile.entry_script]
    if profile.shared_entry_script is not None:
        paths.append(ROOT / profile.shared_entry_script)
    paths += [
             ROOT / "src/agent_workload_characterization/runners/toolsandbox_worker.py",
             ROOT / "src/agent_workload_characterization/runners/preparation.py",
             ROOT / "src/agent_workload_characterization/runners/__init__.py",
             ROOT / "src/agent_workload_characterization/collectors/__init__.py",
             ROOT / "src/agent_workload_characterization/collectors/semantic_recorder.py",
             ROOT / "src/agent_workload_characterization/collectors/host_process.py",
             ROOT / "src/agent_workload_characterization/collectors/execution_measurement.py",
             ROOT / "src/agent_workload_characterization/__init__.py",
             ROOT / "docs/trace_contract.md",
             VENV_PYTHON]
    return [file_record(p, p.relative_to(ROOT)) for p in paths]


def build_identity(root: Path = ROOT, *, budgets: dict | None = None,
                   profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    if budgets is not None and root.resolve() == ROOT.resolve():
        raise ValueError("shortened test budgets require a temporary project root")
    env_dir = root / profile.env_rel
    manifest_path = env_dir / "source-manifest.json"
    freeze_path = env_dir / "venv-freeze.txt"
    if not manifest_path.is_file() or not freeze_path.is_file():
        raise ValueError("source not prepared; run --prepare-source first (offline, local copy only)")
    version = subprocess.run([str(VENV_PYTHON), "--version"], capture_output=True,
                             text=True).stdout.strip()
    scenario_names = profile.scenario_names or (SCENARIO_NAME,)
    serialized_schedule = ([[name for name in round_tasks]
                           for round_tasks in profile.batch_schedule]
                          if profile.batch_schedule is not None else None)
    scenario_records = [scenario_facts(root, name, profile=profile)
                        for name in scenario_names]
    scenario_identity = ({**scenario_records[0], "official_baseline": True,
                          "deviations_from_public_hepm_runs": [
                              "no summarize_the_task harness tool (H-EPM injection; absent from official source)",
                              "no tool-graph suggestion",
                              "no scrambled/distraction variants (base scenario)",
                              "official instruction, initial state, tools and evaluator unchanged"]}
                         if len(scenario_records) == 1 else {
                             "tasks": scenario_records,
                             "official_baseline": True,
                             "fixed_round_robin_schedule": serialized_schedule,
                             "batch_budget": profile.batch_budget,
                             "deviations_from_public_hepm_runs": [
                                 "no summarize_the_task harness tool (H-EPM injection; absent from official source)",
                                 "no tool-graph suggestion",
                                 "no scrambled/distraction variants (base scenarios)",
                                 "official instructions, initial states, tools and evaluators unchanged"]})
    return {
        "schema": "toolsandbox-resource-pilot-identity-v1",
        "collection": profile.collection,
        "official_source": {
            "origin_path": "references/repos/ToolSandbox",
            "origin_commit": SOURCE_COMMIT,
            "frozen_copy": str(profile.source_copy_rel),
            "source_manifest": str(manifest_path.relative_to(root)),
            "source_manifest_sha256": file_record(manifest_path,
                                                  manifest_path.relative_to(root))["sha256"],
            "reference_tree_unchanged_required": True,
        },
        "scenario": scenario_identity,
        "interpreter": {"path": str(VENV_PYTHON.relative_to(ROOT)), "version": version},
        "dependencies": {
            "strategy": "minimal subset actually imported by the pilot chain",
            "pinned_from_pyproject": PINNED_FROM_PYPROJECT,
            "not_installed": NOT_INSTALLED,
            "freeze_file": str(freeze_path.relative_to(root)),
            "freeze_sha256": file_record(freeze_path, freeze_path.relative_to(root))["sha256"],
            "full_official_environment_claimed": False,
        },
        "code_and_runtime_files": code_files(root, profile=profile),
        "route": ROUTE,
        "retry": RETRY,
        "budgets": {**BUDGETS, **(budgets or {})},
        "batch": ({"run_count": sum(len(x) for x in profile.batch_schedule),
                   "rounds": serialized_schedule,
                   "total_wall_s": profile.batch_budget["total_wall_s"],
                   "cleanup_reserve_s": profile.batch_budget["cleanup_reserve_s"],
                   "failure_policy": profile.batch_budget["failure_policy"],
                   "attempt_retry": profile.batch_budget["attempt_retry"],
                   "max_logical_model_calls": profile.batch_budget["max_logical_model_calls"],
                   "logical_call_basis": profile.batch_budget["logical_call_basis"]}
                  if profile.batch_schedule is not None else None),
        "sampling": {"interval_s": 0.5,
                     "scope": "worker host process (pid + starttime pinned)",
                     "boundaries": "worker writes its own /proc boundary reads at phase edges"},
        "topology": TOPOLOGY,
        "known_nondeterminism": KNOWN_NONDETERMINISM,
        "paths": {"output_root": str(root),
                  "approval": str(profile.report_rel / "APPROVAL.json"),
                  "report": str(profile.report_rel / "run-report.json"),
                  "attempt_root": str(profile.raw_rel / "<run_id>"),
                  "env": str(profile.env_rel)},
        "approval_flag": profile.approval_flag,
        "execute_command": command_for(profile),
        "monetary": {"actual_bill": "unknown", "hard_cap": None,
                     "explicit_acceptance_required_for_execution": True},
    }


def namespace_state(root: Path, *, profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    raw_dir = root / profile.raw_rel
    report_dir = root / profile.report_rel
    attempts = sorted(p.name for p in raw_dir.iterdir()) if raw_dir.exists() else []
    reports = sorted(p.name for p in report_dir.iterdir()) if report_dir.exists() else []
    return {"attempts": attempts,
            "report_records": [n for n in reports if n != "APPROVAL.json"],
            "approval_present": (report_dir / "APPROVAL.json").is_file()}


def plan_mode(root: Path = ROOT, *, budgets: dict | None = None,
              profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    identity = build_identity(root, budgets=budgets, profile=profile)
    digest = identity_sha(identity)
    env_dir = root / profile.env_rel
    match = False
    if (env_dir / "frozen-identity.json").is_file() and (env_dir / "plan-identity.json").is_file():
        frozen = json.loads((env_dir / "frozen-identity.json").read_text())
        saved = json.loads((env_dir / "plan-identity.json").read_text())
        match = (frozen.get("identity") == saved.get("identity") == identity
                 and frozen.get("identity_sha256") == saved.get("identity_sha256") == digest)
    ns = namespace_state(root, profile=profile)
    approval_path = root / profile.report_rel / "APPROVAL.json"
    approval_status = "missing"
    if approval_path.exists():
        try:
            approval = json.loads(approval_path.read_text())
            approval_status = "valid" if (
                approval.get("schema") == "toolsandbox-pilot-approval-v1"
                and approval.get("collection") == profile.collection
                and approval.get("user_approval") == "approved"
                and approval.get("identity_sha256") == digest
                and approval.get("accept_unknown_cost_no_hard_cap") is True
                and "entry_invocation" not in approval) else "invalid_or_stale"
        except (OSError, ValueError, AttributeError):
            approval_status = "invalid_or_stale"
    clean = not ns["attempts"] and not ns["report_records"]
    return {"collection": profile.collection, "identity": identity, "identity_sha256": digest,
            "identity_matches_frozen": match,
            "existing_attempts": ns["attempts"],
            "existing_report_records": ns["report_records"],
            "approval_status": approval_status,
            "ready_for_approval": match and clean,
            "ready_for_execution": match and clean and approval_status == "valid",
            "real_api_compatibility_verified": False,
            "note": "candidate identity only; nothing approved or executed"}


def freeze(root: Path = ROOT, *, budgets: dict | None = None,
           profile: EntryProfile = PILOT_01_PROFILE) -> dict:
    plan = plan_mode(root, budgets=budgets, profile=profile)
    if plan["existing_attempts"] or plan["existing_report_records"]:
        raise ValueError("occupied execution namespace")
    env_dir = root / profile.env_rel
    destinations = [env_dir / n for n in ("plan-identity.json", "frozen-identity.json",
                                          "preparation-manifest.json")]
    if any(p.exists() for p in destinations):
        raise FileExistsError("preparation freeze already exists; never overwrite")
    record = {"schema": "toolsandbox-pilot-freeze-v1",
              "identity": plan["identity"], "identity_sha256": plan["identity_sha256"]}
    for path in destinations[:2]:
        with path.open("x") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    manifest = {"schema": "toolsandbox-pilot-preparation-manifest-v1",
                "identity_sha256": plan["identity_sha256"],
                "inputs": [*plan["identity"]["code_and_runtime_files"],
                           file_record(env_dir / "source-manifest.json",
                                       profile.env_rel / "source-manifest.json"),
                           file_record(env_dir / "venv-freeze.txt",
                                       profile.env_rel / "venv-freeze.txt")],
                "outputs": [file_record(p, p.relative_to(root)) for p in destinations[:2]],
                "input_root": str(ROOT), "output_root": str(root),
                "execution_authorized": False}
    with destinations[2].open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return plan_mode(root, budgets=budgets, profile=profile)


def verify_run_archive(run_dir: Path) -> tuple[bool, list[str]]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return False, ["missing manifest"]
    manifest = json.loads(manifest_path.read_text())
    errors = []
    listed = {e["path"] for e in manifest["files"]}
    actual = {str(p.relative_to(run_dir)) for p in run_dir.rglob("*")
              if p.is_file() and p.name != "manifest.json"}
    for rel in sorted(listed - actual):
        errors.append(f"listed_missing:{rel}")
    for rel in sorted(actual - listed):
        errors.append(f"unlisted_actual:{rel}")
    for entry in manifest["files"]:
        p = run_dir / entry["path"]
        if p.is_file():
            data = p.read_bytes()
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                errors.append(f"hash_mismatch:{entry['path']}")
    return not errors, errors


def wait_for_worker(proc, boundary_path: Path, budgets: dict, common_deadline_ns: int):
    """Parent-side hard stop; a blocked SDK/tool/evaluator cannot bypass this wait."""
    cursor = 0
    phases = []
    active = None
    while True:
        if boundary_path.is_file():
            with boundary_path.open() as stream:
                stream.seek(cursor)
                while True:
                    line = stream.readline()
                    if not line or not line.endswith("\n"):
                        break  # retain the position before a partially written record
                    cursor = stream.tell()
                    row = json.loads(line)
                    phases.append(row)
                    name = row["phase"]
                    if name in ("play_begin", "evaluate_begin"):
                        stage = name.removesuffix("_begin")
                        deadline = min(row["phase_start_ns"] + int(budgets[stage + "_s"] * 1e9),
                                       common_deadline_ns)
                        active = {"phase": stage, "phase_start_ns": row["phase_start_ns"],
                                  "deadline_ns": deadline,
                                  "kind": "common_work_deadline" if deadline == common_deadline_ns else stage + "_deadline"}
                    elif active is not None and name == active["phase"] + "_end":
                        active = None
        deadline_ns = active["deadline_ns"] if active else common_deadline_ns
        now_ns = time.monotonic_ns()
        if now_ns >= deadline_ns:
            timeout = {**(active or {"phase": None, "kind": "common_work_deadline"}),
                       "deadline_ns": deadline_ns, "observed_ns": now_ns}
            proc.kill()
            return proc.wait(), timeout, phases
        try:
            # Re-read newly persisted phase signals while waiting, not only after a call returns.
            return proc.wait(timeout=min(.02, (deadline_ns-now_ns)/1e9)), None, phases
        except subprocess.TimeoutExpired:
            continue


def _read_runtime_limit(path: Path):
    try:
        return path.read_text().strip()
    except OSError:
        return "unknown"


def runtime_environment_record(pid: int, starttime_ticks: int) -> dict:
    """Persist the small set of host limits needed to interpret worker samples."""
    affinity = None
    try:
        affinity = sorted(os.sched_getaffinity(pid))
    except (AttributeError, OSError):
        pass
    cgroup_path = None
    try:
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            hierarchy, controllers, path = line.split(":", 2)
            if hierarchy == "0" and not controllers:
                cgroup_path = path.lstrip("/")
                break
    except (OSError, ValueError):
        pass
    cg = Path("/sys/fs/cgroup") / (cgroup_path or "__unavailable__")
    return {
        "python_executable": str(VENV_PYTHON),
        "python_version": sys.version,
        "pid": pid,
        "starttime_ticks": starttime_ticks,
        "sc_clk_tck": os.sysconf("SC_CLK_TCK"),
        "sc_page_size": os.sysconf("SC_PAGE_SIZE"),
        "online_cpu_count": os.cpu_count(),
        "worker_cpu_affinity": affinity if affinity is not None else "unknown",
        "worker_affinity_cpu_count": len(affinity) if affinity is not None else None,
        "cgroup_v2_path": cgroup_path if cgroup_path is not None else "unknown",
        "cgroup_limits": {
            "cpu.max": _read_runtime_limit(cg / "cpu.max"),
            "cpuset.cpus.effective": _read_runtime_limit(cg / "cpuset.cpus.effective"),
            "memory.max": _read_runtime_limit(cg / "memory.max"),
        },
        "online_count_is_worker_available_count": False,
    }


def execute(root: Path, plan: dict, *, transport: dict | None = None,
            profile: EntryProfile = PILOT_01_PROFILE,
            scenario_name: str | None = None, run_id: str | None = None,
            run_metadata: dict | None = None, budgets_override: dict | None = None,
            batch_deadline_ns: int | None = None,
            batch_work_deadline_ns: int | None = None,
            report_path: Path | None = None,
            outer_manifest_path: Path | None = None) -> int:
    if not plan["ready_for_execution"]:
        raise ValueError("execution refused: identity/approval/namespace gate not satisfied")
    identity = plan["identity"]
    budgets = {**identity["budgets"], **(budgets_override or {})}
    scenario_name = scenario_name or (profile.scenario_names[0]
                                      if profile.scenario_names else SCENARIO_NAME)
    if transport is None:
        transport = {"kind": "openai_compatible",
                     "base_url": ROUTE["api_base"],
                     "model": ROUTE["request_model_raw_client"],
                     "api_key_env": ROUTE["api_key_env"]}
    run_id = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + profile.run_suffix)
    run_dir = root / profile.raw_rel / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "ATTEMPT_STARTED.json").write_text(json.dumps(
        {"run_id": run_id, "collection": profile.collection,
         "identity_sha256": plan["identity_sha256"],
         "scenario": scenario_name, "run_metadata": run_metadata,
         "started_at_utc": datetime.now(timezone.utc).isoformat()}, indent=1) + "\n")
    job = {
        "run_id": run_id, "run_dir": str(run_dir),
        "scenario_name": scenario_name,
        "run_metadata": run_metadata,
        "source_root": str(root / identity["official_source"]["frozen_copy"]),
        "source_manifest": str(root / identity["official_source"]["source_manifest"]),
        "transport": transport,
        "budgets": budgets, "retry": identity["retry"],
        "known_nondeterminism": KNOWN_NONDETERMINISM,
    }
    job_path = run_dir / "job.json"

    from agent_workload_characterization.collectors.host_process import (
        HostProcessReader, read_starttime)

    spawn_ns = time.monotonic_ns()
    work_deadline_s = (budgets["total_wall_s"] - budgets["cleanup_reserve_s"])
    common_deadline_ns = spawn_ns + int(work_deadline_s * 1e9)
    total_deadline_ns = spawn_ns + int(budgets["total_wall_s"] * 1e9)
    if batch_deadline_ns is not None:
        common_deadline_ns = min(common_deadline_ns, batch_work_deadline_ns or batch_deadline_ns)
        total_deadline_ns = min(total_deadline_ns, batch_deadline_ns)
    effective_work_deadline_s = (common_deadline_ns - spawn_ns) / 1e9
    job.update(parent_start_ns=spawn_ns, common_work_deadline_ns=common_deadline_ns,
               total_deadline_ns=total_deadline_ns)
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=1) + "\n")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"),
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "HOME": os.environ.get("HOME", "")}
    if transport["kind"] == "openai_compatible":
        # No credential access at all for an offline fake execution.
        env[ROUTE["api_key_env"]] = os.environ.get(ROUTE["api_key_env"], "")
    stdout_f = open(run_dir / "worker.stdout", "w")
    stderr_f = open(run_dir / "worker.stderr", "w")
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-B", "-m", "agent_workload_characterization.runners.toolsandbox_worker",
         str(job_path)], cwd=str(ROOT), env=env, stdout=stdout_f, stderr=stderr_f)
    starttime = read_starttime(proc.pid)
    environment_path = run_dir / "environment.json"
    environment_path.write_text(json.dumps(runtime_environment_record(proc.pid, starttime),
                                           ensure_ascii=False, indent=1) + "\n")
    reader = HostProcessReader(proc.pid, expected_starttime=starttime)
    samples_path = run_dir / "samples.jsonl"
    stop = threading.Event()
    sample_rows = []

    def sampler():
        next_t = time.monotonic()
        while not stop.is_set():
            snap = reader.read()
            row = {"t_monotonic_ns": snap.t_monotonic_ns, "pid": snap.pid,
                   "starttime_ticks": snap.starttime_ticks, "cpu_ticks": snap.cpu_ticks,
                   "user_ticks": snap.user_ticks, "system_ticks": snap.system_ticks,
                   "rss_bytes": snap.rss_bytes, "threads": snap.threads,
                   "process_io": snap.process_io,
                   "context_switches": snap.context_switches,
                   "read_status": snap.read_status}
            sample_rows.append(row)
            with samples_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            next_t += 0.5
            delay = next_t - time.monotonic()
            if delay > 0:
                stop.wait(delay)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    killed = False
    rc = None
    try:
        rc, timeout, phase_signals = wait_for_worker(
            proc, run_dir / "boundaries.jsonl", budgets, common_deadline_ns)
        killed = timeout is not None
    finally:
        stop.set()
        thread.join(timeout=5)
        stdout_f.close()
        stderr_f.close()
    end_ns = time.monotonic_ns()
    remaining_starttime = read_starttime(proc.pid)
    cleanup = {"pid": proc.pid, "starttime_ticks": starttime, "returncode": proc.returncode,
               "wait_reaped": proc.returncode is not None,
               "original_process_gone": remaining_starttime is None or remaining_starttime != starttime,
               "sampler_stopped": not thread.is_alive(), "checked_monotonic_ns": end_ns}

    worker_result = None
    result_path = run_dir / "result.json"
    if result_path.is_file():
        worker_result = json.loads(result_path.read_text())
    gaps = [b - a for a, b in zip([r["t_monotonic_ns"] for r in sample_rows],
                                  [r["t_monotonic_ns"] for r in sample_rows][1:])]
    regressions = sum(1 for a, b in zip(sample_rows, sample_rows[1:])
                      if a["cpu_ticks"] is not None and b["cpu_ticks"] is not None
                      and b["cpu_ticks"] < a["cpu_ticks"])
    exit_code = 4 if killed else (rc if rc is not None else 5)
    boundary_path = run_dir / "boundaries.jsonl"
    boundary_text = boundary_path.read_text() if boundary_path.is_file() else ""
    phases = [json.loads(line) for line in boundary_text.splitlines(keepends=True) if line.endswith("\n")]
    evaluation = worker_result.get("evaluation") if worker_result else None
    from agent_workload_characterization.collectors.execution_measurement import span_coverage
    events_path = run_dir / "events.jsonl"
    coverage = span_coverage(events_path)
    event_rows = ([json.loads(line) for line in events_path.read_text().splitlines(keepends=True)
                   if line.endswith("\n")] if events_path.is_file() else [])
    terminal_ids = {e["event_id"] for e in event_rows if e.get("status") in ("closed", "error", "unclosed")}
    censored_ids = [e["event_id"] for e in event_rows if e.get("status") == "open"
                    and e["event_id"] not in terminal_ids]
    report = {
        "schema": "toolsandbox-pilot-run-report-v1",
        "collection": profile.collection, "run_id": run_id,
        "identity_sha256": plan["identity_sha256"], "scenario": scenario_name,
        "run_metadata": run_metadata,
        "worker_exit_code": rc, "killed_by_deadline": killed,
        "exit_code": exit_code,
        "wall_s": (end_ns - spawn_ns) / 1e9,
        "work_deadline_s": effective_work_deadline_s,
        "parent_start_ns": spawn_ns, "common_work_deadline_ns": common_deadline_ns,
        "total_deadline_ns": total_deadline_ns, "deadline_timeout": timeout,
        "cleanup": cleanup,
        "evaluation": evaluation,
        "evaluation_status": "completed" if evaluation is not None else (
            "incomplete" if any(p["phase"] == "evaluate_begin" for p in phases) else "not_started"),
        "boundary_incomplete_tail": bool(boundary_text and not boundary_text.endswith("\n")),
        "measurement": {"span_coverage": coverage, "right_censored_event_ids": censored_ids,
                        "worker_completion": "partial" if worker_result is None else "reported",
                        "note": "no synthetic terminal rows are appended after a deadline kill"},
        "budget_phase_report": {
            "play_s_budget": budgets["play_s"], "evaluate_s_budget": budgets["evaluate_s"],
            "phases": phases, "parent_observed_phase_signals": phase_signals,
            "note": "actual play/evaluate start signals are persisted before blocking; parent kills at the earlier phase/common deadline; imports/setup consume common work budget"},
        "host_sampling": {"rows": len(sample_rows), "interval_target_s": 0.5,
                          "max_gap_ns": max(gaps, default=None),
                          "nonpositive_gaps": sum(1 for g in gaps if g <= 0),
                          "cpu_counter_regressions": regressions,
                          "scope": "worker process pid+starttime; shared scope, not per-tool"},
        "worker_result": worker_result,
        "archive_verification": None,
        "actual_bill": "unknown",
    }
    marker = {"run_id": run_id, "identity_sha256": plan["identity_sha256"],
              "exit_code": exit_code, "worker_exit_code": rc, "deadline_timeout": timeout,
              "cleanup": cleanup, "worker_window_wall_s": report["wall_s"],
              "meaning": "attempt lifecycle finished; not a task-success label"}
    (run_dir / "ATTEMPT_COMPLETED.json").write_text(json.dumps(marker, indent=1) + "\n")
    manifest = {"schema": "toolsandbox-pilot-run-manifest-v1",
                "identity_sha256": plan["identity_sha256"], "run_id": run_id,
                "files": [file_record(p, p.relative_to(run_dir)) for p in sorted(run_dir.rglob("*"))
                          if p.is_file() and p.name != "manifest.json"]}
    with (run_dir / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    valid, errors = verify_run_archive(run_dir)
    report["archive_verification"] = {"valid": valid, "errors": errors}
    if not valid:
        exit_code = exit_code or 7
    report["exit_code"] = exit_code
    report["worker_window_wall_s"] = report["wall_s"]
    report["wall_s"] = (time.monotonic_ns() - spawn_ns) / 1e9
    report["within_total_budget"] = time.monotonic_ns() <= total_deadline_ns
    report["wall_scope"] = "parent start through cleanup and raw archive verification; final report/outer-manifest writes follow this snapshot"
    report["remaining_cleanup_archive_s"] = max(0, (total_deadline_ns-end_ns)/1e9)
    report_path = report_path or (root / profile.report_rel / "run-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    outer_manifest = {"identity_sha256": plan["identity_sha256"], "run_id": run_id,
                      "inputs": [file_record(root / p, p) for p in
                                 (profile.report_rel / "APPROVAL.json",
                                  profile.env_rel / "plan-identity.json",
                                  profile.env_rel / "frozen-identity.json",
                                  profile.raw_rel / run_id / "manifest.json")],
                      "outputs": [file_record(report_path, report_path.relative_to(root))]}
    outer_manifest_path = outer_manifest_path or (root / profile.report_rel / "manifest.json")
    outer_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with outer_manifest_path.open("x") as stream:
        json.dump(outer_manifest, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    return exit_code


def main(argv=None, *, root: Path = ROOT,
         profile: EntryProfile = PILOT_01_PROFILE) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-source", action="store_true",
                       help="freeze the official source copy and venv record; never overwrites")
    modes.add_argument("--freeze", action="store_true",
                       help="write candidate plan/frozen identity; never overwrites, never approves")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument(profile.approval_flag, action="store_true", dest="approved")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not args.approved:
                raise ValueError("explicit collection-specific approval flag required")
            return execute(root, plan_mode(root, profile=profile), profile=profile)
        if args.prepare_source:
            print(json.dumps(prepare_source(root, profile=profile), ensure_ascii=False, indent=2))
            return 0
        plan = freeze(root, profile=profile) if args.freeze else plan_mode(root, profile=profile)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, FileExistsError, subprocess.CalledProcessError) as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
