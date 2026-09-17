"""RUN-02-R1 thin namespace wrapper.

This module reuses the RUN-02 runner and changes only the fixed approval,
attempt, and preflight-evidence namespace.  It never falls back to the
original RUN-02 approval or marker.
"""

from __future__ import annotations

import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from . import run_02_entry as core

PROJECT_ROOT = core.PROJECT_ROOT
R1_ROOT = PROJECT_ROOT / "reports/resource/RUN-02/retries/R1"
R1_APPROVAL = R1_ROOT / "APPROVAL.txt"
R1_MARKER = R1_ROOT / "ATTEMPT_STARTED.json"
R1_PREFLIGHT = R1_ROOT / "PREFLIGHT.json"
OLD_APPROVAL = PROJECT_ROOT / "reports/resource/RUN-02/APPROVAL.txt"
OLD_MARKER = PROJECT_ROOT / "reports/resource/RUN-02/ATTEMPT_STARTED.json"
OLD_PREFLIGHT = PROJECT_ROOT / "reports/resource/RUN-02/PREFLIGHT_DIAGNOSTIC.json"

R1_IDENTITY_EXTRAS = {
    "attempt_label": "RUN-02-R1",
    "parent_failure": {
        "collection": "RUN-02",
        "approval_path": str(OLD_APPROVAL),
        "approval_sha256": "cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a",
        "marker_path": str(OLD_MARKER),
        "marker_sha256": "8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437",
        "preflight_path": str(OLD_PREFLIGHT),
        "preflight_sha256": "ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc",
    },
    "r1_paths": {
        "approval": str(R1_APPROVAL),
        "attempt_marker": str(R1_MARKER),
        "preflight_evidence": str(R1_PREFLIGHT),
        "raw": "data/raw/generated/RUN-02/<new_run_id>",
        "report": "reports/resource/RUN-02/<new_run_id>",
    },
    "approval": str(R1_APPROVAL),
    "output": {
        "raw": "data/raw/generated/RUN-02/<new_run_id>",
        "report": "reports/resource/RUN-02/<new_run_id>",
    },
    "execution_permission": {
        "tool_execution_permission": "pending",
        "required": "single command in an approved environment with access to unix:///var/run/docker.sock",
        "no_alternatives": ["chmod", "sudo", "remote_docker", "global_sandbox_disable"],
    },
    "entry_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "support_code_sha256": {
        "runners/report_writer.py": hashlib.sha256(
            (Path(__file__).with_name("report_writer.py")).read_bytes()
        ).hexdigest(),
    },
}


@contextmanager
def _r1_configuration():
    saved = (core.APPROVAL_PATH, core.ATTEMPT_MARKER_PATH,
             core.PREFLIGHT_EVIDENCE_PATH, core.IDENTITY_EXTRAS)
    core.APPROVAL_PATH = R1_APPROVAL
    core.ATTEMPT_MARKER_PATH = R1_MARKER
    core.PREFLIGHT_EVIDENCE_PATH = R1_PREFLIGHT
    core.IDENTITY_EXTRAS = R1_IDENTITY_EXTRAS
    try:
        yield
    finally:
        (core.APPROVAL_PATH, core.ATTEMPT_MARKER_PATH,
         core.PREFLIGHT_EVIDENCE_PATH, core.IDENTITY_EXTRAS) = saved


def build_plan() -> dict:
    with _r1_configuration():
        plan = core.build_plan()
    plan["entry"]["module"] = __name__
    plan["entry"]["plan_command"] = (
        "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python "
        "-m agent_workload_characterization.runners.run_02_r1_entry")
    plan["entry"]["execute_command"] = (
        "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python "
        "-m agent_workload_characterization.runners.run_02_r1_entry "
        "--execute --i-approve-the-run-02-r1")
    plan["authorization"] = {
        "user_approval": "pending",
        "tool_execution_permission": "pending",
        "execution": False,
    }
    return plan


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--execute" not in argv:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    if "--i-approve-the-run-02-r1" in argv:
        argv[argv.index("--i-approve-the-run-02-r1")] = "--i-approve-the-run-02"
    with _r1_configuration():
        return core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
