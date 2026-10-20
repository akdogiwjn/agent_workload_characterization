#!/usr/bin/env python3
"""Continue the fixed 27-slot study in a new namespace, reusing each chain."""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
COLLECTION = "LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01"
ENV = Path("env/local-three-class-repeat-01-continuation-01")
REPORT = Path("reports/resource") / COLLECTION
RAW = Path("data/raw/generated") / COLLECTION
ENTRY = Path("scripts/local_three_class_repeat_01_continuation_01_entry.py")
FLAG = "--i-approve-the-local-three-class-repeat-01-continuation-01"
ENDPOINT = "unix:///var/run/docker.sock"
PYTHONS = {
    "Coding": ".venvs/swebench-eval-02e7a74/bin/python",
    "Office": ".venvs/docops-pilot-01/bin/python",
    "Assistant": ".venvs/toolsandbox-pilot-01/bin/python",
}
TASKS = {
    "Coding": ("django__django-16485", "astropy__astropy-13236", "astropy__astropy-13398"),
    "Office": ("atomic__excel_001_budget_bucket_totals_seed",
               "atomic__ppt_008_bullet_editing_seed", "atomic__pdf_004_audit_pages_reorder_seed"),
    "Assistant": ("send_message_with_contact_content_cellular_off",
                  "add_reminder_content_and_week_delta_and_time",
                  "modify_contact_with_message_recency_multiple_user_turn"),
}
CAPS = {"Coding": 1800, "Office": 2700, "Assistant": 480}
BATCH_WALL_S = 14 * 3600
BATCH_CLOSEOUT_S = 300
OLD_COLLECTION = "LOCAL-THREE-CLASS-REPEAT-01"
OLD_RUN_ID = "20261016T182559Z-09-r0-office"
OLD_IDENTITY = "460c9c28e4799d864ff2aa3a2bf7cf2e272fa095eabb917f4bec4f1b45893b22"
IMAGE_PINS = {
    "django__django-16485": {
        "reference": "swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2",
        "config_id": "sha256:bba60201758effbb3e4795367d470e3d0e00427f0e2e86636801b9f93df0b664"},
    "astropy__astropy-13236": {
        "reference": "swebench/sweb.eval.arm64.astropy_1776_astropy-13236@sha256:e7512a4ee3451cdd949098a496fb68f8488a4970ef00ab3d96ed40a5fb1a2011",
        "config_id": "sha256:55adab20ce3beba93ae8e85a09cd184662f154bd091dc7e8e195dbcbff45afac"},
    "astropy__astropy-13398": {
        "reference": "swebench/sweb.eval.arm64.astropy_1776_astropy-13398@sha256:4475e9bab862169dc0622cc9686f6a6e53232dc7beba244b525ec2af4fef6a4a",
        "config_id": "sha256:16b4fee7c64b3a0c501c2e25402197cd8aeb870b33d49a6e034ddc3c2eb79a3c"},
}


@dataclass(frozen=True)
class BatchProfile:
    key: str
    collection: str
    env: Path
    report: Path
    raw: Path
    entry: Path
    approval_flag: str
    run_suffix: str
    batch_wall_s: int
    closeout_reserve_s: int


CONTINUATION_PROFILE = BatchProfile(
    "continuation01", COLLECTION, ENV, REPORT, RAW, ENTRY, FLAG,
    "localthreechaincont01", BATCH_WALL_S, BATCH_CLOSEOUT_S)
COMPLETE_02_PROFILE = BatchProfile(
    "complete02", "LOCAL-THREE-CLASS-COMPLETE-02",
    Path("env/local-three-class-complete-02"),
    Path("reports/resource/LOCAL-THREE-CLASS-COMPLETE-02"),
    Path("data/raw/generated/LOCAL-THREE-CLASS-COMPLETE-02"),
    Path("scripts/local_three_class_repeat_01_continuation_01_entry.py"),
    "--i-approve-the-local-three-class-complete-02",
    "localthreeclasscomplete02", 9 * 3600, 600)
PROFILES = {p.key: p for p in (CONTINUATION_PROFILE, COMPLETE_02_PROFILE)}
COMPLETE_02_SLOTS = (
    ("Coding", 1, "django__django-16485"),
    ("Coding", 2, "astropy__astropy-13398"),
    ("Coding", 2, "django__django-16485"),
    ("Coding", 2, "astropy__astropy-13236"),
    ("Office", 0, "atomic__ppt_008_bullet_editing_seed"),
    ("Office", 0, "atomic__pdf_004_audit_pages_reorder_seed"),
    ("Office", 1, "atomic__ppt_008_bullet_editing_seed"),
    ("Office", 1, "atomic__pdf_004_audit_pages_reorder_seed"),
    ("Office", 1, "atomic__excel_001_budget_bucket_totals_seed"),
    ("Office", 2, "atomic__pdf_004_audit_pages_reorder_seed"),
    ("Office", 2, "atomic__excel_001_budget_bucket_totals_seed"),
    ("Office", 2, "atomic__ppt_008_bullet_editing_seed"),
)
PULL_OBSERVATIONS = {
    "astropy__astropy-13236": {
        "command": "docker --host unix:///var/run/docker.sock pull " + IMAGE_PINS["astropy__astropy-13236"]["reference"],
        "returncode": 0,
        "terminal_excerpt": "Digest: sha256:e7512a4ee3451cdd949098a496fb68f8488a4970ef00ab3d96ed40a5fb1a2011\nStatus: Downloaded newer image",
        "excerpt_only": True, "duration_s": None},
    "astropy__astropy-13398": {
        "command": "docker --host unix:///var/run/docker.sock pull " + IMAGE_PINS["astropy__astropy-13398"]["reference"],
        "returncode": 0,
        "terminal_excerpt": "Digest: sha256:4475e9bab862169dc0622cc9686f6a6e53232dc7beba244b525ec2af4fef6a4a\nStatus: Downloaded newer image",
        "excerpt_only": True, "duration_s": None,
        "interrupted_prior_invocation": "interrupted; subsequent inspect still found absent; this invocation completed"},
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(obj) -> str:
    return sha_bytes(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")).encode())


def file_record(path: Path | str, root: Path = ROOT) -> dict:
    path = Path(path)
    full = path if path.is_absolute() else root / path
    data = full.read_bytes()
    try:
        relative = full.relative_to(root).as_posix()
    except ValueError:
        relative = str(full)
    return {"path": relative, "bytes": len(data), "sha256": sha_bytes(data)}


def write_new(path: Path | str, value, root: Path = ROOT) -> None:
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    with full.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def read_json(path: Path | str, root: Path = ROOT):
    return json.loads((root / path).read_text(encoding="utf-8"))


def planned_schedule(profile: BatchProfile = CONTINUATION_PROFILE) -> list[dict]:
    if profile.key == "complete02":
        prior = json.loads((ROOT / "reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/summary.json").read_text())
        prior_slots = prior["slot_census_27"]
        rows = []
        for sequence, (chain, round_index, task) in enumerate(COMPLETE_02_SLOTS):
            candidates = [x for x in prior_slots if x.get("chain") == chain
                          and x.get("round") == round_index and x.get("task") == task]
            if chain == "Coding":
                matches = [x for x in candidates if x.get("slot_status") == "not_executed"]
                if len(matches) != 1:
                    raise ValueError(f"replacement Coding slot is not uniquely unexecuted: {task}/r{round_index}")
                row = {"replaces_original_sequence": matches[0]["original_sequence"]}
            else:
                refs = [x for x in prior["run_references"] if x.get("chain") == chain
                        and x.get("round") == round_index and x.get("task") == task
                        and x.get("profile_stratum") == "continuation_Office_route_mismatch"]
                if len(refs) != 1:
                    raise ValueError(f"replacement Office attempt is not unique: {task}/r{round_index}")
                row = {"replaces_run_id": refs[0]["run_id"],
                       "replaces_collection": refs[0]["collection"]}
            rows.append({"sequence": sequence, "chain": chain,
                         "round": round_index, "task": task, **row})
        if len(rows) != 12 or len({(x["chain"], x["round"], x["task"]) for x in rows}) != 12:
            raise AssertionError("complete02 schedule must contain twelve unique fixed slots")
        return rows
    rows = []
    original_sequence = 0
    continuation_sequence = 0
    for chain, tasks in TASKS.items():
        for round_index in range(3):
            order = (round_index % 3, (round_index + 1) % 3, (round_index + 2) % 3)
            for task_index in order:
                slot = {"sequence": continuation_sequence,
                        "original_sequence": original_sequence,
                        "chain": chain, "round": round_index,
                        "task": tasks[task_index]}
                if not (chain == "Office" and round_index == 0 and task_index == 0):
                    rows.append(slot)
                    continuation_sequence += 1
                original_sequence += 1
    return rows


def assistant_profile(profile: BatchProfile = CONTINUATION_PROFILE):
    import toolsandbox_resource_pilot_01_entry as ts
    return ts.VOLCANO_PROFILE._replace(
        collection=profile.collection, env_rel=profile.env, report_rel=profile.report, raw_rel=profile.raw,
        approval_flag=profile.approval_flag, entry_script=str(profile.entry), run_suffix=profile.run_suffix,
        source_copy_rel=Path("env/toolsandbox-resource-pilot-01/source"),
        shared_entry_script="scripts/toolsandbox_resource_pilot_01_entry.py",
        scenario_names=TASKS["Assistant"], batch_schedule=None, batch_budget=None)


def _record_set(paths: list[Path | str]) -> list[dict]:
    unique = {file_record(p)["path"]: file_record(p) for p in paths}
    return [unique[k] for k in sorted(unique)]


def _coding_component(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    """Assemble the existing per-task CodingPilotRunner for all fixed tasks."""
    from agent_workload_characterization.runners import p1_12_entry as p1
    from agent_workload_characterization.runners.mini_agent_adapter import MiniSweAgentHarness
    from agent_workload_characterization.runners.coding_pilot import SwebenchVerifierRunner
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    import coding_measurement_volcano_01_entry as coding

    cfg = p1.load_config()
    route = coding._configured_route()
    if route["request_model"] != "openai/deepseek-v4-flash":
        raise ValueError("Coding model route mismatch")
    bundled = MiniSweAgentHarness.load_bundled_config(p1.MINI_VENV_PY)
    model_cfg = bundled.get("model") or {}
    mini_config = {"agent": dict(bundled.get("agent") or {}),
                   "model": {"model_name": "openai/deepseek-v4-flash",
                             "model_kwargs": {k: v for k, v in
                                 (model_cfg.get("model_kwargs") or {}).items()
                                 if k not in ("num_retries", "max_tokens")}},
                   "environment": dict(bundled.get("environment") or {})}
    task_rows = []
    for task_name in TASKS["Coding"]:
        task = next(x for x in cfg["tasks"] if x["instance_id"] == task_name)
        record = file_record(task["record_locator"])
        pin = IMAGE_PINS[task_name]
        if task["image_arm64_digest"] != pin["reference"]:
            raise ValueError("Coding task image reference drift: " + task_name)
        runtime = DockerCliRuntime(authorized=False, collection=profile.collection)
        harness = MiniSweAgentHarness(p1.MINI_VENV_PY, authorized=False,
            mini_config=mini_config, target_image_ref=pin["reference"])
        verifier = SwebenchVerifierRunner(authorized=False,
                                         model_name="mini-SWE-agent-2.4.6")
        runner = p1.build_task_runner(cfg, task_name, authorized=False,
            runtime=runtime, harness=harness, verifier=verifier,
            project_root=ROOT, limits=p1._attempt_limits(cfg), collection=profile.collection)
        if (runner.task.instance_id != task_name or runner.image != pin["reference"]
                or runner.limits.max_model_requests != 30
                or runner.limits.max_steps != 30
                or runner.limits.max_output_tokens_per_request != 4096):
            raise ValueError("Coding production runner assembly mismatch: " + task_name)
        task_rows.append({"task": task_name, "record": record, "image": pin,
            "limits": runner.limits.to_dict(),
            "container_limits": {"agent_cpu": runner.agent_container_cpu,
                "agent_memory": runner.agent_container_mem,
                "verifier_cpu": runner.verifier_container_cpu,
                "verifier_memory": runner.verifier_container_mem}})

    code = [Path("src/agent_workload_characterization/runners/p1_12_entry.py"),
        Path("src/agent_workload_characterization/runners/coding_pilot.py"),
        Path("src/agent_workload_characterization/runners/mini_agent_adapter.py"),
        Path("src/agent_workload_characterization/runners/container_runtime.py"),
        Path("src/agent_workload_characterization/runners/tool_event_env.py"),
        Path("src/agent_workload_characterization/runners/smoke_launcher.py"),
        Path("src/agent_workload_characterization/collectors/execution_measurement.py"),
        Path("src/agent_workload_characterization/collectors/resource_sampler.py"),
        Path("src/agent_workload_characterization/collectors/host_process.py"),
        Path("src/agent_workload_characterization/collectors/semantic_recorder.py"),
        Path("workload_catalog/p1_12_deepseek_official.yaml"),
        Path("workload_catalog/p1_12.yaml"),
        Path("scripts/coding_measurement_volcano_01_entry.py"), profile.entry,
        Path(".venvs/mini-swe-agent-2.4.6-env01/bin/python"),
        Path(".venvs/swebench-eval-02e7a74/bin/python")]
    return {"schema": "existing_coding_pilot_per_task_runner",
            "route": route, "model_config": mini_config,
            "attempt_retry": 0, "tasks": task_rows,
            "code_and_runtime_files": _record_set(code),
            "budget": {"max_model_requests": 30, "max_steps": 30,
                "max_output_tokens_per_request": 4096,
                "agent_wall_s": 1500, "verifier_wall_s": 300,
                "total_wall_s": 1800, "agent_cpu": 4, "verifier_cpu": 4,
                "agent_memory_gib": 8, "verifier_memory_gib": 8}}


def validate_office_route(config: dict, expected: dict) -> None:
    """Fail closed before any model client is constructed; never log credentials."""
    route = config.get("model_route")
    keys = ("api_base", "request_model", "credential_env")
    if (not isinstance(route, dict)
            or any(not isinstance(expected.get(k), str) or not expected[k] for k in keys)
            or any(route.get(k) != expected[k] for k in keys)
            or not expected["api_base"].startswith("https://")):
        raise ValueError("Office per-run model_route missing or differs from frozen route")


def office_config_with_route(office, task: dict, round_index: int, route: dict,
                             profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    config = office.run_config(task["key"], round_index, task["image_ref"],
                              task["image_id"], collection=profile.collection)
    config["model_route"] = {k: route[k] for k in
                             ("api_base", "request_model", "credential_env")}
    validate_office_route(config, route)
    return config


def _office_component(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    import docops_office_repeat_01_entry as office
    import docops_measurement_validate_01_entry as single
    frozen = read_json("env/docops-office-repeat-01/frozen-identity.json")
    if office.identity_sha(frozen["identity"]) != frozen["identity_sha256"]:
        raise ValueError("historical Office identity digest mismatch")
    ids = {x["key"]: x["image_id"] for x in frozen["identity"]["tasks"]}
    base = office.build_identity(ids)
    route = single.configured_route(single.VOLCANO_02_PROFILE)
    task_configs = {}
    for task in base["tasks"]:
        task_configs[task["key"]] = [
            office_config_with_route(office, task, rnd, route, profile)
            for rnd in range(3)]
    measurement_identity = single.build_identity(profile=single.VOLCANO_02_PROFILE)
    code = {x["path"]: x for x in [*base["code_and_runtime_files"],
                                     *measurement_identity["code_and_runtime_files"]]}
    code[profile.entry.as_posix()] = file_record(profile.entry)
    return {"schema": "existing_docops_shared_run_attempt",
        "historical_identity_sha256": frozen["identity_sha256"],
        "docops_commit": base["docops_commit"],
        "base_image": base["base_image"], "tasks": base["tasks"],
        "run_configs_by_task_round": task_configs,
        "tools": base["tools"], "model": {**base["model"], **route, "route": route},
        "measurement_contract": measurement_identity.get("measurement_contract"),
        "code_and_runtime_files": [code[k] for k in sorted(code)],
        "budget": base["budget"]}


def _assistant_component(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    import toolsandbox_resource_pilot_01_entry as ts
    return ts.build_identity(ROOT, profile=assistant_profile(profile))


def component(chain: str, profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    return {"Coding": _coding_component,
            "Office": _office_component,
            "Assistant": _assistant_component}[chain](profile)


def _component_process(chain: str, profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    env = dict(os.environ)
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    env["PYTHONPATH"] = "src:scripts"
    result = subprocess.run([str(ROOT / PYTHONS[chain]), "-B", str(ROOT / profile.entry),
                             "--profile", profile.key, "--component", chain], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=240)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1][:240] if result.stderr.strip() else "no stderr"
        raise RuntimeError(f"{chain} identity assembly failed: rc={result.returncode}; {detail}")
    return json.loads(result.stdout)


def _docker_inspect(ref: str) -> dict:
    result = subprocess.run(["docker", "--host", ENDPOINT, "image", "inspect", ref,
        "--format", "{{.Id}} {{.Os}}/{{.Architecture}} {{json .RepoDigests}}"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("fixed image missing or inspect failed: " + ref)
    fields = result.stdout.strip().split(" ", 2)
    if len(fields) != 3:
        raise ValueError("malformed Docker image identity: " + ref)
    return {"reference": ref, "local_config_id": fields[0],
            "platform": fields[1], "repo_digests": json.loads(fields[2])}


def _image_records() -> list[dict]:
    import yaml
    coding = yaml.safe_load((ROOT / "workload_catalog/p1_12_deepseek_official.yaml").read_text())
    records = []
    for task in coding["tasks"]:
        pin = IMAGE_PINS[task["instance_id"]]
        manifest_path = ROOT / "data/catalog/p1_12_closure_evidence" / (
            "registry_manifest_" + pin["reference"].split("/")[1].split("@")[0] + ".json")
        config_path = ROOT / "data/catalog/p1_12_closure_evidence" / (
            "registry_config_" + pin["reference"].split("/")[1].split("@")[0] + ".json")
        manifest = json.loads(manifest_path.read_text())
        config = json.loads(config_path.read_text())
        if (task["image_arm64_digest"] != pin["reference"]
                or manifest.get("config", {}).get("digest") != pin["config_id"]
                or config.get("architecture") != "arm64" or config.get("os") != "linux"):
            raise ValueError("registered Coding digest/config/platform mismatch")
        observed = _docker_inspect(pin["reference"])
        if (observed["local_config_id"] != pin["config_id"]
                or observed["platform"] != "linux/arm64"
                or pin["reference"] not in observed["repo_digests"]):
            raise ValueError("local Coding image differs from exact registered digest")
        records.append({"chain": "Coding", "task": task["instance_id"],
            **pin, "registry_digest": pin["reference"].split("@",1)[1],
            "registry_manifest": file_record(manifest_path),
            "registry_config": file_record(config_path),
            "pull_observation": PULL_OBSERVATIONS.get(task["instance_id"]), **observed})

    import docops_office_repeat_01_entry as office
    old = read_json("env/docops-office-repeat-01/frozen-identity.json")
    for task in old["identity"]["tasks"]:
        observed = _docker_inspect(task["image_ref"])
        if observed["local_config_id"] != task["image_id"] or observed["platform"] != "linux/arm64":
            raise ValueError("Office image differs from fixed frozen image ID")
        records.append({"chain": "Office", "task": task["key"],
                        "expected_id": task["image_id"], **observed})
    base = old["identity"]["base_image"]
    observed = _docker_inspect(base["reference"])
    if observed["local_config_id"] != base["expected_id"] or observed["platform"] != "linux/arm64":
        raise ValueError("Office base image differs from fixed frozen ID")
    records.append({"chain": "Office", "task": "base", "expected_id": base["expected_id"], **observed})
    return records


def _snapshot_protected(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    roots = [Path("env/local-three-class-repeat-01"),
        Path("reports/resource/LOCAL-THREE-CLASS-REPEAT-01"),
        Path("data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01"),
        Path("data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01"),
        Path("reports/resource/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01"),
        Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-characterization-v1"),
        Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v1"),
        Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2"),
        Path("env/local-three-class-repeat-01-offline-repair")]
    if profile.key == "complete02":
        roots.extend([Path("env/local-three-class-repeat-01-continuation-01"),
                      Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2")])
    out = {}
    for base in roots:
        out[str(base)] = [file_record(p) for p in sorted((ROOT / base).rglob("*"))
                          if p.is_file() and "__pycache__" not in p.parts]
    return out


def _save_dependency_freezes(profile: BatchProfile = CONTINUATION_PROFILE) -> list[dict]:
    env_dir = ROOT / profile.env
    env_dir.mkdir(parents=True, exist_ok=True)
    result = []
    interpreters = {
        "coding-mini": ".venvs/mini-swe-agent-2.4.6-env01/bin/python",
        "coding-evaluator": ".venvs/swebench-eval-02e7a74/bin/python",
        "office": ".venvs/docops-pilot-01/bin/python",
        "assistant": ".venvs/toolsandbox-pilot-01/bin/python"}
    for name, path in interpreters.items():
        p = subprocess.run([str(ROOT / path), "-m", "pip", "freeze", "--disable-pip-version-check"],
            cwd=ROOT, capture_output=True, text=True, timeout=90, check=True)
        target = profile.env / f"{name}-freeze.txt"
        if (ROOT / target).exists():
            if (ROOT / target).read_text(encoding="utf-8") != p.stdout:
                raise ValueError("venv freeze changed after preparation: " + name)
        else:
            with (ROOT / target).open("x", encoding="utf-8") as stream:
                stream.write(p.stdout)
        result.append(file_record(target))
    return result


def _prepare_assistant_source_files(profile: BatchProfile = CONTINUATION_PROFILE) -> list[dict]:
    source_env = ROOT / "env/toolsandbox-measurement-volcano-01"
    dest = ROOT / profile.env
    dest.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ("source-manifest.json", "venv-freeze.txt"):
        source = source_env / name
        target = dest / name
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ValueError("ToolSandbox frozen source metadata changed")
        else:
            shutil.copyfile(source, target)
        records.append(file_record(target))
    return records


def _old_excel_binding(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    raw_dir = Path("data/raw/generated") / OLD_COLLECTION / OLD_RUN_ID
    report_dir = Path("reports/resource") / OLD_COLLECTION
    raw_manifest = file_record(raw_dir / "manifest.json")
    summary = read_json(raw_dir / "summary.json")
    if (summary.get("identity_sha256") != OLD_IDENTITY
            or summary.get("task_key") != TASKS["Office"][0]
            or summary.get("round") != 0):
        raise ValueError("old Excel sample identity/task/round mismatch")
    return {"collection": OLD_COLLECTION, "run_id": OLD_RUN_ID,
        "task": summary["task_key"], "round": summary["round"],
        "identity_sha256": OLD_IDENTITY, "raw_manifest": raw_manifest,
        "outer_report": file_record(report_dir / OLD_RUN_ID / "run-report.json"),
        "historical_batch_summary": file_record(report_dir / "batch-summary.json"),
        "old_approval": file_record(report_dir / "APPROVAL.json"),
        "old_frozen_identity": file_record("env/local-three-class-repeat-01/frozen-identity.json"),
        "old_plan_identity": file_record("env/local-three-class-repeat-01/plan-identity.json"),
        "comparability": _office_comparability(summary, profile)}


def _office_comparability(old_summary: dict, profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    """Compare the original Excel configuration and execution code to this profile."""
    import docops_office_repeat_01_entry as office
    import docops_measurement_validate_01_entry as single
    old_identity = read_json("env/local-three-class-repeat-01/frozen-identity.json")["identity"]["components"]["Office"]
    task = next(t for t in old_identity["tasks"] if t["key"] == TASKS["Office"][0])
    route = single.configured_route(single.VOLCANO_02_PROFILE)
    current = office_config_with_route(office, task, 0, route, profile)
    run_inputs = {x["path"]: x["sha256"] for x in
        json.loads((ROOT / "data/raw/generated" / OLD_COLLECTION / OLD_RUN_ID / "manifest.json").read_text())["inputs"]}
    new_code = {x["path"]: x["sha256"] for x in office.fixed_code_records()}
    core = ["scripts/docops_word_resource_01_entry.py",
            "src/agent_workload_characterization/runners/docops_word_agent.py",
            "src/agent_workload_characterization/runners/docops_environment.py",
            "src/agent_workload_characterization/collectors/execution_measurement.py",
            "src/agent_workload_characterization/collectors/resource_sampler.py"]
    code_match = {p: (run_inputs.get(p) == new_code.get(p)) for p in core}
    old_config = old_identity["run_configs"][TASKS["Office"][0]]
    old_budget = {"max_steps": old_config["max_steps"],
                  "max_tokens_per_request": old_config["max_tokens"],
                  "agent_s": old_config["agent_budget_s"],
                  "verifier_s": old_config["verifier_budget_s"],
                  "wall_s": old_config["total_wall_s"]}
    config_match = (old_summary.get("max_steps") == current["max_steps"]
        and old_summary.get("task_image", {}).get("expected_id") == current["image_id"]
        and old_identity.get("model", {}).get("api_base") == route["api_base"]
        and old_identity.get("model", {}).get("request_model") == route["request_model"]
        and all(code_match.values())
        and old_budget.get("max_steps") == current["max_steps"]
        and old_budget.get("max_tokens_per_request") == current["max_tokens"]
        and old_budget.get("agent_s") == current["agent_budget_s"]
        and old_budget.get("verifier_s") == current["verifier_budget_s"]
        and old_budget.get("wall_s") == current["total_wall_s"]
        and old_identity.get("tools", {}).get("same_tool_names_all_tasks"))
    return {"old_vs_new_task_execution_profile_matches": bool(config_match),
        "old_run_config_from_summary": {"max_steps": old_summary.get("max_steps"),
            "task_image": old_summary.get("task_image"), "budget": old_budget,
            "route": old_identity.get("model"),
            "tools": old_identity.get("tools")},
        "new_config": current, "core_code_hash_matches": code_match,
        "basis": "raw manifest execution-input hashes, saved old identity, and current frozen task config"}


def build_identity(*, image_records: list[dict] | None = None,
                   profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    # The Assistant identity reader requires its new-collection source manifest
    # to exist before the three per-venv components are assembled.
    freezes = _save_dependency_freezes(profile)
    source_files = _prepare_assistant_source_files(profile)
    components = {chain: _component_process(chain, profile) for chain in TASKS}
    office_route = components["Office"]["model"]["route"]
    coding_route = components["Coding"]["route"]
    assistant_route = components["Assistant"]["route"]
    routes = [office_route["api_base"], coding_route["api_base"], assistant_route["api_base"]]
    if len(set(routes)) != 1:
        raise ValueError("three chain API base URLs differ")
    if (components["Coding"]["route"]["request_model"] != "openai/deepseek-v4-flash"
            or components["Office"]["model"]["request_model"] != "openai/deepseek-v4-flash"
            or components["Assistant"]["route"]["request_model_alias"] != "openai/deepseek-v4-flash"):
        raise ValueError("three chain model aliases differ from frozen request model")
    old_excel = _old_excel_binding(profile)
    schedule = planned_schedule(profile)
    expected_slots = 12 if profile.key == "complete02" else 26
    if len(schedule) != expected_slots:
        raise AssertionError(f"{profile.key} schedule must have {expected_slots} slots")
    identity = {"schema": f"local-three-class-{profile.key}-identity-v1",
        "collection": profile.collection, "components": components, "schedule": schedule,
        "images": image_records or [], "dependency_freezes": freezes,
        "assistant_frozen_source_metadata": source_files,
        "old_excel_sample_binding": old_excel,
        "attempt_retry": 0, "per_attempt_wall_caps_s": CAPS,
        "batch": {"wall_s": profile.batch_wall_s, "closeout_reserve_s": profile.closeout_reserve_s,
                  "preparation_and_image_fetch_excluded": True,
                  "next_attempt_requires_full_cap_and_closeout": True},
        "cost": {"actual_bill": "unknown", "hard_cap": None,
                 "user_acceptance": "current request explicitly accepts unknown costs without a hard cap"},
        "network": "shared netns per-interface; not task/API exclusive",
        "paths": {"env": str(profile.env), "reports": str(profile.report), "raw": str(profile.raw)},
        "approval_flag": profile.approval_flag, "entry": file_record(profile.entry),
        "historical_acceptance_bug_fix": file_record("scripts/local_three_class_repeat_01_entry.py")}
    return identity


def namespace_clean(root: Path = ROOT, profile: BatchProfile = CONTINUATION_PROFILE) -> bool:
    raw = root / profile.raw
    report = root / profile.report
    return not ((raw.exists() and any(raw.iterdir()))
        or (report.exists() and any(p.name != "APPROVAL.json" for p in report.iterdir())))


def verify_identity(frozen: dict, root: Path = ROOT,
                    profile: BatchProfile = CONTINUATION_PROFILE) -> None:
    ident = frozen["identity"]
    if digest(ident) != frozen["identity_sha256"]:
        raise ValueError(f"{profile.key} identity digest mismatch")
    for row in iter_file_rows(ident):
        if file_record(row["path"], root) != row:
            raise ValueError(f"{profile.key} identity source drift: " + row["path"])


def iter_file_rows(obj):
    if isinstance(obj, dict):
        if {"path", "bytes", "sha256"}.issubset(obj):
            yield {k: obj[k] for k in ("path", "bytes", "sha256")}
        else:
            for value in obj.values():
                yield from iter_file_rows(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_file_rows(value)


def prepare(profile: BatchProfile = CONTINUATION_PROFILE) -> dict:
    if not namespace_clean(profile=profile) or (ROOT / profile.env / "plan-identity.json").exists():
        raise ValueError(f"{profile.key} namespace occupied; refusing overwrite")
    preparation_started = time.monotonic()
    preparation_started_utc = datetime.now(timezone.utc).isoformat()
    (ROOT / profile.env).mkdir(parents=True, exist_ok=True)
    protected = _snapshot_protected(profile)
    protected_path = ROOT / profile.env / "protected-before.json"
    if protected_path.exists():
        if json.loads(protected_path.read_text(encoding="utf-8")) != protected:
            raise ValueError("protected history snapshot changed during preparation")
    else:
        write_new(profile.env / "protected-before.json", protected)
    images = _image_records()
    identity = build_identity(image_records=images, profile=profile)
    frozen = {"schema": f"local-three-class-{profile.key}-freeze-v1",
              "identity": identity, "identity_sha256": digest(identity)}
    write_new(profile.env / "plan-identity.json", frozen)
    write_new(profile.env / "frozen-identity.json", frozen)
    prep_inputs = list(iter_file_rows(identity)) + [file_record(profile.env / "protected-before.json")]
    outputs = [file_record(p) for p in sorted((ROOT / profile.env).rglob("*"))
               if p.is_file() and p.name != "preparation-manifest.json"]
    write_new(profile.env / "preparation-manifest.json", {
        "identity_sha256": frozen["identity_sha256"], "inputs": prep_inputs,
        "outputs": outputs, "source": "current authorized continuation request",
        "started_at_utc": preparation_started_utc,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "wall_s": time.monotonic() - preparation_started,
        "image_pull_durations_s": {task: observation.get("duration_s")
            for task, observation in PULL_OBSERVATIONS.items()}})
    verify_identity(frozen, profile=profile)
    return {"identity_sha256": frozen["identity_sha256"],
            "slot_count": len(identity["schedule"]), "namespace_clean": True,
            "images": images, "office_merge_comparable":
                identity["old_excel_sample_binding"]["comparability"]}


def _manifest_file_rows(run_dir: Path, chain: str) -> dict[str, dict]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if chain == "Coding":
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ValueError("Coding raw manifest files mapping missing")
        return {path: {"path": path, "bytes": (run_dir / path).stat().st_size,
                       "sha256": sha} for path, sha in files.items()}
    files = manifest.get("outputs" if chain == "Office" else "files")
    if not isinstance(files, list):
        raise ValueError(f"{chain} raw manifest file list missing")
    return {x["path"]: {k: x[k] for k in ("path", "bytes", "sha256")} for x in files}


def verify_raw(run_dir: Path, chain: str) -> dict:
    rows = _manifest_file_rows(run_dir, chain)
    actual = {p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*")
              if p.is_file() and p.name != "manifest.json"}
    if set(rows) != actual:
        raise ValueError(f"raw file set mismatch:{chain}")
    for rel, row in rows.items():
        data = (run_dir / rel).read_bytes()
        if len(data) != row["bytes"] or sha_bytes(data) != row["sha256"]:
            raise ValueError("raw hash mismatch: " + rel)
    return {"files": len(rows), "file_set_match": True, "hashes_match": True}


def _interval_status(rows, metric_names=("cpu", "io_read", "io_write")) -> dict:
    result = {name: {"valid": 0, "gaps": 0, "candidate": 0} for name in metric_names}
    for row in rows or []:
        metrics = row.get("metrics", {})
        for name in metric_names:
            if name in metrics:
                result[name]["candidate"] += 1
                if metrics[name].get("status") == "valid":
                    result[name]["valid"] += 1
                else:
                    result[name]["gaps"] += 1
    return result


def _supplement_quality(raw_dir: Path) -> dict:
    path = raw_dir / "supplemental_measurements.json"
    if not path.is_file():
        return {"network_samples": 0, "network_valid_interface_interval_records": 0,
                "network_gap_intervals": None, "disk_roles": {}, "cache": "unknown"}
    supp = json.loads(path.read_text())
    network = supp.get("network", {})
    disk_roles = {}
    for field in ("container_disk_footprints", "disk_footprint"):
        root = supp.get(field)
        if isinstance(root, dict):
            for role, data in root.items():
                if isinstance(data, dict):
                    fp = data.get("footprint", data)
                    disk_roles[role] = fp.get("status", "unknown") if isinstance(fp, dict) else "unknown"
    net_intervals = network.get("intervals") or []
    per_interface = {}
    for row in net_intervals:
        interface = row.get("interface", "unknown")
        entry = per_interface.setdefault(interface, {"candidate": 0, "valid": 0, "gaps": 0})
        entry["candidate"] += len(row.get("metrics", {}))
        for metric in row.get("metrics", {}).values():
            if metric.get("status") == "valid":
                entry["valid"] += 1
            else:
                entry["gaps"] += 1
    valid = sum(row["valid"] for row in per_interface.values())
    candidate = sum(row["candidate"] for row in per_interface.values())
    cache = "unsupported"
    for scope in (supp.get("disk_footprint", {}), supp.get("container_disk_footprints", {})):
        for v in (scope.values() if isinstance(scope, dict) else []):
            if isinstance(v, dict) and (v.get("role") == "shared_task_cache" or v.get("status") == "unsupported"):
                cache = "unsupported"
    return {"network_samples": len(network.get("samples", [])),
        "network_candidate_interface_metric_interval_records": candidate,
        "network_valid_interface_interval_records": valid,
        "network_gap_interface_interval_records": candidate - valid,
        "network_per_interface": per_interface,
        "network_gap_intervals": network.get("metric_gap_count"),
        "network_status": network.get("status", "unknown"),
        "disk_roles": disk_roles, "cache": cache,
        "supplement_status": supp.get("status", "unknown")}


def verifier_not_applicable(raw_dir: Path, report: dict, evidence: dict) -> bool:
    """Only an explicitly skipped verifier may have no verifier observations."""
    if (report.get("execution_status") != "no_candidate"
            or report.get("evaluation_status") != "not_run"
            or any(v.get("scope_kind") == "verifier_container" for v in evidence.values())):
        return False
    path = raw_dir / "events.jsonl"
    if not path.is_file():
        return False
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    skipped = any(e.get("kind") == "verifier" and e.get("attrs", {}).get("status") == "not_run"
                  for e in events)
    started = any((e.get("kind") == "container" and e.get("attrs", {}).get("scope") == "verifier"
                   and e.get("attrs", {}).get("action") == "start")
                  or (e.get("kind") == "verifier" and e.get("attrs", {}).get("status") == "running")
                  for e in events)
    return skipped and not started


def measurement_quality(raw_dir: Path, chain: str, report: dict) -> dict:
    gaps = []
    cpu = {}; memory = {}; io = {}; not_applicable = {}
    if chain == "Office":
        summary = report.get("summary", {})
        if not summary and (raw_dir / "summary.json").is_file():
            summary = json.loads((raw_dir / "summary.json").read_text())
        measurement = summary.get("measurement", {})
        intervals = measurement.get("resource_intervals", {})
        for scope in ("container", "host_agent_process"):
            if scope not in intervals:
                gaps.append(scope + "_resource_intervals_missing")
                cpu[scope] = {"valid": 0, "candidate": 0, "gaps": 0}
                io[scope] = {}
                continue
            status = _interval_status(intervals[scope])
            cpu[scope], io[scope] = status["cpu"], {k:v for k,v in status.items() if k != "cpu"}
            if not status["cpu"]["valid"]:
                gaps.append(scope + "_cpu_intervals_missing")
        samples = summary.get("samples", [])
        memory["container"] = sum(1 for x in samples if x.get("container", {}).get("mem_current_bytes") is not None)
        memory["host_agent_process"] = sum(1 for x in samples if x.get("host_agent", {}).get("rss_bytes") is not None)
        if not memory["container"]:
            gaps.append("container_memory_current_missing")
        if measurement.get("call_timing_status") != "complete":
            gaps.append("request_tool_timing_partial")
        disk_required = ["task_workspace_submission"]
        supp = _supplement_quality(raw_dir)
        disk = json.loads((raw_dir / "supplemental_measurements.json").read_text()).get("container_disk_footprints", {})
        for name in disk_required:
            entry = disk.get(name)
            if not entry or entry.get("footprint", {}).get("status") != "complete":
                gaps.append(name + "_footprint_partial")
    elif chain == "Coding":
        samples_path = raw_dir / "samples.json"
        samples = json.loads(samples_path.read_text()) if samples_path.is_file() else {}
        evidence = samples.get("evidence", {})
        verifier_skipped = verifier_not_applicable(raw_dir, report, evidence)
        if verifier_skipped:
            not_applicable = {name: {"status": "not_applicable",
                              "reason": "no_candidate; evaluation explicitly not_run; verifier not started"}
                              for name in ("verifier_container", "verifier_workspace")}
        for scope_id, scope in evidence.items():
            kind = scope.get("scope_kind", "unknown")
            rows = scope.get("samples", [])
            intervals = _interval_status_from_samples(rows)
            cpu[kind] = intervals["cpu"]
            io[kind] = {k:v for k,v in intervals.items() if k != "cpu"}
            memory[kind] = sum(1 for row in rows
                if _sample_read_ok(row, "memory")
                and row.get("mem_current_bytes") is not None)
        if not any(v.get("valid", 0) for k,v in cpu.items() if k == "agent_container"):
            gaps.append("agent_container_cpu_intervals_missing")
        if not verifier_skipped and not any(v.get("valid", 0) for k,v in cpu.items() if k == "verifier_container"):
            gaps.append("verifier_container_cpu_intervals_missing")
        if not memory.get("agent_container"):
            gaps.append("agent_container_memory_current_missing")
        supp = _supplement_quality(raw_dir)
        disk = json.loads((raw_dir / "supplemental_measurements.json").read_text()).get("container_disk_footprints", {})
        for name in (("agent_workspace",) if verifier_skipped else ("agent_workspace", "verifier_workspace")):
            if disk.get(name, {}).get("footprint", {}).get("status") != "complete":
                gaps.append(name + "_footprint_partial")
    else:
        sample_rows = report.get("host_sampling", {}).get("resource_intervals", [])
        status = _interval_status(sample_rows)
        cpu["assistant_worker"] = status["cpu"]
        io["assistant_worker"] = {k:v for k,v in status.items() if k != "cpu"}
        if not status["cpu"]["valid"]:
            gaps.append("assistant_worker_cpu_intervals_missing")
        samples_path = raw_dir / "samples.jsonl"
        nmem = 0
        if samples_path.is_file():
            for line in samples_path.read_text().splitlines():
                if not line.strip():
                    continue
                sample = json.loads(line)
                if _sample_read_ok(sample, "memory") and sample.get("rss_bytes") is not None:
                    nmem += 1
        memory["assistant_worker"] = nmem
        if not nmem:
            gaps.append("assistant_worker_rss_missing")
        supp = _supplement_quality(raw_dir)
        task_state = json.loads((raw_dir / "supplemental_measurements.json").read_text()).get("task_workspace", {})
        if task_state.get("status") != "not_applicable":
            gaps.append("assistant_task_workspace_status_unexpected")

    supp = _supplement_quality(raw_dir)
    if supp["network_samples"] < 2 or supp["network_valid_interface_interval_records"] < 1:
        gaps.append("shared_netns_valid_intervals_missing")
    return {"status": "complete" if not gaps else "partial", "gaps": sorted(set(gaps)),
        "not_applicable": not_applicable,
        "cpu_intervals": cpu, "memory_valid_samples": memory, "io_intervals": io,
        "network": supp, "observation_scope": "shared netns interfaces; not task/API-exclusive"}


def _interval_status_from_samples(samples: list[dict]) -> dict:
    from agent_workload_characterization.collectors.execution_measurement import counter_rate_intervals

    identity = ["scope"]
    status = {
        "cpu": {"path": "cpu_usage_usec", "divisor": 1_000_000,
                "unit": "cpu_seconds", "rate_unit": "average_core",
                "identity_paths": identity, "status_paths": [("read_status", "cpuacct.usage")]},
        "io_read": {"path": "io_read_bytes", "unit": "bytes",
                     "rate_unit": "bytes_per_second", "identity_paths": identity,
                     "status_paths": [("read_status", "io")]},
        "io_write": {"path": "io_write_bytes", "unit": "bytes",
                      "rate_unit": "bytes_per_second", "identity_paths": identity,
                      "status_paths": [("read_status", "io")]},
    }
    projected = counter_rate_intervals(samples, status)
    out = {name: {"candidate": len(projected),
                  "valid": sum(x["metrics"][name]["status"] == "valid" for x in projected),
                  "gaps": sum(x["metrics"][name]["status"] != "valid" for x in projected)}
           for name in status}
    return out


def _sample_read_ok(sample: dict, metric: str) -> bool:
    status = sample.get("read_status")
    if isinstance(status, str):
        return status in ("ok", "valid", "complete")
    if not isinstance(status, dict):
        return False
    keys = {"cpu": ("cpuacct.usage", "cpu", "status"),
            "memory": ("memory.usage_in_bytes", "memory.current", "memory", "status"),
            "io_read": ("io", "blkio.io_service_bytes_recursive", "status"),
            "io_write": ("io", "blkio.io_service_bytes_recursive", "status")}[metric]
    value = next((status[k] for k in keys if k in status), None)
    return isinstance(value, str) and value.startswith("ok")


def _cleanup_and_archive(chain: str, report: dict, raw_dir: Path, raw_check: dict | None) -> dict:
    cleanup = "unknown"
    if chain == "Office":
        summary = report.get("summary", {})
        if not summary and (raw_dir / "summary.json").is_file():
            summary = json.loads((raw_dir / "summary.json").read_text())
        event = next((x for x in summary.get("events", [])
                      if x.get("phase") == "removal_verified"), None)
        result = report.get("removal_verified") or (event or {}).get("result")
        image_event = next((x for x in summary.get("events", [])
                            if x.get("phase") == "image_tag_after_stop"), None)
        image_present = report.get("image_retention_verified")
        if image_present is None and image_event:
            image_present = image_event.get("present") is True and bool(image_event.get("id"))
        cleanup = "confirmed" if result == "removed" and image_present is True else "unconfirmed"
        if image_present is False:
            cleanup = "image_not_retained"
    elif chain == "Coding":
        cleanup = "confirmed" if report.get("cleanup_status") == "ok" else "unconfirmed"
    else:
        cleanup_obj = report.get("cleanup", {})
        if not cleanup_obj and (raw_dir / "ATTEMPT_COMPLETED.json").is_file():
            cleanup_obj = json.loads((raw_dir / "ATTEMPT_COMPLETED.json").read_text()).get("cleanup", {})
        cleanup = "confirmed" if all(cleanup_obj.get(k) is True
            for k in ("wait_reaped", "original_process_gone", "sampler_stopped")) else "unconfirmed"
    archive = "verified" if raw_check and raw_check.get("file_set_match") and raw_check.get("hashes_match") else "unverified"
    if chain == "Assistant" and report.get("archive_verification", {}).get("valid") is not True:
        archive = "unverified"
    if chain == "Office" and report.get("archive_valid") is False:
        archive = "unverified"
    if chain == "Coding" and report.get("archive_status") not in ("ok", "complete"):
        archive = "unverified"
    return {"cleanup": cleanup, "archive": archive}


def slot_acceptance(chain: str, slot: dict, report: dict, raw_dir: Path) -> dict:
    raw_check = None
    archive_error = None
    try:
        raw_check = verify_raw(raw_dir, chain)
    except Exception as exc:
        archive_error = type(exc).__name__
    cleanup_archive = _cleanup_and_archive(chain, report, raw_dir, raw_check)
    quality_error = None
    try:
        quality = measurement_quality(raw_dir, chain, report)
    except Exception as exc:
        quality_error = type(exc).__name__
        quality = {"status": "partial", "gaps": ["measurement_parse_error:" + quality_error],
                   "cpu_intervals": {}, "memory_valid_samples": {}, "io_intervals": {},
                   "network": {}, "observation_scope": "unknown"}
    if archive_error:
        quality["gaps"].append("raw_archive_validation_error:" + archive_error)
        quality["status"] = "partial"
    status = _report_outcome(chain, report)
    return {**slot, "slot_status": "executed",
        "report_status": status,
        "task_result": _task_result(chain, report),
        "agent_termination": _termination(chain, report),
        "infra_status": _infra(chain, report),
        "measurement": quality, "cleanup_status": cleanup_archive["cleanup"],
        "archive_status": cleanup_archive["archive"],
        "archive_error_type": archive_error,
        "measurement_parse_error_type": quality_error}


def _report_outcome(chain, report):
    if chain == "Office":
        return "reported" if report.get("summary", {}).get("outcome") is not None else "missing"
    if chain == "Coding":
        return "reported" if report.get("execution_status") else "missing"
    return "reported" if report.get("worker_result") is not None else "missing"


def _task_result(chain, report):
    if chain == "Office":
        return report.get("summary", {}).get("outcome", {}).get("phases", {}).get("verifier", {}).get("reward")
    if chain == "Coding":
        return report.get("resolved")
    return report.get("evaluation", {}).get("raw_metrics", report.get("evaluation"))


def _termination(chain, report):
    if chain == "Office":
        return report.get("summary", {}).get("outcome", {}).get("phases", {}).get("agent", {}).get("status")
    if chain == "Coding":
        return report.get("execution_status")
    worker = report.get("worker_result") or {}
    return worker.get("stop_reason") or report.get("exit_code")


def _infra(chain, report):
    if chain == "Office":
        return "failed" if report.get("summary", {}).get("outcome", {}).get("infra_failures") else "ok"
    if chain == "Coding":
        return "ok" if report.get("cleanup_status") == "ok" and report.get("execution_status") not in (None, "infra_failure") else "failed"
    if report.get("worker_wait_error"):
        return "failed"
    if report.get("killed_by_deadline"):
        # A configured parent deadline is an Agent termination, not an
        # infrastructure failure, provided cleanup/reaping is separately confirmed.
        return "ok"
    if report.get("failure") or report.get("worker_exit_code") not in (None, 0):
        return "failed"
    return "ok"


def stop_policy(result: dict, *, shared_auth_failure: bool = False) -> tuple[bool, bool, str | None]:
    """Return (stop this class, stop all classes, reason)."""
    if result.get("cleanup_status") != "confirmed":
        return True, True, "cleanup_unconfirmed"
    if result.get("archive_status") != "verified":
        return True, False, "archive_or_acceptance_failure"
    if shared_auth_failure:
        return True, True, "shared_gateway_authentication_or_route_failure"
    if result.get("measurement", {}).get("status") != "complete":
        return True, False, "critical_measurement_gap"
    if result.get("infra_status") != "ok":
        return True, False, "chain_infrastructure_failure"
    return False, False, None


def _run_office(slot, frozen, run_id, batch_work_deadline,
                profile: BatchProfile = CONTINUATION_PROFILE):
    import docops_office_repeat_01_entry as office
    import docops_word_resource_01_entry as shared
    comp = frozen["identity"]["components"]["Office"]
    task = next(x for x in comp["tasks"] if x["key"] == slot["task"])
    config = comp["run_configs_by_task_round"][slot["task"]][slot["round"]]
    validate_office_route(config, comp["model"]["route"])
    inputs = [*comp["code_and_runtime_files"], *task["files"], file_record(profile.entry)]
    run_paths = {"task_toml": "/task.toml", "instruction": "/instruction.md",
        "task_metadata": "/environment/task_metadata.json"}
    runplan = {"run_id": run_id, "identity_sha256": frozen["identity_sha256"],
        "run_config": config, "run_inputs": inputs,
        "identity": {"files": {k: next(x for x in inputs if x["path"].endswith(v))
                                 for k,v in run_paths.items()}},
        "batch_work_deadline_monotonic": batch_work_deadline}
    summary = asyncio.run(shared.run_attempt(ROOT, runplan))
    life = {x.get("phase"): x for x in summary.get("events", [])}
    result = {"collection": profile.collection, "run_id": run_id,
        "identity_sha256": frozen["identity_sha256"], "summary": summary,
        "exit_code": shared.exit_code_for(summary),
        "removal_verified": life.get("removal_verified", {}).get("result"),
        "image_retention_verified": life.get("image_tag_after_stop", {}).get("id") == task["image_id"]}
    write_new(profile.report / run_id / "run-report.json", result)
    return result["exit_code"]


def _run_coding(slot, frozen, run_id, api_base, api_key,
                profile: BatchProfile = CONTINUATION_PROFILE):
    from agent_workload_characterization.runners import p1_12_entry as p1
    from agent_workload_characterization.runners.mini_agent_adapter import MiniSweAgentHarness
    from agent_workload_characterization.runners.coding_pilot import SwebenchVerifierRunner
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    import coding_measurement_volcano_01_entry as coding
    cfg = p1.load_config()
    bundled = MiniSweAgentHarness.load_bundled_config(p1.MINI_VENV_PY)
    model_cfg = bundled.get("model") or {}
    mini_config = {"agent": dict(bundled.get("agent") or {}),
        "model": {"model_name": "openai/deepseek-v4-flash",
            "model_kwargs": {k:v for k,v in (model_cfg.get("model_kwargs") or {}).items()
                             if k not in ("num_retries", "max_tokens")}},
        "environment": dict(bundled.get("environment") or {})}
    task = next(x for x in cfg["tasks"] if x["instance_id"] == slot["task"])
    pin = IMAGE_PINS[slot["task"]]
    runtime = DockerCliRuntime(authorized=True, collection=profile.collection)
    harness = MiniSweAgentHarness(p1.MINI_VENV_PY, authorized=True,
        mini_config=mini_config, target_image_ref=pin["reference"])
    verifier = SwebenchVerifierRunner(authorized=True, model_name="mini-SWE-agent-2.4.6")
    credentials = {"OPENAI_API_BASE": api_base, "OPENAI_API_KEY": api_key}
    runner = p1.build_task_runner(cfg, slot["task"], authorized=True,
        runtime=runtime, harness=harness, verifier=verifier, credentials=credentials,
        project_root=ROOT, limits=p1._attempt_limits(cfg), collection=profile.collection)
    if runner.image != pin["reference"]:
        raise ValueError("Coding task builder image differs from registered pin")
    runner.execution_identity_sha256 = frozen["identity_sha256"]
    outcome = dataclasses.asdict(runner.run(run_id=run_id))
    outcome.update(identity_sha256=frozen["identity_sha256"], route=coding._configured_route(),
                   task=slot["task"], round=slot["round"], sequence=slot["sequence"])
    write_new(profile.report / run_id / "run-report.json", outcome)
    return coding.exit_code_for(outcome)


def _run_assistant(slot, frozen, run_id, batch_deadline, batch_work_deadline,
                   profile: BatchProfile = CONTINUATION_PROFILE):
    import toolsandbox_resource_pilot_01_entry as ts
    assistant = assistant_profile(profile)
    plan = {"ready_for_execution": True,
        "identity": frozen["identity"]["components"]["Assistant"],
        "identity_sha256": frozen["identity_sha256"]}
    report_path = ROOT / profile.report / run_id / "run-report.json"
    outer_manifest = ROOT / profile.report / run_id / "outer-manifest.json"
    rc = ts.execute(ROOT, plan, profile=assistant, scenario_name=slot["task"],
        run_id=run_id, run_metadata=slot,
        batch_deadline_ns=int(batch_deadline * 1e9),
        batch_work_deadline_ns=int(batch_work_deadline * 1e9),
        report_path=report_path, outer_manifest_path=outer_manifest)
    return rc


def _child(slot_index: int, run_id: str, deadline: float, work_deadline: float,
           api_base: str, api_key: str,
           profile: BatchProfile = CONTINUATION_PROFILE) -> int:
    frozen = read_json(profile.env / "frozen-identity.json")
    verify_identity(frozen, profile=profile)
    slot = frozen["identity"]["schedule"][slot_index]
    allocation = read_json(profile.report / run_id / "ATTEMPT_STARTED.json")
    approval = read_json(profile.report / "APPROVAL.json")
    if (allocation.get("slot") != slot or allocation.get("identity_sha256") != frozen["identity_sha256"]
            or approval.get("identity_sha256") != frozen["identity_sha256"]):
        raise ValueError("slot identity/approval mismatch")
    if slot["chain"] == "Office":
        return _run_office(slot, frozen, run_id, work_deadline, profile)
    if slot["chain"] == "Coding":
        return _run_coding(slot, frozen, run_id, api_base, api_key, profile)
    return _run_assistant(slot, frozen, run_id, deadline, work_deadline, profile)


def _class_protocol_failure(raw_dir: Path, chain: str) -> bool:
    event_path = raw_dir / ("agent/events.jsonl" if chain == "Office" else "events.jsonl")
    if not event_path.is_file():
        return False
    # BadRequestError can wrap provider authentication/configuration failures.
    # Stop conservatively on the structured class, without inspecting or copying
    # error messages that may contain credential fragments.
    classes = {"AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError"}
    try:
        for line in event_path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("kind") == "llm_request":
                attrs = event.get("attrs", {})
                if any(isinstance(attrs.get(k), str) and attrs[k] in classes
                       for k in ("error_type", "exception_type", "error_class")):
                    return True
                # SemanticRecorder stores the fixed-whitelist class in this
                # sanitized envelope, not the optional fields above.
                if attrs.get("error") in tuple(c + ":<sanitized>" for c in classes):
                    return True
    except (OSError, ValueError, TypeError):
        return False
    return False


def _run_report_path(chain: str, run_id: str,
                     profile: BatchProfile = CONTINUATION_PROFILE) -> Path:
    return ROOT / profile.report / run_id / "run-report.json"


def execute(profile: BatchProfile = CONTINUATION_PROFILE) -> int:
    frozen = read_json(profile.env / "frozen-identity.json")
    verify_identity(frozen, profile=profile)
    if not namespace_clean(profile=profile):
        raise ValueError(f"{profile.key} namespace already contains an attempt")
    office = frozen["identity"]["components"]["Office"]
    for configs in office["run_configs_by_task_round"].values():
        for config in configs:
            validate_office_route(config, office["model"]["route"])
    live_images = _image_records()
    if live_images != frozen["identity"]["images"]:
        raise ValueError("live image identity differs from frozen identity")
    from agent_workload_characterization.runners.smoke_launcher import load_credentials
    api_base, api_key = load_credentials()
    routes = [frozen["identity"]["components"][chain]["route"]["api_base"]
        if chain != "Office" else frozen["identity"]["components"][chain]["model"]["route"]["api_base"]
        for chain in TASKS]
    if any(route != api_base for route in routes):
        raise ValueError("credential route differs from frozen chain routes")
    env = dict(os.environ)
    env.update({"LITELLM_LOCAL_MODEL_COST_MAP": "True", "PYTHONPATH": "src:scripts",
        "VOLCANO_API_KEY": api_key, "DEEPSEEK_API_KEY": api_key,
        "OPENAI_API_KEY": api_key, "OPENAI_API_BASE": api_base,
        "PILOT_API_KEY": api_key, "PILOT_API_BASE": api_base,
        "DOCKER_HOST": ENDPOINT})
    env.pop("DOCKER_CONTEXT", None)
    write_new(profile.report / "APPROVAL.json", {"schema": f"local-three-class-{profile.key}-approval-v1",
        "collection": profile.collection, "identity_sha256": frozen["identity_sha256"],
        "user_approval": "approved", "source": "explicit current user request",
        "scope": frozen["identity"]["schedule"], "attempt_retry": 0,
        "cost": "unknown; no hard cap; explicitly accepted",
        "framework_retries": "existing per-chain policies unchanged",
        "approved_at_utc": datetime.now(timezone.utc).isoformat()})
    batch_start = time.monotonic()
    batch_deadline = batch_start + profile.batch_wall_s
    work_deadline = batch_deadline - profile.closeout_reserve_s
    write_new(profile.report / "ATTEMPT_STARTED.json", {"collection": profile.collection,
        "identity_sha256": frozen["identity_sha256"], "started_monotonic": batch_start,
        "batch_wall_limit_s": profile.batch_wall_s, "closeout_reserve_s": profile.closeout_reserve_s,
        "meaning": "batch authorization consumed; per-run markers identify attempts"})
    runs = []
    stopped_classes = {}
    stop_all = None
    for slot in frozen["identity"]["schedule"]:
        chain = slot["chain"]
        reason = stop_all or stopped_classes.get(chain)
        remaining = work_deadline - time.monotonic()
        if remaining < CAPS[chain]:
            reason = "insufficient_remaining_budget_for_full_attempt_and_closeout"
        if reason:
            runs.append({**slot, "slot_status": "not_executed", "stop_reason": reason})
            continue
        verify_identity(frozen, profile=profile)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{slot['sequence']:02d}-r{slot['round']}-{chain.lower()}"
        write_new(profile.report / run_id / "ATTEMPT_STARTED.json", {"slot": slot,
            "run_id": run_id, "identity_sha256": frozen["identity_sha256"],
            "started_at_utc": datetime.now(timezone.utc).isoformat()})
        log_path = ROOT / profile.report / run_id / "entry.log"
        command = [str(ROOT / PYTHONS[chain]), "-B", str(ROOT / profile.entry),
            "--profile", profile.key,
            "--child", str(slot["sequence"]), "--run-id", run_id,
            "--deadline", str(batch_deadline), "--work-deadline", str(work_deadline)]
        started = time.monotonic()
        try:
            with log_path.open("x", encoding="utf-8") as log:
                proc = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                    stderr=log, timeout=CAPS[chain],
                    check=False)
            parent_rc = proc.returncode
        except subprocess.TimeoutExpired:
            parent_rc = 124
        report_path = _run_report_path(chain, run_id, profile)
        raw_dir = ROOT / profile.raw / run_id
        report = {}
        parse_error = None
        try:
            report = json.loads(report_path.read_text())
        except Exception as exc:
            parse_error = type(exc).__name__
        acceptance = {**slot, "run_id": run_id,
            "identity_sha256": frozen["identity_sha256"],
            "returncode": parent_rc, "runner_wall_s": time.monotonic()-started,
            "raw_path": str(profile.raw / run_id), "report_path": str(profile.report / run_id / "run-report.json")}
        if parse_error:
            acceptance.update(slot_acceptance(chain, slot, {}, raw_dir))
            acceptance.update(slot_status="executed", acceptance_status="error",
                report_parse_error_type=parse_error, task_result=None,
                agent_termination="unknown", infra_status="unknown")
        else:
            acceptance.update(slot_acceptance(chain, slot, report, raw_dir))
        auth_failure = _class_protocol_failure(raw_dir, chain)
        stop_class, stop_batch, reason = stop_policy(acceptance, shared_auth_failure=auth_failure)
        acceptance.update(acceptance_status="error" if parse_error else "complete",
                          stop_reason=reason, shared_auth_failure=auth_failure)
        write_new(profile.report / run_id / "VALIDATION.json", acceptance)
        runs.append(acceptance)
        print(json.dumps({k: acceptance.get(k) for k in
            ("sequence", "chain", "task", "round", "run_id", "slot_status", "measurement", "stop_reason")},
            ensure_ascii=False), flush=True)
        if stop_class:
            stopped_classes[chain] = reason or "chain_stop"
        if stop_batch:
            stop_all = reason or "global_stop"
    elapsed = time.monotonic() - batch_start
    summary = {"collection": profile.collection, "identity_sha256": frozen["identity_sha256"],
        "wall_s": elapsed, "within_batch_wall_limit": elapsed <= profile.batch_wall_s,
        "class_stops": stopped_classes, "global_stop": stop_all,
        "runs": runs,
        "counts": {
            "executed": sum(x.get("slot_status") == "executed" for x in runs),
            "not_executed": sum(x.get("slot_status") == "not_executed" for x in runs),
            "acceptance_errors": sum(x.get("acceptance_status") == "error" for x in runs),
            "infra_failed": sum(x.get("infra_status") == "failed" for x in runs),
            "measurement_partial": sum(x.get("measurement", {}).get("status") == "partial" for x in runs),
            "cleanup_unconfirmed": sum(x.get("cleanup_status") != "confirmed" for x in runs if x.get("run_id")),
            "archive_unverified": sum(x.get("archive_status") != "verified" for x in runs if x.get("run_id")),
        },
        "attempts_started": sum(bool(x.get("run_id")) for x in runs)}
    write_new(profile.report / "batch-summary.json", summary)
    write_new(profile.report / "ATTEMPT_COMPLETED.json", {k:v for k,v in summary.items() if k != "runs"})
    outputs = [file_record(p) for p in sorted((ROOT / profile.report).rglob("*")) if p.is_file()]
    raw_manifests = [file_record(profile.raw / x["run_id"] / "manifest.json") for x in runs
                     if x.get("run_id") and (ROOT / profile.raw / x["run_id"] / "manifest.json").is_file()]
    write_new(profile.report / "manifest.json", {"identity_sha256": frozen["identity_sha256"],
        "inputs": [file_record(profile.env / x) for x in ("plan-identity.json", "frozen-identity.json")],
        "raw_manifests": raw_manifests, "outputs": outputs})
    return 0 if not any(x.get("acceptance_status") == "error" for x in runs) else 7


def _child_main(args) -> int:
    api_base = os.environ.get("PILOT_API_BASE", "")
    api_key = os.environ.get("PILOT_API_KEY", "")
    return _child(args.child, args.run_id, args.deadline, args.work_deadline,
                  api_base, api_key, PROFILES[args.profile])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--profile", choices=tuple(PROFILES), default=CONTINUATION_PROFILE.key)
    parser.add_argument("--component", choices=TASKS)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    for profile in PROFILES.values():
        parser.add_argument(profile.approval_flag, action="store_true",
                            dest=f"approved_{profile.key}")
    parser.add_argument("--child", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--work-deadline", type=float)
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    if args.component:
        print(json.dumps(component(args.component, profile), ensure_ascii=False)); return 0
    if args.child is not None:
        return _child_main(args)
    if args.execute:
        if not getattr(args, f"approved_{profile.key}"):
            raise ValueError(f"{profile.key}-specific approval flag required")
        return execute(profile)
    result = prepare(profile) if args.prepare else {"namespace_clean": namespace_clean(profile=profile),
        "schedule": planned_schedule(profile), "identity_exists": (ROOT / profile.env / "frozen-identity.json").is_file(),
        "collection": profile.collection}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
