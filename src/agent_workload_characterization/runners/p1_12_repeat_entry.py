"""Offline-prepared, single gated entry for the repaired Coding repeats.

This is a thin coordinator over the existing P1-12 batch functions.  It has
its own identity, approval/attempt namespace and one exact command; it does
not add retry or runner logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import uuid

from . import p1_12_entry as base

COLLECTION = "P1-12-CODING-REPEAT-01"
STATE_ROOT = base.PROJECT_ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
# Production default is unchanged; offline tests may replace this with a
# temporary project root so CodingPilotRunner raw output cannot reach the
# formal collection.
RAW_PROJECT_ROOT = base.PROJECT_ROOT
APPROVAL = STATE_ROOT / "APPROVAL.json"
ATTEMPT = STATE_ROOT / "ATTEMPT_STARTED.json"
PREFLIGHT = STATE_ROOT / "PREFLIGHT.json"
COMMAND = ("PYTHONPATH=src " + str(base.EVAL_VENV_PY) + " -B -m "
           "agent_workload_characterization.runners.p1_12_repeat_entry "
           "--execute --i-approve-the-p1-12-coding-repeat-01")
APPROVAL_TEXT = ("用户批准：按已核验的修复后 Coding 小规模重复实验清单，"
                 "对三个登记 task 各执行三次，顺序执行；失败即停、不补跑、"
                 "不扩预算。FINISH-02 仅为链路验证，不计入本批重复样本。")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _identity(cfg):
    code = {}
    for path in sorted((base.CODE_ROOT / "src/agent_workload_characterization").rglob("*.py")):
        code[str(path.relative_to(base.CODE_ROOT))] = _sha(path)
    return {
        "collection": COLLECTION,
        "catalog": {"path": str(base.CATALOG.relative_to(base.PROJECT_ROOT)),
                    "sha256": _sha(base.CATALOG)},
        "dataset": cfg["dataset"],
        "agent": cfg["agent"],
        "tasks": {t["instance_id"]: {"record_sha256": t["record_sha256"],
                                      "image_arm64_digest": t["image_arm64_digest"]}
                  for t in cfg["tasks"]},
        "design": {"rounds": cfg["design"]["rounds"],
                   "repeats_per_task": cfg["design"]["repeats_per_task"],
                   "block_seed": cfg["design"]["block_seed"],
                   "order": [{"round": r, "instance_id": i}
                             for r, i in base.block_order(cfg)]},
        "budget_per_attempt": cfg["budget_per_attempt"],
        "budget_batch": cfg["budget_batch"],
        "failure_policy": cfg["failure_policy"],
        "interpreters": {"entry": str(base.EVAL_VENV_PY),
                         "agent": str(base.MINI_VENV_PY)},
        "code_sha256": code,
        "approval_path": str(APPROVAL.relative_to(base.PROJECT_ROOT)),
        "attempt_path": str(ATTEMPT.relative_to(base.PROJECT_ROOT)),
        "report_root": str(STATE_ROOT.relative_to(base.PROJECT_ROOT)),
        "command": COMMAND,
    }


def build_plan():
    cfg = base.load_config()
    ident = _identity(cfg)
    return {"task": "P1-12", "collection": COLLECTION, "mode": "plan_only",
            "identity": ident, "command": COMMAND,
            "authorization": {"user_approval": "pending",
                               "tool_execution_permission": "pending"},
            "limits": {"per_attempt": cfg["budget_per_attempt"],
                       "batch": cfg["budget_batch"]},
            "scope": "3 registered tasks x 3 rounds; one batch; no retry; no FINISH-01/02 reuse",
            "readiness": base.readiness(cfg)}


def _write(path, payload):
    base.write_json(path, payload)


def _finish(detail, status):
    record = json.loads(ATTEMPT.read_text())
    record.update(status=status, detail=detail,
                  finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    tmp = ATTEMPT.with_name("ATTEMPT_FINISH-" + uuid.uuid4().hex + ".json")
    _write(tmp, record)
    tmp.replace(ATTEMPT)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-approve-the-p1-12-coding-repeat-01", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_p1_12_coding_repeat_01:
        print(json.dumps(build_plan(), indent=2, ensure_ascii=False))
        return 0
    if not (args.execute and args.i_approve_the_p1_12_coding_repeat_01):
        return 2
    if Path(sys.executable).resolve() != base.EVAL_VENV_PY.resolve():
        print("REFUSED:wrong_evaluator_interpreter")
        return 3
    cfg = None
    ident = None
    try:
        cfg = base.load_config()
        ident = _identity(cfg)
        base.guarded(STATE_ROOT, new=True)
        base.guarded(APPROVAL, new=True)
        base.guarded(ATTEMPT, new=True)
        _write(APPROVAL, {"approved": True, "approved_by": "lcq",
                          "approved_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "approval_text": APPROVAL_TEXT, "checklist_identity": ident})
        _write(ATTEMPT, {"status": "started", "identity": ident,
                         "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    except Exception as exc:
        print("REFUSED:" + type(exc).__name__)
        return 3
    deadline = time.monotonic() + cfg["budget_batch"]["batch_wall_min"] * 60
    rc, detail = 5, "execution_failed"
    try:
        from .g1_02_entry import local_docker_environment
        with local_docker_environment():
            preflight = base.preflight_checks(cfg)
            if preflight["status"] != "READY":
                _write(PREFLIGHT, preflight)
                detail = "preflight_not_ready"
                _finish(detail, "failed")
                print(json.dumps({"returncode": 4, "detail": detail}))
                return 4
            docker_pre = base.docker_image_preflight(cfg, deadline=deadline)
            preflight["docker_images"] = docker_pre
            _write(PREFLIGHT, preflight)
            if docker_pre["status"] != "READY":
                detail = "docker_image_preflight_not_ready"
                _finish(detail, "failed")
                print(json.dumps({"returncode": 4, "detail": detail}))
                return 4
            credentials = base.resolve_credentials()
            runtime_factory, harness_factory, verifier_factory = base.production_factories(COLLECTION)
            output = STATE_ROOT / "batch"
            result = base.run_batch(runtime_factory, harness_factory, verifier_factory, output,
                                    config=cfg, deadline=deadline, identity=ident,
                                    credentials=credentials, collection=COLLECTION,
                                    project_root=RAW_PROJECT_ROOT)
            rc = 0 if result["status"] == "complete" and result.get("archive_status") == "complete" else 5
            detail = (f"batch_{result['status']}_executed_"
                      f"{sum(1 for a in result['attempts'] if a.get('status') == 'executed')}"
                      f"_failed_{sum(1 for a in result['attempts'] if a.get('status') == 'failed')}"
                      f"_not_executed_{sum(1 for a in result['attempts'] if a.get('status') == 'not_executed')}")
            _finish(detail, "completed" if rc == 0 else "failed")
            print(json.dumps({"returncode": rc, "detail": detail}, ensure_ascii=False))
            return rc
    except Exception as exc:
        detail = type(exc).__name__
        try:
            _finish(detail, "failed")
        except Exception:
            pass
        print(json.dumps({"returncode": 5, "detail": detail}, ensure_ascii=False))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
