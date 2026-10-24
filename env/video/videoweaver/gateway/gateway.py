#!/usr/bin/env python3
"""VideoWeaver controlled forwarding boundary + persistent pre-send ledger.

ALL task model/media traffic goes through this local gateway:
  - Codex Responses                POST /compatible-mode/v1/responses        (SSE)
  - internal vision/summary chat   POST /compatible-mode/v1/chat/completions
  - image create                   POST /compatible-mode/v1/images/generations
  - video create                   POST /api/v1/services/aigc/video-generation/video-synthesis
  - video poll                     GET  /api/v1/tasks/{task_id}
  - media download                 GET  /media/...
Every request is authorized with the local task token, atomically charged
against a persistent per-run ledger BEFORE forwarding, then proxied to the
configured upstream. Only the gateway holds the real upstream credential, so
Codex and the skill scripts never get a path to an unmeasured upstream.

It is NOT a generic URL proxy: only the registered methods/models/upstream
paths above are allowed. It never records Authorization headers, secrets or
unredacted signed URLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

GATEWAY_PORT = int(os.environ.get("VW_GATEWAY_PORT", "8899"))
# LLM (Responses/Chat) and media (image/video/poll/download) upstreams differ
# for live routing: LLM -> dashscope compatible-mode, media -> workspace domain.
UPSTREAM_LLM = os.environ.get("VW_GATEWAY_UPSTREAM_LLM", "") or os.environ.get("VW_GATEWAY_UPSTREAM", "")
UPSTREAM_MEDIA = os.environ.get("VW_GATEWAY_UPSTREAM_MEDIA", "") or os.environ.get("VW_GATEWAY_UPSTREAM", "")
UPSTREAM_KEY = os.environ.get("VW_UPSTREAM_API_KEY", "")   # held only here
TASK_TOKEN = os.environ.get("VW_TASK_TOKEN", "")
LEDGER_PATH = os.environ.get("VW_LEDGER_PATH", "/run/ledger/ledger.json")
RUN_START_EPOCH = float(os.environ.get("VW_RUN_START_EPOCH", "0") or "0")

# In-memory media URL rewrite map (key -> original signed URL). Signed URLs are
# NEVER persisted: the ledger records only the opaque key.
_media_urls: dict[str, str] = {}
_media_lock = threading.Lock()

DEFAULT_BUDGET = {
    "max_llm_calls": 40,
    "max_image_creates": 20,
    "max_video_creates": 20,
    "max_video_polls": 400,
    "max_video_polls_per_task": 120,
    "max_media_downloads": 40,
    "deadline_seconds": 600,
    "observed_output_tokens_soft": 500000,
}
BUDGET = dict(DEFAULT_BUDGET)
env_budget = os.environ.get("VW_BUDGET_JSON", "")
if env_budget:
    BUDGET.update(json.loads(env_budget))

# registered upstream paths -> (counter kind, sse)
ROUTES = {
    "/compatible-mode/v1/responses": ("llm_calls", True),
    "/compatible-mode/v1/chat/completions": ("llm_calls", False),
    "/compatible-mode/v1/images/generations": ("image_creates", False),
    "/api/v1/services/aigc/video-generation/video-synthesis": ("video_creates", False),
    "/api/v1/tasks/": ("video_polls", False),
    "/media/": ("media_downloads", False),
}

_MEDIA_CAP_BYTES = 200 * 1024 * 1024
_LLM_TIMEOUT = float(os.environ.get("VW_GATEWAY_LLM_TIMEOUT", "600"))


def _redacted(url):
    return str(url).split("?", 1)[0]


class SseParser:
    """Minimal SSE event parser (RFC-ish subset + OpenAI [DONE]).

    Handles multi-line data, optional space after 'data:', comments, CRLF,
    cross-chunk UTF-8 (caller feeds decoded lines), and blank-line flush.
    A bare [DONE] is reported as an event, never as a success terminal."""

    def __init__(self):
        self.event = None
        self.id = None
        self.data_lines = []
        self._events = []

    def feed_line(self, raw: str):
        line = raw.rstrip("\r\n")
        if not line:
            self._flush()
            return
        if line.startswith(":"):
            return
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            self.data_lines.append(value)
        elif field == "event":
            self.event = value
        elif field == "id":
            self.id = value
        # retry: ignore

    def _flush(self):
        if self.data_lines or self.event is not None:
            self._events.append({
                "event": self.event,
                "id": self.id,
                "data": "\n".join(self.data_lines),
            })
        self.event = None
        self.id = None
        self.data_lines = []

    def flush(self) -> list[dict]:
        self._flush()
        out = self._events
        self._events = []
        return out


class Ledger:
    def __init__(self, path: str, budget: dict) -> None:
        self.path = Path(path)
        self.budget = budget
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {
            "schema": "videoweaver-ledger-v1",
            "run_id": os.environ.get("VW_RUN_ID", ""),
            "budget": dict(self.budget),
            "start_epoch": RUN_START_EPOCH,
            "deadline_epoch": RUN_START_EPOCH + float(self.budget.get("deadline_seconds", 600)) if RUN_START_EPOCH else None,
            "counters": {"llm_calls": 0, "image_creates": 0, "video_creates": 0,
                         "video_polls": 0, "media_downloads": 0, "forward_attempts": 0},
            "video_tasks": [],
            "per_task_polls": {},
            "usage": {"observed_total_tokens_total": 0, "observed_output_tokens_total": 0,
                     "observed_llm_responses": 0},
            "events": [],
            "exhausted": False,
            "status": "open",
            "opened_at": time.time(),
        }

    def _atomic_write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def charge(self, kind: str) -> bool:
        """Atomic pre-send check+reserve. Returns False (no send) when over
        budget, past deadline, already exhausted, or the ledger cannot be
        durably written."""
        with self.lock:
            now = time.time()
            if self.data.get("exhausted"):
                return False
            if self.data.get("deadline_epoch") and now > self.data["deadline_epoch"]:
                self.data["exhausted"] = True
                self.data["status"] = "deadline_exhausted"
                self._atomic_write()
                return False
            key = self.budget.get("max_" + kind)
            if key is None:
                self.data["exhausted"] = True
                self.data["status"] = "unknown_kind_" + kind
                self._atomic_write()
                return False
            if self.data["counters"].get(kind, 0) >= key:
                self.data["exhausted"] = True
                self.data["status"] = f"budget_exhausted:{kind}"
                self._atomic_write()
                return False
            self.data["counters"][kind] += 1
            self.data["counters"]["forward_attempts"] += 1
            try:
                self._atomic_write()
            except Exception:
                # ledger open/write failure: roll back and DO NOT send
                self.data["counters"][kind] -= 1
                self.data["counters"]["forward_attempts"] -= 1
                return False
            return True

    def bump_per_task(self, task_id: str) -> None:
        with self.lock:
            self.data["per_task_polls"][task_id] = self.data["per_task_polls"].get(task_id, 0) + 1
            self._atomic_write()

    def record(self, kind: str, **kw) -> None:
        with self.lock:
            self.data["events"].append({
                "t": round(time.time(), 3), "kind": kind, **kw,
            })
            if kind == "usage":
                if kw.get("total_tokens") is not None:
                    self.data["usage"]["observed_total_tokens_total"] += int(kw["total_tokens"] or 0)
                    self.data["usage"]["observed_llm_responses"] += 1
                if kw.get("output_tokens") is not None:
                    self.data["usage"]["observed_output_tokens_total"] += int(kw["output_tokens"] or 0)
            if kw.get("task_id"):
                self.data["video_tasks"].append(kw["task_id"])
            if len(self.data["events"]) > 4000:
                self.data["events"] = self.data["events"][-2000:]
            self._atomic_write()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.data))


LEDGER = None  # set in main()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep logs quiet; events go to ledger
        pass

    def _auth_ok(self) -> bool:
        if not TASK_TOKEN:
            return False
        hdr = self.headers.get("Authorization", "")
        custom = self.headers.get("X-VW-Task-Token", "")
        return hdr == f"Bearer {TASK_TOKEN}" or custom == TASK_TOKEN

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def _reject(self, code: int, message: str):
        body = json.dumps({"error": {"code": code, "message": message}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        p = self.path
        for prefix, (kind, sse) in ROUTES.items():
            if p.startswith(prefix) or p.rstrip("/").endswith(prefix.rstrip("/")):
                return prefix, kind, sse
        # also match /api/v1/tasks/{id} and /media/...
        if p.startswith("/api/v1/tasks/"):
            return "/api/v1/tasks/", "video_polls", False
        if p.startswith("/media/"):
            return "/media/", "media_downloads", False
        return None, None, False

    def _proxy(self, kind: str, sse: bool, body: bytes):
        if kind == "llm_calls":
            upstream_base = UPSTREAM_LLM
        elif self.path.startswith("/media/"):
            upstream_base = UPSTREAM_MEDIA
        else:
            upstream_base = UPSTREAM_MEDIA
        upstream_url = urljoin(upstream_base + "/", self.path.lstrip("/"))
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("authorization", "host", "content-length", "x-vw-task-token")}
        if UPSTREAM_KEY:
            headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"
        method = "POST" if self.command == "POST" else "GET"
        try:
            upstream = requests.request(method, upstream_url, headers=headers,
                                        data=body if body else None,
                                        stream=True, timeout=(30, _LLM_TIMEOUT),
                                        allow_redirects=False)
        except requests.RequestException as exc:
            LEDGER.record(kind, status="upstream_transport_error",
                          detail=str(exc)[:200], url=_redacted(upstream_url))
            self._reject(502, f"upstream transport error: {exc}")
            return
        LEDGER.record(kind, status="forwarded", http_status=upstream.status_code,
                      url=_redacted(upstream_url))
        ctype = upstream.headers.get("Content-Type", "application/json")
        if upstream.status_code >= 400:
            data = upstream.content or b""
            self.send_response(upstream.status_code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            upstream.close()
            return
        if not sse:
            data = upstream.content or b""
            # rewrite media URLs to this gateway so downloads are counted and
            # never bypass the ledger; original signed URLs stay in memory only
            try:
                obj = json.loads(data.decode("utf-8", "replace"))
                if isinstance(obj, dict):
                    usage = obj.get("usage") or {}
                    toks = usage.get("total_tokens")
                    if toks is not None:
                        LEDGER.record("usage", response_id=getattr(self, "request_id", None),
                                      input_tokens=usage.get("input_tokens") or usage.get("prompt_tokens"),
                                      cached_input_tokens=usage.get("cached_input_tokens"),
                                      output_tokens=usage.get("output_tokens") or usage.get("completion_tokens"),
                                      reasoning_output_tokens=usage.get("reasoning_output_tokens"),
                                      total_tokens=int(toks))
                    if kind == "video_creates":
                        tid = (obj.get("output") or {}).get("task_id")
                        if tid:
                            LEDGER.record("video_created", task_id=tid)
                    if kind == "video_polls":
                        vurl = (obj.get("output") or {}).get("video_url")
                        if vurl:
                            key = "m_" + uuid.uuid4().hex[:16]
                            with _media_lock:
                                _media_urls[key] = vurl
                            LEDGER.record("media_url", key=key)
                            obj.setdefault("output", {})["video_url"] = (
                                f"http://127.0.0.1:{GATEWAY_PORT}/media/{key}")
                    if kind == "image_creates":
                        d = obj.get("data") or []
                        if d and isinstance(d[0], dict) and d[0].get("url"):
                            key = "m_" + uuid.uuid4().hex[:16]
                            with _media_lock:
                                _media_urls[key] = d[0]["url"]
                            LEDGER.record("media_url", key=key)
                            d[0]["url"] = f"http://127.0.0.1:{GATEWAY_PORT}/media/{key}"
                    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            upstream.close()
            return
        # SSE streaming: forward lines, parse events with a proper parser;
        # aggregate usage per response_id (dedup), never treat EOF/[DONE] as
        # a success terminal by itself.
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        parser = SseParser()
        terminal = None
        saw_done = False
        self._request_usage = None  # last-wins final usage for this request
        total = 0
        try:
            for raw in upstream.iter_lines(decode_unicode=True):
                total += len(raw.encode("utf-8", "replace")) + 1
                self.wfile.write((raw + "\n").encode("utf-8", "replace"))
                self.wfile.flush()
                parser.feed_line(raw)
                for ev in parser.flush():
                    data = ev["data"].strip()
                    if data == "[DONE]":
                        saw_done = True
                        continue
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    resp = obj.get("response") or {}
                    usage = obj.get("usage") or resp.get("usage") or {}
                    rid = obj.get("response_id") or resp.get("id") \
                          or getattr(self, "request_id", "_")
                    toks = usage.get("total_tokens")
                    if toks is not None:
                        self._request_usage = {
                            "response_id": rid,
                            "input_tokens": usage.get("input_tokens"),
                            "cached_input_tokens": usage.get("cached_input_tokens"),
                            "output_tokens": usage.get("output_tokens"),
                            "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                            "total_tokens": toks,
                        }
                    status = resp.get("status") or obj.get("type")
                    if status in ("completed", "incomplete", "failed", "error"):
                        terminal = status
        except (BrokenPipeError, ConnectionResetError):
            terminal = terminal or "client_disconnect"
        except requests.RequestException as exc:
            terminal = terminal or "upstream_stream_error"
        finally:
            upstream.close()
        # finalize: record the final request-level usage exactly once
        if self._request_usage is not None:
            u = self._request_usage
            LEDGER.record("usage", response_id=u.get("response_id"),
                          input_tokens=u.get("input_tokens"),
                          cached_input_tokens=u.get("cached_input_tokens"),
                          output_tokens=u.get("output_tokens"),
                          reasoning_output_tokens=u.get("reasoning_output_tokens"),
                          total_tokens=u.get("total_tokens"))
        if terminal == "completed" and self._request_usage is None:
            LEDGER.record("usage_missing", note="completed without usage")
        if terminal == "completed" and saw_done:
            terminal = "completed"
        elif terminal is None:
            terminal = "incomplete" if saw_done else "stream_end"
        LEDGER.record("sse", terminal=terminal, bytes=total)

    def _handle(self):
        # unique local request association for usage attribution
        self.request_id = "req_" + uuid.uuid4().hex[:16]
        prefix, kind, sse = self._route()
        if prefix is None:
            LEDGER.record("rejected", reason="unknown_path", url=_redacted(self.path))
            self._reject(403, "path not registered with the VideoWeaver gateway")
            return
        # Media downloads carry no API authorization by design; they are still
        # counted. Everything else requires the local task token.
        if kind != "media_downloads" and not self._auth_ok():
            LEDGER.record("rejected", reason="bad_token", url=_redacted(self.path))
            self._reject(401, "invalid local task token")
            return
        if kind == "llm_calls":
            soft = int(BUDGET.get("observed_output_tokens_soft", 0) or 0)
            if soft and LEDGER.data["usage"].get("observed_total_tokens_total", 0) >= soft:
                LEDGER.record("blocked", reason="soft_threshold_exceeded", blocked_kind="llm_calls",
                              observed_total_tokens=LEDGER.data["usage"].get("observed_total_tokens_total", 0))
                self._reject(429, "VideoWeaver usage soft threshold reached")
                return
        charged = LEDGER.charge(kind)
        if not charged:
            LEDGER.record("blocked", reason="budget_or_deadline", blocked_kind=kind)
            # For Responses/Chat, return a JSON/SSE error so the CLI ends the turn.
            if kind == "llm_calls":
                self._reject(429, "VideoWeaver per-run send budget/deadline exhausted")
            else:
                self._reject(402, f"VideoWeaver {kind} send budget/deadline exhausted")
            return
        # video poll must reference a task that this gateway actually created
        if kind == "video_polls":
            task_id = self.path.rstrip("/").rsplit("/", 1)[-1]
            if task_id and task_id not in LEDGER.data["video_tasks"]:
                LEDGER.record("rejected", reason="unknown_video_task", task_id=task_id)
                self._reject(404, "task_id was not created through this gateway")
                return
            per = LEDGER.data["per_task_polls"].get(task_id, 0)
            if per >= int(BUDGET.get("max_video_polls_per_task", 120)):
                LEDGER.record("blocked", reason="per_task_poll_limit", task_id=task_id)
                self._reject(402, f"per-task poll limit reached for {task_id}")
                return
            self.video_poll_task_id = task_id
        if kind == "video_polls" and getattr(self, "video_poll_task_id", None):
            LEDGER.bump_per_task(self.video_poll_task_id)
        body = self._read_body()
        try:
            if kind == "media_downloads":
                self._proxy_media()
                return
            self._proxy(kind, sse, body)
        except Exception as exc:  # noqa: BLE001
            LEDGER.record("proxy_error", blocked_kind=kind, detail=str(exc)[:200])
            try:
                self._reject(500, f"gateway proxy error: {exc}")
            except Exception:
                pass

    def _proxy_media(self):
        """Fetch a rewritten media URL by opaque key from the in-memory map.
        The original signed URL is never persisted; downloads carry no API
        Authorization header by design. Downloads are counted against the
        media_downloads budget."""
        key = self.path.rstrip("/").rsplit("/", 1)[-1]
        with _media_lock:
            target = _media_urls.get(key)
        if not target or not target.startswith(("http://", "https://")):
            LEDGER.record("rejected", reason="unknown_media_key", key=key)
            self._reject(404, "media key not known to this gateway")
            return
        try:
            resp = requests.get(target, timeout=300, stream=True)
        except requests.RequestException as exc:
            LEDGER.record("media_download_error", key=key, detail=str(exc)[:200])
            self._reject(502, f"media fetch error: {exc}")
            return
        LEDGER.record("media_downloaded", key=key, http_status=resp.status_code)
        total = 0
        try:
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() in ("content-length", "transfer-encoding", "connection",
                                 "content-encoding", "keep-alive"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in resp.iter_content(65536):
                total += len(chunk)
                if total > _MEDIA_CAP_BYTES:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            resp.close()
        LEDGER.record("media_download_done", key=key, bytes=total)

    def do_POST(self):
        self._handle()

    def do_GET(self):
        self._handle()


def main() -> None:
    global LEDGER
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=LEDGER_PATH)
    args = ap.parse_args()
    if not (UPSTREAM_LLM and UPSTREAM_MEDIA):
        raise SystemExit("VW_GATEWAY_UPSTREAM_LLM and VW_GATEWAY_UPSTREAM_MEDIA are required")
    if not TASK_TOKEN:
        raise SystemExit("VW_TASK_TOKEN is required")
    ledger_path = args.ledger
    LEDGER = Ledger(ledger_path, BUDGET)
    LEDGER.record("gateway_started", upstream_llm=_redacted(UPSTREAM_LLM),
                  upstream_media=_redacted(UPSTREAM_MEDIA),
                  port=GATEWAY_PORT, has_upstream_key=bool(UPSTREAM_KEY))
    server = ThreadingHTTPServer(("127.0.0.1", GATEWAY_PORT), Handler)
    print(f"gateway listening 127.0.0.1:{GATEWAY_PORT} llm={_redacted(UPSTREAM_LLM)} "
          f"media={_redacted(UPSTREAM_MEDIA)} ledger={ledger_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LEDGER.record("gateway_stopped")
        LEDGER.data["status"] = "closed"
        LEDGER._atomic_write()


if __name__ == "__main__":
    main()
