#!/usr/bin/env python3
"""Fake Bailian boundary for the VideoWeaver offline cold-start acceptance.

Serves on 127.0.0.1 ONLY (the task container runs with --network none; the
runner maps a provider-keyword fake host to loopback via --add-host). It
replaces EXACTLY the external API boundary:
  - POST /compatible-mode/v1/responses          (Bailian Responses for Codex CLI)
  - POST /compatible-mode/v1/images/generations (Bailian images)
  - POST /api/v1/services/aigc/video-generation/video-synthesis (create)
  - GET  /api/v1/tasks/{task_id}                (poll)
  - GET  /media/...                             (produced media downloads)

Everything else is the REAL production path: pipeline.py, the real Codex
binary, real skill discovery/scripts, real FFmpeg, real merge-video.

The fake "model" drives the real Codex agent by emitting exec_command
function calls in the Responses protocol. A state machine watches the real
output directory and, in order, commands:
  image-gen  -> 8 first-frame images (shot{N}_firstframe.jpg)
  video-gen  -> 8 clips (shot{N}.mp4)
  merge-video -> final.mp4
Once final.mp4 exists the fake returns a plain text completion so Codex
finishes its turn.

Rejected-mode behaviour is exercised by the real adapter scripts (they raise
before sending); this server only sees valid requests in the happy path.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from io import BytesIO

from PIL import Image

PORT = int(os.environ.get("FAKE_PORT", "8666"))
MEDIA_HOST = os.environ.get("VW_FAKE_MEDIA_HOST", f"http://127.0.0.1:{PORT}")
CASE_TXT = os.environ.get("VW_CASE_TXT", "")
OUTPUT_DIR = os.environ.get("VW_FAKE_OUTPUT_DIR", "")
STATE_PATH = os.environ.get("VW_FAKE_STATE_PATH", "")
FAKE_KEY = "fake-offline-key"
IMG_SIZE = (1280, 720)
CLIP = {"w": 1280, "h": 720, "fps": 30, "s": 5}

SHOT_RE = re.compile(
    r"Shot\s+(\d+)\s*\(Scene\s+\d+\):\s*"
    r"First frame:\s*(.*?)\s*Shot action:\s*(.*?)(?=\nShot\s|\Z)",
    re.S)

state = {
    "responses_calls": 0,
    "image_creates": [],
    "video_creates": [],
    "media_downloads": 0,
    "rejected_unknown_hosts": [],
    "last_payload_seen": None,
    "started_monotonic": time.monotonic(),
}
tasks: dict[str, dict] = {}
MAX_RESPONSES = int(os.environ.get("VW_FAKE_MAX_RESPONSES", "60"))
FIRST_CMD = os.environ.get("VW_FAKE_FIRST_COMMAND", "")
DEBUG_ENV = os.environ.get("VW_FAKE_DEBUG_ENV", "")


def persist_state():
    if not STATE_PATH:
        return
    Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(STATE_PATH).write_text(json.dumps(state, ensure_ascii=False, indent=2))


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    if STATE_PATH:
        (Path(STATE_PATH).parent / "fake-server.log").open("a").write(line + "\n")


def load_shots() -> list[dict]:
    """Parse 8 shots {first, action} from the case task text."""
    txt = Path(CASE_TXT).read_text(encoding="utf-8")
    matches = SHOT_RE.findall(txt)
    shots = []
    for n, first, action in matches:
        first = " ".join(first.split())
        action = " ".join(action.split())
        shots.append({"num": int(n), "first": first, "action": action})
    return shots


def session_dirs():
    root = Path(OUTPUT_DIR)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime, reverse=True)


def missing_first_frame(shots) -> tuple[int, str] | None:
    dirs = session_dirs()
    if not dirs:
        return 1, str(OUTPUT_DIR)
    for d in dirs:
        for s in shots:
            img = d / "images" / f"shot{s['num']}_firstframe.jpg"
            if not img.exists():
                return s["num"], str(d)
    return None


def missing_clip(shots) -> tuple[int, str] | None:
    dirs = session_dirs()
    if not dirs:
        return 1, str(OUTPUT_DIR)
    for d in dirs:
        videos = d / "videos"
        if not videos.is_dir():
            for s in shots:
                if not (videos / f"shot{s['num']}.mp4").exists():
                    return s["num"], str(d)
            continue
        for s in shots:
            if not (videos / f"shot{s['num']}.mp4").exists():
                return s["num"], str(d)
    return None


def final_exists():
    for d in session_dirs():
        if (d / "videos" / "final.mp4").exists():
            return str(d / "videos" / "final.mp4")
        for p in d.rglob("final.mp4"):
            return str(p)
    return None


def build_exec_command(cmd: str, workdir: str) -> dict:
    cid = "call_" + uuid.uuid4().hex[:16]
    return {
        "id": cid,
        "type": "function_call",
        "status": "completed",
        "name": "exec_command",
        "arguments": json.dumps({"cmd": cmd, "workdir": workdir}),
        "call_id": cid,
        "parallel_tool_calls": False,
    }


def next_command(shots) -> tuple[dict | None, str]:
    """Return (function_call item, note) for the next real skill command."""
    frames = missing_first_frame(shots)
    if frames:
        n, d = frames
        cmd = (f"{PYTHON} /opt/videoweaver/skills/image-gen/scripts/generate.py "
               f"--prompt {json.dumps(shots[n-1]['first'])} "
               f"--output_file_name shot{n}_firstframe.jpg "
               f"--model qwen-image-3.0 --ratio 16:9 --resolution 2k")
        return build_exec_command(cmd, "/opt/videoweaver/_codex_workspace"), f"image-gen shot{n}"

    clips = missing_clip(shots)
    if clips:
        n, d = clips
        img = str(Path(d) / "images" / f"shot{n}_firstframe.jpg")
        cmd = (f"{PYTHON} /opt/videoweaver/skills/video-gen/scripts/generate.py "
               f"--prompt {json.dumps(shots[n-1]['action'])} "
               f"--first-image {json.dumps(img)} "
               f"--model wan2.6-i2v-flash "
               f"--output shot{n}.mp4 --ratio 16:9 --resolution 720p --duration 5 "
               f"--poll-interval 1")
        return build_exec_command(cmd, "/opt/videoweaver/_codex_workspace"), f"video-gen shot{n}"

    fin = final_exists()
    if not fin:
        clips_paths = []
        for d in session_dirs():
            v = d / "videos"
            if v.is_dir():
                for s in shots:
                    p = v / f"shot{s['num']}.mp4"
                    if p.exists():
                        clips_paths.append(str(p))
        if len(clips_paths) == 8:
            cmd = (f"{PYTHON} /opt/videoweaver/skills/merge-video/scripts/merge_videos.py "
                   f"--video_paths {' '.join(json.dumps(p) for p in clips_paths)} "
                   f"--output_filename final.mp4")
            return build_exec_command(cmd, "/opt/videoweaver/_codex_workspace"), "merge-video"
        return None, "waiting-for-clips"

    return None, f"done:{fin}"


# ---- media synthesis (fake) ----

_media_cache: dict[str, bytes] = {}
_media_lock = threading.Lock()


def fake_image_bytes(label: str) -> bytes:
    img = Image.new("RGB", IMG_SIZE, (40, 40, 40))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    color = (60 + (hashlib.md5(label.encode()).digest()[0] % 160),
             60 + (hashlib.md5(label.encode()).digest()[1] % 160),
             120 + (hashlib.md5(label.encode()).digest()[2] % 120))
    draw.rectangle([80, 80, IMG_SIZE[0] - 80, IMG_SIZE[1] - 80], fill=color)
    draw.text((IMG_SIZE[0] // 2 - 60, IMG_SIZE[1] // 2 - 8), label, fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def fake_clip_bytes(label: str) -> bytes:
    """5s 1280x720 30fps libx264 yuv420p silent clip, distinct per shot."""
    color = (60 + (hashlib.md5(label.encode()).digest()[0] % 160),
             60 + (hashlib.md5(label.encode()).digest()[1] % 160),
             120 + (hashlib.md5(label.encode()).digest()[2] % 120))
    hexcol = "#%02x%02x%02x" % color
    out = f"/tmp/vw-fake-{label}.mp4"
    if os.path.exists(out):
        return Path(out).read_bytes()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=c={hexcol}:s=1280x720:r=30:d=5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out],
        check=True)
    return Path(out).read_bytes()


# ---- HTTP handlers ----

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence default stderr noise
        log("http: " + (fmt % args))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {"_raw": raw.decode("utf-8", "replace")[:2000]}

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, events):
        """events: list of (event_name, data_dict)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for name, data in events:
            self.wfile.write(f"event: {name}\n".encode())
            self.wfile.write(("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode())
        self.wfile.flush()

    def _response_id(self):
        return "resp_" + uuid.uuid4().hex[:24]

    # ---- Responses ----

    def handle_responses(self):
        state["responses_calls"] += 1
        payload = self._read_json()
        state["last_payload_seen"] = {
            "keys": sorted(payload.keys()),
            "model": payload.get("model"),
            "input_len": len(payload.get("input") or []),
        }
        persist_state()
        if state["responses_calls"] > MAX_RESPONSES:
            # Guard against a stalled loop (e.g. media not landing in the
            # output dir); fail loudly instead of looping forever.
            rid = self._response_id()
            item_msg = {
                "id": "msg_" + uuid.uuid4().hex[:16],
                "type": "message", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": (
                    f"STALLED: fake boundary exceeded {MAX_RESPONSES} responses "
                    "without completing the media chain."), "annotations": []}],
            }
            resp_obj = {"id": rid, "object": "response", "created_at": int(time.time()),
                        "status": "completed", "model": payload.get("model", "qwen3.7-plus"),
                        "output": [item_msg], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}
            self._sse([("response.created", {"type": "response.created", "response": resp_obj}),
                       ("response.in_progress", {"type": "response.in_progress", "response": resp_obj}),
                       ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item_msg}),
                       ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item_msg}),
                       ("response.completed", {"type": "response.completed", "response": resp_obj})])
            return
        shots = load_shots()
        rid = self._response_id()
        if DEBUG_ENV and state["responses_calls"] == 2:
            item = build_exec_command("env | sort", "/opt/videoweaver/_codex_workspace")
            note = "debug-env-dump"
        else:
            item, note = next_command(shots)
            if item is None and note.startswith("waiting"):
                # Clips missing but frames done and clips not all present; wait turn.
                item, note = next_command(shots)

        usage = {
            "input_tokens": 1200,
            "output_tokens": 180,
            "total_tokens": 1380,
        }
        if item is None:
            # Final completion: report the produced media and finish the turn.
            fin = final_exists() or ""
            text = (f"任务完成。最终视频: {fin}\n"
                    f"镜头: 8 段，顺序 shot1..shot8，约40秒，1280x720，30fps，无音轨。\n"
                    f"（fake 边界：本结果由禁网 fake 模型驱动真实技能执行生成。）")
            item_msg = {
                "id": "msg_" + uuid.uuid4().hex[:16],
                "type": "message", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
            resp_obj = {
                "id": rid, "object": "response", "created_at": int(time.time()),
                "status": "completed", "model": payload.get("model", "qwen3.7-plus"),
                "output": [item_msg], "usage": usage,
            }
            events = [
                ("response.created", {"type": "response.created", "response": resp_obj}),
                ("response.in_progress", {"type": "response.in_progress", "response": resp_obj}),
                ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item_msg}),
                ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item_msg}),
                ("response.completed", {"type": "response.completed", "response": resp_obj}),
            ]
            self._sse(events)
            return

        resp_obj = {
            "id": rid, "object": "response", "created_at": int(time.time()),
            "status": "in_progress", "model": payload.get("model", "qwen3.7-plus"),
            "output": [item], "usage": usage,
        }
        events = [
            ("response.created", {"type": "response.created", "response": resp_obj}),
            ("response.in_progress", {"type": "response.in_progress", "response": resp_obj}),
            ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item}),
            ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
            ("response.completed", {"type": "response.completed", "response": resp_obj}),
        ]
        self._sse(events)

    def handle_chat(self):
        # chat/completions used by the real summary_txt.py (ReAct_process.txt)
        payload = self._read_json()
        state["chat_completions"] = state.get("chat_completions", 0) + 1
        persist_state()
        self._send_json(200, {
            "choices": [{"message": {"role": "assistant",
                                     "content": "[fake] 已根据 ReAct 过程生成摘要。"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        })

    # ---- images ----

    def handle_images(self):
        payload = self._read_json()
        label = "img_" + hashlib.md5((payload.get("prompt") or "").encode()).hexdigest()[:8]
        body = fake_image_bytes(label)
        name = f"{label}.png"
        with _media_lock:
            _media_cache[name] = body
        state["image_creates"].append({"label": label, "prompt_sha": hashlib.sha256(
            (payload.get("prompt") or "").encode()).hexdigest(), "size": IMG_SIZE})
        persist_state()
        self._send_json(200, {
            "usage": {"output_image_count": 1, "output_tokens": 64},
            "data": [{"url": f"{MEDIA_HOST}/media/{name}", "b64_json": None}],
        })

    # ---- video create / poll / download ----

    def handle_video_create(self):
        payload = self._read_json()
        task_id = str(uuid.uuid4())
        tasks[task_id] = {"status": "RUNNING", "polls": 0,
                          "prompt_sha": hashlib.sha256(
                              (payload.get("input") or {}).get("prompt", "").encode()).hexdigest(),
                          "first_frame_sha": hashlib.sha256(
                              (payload.get("input") or {}).get("img_url", "").encode()).hexdigest()}
        rec = {"task_id": task_id, "t": round(time.time(), 3), **tasks[task_id]}
        state["video_creates"].append(rec)
        persist_state()
        self._send_json(200, {
            "output": {"task_id": task_id, "task_status": "RUNNING"},
            "request_id": "req_" + uuid.uuid4().hex[:24],
        })

    def handle_task(self, task_id):
        task = tasks.get(task_id)
        if task is None:
            self._send_json(404, {"output": {"task_status": "UNKNOWN"}, "message": "unknown task"})
            return
        task["polls"] += 1
        if task["polls"] >= 2:
            task["status"] = "SUCCEEDED"
            label = f"shot{task['polls']}"
            with _media_lock:
                _media_cache.setdefault(f"{task_id}.mp4", fake_clip_bytes(task_id[:8]))
            self._send_json(200, {
                "output": {"task_id": task_id, "task_status": "SUCCEEDED",
                           "video_url": f"{MEDIA_HOST}/media/{task_id}.mp4"},
                "usage": {"video_count": 1, "duration": 5, "resolution": "720P", "audio": False},
            })
            return
        self._send_json(200, {"output": {"task_id": task_id, "task_status": "RUNNING"}})

    def handle_media(self):
        name = self.path.split("/media/", 1)[-1]
        data = None
        with _media_lock:
            data = _media_cache.get(name)
        if data is None:
            if name.endswith(".mp4"):
                data = fake_clip_bytes(name[:8])
            else:
                data = fake_image_bytes(name)
            _media_cache[name] = data
        state["media_downloads"] += 1
        persist_state()
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4" if name.endswith(".mp4") else "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/").endswith("/compatible-mode/v1/responses"):
            self.handle_responses()
        elif self.path.rstrip("/").endswith("/compatible-mode/v1/images/generations"):
            self.handle_images()
        elif self.path.rstrip("/").endswith("/compatible-mode/v1/chat/completions"):
            self.handle_chat()
        elif self.path.rstrip("/").endswith("/api/v1/services/aigc/video-generation/video-synthesis"):
            self.handle_video_create()
        else:
            state["rejected_unknown_hosts"].append(self.path)
            persist_state()
            self._send_json(404, {"message": f"unknown path {self.path}"})

    def do_GET(self):
        if self.path.startswith("/api/v1/tasks/"):
            self.handle_task(self.path.split("/")[-1])
        elif self.path.startswith("/media/"):
            self.handle_media()
        else:
            state["rejected_unknown_hosts"].append(self.path)
            persist_state()
            self._send_json(404, {"message": f"unknown path {self.path}"})


PYTHON = os.environ.get("VW_PYTHON", "/opt/videoweaver-venv/bin/python")


def main():
    if not CASE_TXT or not OUTPUT_DIR:
        raise SystemExit("VW_CASE_TXT and VW_FAKE_OUTPUT_DIR are required")
    shots = load_shots()
    log(f"fake responses server on 127.0.0.1:{PORT}, shots={len(shots)}, "
        f"output={OUTPUT_DIR}, python={PYTHON}, FIRST_CMD={FIRST_CMD!r}, "
        f"MAX_RESPONSES={MAX_RESPONSES}")
    if len(shots) != 8:
        raise SystemExit(f"expected 8 shots, got {len(shots)}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
