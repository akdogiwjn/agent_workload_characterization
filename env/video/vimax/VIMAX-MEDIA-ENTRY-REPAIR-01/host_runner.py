#!/usr/bin/env python3
"""Reusable host lifecycle for ViMax media continuation (REPAIR-01 fixed).

Derived from PILOT-03's host_runner.py with audited fixes (../FIXES.md):

1. Container stdout/stderr and Docker logs are captured from container START
   (a `docker logs --follow` thread) and re-fetched in full BEFORE container
   removal on every path — PILOT-03 deleted the container with only RC1
   left behind, losing the original stack trace.
2. Configuration via --config JSON (task id, plan dir, image identity,
   session, caps, network mode, deadlines) instead of copy-edited constants;
   future pilots reuse this exact runner and entry.
3. Injectable RuntimeOps retained for full-lifecycle offline regression
   (FakeOps drives the same code path that production uses, which catches
   dict-slice-style runtime TypeErrors that compile checks miss).
4. Independent finally blocks: log thread, netns thread, sampler, container
   stop/rm/verify; one cleanup failure never skips the others; log capture
   failure itself is recorded but never blocks cleanup.

Run modes: preflight | freeze | run | cold-start-acceptance (network-gated
full chain with the fake boundary; same runner/entry as production).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from agent_workload_characterization.collectors.execution_measurement import (  # noqa: E402
    directory_footprint_snapshot)
from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CgroupV1FileReader, ResourceSampler)

BASE = Path(__file__).resolve().parent
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
CRED = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")

DEFAULT_CONFIG = {
    "task_id": "VIMAX-MEDIA-ENTRY-REPAIR-01",
    "image": "vimax-task-bailian:arm64-v7-capability-planning-01",
    "image_id": "sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3",
    "plan_dir": str(REPO / "env/video/vimax/VIMAX-GENERATION-PILOT-02/preflight-01/staged-planning"),
    "plan_source_map": str(REPO / "env/video/vimax/VIMAX-GENERATION-PILOT-02/preflight-01/source-map.json"),
    "planning_identity": "7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2",
    "plan_run_id": "vimax-planning-validate-03-20261024T014216Z-3d8d561a",
    "session_id": "media-continuation-01",
    "source_session_id": "planning-validation-03",
    "source_script_sha256": "447e4d88ccd76f9cb4a206f799993620a3c832238dd873c9ae9e905c2452b59a",
    "shot_count": 8,
    "transition_count": 7,
    "work_seconds": 5400.0,
    "closeout_seconds": 300.0,
    "network": "bridge",          # bridge | host | none (registered per run)
    "netns_period_s": 2.0,
    "handshake_timeout_s": 45.0,
    "budget": {
        "llm_calls": 80, "llm_attempts": 80, "image_generations": 40,
        "video_creates": 15, "video_polls": 1800, "media_downloads": 80,
        "single_request_output_tokens": 8192,
        "observed_output_tokens_total": 500000,
        "deadline_seconds": 5400, "transitions": 7,
    },
    "entry_command": ["python3", "/opt/run/generation_entry.py"],
    "add_hosts": [],
    "extra_mounts": [],           # e.g. the fake boundary for the acceptance
    "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "llm_model": "qwen3.7-plus",
    "image_model": "qwen-image-3.0",
    "video_model": "wan2.6-i2v-flash",
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config(path: str | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path:
        overlay = json.loads(Path(path).read_text())
        cfg.update(overlay)
    return cfg


def run(argv, timeout=30):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(argv, 124, e.stdout or "", "TIMEOUT")


class RuntimeOps:
    """Narrow injectable process boundary; production uses exactly these."""
    run = staticmethod(run)
    popen = staticmethod(subprocess.Popen)
    sleep = staticmethod(time.sleep)
    monotonic = staticmethod(time.monotonic)
    write = staticmethod(write)
    sampler_factory = staticmethod(lambda: ResourceSampler(interval_s=0.5))
    cgroup_reader_factory = staticmethod(
        lambda run_id, cid: CgroupV1FileReader(run_id, "agent_container", cid))

    def credentials(self):
        return read_creds_and_route()

    def net_snapshot(self, cid):
        return net_snapshot(cid)


def net_snapshot(cid):
    r = run(DOCKER + ["exec", cid, "cat", "/proc/net/dev"], 10)
    ts = time.monotonic_ns()
    if r.returncode:
        return {"t_monotonic_ns": ts, "read_status": "error",
                "error": "container_netdev_read_failed"}
    interfaces = {}
    for line in r.stdout.splitlines()[2:]:
        if ":" not in line:
            continue
        name, vals = line.split(":", 1)
        nums = vals.split()
        if len(nums) >= 9:
            interfaces[name.strip()] = {"rx_bytes": int(nums[0]),
                                        "tx_bytes": int(nums[8])}
    return {"t_monotonic_ns": ts, "read_status": "ok",
            "scope": "container_netns_interfaces", "interfaces": interfaces}


def read_creds_and_route():
    values = {}
    for line in CRED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() in {"DASHSCOPE_API_KEY", "BAILIAN_WORKSPACE_ID"}:
            values[k.strip()] = v.strip().strip("\"'")
    if not values.get("DASHSCOPE_API_KEY") or not values.get("BAILIAN_WORKSPACE_ID"):
        raise RuntimeError("registered runtime credential variables are unavailable")
    host = values["BAILIAN_WORKSPACE_ID"] + ".cn-beijing.maas.aliyuncs.com"
    return values, host


def image_identity(cfg) -> dict:
    r = run(DOCKER + ["image", "inspect", cfg["image"],
                      "--format", "{{.Id}} {{.Os}} {{.Architecture}}"])
    if r.returncode:
        raise RuntimeError("registered Docker image could not be inspected")
    parts = r.stdout.strip().split()
    actual = {"id": parts[0], "platform": f"{parts[1]}/{parts[2]}"}
    if actual != {"id": cfg["image_id"], "platform": "linux/arm64"}:
        raise RuntimeError("fixed image ID/platform mismatch")
    return actual


def start_attempt(out: Path, cfg: dict, *, ops: RuntimeOps | None = None,
                  env_overlay: dict | None = None,
                  expect_complete: bool = True):
    """One bounded attempt. Production and the network-gated acceptance use
    the SAME path; the acceptance only differs by env_overlay (fake URLs,
    network=none) — the entry/runner code is identical."""
    ops = ops or RuntimeOps()
    plan = Path(cfg["plan_dir"]).resolve()
    entry = BASE / "generation_entry.py"
    work = out / "workspace"
    attempt = work / "attempt"
    attempt.mkdir(parents=True, exist_ok=True)
    if (out / "ATTEMPT-STARTED").exists():
        raise RuntimeError("attempt already started")
    t0 = ops.monotonic()
    run_id = cfg["task_id"].lower() + "-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    work_deadline = t0 + cfg["work_seconds"]
    close_deadline = work_deadline + cfg["closeout_seconds"]
    record = {"task": cfg["task_id"], "run_id": run_id, "attempt": 1, "retry": 0,
              "started_utc": now(), "t0_monotonic": t0,
              "image": image_identity(cfg),
              "generation_entry_sha256": sha(entry),
              "host_runner_sha256": sha(Path(__file__).resolve()),
              "network_mode": cfg["network"],
              "phase_boundaries": {}, "termination": "starting",
              "cleanup_errors": [], "startup_gate": {},
              "http_exchange_count": "unknown"}
    errors = record["cleanup_errors"]
    try:
        record["dir_before"] = directory_footprint_snapshot([
            {"role": "workspace", "path": str(work), "ownership": "host_bound_output"},
            {"role": "attempt", "path": str(attempt), "ownership": "host_bound_output"},
        ], timeout_s=5.0)
    except Exception as exc:  # noqa: BLE001
        errors.append("dir_before:" + type(exc).__name__)
    sampler = ops.sampler_factory()
    sampler_started = False
    sampler_background = False
    cid = ""
    stop = threading.Event()
    net_rows = []
    net_lock = threading.Lock()
    net_thread = None
    log_thread = None
    log_proc = None
    log_stop = threading.Event()
    log_path = out / "container-stdout.log"

    def persist():
        try:
            ops.write(out / "run-record.json", record)
            return True
        except Exception as exc:  # noqa: BLE001
            errors.append("run_record_write:" + type(exc).__name__)
            return False

    def checkpoint():
        if not persist():
            raise OSError("required host state record could not be persisted")

    def close_run(argv, timeout):
        remaining = close_deadline - ops.monotonic()
        if remaining <= 0:
            errors.append("closeout_deadline_exhausted")
            return subprocess.CompletedProcess(argv, 124, "", "closeout exhausted")
        return ops.run(argv, min(float(timeout), remaining))

    try:
        checkpoint()
        creds, host = ops.credentials()
        b = cfg["budget"]
        env = {
            "HOME": "/tmp", "PYTHONPATH": "/opt/vimax/src:/opt/run",
            "VIMAX_LLM_MODEL": cfg["llm_model"],
            "VIMAX_LLM_MODEL_PROVIDER": "openai",
            "VIMAX_LLM_BASE_URL": cfg["llm_base_url"],
            "VIMAX_LLM_API_KEY": creds["DASHSCOPE_API_KEY"],
            "VIMAX_AGENT_MAX_TOKENS": "8192",
            "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
            "VIMAX_IMAGE_MODEL": cfg["image_model"],
            "VIMAX_IMAGE_BASE_URL": f"https://{host}/compatible-mode/v1",
            "VIMAX_IMAGE_API_KEY": creds["DASHSCOPE_API_KEY"],
            "VIMAX_VIDEO_MODEL": cfg["video_model"],
            "VIMAX_VIDEO_BASE_URL": f"https://{host}",
            "VIMAX_VIDEO_API_KEY": creds["DASHSCOPE_API_KEY"],
            "VIMAX_BAILIAN_EVENT_LOG": "/workspace/attempt/model-events.jsonl",
            "VIMAX_BAILIAN_BUDGET_LLM_CALLS": str(b["llm_calls"]),
            "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": str(b["llm_attempts"]),
            "VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS": str(b["image_generations"]),
            "VIMAX_BAILIAN_BUDGET_VIDEO_CREATES": str(b["video_creates"]),
            "VIMAX_BAILIAN_BUDGET_TRANSITIONS": str(b["transitions"]),
            "VIMAX_BAILIAN_BUDGET_VIDEO_POLLS": str(b["video_polls"]),
            "VIMAX_BAILIAN_BUDGET_MEDIA_DOWNLOADS": str(b["media_downloads"]),
            "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS":
                str(b["single_request_output_tokens"]),
            "VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL":
                str(b["observed_output_tokens_total"]),
            "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS": str(b["deadline_seconds"]),
            "VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS": "10",
            "VIMAX_BAILIAN_VIDEO_QUERY_TIMEOUT_SECONDS": "900",
            "VIMAX_BAILIAN_VIDEO_DURATION": "5",
            "VIMAX_BAILIAN_VIDEO_RESOLUTION": "720P",
            "VIMAX_BAILIAN_VIDEO_AUDIO": "false",
            "VIMAX_BAILIAN_VIDEO_PROMPT_EXTEND": "false",
            "VIMAX_BAILIAN_VIDEO_CREATE_TIMEOUT_SECONDS": "60",
            "VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS": "2",
            "VIMAX_IMAGE_NUM_CANDIDATES": "2",
            "VIMAX_VIDEO_CAPABILITY_PROFILE": "bailian-wan26-i2v-first-frame",
            "VIMAX_ENABLE_RUN_SHELL": "0",
            "VIMAX_MEDIA_SESSION_ID": cfg["session_id"],
            "VIMAX_MEDIA_SOURCE_SESSION": cfg["source_session_id"],
            "VIMAX_MEDIA_SOURCE_SCRIPT_SHA256": cfg["source_script_sha256"],
            "VIMAX_MEDIA_SHOT_COUNT": str(cfg["shot_count"]),
            "VIMAX_STARTUP_GATE_REQUIRED": "1",
            "VIMAX_STARTUP_HANDSHAKE_TIMEOUT_SECONDS": str(cfg["handshake_timeout_s"]),
        }
        if env_overlay:
            env.update(env_overlay)
        container_name = cfg["task_id"].lower() + "-" + uuid.uuid4().hex[:10]
        args = DOCKER + ["run", "-d", "--name", container_name,
                         "--label", f"org.agent-workload.task={run_id}",
                         "--network", cfg["network"],
                         "--read-only",
                         "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
                         "--memory", "8g", "--cpus", "8",
                         "--cpuset-cpus", "0-7", "--pids-limit", "512",
                         "--user", f"{os.getuid()}:{os.getgid()}",
                         "--workdir", "/workspace",
                         "--mount", f"type=bind,source={work},target=/workspace",
                         "--mount", f"type=bind,source={plan},target=/planning,readonly",
                         "--mount", f"type=bind,source={entry},target=/opt/run/generation_entry.py,readonly"]
        for m in cfg.get("extra_mounts", []):
            args += ["--mount", m]
        for ah in cfg.get("add_hosts", []):
            args += ["--add-host", ah]
        for k, v in env.items():
            args += ["-e", f"{k}={v}"]
        args += [cfg["image"]] + list(cfg.get("entry_command",
                                              ["python3", "/opt/run/generation_entry.py"]))
        try:
            started = ops.run(args, 60)
        finally:
            creds.clear()
            args.clear()
            env.clear()
        if started.returncode:
            raise RuntimeError("container start failed; sensitive output suppressed")
        cid = started.stdout.strip()
        if not cid:
            raise RuntimeError("docker start returned no container ID")
        record["container"] = {"name": container_name, "id": cid}
        record["termination"] = "container_started"
        record["phase_boundaries"]["container_start"] = {"monotonic": ops.monotonic()}
        checkpoint()

        # ---- log capture from container START (PILOT-03 audit fix) --------
        def log_follow():
            nonlocal log_proc
            try:
                log_proc = ops.popen(
                    DOCKER + ["logs", "-f", "--timestamps", cid],
                    stdout=open(log_path, "w", encoding="utf-8"),
                    stderr=subprocess.STDOUT)
                log_proc.wait()
            except Exception as exc:  # noqa: BLE001
                errors.append("log_follow:" + type(exc).__name__)
        log_thread = threading.Thread(target=log_follow, daemon=True)
        log_thread.start()

        owned = ops.run(DOCKER + ["inspect", "-f",
                                  '{{index .Config.Labels "org.agent-workload.task"}}',
                                  cid], 10)
        if owned.returncode or owned.stdout.strip() != run_id:
            raise RuntimeError("container ownership verification failed")
        record["container"]["ownership_verified"] = True
        record["phase_boundaries"]["ownership_verified"] = {"monotonic": ops.monotonic()}
        checkpoint()

        sampler.register(run_id, "agent_container",
                         ops.cgroup_reader_factory(run_id, cid))
        sampler.start(run_id)
        try:
            sampler.enable_stream(run_id, out / "samples" / "resource-stream.jsonl")
            bs = sampler.samples(run_id).boundary_start
            write(out / "samples" / "boundaries.json",
                  {"schema": "resource-boundaries-v1",
                   "boundary_start": bs.to_dict() if bs else None,
                   "utc_start": now()})
        except Exception as exc:  # noqa: BLE001
            errors.append("stream_init:" + type(exc).__name__)
        sampler_started = True
        sampler.start_background_sampling()
        sampler_background = True
        baseline = sampler.samples(run_id).boundary_start
        if baseline is None or baseline.cpu_usage_usec is None \
                or baseline.mem_current_bytes is None:
            raise RuntimeError("cgroup baseline unavailable; startup blocked")
        sampler_deadline = min(work_deadline, ops.monotonic() + 5.0)
        sample_ready = False
        while ops.monotonic() < sampler_deadline:
            try:
                samples = sampler.samples(run_id).samples
                if samples and samples[-1].cpu_usage_usec is not None \
                        and samples[-1].mem_current_bytes is not None:
                    sample_ready = True
                    break
            except Exception:  # noqa: BLE001
                pass
            ops.sleep(0.05)
        if not sample_ready:
            raise TimeoutError("sampler did not read CPU and memory before release")
        record["startup_gate"]["sampling_ready"] = True
        record["phase_boundaries"]["sampling_ready"] = {"monotonic": ops.monotonic()}
        checkpoint()

        net_stream_path = out / "samples" / "netns-stream.jsonl"
        net_stream_path.parent.mkdir(parents=True, exist_ok=True)
        net_stream_fh = net_stream_path.open("a", encoding="utf-8", newline="\n")

        def netloop():
            deadline = ops.monotonic()
            while not stop.is_set():
                t0 = ops.monotonic()
                snap_row = ops.net_snapshot(cid)
                t1 = ops.monotonic()
                snap_row["t_monotonic_ns"] = snap_row.get("t_monotonic_ns") or int(t0 * 1e9)
                snap_row["read_end_monotonic_ns"] = int(t1 * 1e9)
                snap_row["read_wall_ns"] = int((t1 - t0) * 1e9)
                snap_row["schema"] = "netns-stream-v1"
                snap_row["utc"] = now()
                with net_lock:
                    net_rows.append(snap_row)
                    try:
                        net_stream_fh.write(json.dumps(snap_row, ensure_ascii=False) + "\n")
                        net_stream_fh.flush()
                    except Exception as exc:  # noqa: BLE001
                        errors.append("net_stream_write:" + type(exc).__name__)
                deadline += cfg["netns_period_s"]
                stop.wait(max(0, deadline - ops.monotonic()))

        first_net = ops.net_snapshot(cid)
        if first_net.get("read_status") != "ok":
            raise RuntimeError("container netns sample not readable before release")
        net_rows.append(first_net)
        net_thread = threading.Thread(target=netloop, daemon=True)
        net_thread.start()

        wait_for_marker(attempt / "STARTUP-READY.json",
                        min(work_deadline, ops.monotonic() + cfg["handshake_timeout_s"]),
                        ops, cid, run_id)
        record["startup_gate"]["ready"] = True
        record["phase_boundaries"]["container_ready"] = {"monotonic": ops.monotonic()}
        checkpoint()
        ops.write(attempt / "STARTUP-RELEASE.json",
                  {"state": "released_after_ownership_and_sampler",
                   "t_monotonic": ops.monotonic()})
        record["startup_gate"]["released"] = True
        record["phase_boundaries"]["startup_released"] = {"monotonic": ops.monotonic()}
        checkpoint()
        wait_for_marker(attempt / "STARTUP-ACK.json",
                        min(work_deadline, ops.monotonic() + 10.0), ops, cid, run_id)
        record["startup_gate"]["acknowledged"] = True
        checkpoint()

        complete = attempt / "COMPLETE"
        while ops.monotonic() < work_deadline:
            if complete.is_file():
                record["termination"] = "native_agent_done"
                break
            state = ops.run(DOCKER + ["inspect", "-f", "{{.State.Running}}", cid], 8)
            if state.returncode == 0 and state.stdout.strip() == "false":
                record["termination"] = "container_exited_without_complete"
                break
            if state.returncode != 0:
                raise RuntimeError("container state became unavailable")
            ops.sleep(0.5)
        else:
            record["termination"] = "work_deadline"
        record["phase_boundaries"]["agent_work"] = {
            "start_monotonic": record["phase_boundaries"].get(
                "startup_released", {}).get("monotonic"),
            "end_monotonic": ops.monotonic(),
            "deadline_reached": record["termination"] == "work_deadline"}
        checkpoint()
        if record["termination"] == "work_deadline":
            ops.run(DOCKER + ["kill", cid], 10)
    except BaseException as exc:  # noqa: BLE001
        record["termination"] = "runner_exception"
        record["primary_error"] = {"type": type(exc).__name__,
                                   "message": str(exc)[:500]}
    finally:
        # ---- independent finally blocks (one failure never skips others) ---
        if cid and not record.get("startup_gate", {}).get("released"):
            try:
                ops.write(attempt / "STARTUP-ABORT.json",
                          {"state": "aborted_before_release",
                           "reason": (record.get("primary_error") or {})
                           .get("type", "host_closeout")})
            except Exception as exc:  # noqa: BLE001
                errors.append("startup_abort_write:" + type(exc).__name__)
        stop.set()
        if net_thread:
            net_thread.join(timeout=10)
            if net_thread.is_alive():
                errors.append("netns_sampler_thread_join_timeout")
        try:
            net_stream_fh.close()
        except Exception as exc:  # noqa: BLE001
            errors.append("net_stream_close:" + type(exc).__name__)
        if cid:
            try:
                final_net = ops.net_snapshot(cid)
                with net_lock:
                    net_rows.append(final_net)
                record["phase_boundaries"]["netns_final_boundary"] = {
                    "t_monotonic_ns": final_net.get("t_monotonic_ns"),
                    "read_status": final_net.get("read_status")}
            except Exception as exc:  # noqa: BLE001
                errors.append("netns_final_boundary:" + type(exc).__name__)
        if sampler_started:
            try:
                if sampler_background:
                    sampler.stop_background_sampling()
                sampler.stop(record["run_id"])
            except Exception as exc:  # noqa: BLE001
                errors.append("sampler_stop:" + type(exc).__name__)
            try:
                sampler.close_streams()
                be = sampler.samples(run_id).boundary_end
                bf = out / "samples" / "boundaries.json"
                if bf.exists():
                    bd = json.loads(bf.read_text())
                    bd["boundary_end"] = be.to_dict() if be else None
                    bd["utc_end"] = now()
                    write(bf, bd)
            except Exception as exc:  # noqa: BLE001
                errors.append("stream_close:" + type(exc).__name__)
        if cid:
            try:
                if record["termination"] in ("native_agent_done",
                                             "container_exited_without_complete"):
                    record["phase_boundaries"]["agent_stop"] = {
                        "monotonic": ops.monotonic()}
                close_run(DOCKER + ["stop", "-t", "15", cid], 20)
                waited = close_run(DOCKER + ["wait", cid], 15)
                record["container_exit_code"] = (
                    int(waited.stdout.strip())
                    if waited.returncode == 0 and waited.stdout.strip().isdigit()
                    else None)
                # ---- full log re-fetch BEFORE removal (PILOT-03 audit fix) --
                try:
                    logs = close_run(DOCKER + ["logs", "--timestamps", cid], 20)
                    if logs.returncode == 0:
                        (out / "container-logs-final.log").write_text(
                            logs.stdout, encoding="utf-8")
                    else:
                        errors.append("docker_logs_prefetch:" + str(logs.returncode))
                except Exception as exc:  # noqa: BLE001
                    errors.append("docker_logs_prefetch:" + type(exc).__name__)
                rm = close_run(DOCKER + ["rm", "-f", cid], 20)
                record["container_rm_returncode"] = rm.returncode
                record["container_removed_verified"] = \
                    close_run(DOCKER + ["inspect", cid], 8).returncode != 0
                if not record["container_removed_verified"]:
                    errors.append("container_removal_not_verified")
                try:
                    record["dir_after"] = directory_footprint_snapshot([
                        {"role": "workspace", "path": str(work), "ownership": "host_bound_output"},
                        {"role": "attempt", "path": str(attempt), "ownership": "host_bound_output"},
                    ], timeout_s=5.0)
                except Exception as exc:  # noqa: BLE001
                    errors.append("dir_after:" + type(exc).__name__)
            except Exception as exc:  # noqa: BLE001
                errors.append("container_cleanup:" + type(exc).__name__)
        # stop the log follow thread AFTER container removal (logs -f exits)
        log_stop.set()
        if log_proc is not None:
            try:
                log_proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        if log_thread:
            log_thread.join(timeout=10)
            if log_thread.is_alive():
                errors.append("log_follow_thread_join_timeout")
        record["phase_boundaries"]["closeout_end_monotonic"] = ops.monotonic()
        record["total_wall_s"] = ops.monotonic() - t0
        record["attempt_wall_s"] = record["total_wall_s"]
        if sampler_started:
            try:
                evidence = sampler.all_scope_evidence()
                write(out / "resource-evidence.json", evidence)
                samples = evidence.get(record["run_id"], {}).get("samples", [])
                (out / "resource-samples.jsonl").write_text(
                    "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in samples))
                record["resource_summary"] = sampler.all_scope_summaries()
            except Exception as exc:  # noqa: BLE001
                errors.append("resource_export:" + type(exc).__name__)
        with net_lock:
            nrows = list(net_rows)
        try:
            (out / "netns-samples.jsonl").write_text(
                "".join(json.dumps(x) + "\n" for x in nrows))
        except Exception as exc:  # noqa: BLE001
            errors.append("netns_write:" + type(exc).__name__)
        if (attempt / "COMPLETE").exists():
            try:
                record["agent_complete"] = json.loads(
                    (attempt / "COMPLETE").read_text())
            except Exception:  # noqa: BLE001
                record["agent_complete"] = "corrupt"
        if (attempt / "ENTRY-FAILED.json").exists():
            try:
                record["entry_failure"] = json.loads(
                    (attempt / "ENTRY-FAILED.json").read_text())
            except Exception:  # noqa: BLE001
                record["entry_failure"] = "corrupt"
        record["network_scope"] = ("container netns per-interface RX/TX; "
                                   "not API-specific bytes")
        persist()
    ok = record.get("termination") == "native_agent_done" and not errors
    if expect_complete is False:
        # failure-injection runs: success means the failure was HANDLED
        ok = not errors or record.get("entry_failure") or record.get("primary_error")
    return (0 if ok else 1), record


def wait_for_marker(path: Path, deadline: float, ops: RuntimeOps,
                    container_id: str, run_id: str) -> None:
    while ops.monotonic() < deadline:
        if path.is_file():
            return
        state = ops.run(DOCKER + ["inspect", "-f", "{{.State.Running}}",
                                  container_id], 5)
        if state.returncode == 0 and state.stdout.strip() == "false":
            raise RuntimeError("container exited before startup handshake marker")
        if state.returncode != 0:
            raise RuntimeError("container status unavailable during startup handshake")
        ops.sleep(0.05)
    raise TimeoutError("startup handshake marker timed out")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("run", "cold-start-acceptance"))
    p.add_argument("--out", required=True)
    p.add_argument("--config")
    p.add_argument("--env-overlay", help="JSON file with env overrides "
                                         "(fake URLs for the acceptance run)")
    a = p.parse_args()
    out = Path(a.out).resolve()
    if out.exists():
        raise SystemExit(f"refusing: output directory exists: {out}")
    out.mkdir(parents=True)
    cfg = load_config(a.config)
    overlay = json.loads(Path(a.env_overlay).read_text()) if a.env_overlay else None
    if a.mode == "cold-start-acceptance":
        cfg["network"] = "none"      # registered: acceptance is network-gated

        class AcceptanceOps(RuntimeOps):
            """The acceptance NEVER touches the registered credential file:
            the fake boundary only accepts its own synthetic key."""
            def credentials(self):
                fake = {"DASHSCOPE_API_KEY": "fake-offline-key",
                        "BAILIAN_WORKSPACE_ID": "fake-ws"}
                return fake, "127.0.0.1"

        ops = AcceptanceOps()
    else:
        ops = RuntimeOps()
    rc, record = start_attempt(out, cfg, ops=ops, env_overlay=overlay)
    print(json.dumps({"run_id": record["run_id"],
                      "termination": record["termination"],
                      "entry_failure": bool(record.get("entry_failure")),
                      "cleanup_errors": record["cleanup_errors"],
                      "rc": rc}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
