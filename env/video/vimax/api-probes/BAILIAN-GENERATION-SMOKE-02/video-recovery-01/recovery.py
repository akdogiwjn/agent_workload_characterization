#!/usr/bin/env python3
"""BAILIAN-GENERATION-SMOKE-02 / video-recovery-01.

Authorized ONLY to: poll the ONE existing video task, download its result,
and run local media checks. No new video task, no image regeneration, no
LLM call, no smoke re-run.

Reads the task_id from the ORIGINAL creation response in ../verification.json
(never from chat text). Polls at most 12 times (target 10 s interval) under a
shared 180 s wall deadline, zero retries; 401/403 or missing/expired task
stops immediately. Download uses the separate media client WITHOUT the model
API Authorization header. All counters/timing/redaction reuse the fixed
probe module.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REC_DIR = Path(__file__).resolve().parent
PROBE_DIR = REC_DIR.parent
sys.path.insert(0, str(PROBE_DIR))

import probe  # noqa: E402

POLL_MAX = 12
POLL_INTERVAL_S = 10.0
DEADLINE_S = 180.0
POLL_WINDOW_S = 120.0  # leave >=60 s of the shared deadline for download+checks
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN")


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
    tmp.rename(path)


def main() -> int:
    t0 = time.monotonic()
    hard_deadline = t0 + DEADLINE_S
    poll_deadline = t0 + POLL_WINDOW_S
    counters = probe.Counters()

    # ---- task identity from the ORIGINAL response (not chat text) ----------
    orig = json.loads((PROBE_DIR / "verification.json").read_text())
    create = orig["steps"]["D_video"]["create_verdict"]
    task_id = create["task_id"]
    assert task_id and isinstance(task_id, str) and len(task_id) >= 32, \
        "task_id missing/unusable in original creation response"

    state = {
        "schema": "bailian-generation-smoke-02-video-recovery-01-v1",
        "task": "video-recovery-01",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "authorization_scope": "poll existing task + download + local media "
                               "checks only; no new generation of any kind",
        "source_task": {
            "task_id": task_id,
            "from": "../verification.json steps.D_video.create_verdict",
            "create_request_id": create.get("request_id"),
            "original_verdict_preserved": "UNKNOWN (timeout_task_still_running) + 40x401 poll log remain in ../verification.json",
        },
        "limits": {"polls_max": POLL_MAX, "poll_interval_target_s": POLL_INTERVAL_S,
                   "deadline_s": DEADLINE_S, "retries": "disabled at every layer"},
        "polls": [],
        "video": {},
    }
    vpath = REC_DIR / "verification.json"

    def persist() -> None:
        state["counters"] = counters.snapshot()
        # merge, never overwrite: per-stage timings recorded earlier in the
        # run must survive later persist() calls (post-run fix; the first
        # real run lost download_s this way — see summary.md)
        state.setdefault("timings", {})
        state["timings"]["total_wall_s"] = round(time.monotonic() - t0, 3)
        write_json(vpath, state)

    persist()
    ws = probe.load_workspace_id()
    if not ws:
        state["error"] = "workspace id no longer registered"
        persist()
        return 4
    url = probe.build_video_task_url(ws) + task_id
    state["poll_url"] = url
    api_key = probe.load_credential()
    auth = {"Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"}
    api = probe.make_api_client()
    media = probe.make_media_client()

    # ---- bounded poll loop (12 max; stop on terminal/auth/missing) ---------
    terminal = None
    final_output = None
    usage = None
    exit_code = 0
    try:
        for i in range(POLL_MAX):
            if time.monotonic() > poll_deadline:
                state["polls"].append({"stop": "poll_window_exhausted"})
                break
            rec = probe.http_call(counters, api, "GET", url,
                                  counter_key="poll", headers=auth,
                                  deadline=hard_deadline)
            j = rec.get("json") or {}
            out = j.get("output") or {}
            status = out.get("task_status")
            entry = {"poll_index": i, "ok": rec.get("ok"),
                     "http_status": rec.get("http_status"),
                     "task_status": status,
                     "request_id": j.get("request_id"),
                     "error_code": out.get("code") or j.get("code"),
                     "error_message": out.get("message") or j.get("message")}
            state["polls"].append(entry)
            persist()
            if not rec.get("ok"):
                terminal = "CLIENT_ERROR"
                break
            if rec.get("http_status") in (401, 403):
                terminal = "AUTH_ERROR"
                state["auth_error_note"] = ("poll auth failed; stopping "
                                            "immediately, no retry")
                break
            if status in TERMINAL:
                terminal = status
                final_output = out
                usage = j.get("usage")
                break
            time.sleep(POLL_INTERVAL_S)
        else:
            state["polls"].append({"stop": "poll_budget_exhausted"})
        state["terminal"] = terminal
        persist()

        # ---- download + local checks (only on SUCCEEDED) -------------------
        if terminal == "SUCCEEDED":
            video_url = (final_output or {}).get("video_url")
            state["video"]["usage"] = usage
            tdl = time.monotonic()
            dl = probe.download_media(counters, media, video_url,
                                      REC_DIR / "D-video.mp4",
                                      probe.VIDEO_DL_CAP, hard_deadline)
            dl["url"] = probe.strip_url_query(video_url)
            state["video"]["download"] = dl
            state["timings"]["download_s"] = round(time.monotonic() - tdl, 3)
            persist()
            if dl.get("ok"):
                ffp = probe.ffprobe_video(REC_DIR / "D-video.mp4")
                dec = probe.decode_check(REC_DIR / "D-video.mp4")
                frames = probe.extract_frames(REC_DIR / "D-video.mp4",
                                              REC_DIR / "frames")
                diff, fstats = probe.frame_motion_and_layout(frames)
                if ffp:
                    ffp["frame_stats"] = fstats.get("layout")
                state["video"]["media"] = {
                    "bytes": dl["bytes"], "sha256": dl["sha256"],
                    "ffprobe": ffp, "decode_ok": dec,
                    "frames": [f.name for f in frames],
                    "first_last_diff_ratio": diff,
                    "frame_stats_list": fstats.get("frame_stats_list"),
                }
                verdict = probe.judge_D_video(dl, ffp, dec, frames, diff)
                state["video"]["verdict"] = verdict
                if verdict["verdict"] != "PASS":
                    exit_code = 7
            else:
                state["video"]["verdict"] = {
                    "verdict": "FAIL",
                    "reason": f"download_failed_{dl.get('error_type')}",
                    "note": "no new task is created on download failure"}
                exit_code = 7
        elif terminal in ("FAILED", "CANCELED", "UNKNOWN"):
            state["video"]["verdict"] = {
                "verdict": "FAIL", "reason": f"task_{terminal}",
                "final_output": final_output,
                "note": "server-side terminal state; expiry/UNKNOWN is NOT "
                        "treated as a model generation failure"}
            exit_code = 7
        elif terminal == "AUTH_ERROR":
            state["video"]["verdict"] = {"verdict": "UNKNOWN",
                                         "reason": "poll_auth_error"}
            exit_code = 7
        else:
            state["video"]["verdict"] = {
                "verdict": "UNKNOWN",
                "reason": "not_terminal_within_budget",
                "note": "task may still be running remotely; may still "
                        "incur cost; task_id retained; no cancellation "
                        "claimed (cancel API not verified)"}
            exit_code = 7
        persist()
    except Exception as exc:  # noqa: BLE001 — evidence always lands on disk
        state["unexpected_error"] = {"type": type(exc).__name__,
                                     "redacted": probe.redact(str(exc))[:800]}
        exit_code = 7
        persist()
    finally:
        api.close()
        media.close()
        auth.pop("Authorization", None)
        persist()
        m = probe.build_manifest(REC_DIR, inputs={
            "source_verification": "../verification.json",
            "reused_code": "../probe.py (fixed poll auth + 401/403 stop)",
            "credential": {"file": str(probe.CREDENTIAL_FILE),
                           "env": probe.CREDENTIAL_ENV,
                           "workspace_env": probe.WORKSPACE_ENV,
                           "value_stored": False}})
        write_json(REC_DIR / "manifest.json", m)

    print(json.dumps({
        "terminal": state.get("terminal"),
        "video_verdict": (state.get("video") or {}).get("verdict", {}).get(
            "verdict") if isinstance((state.get("video") or {}).get("verdict"), dict) else None,
        "polls": counters.snapshot()["poll_requests"],
        "downloads": counters.snapshot()["download_requests"],
        "report": str(vpath)}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
