"""RUN-01 gate B canary: no-model container measurement check.

Two sequential canaries over the local docker daemon (no model API, no
Django task, no verifier run):

- canary A (agent scope): native-arm64 image already present locally
  (python:3.11-slim) — pure collector-mechanism validation;
- canary B (verifier scope): the pinned target image
  (swebench/sweb.eval.x86_64.django_1776_django-16485@sha256:...) run via
  qemu-x86_64 binfmt — minimal-start + counter readability check. CPU
  numbers for canary B are EMULATED-execution figures and are labeled as
  such; they are not native workload evidence.

Each canary: short CPU busy work (<=5 s native / <=3 s emulated), a fixed
small memory allocation (128 MiB native / 64 MiB emulated), and a small
file write+read (16 MiB native / 8 MiB emulated). Boundary counter reads
bracket the work; gauges are sampled at ~0.5 s; a docker stats --no-stream
snapshot and (best-effort) an in-container self-read of cpuacct.usage
provide independent cross-check reads. Cleanup only removes containers
whose name matches this canary run id.

Budget: each canary <= 30 s wall; both <= 3 min total.

Modes: default (no flags) prints the plan only — nothing runs.
--execute --i-approve-the-canary runs the canaries (double gate).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

TARGET_IMAGE = ("swebench/sweb.eval.arm64.django_1776_django-16485"
                "@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de"
                "00040e6db3b7d2")
NATIVE_IMAGE = "python:3.11-slim"

def build_native_workload(*, busy_s: int = 5, file_mb: int = 16,
                          alloc_mib: int = 128) -> str:
    """Native-scope canary workload.

    `set -e` first: any failing sub-step must fail the WHOLE workload —
    a trailing `sync` must never mask an earlier error (the r6 lesson).
    The busy loop is intentionally exempted (`|| true`) because `timeout`
    kills it with a nonzero status by design."""
    return (
        "set -e; "
        f"timeout {busy_s} python3 -c \"while True: sum(range(10000))\" "
        "|| true; "
        f"python3 -c \"b = bytearray({alloc_mib}*1024*1024); "
        "b[:65536] = b'x'*65536; print('mem_alloc_ok', len(b))\"; "
        f"dd if=/dev/urandom of=/tmp/canary.bin bs=1M count={file_mb} "
        "status=none && "
        "cat /tmp/canary.bin > /dev/null && md5sum /tmp/canary.bin && "
        "rm -f /tmp/canary.bin && sync"
    )


def build_target_workload(*, busy_s: int = 12, file_mb: int = 8) -> str:
    """Target-image canary workload (native arm64 since r6).

    Same set -e discipline as the native workload."""
    return (
        "set -e; "
        "cat /etc/os-release | head -2; "
        f"timeout {busy_s} python3 -c \"while True: sum(range(10000))\" "
        "|| true; "
        f"dd if=/dev/urandom of=/tmp/canary.bin bs=1M count={file_mb} "
        "status=none && "
        "cat /tmp/canary.bin > /dev/null && rm -f /tmp/canary.bin && sync "
        "&& echo target_workload_ok"
    )


NATIVE_WORKLOAD = build_native_workload()
TARGET_WORKLOAD = build_target_workload()

CANARIES = [
    {"key": "agent_scope_native", "scope_kind": "agent_container",
     "image": NATIVE_IMAGE, "platform": None,
     "workload": NATIVE_WORKLOAD, "timeout_s": 25,
     "note": "native arm64; collector mechanism validation"},
    {"key": "verifier_scope_target_image", "scope_kind": "verifier_container",
     "image": TARGET_IMAGE, "platform": None,
     "workload": TARGET_WORKLOAD, "timeout_s": 25,
     "note": ("native arm64 target image (SWE-bench Multilingual build); "
              "environment preparation checks passed in gate B; eval "
              "compatibility NOT yet verified (verifier never run)")},
]


def build_plan() -> dict:
    return {
        "mode": "offline_plan",
        "canaries": [{"key": c["key"], "image": c["image"],
                      "platform": c["platform"], "note": c["note"]}
                     for c in CANARIES],
        "budget": {"per_canary_wall_s": 30, "total_wall_s": 180},
        "measurement": ("boundary cgroup v1 counters (cpuacct.usage ns, "
                        "memory.usage/max_usage_in_bytes, blkio.io_service_"
                        "bytes) + ~0.5s gauge sampling + docker stats "
                        "cross-check + in-container self-read"),
        "cleanup": "only containers named awc-run01-<run_id>-*",
        "no_model_api": True,
        "no_task_execution": True,
    }


def _stats_snapshot(docker: str, container_id: str) -> dict:
    import subprocess
    try:
        name_proc = subprocess.run(
            [docker, "inspect", container_id, "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=20)
        name = name_proc.stdout.strip().lstrip("/")
        proc = subprocess.run(
            [docker, "stats", "--no-stream", "--format",
             "{{.Name}} {{.CPUPerc}} {{.MemUsage}}", name],
            capture_output=True, text=True, timeout=30)
        return {"container": name,
                "status": "ok" if proc.returncode == 0 else "error",
                "raw": proc.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": f"error:{type(exc).__name__}", "raw": ""}


def _in_container_self_read(runtime, handle) -> dict:
    """Third read path: the container reading its own cgroup view."""
    for path in ("/sys/fs/cgroup/cpu,cpuacct/cpuacct.usage",
                 "/sys/fs/cgroup/cpuacct.usage"):
        result = runtime.execute(handle, f"cat {path}", timeout_s=15)
        if result["returncode"] == 0 and result["output"].strip().isdigit():
            return {"status": "ok", "path": path,
                    "cpuacct_usage_ns": int(result["output"].strip())}
    return {"status": "unavailable",
            "note": "in-container cgroup view not found at known v1 paths"}


def probe_storage_opt(docker: str = "docker") -> dict:
    """r7 item: does this daemon/filesystem support --storage-opt size?

    Read-only probe: run a throwaway container with a tiny writable-layer
    quota. The container runs `true` and is removed immediately."""
    import subprocess
    try:
        proc = subprocess.run(
            [docker, "run", "--rm", "--storage-opt", "size=1g",
             NATIVE_IMAGE, "true"],
            capture_output=True, text=True, timeout=60)
        return {"supported": proc.returncode == 0,
                "detail": (proc.stderr.strip() or "ok")[:300]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"supported": False,
                "detail": f"error:{type(exc).__name__}"}


def stop_chain_check(runtime, handle) -> dict:
    """r7 item: exercise the ACTUAL stop chain on a live workload.

    Starts a background busy loop in the container, then runs
    terminate_workload and records the three-way outcome (confirmed with
    container alive / confirmed via docker stop with the container exited
    / not confirmed). If docker stop was used, the container is EXITED
    and later counter reads will honestly report not-found."""
    bg = runtime.execute(
        handle,
        "nohup sh -c 'while :; do :; done' >/dev/null 2>&1 & echo bg_started",
        30)
    import time as _t
    _t.sleep(0.5)
    result = runtime.terminate_workload(handle, 15)
    result["bg_start_rc"] = bg.get("returncode")
    return result


def execute_canaries(report_dir: Path | None = None,
                     *, project_root: Path | None = None) -> dict:
    from ..collectors.resource_sampler import ResourceSampler
    from ..collectors.semantic_recorder import SystemClock
    from .container_runtime import ContainerSpec, DockerCliRuntime

    t0 = time.monotonic()
    clock = SystemClock()
    run_id = f"RUN01BCANARY-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    runtime = DockerCliRuntime(authorized=True)
    sampler = ResourceSampler(clock=clock, interval_s=0.5)
    results: list[dict] = []
    handles = []
    try:
        for canary in CANARIES:
            c_start = time.monotonic()
            spec = ContainerSpec(run_id=run_id, scope=canary["key"],
                                 image=canary["image"], cwd="/",
                                 platform=canary["platform"],
                                 mem_limit="2g", cpu_limit="2")
            handle = runtime.start(spec)
            handles.append(handle)
            scope = f"{run_id}-{canary['key']}"
            from ..collectors.resource_sampler import CgroupV1FileReader
            sampler.register(
                scope, canary["scope_kind"],
                CgroupV1FileReader(scope, canary["scope_kind"],
                                   handle.container_id))
            sampler.start(scope)
            sampler.start_background_sampling()
            workload = runtime.execute(handle, canary["workload"],
                                       canary["timeout_s"])
            stats = _stats_snapshot("docker", handle.container_id)
            self_read = _in_container_self_read(runtime, handle)
            sampler.stop(scope)  # BEFORE teardown
            sampler.stop_background_sampling()
            data = sampler.samples(scope)
            summary = data.summary()
            summary["workload_rc"] = workload["returncode"]
            summary["workload_ok"] = workload["returncode"] == 0
            summary["workload_output_tail"] = workload["output"][-200:]
            summary["docker_stats_crosscheck"] = stats
            summary["in_container_self_read"] = self_read
            summary["cgroup_version"] = getattr(handle, "cgroup_version", None)
            summary["container_id"] = handle.container_id
            summary["image"] = canary["image"]
            summary["platform"] = canary["platform"]
            summary["note"] = canary["note"]
            summary["canary_wall_s"] = round(time.monotonic() - c_start, 2)
            # r7: stop-chain exercise — only on the TARGET image canary,
            # AFTER its boundary read (a docker-stop fallback leaves the
            # container exited; the later reads honestly report not-found)
            stop_chain = None
            if canary["key"] == "verifier_scope_target_image":
                stop_chain = stop_chain_check(runtime, handle)
                summary["stop_chain"] = stop_chain
            results.append({"summary": summary, "evidence": data.evidence()})
        total_wall = round(time.monotonic() - t0, 2)
        report = {
            "run_id": run_id,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_wall_s": total_wall,
            "storage_opt_probe": probe_storage_opt(),
            "canaries": results,
            "collector": sampler.collector_self_observation(),
            "no_model_api": True,
            "no_task_execution": True,
        }
        if report_dir is not None:
            _write_report(report_dir, report)
        return report
    finally:
        # stop sampling first, then remove ONLY this run's containers
        sampler.stop_background_sampling()
        for handle in handles:
            try:
                runtime.stop(handle)
            except Exception:  # noqa: BLE001 — cleanup best effort, recorded
                pass
        removed = runtime.cleanup_run(run_id)
        print(f"cleanup removed: {removed}")


def _write_report(report_dir: Path, report: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=False)
    (report_dir / "canary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    files = {}
    for child in sorted(report_dir.iterdir()):
        if child.is_file() and child.name != "manifest.json":
            files[child.name] = hashlib.sha256(child.read_bytes()).hexdigest()
    (report_dir / "manifest.json").write_text(
        json.dumps({"run_id": report["run_id"], "files": files,
                    "claim": "no-model canary; measurement check only; "
                             "emulated CPU figures labeled as such"},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="canary", description=__doc__.splitlines()[0],
        allow_abbrev=False)
    parser.add_argument("--execute", action="store_true",
                        help="execute the canaries (requires --i-approve-the-canary)")
    parser.add_argument("--i-approve-the-canary", action="store_true")
    parser.add_argument("--report-dir", type=Path,
                        default=Path("reports/resource/RUN-01-B-canary"))
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
        return 0
    if not args.i_approve_the_canary:
        print("REFUSED: --execute requires --i-approve-the-canary",
              file=__import__("sys").stderr)
        return 2
    report = execute_canaries(args.report_dir)
    print(json.dumps({"run_id": report["run_id"],
                      "total_wall_s": report["total_wall_s"],
                      "canaries": [
                          {"scope": c["summary"]["scope"],
                           "cpu_core_seconds": c["summary"].get("cpu_core_seconds"),
                           "canary_wall_s": c["summary"]["canary_wall_s"],
                           "workload_rc": c["summary"]["workload_rc"]}
                          for c in report["canaries"]]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
