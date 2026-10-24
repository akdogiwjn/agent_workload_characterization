#!/usr/bin/env python3
"""Fake Bailian boundary for the ViMax network-gated validation.

Serves, on 127.0.0.1 ONLY, the endpoints the Bailian adapters call:
  POST /compatible-mode/v1/chat/completions          (LLM: agent loop + LangChain)
  POST /compatible-mode/v1/images/generations        (image T2I/I2I -> URL)
  POST /api/v1/services/aigc/video-generation/video-synthesis  (task create)
  GET  /api/v1/tasks/{task_id}                       (poll -> SUCCEEDED + URL)
  GET  /media/{name}                                 (synthetic PNG/MP4)

NO real credentials and NO real network are involved. Every synthetic media
file is clearly identifiable (big index digit + colored bar). The LLM router
returns fixed, schema-valid answers:
- tool-calling requests (ViMax agent loop): PLANNING_INPUT -> narrative
  planning call; render prompt -> render call; tool results -> short text.
- plain requests (PydanticOutputParser chains) are routed by system-prompt
  keywords: characters / storyboard / decompose / camera tree / reference
  image selection / best image selection.
All shots are small-variation with independent cameras: no first+last-frame
path, no camera-transition branch (those capabilities are covered by the
adapter unit tests instead).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from aiohttp import web

MEDIA_DIR = Path(os.environ.get("FAKE_MEDIA_DIR", "/tmp/fake-bailian-media"))
SHOT_COUNT = int(os.environ.get("FAKE_SHOT_COUNT", "8"))
VIDEO_DURATION_S = 5
VIDEO_W, VIDEO_H = 1280, 720
IMAGE_W, IMAGE_H = 1600, 900
TASK_POLL_RUNNING_ROUNDS = int(os.environ.get("FAKE_POLL_RUNNING_ROUNDS", "2"))

PORT = int(os.environ.get("FAKE_PORT", "8666"))
FAKE_API_KEY = "fake-offline-key-not-real"
_requests_seen: list[dict] = []
_tasks: dict[str, dict] = {}
_media_serial = 0
# error injection modes for adapter unit tests: "" (normal) |
# "auth_error" (401 everywhere) | "bad_json" (invalid JSON) |
# "download_404" (media 404) | "video_never_terminal" (poll stays RUNNING) |
# "plan_variation_medium" (decompose plans medium-variation shots) |
# "dl_redirect_once"/"dl_redirect_twice"/"dl_redirect_loop"/
# "dl_redirect_relative"/"dl_oversize"/"dl_401" (media-download counterexamples)
_mode = ""
_image_requests = 0


def log(kind: str, **kw) -> None:
    record = {"ts": time.time(), "kind": kind, **kw}
    _requests_seen.append(record)
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# synthetic media generation (clearly identifiable, decodable)
# --------------------------------------------------------------------------- #

def make_frame_png(index: int, label: str, path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (IMAGE_W, IMAGE_H), (24, 24, 32))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 260, IMAGE_H], fill=(40 * ((index % 6) + 1), 60, 90))
    # big index digit drawn as stacked blocks (font-free, unambiguous)
    d.rectangle([380, 280, 1220, 620], fill=(15, 15, 20))
    for i, on in enumerate(_digit_blocks(index)):
        x = 420 + (i % 3) * 270
        y = 310 + (i // 3) * 160
        if on:
            d.rectangle([x, y, x + 220, y + 130], fill=(240, 200, 40))
    d.text((400, 680), label, fill=(230, 230, 230))
    d.text((400, 720), f"SYNTHETIC-SHOT-{index:02d} / NOT REAL OUTPUT", fill=(150, 150, 150))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def _digit_blocks(index: int) -> list[bool]:
    """3x2 on/off grid encoding the shot index (0-63) without fonts."""
    bits = []
    for pos in range(6):
        bits.append(bool((index >> pos) & 1))
    return bits


def make_clip_mp4(index: int, png: Path, path: Path) -> None:
    """5 s 1280x720 30 fps clip from the synthetic frame with slow zoom
    (decodable, clearly dynamic, no audio)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-loop", "1", "-i", str(png),
         "-t", str(VIDEO_DURATION_S),
         "-vf", (f"scale={VIDEO_W * 2}:{VIDEO_H * 2},"
                 f"zoompan=z='min(zoom+0.0006,1.15)':d={VIDEO_DURATION_S * 30}:"
                 f"s={VIDEO_W}x{VIDEO_H}:fps=30"),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
         "-an", str(path)],
        check=True, timeout=180)


def prepare_media() -> None:
    if MEDIA_DIR.exists() and (MEDIA_DIR / "READY").exists():
        return
    for idx in range(SHOT_COUNT):
        png = MEDIA_DIR / f"frame-{idx:02d}.png"
        make_frame_png(idx, f"SHOT {idx}", png)
        make_clip_mp4(idx, png, MEDIA_DIR / f"clip-{idx:02d}.mp4")
    (MEDIA_DIR / "READY").write_text("ok\n")
    print(f"fake media ready in {MEDIA_DIR}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# fixed LLM payloads
# --------------------------------------------------------------------------- #

CHARACTER = {
    "idx": 0,
    "identifier_in_scene": "摄影师",
    "is_visible": True,
    "static_features": (
        "A photographer in their thirties with short black hair, "
        "carrying a camera and a tripod."),
    "dynamic_features": "Wearing a khaki utility vest and dark jeans.",
}


def storyboard_payload() -> dict:
    shots = []
    for i in range(SHOT_COUNT):
        shots.append({
            "idx": i,
            "is_last": i == SHOT_COUNT - 1,
            "cam_idx": i,
            "visual_desc": (
                f"Shot {i}: the photographer works in the city from dawn to "
                "night; wide establishing composition, 16:9."),
            "audio_desc": "[Sound Effect] City ambient sound",
        })
    return {"storyboard": shots}


def decompose_payload() -> dict:
    """Per-shot VisDescDecompositionResponse (the pipeline calls decompose
    once per shot; single object, not a list)."""
    return {
        "ff_desc": ("First frame of a synthetic city shot: the photographer "
                    "stands in the city, wide composition, natural light."),
        "ff_vis_char_idxs": [0],
        "lf_desc": ("Last frame of the same synthetic shot: identical "
                    "composition with a tiny positional change."),
        "lf_vis_char_idxs": [0],
        "motion_desc": ("Static camera; the photographer adjusts position "
                        "slowly."),
        # "plan_variation_medium" injection plans a medium-variation shot to
        # exercise the capability preflight (must be rejected BEFORE any
        # paid media request); default small = first-frame-only path
        "variation_type": ("medium" if _mode == "plan_variation_medium"
                           else "small"),
        "variation_reason": ("injected medium variation (first+last frame "
                             "required)" if _mode == "plan_variation_medium"
                             else "Only minor changes between the first and "
                             "last frame; the video model supports "
                             "first-frame only."),
    }


def camera_tree_payload() -> dict:
    return {"camera_parent_items": [None] * SHOT_COUNT}


def reference_selection_payload() -> dict:
    return {
        "ref_image_indices": [0],
        "text_prompt": ("Synthetic keyframe prompt for the shot; consistent "
                        "photographer appearance."),
    }


def best_image_payload() -> dict:
    return {"best_image_index": 0, "reason": "synthetic candidate 0"}


# --------------------------------------------------------------------------- #
# LLM routing
# --------------------------------------------------------------------------- #

def _message_texts(body: dict) -> list[tuple[str, str]]:
    out = []
    for msg in body.get("messages") or []:
        role = msg.get("role", "")
        content = msg.get("content")
        if isinstance(content, str):
            out.append((role, content))
        elif isinstance(content, list):
            parts = [p.get("text", "") for p in content
                     if isinstance(p, dict) and p.get("type") == "text"]
            out.append((role, "\n".join(parts)))
    return out


def _assistant_tool_messages(body: dict) -> list[str]:
    names = []
    for msg in body.get("messages") or []:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                fn = (tc.get("function") or {}).get("name")
                if fn:
                    names.append(fn)
    return names


def _system_text(body: dict) -> str:
    texts = [t for r, t in _message_texts(body) if r == "system"]
    return "\n".join(texts)


def _llm_response(body: dict) -> dict:
    tools = body.get("tools") or []
    if tools:
        return _agent_loop_response(body)
    return _structured_output_response(body)


def _agent_loop_response(body: dict) -> dict:
    texts = _message_texts(body)
    user_count = sum(1 for r, _ in texts if r == "user")
    prior_calls = _assistant_tool_messages(body)

    def message(content: str) -> dict:
        return {"role": "assistant", "content": content}

    def tool_call(name: str, args: dict) -> dict:
        cid = "call_" + uuid.uuid4().hex[:12]
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": cid, "type": "function",
                "function": {"name": name,
                             "arguments": json.dumps(args, ensure_ascii=False)},
            }],
        }, cid

    def respond_text():
        return _chat_completion(
            message("Narrative planning artifacts are ready for review."))

    # the native loop keeps ONLY user/assistant TEXT between turns, so
    # prior_calls is non-empty only WITHIN a turn (after tool results).
    if "vimax_render_video" in prior_calls:
        return respond_text()
    if "vimax_narrative_planning" in prior_calls:
        return respond_text()
    if user_count <= 1:
        msg, cid = tool_call("vimax_narrative_planning", {
            "script": ("FAKE-SCRIPT: a city photographer works from sunrise "
                       "to late night across eight shots."),
            "user_requirement": ("Keep eight shots in order; every shot is a "
                                 "small-variation single first-frame shot; "
                                 "16:9; ~5 s each; no dialogue."),
            "style": "documentary, natural light",
        })
        return _chat_completion(msg, tool_call_id=cid,
                                tool_name="vimax_narrative_planning")
    msg, cid = tool_call("vimax_render_video", {})
    return _chat_completion(msg, tool_call_id=cid,
                            tool_name="vimax_render_video")


def _structured_output_response(body: dict) -> dict:
    system = _system_text(body)
    blob = system + "\n" + "\n".join(t for _, t in _message_texts(body))
    if "extract all relevant character" in blob or "character information" in blob:
        payload = {"characters": [CHARACTER]}
    elif "storyboard artist" in blob:
        payload = storyboard_payload()
    elif "visual text analyst" in blob or "first frame, the static last frame" in blob:
        payload = decompose_payload()
    elif "parent camera" in blob or "CAMERA_SEQ" in blob:
        payload = camera_tree_payload()
    elif "select the most suitable reference images" in blob:
        payload = reference_selection_payload()
    elif "visual assessment expert" in blob:
        payload = best_image_payload()
    else:
        payload = {"characters": [CHARACTER]}  # conservative default
    return _chat_completion({"role": "assistant",
                             "content": json.dumps(payload, ensure_ascii=False)})


def _chat_completion(message: dict, tool_call_id: str | None = None,
                     tool_name: str | None = None) -> dict:
    choice: dict = {"index": 0, "message": message,
                    "finish_reason": "tool_calls" if tool_call_id else "stop"}
    resp = {
        "id": "chatcmpl-fake-" + uuid.uuid4().hex[:10],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "fake-bailian-boundary",
        "choices": [choice],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10,
                  "total_tokens": 20},
    }
    return resp


# --------------------------------------------------------------------------- #
# HTTP handlers
# --------------------------------------------------------------------------- #

def _check_auth(request: web.Request) -> web.Response | None:
    if _mode == "auth_error":
        log("auth_rejected", path=request.path, mode=_mode)
        return web.json_response(
            {"error": {"message": "injected auth failure (fake boundary)",
                       "type": "invalid_request_error",
                       "code": "invalid_api_key"}},
            status=401)
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {FAKE_API_KEY}":
        log("auth_rejected", path=request.path)
        return web.json_response(
            {"error": {"message": "Incorrect API key provided (fake boundary)",
                       "type": "invalid_request_error",
                       "code": "invalid_api_key"}},
            status=401)
    return None


async def handle_chat(request: web.Request) -> web.StreamResponse:
    denied = _check_auth(request)
    if denied:
        return denied
    body = await request.json()
    log("llm_call", tools=bool(body.get("tools")),
        messages=len(body.get("messages") or []))
    if _mode == "bad_json":
        return web.Response(text="this is not json <", status=200,
                            content_type="application/json")
    return web.json_response(_llm_response(body))


async def handle_images(request: web.Request) -> web.StreamResponse:
    denied = _check_auth(request)
    if denied:
        return denied
    body = await request.json()
    if _mode == "bad_json":
        return web.Response(text="not-json<{", status=200,
                            content_type="application/json")
    global _media_serial
    # every image request returns the next synthetic frame, round-robin by
    # request serial so different shots get different identifiable frames
    index = _media_serial % SHOT_COUNT
    _media_serial += 1
    refs = body.get("image")
    ref_count = len(refs) if isinstance(refs, list) else (1 if refs else 0)
    if ref_count > 3:
        return web.json_response(
            {"error": {"message": "qwen-image-3.0 supports at most 3 "
                                  "reference images", "code": "InvalidParameter"}},
            status=400)
    global _image_requests
    _image_requests += 1
    log("image_generate", reference_count=ref_count, frame_index=index)
    return web.json_response({
        "created": int(time.time()),
        "data": [{"url": f"http://127.0.0.1:{PORT}"
                         f"/media/frame-{index:02d}.png"}],
        "usage": {"input_image_count": ref_count,
                  "input_image_type": "qima_input_1k",
                  "output_image_count": 1,
                  "output_image_type": "qima_output_1k",
                  "output_width": IMAGE_W, "output_height": IMAGE_H},
    })


async def handle_video_create(request: web.Request) -> web.StreamResponse:
    global _media_serial
    denied = _check_auth(request)
    if denied:
        return denied
    if request.headers.get("X-DashScope-Async") != "enable":
        return web.json_response(
            {"code": "BadRequest", "message": "missing X-DashScope-Async"},
            status=400)
    body = await request.json()
    img_url = ((body.get("input") or {}).get("img_url") or "")
    if not img_url:
        return web.json_response(
            {"code": "InvalidParameter",
             "message": "wan2.6-i2v-flash requires a first frame"},
            status=400)
    # map the embedded frame index if the caller encoded one; default 0
    index = _media_serial % SHOT_COUNT
    for i in range(SHOT_COUNT):
        if f"SHOTIDX{i:02d}" in img_url:
            index = i
    _media_serial += 1
    task_id = "fake-task-" + uuid.uuid4().hex[:12]
    _tasks[task_id] = {"frame": index, "polls": 0, "status": "PENDING"}
    log("video_create", task_id=task_id, frame_index=index)
    return web.json_response({
        "output": {"task_id": task_id, "task_status": "PENDING"},
        "request_id": "fake-req-" + uuid.uuid4().hex[:10]})


async def handle_task_poll(request: web.Request) -> web.StreamResponse:
    denied = _check_auth(request)
    if denied:
        return denied
    task_id = request.match_info["task_id"]
    task = _tasks.get(task_id)
    if task is None:
        return web.json_response(
            {"output": {"task_id": task_id, "task_status": "UNKNOWN"},
             "request_id": "fake-req-unknown"}, status=200)
    task["polls"] += 1
    if _mode == "video_never_terminal":
        task["status"] = "RUNNING"
        return web.json_response(
            {"output": {"task_id": task_id, "task_status": "RUNNING"},
             "request_id": "fake-req-" + uuid.uuid4().hex[:10]})
    if task["polls"] <= TASK_POLL_RUNNING_ROUNDS:
        task["status"] = "RUNNING"
        log("video_poll", task_id=task_id, status="RUNNING",
            polls=task["polls"])
        return web.json_response(
            {"output": {"task_id": task_id, "task_status": "RUNNING"},
             "request_id": "fake-req-" + uuid.uuid4().hex[:10]})
    task["status"] = "SUCCEEDED"
    log("video_poll", task_id=task_id, status="SUCCEEDED",
        polls=task["polls"])
    return web.json_response({
        "output": {
            "task_id": task_id, "task_status": "SUCCEEDED",
            "video_url": (f"http://127.0.0.1:{PORT}"
                          f"/media/clip-{task['frame']:02d}.mp4"),
        },
        "usage": {"video_count": 1, "duration": VIDEO_DURATION_S,
                  "SR": 720, "input_video_duration": 0,
                  "output_video_duration": VIDEO_DURATION_S, "audio": False},
        "request_id": "fake-req-" + uuid.uuid4().hex[:10]})


async def handle_media(request: web.Request) -> web.StreamResponse:
    # media downloads carry NO Authorization (asserted by the validation)
    if _mode == "download_404" or _mode == "dl_404":
        return web.Response(status=404)
    if _mode == "dl_401":
        return web.Response(status=401, text="media auth injected failure")
    if _mode == "dl_oversize":
        return web.Response(
            body=b"x" * (21 * 1024 * 1024),  # 21 MB > 20 MB cap
            headers={"Content-Type": "application/octet-stream"})
    name = request.match_info["name"]
    if _mode == "dl_redirect_once":
        # ONE absolute redirect to the real asset -> must succeed
        return web.Response(status=302, headers={
            "Location": f"http://127.0.0.1:{PORT}/media-direct/{name}"})
    if _mode == "dl_redirect_twice":
        # TWO chained redirects -> adapter must fail explicitly
        return web.Response(status=302, headers={
            "Location": f"http://127.0.0.1:{PORT}/media-hop/{name}"})
    if _mode == "dl_redirect_loop":
        # A -> B -> A loop -> fails via the 2-redirect rule
        return web.Response(status=302, headers={
            "Location": f"http://127.0.0.1:{PORT}/media-loop-a/{name}"})
    if _mode == "dl_redirect_relative":
        # RELATIVE Location -> adapter must resolve via urljoin and succeed
        return web.Response(status=302, headers={
            "Location": f"/media-direct/{name}"})
    return await _serve_media_file(name)


async def _serve_media_file(name: str) -> web.StreamResponse:
    path = (MEDIA_DIR / name).resolve()
    if not str(path).startswith(str(MEDIA_DIR.resolve())) or not path.is_file():
        return web.Response(status=404)
    ctype = "video/mp4" if name.endswith(".mp4") else "image/png"
    return web.FileResponse(path, headers={"Content-Type": ctype})


async def handle_media_direct(request: web.Request) -> web.StreamResponse:
    return await _serve_media_file(request.match_info["name"])


async def handle_media_hop(request: web.Request) -> web.StreamResponse:
    # second hop of dl_redirect_twice
    name = request.match_info["name"]
    return web.Response(status=302, headers={
        "Location": f"http://127.0.0.1:{PORT}/media-direct/{name}"})


async def handle_media_loop_a(request: web.Request) -> web.StreamResponse:
    return web.Response(status=302, headers={
        "Location": f"http://127.0.0.1:{PORT}/media-loop-b/"
                    + request.match_info["name"]})


async def handle_media_loop_b(request: web.Request) -> web.StreamResponse:
    return web.Response(status=302, headers={
        "Location": f"http://127.0.0.1:{PORT}/media-loop-a/"
                    + request.match_info["name"]})


async def handle_admin_mode(request: web.Request) -> web.StreamResponse:
    global _mode
    body = await request.json()
    _mode = str(body.get("mode", ""))
    log("admin_mode", mode=_mode)
    return web.json_response({"mode": _mode})


async def handle_stats(request: web.Request) -> web.StreamResponse:
    return web.json_response({"requests": _requests_seen,
                              "image_requests": _image_requests,
                              "tasks": {
        k: {"frame": v["frame"], "polls": v["polls"], "status": v["status"]}
        for k, v in _tasks.items()}})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/compatible-mode/v1/chat/completions", handle_chat)
    app.router.add_post("/compatible-mode/v1/images/generations", handle_images)
    app.router.add_post("/api/v1/services/aigc/video-generation/video-synthesis",
                        handle_video_create)
    app.router.add_get("/api/v1/tasks/{task_id}", handle_task_poll)
    app.router.add_get("/media/{name}", handle_media)
    app.router.add_get("/media-direct/{name}", handle_media_direct)
    app.router.add_get("/media-hop/{name}", handle_media_hop)
    app.router.add_get("/media-loop-a/{name}", handle_media_loop_a)
    app.router.add_get("/media-loop-b/{name}", handle_media_loop_b)
    app.router.add_get("/stats", handle_stats)
    app.router.add_post("/admin/mode", handle_admin_mode)
    return app


def main() -> int:
    port = PORT
    prepare_media()
    app = build_app()
    print(f"fake bailian boundary on 127.0.0.1:{port}, media={MEDIA_DIR}",
          file=sys.stderr, flush=True)
    web.run_app(app, host="127.0.0.1", port=port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
