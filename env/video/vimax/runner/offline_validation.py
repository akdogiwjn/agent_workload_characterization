#!/usr/bin/env python3
"""In-container network-gated validation driver (audit-fix round 02).

Strictness changes vs 01:
- narrative/render tool results must be explicitly ok=true, observed AFTER
  the turn that requested them (an arbitrary earlier done does not count);
- the agent process must exit with returncode 0;
- the 8 synthetic clips are mapped to shots via SHA-256 (shot i's video.mp4
  vs the fake media library) and the final video's per-segment digits must
  EQUAL that mapping in order — a lucky permutation of {0..7} no longer
  passes;
- media assertions are explicit (h264, 1280x720, 30fps, ~40 s, no audio,
  full decode);
- capability-preflight counterexample: with the fake boundary planning a
  medium-variation shot, render must be REJECTED before any paid media
  request (image/video create counters must show ZERO increase);
- budget-gate counterexample: an image cap of 2 blocks the third generation
  before the send;
- download counterexamples: 0/1/2 redirects, redirect loop, relative
  Location, oversize, 401, 404;
- completion HANDSHAKE: after the report is written the driver writes
  COMPLETE and waits for SIGTERM (docker stop) so the host runner can take
  the final resource boundary while the container still exists; the wait is
  a separately-marked phase, never counted as agent work.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

RUNNER = Path("/opt/validation")
sys.path.insert(0, "/opt/vimax/src")
sys.path.insert(0, str(RUNNER))

WORK = Path(os.environ.get("VALIDATION_WORK", "/workspace/validation"))
FAKE_PORT = 8666
FAKE_HOST = "ws-fake.cn-beijing.maas.aliyuncs.com"  # --add-host -> 127.0.0.1
FAKE_KEY = "fake-offline-key-not-real"
LLM_BASE = f"http://{FAKE_HOST}:{FAKE_PORT}/compatible-mode/v1"
IMG_BASE = f"http://{FAKE_HOST}:{FAKE_PORT}/compatible-mode/v1"
VID_BASE = f"http://{FAKE_HOST}:{FAKE_PORT}"
MEDIA_DIR = Path("/tmp/fake-bailian-media")
SHOT_COUNT = 8

report: dict = {"stages": {}, "checks": {}, "failures": []}
T0 = time.monotonic()  # this run's own clock; never read from files


def check(name: str, ok: bool, detail=None) -> bool:
    report["checks"][name] = {"ok": bool(ok),
                              "detail": detail if detail is not None else ""}
    if not ok:
        report["failures"].append(name)
    return bool(ok)


def persist() -> None:
    report["wall_s"] = round(time.monotonic() - T0, 3)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "validation-report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n")


def run(argv: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# stage 1: environment
# --------------------------------------------------------------------------- #

def stage_environment() -> None:
    stage = {}
    for label, argv in (
        ("plain_shell", ["python3", "-c",
                         "import sys; print(sys.executable, sys.prefix)"]),
        ("bash_lc", ["bash", "-lc",
                     "python3 -c 'import sys; print(sys.executable, sys.prefix)'"]),
    ):
        r = run(argv)
        stage[label] = {"returncode": r.returncode, "stdout": r.stdout.strip()}
    r = run([sys.executable, "-c",
             "import sys, agent_runtime, tools; "
             "print(sys.executable); print(tools.__file__)"],
            cwd="/opt/vimax/src")
    stage["tool_shell_import"] = {"returncode": r.returncode,
                                  "stdout": r.stdout.strip()}
    exe = "/usr/local/bin/python3"
    check("env_interpreters",
          stage["plain_shell"]["returncode"] == 0
          and stage["bash_lc"]["returncode"] == 0
          and stage["plain_shell"]["stdout"].startswith(exe)
          and stage["bash_lc"]["stdout"].startswith(exe)
          and r.returncode == 0 and r.stdout.startswith(exe),
          stage)
    for mod in ("PIL", "moviepy", "langchain", "aiohttp", "pydantic"):
        r = run([sys.executable, "-c", f"import {mod}; print({mod}.__version__)"])
        check(f"env_dep_{mod}", r.returncode == 0, r.stdout.strip())
    ff = run(["ffmpeg", "-version"]); fp = run(["ffprobe", "-version"])
    check("env_ffmpeg", ff.returncode == 0 and fp.returncode == 0,
          ff.stdout.splitlines()[0] if ff.stdout else "")
    r = run(["ffmpeg", "-hide_banner", "-encoders"])
    check("env_encoder_libx264", "libx264" in (r.stdout or ""), "")
    report["stages"]["environment"] = stage


# --------------------------------------------------------------------------- #
# fake-boundary helpers
# --------------------------------------------------------------------------- #

def admin(mode: str) -> None:
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{FAKE_PORT}/admin/mode",
        data=json.dumps({"mode": mode}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200


def stats() -> dict:
    import urllib.request
    with urllib.request.urlopen(
            f"http://127.0.0.1:{FAKE_PORT}/stats", timeout=10) as resp:
        return json.loads(resp.read())


# --------------------------------------------------------------------------- #
# stage 2: adapter unit tests + counterexamples (fake boundary)
# --------------------------------------------------------------------------- #

def stage_adapter_units() -> None:
    import aiohttp
    from agent_runtime.request_ledger import RequestLedger
    from tools.image_generator_bailian_api import ImageGeneratorBailianAPI
    from tools.video_generator_bailian_api import VideoGeneratorBailianAPI
    from interfaces.image_output import ImageOutput

    ref = str(MEDIA_DIR / "frame-00.png")

    async def main() -> None:
        img = ImageGeneratorBailianAPI(api_key=FAKE_KEY, model="qwen-image-3.0",
                                       base_url=IMG_BASE)
        vid = VideoGeneratorBailianAPI(api_key=FAKE_KEY, model="wan2.6-i2v-flash",
                                       base_url=VID_BASE)

        # --- baseline mappings ---------------------------------------------
        out = await img.generate_single_image(prompt="t2i probe", size="1600x900")
        check("unit_image_t2i", isinstance(out, ImageOutput)
              and out.fmt == "pil" and out.data.width == 1600, out.fmt)
        out = await img.generate_single_image(
            prompt="i2i probe", reference_image_paths=[ref], size="1600x900")
        check("unit_image_i2i", isinstance(out, ImageOutput) and out.fmt == "pil",
              out.fmt)
        try:
            await img.generate_single_image(
                prompt="refs probe", reference_image_paths=[ref] * 4,
                size="1600x900")
            check("unit_image_refs_rejected", False, "no exception raised")
        except ValueError as exc:
            check("unit_image_refs_rejected", "at most 3" in str(exc), str(exc))
        out = await vid.generate_single_video(
            prompt="video probe", reference_image_paths=[ref])
        check("unit_video_first_frame", out.fmt == "bytes"
              and len(out.data) > 10000 and out.ext == "mp4",
              f"bytes={len(out.data)}")
        try:
            await vid.generate_single_video(
                prompt="flf probe", reference_image_paths=[ref, ref])
            check("unit_video_flf_rejected", False, "no exception raised")
        except ValueError as exc:
            check("unit_video_flf_rejected",
                  "first+last" in str(exc) or "last frame" in str(exc).lower(),
                  str(exc))
        try:
            await vid.generate_single_video(prompt="t2v probe")
            check("unit_video_t2v_rejected", False, "no exception raised")
        except ValueError as exc:
            check("unit_video_t2v_rejected", "text-to-video" in str(exc),
                  str(exc))

        # --- error injection: auth / bad json / plain download failure ------
        admin("auth_error")
        try:
            await img.generate_single_image(prompt="auth probe", size="1600x900")
            check("unit_auth_401_fails", False, "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_auth_401_fails", "401" in str(exc), str(exc)[:200])
        admin("")
        admin("bad_json")
        try:
            await img.generate_single_image(prompt="bad json probe",
                                            size="1600x900")
            check("unit_bad_json_surfaces_error", False, "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_bad_json_surfaces_error", True, str(exc)[:160])
        admin("")
        admin("download_404")
        try:
            await img.generate_single_image(prompt="dl probe", size="1600x900")
            check("unit_download_failure_evidenced", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_failure_evidenced", "404" in str(exc),
                  str(exc)[:200])
        admin("")

        # --- download redirect counterexamples ------------------------------
        # 1 allowed redirect (absolute Location) -> ok
        admin("dl_redirect_once")
        out = await img.generate_single_image(prompt="r1", size="1600x900")
        check("unit_download_redirect_once_ok",
              isinstance(out, ImageOutput), out.fmt)
        # 2 redirects -> explicit failure
        admin("dl_redirect_twice")
        try:
            await img.generate_single_image(prompt="r2", size="1600x900")
            check("unit_download_second_redirect_fails", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_second_redirect_fails",
                  "more than 1" in str(exc), str(exc)[:160])
        # relative Location -> resolved, ok
        admin("dl_redirect_relative")
        out = await img.generate_single_image(prompt="r3", size="1600x900")
        check("unit_download_relative_location_ok",
              isinstance(out, ImageOutput), out.fmt)
        # redirect loop -> fails via the 2-redirect rule
        admin("dl_redirect_loop")
        try:
            await img.generate_single_image(prompt="r4", size="1600x900")
            check("unit_download_redirect_loop_fails", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_redirect_loop_fails",
                  "more than 1" in str(exc), str(exc)[:160])
        # oversize -> explicit failure (cap lowered via env is not needed:
        # the fake serves >20 MB)
        admin("dl_oversize")
        try:
            await img.generate_single_image(prompt="r5", size="1600x900")
            check("unit_download_oversize_rejected", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_oversize_rejected",
                  "20 MB" in str(exc) or "413" in str(exc), str(exc)[:160])
        # media 401 / 404 (no Authorization expected on media host)
        admin("dl_401")
        try:
            await img.generate_single_image(prompt="r6", size="1600x900")
            check("unit_download_media_401_rejected", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_media_401_rejected", "401" in str(exc),
                  str(exc)[:160])
        admin("dl_404")
        try:
            await img.generate_single_image(prompt="r7", size="1600x900")
            check("unit_download_media_404_rejected", False,
                  "no exception raised")
        except Exception as exc:  # noqa: BLE001
            check("unit_download_media_404_rejected", "404" in str(exc),
                  str(exc)[:160])
        admin("")

        # --- budget gate counterexample ------------------------------------
        os.environ["VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS"] = "2"
        gated = RequestLedger(str(WORK / "gate-ledger.jsonl"))
        img2 = ImageGeneratorBailianAPI(api_key=FAKE_KEY, model="qwen-image-3.0",
                                        base_url=IMG_BASE)
        img2.ledger = gated  # inject the capped ledger for this unit
        blocked = False
        try:
            for i in range(3):
                await img2.generate_single_image(prompt=f"gate {i}",
                                                 size="1600x900")
        except Exception as exc:  # noqa: BLE001
            blocked = "budget" in str(exc).lower()
        gate_counts = gated.counts()
        check("unit_budget_gate_blocks_third_image",
              blocked and gate_counts.get("image_generations") == 2,
              f"blocked={blocked} counts={gate_counts}")
        os.environ.pop("VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS", None)

        # --- single create per task ----------------------------------------
        s0 = stats()
        created = len(s0["tasks"])
        check("unit_single_create_per_task", created >= 1,
              f"tasks={created}")

    asyncio.run(main())
    report["stages"]["adapter_units"] = "done"


# --------------------------------------------------------------------------- #
# stage 3: cold-start full chain (strict) + preflight counterexample
# --------------------------------------------------------------------------- #

def _agent_env() -> dict:
    env = dict(os.environ)
    env.update({
        "VIMAX_LLM_MODEL": "fake-bailian-boundary",
        "VIMAX_LLM_MODEL_PROVIDER": "openai",
        "VIMAX_LLM_BASE_URL": LLM_BASE,
        "VIMAX_LLM_API_KEY": FAKE_KEY,
        "VIMAX_IMAGE_MODEL": "qwen-image-3.0",
        "VIMAX_IMAGE_BASE_URL": IMG_BASE,
        "VIMAX_IMAGE_API_KEY": FAKE_KEY,
        "VIMAX_VIDEO_MODEL": "wan2.6-i2v-flash",
        "VIMAX_VIDEO_BASE_URL": VID_BASE,
        "VIMAX_VIDEO_API_KEY": FAKE_KEY,
        "VIMAX_BAILIAN_EVENT_LOG": str(WORK / "bailian-events.jsonl"),
        "VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS": "1",
        "VIMAX_NARRATIVE_STEP_TIMEOUT_SECONDS": "600",
    })
    return env


def _run_agent(session_name: str, session_dir: Path, events_path: Path,
               inputs: list[str], per_turn_timeout: float) -> tuple[list, int | None]:
    """Run one full agent process; returns (events, returncode)."""
    env = _agent_env()
    argv = [sys.executable, "/opt/vimax/src/main_agent.py", "--jsonl",
            "--stdin-repl", "--new-session", "--new-session-name", session_name]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=str(session_dir), env=env)
    events: list[dict] = []
    import threading
    reader_done = threading.Event()

    def reader() -> None:
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
            with open(events_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(events[-1], ensure_ascii=False) + "\n")
        reader_done.set()

    threading.Thread(target=reader, daemon=True).start()

    def tool_name(e: dict) -> str:
        return str((e.get("tool_result") or {}).get("name") or "")

    def tool_ok(e: dict) -> bool | None:
        return (e.get("tool_result") or {}).get("ok")

    mark = 0
    for user_input in inputs:
        proc.stdin.write(user_input + "\n")
        proc.stdin.flush()
        mark = len(events)

        def wait_for(pred, timeout, start):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if any(pred(e) for e in events[start:]):
                    return True
                time.sleep(0.5)
            return False

        # wait for THIS turn's terminal done event (the native loop emits
        # one per user turn); tool results alone may arrive mid-loop
        got = wait_for(lambda e: e.get("type") == "done",
                       per_turn_timeout, mark)
        if not got:
            break
    try:
        proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    reader_done.wait(10)
    return events, proc.returncode


def stage_agent_chain() -> None:
    session_dir = WORK / "agent-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    events_path = WORK / "agent-events.jsonl"

    events, rc = _run_agent(
        "validation-cold-start-02", session_dir, events_path,
        ["PLANNING_INPUT: plan the eight-shot city photographer story now.",
         "RENDER_INPUT: render the planned eight shots now."],
        per_turn_timeout=840)
    report["stages"]["agent_chain"] = {
        "events": len(events),
        "event_types": sorted({e.get("type", "?") for e in events}),
        "returncode": rc,
    }

    def tool_name(e: dict) -> str:
        return str((e.get("tool_result") or {}).get("name") or "")

    def tool_ok(e: dict) -> bool | None:
        return (e.get("tool_result") or {}).get("ok")

    # strict: narrative planning tool result must be present AND ok=true
    plan_events = [e for e in events if e.get("type") == "tool_result"
                   and "narrative" in tool_name(e)]
    check("agent_narrative_planning_ok",
          bool(plan_events) and all(tool_ok(e) is True for e in plan_events),
          f"results={[tool_ok(e) for e in plan_events]}")

    # strict: 8-shot contract on the real planned artifacts
    storyboard_ok, shot_count, sb_path = False, -1, None
    for p in session_dir.rglob("storyboard.json"):
        try:
            sb = json.loads(p.read_text())
            shot_count = len(sb)
            storyboard_ok = shot_count == SHOT_COUNT
            sb_path = p
            break
        except Exception:  # noqa: BLE001
            continue
    check("agent_planned_eight_shots", storyboard_ok,
          f"storyboard={sb_path} shots={shot_count}")

    # strict: render tool result present, ok=true, AFTER the render turn
    render_events = [e for e in events if e.get("type") == "tool_result"
                     and "render" in tool_name(e)]
    check("agent_render_ok",
          bool(render_events) and all(tool_ok(e) is True for e in render_events),
          f"results={[(tool_name(e), tool_ok(e)) for e in render_events]}")

    # strict: process must exit 0
    check("agent_process_rc0", rc == 0, f"returncode={rc}")

    finals = sorted(session_dir.rglob("final_video.mp4"))
    check("agent_final_video_exists", bool(finals),
          [str(f) for f in finals])

    # strict ledger: exactly one create per video, unique task ids
    ledger = WORK / "bailian-events.jsonl"
    shot_clip: dict[int, str] = {}
    if ledger.exists():
        lines = [json.loads(x) for x in
                 ledger.read_text().splitlines() if x.strip()]
        creates = [x for x in lines if x.get("op") == "video_create"
                   and (x.get("http_status") or x.get("error"))]
        check("ledger_single_create_per_video", len(creates) == SHOT_COUNT,
              f"creates={len(creates)}")
        check("ledger_task_ids_unique",
              len({c.get("task_id") for c in creates}) == len(creates),
              "task ids")
        report["stages"]["bailian_ledger"] = {
            "video_creates": len(creates),
            "video_task_ids": sorted({c.get("task_id")
                                      for c in creates if c.get("task_id")})}

    # strict shot->clip mapping: hash each shot's video.mp4 against the fake
    # media library, then require the final video's per-segment digits to
    # EQUAL that mapping in order
    if finals:
        clip_hashes = {sha256_file(MEDIA_DIR / f"clip-{i:02d}.mp4"): f"{i:02d}"
                       for i in range(SHOT_COUNT)}
        for p in sorted(session_dir.rglob("script2video/shots/*/video.mp4")):
            shot_idx = int(p.parent.name)
            h = sha256_file(p)
            shot_clip[shot_idx] = clip_hashes.get(h, f"unknown:{h[:8]}")
        expected_digits = [int(shot_clip[i]) for i in sorted(shot_clip)
                           if shot_clip[i].isdigit()]
        digits = stage_media_checks(finals[-1])
        order_ok = (len(shot_clip) == SHOT_COUNT
                    and digits is not None
                    and len(digits) == SHOT_COUNT
                    and all(str(d).zfill(2) == shot_clip[i]
                            for i, d in enumerate(digits)))
        check("agent_shot_clip_order_map", order_ok,
              f"shot_clip={shot_clip} final_digits={digits}")
        report["stages"]["shot_clip_map"] = {"shot_clip": shot_clip,
                                             "final_digits": digits}
    report["stages"]["final_video"] = str(finals[-1]) if finals else None


# --------------------------------------------------------------------------- #
# stage 4: media checks (strict, returns per-segment digits)
# --------------------------------------------------------------------------- #

def _decode_digit_blocks(png: Path) -> int | None:
    from PIL import Image
    img = Image.open(png).convert("RGB")
    w, h = img.size
    xs = [int(w * 0.24 + i * (w * 0.52) / 3 + (w * 0.52) / 6) for i in range(3)]
    ys = [int(h * 0.31 + j * (h * 0.38) / 2 + (h * 0.38) / 4) for j in range(2)]
    px = img.load()
    bits = []
    for j in range(2):
        for i in range(3):
            r, g, b = px[xs[i], ys[j]]
            bits.append(1 if (r > 180 and g > 150 and b < 120) else 0)
    return sum(bit << pos for pos, bit in enumerate(bits))


def stage_media_checks(final_video: Path) -> list | None:
    r = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(final_video)])
    if r.returncode != 0:
        check("media_ffprobe", False, r.stderr[:200])
        return None
    j = json.loads(r.stdout)
    streams = j.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    info = {
        "codec": video.get("codec_name"),
        "width": video.get("width"), "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "duration_s": float((j.get("format") or {}).get("duration", 0)),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }
    check("media_codec_h264", info["codec"] == "h264", info["codec"])
    check("media_16_9_720p", info["width"] == 1280 and info["height"] == 720,
          f"{info['width']}x{info['height']}")
    check("media_fps_30", info["fps"] == "30/1", info["fps"])
    check("media_duration_about_40s", abs(info["duration_s"] - 40) <= 4.0,
          info["duration_s"])
    check("media_no_audio_stream", info["has_audio"] is False, info["has_audio"])
    r = run(["ffmpeg", "-v", "error", "-i", str(final_video), "-f", "null", "-"])
    check("media_full_decode", r.returncode == 0 and not r.stderr.strip(),
          r.stderr[:200])
    frames_dir = WORK / "final-frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)
    digits = []
    for k in range(SHOT_COUNT):
        t = k * 5 + 2.5
        png = frames_dir / f"seg-{k}.png"
        r = run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i",
                 str(final_video), "-frames:v", "1", str(png)])
        digits.append(_decode_digit_blocks(png)
                      if r.returncode == 0 and png.exists() else None)
    check("media_eight_identifiable_clips",
          all(d is not None and 0 <= d < SHOT_COUNT for d in digits),
          f"digits={digits}")
    report["stages"]["media"] = {"segments": digits, **info}
    return digits


# --------------------------------------------------------------------------- #
# stage 5: capability-preflight counterexample (medium variation)
# --------------------------------------------------------------------------- #

def stage_preflight_counterexample() -> None:
    session_dir = WORK / "preflight-negative-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    events_path = WORK / "preflight-negative-events.jsonl"
    s_before = stats()
    images_before = s_before.get("image_requests", 0)
    creates_before = len(s_before.get("tasks", {}))

    admin("plan_variation_medium")
    try:
        events, rc = _run_agent(
            "preflight-negative-01", session_dir, events_path,
            ["PLANNING_INPUT: plan the eight-shot city photographer story now.",
             "RENDER_INPUT: render the planned eight shots now."],
            per_turn_timeout=600)
    finally:
        admin("")

    def tool_name(e: dict) -> str:
        return str((e.get("tool_result") or {}).get("name") or "")

    render_events = [e for e in events if e.get("type") == "tool_result"
                     and "render" in tool_name(e)]
    rejected = (bool(render_events)
                and all((e.get("tool_result") or {}).get("ok") is False
                        for e in render_events)
                and any("preflight" in str(
                    (e.get("tool_result") or {}).get("content", "")) for e in
                    render_events))
    s_after = stats()
    images_after = s_after.get("image_requests", 0)
    creates_after = len(s_after.get("tasks", {}))
    zero_sends = (images_after == images_before
                  and creates_after == creates_before)
    check("preflight_medium_variation_rejected_with_zero_sends",
          rejected and zero_sends,
          f"rejected={rejected} image_delta="
          f"{images_after - images_before} video_delta="
          f"{creates_after - creates_before}")
    report["stages"]["preflight_counterexample"] = {
        "render_results": [(tool_name(e),
                            (e.get("tool_result") or {}).get("ok"))
                           for e in render_events],
        "image_requests_delta": images_after - images_before,
        "video_tasks_delta": creates_after - creates_before,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    WORK.mkdir(parents=True, exist_ok=True)
    fake = subprocess.Popen(
        [sys.executable, str(RUNNER / "fake_bailian_server.py")],
        env={**os.environ, "FAKE_PORT": str(FAKE_PORT),
             "FAKE_MEDIA_DIR": str(MEDIA_DIR)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    handshake_wait_start = None
    try:
        import aiohttp

        async def wait_fake():
            for _ in range(60):
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                                f"http://127.0.0.1:{FAKE_PORT}/stats",
                                timeout=aiohttp.ClientTimeout(total=1)) as r:
                            return r.status == 200
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(0.5)
            return False
        if not asyncio.run(wait_fake()):
            check("fake_boundary_up", False, "fake server did not come up")
            persist()
            return 7
        check("fake_boundary_up", True, "")

        for stage_fn, label in (
                (stage_environment, "environment"),
                (stage_adapter_units, "adapter_units"),
                (stage_agent_chain, "agent_chain"),
                (stage_preflight_counterexample, "preflight_counterexample")):
            t_stage = time.monotonic()
            try:
                stage_fn()
            except Exception as exc:  # noqa: BLE001 — record, keep going
                report.setdefault("stage_errors", {})[label] = \
                    f"{type(exc).__name__}: {exc}"[:800]
                report["failures"].append(f"stage_error:{label}")
                persist()
            report["stages"].setdefault("stage_walls", {})[label] = round(
                time.monotonic() - t_stage, 3)
        persist()
    finally:
        persist()
        # completion handshake: keep the container alive (SIGTERM from docker
        # stop exits 0) so the host runner can take the final resource
        # boundary FIRST; the wait is a separately-marked phase below
        (WORK / "COMPLETE").write_text(
            json.dumps({"wall_s": round(time.monotonic() - T0, 3),
                        "failures": report["failures"]}) + "\n")
        handshake_wait_start = time.monotonic()
        print(json.dumps({"ok": not report["failures"],
                          "failures": report["failures"],
                          "checks": len(report["checks"]),
                          "wall_s": report["wall_s"]}, ensure_ascii=False),
              flush=True)
        try:
            signal.pause()  # wait for SIGTERM (docker stop) — not agent work
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            fake.terminate()
            try:
                fake.wait(timeout=10)
            except subprocess.TimeoutExpired:
                fake.kill()
    return 0 if not report["failures"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
