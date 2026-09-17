"""RUN-02-R2 fixed namespace entry.

This is a deliberately thin adapter around the accepted RUN-02 runner.  It
binds a new approval/attempt namespace, resolves the one approved credential
reference in memory, and removes proxy/context inheritance only for this
process and its children.  It does not provide arbitrary paths or retry.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from . import run_02_entry as core
from . import smoke_launcher

PROJECT_ROOT = core.PROJECT_ROOT
R2_ROOT = PROJECT_ROOT / "reports/resource/RUN-02/retries/R2"
R2_APPROVAL = R2_ROOT / "APPROVAL.txt"
R2_MARKER = R2_ROOT / "ATTEMPT_STARTED.json"
R2_PREFLIGHT = R2_ROOT / "PREFLIGHT.json"

R1_ROOT = PROJECT_ROOT / "reports/resource/RUN-02/retries/R1"
READY_SUMMARY = PROJECT_ROOT / (
    "reports/preparation/READY-01/20260914T111017Z-7eb3c4/summary.json")
READY_MANIFEST = READY_SUMMARY.with_name("manifest.json")

R2_IDENTITY_EXTRAS = {
    "attempt_label": "RUN-02-R2",
    "parent_failure": {
        "attempt_label": "RUN-02-R1",
        "approval_path": str(R1_ROOT / "APPROVAL.txt"),
        "approval_sha256": "1f9442a7196b14a292b0b3ca1bf0f296bbfc0399328a754f754cac78aeb48d74",
        "marker_path": str(R1_ROOT / "ATTEMPT_STARTED.json"),
        "marker_sha256": "edebe9f82a3fdf91380b1c71e7c35d9954ed4fa330bd99eac9bbdec99503102d",
        "preflight_path": str(R1_ROOT / "PREFLIGHT.json"),
        "preflight_sha256": "55768beef63d97f3de6abee4facb17a23e94ba83d5c2abcb88692b65bf5ec96d",
    },
    "readiness_evidence": {
        "summary_path": str(READY_SUMMARY),
        "summary_sha256": "cc234ad87b9c00189c20f9ec8c1836a3f762aca36a9ac420b83533b323ac2a65",
        "manifest_path": str(READY_MANIFEST),
        "manifest_sha256": "af76a6e481d56488f09031eb0702780dbc928174e2998151ef2f01725a4bf942",
        "status": "READY_FOR_APPROVAL",
    },
    "r2_paths": {
        "approval": str(R2_APPROVAL),
        "attempt_marker": str(R2_MARKER),
        "preflight_evidence": str(R2_PREFLIGHT),
        "raw": "data/raw/generated/RUN-02/<new_run_id>",
        "report": "reports/resource/RUN-02/<new_run_id>",
    },
    "approval": str(R2_APPROVAL),
    "credential_route": {
        "reference": "{env:VOLCANO_API_KEY}",
        "source": str(smoke_launcher.DEFAULT_CONFIG),
        "resolved_in_memory": True,
        "runner_mapping": {"base": "OPENAI_API_BASE", "key": "OPENAI_API_KEY"},
        "proxy_policy": "clear_only_this_process_and_children",
    },
    "execution_permission": {
        "tool_execution_permission": "pending",
        "required": "single command in an approved environment with access to unix:///var/run/docker.sock",
        "no_alternatives": ["chmod", "sudo", "remote_docker", "global_sandbox_disable"],
    },
    "entry_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "support_code_sha256": {
        "runners/smoke_launcher.py": hashlib.sha256(
            Path(smoke_launcher.__file__).read_bytes()).hexdigest(),
    },
}


@contextmanager
def _r2_configuration():
    saved = (core.APPROVAL_PATH, core.ATTEMPT_MARKER_PATH,
             core.PREFLIGHT_EVIDENCE_PATH, core.IDENTITY_EXTRAS,
             core._credentials)
    core.APPROVAL_PATH = R2_APPROVAL
    core.ATTEMPT_MARKER_PATH = R2_MARKER
    core.PREFLIGHT_EVIDENCE_PATH = R2_PREFLIGHT
    core.IDENTITY_EXTRAS = R2_IDENTITY_EXTRAS
    core._credentials = _r2_credentials
    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                   "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                   "SMOKE_APPROVED_PROXY", "DOCKER_CONTEXT")
    old = {name: os.environ.get(name) for name in proxy_names}
    old_docker_host = os.environ.get("DOCKER_HOST")
    for name in proxy_names:
        os.environ.pop(name, None)
    os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    try:
        yield
    finally:
        (core.APPROVAL_PATH, core.ATTEMPT_MARKER_PATH,
         core.PREFLIGHT_EVIDENCE_PATH, core.IDENTITY_EXTRAS,
         core._credentials) = saved
        if old_docker_host is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = old_docker_host
        if old.get("DOCKER_CONTEXT") is None:
            os.environ.pop("DOCKER_CONTEXT", None)
        else:
            os.environ["DOCKER_CONTEXT"] = old["DOCKER_CONTEXT"]
        for name in proxy_names:
            if name == "DOCKER_CONTEXT":
                continue
            if old[name] is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old[name]


def _r2_credentials() -> dict[str, str]:
    # Enforce the exact approved route before invoking the compatible loader;
    # this keeps smoke launcher's broader compatibility unchanged.
    if not _selected_reference():
        raise core.Run02EntryError("RUN-02-R2 credential route is not approved")
    try:
        api_base, api_key = smoke_launcher.load_credentials(
            smoke_launcher.DEFAULT_CONFIG)
    except smoke_launcher.LauncherError as exc:
        raise core.Run02EntryError("RUN-02-R2 credentials unavailable") from exc
    restricted = smoke_launcher.build_restricted_env(api_base, api_key)
    return {core.SDK_BASE_ENV: restricted["PILOT_API_BASE"],
            core.SDK_KEY_ENV: restricted["PILOT_API_KEY"]}


def _selected_reference() -> bool:
    try:
        raw = smoke_launcher.DEFAULT_CONFIG.read_bytes()
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError:
            cfg = json.loads(smoke_launcher._strip_jsonc(raw.decode("utf-8")))
        reference = cfg["provider"][smoke_launcher.PROVIDER_NAME]["options"]["apiKey"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return False
    return reference == "{env:VOLCANO_API_KEY}"


def build_plan() -> dict:
    with _r2_configuration():
        _, identity = core.build_run02_runner(authorized=False)
    return {
        "mode": "offline_plan", "collection": "RUN-02",
        "attempt_label": "RUN-02-R2", "identity": identity,
        "entry": {
            "module": __name__, "interpreter": str(core.EVAL_VENV_PY),
            "plan_command": "PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.run_02_r2_entry",
            "execute_command": "env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u all_proxy -u no_proxy -u SMOKE_APPROVED_PROXY -u DOCKER_CONTEXT PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python -m agent_workload_characterization.runners.run_02_r2_entry --execute --i-approve-the-run-02-r2",
        },
        "authorization": {"user_approval": "pending",
                           "tool_execution_permission": "pending",
                           "execution": False},
        "side_effects": {"docker": False, "network": False, "model": False,
                          "credentials_read": False, "r2_created": False},
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--execute" not in argv:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    if "--i-approve-the-run-02-r2" not in argv:
        print("REFUSED: --execute requires the RUN-02-R2 approval flag", file=sys.stderr)
        return 2
    argv[argv.index("--i-approve-the-run-02-r2")] = "--i-approve-the-run-02"
    with _r2_configuration():
        return core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
