#!/usr/bin/env python3
"""Fake Bailian boundary for the network-gated cold-start acceptance.

Serves on 127.0.0.1 ONLY (container is --network none; no real network).
Replaces EXACTLY the external API boundary:
  - LLM chat completions (agent tool-call + inner LangChain JSON routing)
  - image generation (synthetic PNG per request, count recorded)
  - video task create/poll/download (8 MAJOR shot clips + 7 TRANSITION
    clips, distinguishable by the request prompt: transitions carry the
    native "transition between the shots" prompt template)
Everything else (session seeding, plan copy, agent loop, tool routing,
pipeline, selectors, FFmpeg, concat, export) is the REAL production path.

Stats are persisted to /workspace/attempt/fake-stats.json after every
state change so the host acceptance can verify:
  - exactly 19 image creates (3 portraits + 8 shots x 2 candidates)
  - exactly 15 video creates: 8 major + 7 transition, with per-request
    prompt/img hashes and the clip each task returned
  - no request ever left the loopback boundary
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from aiohttp import web

PORT = int(os.environ.get("FAKE_PORT", "8666"))
MEDIA = Path(os.environ.get("FAKE_MEDIA_DIR", "/tmp/fake-media"))
STATS = Path(os.environ.get("FAKE_STATS_PATH", "/workspace/attempt/fake-stats.json"))
FAKE_KEY = "fake-offline-key"
MAJOR_COUNT = 8
TRANSITION_COUNT = 7
CLIP_SECONDS = 5
W, H, FPS = 1280, 720, 30
IMG_W, IMG_H = 1600, 900
POLL_RUNNING_ROUNDS = 2
SESSION_ID = os.environ.get("VIMAX_MEDIA_SESSION_ID", "media-continuation-01")
PUBLIC_HOST = os.environ.get("FAKE_PUBLIC_HOST", f"127.0.0.1:{PORT}")
BASE_URL = f"http://{PUBLIC_HOST}"

state = {
    "llm_calls": 0,
    "image_creates": [],
    "video_creates": [],        # dicts: task_id, kind, prompt_sha, img_sha, clip
    "media_downloads": 0,
    "rejected_unknown_hosts": [],
    "started_monotonic": time.monotonic(),
}
tasks: dict[str, dict] = {}


def persist_stats() -> None:
    try:
        STATS.parent.mkdir(parents=True, exist_ok=True)
        clip_hashes = {}
        for name in sorted(p.name for p in MEDIA.glob("*.mp4")):
            clip_hashes[name] = hashlib.sha256(
                (MEDIA / name).read_bytes()).hexdigest()
        payload = {**state, "clip_sha256": clip_hashes,
                   "major_clips": MAJOR_COUNT,
                   "transition_clips": TRANSITION_COUNT}
        tmp = STATS.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, STATS)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# synthetic media
# --------------------------------------------------------------------------- #

def _digit_blocks(index: int) -> list[bool]:
    return [bool((index >> pos) & 1) for pos in range(6)]


def make_png(path: Path, label: str, index: int, variant: str) -> None:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (IMG_W, IMG_H), (24, 24, 32))
    d = ImageDraw.Draw(img)
    bar = {"major": (60, 120, 200), "transition": (200, 120, 60),
           "portrait": (120, 60, 200), "candidate": (60, 180, 120)}.get(
        variant, (90, 90, 90))
    d.rectangle([0, 0, 120, IMG_H], fill=bar)
    d.rectangle([380, 260, 1220, 640], fill=(15, 15, 20))
    for i, on in enumerate(_digit_blocks(index)):
        x = 420 + (i % 3) * 270
        y = 300 + (i // 3) * 170
        if on:
            d.rectangle([x, y, x + 220, y + 140], fill=(240, 200, 40))
    d.text((400, 680), f"{label} #{index:02d} {variant.upper()}-SYNTHETIC",
           fill=(230, 230, 230))
    d.text((400, 710), "FAKE BOUNDARY MEDIA — NOT A RESEARCH SAMPLE",
           fill=(150, 150, 150))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def make_clip(path: Path, index: int, variant: str) -> None:
    """5 s 1280x720 30 fps H.264 clip with a slow zoom (decodable, dynamic,
    clearly identifiable). Transitions get a distinctive top bar so the
    acceptance can distinguish kinds even inside the media itself."""
    src = path.with_suffix(".src.png")
    make_png(src, "CLIP", index, variant)
    bar_color = "0x3c78c8" if variant == "major" else "0xc8783c"
    vf = (f"scale={W*2}:{H*2},"
          f"zoompan=z='min(zoom+0.0006,1.15)':d={CLIP_SECONDS*FPS}:"
          f"s={W}x{H}:fps={FPS},"
          f"drawbox=x=0:y=0:w=iw:h=40:color={bar_color}@0.9:t=fill")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(src),
         "-t", str(CLIP_SECONDS), "-vf", vf, "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-an", str(path)],
        check=True, timeout=300)
    src.unlink(missing_ok=True)


def prepare_media() -> None:
    ready = MEDIA / "READY"
    if ready.exists():
        return
    for i in range(MAJOR_COUNT):
        make_clip(MEDIA / f"major-{i:02d}.mp4", i, "major")
    for i in range(TRANSITION_COUNT):
        make_clip(MEDIA / f"transition-{i:02d}.mp4", 100 + i, "transition")
    ready.write_text("ok\n")
    print(f"fake media ready ({MAJOR_COUNT} major + {TRANSITION_COUNT} "
          f"transitions)", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# LLM routing
# --------------------------------------------------------------------------- #

def _texts(body: dict) -> list[tuple[str, str]]:
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


def llm_response(body: dict) -> dict:
    state["llm_calls"] += 1
    has_tools = bool(body.get("tools"))
    texts = _texts(body)
    system = "\n".join(t for r, t in texts if r == "system")
    user_count = sum(1 for r, _ in texts if r == "user")
    prior_tool_calls = []
    saw_tool_result = False
    for msg in body.get("messages") or []:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                prior_tool_calls.append((tc.get("function") or {}).get("name"))
        if msg.get("role") == "tool":
            saw_tool_result = True

    def content_msg(text: str) -> dict:
        return {"role": "assistant", "content": text}

    def tool_msg(name: str, args: dict) -> dict:
        return {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_" + uuid.uuid4().hex[:12], "type": "function",
            "function": {"name": name,
                         "arguments": json.dumps(args, ensure_ascii=False)}}]}

    if has_tools:
        if prior_tool_calls or saw_tool_result:
            # after the render tool result -> final text for the turn
            return _completion(content_msg(
                "渲染工具已执行完毕。已按要求仅调用一次 vimax_render_video，"
                "结果如上。"))
        return _completion(tool_msg("vimax_render_video",
                                    {"session_id": SESSION_ID}))

    # inner LangChain (PydanticOutputParser JSON text) — route by prompt
    blob = system + "\n" + "\n".join(t for _, t in texts)
    if "select the most suitable reference images" in blob:
        payload = {"ref_image_indices": [0],
                   "text_prompt": "synthetic reference-consistent keyframe"}
    elif "visual assessment expert" in blob:
        payload = {"best_image_index": 0, "reason": "synthetic candidate 0"}
    else:
        payload = {"ref_image_indices": [0], "text_prompt": "synthetic"}
    return _completion(content_msg(json.dumps(payload, ensure_ascii=False)))


def _completion(message: dict) -> dict:
    return {
        "id": "chatcmpl-fake-" + uuid.uuid4().hex[:10],
        "object": "chat.completion", "created": int(time.time()),
        "model": "fake-bailian-boundary",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls"
                     if message.get("tool_calls") else "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20,
                  "total_tokens": 70},
    }


# --------------------------------------------------------------------------- #
# HTTP handlers
# --------------------------------------------------------------------------- #

def _auth_ok(request) -> bool:
    return request.headers.get("Authorization") == f"Bearer {FAKE_KEY}"


async def handle_chat(request: web.Request) -> web.StreamResponse:
    if not _auth_ok(request):
        return web.json_response({"error": {"code": "invalid_api_key"}},
                                 status=401)
    body = await request.json()
    return web.json_response(llm_response(body))


async def handle_images(request: web.Request) -> web.StreamResponse:
    if not _auth_ok(request):
        return web.json_response({"error": {"code": "invalid_api_key"}},
                                 status=401)
    body = await request.json()
    refs = body.get("image")
    ref_count = len(refs) if isinstance(refs, list) else (1 if refs else 0)
    seq = len(state["image_creates"])
    name = f"image-{seq:02d}.png"
    make_png(MEDIA / name, "IMG", seq, "candidate")
    state["image_creates"].append({
        "seq": seq, "file": name, "reference_count": ref_count,
        "prompt_sha256": hashlib.sha256(
            str(body.get("prompt", "")).encode()).hexdigest()[:16],
        "url": f"{BASE_URL}/media/{name}"})
    persist_stats()
    return web.json_response({
        "created": int(time.time()),
        "data": [{"url": f"{BASE_URL}/media/{name}"}],
        "usage": {"input_image_count": ref_count,
                  "input_image_type": "qima_input_1k",
                  "output_image_count": 1,
                  "output_image_type": "qima_output_1k",
                  "output_width": IMG_W, "output_height": IMG_H}})


async def handle_video_create(request: web.Request) -> web.StreamResponse:
    if not _auth_ok(request):
        return web.json_response({"error": {"code": "invalid_api_key"}},
                                 status=401)
    if request.headers.get("X-DashScope-Async") != "enable":
        return web.json_response({"code": "BadRequest",
                                  "message": "missing X-DashScope-Async"},
                                 status=400)
    body = await request.json()
    inp = body.get("input") or {}
    prompt = str(inp.get("prompt", ""))
    img_url = str(inp.get("img_url", ""))
    is_transition = "transition between the shots" in prompt.lower() \
        or "two shots" in prompt.lower()
    majors = sum(1 for c in state["video_creates"] if c["kind"] == "major")
    transitions = sum(1 for c in state["video_creates"]
                      if c["kind"] == "transition")
    if is_transition:
        if transitions >= TRANSITION_COUNT:
            return web.json_response(
                {"code": "BudgetExceeded",
                 "message": f"fake transition budget ({TRANSITION_COUNT})"},
                status=400)
        clip = f"transition-{transitions:02d}.mp4"
        kind = "transition"
    else:
        if majors >= MAJOR_COUNT:
            return web.json_response(
                {"code": "BudgetExceeded",
                 "message": f"fake major budget ({MAJOR_COUNT})"}, status=400)
        clip = f"major-{majors:02d}.mp4"
        kind = "major"
    img_sha = hashlib.sha256(img_url.encode()).hexdigest()[:16]
    task_id = "fake-task-" + uuid.uuid4().hex[:12]
    tasks[task_id] = {"kind": kind, "clip": clip, "polls": 0}
    state["video_creates"].append({
        "task_id": task_id, "kind": kind, "clip": clip,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "img_url_sha256": img_sha,
        "prompt_head": prompt[:80]})
    persist_stats()
    return web.json_response({
        "output": {"task_id": task_id, "task_status": "PENDING"},
        "request_id": "fake-req-" + uuid.uuid4().hex[:10]})


async def handle_poll(request: web.Request) -> web.StreamResponse:
    if not _auth_ok(request):
        return web.json_response({"error": {"code": "invalid_api_key"}},
                                 status=401)
    task_id = request.match_info["task_id"]
    task = tasks.get(task_id)
    if task is None:
        return web.json_response(
            {"output": {"task_id": task_id, "task_status": "UNKNOWN"}},
            status=200)
    task["polls"] += 1
    if task["polls"] <= POLL_RUNNING_ROUNDS:
        return web.json_response(
            {"output": {"task_id": task_id, "task_status": "RUNNING"},
             "request_id": "fake-req-" + uuid.uuid4().hex[:10]})
    return web.json_response({
        "output": {"task_id": task_id, "task_status": "SUCCEEDED",
                   "video_url": f"{BASE_URL}/media/{task['clip']}"},
        "usage": {"video_count": 1, "duration": CLIP_SECONDS, "SR": 720,
                  "input_video_duration": 0,
                  "output_video_duration": CLIP_SECONDS, "audio": False},
        "request_id": "fake-req-" + uuid.uuid4().hex[:10]})


async def handle_media(request: web.Request) -> web.StreamResponse:
    state["media_downloads"] += 1
    name = request.match_info["name"]
    path = (MEDIA / name).resolve()
    if not str(path).startswith(str(MEDIA.resolve())) or not path.is_file():
        return web.Response(status=404)
    ctype = "video/mp4" if name.endswith(".mp4") else "image/png"
    return web.FileResponse(path, headers={"Content-Type": ctype})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/compatible-mode/v1/chat/completions", handle_chat)
    app.router.add_post("/compatible-mode/v1/images/generations", handle_images)
    app.router.add_post("/api/v1/services/aigc/video-generation/video-synthesis",
                        handle_video_create)
    app.router.add_get("/api/v1/tasks/{task_id}", handle_poll)
    app.router.add_get("/media/{name}", handle_media)

    async def handle_health(request: web.Request) -> web.StreamResponse:
        return web.json_response({"ok": True, "media_ready":
                                  (MEDIA / "READY").exists()})
    app.router.add_get("/health", handle_health)
    return app


def main() -> int:
    prepare_media()
    persist_stats()
    print(f"fake bailian boundary on 127.0.0.1:{PORT}", file=sys.stderr,
          flush=True)
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
