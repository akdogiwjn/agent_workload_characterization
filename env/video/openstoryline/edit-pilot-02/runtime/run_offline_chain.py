from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from asr_cache_runtime import docker_asr_args, validate_host_cache

ROOT = Path("/home/lcq/agent_workload_characterization")
RUN = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-04"
IMAGE = "openstoryline-task:arm64-asr-adapted-v9-asr-cache-preflight"
CONTAINER = "openstoryline-offline-full-chain-cache-01"


def main() -> int:
    cache_files = validate_host_cache()
    RUN.mkdir(parents=True, exist_ok=False)
    (RUN / "input").mkdir()
    (RUN / "output").mkdir()
    previous = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-03"
    for name in ("source.mp4",):
        (RUN / "input" / name).write_bytes((previous / "input" / name).read_bytes())
    for name in ("config.toml", "validate_full_chain.py"):
        (RUN / name).write_bytes((previous / name).read_bytes())

    base = ["docker", "--host", "unix:///var/run/docker.sock"]
    exists = subprocess.run(base + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    if exists:
        raise RuntimeError(f"refusing to reuse existing container {CONTAINER}")

    cmd = base + [
        "run", "--rm", "--name", CONTAINER, "--network=none", "--cpus=4", "--memory=8g",
        "--mount", f"type=bind,src={RUN / 'input'},dst=/workspace/input,readonly",
        "--mount", f"type=bind,src={RUN / 'output'},dst=/workspace/output",
        "--mount", f"type=bind,src={RUN},dst=/workspace/validation,readonly",
        *docker_asr_args(),
        "--entrypoint", "python3", IMAGE,
        "/workspace/validation/validate_full_chain.py",
    ]
    (RUN / "host-cache-preflight.json").write_text(json.dumps({
        "status": "PASS", "host_cache_root": str(ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/models"),
        "container_mount": "/root/.cache/modelscope:ro", "required_files": cache_files,
    }, indent=2) + "\n")
    (RUN / "launch-record.json").write_text(json.dumps({
        "image": IMAGE, "container": CONTAINER, "network": "none", "cpus": 4,
        "memory_bytes": 8589934592, "credentials_read": False,
        "model_api_calls": 0, "cache_mount_contract": "OPENSTORYLINE-ENV-01/asr-cache-contract.json",
        "started_monotonic_ns": time.monotonic_ns(),
    }, indent=2) + "\n")
    stdout = (RUN / "container-stdout.log").open("x", encoding="utf-8")
    stderr = (RUN / "container-stderr.log").open("x", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, text=True)
    deadline = time.monotonic() + 2700
    timed_out = False
    try:
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(.25)
        if proc.poll() is None:
            timed_out = True
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    finally:
        stdout.close()
        stderr.close()
        subprocess.run(base + ["rm", "-f", CONTAINER], capture_output=True, text=True)
        remaining = subprocess.run(base + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                                   capture_output=True, text=True)
        (RUN / "launcher-result.json").write_text(json.dumps({
            "exit_code": proc.returncode, "timed_out": timed_out,
            "container_absent_after_cleanup": not bool(remaining.stdout.strip()),
            "finished_monotonic_ns": time.monotonic_ns(),
        }, indent=2) + "\n")
    return 124 if timed_out else int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
