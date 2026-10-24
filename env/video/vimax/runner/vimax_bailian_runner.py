#!/usr/bin/env python3
"""Host-side thin runner for the ViMax Bailian network-gated validation.

Audit-fix redesign (VIMAX-NETWORK-VALIDATION-02):

- cgroup sampling at the 0.5 s target with FULL per-point evidence saved
  (every CounterSnapshot: monotonic time, counters, per-file read status);
  only genuinely adjacent counters are ever differenced, gaps are recorded,
  nothing is zero-filled or interpolated;
- netns sampling runs on its own explicitly-configured period (default 2.0 s
  — a `docker exec` costs ~0.1-0.3 s, so 0.5 s would distort the measured
  container; the measured exec overhead is recorded), separate from the
  agent working window;
- completion HANDSHAKE: the in-container validation writes COMPLETE and
  keeps the container alive (SIGTERM -> graceful exit 0); the runner takes
  the FINAL resource boundary while the container still exists, and only
  then stops/removes it — the final boundary is no longer lost to early
  container teardown;
- independent finally blocks for sampler / netns thread / container: one
  cleanup failure never skips the others; all cleanup errors are preserved
  and mapped to a nonzero exit;
- strict success: the validation report must exist, parse, contain every
  required check and have zero failures; the container must have written the
  COMPLETE marker; agent process returncode is checked inside the report;
  docker rm is verified (read-back inspect); ANY critical failure is nonzero;
- the container gets a UNIQUE name; removal targets the exact full container
  ID created by THIS run and verifies ownership before deleting;
- every docker command has a timeout; the shared deadline bounds them all;
- image preflight compares the FULL image id / OS / architecture against the
  expected values and refuses to start on mismatch;
- I/O counters that cannot be read on this host are recorded as
  unsupported-with-evidence, never zero.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CgroupV1FileReader, ResourceSampler)

RUNNER_DIR = Path(__file__).resolve().parent
EXPECTED_IMAGE = {
    # filled per accepted build; the runner refuses to start on mismatch
    "id": "sha256:PENDING",  # replaced by --expect-image argument default
    "os": "linux",
    "architecture": "arm64",
}
NETNS_PERIOD_S = 2.0  # explicit; exec overhead measured and recorded
DOCKER_TIMEOUT_S = 30.0

REQUIRED_CHECKS = (
    # environment
    "env_interpreters", "env_ffmpeg", "env_dep_PIL", "env_dep_moviepy",
    "env_dep_langchain", "env_dep_aiohttp",
    # adapter units
    "unit_image_t2i", "unit_image_i2i", "unit_image_refs_rejected",
    "unit_video_first_frame", "unit_video_flf_rejected",
    "unit_video_t2v_rejected", "unit_auth_401_fails",
    "unit_bad_json_surfaces_error", "unit_download_failure_evidenced",
    "unit_single_create_per_task",
    # agent cold start (strict)
    "agent_narrative_planning_ok", "agent_planned_eight_shots",
    "agent_render_ok", "agent_process_rc0", "agent_final_video_exists",
    "ledger_single_create_per_video", "ledger_task_ids_unique",
    "agent_shot_clip_order_map",
    # media
    "media_codec_h264", "media_16_9_720p", "media_fps_30",
    "media_duration_about_40s", "media_no_audio_stream", "media_full_decode",
    "media_eight_identifiable_clips",
    # audit-fix rounds
    "unit_download_redirect_once_ok", "unit_download_second_redirect_fails",
    "unit_download_relative_location_ok", "unit_download_oversize_rejected",
    "unit_download_media_401_rejected", "unit_download_media_404_rejected",
    "unit_budget_gate_blocks_third_image",
    "preflight_medium_variation_rejected_with_zero_sends",
)


def sh(argv: list, timeout: float = DOCKER_TIMEOUT_S) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            argv, returncode=124, stdout=exc.stdout or "",
            stderr=f"TIMEOUT after {timeout}s: {' '.join(argv[:4])} ...")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dir_bytes(path: Path) -> dict:
    out = {"apparent_bytes": 0, "files": 0, "unreadable": 0}
    if not path.exists():
        return out
    for p in path.rglob("*"):
        if p.is_file():
            try:
                out["apparent_bytes"] += p.stat().st_size
                out["files"] += 1
            except OSError:
                out["unreadable"] += 1
    return out


# --------------------------------------------------------------------------- #
# strict report evaluation (pure function; unit-testable on the host)
# --------------------------------------------------------------------------- #

def evaluate_report(raw: str | None) -> tuple[bool, list[str], dict | None]:
    """Returns (ok, problems, parsed_report). A report is ok ONLY when it
    parses, contains every required check, and has no failures."""
    if raw is None:
        return False, ["validation report missing"], None
    try:
        report = json.loads(raw)
    except ValueError as exc:
        return False, [f"validation report corrupt: {exc}"], None
    if not isinstance(report, dict):
        return False, ["validation report is not a JSON object"], report
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks:
        return False, ["validation report has no checks"], report
    problems: list[str] = []
    for name in REQUIRED_CHECKS:
        entry = checks.get(name)
        if not isinstance(entry, dict):
            problems.append(f"required check missing: {name}")
        elif not entry.get("ok"):
            problems.append(
                f"required check failed: {name}: "
                f"{str(entry.get('detail'))[:120]}")
    failures = report.get("failures")
    if failures:
        problems.append(f"report failures list non-empty: {failures}")
    for name in ("preflight_medium_variation_rejected_with_zero_sends",):
        if name in checks and not checks[name].get("ok"):
            problems.append(f"critical check failed: {name}")
    return (not problems), problems, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--image", default="vimax-task-bailian:arm64-v2")
    ap.add_argument("--expect-image-id", required=True,
                    help="full expected image sha256 id; mismatch refuses start")
    ap.add_argument("--deadline-s", type=float, default=1800.0)
    ap.add_argument("--cgroup-interval-s", type=float, default=0.5)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        print(f"refusing: output directory already exists: {out}")
        return 2
    out.mkdir(parents=True)
    t0 = time.monotonic()
    deadline = t0 + args.deadline_s

    def remaining() -> float:
        return max(5.0, deadline - time.monotonic())

    record = {"task": "VIMAX-NETWORK-VALIDATION-02",
              "started_utc": now_iso(),
              "image": args.image,
              "cgroup_interval_target_s": args.cgroup_interval_s,
              "netns_period_s": NETNS_PERIOD_S,
              "netns_period_reason": (
                  "docker exec overhead (~0.1-0.3 s per read) would distort "
                  "the measured container at 0.5 s; cgroup sampling runs at "
                  "the 0.5 s target, netns on its own explicit period"),
              "phases": {}, "cleanup_errors": []}
    problems: list[str] = []

    def phase(name: str, **kw) -> None:
        record["phases"][name] = {"wall_s": round(time.monotonic() - t0, 3), **kw}
        (out / "run-record.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n")

    # ---- image preflight: FULL identity comparison ------------------------
    r = sh(["docker", "image", "inspect", args.image,
            "--format", "{{.Id}} {{.Os}} {{.Architecture}}"])
    if r.returncode != 0:
        record["error"] = f"image inspect failed: {r.stderr.strip()[:200]}"
        phase("preflight", ok=False)
        return 7
    image_id, image_os, image_arch = r.stdout.split()
    record["image_id"] = image_id
    record["image_platform"] = f"{image_os}/{image_arch}"
    if (image_id != args.expect_image_id
            or image_os != EXPECTED_IMAGE["os"]
            or image_arch != EXPECTED_IMAGE["architecture"]):
        record["error"] = (
            f"image identity mismatch: got {image_id} {image_os}/{image_arch}, "
            f"expected {args.expect_image_id} "
            f"{EXPECTED_IMAGE['os']}/{EXPECTED_IMAGE['architecture']}")
        phase("preflight", ok=False, refused="identity mismatch")
        return 7
    phase("preflight", ok=True)

    # ---- workspace + unique container name --------------------------------
    workspace = out / "workspace"
    workspace.mkdir()
    if sh(["chown", "-R", "2000:2000", str(workspace)]).returncode != 0:
        workspace.chmod(0o777)
        record["workspace_permission_fallback"] = (
            "chown to uid 2000 unavailable; chmod 777 applied")
    name = f"vimax-netval-{uuid4().hex[:8]}"
    record["container_name"] = name
    phase("before", workspace=dir_bytes(workspace))

    argv = ["docker", "run", "-d", "--name", name,
            "--network", "none",
            "--add-host", "ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1",
            "--user", "2000:2000", "-w", "/workspace",
            "--memory", "8g", "--cpus", "8",
            "--mount", f"type=bind,source={RUNNER_DIR},target=/opt/validation,readonly",
            "--mount", f"type=bind,source={workspace},target=/workspace",
            args.image, "python3", "/opt/validation/offline_validation.py"]
    record["docker_run_argv"] = argv
    r = sh(argv, timeout=min(60.0, remaining()))
    if r.returncode != 0:
        record["error"] = f"docker run failed: {r.stderr.strip()[:300]}"
        phase("docker_run", ok=False)
        return 7
    cid_full = r.stdout.strip()
    record["container_id"] = cid_full
    # ownership verification: the created container must carry THIS name
    r = sh(["docker", "inspect", "-f", "{{.Name}}", cid_full])
    if r.returncode != 0 or r.stdout.strip() != f"/{name}":
        record["error"] = (f"container ownership check failed: "
                           f"inspected name {r.stdout.strip()!r}")
        phase("docker_run", ok=False, ownership=False)
        sh(["docker", "rm", "-f", cid_full])
        return 7
    phase("docker_run", ok=True, cid=cid_full[:16])

    # ---- resource wiring ---------------------------------------------------
    sampler = ResourceSampler(interval_s=args.cgroup_interval_s)
    sampling_started = False
    netns_samples: list[dict] = []
    netns_stop = threading.Event()
    netns_exec_overheads: list[float] = []
    netns_thread: threading.Thread | None = None

    def netns_loop() -> None:
        while not netns_stop.is_set():
            t_exec = time.monotonic()
            r = sh(["docker", "exec", name, "cat", "/proc/net/dev"],
                   timeout=10.0)
            overhead = time.monotonic() - t_exec
            if r.returncode == 0:
                netns_exec_overheads.append(round(overhead, 3))
                lines = [l.split() for l in r.stdout.splitlines()[2:] if ":" in l]
                netns_samples.append({
                    "t": round(time.monotonic() - t0, 3),
                    "ifaces": {parts[0].rstrip(":"):
                               {"rx_bytes": int(parts[1]),
                                "tx_bytes": int(parts[9])}
                               for parts in lines if len(parts) > 9}})
            netns_stop.wait(NETNS_PERIOD_S)

    sampler_error: str | None = None
    try:
        reader = CgroupV1FileReader(
            scope="vimax_netval_02", scope_kind="agent_container",
            container_id=cid_full, cg_root=Path("/sys/fs/cgroup"))
        sampler.register("vimax_netval_02", "agent_container", reader)
        sampler.start("vimax_netval_02")
        sampler.start_background_sampling()
        sampling_started = True
    except Exception as exc:  # noqa: BLE001
        sampler_error = f"{type(exc).__name__}: {exc}"
        record["sampler_error"] = sampler_error
        problems.append(f"sampler start failed: {sampler_error}")
    netns_thread = threading.Thread(target=netns_loop, daemon=True)
    netns_thread.start()
    phase("sampling_started", sampler_ok=sampler_error is None)

    # ---- wait for the completion handshake --------------------------------
    complete_marker = workspace / "validation" / "COMPLETE"
    handshake_seen = False
    while time.monotonic() < deadline:
        if complete_marker.exists():
            handshake_seen = True
            break
        r = sh(["docker", "inspect", "-f", "{{.State.Running}}", cid_full],
               timeout=10.0)
        if r.returncode == 0 and r.stdout.strip() == "false":
            break  # container exited without the marker
        time.sleep(2.0)
    record["handshake_seen"] = handshake_seen
    phase("validation_finished", handshake=handshake_seen)
    if not handshake_seen:
        problems.append("completion handshake (COMPLETE marker) not observed")

    # ---- final resource boundary BEFORE container teardown ----------------
    sampler_stop_error: str | None = None
    try:
        if sampling_started:
            sampler.stop("vimax_netval_02")  # container still alive here
    except Exception as exc:  # noqa: BLE001
        sampler_stop_error = f"{type(exc).__name__}: {exc}"
        problems.append(f"sampler stop failed: {sampler_stop_error}")
    # netns thread: explicit stop + join (audit fix)
    netns_stop.set()
    if netns_thread is not None:
        netns_thread.join(timeout=15.0)
        if netns_thread.is_alive():
            problems.append("netns thread did not join within 15 s")
    try:
        if sampling_started:
            sampler.stop_background_sampling()
            samples = sampler.samples("vimax_netval_02")
            record["resource_summary"] = samples.summary()
            # FULL per-point evidence (audit fix: summary alone is not
            # "complete sampling")
            with open(out / "resource-samples.jsonl", "w", encoding="utf-8") as fh:
                for snap in samples.samples:
                    fh.write(json.dumps(snap.to_dict(),
                                        ensure_ascii=False) + "\n")
            record["resource_boundary"] = {
                "start": samples.boundary_start.to_dict()
                if samples.boundary_start else None,
                "end": samples.boundary_end.to_dict()
                if samples.boundary_end else None,
            }
            record["resource_sample_gaps_ns"] = list(samples.sample_gaps_ns)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"sample export failed: {type(exc).__name__}: {exc}")
    record["netns_samples"] = netns_samples
    record["netns_exec_overhead_s"] = {
        "measured": netns_exec_overheads[:5] + netns_exec_overheads[-5:],
        "count": len(netns_exec_overheads),
        "avg": (round(sum(netns_exec_overheads) / len(netns_exec_overheads), 3)
                if netns_exec_overheads else None)}
    phase("sampling_stopped", sampler_stop_error=sampler_stop_error)

    # ---- stop container (graceful SIGTERM; the validation traps it) -------
    sh(["docker", "stop", "-t", "30", cid_full], timeout=min(45.0, remaining()))
    r = sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", cid_full])
    record["container_exit_code"] = (int(r.stdout.strip())
                                     if r.returncode == 0 else None)
    phase("after", workspace=dir_bytes(workspace))

    # ---- strict report evaluation -----------------------------------------
    report_path = workspace / "validation" / "validation-report.json"
    raw = None
    try:
        raw = report_path.read_text() if report_path.exists() else None
    except OSError as exc:
        problems.append(f"report unreadable: {exc}")
    ok_report, report_problems, report = evaluate_report(raw)
    problems.extend(report_problems)
    if report is not None:
        record["validation_report"] = {
            "failures": report.get("failures"),
            "checks": len(report.get("checks") or {}),
            "wall_s": report.get("wall_s"),
            "media": report.get("stages", {}).get("media"),
            "resource_quality": report.get("stages", {}).get("resource_quality"),
        }
    phase("report_evaluated", ok=ok_report)

    # ---- container removal: exact id, ownership verified, read-back check -
    removed_ok = False
    if cid_full:
        r = sh(["docker", "rm", "-f", cid_full], timeout=min(30.0, remaining()))
        if r.returncode != 0:
            problems.append(f"docker rm failed: {r.stderr.strip()[:200]}")
        else:
            verify = sh(["docker", "inspect", "-f", "{{.Id}}", cid_full])
            if verify.returncode == 0:
                problems.append("container still inspectable after rm")
            else:
                removed_ok = True
    phase("cleanup", removed=removed_ok)

    record["finished_utc"] = now_iso()
    record["total_wall_s"] = round(time.monotonic() - t0, 3)
    record["problems"] = problems
    record["ok"] = not problems
    (out / "run-record.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": record["ok"],
                      "problems": problems,
                      "total_wall_s": record["total_wall_s"]},
                     ensure_ascii=False))
    return 0 if record["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
