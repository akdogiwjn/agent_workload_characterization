from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from asr_cache_runtime import docker_asr_args, validate_host_cache

ROOT = Path("/home/lcq/agent_workload_characterization")
RUN = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-06"
PREVIOUS = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/full-chain-05"
SESSION = "offline-full-chain-dc10a6e09dbc46dda132c22d174f2345"
IMAGE = "openstoryline-task:arm64-asr-adapted-v10-prompt-path-fix"
CONTAINER = "openstoryline-offline-render-audio-01"


def main() -> int:
    files = validate_host_cache()
    RUN.mkdir(parents=True, exist_ok=False)
    (RUN / "input").mkdir()
    (RUN / "output").mkdir()
    (RUN / "config.toml").write_bytes((PREVIOUS / "config.toml").read_bytes())
    (RUN / "render_saved_timeline.py").write_bytes(
        Path(__file__).with_name("render_saved_timeline.py").read_bytes())
    (RUN / "input/source.mp4").write_bytes((PREVIOUS / "input/source.mp4").read_bytes())
    shutil.copytree(PREVIOUS / "output" / SESSION, RUN / "output" / SESSION)
    shutil.copytree(PREVIOUS / "output/.server_cache", RUN / "output/.server_cache")
    (RUN / "launch-record.json").write_text(json.dumps({
        "image": IMAGE, "container": CONTAINER, "network": "none",
        "limits": {"cpus": 4, "memory": "8GiB"}, "session_id": SESSION,
        "continued_from": "preparation/full-chain-05/output",
        "tool_call": "render_video only",
        "render_include_video_audio": True, "video_volume_scale": 1.0,
        "asr_invocations": 0, "model_requests": 0,
        "started_monotonic_ns": time.monotonic_ns(),
    }, indent=2) + "\n")

    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    existing = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$",
                                         "--format", "{{.ID}}"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if existing:
        raise RuntimeError(f"refusing to reuse existing container {CONTAINER}")
    cmd = docker + [
        "run", "--rm", "--name", CONTAINER, "--network=none", "--cpus=4", "--memory=8g",
        "--mount", f"type=bind,src={RUN / 'input'},dst=/workspace/input,readonly",
        "--mount", f"type=bind,src={RUN / 'output'},dst=/workspace/output",
        "--mount", f"type=bind,src={RUN},dst=/workspace/validation,readonly",
        *docker_asr_args(), "--entrypoint", "python3", IMAGE,
        "/workspace/validation/render_saved_timeline.py",
    ]
    stdout = (RUN / "container-stdout.log").open("x", encoding="utf-8")
    stderr = (RUN / "container-stderr.log").open("x", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, text=True)
    deadline = time.monotonic() + 600
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
        remaining = subprocess.run(docker + ["ps", "-a", "--filter", f"name=^{CONTAINER}$",
                                              "--format", "{{.ID}}"],
                                   capture_output=True, text=True)
        (RUN / "launcher-result.json").write_text(json.dumps({
            "exit_code": proc.returncode, "timed_out": timed_out,
            "container_absent_after_cleanup": not bool(remaining.stdout.strip()),
            "finished_monotonic_ns": time.monotonic_ns(),
        }, indent=2) + "\n")
    return 124 if timed_out else int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
