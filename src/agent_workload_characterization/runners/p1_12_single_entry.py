"""One-shot P1-12 Django finish-protocol revalidation entry.

This is a thin coordinator over the existing P1-12/CodingPilotRunner chain.
It is intentionally limited to django__django-16485 and one attempt; it does
not call the nine-attempt batch entry or create a retry loop.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

from . import p1_12_entry as base

TASK_ID = "django__django-16485"
COLLECTION = "P1-12-FINISH-02"
STATE_ROOT = base.PROJECT_ROOT / "reports/resource/P1-12/revalidations/FINISH-02"
APPROVAL = STATE_ROOT / "APPROVAL.json"
ATTEMPT = STATE_ROOT / "ATTEMPT_STARTED.json"
PREFLIGHT = STATE_ROOT / "PREFLIGHT.json"
SUMMARY = STATE_ROOT / "SUMMARY.json"
MANIFEST = STATE_ROOT / "MANIFEST.json"
COMMAND = ("PYTHONPATH=src " + str(base.EVAL_VENV_PY) + " -B -m "
           "agent_workload_characterization.runners.p1_12_single_entry "
           "--execute --i-approve-the-p1-12-django-finish-02")
APPROVAL_TEXT = """用户批准：按当前已验证 DeepSeek 官方 API 配置，对 django__django-16485 执行一次 Django 提交结束链路真实验证；不重试、不补跑、不扩大到九次批次。保持原提示词、30 请求上限、输出 token、时间与容器资源限制；CPU-02 与 Replay 继续暂停。"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cfg_and_task():
    cfg = base.load_config()
    task = next((t for t in cfg["tasks"] if t["instance_id"] == TASK_ID), None)
    if task is None:
        raise base.P112Error("task_not_registered")
    selected = copy.deepcopy(cfg)
    selected["tasks"] = [copy.deepcopy(task)]
    return cfg, selected, task


def identity(cfg, task):
    code = {}
    for path in sorted((base.CODE_ROOT / "src/agent_workload_characterization").rglob("*.py")):
        code[str(path.relative_to(base.CODE_ROOT))] = _sha(path)
    return {
        "collection": COLLECTION,
        "task": TASK_ID,
        "catalog": {"path": str(base.CATALOG.relative_to(base.PROJECT_ROOT)),
                    "sha256": _sha(base.CATALOG)},
        "record": {"path": task["record_locator"],
                   "sha256": task["record_sha256"]},
        "image": task["image_arm64_digest"],
        "model": {
            "provider": cfg["agent"]["provider"],
            "api_base": cfg["agent"]["api_base"],
            "model_key": cfg["agent"]["model_key"],
            "model_request_id": cfg["agent"]["model_request_id"],
            "display_name": cfg["agent"]["model_display_name"],
            "version_basis": cfg["agent"]["model_version_basis"],
        },
        "mini_venv": str(base.MINI_VENV_PY),
        "evaluator_venv": str(base.EVAL_VENV_PY),
        "code_sha256": code,
        "finish_protocol_adapter_sha256": code[
            "src/agent_workload_characterization/runners/mini_agent_adapter.py"],
        "budget": cfg["budget_per_attempt"],
        "container": {"cpu": "4", "memory": "8g", "network": "none",
                      "pull": "never"},
        "approval_path": str(APPROVAL.relative_to(base.PROJECT_ROOT)),
        "attempt_path": str(ATTEMPT.relative_to(base.PROJECT_ROOT)),
        "report_path": str(STATE_ROOT.relative_to(base.PROJECT_ROOT)),
        "command": COMMAND,
    }


def _write_new(path: Path, payload):
    base.write_json(path, payload)


def _finish(status: str, detail: str):
    record = json.loads(ATTEMPT.read_text())
    record.update(status=status, detail=detail,
                  finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    tmp = ATTEMPT.with_name("ATTEMPT_FINISH-" + uuid.uuid4().hex + ".json")
    _write_new(tmp, record)
    tmp.replace(ATTEMPT)


def _summary_payload(*, ident, outcome=None, trajectory=None, failure=None):
    info = (trajectory or {}).get("info", {})
    stats = info.get("model_stats") or {}
    return {
        "run_id": outcome.run_id if outcome else None,
        "attempt_id": outcome.attempt_id if outcome else None,
        "task": TASK_ID,
        "execution_command": COMMAND,
        "identity": ident,
        "model_calls": stats.get("api_calls"),
        "mini_exit_status": info.get("exit_status"),
        "submitted": info.get("exit_status") == "Submitted",
        "submission_content_recorded": bool(info.get("submission")),
        "execution_status": outcome.execution_status if outcome else "not_started",
        "evaluation_status": outcome.evaluation_status if outcome else "not_run",
        "resolved": outcome.resolved if outcome else None,
        "archive_status": outcome.archive_status if outcome else "not_started",
        "cleanup_status": outcome.cleanup_status if outcome else "not_started",
        "cleanup_errors": outcome.cleanup_errors if outcome else [],
        "budget_usage": outcome.budget_usage if outcome else None,
        "raw_run_dir": outcome.run_dir if outcome else None,
        "failure": failure,
        "historical_note": (
            "Historical P1-12 runs were affected by the pre-fix finish-protocol "
            "defect; this is a new API/model configuration and is not a controlled "
            "same-model comparison."),
    }


def _write_manifest(ident, summary_path: Path, raw_run_dir: str | None):
    outputs = {str(summary_path.relative_to(STATE_ROOT)):
               {"bytes": summary_path.stat().st_size, "sha256": _sha(summary_path)}}
    if raw_run_dir:
        raw_manifest = Path(raw_run_dir) / "manifest.json"
        if raw_manifest.is_file():
            outputs["raw_run_manifest"] = {
                "path": str(raw_manifest.relative_to(base.PROJECT_ROOT)),
                "bytes": raw_manifest.stat().st_size,
                "sha256": _sha(raw_manifest)}
    _write_new(MANIFEST, {"identity": ident, "outputs": outputs,
                          "manifest_self_hash": False,
                          "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    check = json.loads(MANIFEST.read_text())["outputs"]
    for name, meta in check.items():
        path = (summary_path if name != "raw_run_manifest"
                else base.PROJECT_ROOT / meta["path"])
        if path.stat().st_size != meta["bytes"] or _sha(path) != meta["sha256"]:
            raise base.P112Error("report_hash_mismatch")


def build_plan():
    cfg, selected, task = _cfg_and_task()
    ident = identity(cfg, task)
    return {"task": TASK_ID, "collection": COLLECTION, "mode": "plan_only",
            "identity": ident, "command": COMMAND,
            "authorization": {"user_approval": "pending",
                               "tool_execution_permission": "pending"},
            "limits": cfg["budget_per_attempt"],
            "scope": "one attempt; no retry; no nine-attempt batch"}


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-approve-the-p1-12-django-finish-02", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_p1_12_django_finish_02:
        print(json.dumps(build_plan(), indent=2, ensure_ascii=False))
        return 0
    if not (args.execute and args.i_approve_the_p1_12_django_finish_02):
        return 2

    if Path(sys.executable).resolve() != base.EVAL_VENV_PY.resolve():
        print("REFUSED:wrong_evaluator_interpreter")
        return 3

    ident = None
    try:
        cfg, selected, task = _cfg_and_task()
        ident = identity(cfg, task)
        base.guarded(STATE_ROOT, new=True)
        base.guarded(APPROVAL, new=True)
        base.guarded(ATTEMPT, new=True)
        _write_new(APPROVAL, {"approved": True, "approved_by": "lcq",
                               "approved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "approval_text": APPROVAL_TEXT,
                               "checklist_identity": ident})
        _write_new(ATTEMPT, {"status": "started", "identity": ident,
                              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    except Exception as exc:
        print("REFUSED:" + type(exc).__name__)
        return 3

    outcome = None
    trajectory = None
    failure = None
    try:
        from .g1_02_entry import local_docker_environment
        deadline = time.monotonic() + cfg["budget_per_attempt"]["total_wall_min"] * 60
        with local_docker_environment():
            preflight = base.preflight_checks(selected)
            _write_new(PREFLIGHT, preflight)
            if preflight["status"] != "READY":
                raise base.P112Error("preflight_not_ready")
            docker_pre = base.docker_image_preflight(selected, deadline=deadline)
            preflight["docker_images"] = docker_pre
            # PREFLIGHT is created above; this is a new state file only after
            # the same identity and path guard have passed.
            PREFLIGHT.unlink()
            _write_new(PREFLIGHT, preflight)
            if docker_pre["status"] != "READY":
                raise base.P112Error("docker_image_preflight_not_ready")
            credentials = base.resolve_credentials()
            runtime_factory, harness_factory, verifier_factory = base.production_factories()
            runner = base.build_task_runner(
                selected, TASK_ID, authorized=True,
                runtime=runtime_factory(),
                harness=harness_factory(task["image_arm64_digest"]),
                verifier=verifier_factory(), credentials=credentials,
                limits=base._attempt_limits(cfg, total_wall_s=deadline-time.monotonic()),
                collection=COLLECTION)
            outcome = runner.run()
            raw_dir = Path(outcome.run_dir)
            traj_path = raw_dir / "mini_trajectory.json"
            if traj_path.is_file():
                trajectory = json.loads(traj_path.read_text())
            payload = _summary_payload(ident=ident, outcome=outcome,
                                       trajectory=trajectory)
            _write_new(SUMMARY, payload)
            _write_manifest(ident, SUMMARY, outcome.run_dir)
            submitted = payload["submitted"]
            success = (submitted and outcome.execution_status == "ok"
                       and outcome.evaluation_status == "ok"
                       and outcome.archive_status in ("ok", "complete")
                       and outcome.cleanup_status == "ok")
            detail = ("submitted_and_evaluated" if success
                      else "finish_or_pipeline_incomplete")
            _finish("completed" if success else "failed", detail)
            print(json.dumps({"returncode": 0 if success else 5,
                              "detail": detail,
                              "run_id": outcome.run_id,
                              "model_calls": payload["model_calls"],
                              "submitted": submitted,
                              "resolved": outcome.resolved,
                              "execution_status": outcome.execution_status,
                              "evaluation_status": outcome.evaluation_status,
                              "cleanup_status": outcome.cleanup_status},
                             ensure_ascii=False))
            return 0 if success else 5
    except Exception as exc:
        failure = type(exc).__name__
        try:
            payload = _summary_payload(ident=ident, outcome=outcome,
                                       trajectory=trajectory, failure=failure)
            if not SUMMARY.exists():
                _write_new(SUMMARY, payload)
            _write_manifest(ident, SUMMARY, outcome.run_dir if outcome else None)
        except Exception:
            pass
        try:
            _finish("failed", failure)
        except Exception:
            pass
        print(json.dumps({"returncode": 5, "detail": failure}, ensure_ascii=False))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
