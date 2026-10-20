#!/usr/bin/env python3
"""One fixed django__django-16485 measurement attempt via Volcano."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
from agent_workload_characterization.runners import c_entry
from agent_workload_characterization.runners.smoke_launcher import (
    DEFAULT_CONFIG, PROVIDER_NAME, MODEL_KEY, _strip_jsonc, load_credentials)

ROOT = c_entry.PROJECT_ROOT
COLLECTION = "CODING-MEASUREMENT-VOLCANO-01"
ENV_REL = Path("env/coding-measurement-volcano-01")
REPORT_REL = Path("reports/resource") / COLLECTION
RAW_REL = Path("data/raw/generated") / COLLECTION
FLAG = "--i-approve-the-coding-measurement-volcano-01"
ENTRY_REL = Path("scripts/coding_measurement_volcano_01_entry.py")
REQUEST_MODEL = "openai/deepseek-v4-flash"
EXPECTED_IMAGE_ID = "sha256:bba60201758effbb3e4795367d470e3d0e00427f0e2e86636801b9f93df0b664"
DOCKER_ENDPOINT = "unix:///var/run/docker.sock"


def _configured_route() -> dict:
    raw = DEFAULT_CONFIG.read_bytes()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        config = json.loads(_strip_jsonc(raw.decode("utf-8")))
    provider = config["provider"][PROVIDER_NAME]
    model = provider["models"][MODEL_KEY]
    options = provider["options"]
    if model.get("name", "").strip().lower() != "deepseek-v4-flash":
        raise ValueError("configured Volcano model entry changed")
    if options.get("apiKey") != "{env:VOLCANO_API_KEY}":
        raise ValueError("configured Volcano credential reference changed")
    base = options.get("baseURL")
    if not isinstance(base, str) or not base.startswith("https://"):
        raise ValueError("configured Volcano API address is not HTTPS")
    return {"provider": PROVIDER_NAME, "api_base": base,
            "request_model": REQUEST_MODEL, "credential_env": "VOLCANO_API_KEY",
            "config_source": str(DEFAULT_CONFIG)}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(path: Path, rel: Path | str) -> dict:
    data = path.read_bytes()
    return {"path": str(rel), "bytes": len(data), "sha256": _sha(data)}


def build_identity() -> dict:
    checks = c_entry._verify_identities()
    runner, base = c_entry.build_c_runner(
        authorized=False, collection=COLLECTION, model_name=REQUEST_MODEL,
        credentials_env=("PILOT_API_BASE", "PILOT_API_KEY"))
    del runner
    catalog = c_entry._load_catalog()
    route = _configured_route()
    code_paths = [ENTRY_REL, Path("src/agent_workload_characterization/runners/c_entry.py"),
        Path("src/agent_workload_characterization/runners/coding_pilot.py"),
        Path("src/agent_workload_characterization/runners/mini_agent_adapter.py"),
        Path("src/agent_workload_characterization/runners/container_runtime.py"),
        Path("src/agent_workload_characterization/runners/tool_event_env.py"),
        Path("src/agent_workload_characterization/collectors/host_process.py"),
        Path("src/agent_workload_characterization/collectors/resource_sampler.py"),
        Path("src/agent_workload_characterization/collectors/execution_measurement.py"),
        Path("src/agent_workload_characterization/runners/smoke_launcher.py"),
        Path("workload_catalog/coding_pilot.yaml"),
        Path("data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3/django__django-16485/record.json"),
        Path("docs/trace_contract.md"),
        Path(".venvs/mini-swe-agent-2.4.6-env01/bin/python"),
        Path(".venvs/swebench-eval-02e7a74/bin/python")]
    from agent_workload_characterization.collectors.execution_measurement import CONTRACT
    identity = {
        "schema": "coding-measurement-volcano-identity-v1",
        "collection": COLLECTION,
        "source_identity_checks": checks,
        "base_assembly": base,
        "route": route,
        "task_image": {"reference": c_entry.TARGET_IMAGE,
                       "expected_local_image_id": EXPECTED_IMAGE_ID,
                       "platform": "linux/arm64"},
        "budget": base["budget"],
        "container_limits": base["container_limits"],
        "attempt_retry": 0,
        "measurement_contract": CONTRACT,
        "code_and_inputs": [_record(ROOT / p, p) for p in code_paths],
        "paths": {"plan": str(ENV_REL / "plan-identity.json"),
                  "frozen": str(ENV_REL / "frozen-identity.json"),
                  "approval": str(REPORT_REL / "APPROVAL.json"),
                  "attempt_marker": str(REPORT_REL / "ATTEMPT_STARTED.json"),
                  "raw": str(RAW_REL / "<run_id>")},
        "approval_flag": FLAG,
        "docker_endpoint": DOCKER_ENDPOINT,
        "execute_command": ("PYTHONPATH=src LITELLM_LOCAL_MODEL_COST_MAP=True "
            ".venvs/swebench-eval-02e7a74/bin/python -B "
            "scripts/coding_measurement_volcano_01_entry.py --execute " + FLAG),
        "cost": {"actual_bill": "unknown", "hard_cap": None},
    }
    return identity


def identity_digest(identity: dict) -> str:
    return _sha(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode())


def plan_mode() -> dict:
    identity = build_identity()
    digest = identity_digest(identity)
    env_dir, report_dir, raw_dir = ROOT / ENV_REL, ROOT / REPORT_REL, ROOT / RAW_REL
    frozen_path, saved_path = env_dir / "frozen-identity.json", env_dir / "plan-identity.json"
    match = False
    if frozen_path.is_file() and saved_path.is_file():
        frozen, saved = json.loads(frozen_path.read_text()), json.loads(saved_path.read_text())
        match = (frozen.get("identity") == saved.get("identity") == identity
                 and frozen.get("identity_sha256") == saved.get("identity_sha256") == digest)
    attempts = sorted(p.name for p in raw_dir.iterdir()) if raw_dir.exists() else []
    records = sorted(p.name for p in report_dir.iterdir()
                     if p.name not in {"APPROVAL.json"}) if report_dir.exists() else []
    approval = "missing"
    path = report_dir / "APPROVAL.json"
    if path.is_file():
        try:
            a = json.loads(path.read_text())
            approval = "valid" if a.get("schema") == "coding-single-run-approval-v1" \
                and a.get("collection") == COLLECTION and a.get("user_approval") == "approved" \
                and a.get("identity_sha256") == digest and a.get("accept_unknown_cost_no_hard_cap") is True else "invalid_or_stale"
        except (OSError, ValueError, AttributeError):
            approval = "invalid_or_stale"
    clean = not attempts and not records
    return {"collection": COLLECTION, "identity": identity, "identity_sha256": digest,
            "identity_matches_frozen": match, "existing_attempts": attempts,
            "existing_namespace_records": records, "approval_status": approval,
            "ready_for_approval": match and clean,
            "ready_for_execution": match and clean and approval == "valid"}


def freeze() -> dict:
    plan = plan_mode()
    if plan["existing_attempts"] or plan["existing_namespace_records"]:
        raise ValueError("coding namespace occupied; freeze refused")
    env_dir = ROOT / ENV_REL
    destinations = [env_dir / "plan-identity.json", env_dir / "frozen-identity.json",
                    env_dir / "preparation-manifest.json"]
    if any(p.exists() for p in destinations):
        raise FileExistsError("preparation identity already exists; refusing overwrite")
    env_dir.mkdir(parents=True, exist_ok=True)
    record = {"schema": "coding-measurement-freeze-v1", "identity": plan["identity"],
              "identity_sha256": plan["identity_sha256"]}
    for p in destinations[:2]:
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema": "coding-measurement-preparation-manifest-v1",
                "identity_sha256": plan["identity_sha256"],
                "inputs": plan["identity"]["code_and_inputs"],
                "outputs": [_record(p, p.relative_to(ROOT)) for p in destinations[:2]],
                "execution_authorized": False}
    destinations[2].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return plan_mode()


def _actual_image() -> tuple[str, str]:
    env = dict(os.environ)
    env["DOCKER_HOST"] = DOCKER_ENDPOINT
    env.pop("DOCKER_CONTEXT", None)
    p = subprocess.run(["docker", "--host", DOCKER_ENDPOINT, "image", "inspect",
        c_entry.TARGET_IMAGE, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
        capture_output=True, text=True, timeout=30, env=env, check=True)
    ident, platform = p.stdout.strip().split()
    return ident, platform


def execute() -> int:
    plan = plan_mode()
    if not plan["identity_matches_frozen"] or plan["existing_attempts"] or plan["existing_namespace_records"]:
        raise ValueError("identity mismatch or existing attempt; execution refused")
    actual_id, platform = _actual_image()
    if (actual_id, platform) != (EXPECTED_IMAGE_ID, "linux/arm64"):
        raise ValueError("registered Coding image identity/platform mismatch")
    api_base, api_key = load_credentials()
    if api_base != plan["identity"]["route"]["api_base"]:
        raise ValueError("Volcano API address changed since freeze")
    report_dir = ROOT / REPORT_REL
    report_dir.mkdir(parents=True, exist_ok=True)
    approval_path = report_dir / "APPROVAL.json"
    approval = {"schema": "coding-single-run-approval-v1", "collection": COLLECTION,
        "identity_sha256": plan["identity_sha256"], "user_approval": "approved",
        "approval_source": "explicit user authorization in current request",
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "accept_unknown_cost_no_hard_cap": True,
        "scope": {"task": "django__django-16485", "attempts": 1,
                  "attempt_retry": 0, "budget": plan["identity"]["budget"],
                  "framework_retry_policy": "existing catalog policy; no added retry",
                  "cost": "unknown; no hard cap accepted"}}
    with approval_path.open("x") as f:
        json.dump(approval, f, ensure_ascii=False, indent=2); f.write("\n")
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-django16485-" + uuid.uuid4().hex[:6]
    marker = report_dir / "ATTEMPT_STARTED.json"
    with marker.open("x") as f:
        json.dump({"status": "started", "run_id": run_id,
                   "identity_sha256": plan["identity_sha256"],
                   "started_at_utc": datetime.now(timezone.utc).isoformat()}, f, indent=2)
        f.write("\n")
    credentials = {c_entry.SDK_BASE_ENV: api_base, c_entry.SDK_KEY_ENV: api_key}
    runner, _ = c_entry.build_c_runner(authorized=True, credentials=credentials,
        collection=COLLECTION, model_name=REQUEST_MODEL,
        credentials_env=("PILOT_API_BASE", "PILOT_API_KEY"))
    runner.execution_identity_sha256 = plan["identity_sha256"]
    try:
        outcome = runner.run(run_id=run_id)
        result = dataclasses.asdict(outcome)
        result["identity_sha256"] = plan["identity_sha256"]
    except Exception as exc:
        result = {"run_id": run_id, "identity_sha256": plan["identity_sha256"],
                  "execution_status": "infra_failure", "error_type": type(exc).__name__}
    marker_data = json.loads(marker.read_text())
    marker_data.update(status="finished", result={k: result.get(k) for k in
        ("execution_status", "evaluation_status", "archive_status", "resolved", "cleanup_status")})
    marker.write_text(json.dumps(marker_data, ensure_ascii=False, indent=2) + "\n")
    report_path = report_dir / "run-report.json"
    report = {"schema": "coding-measurement-volcano-run-report-v1", **result,
              "route": {k: v for k, v in plan["identity"]["route"].items()
                        if k != "config_source"},
              "image_inspect": {"id": actual_id, "platform": platform},
              "actual_bill": "unknown"}
    with report_path.open("x") as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write("\n")
    raw_dir = ROOT / RAW_REL / run_id
    inputs = [_record(p, p.relative_to(ROOT)) for p in
        (approval_path, marker, ROOT / ENV_REL / "plan-identity.json",
         ROOT / ENV_REL / "frozen-identity.json", raw_dir / "manifest.json") if p.is_file()]
    manifest_path = report_dir / "manifest.json"
    outputs = [_record(report_path, report_path.relative_to(ROOT)),
               _record(marker, marker.relative_to(ROOT))]
    with manifest_path.open("x") as f:
        json.dump({"schema": "coding-measurement-volcano-manifest-v1",
                   "identity_sha256": plan["identity_sha256"], "inputs": inputs,
                   "outputs": outputs}, f, ensure_ascii=False, indent=2); f.write("\n")
    return 0 if result.get("cleanup_status") == "ok" and result.get("archive_status") == "complete" else 7


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument(FLAG, action="store_true")
    args = parser.parse_args(argv)
    if args.execute:
        if not getattr(args, FLAG[2:].replace('-', '_')):
            print("REFUSED: collection-specific approval flag required", file=sys.stderr)
            return 2
        return execute()
    print(json.dumps(freeze() if args.freeze else plan_mode(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
