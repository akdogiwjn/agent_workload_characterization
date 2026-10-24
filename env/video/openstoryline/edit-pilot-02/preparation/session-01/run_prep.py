from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
RUN = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/session-01"
IMAGE = "openstoryline-task:arm64-asr-adapted-v5-request-gated"
IMAGE_ID = "sha256:2a9c470de5fd9289cbf63dc3cc52fb34ff78c42a7eb9e9a6f0f40546ab73fc4a"
CONTAINER = "awc-os-edit-pilot-02-prep-01"
DEADLINE_S = 3600


def main() -> int:
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    preexisting = subprocess.run(
        docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if preexisting:
        raise RuntimeError(f"refusing to reuse pre-existing container {CONTAINER}")
    key_path = Path("/tmp/opencode/oskey")
    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError("registered key file was empty")

    env = os.environ.copy()
    env["DASHSCOPE_API_KEY"] = key
    env.pop("OPENSTORYLINE_TRACE_DIR", None)
    argv = docker + [
        "run", "--name", CONTAINER, "--network", "bridge", "--cpus", "4", "--memory", "8g",
        "-v", f"{RUN / 'input'}:/workspace/input:ro",
        "-v", f"{RUN / 'output'}:/workspace/output",
        "-v", f"{ROOT / 'env/video/openstoryline/OPENSTORYLINE-ENV-01/models'}:/root/.cache/modelscope:ro",
        "-e", "DASHSCOPE_API_KEY",
        "-e", "OPENSTORYLINE_MAX_LOGICAL_REQUESTS=12",
        "-e", "OPENSTORYLINE_MAX_TOKENS=32768",
        IMAGE,
        "python3", "/opt/openstoryline/openstoryline_task_entry.py",
        "--request", "/workspace/output/request.json",
    ]
    (RUN / "launch-record.json").write_text(json.dumps({
        "namespace": "OPENSTORYLINE-EDIT-PILOT-02",
        "session": 1,
        "image_tag": IMAGE,
        "image_id": IMAGE_ID,
        "container_name": CONTAINER,
        "network": "bridge (needed for registered Bailian Chat Completions route)",
        "cpus": 4,
        "memory_bytes": 8589934592,
        "request_budget": 12,
        "cumulative_observed_usage_gate": 32768,
        "max_configured_output_tokens_per_request": 4096,
        "max_wall_s": DEADLINE_S,
        "credential_source": "registered /tmp/opencode/oskey, injected as DASHSCOPE_API_KEY; value not recorded",
        "started_monotonic_ns": time.monotonic_ns(),
    }, indent=2) + "\n")

    out = (RUN / "docker-stdout.log").open("w", encoding="utf-8")
    err = (RUN / "docker-stderr.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=out, stderr=err, text=True)
    deadline = time.monotonic() + DEADLINE_S
    timed_out = False
    try:
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.25)
        if proc.poll() is None:
            timed_out = True
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    finally:
        out.close()
        err.close()
        cleanup = subprocess.run(docker + ["rm", "-f", CONTAINER], capture_output=True, text=True)
        verify = subprocess.run(docker + ["ps", "-a", "--filter", f"id={CONTAINER}", "--format", "{{.ID}}"],
                                capture_output=True, text=True)
        status = {
            "exit_code": proc.returncode,
            "timed_out": timed_out,
            "elapsed_s": round(time.monotonic() - (deadline - DEADLINE_S), 3),
            "container_rm_exit_code": cleanup.returncode,
            "container_rm_output": cleanup.stdout.strip(),
            "container_rm_error": cleanup.stderr.strip(),
            "container_absent_after_cleanup": not bool(verify.stdout.strip()),
            "finished_monotonic_ns": time.monotonic_ns(),
        }
        (RUN / "launcher-result.json").write_text(json.dumps(status, indent=2) + "\n")
    return 124 if timed_out else int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
