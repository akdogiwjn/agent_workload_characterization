from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from asr_cache_runtime import docker_asr_args, validate_host_cache

ROOT = Path("/home/lcq/agent_workload_characterization")
OUT = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/cache-mount-fix-01/container-preflight-01"
IMAGE = "openstoryline-task:arm64-asr-adapted-v9-asr-cache-preflight"
CONTAINER = "openstoryline-asr-cache-preflight-01"


def main() -> int:
    host_files = validate_host_cache()
    OUT.mkdir(parents=True, exist_ok=False)
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    existing = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if existing:
        raise RuntimeError(f"refusing to reuse existing container {CONTAINER}")
    code = (
        "import json,sys; from asr_adapter.cache_preflight import validate_asr_cache; "
        "records=validate_asr_cache(); "
        "assert 'torch' not in sys.modules and 'funasr' not in sys.modules; "
        "print(json.dumps({'status':'PASS','models_loaded':False,'torch_imported':False,"
        "'funasr_imported':False,'files':records}))"
    )
    cmd = docker + ["run", "--rm", "--name", CONTAINER, "--network=none", "--cpus=1", "--memory=1g",
                    *docker_asr_args(), "--entrypoint", "python3", IMAGE, "-c", code]
    (OUT / "host-cache-preflight.json").write_text(json.dumps({
        "status": "PASS", "cache_files": host_files,
        "mount": "/home/lcq/agent_workload_characterization/env/video/openstoryline/OPENSTORYLINE-ENV-01/models:/root/.cache/modelscope:ro",
    }, indent=2) + "\n")
    (OUT / "launch-record.json").write_text(json.dumps({
        "image": IMAGE, "image_id": "sha256:b428550cf7870804a3836ecc5d008d9e9597ab2c60b4df057b1aac8760e1e7ed",
        "container": CONTAINER, "network": "none", "model_loading": False,
        "model_api_calls": 0, "started_monotonic_ns": time.monotonic_ns(),
    }, indent=2) + "\n")
    stdout = (OUT / "container-stdout.log").open("x", encoding="utf-8")
    stderr = (OUT / "container-stderr.log").open("x", encoding="utf-8")
    try:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=90, check=False)
    finally:
        stdout.close()
        stderr.close()
    remaining = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                               capture_output=True, text=True)
    result = {
        "exit_code": proc.returncode,
        "container_absent_after_cleanup": not bool(remaining.stdout.strip()),
        "finished_monotonic_ns": time.monotonic_ns(),
    }
    (OUT / "launcher-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
