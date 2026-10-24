"""VIDEO-USE-ENV-01: no-model closed-loop validation for the video-use task image.

Infrastructure test only — NOT an agent experiment, NOT a real workload
sample, NOT a full video-use functional verification. No credentials are
read, no model/ASR/API calls are made, no external media is downloaded.

What it validates when executed (--execute --i-approve-video-use-env01):
  1. one fresh container per case from video-use-task:arm64-v1 (network none);
  2. in-container synthetic clip generation (FFmpeg lavfi, CPU libx264+aac);
  3. one REAL video-use render.py pipeline run (segment extract + grade +
     fades -> concat -> two-pass loudnorm) on the synthetic clips;
  4. ffprobe verification of the produced MP4 (format/duration/codecs);
  5. continuous 0.5s cgroup sampling via the project collector path
     (DockerCliRuntime.read_counters -> CgroupV1FileReader) with monotonic
     timestamps, CPU, memory and available I/O counters;
  6. proof that FFmpeg task subprocesses are members of the monitored
     container cgroup (not only the main container PID);
  7. before/after apparent-size scans of explicit input/output directories;
  8. per-command start/end monotonic boundaries, return codes, hashes;
  9. one timeout counterexample: short exec budget on a long encode ->
     terminate chain -> container removed, image retained;
 10. cleanup verification: containers removed, images still present.

Offline mode (default) runs only the pure helpers so unit tests can cover
EDL/command construction, model-route rejection and report assembly without
Docker.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

COLLECTION = "VIDEO-USE-ENV-01"
TASK_IMAGE = "video-use-task:arm64-v1"
BASE_IMAGE = "video-common-base:arm64-v1"
VENV_PYTHON = "/opt/video-use-venv/bin/python"
SAMPLE_INTERVAL_S = 0.5
REPORT_PATH = ROOT / "env/video/video-use/validation/env01-validation.json"
UPSTREAM_COMMIT = "43cfc566833548093455c9d4a46bd69913b7e552"

SYNTH_SECONDS_A = 6.0
SYNTH_SECONDS_B = 5.0
SEGMENT_A = {"source": "clip_a.mp4", "start": 0.5, "end": 3.0, "beat": "synthetic_open"}
SEGMENT_B = {"source": "clip_b.mp4", "start": 1.0, "end": 4.0, "beat": "synthetic_close"}
EXPECTED_TOTAL_S = (SEGMENT_A["end"] - SEGMENT_A["start"]) + (SEGMENT_B["end"] - SEGMENT_B["start"])

NOT_TESTED = [
    "ElevenLabs Scribe transcription (transcribe.py) — requires a real API key; none read, none called",
    "visual self-eval chain (timeline_view PNG quality assertions) — not run",
    "Codex CLI inside the task container and model routing — CLI not installed this round",
    "real footage / full video-use workflow — synthetic clips only",
    "yt-dlp, animation engines (HyperFrames/Remotion/Manim), browser stack — not installed",
]


# --------------------------------------------------------------------------- #
# pure helpers (offline-testable)
# --------------------------------------------------------------------------- #

def validate_model_route(route: dict) -> dict:
    """Explicit-route contract: endpoint, model and credential env-var NAME.

    Missing fields must hard-reject; no provider default, no cross-vendor
    fallback. Credential VALUES (or key-derived material) must never be part
    of the route and are rejected if present.
    """
    missing = [f for f in ("api_base", "model", "api_key_env") if not route.get(f)]
    if missing:
        raise ValueError("model route incomplete, refusing to build client: missing " +
                         ", ".join(missing))
    forbidden = [k for k in route if k in ("api_key", "api_key_value", "authorization",
                                           "headers", "credentials")]
    if forbidden:
        raise ValueError("model route must not embed credential material: " +
                         ", ".join(forbidden))
    return {"api_base": route["api_base"], "model": route["model"],
            "api_key_env": route["api_key_env"]}


def synthesis_commands() -> list[dict]:
    """Two short synthetic clips generated at runtime (no downloads)."""
    return [
        {"name": "mkdir_task_dirs", "shell": "mkdir -p /task/sources /task/edit"},
        {"name": "clip_a.mp4", "shell": (
            "ffmpeg -y -hide_banner -loglevel error "
            "-f lavfi -i testsrc2=duration=%.1f:size=640x360:rate=24 "
            "-f lavfi -i sine=frequency=440:duration=%.1f "
            "-c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p "
            "-c:a aac -b:a 128k -shortest /task/sources/clip_a.mp4"
            % (SYNTH_SECONDS_A, SYNTH_SECONDS_A))},
        {"name": "clip_b.mp4", "shell": (
            "ffmpeg -y -hide_banner -loglevel error "
            "-f lavfi -i testsrc2=duration=%.1f:size=640x360:rate=24 "
            "-f lavfi -i sine=frequency=660:duration=%.1f "
            "-vf hue=h=90 -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p "
            "-c:a aac -b:a 128k -shortest /task/sources/clip_b.mp4"
            % (SYNTH_SECONDS_B, SYNTH_SECONDS_B))},
    ]


def build_edl() -> dict:
    return {
        "sources": {
            "clip_a.mp4": "/task/sources/clip_a.mp4",
            "clip_b.mp4": "/task/sources/clip_b.mp4",
        },
        "ranges": [dict(SEGMENT_A), dict(SEGMENT_B)],
        "grade": "eq=contrast=1.05:saturation=1.05",
    }


def edl_write_command(edl: dict) -> str:
    import shlex
    payload = json.dumps(edl, separators=(",", ":"))
    return "mkdir -p /task/edit && python3 -c " + \
        shlex.quote("import json,sys;open('/task/edit/edl.json','w').write(sys.argv[1])") + \
        " " + shlex.quote(payload)


def render_command() -> str:
    return (f"{VENV_PYTHON} /opt/video-use/helpers/render.py /task/edit/edl.json "
            f"-o /task/edit/final.mp4 --no-subtitles")


def ffprobe_command(path: str) -> str:
    return ("ffprobe -v error -show_entries "
            "format=duration,format_name,size:stream=codec_name,codec_type,width,height,avg_frame_rate "
            "-of json " + path)


def hash_command(paths: list[str]) -> str:
    return "sha256sum " + " ".join(paths)


def timeout_encode_command() -> str:
    """Deliberately long encode used for the timeout cleanup counterexample."""
    return ("mkdir -p /task/edit && ffmpeg -y -hide_banner -loglevel error "
            "-f lavfi -i testsrc2=duration=600:size=1920x1080:rate=30 "
            "-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p /task/edit/slow.mp4")


def container_disk_specs() -> list[dict]:
    return [
        {"path": "/task/sources", "role": "task_input_sources",
         "scope": "video_use_task_container", "ownership": "task_scoped"},
        {"path": "/task/edit", "role": "task_output_edit",
         "scope": "video_use_task_container", "ownership": "task_scoped"},
        {"path": "/opt/video-use", "role": "skill_source_copy",
         "scope": "video_use_task_container", "ownership": "image_content"},
        {"path": "/root/.cache", "role": "container_user_cache",
         "scope": "video_use_task_container", "ownership": "shared_cache"},
    ]


def rate_counter_specs() -> dict:
    return {
        "cpu": {"path": ("container", "cpu_usage_usec"), "unit": "core_s",
                "rate_unit": "cores", "divisor": 1_000_000,
                "identity_paths": [("container", "container_id")],
                "status_paths": [("container", "read_status", "cpuacct.usage")]},
        "io_read": {"path": ("container", "io_read_bytes"), "unit": "bytes",
                    "identity_paths": [("container", "container_id")],
                    "status_paths": [("container", "read_status", "io")]},
        "io_write": {"path": ("container", "io_write_bytes"), "unit": "bytes",
                     "identity_paths": [("container", "container_id")],
                     "status_paths": [("container", "read_status", "io")]},
    }


def validate_ffprobe(probe: dict) -> dict:
    """Structural verification of the rendered output (readability, duration,
    codecs) — NOT a semantic quality judgement."""
    problems = []
    streams = probe.get("streams") or []
    codecs = {(s.get("codec_type"), s.get("codec_name")) for s in streams}
    if ("video", "libx264") not in codecs and ("video", "h264") not in codecs:
        problems.append("no h264/libx264 video stream")
    if ("audio", "aac") not in codecs:
        problems.append("no aac audio stream")
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    if vstream.get("width") != 1920 or vstream.get("height") != 1080:
        problems.append(f"unexpected resolution {vstream.get('width')}x{vstream.get('height')}")
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        duration = None
        problems.append("duration unreadable")
    if duration is not None and abs(duration - EXPECTED_TOTAL_S) > 0.35:
        problems.append(f"duration {duration:.3f}s differs from expected {EXPECTED_TOTAL_S:.3f}s")
    return {"ok": not problems, "problems": problems,
            "observed_duration_s": duration, "expected_duration_s": EXPECTED_TOTAL_S}


def build_task_spec(run_id: str, scope: str, image: str = TASK_IMAGE):
    from agent_workload_characterization.runners.container_runtime import ContainerSpec
    return ContainerSpec(run_id=run_id, scope=scope, image=image, cwd="/task",
                         env={}, timeout_s=600, mem_limit="4g", network="none")


# --------------------------------------------------------------------------- #
# live helpers
# --------------------------------------------------------------------------- #

class ContainerScopeSampler(threading.Thread):
    """0.5s cgroup sampling via the project collector path (host reads the
    task container's cgroup; monotonic timestamps preserved)."""

    def __init__(self, handle, runtime, interval_s: float = SAMPLE_INTERVAL_S):
        super().__init__(daemon=True)
        self.handle = handle
        self.runtime = runtime
        self.interval_s = interval_s
        self.stop_event = threading.Event()
        self.rows: list[dict] = []
        self.lock = threading.Lock()

    def read_once(self, role: str) -> dict:
        row = {"t_monotonic_ns": time.monotonic_ns(), "clock_domain": "system_monotonic",
               "role": role}
        t = row["t_monotonic_ns"]
        try:
            snap = self.runtime.read_counters(self.handle, t).to_dict()
            snap.update(container_id=self.handle.container_id,
                        cgroup_version=self.handle.cgroup_version)
            row["container"] = snap
        except Exception as exc:  # noqa: BLE001 — reader failure is recorded, never faked
            row["container_error"] = type(exc).__name__
        with self.lock:
            self.rows.append(row)
        return row

    def run(self):
        self.read_once("boundary_start")
        while not self.stop_event.is_set():
            self.stop_event.wait(self.interval_s)
            if not self.stop_event.is_set():
                self.read_once("sample")
        self.read_once("boundary_end")


def cgroup_membership_observation(handle, cgroup_dir: Path) -> dict:
    """Host-side: list PIDs in the container's cgroup and their comm names.

    Proves the FFmpeg task subprocess (spawned via docker exec, descendant of
    the exec session — NOT the container init PID) is inside the monitored
    cgroup.
    """
    t = time.monotonic_ns()
    pids: dict[str, str] = {}
    status = {}
    for rel in ("cgroup.procs", "tasks"):
        try:
            text = (cgroup_dir / rel).read_text(encoding="ascii", errors="replace")
            status[rel] = "ok"
        except OSError as exc:
            status[rel] = type(exc).__name__
            continue
        for line in text.split():
            pid = line.strip()
            if not pid or pid in pids:
                continue
            try:
                comm = Path(f"/proc/{pid}/comm").read_text(
                    encoding="ascii", errors="replace").strip()
            except OSError:
                comm = "unreadable"
            pids[pid] = comm
    return {"t_monotonic_ns": t, "cgroup_dir": str(cgroup_dir), "status": status,
            "pid_count": len(pids), "comm_by_pid": pids,
            "ffmpeg_pids": sorted(p for p, c in pids.items() if "ffmpeg" in c)}


def summarize_intervals(rows: list[dict]) -> dict:
    from agent_workload_characterization.collectors.execution_measurement import \
        counter_rate_intervals
    intervals = counter_rate_intervals(rows, rate_counter_specs())
    summary = {}
    for metric in ("cpu", "io_read", "io_write"):
        items = [iv["metrics"][metric] for iv in intervals if metric in iv.get("metrics", {})]
        valid = [m for m in items if m["status"] == "valid"]
        total = sum(m["delta"] for m in valid if m["delta"] is not None)
        summary[metric] = {
            "interval_count": len(items), "valid": len(valid),
            "gap": len(items) - len(valid),
            "total_delta": total,
            "unit": ({"cpu": "core_s", "io_read": "bytes", "io_write": "bytes"})[metric],
            "gap_reasons": sorted({m["reason"] for m in items if m["status"] != "valid"
                                   and m.get("reason")}),
        }
    return summary


def mem_gauge_summary(rows: list[dict]) -> dict:
    current = [r["container"]["mem_current_bytes"] for r in rows
               if r.get("container", {}).get("mem_current_bytes") is not None]
    peak = [r["container"]["mem_peak_bytes"] for r in rows
            if r.get("container", {}).get("mem_peak_bytes") is not None]
    return {"samples_with_current": len(current),
            "max_sampled_current_bytes": max(current) if current else None,
            "kernel_peak_bytes_max": max(peak) if peak else None,
            "note": "cgroup v1 memory.usage_in_bytes gauge and memory.max_usage_in_bytes "
                    "kernel peak; different bases, never summed"}


# --------------------------------------------------------------------------- #
# live phases
# --------------------------------------------------------------------------- #

def _exec_record(runtime, handle, name: str, shell: str, timeout_s: float,
                 **kw) -> dict:
    t0 = time.monotonic_ns()
    result = runtime.execute(handle, shell, timeout_s=timeout_s, **kw)
    t1 = time.monotonic_ns()
    output = result.get("output", "")
    return {"name": name, "t_start_monotonic_ns": t0, "t_end_monotonic_ns": t1,
            "duration_s": (t1 - t0) / 1e9, "returncode": result.get("returncode"),
            "timed_out": bool(result.get("timed_out", False)),
            "termination": result.get("termination"),
            "output_excerpt": output[-2000:] if output else "",
            "output_bytes_total": result.get("output_bytes_total", len(output))}


def image_identity(reference: str) -> dict:
    """Query one image identity; NEVER raises — a failed query (timeout,
    OSError, malformed output) is returned as an explicit failure record so
    the report always lands with the evidence of the failed check."""
    import subprocess
    try:
        proc = subprocess.run(["docker", "inspect", reference,
                               "--format", "{{.Id}} {{.Architecture}} {{.Os}}"],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001 — TimeoutExpired/OSError -> record
        return {"reference": reference, "present": None,
                "query_error": type(exc).__name__}
    if proc.returncode != 0:
        return {"reference": reference, "present": False}
    try:
        cid, arch, os_name = proc.stdout.split()
    except ValueError:
        return {"reference": reference, "present": None,
                "query_error": "malformed_inspect_output"}
    return {"reference": reference, "present": True, "image_id": cid,
            "architecture": arch, "os": os_name}


def expected_image_identities() -> dict:
    """Registered image identities (full ID + arch + os) from the
    environment manifests — the single source of truth for preflight."""
    base = json.loads((ROOT / "env/video/base/base-image.json").read_text())
    task = json.loads((ROOT / "env/video/video-use/env-manifest.json").read_text())
    return {
        base["tag"]: {"image_id": base["image_id"],
                      "architecture": base["architecture"], "os": base["os"]},
        task["image"]["tag"]: {"image_id": task["image"]["image_id"],
                               "architecture": task["image"]["architecture"],
                               "os": task["image"]["os"]},
    }


def verify_image_identities(actual: list[dict], expected: dict) -> list[str]:
    """Strict full-identity comparison; presence alone is NOT a pass.

    Any missing image, unregistered reference, or mismatch of image ID /
    architecture / os is an explicit failure string.
    """
    problems = []
    for img in actual:
        ref = img.get("reference")
        if img.get("query_error"):
            # a failed identity query is an explicit failure — it is NOT the
            # same as "missing" and must never be treated as a pass
            problems.append(f"{ref}: image identity query failed"
                            f" ({img.get('query_error')})")
            continue
        exp = expected.get(ref)
        if not img.get("present"):
            problems.append(f"{ref}: image missing")
        elif exp is None:
            problems.append(f"{ref}: not registered in environment manifests")
        else:
            if img.get("image_id") != exp["image_id"]:
                problems.append(f"{ref}: image id mismatch observed={img.get('image_id')}"
                                f" registered={exp['image_id']}")
            if img.get("architecture") != exp["architecture"]:
                problems.append(f"{ref}: architecture mismatch"
                                f" observed={img.get('architecture')}"
                                f" registered={exp['architecture']}")
            if img.get("os") != exp["os"]:
                problems.append(f"{ref}: os mismatch observed={img.get('os')}"
                                f" registered={exp['os']}")
    return problems


def acceptance_failures(report: dict) -> list[str]:
    """Strict acceptance for the no-model validation report.

    EVERY evidence group must be present and valid: render result, ffprobe,
    cgroup membership, sampling rows (with real container counter reads and
    at least one valid CPU interval), memory gauge samples, render-boundary
    disk delta, artifact hashes, timeout counterexample with termination
    record, removal verification, image retention AND full image identity.
    Missing or empty evidence is a FAILURE — never a silent pass.
    """
    problems = []
    sc = report.get("success_case") or {}
    tc = report.get("timeout_case") or {}

    if sc.get("status") != "render_complete":
        problems.append(f"success_case status={sc.get('status')!r}")
    if not (sc.get("ffprobe") or {}).get("validation", {}).get("ok"):
        problems.append("ffprobe validation not ok")
    if not sc.get("membership_observations"):
        problems.append("no membership observations saved")
    if not sc.get("membership_ffmpeg_seen"):
        problems.append("ffmpeg membership in monitored cgroup not observed")
    if sc.get("removal_verification") != "removed":
        problems.append(f"success container removal={sc.get('removal_verification')!r}")

    rows = sc.get("sampler_rows") or []
    if not rows:
        problems.append("no sampler rows saved")
    else:
        if not any(row.get("container") for row in rows):
            problems.append("no sampler row contains a container counter read")
        cpu = (sc.get("rate_summary") or {}).get("cpu") or {}
        expected_intervals = max(len(rows) - 1, 0)
        # FULL coverage required: every adjacent pair must be a valid CPU
        # interval (gap == 0). Legal zero deltas are valid intervals and stay
        # allowed; only gaps (unreadable/reset/identity change) fail.
        if cpu.get("valid") != expected_intervals or cpu.get("gap") != 0:
            problems.append(
                f"cpu intervals incomplete: valid={cpu.get('valid')}"
                f" gap={cpu.get('gap')} expected_valid={expected_intervals}")
        if cpu.get("interval_count") != expected_intervals:
            problems.append("cpu interval count does not match sampler rows")
        if not (sc.get("mem_gauge_summary") or {}).get("samples_with_current"):
            problems.append("no memory gauge samples")

    footprint = sc.get("render_footprint") or {}
    edit = next((p for p in footprint.get("paths", [])
                 if p.get("role") == "task_output_edit"), None)
    if (not edit or edit.get("delta_status") != "observed"
            or not isinstance(edit.get("delta_bytes"), int)):
        problems.append("task_output_edit render-boundary delta not observed")

    # hashes must be WELL-FORMED sha-256 — presence alone is not validity
    hashes = sc.get("artifact_hashes") or {}
    sha256_pattern = re.compile(r"^[0-9a-f]{64}$")
    for artifact in ("/task/sources/clip_a.mp4", "/task/sources/clip_b.mp4",
                     "/task/edit/final.mp4"):
        value = hashes.get(artifact)
        if not value:
            problems.append(f"missing artifact hash {artifact}")
        elif not sha256_pattern.fullmatch(str(value)):
            problems.append(f"artifact hash not valid sha-256: {artifact}")

    if tc.get("timed_out") is not True:
        problems.append("timeout case did not time out")
    # termination must be CONFIRMED — a present-but-unconfirmed record is a
    # failure, not a pass
    term = tc.get("termination_explicit")
    if not isinstance(term, dict) or term.get("confirmed") is not True:
        problems.append("explicit termination not confirmed")
    if tc.get("removal_verification") != "removed":
        problems.append(f"timeout container removal={tc.get('removal_verification')!r}")

    if not (report.get("cleanup") or {}).get("images_retained"):
        problems.append("images not retained")
    identity_problems = (report.get("image_identity_problems") or {})
    for phase in ("images_before", "images_after"):
        for p in identity_problems.get(phase) or []:
            problems.append(f"image identity ({phase}): {p}")
    return problems


def run_success_case(runtime, run_id: str) -> dict:
    from agent_workload_characterization.collectors.execution_measurement import \
        (container_directory_footprint_snapshot, disk_footprint_report)
    spec = build_task_spec(run_id, "video_use_task")
    handle = runtime.start(spec)
    record = {"run_id": run_id, "container_id": handle.container_id,
              "cgroup_version": handle.cgroup_version,
              "cgroup_dir": str(handle.cgroup_dir) if handle.cgroup_dir else None,
              "image": TASK_IMAGE, "commands": []}
    try:
        try:
            init_pid = runtime.container_init_pid(handle)
            record["container_init_pid"] = init_pid

            disk_before = container_directory_footprint_snapshot(
                runtime, handle, container_disk_specs(), timeout_s=20.0)
            record["disk_before"] = disk_before

            for synth in synthesis_commands():
                rec = _exec_record(runtime, handle, "synth:" + synth["name"],
                                   synth["shell"], timeout_s=120)
                record["commands"].append(rec)
                if rec["returncode"] != 0:
                    record["status"] = "synthesis_failed"
                    return record
            record["commands"].append(_exec_record(
                runtime, handle, "write_edl", edl_write_command(build_edl()), timeout_s=30))

            # disk boundary right before/after the render phase (input already
            # written, edit/ empty)
            pre_render = container_directory_footprint_snapshot(
                runtime, handle, container_disk_specs(), timeout_s=20.0)

            sampler = ContainerScopeSampler(handle, runtime)
            membership: list[dict] = []
            render_result: dict = {}
            render_error: str | None = None

            def _render():
                nonlocal render_result, render_error
                try:
                    render_result = _exec_record(runtime, handle, "render_edl",
                                                 render_command(), timeout_s=420)
                except Exception as exc:  # noqa: BLE001
                    render_error = type(exc).__name__

            sampler.start()
            render_thread = threading.Thread(target=_render)
            try:
                render_thread.start()
                while render_thread.is_alive():
                    if handle.cgroup_dir is not None:
                        membership.append(
                            cgroup_membership_observation(handle, handle.cgroup_dir))
                    time.sleep(0.3)
                render_thread.join()
                if handle.cgroup_dir is not None:
                    membership.append(
                        cgroup_membership_observation(handle, handle.cgroup_dir))
            finally:
                # Guard: on ANY exit path — including render_thread.start()
                # FAILURE — stop the sampler and keep the evidence collected
                # so far. A thread that never started (ident is None) must
                # not be joined; the start failure is recorded explicitly.
                if render_thread.ident is not None:
                    render_thread.join(timeout=5)
                sampler.stop_event.set()
                if sampler.ident is not None:
                    sampler.join(timeout=10)
                    if sampler.is_alive():
                        sampler.read_once("boundary_forced_after_join_timeout")
                if render_result:
                    record["commands"].append(render_result)
                elif render_thread.ident is None:
                    record["commands"].append(
                        {"name": "render_edl", "error": "render_thread_start_failed"})
                else:
                    record["commands"].append(
                        {"name": "render_edl", "error": render_error})
                record["membership_observations"] = membership
                record["membership_ffmpeg_seen"] = any(
                    obs["ffmpeg_pids"] for obs in membership)
                record["membership_non_init_task_processes"] = sorted({
                    comm for obs in membership for comm in obs["comm_by_pid"].values()
                    if comm not in ("sleep",)})
                record["sampler_rows"] = sampler.rows
                record["rate_summary"] = summarize_intervals(sampler.rows)
                record["mem_gauge_summary"] = mem_gauge_summary(sampler.rows)

            post_render = container_directory_footprint_snapshot(
                runtime, handle, container_disk_specs(), timeout_s=20.0)
            record["render_footprint"] = disk_footprint_report(pre_render, post_render)
            record["overall_footprint"] = disk_footprint_report(disk_before, post_render)

            if render_result and render_result.get("returncode") == 0:
                probe_rec = _exec_record(runtime, handle, "ffprobe_final",
                                         ffprobe_command("/task/edit/final.mp4"), timeout_s=30)
                record["commands"].append(probe_rec)
                try:
                    probe_json = json.loads(probe_rec["output_excerpt"])
                    record["ffprobe"] = {"raw": probe_json,
                                         "validation": validate_ffprobe(probe_json)}
                except json.JSONDecodeError:
                    record["ffprobe"] = {"raw": None,
                                         "validation": {"ok": False,
                                                        "problems": ["ffprobe output unparseable"]}}
                hash_rec = _exec_record(runtime, handle, "hash_artifacts", hash_command(
                    ["/task/sources/clip_a.mp4", "/task/sources/clip_b.mp4",
                     "/task/edit/final.mp4"]), timeout_s=30)
                record["commands"].append(hash_rec)
                record["artifact_hashes"] = dict(
                    line.split()[::-1] for line in hash_rec["output_excerpt"].splitlines()
                    if len(line.split()) == 2)
                record["status"] = "render_complete"
            else:
                record["status"] = "render_failed"
            record["termination"] = None  # normal completion; no termination chain run
            return record
        except Exception as exc:  # noqa: BLE001 — keep partial evidence, never
            # let an exception skip cleanup or lose the record
            import traceback
            record["status"] = "exception:" + type(exc).__name__
            record["exception_detail"] = traceback.format_exc()[-1500:]
            return record
    finally:
        runtime.stop(handle)
        record["removal_verification"] = runtime.verify_removal(handle)


def run_timeout_case(runtime, run_id: str) -> dict:
    spec = build_task_spec(run_id, "video_use_task_timeout")
    handle = runtime.start(spec)
    record = {"run_id": run_id, "container_id": handle.container_id,
              "image": TASK_IMAGE, "commands": []}
    try:
        try:
            rec = _exec_record(runtime, handle, "timeout_encode",
                               timeout_encode_command(), timeout_s=4.0)
            record["commands"].append(rec)
            record["timed_out"] = bool(rec.get("timed_out"))
            # The exec timeout path shares its (now exhausted) deadline, so the
            # chain records budget_exhausted — the real runners then call
            # terminate_workload with a FRESH phase budget. Do the same here.
            record["termination_from_exec"] = rec.get("termination")
            try:
                record["termination_explicit"] = runtime.terminate_workload(
                    handle, timeout_s=15.0)
            except Exception as exc:  # noqa: BLE001
                record["termination_explicit"] = {"error": type(exc).__name__}
            record["status"] = "timeout_counterexample_executed"
            return record
        except Exception as exc:  # noqa: BLE001 — same guard as the success case
            import traceback
            record["status"] = "exception:" + type(exc).__name__
            record["exception_detail"] = traceback.format_exc()[-1500:]
            return record
    finally:
        runtime.stop(handle)
        record["removal_verification"] = runtime.verify_removal(handle)


def _write_report(report: dict) -> Path:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return REPORT_PATH


def execute() -> int:
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    run_id = time.strftime("env01-%Y%m%dT%H%M%SZ", time.gmtime())
    runtime = DockerCliRuntime(authorized=True, collection=COLLECTION)
    report = {
        "schema": "video-use-env01-no-model-validation-v1",
        "task": COLLECTION,
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "upstream_commit": UPSTREAM_COMMIT,
        "purpose": "infrastructure validation only; not an agent experiment, "
                   "not a real workload sample, not full video-use verification",
        "images_before": [image_identity(BASE_IMAGE), image_identity(TASK_IMAGE)],
        "sampling": {
            "interval_target_s": SAMPLE_INTERVAL_S,
            "path": "DockerCliRuntime.read_counters -> CgroupV1FileReader (host reads task container cgroup)",
            "clock": "host time.monotonic_ns; container kernel monotonic for disk scans",
        },
        "network_scope": "task containers run with --network none; no task or API "
                         "traffic exists and none is claimed; host shared-netns "
                         "background is not attributed to any task",
    }
    # Last-resort guard: ANY unexpected exception still lands the report on
    # disk with an explicit execute_error record — never a lost report.
    try:
        # Strict preflight: the full registered identity (image ID + arch + os)
        # must match BEFORE any container is started; on mismatch (or a failed
        # identity query) refuse to run.
        expected = expected_image_identities()
        preflight = verify_image_identities(report["images_before"], expected)
        report["image_identity_problems"] = {"images_before": preflight}
        if preflight:
            report["preflight_refused"] = True
            report["not_tested"] = NOT_TESTED
            report["acceptance_failures"] = acceptance_failures(report)
            report["overall"] = "fail_or_partial"
            _write_report(report)
            print(json.dumps({"overall": report["overall"],
                              "refused": "image identity mismatch or query failure",
                              "report": str(REPORT_PATH)}, ensure_ascii=False))
            return 7

        # Belt-and-suspenders: a case-level exception is recorded in the
        # report; the report is ALWAYS written, never lost to a crash.
        for name, fn, suffix in (("success_case", run_success_case, "-ok"),
                                 ("timeout_case", run_timeout_case, "-to")):
            try:
                report[name] = fn(runtime, run_id + suffix)
            except Exception as exc:  # noqa: BLE001
                import traceback
                report[name] = {"status": "exception:" + type(exc).__name__,
                                "exception_detail": traceback.format_exc()[-1500:]}
        images_after = [image_identity(BASE_IMAGE), image_identity(TASK_IMAGE)]
        report["image_identity_problems"]["images_after"] = \
            verify_image_identities(images_after, expected)
        report["cleanup"] = {
            "images_after": images_after,
            "images_retained": (all(img["present"] for img in report["images_before"])
                                and all(img["present"] for img in images_after)),
            "note": "containers are deleted per case; images retained by design",
        }
        report["not_tested"] = NOT_TESTED
        problems = acceptance_failures(report)
        report["acceptance_failures"] = problems
        report["overall"] = "pass" if not problems else "fail_or_partial"
        _write_report(report)
        print(json.dumps({"overall": report["overall"], "report": str(REPORT_PATH)},
                         ensure_ascii=False))
        return 0 if not problems else 7
    except Exception as exc:  # noqa: BLE001
        import traceback
        report["execute_error"] = type(exc).__name__
        report["execute_error_detail"] = traceback.format_exc()[-1500:]
        try:
            report.setdefault("acceptance_failures", acceptance_failures(report))
        except Exception:  # noqa: BLE001
            report["acceptance_failures"] = ["acceptance check itself failed"]
        report["overall"] = "fail_or_partial"
        _write_report(report)
        print(json.dumps({"overall": report["overall"],
                          "execute_error": type(exc).__name__,
                          "report": str(REPORT_PATH)}, ensure_ascii=False))
        return 7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true",
                    help="run the live no-model validation (Docker required)")
    ap.add_argument("--i-approve-video-use-env01", action="store_true",
                    help="explicit confirmation flag required together with --execute")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_video_use_env01:
            print("refusing: --execute requires --i-approve-video-use-env01")
            return 2
        return execute()
    print("offline mode: pure helpers only; use --execute "
          "--i-approve-video-use-env01 for the live validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
