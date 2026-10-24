from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from asr_cache_runtime import docker_asr_args, validate_host_cache

ROOT = Path("/home/lcq/agent_workload_characterization")
RUN = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05"
PREVIOUS = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-04"
SESSION = "offline-full-chain-dc10a6e09dbc46dda132c22d174f2345"
IMAGE = "openstoryline-task:arm64-asr-adapted-v10-prompt-path-fix"
CONTAINER = "openstoryline-offline-full-chain-resume-01"


def main() -> int:
    cache_files = validate_host_cache()
    RUN.mkdir(parents=True, exist_ok=False)
    (RUN / "input").mkdir()
    (RUN / "output").mkdir()
    (RUN / "config.toml").write_bytes((PREVIOUS / "config.toml").read_bytes())
    (RUN / "continue_full_chain.py").write_bytes(Path(__file__).with_name("continue_full_chain.py").read_bytes())
    (RUN / "input/source.mp4").write_bytes((PREVIOUS / "input/source.mp4").read_bytes())
    old_store = PREVIOUS / "output" / SESSION
    old_cache = PREVIOUS / "output/.server_cache" / SESSION
    if not old_store.is_dir() or not old_cache.is_dir():
        raise RuntimeError("cannot resume: preserved load_media/split_shots/local_asr ArtifactStore is incomplete")
    shutil.copytree(old_store, RUN / "output" / SESSION)
    (RUN / "output/.server_cache").mkdir()
    shutil.copytree(old_cache, RUN / "output/.server_cache" / SESSION)

    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    existing = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if existing:
        raise RuntimeError(f"refusing to reuse existing container {CONTAINER}")
    cmd = docker + [
        "run", "--rm", "--name", CONTAINER, "--network=none", "--cpus=4", "--memory=8g",
        "--mount", f"type=bind,src={RUN / 'input'},dst=/workspace/input,readonly",
        "--mount", f"type=bind,src={RUN / 'output'},dst=/workspace/output",
        "--mount", f"type=bind,src={RUN},dst=/workspace/validation,readonly",
        *docker_asr_args(), "--entrypoint", "python3", IMAGE,
        "/workspace/validation/continue_full_chain.py",
    ]
    (RUN / "cache-preflight.json").write_text(json.dumps({
        "status": "PASS", "model_loading": False, "local_asr_repeated": False,
        "same_cache_contract_as_test_and_formal": True, "files": cache_files,
    }, indent=2) + "\n")
    (RUN / "resume-record.json").write_text(json.dumps({
        "image": IMAGE, "container": CONTAINER, "network": "none",
        "session_id": SESSION, "resumed_from": "preparation/full-chain-04/output",
        "resumed_nodes": ["load_media", "split_shots", "local_asr"],
        "continued_nodes": ["speech_rough_cut", "plan_timeline_pro", "elementrec_transition", "elementrec_text", "render_video"],
        "real_model_requests": 0, "local_asr_invocations_in_this_container": 0,
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
        subprocess.run(docker + ["rm", "-f", CONTAINER], capture_output=True, text=True)
        remaining = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.ID}}"],
                                   capture_output=True, text=True)
        (RUN / "launcher-result.json").write_text(json.dumps({
            "exit_code": proc.returncode, "timed_out": timed_out,
            "container_absent_after_cleanup": not bool(remaining.stdout.strip()),
            "finished_monotonic_ns": time.monotonic_ns(),
        }, indent=2) + "\n")
    return 124 if timed_out else int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
