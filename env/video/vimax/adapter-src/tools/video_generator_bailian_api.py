"""Bailian (Aliyun Model Studio) video generator for ViMax.

Adapts ViMax's VideoGenerator protocol to the Bailian native async
video-synthesis endpoint verified in BAILIAN-GENERATION-SMOKE-02 +
video-recovery-01:

  POST {base_url}/api/v1/services/aigc/video-generation/video-synthesis
       (header X-DashScope-Async: enable)
  GET  {base_url}/api/v1/tasks/{task_id}      (Authorization REQUIRED)

base_url example: https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com

Contract decisions (documented, no silent degradation):
- wan2.6-i2v-flash is a FIRST-FRAME i2v model. ViMax's reference-image
  convention is: 1 image = first frame, 2 images = first + LAST frame.
  2 images are therefore REJECTED with ValueError (never silently dropped
  to first-frame-only, never swapped to another model). 0 images are also
  rejected: this model has no text-to-video mode.
- exactly ONE remote task is created per call; the task_id is persisted to
  the event ledger BEFORE polling; the poll loop queries ONLY that task;
- polls always carry the Authorization header; 401/403 fail immediately
  without burning the poll budget; a poll transport error aborts (never
  re-creates a paid task);
- the CREATE call has ZERO retries by design: a 5xx response may mean the
  task was actually accepted, so retrying could create a second paid task;
- the final video download carries NO Authorization (separate no-auth
  session), at most one redirect, 200 MB cap; download retries are bounded
  and idempotent;
- duration/resolution/audio/prompt_extend come from explicit environment
  variables (ViMax passes none of them through kwargs): VIMAX_BAILIAN_VIDEO_
  DURATION=5, _RESOLUTION=720P, _AUDIO=false, _PROMPT_EXTEND=false;
- every create/poll/download appends a redacted JSONL event to
  VIMAX_BAILIAN_EVENT_LOG (op, url without query, http status, task_id,
  usage, error) for the production ledger.
"""
from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, List

from urllib.parse import urljoin, urlparse

import aiohttp

from agent_runtime.request_ledger import get_ledger
from interfaces.video_output import VideoOutput

_VIDEO_DOWNLOAD_CAP_BYTES = 200 * 1024 * 1024
_MAX_MEDIA_REDIRECTS = 1  # a second redirect is an explicit failure (audit fix)


def _media_url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class BailianVideoAPIError(RuntimeError):
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        super().__init__(f"Bailian video generation failed with HTTP {status_code}: {payload}")


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _float_env(name: str, default: float, minimum: float = 1.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _create_timeout() -> float:
    return _float_env("VIMAX_BAILIAN_VIDEO_CREATE_TIMEOUT_SECONDS", 60.0)


def _request_timeout() -> float:
    return _float_env("VIMAX_BAILIAN_VIDEO_REQUEST_TIMEOUT_SECONDS", 60.0)


def _poll_interval() -> float:
    return _float_env("VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS", 10.0, minimum=1.0)


def _query_window() -> float:
    return _float_env("VIMAX_BAILIAN_VIDEO_QUERY_TIMEOUT_SECONDS", 900.0, minimum=10.0)


def _download_timeout() -> float:
    return _float_env("VIMAX_BAILIAN_DOWNLOAD_TIMEOUT_SECONDS", 300.0)


def _http_max_attempts() -> int:
    return _int_env("VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS", 2)


def _video_duration() -> int:
    return _int_env("VIMAX_BAILIAN_VIDEO_DURATION", 5)


def _video_resolution() -> str:
    return os.environ.get("VIMAX_BAILIAN_VIDEO_RESOLUTION", "720P")


def _video_audio() -> bool:
    return os.environ.get("VIMAX_BAILIAN_VIDEO_AUDIO", "false").lower() in ("1", "true", "yes")


def _video_prompt_extend() -> bool:
    return os.environ.get("VIMAX_BAILIAN_VIDEO_PROMPT_EXTEND", "false").lower() in ("1", "true", "yes")


def _redacted(url: str) -> str:
    return str(url).split("?", 1)[0]


def _safe_error(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: payload.get(k) for k in ("code", "message", "error")
                if k in payload}
    return str(payload)[:400]


def _image_path_to_data_url(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode("ascii")


class VideoGeneratorBailianAPI:
    """Generate videos through Bailian's native async video-synthesis API."""

    def __init__(
        self,
        api_key: str,
        model: str = "wan2.6-i2v-flash",
        base_url: str = "",
        rate_limiter: Any = None,
    ) -> None:
        if not base_url:
            raise ValueError("Bailian video generator requires the workspace base_url "
                             "(https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.ledger = get_ledger()

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str] | None = None,
        aspect_ratio: str | None = "16:9",
        **kwargs: Any,
    ) -> VideoOutput:
        references = list(reference_image_paths or [])
        if len(references) == 0:
            raise ValueError(
                f"{self.model} is a first-frame image-to-video model; "
                "text-to-video (0 reference images) is not supported and is "
                "rejected instead of silently switching models")
        if len(references) == 2:
            raise ValueError(
                f"{self.model} does NOT support first+last frame generation; "
                "the last-frame image would have to be silently dropped, so "
                "the request is rejected (no model substitution)")
        if len(references) > 2:
            raise ValueError(
                f"{self.model} supports at most one first-frame reference "
                f"image; got {len(references)}")
        if self.rate_limiter is not None:
            await self.rate_limiter.acquire()

        self.ledger.guard("video_creates")
        self.ledger.bump("video_creates")
        call_id = self.ledger.open(
            "video_call", model=self.model,
            duration=_video_duration(),
            resolution=_video_resolution(),
            audio=_video_audio(),
            first_frame=references[0])

        progress = kwargs.get("progress")
        if progress is not None:
            progress("video_generation", f"Creating video task with {self.model}",
                     {"model": self.model, "first_frame": references[0]})

        payload: dict[str, Any] = {
            "model": self.model,
            "input": {
                "prompt": prompt,
                "img_url": _image_path_to_data_url(references[0]),
            },
            "parameters": {
                "resolution": _video_resolution(),
                "duration": _video_duration(),
                "audio": _video_audio(),
                "prompt_extend": _video_prompt_extend(),
                "watermark": False,
            },
        }

        try:
            task_id = await self._create_task(payload, call_id)
            self.ledger.close(call_id, "ok", task_id=task_id,
                              create_status="accepted")
            video_url, usage = await self._poll_task(task_id, progress)
            data = await self._download(video_url)
        except Exception as exc:  # noqa: BLE001 — close the call ledger entry
            self.ledger.error(call_id, type(exc).__name__)
            raise
        if progress is not None:
            progress("video_completed", "Bailian video generation completed",
                     {"model": self.model, "task_id": task_id,
                      "bytes": len(data)})
        self.ledger.observe_usage(video_task_usage=usage)
        return VideoOutput(fmt="bytes", ext="mp4", data=data)

    # ------------------------------------------------------------------ #
    def _headers(self, *, async_header: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if async_header:
            headers["X-DashScope-Async"] = "enable"
        return headers

    async def _create_task(self, payload: dict[str, Any],
                           call_id: str | None = None) -> str:
        """ZERO retries by design: a 5xx may mean the paid task was already
        accepted; retrying could create a second billed task. A transport
        timeout is right-censored in the ledger (outcome unknown)."""
        url = (f"{self.base_url}/api/v1/services/aigc/"
               "video-generation/video-synthesis")
        timeout = aiohttp.ClientTimeout(total=_create_timeout())
        sub_id = self.ledger.open(
            "video_create", url=_redacted(url), model=self.model,
            parent_call=call_id,
            duration=_video_duration(),
            resolution=_video_resolution(),
            audio=_video_audio())
        try:
            async with aiohttp.ClientSession(timeout=timeout,
                                             trust_env=False) as session:
                async with session.post(url,
                                        headers=self._headers(async_header=True),
                                        json=payload) as resp:
                    text = await resp.text()
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError:
                        body = {"message": text}
                    if resp.status >= 400:
                        self.ledger.error(sub_id, f"http_{resp.status}",
                                          error=_safe_error(body))
                        raise BailianVideoAPIError(resp.status, body)
                    output = body.get("output") or {}
                    task_id = output.get("task_id")
                    if not task_id:
                        self.ledger.error(sub_id, "no_task_id")
                        raise ValueError(f"Bailian video create missing task_id: {body}")
                    self.ledger.close(sub_id, "ok",
                                      http_status=resp.status,
                                      task_id=task_id,
                                      task_status=output.get("task_status"),
                                      provider_request_id=body.get("request_id"))
                    return task_id
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            self.ledger.error(sub_id, type(exc).__name__,
                              right_censored=True,
                              note="create outcome unknown; NO retry "
                                   "(zero-retry policy, anti double-billing)")
            raise

    async def _poll_task(self, task_id: str, progress: Any) -> tuple[str, Any]:
        """Poll ONLY this task. Polls carry Authorization. 401/403 abort
        immediately; a transport error aborts (never re-creates)."""
        url = f"{self.base_url}/api/v1/tasks/{task_id}"
        timeout = aiohttp.ClientTimeout(total=_request_timeout())
        window = _query_window()
        interval = _poll_interval()
        started = time.monotonic()
        polls = 0
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            while True:
                elapsed = time.monotonic() - started
                if elapsed > window:
                    self.ledger.close(poll_rid,
                                      "query_window_exhausted")
                    raise BailianVideoAPIError(
                        408, f"video task {task_id} not terminal after "
                             f"{window:g}s ({polls} polls); task may still "
                             "run remotely and bill")
                await asyncio.sleep(interval if polls else 0)
                polls += 1
                self.ledger.guard("video_polls")
                self.ledger.bump("video_polls")
                poll_rid = self.ledger.open("video_poll", task_id=task_id,
                                            poll=polls)
                async with session.get(url, headers=self._headers()) as resp:
                    text = await resp.text()
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError:
                        body = {"message": text}
                    output = body.get("output") or {}
                    status = output.get("task_status")
                    if resp.status in (401, 403):
                        self.ledger.error(poll_rid,
                                          f"http_{resp.status}",
                                          error=_safe_error(body))
                        raise BailianVideoAPIError(
                            resp.status,
                            f"poll auth failed (status {resp.status}); "
                            "aborting without retry")
                    if resp.status >= 400:
                        self.ledger.error(poll_rid,
                                          f"http_{resp.status}",
                                          error=_safe_error(body))
                        raise BailianVideoAPIError(resp.status, body)
                    if status == "SUCCEEDED":
                        video_url = output.get("video_url")
                        if not video_url:
                            self.ledger.error(poll_rid,
                                              "succeeded_without_video_url")
                            raise ValueError(
                                f"SUCCEEDED without video_url: {body}")
                        self.ledger.close(poll_rid, "ok",
                                          task_status=status,
                                          usage=body.get("usage"))
                        if progress is not None:
                            progress("video_poll_succeeded",
                                     f"Video task {task_id} succeeded",
                                     {"task_id": task_id, "polls": polls})
                        return video_url, body.get("usage")
                    if status in ("FAILED", "CANCELED", "UNKNOWN"):
                        self.ledger.error(poll_rid,
                                          f"task_{status}",
                                          error={"code": output.get("code"),
                                                 "message": output.get("message")})
                        raise BailianVideoAPIError(
                            502, f"video task {task_id} terminal state "
                                 f"{status}: {output.get('code')} "
                                 f"{output.get('message')}")
                    self.ledger.close(poll_rid, "ok",
                                      task_status=status)

    async def _download(self, url: str) -> bytes:
        """Download the produced video WITHOUT the model API Authorization
        header. Hardened (audit fix): at most ONE redirect; relative
        Location resolved via urljoin; only http/https; bounded idempotent
        retries that never reset the per-call deadline; 200 MB cap."""
        if not _media_url_allowed(url):
            raise BailianVideoAPIError(400, f"media URL not http/https: {_redacted(url)}")
        self.ledger.guard("media_downloads")
        self.ledger.bump("media_downloads")
        request_id = self.ledger.open("video_download", url=_redacted(url))
        timeout = aiohttp.ClientTimeout(total=_download_timeout())
        deadline = time.monotonic() + _download_timeout()
        attempts = 0
        redirects = 0
        current = url
        try:
            async with aiohttp.ClientSession(timeout=timeout,
                                             trust_env=False) as session:
                while True:
                    if time.monotonic() > deadline:
                        self.ledger.error(request_id, "DeadlineExceeded",
                                          redirects=redirects)
                        raise BailianVideoAPIError(408, "download deadline exceeded")
                    attempts += 1
                    try:
                        async with session.get(current, allow_redirects=False) as resp:
                            if resp.status in (301, 302, 303, 307, 308):
                                location = resp.headers.get("Location", "")
                                if not location:
                                    raise BailianVideoAPIError(
                                        resp.status, "redirect without Location")
                                target = urljoin(current, location)
                                if not _media_url_allowed(target):
                                    raise BailianVideoAPIError(
                                        resp.status,
                                        f"redirect target not http/https: {_redacted(target)}")
                                if redirects + 1 > _MAX_MEDIA_REDIRECTS:
                                    self.ledger.error(
                                        request_id, "TooManyRedirects",
                                        redirects=redirects + 1)
                                    raise BailianVideoAPIError(
                                        resp.status,
                                        f"more than {_MAX_MEDIA_REDIRECTS} media redirect")
                                redirects += 1
                                current = target
                                continue
                            if resp.status >= 400:
                                body = await resp.text()
                                if (resp.status == 429 or resp.status >= 500) \
                                        and attempts < _http_max_attempts() \
                                        and time.monotonic() <= deadline:
                                    await asyncio.sleep(min(2 ** attempts, 8))
                                    continue
                                self.ledger.error(request_id,
                                                  f"http_{resp.status}",
                                                  redirects=redirects,
                                                  body_excerpt=body[:200])
                                raise BailianVideoAPIError(resp.status, body[:400])
                            data = bytearray()
                            async for chunk in resp.content.iter_chunked(65536):
                                data.extend(chunk)
                                if len(data) > _VIDEO_DOWNLOAD_CAP_BYTES:
                                    self.ledger.error(request_id,
                                                      "size_cap_exceeded",
                                                      redirects=redirects)
                                    raise BailianVideoAPIError(
                                        413, "video exceeds 200 MB cap")
                            if not data:
                                self.ledger.error(request_id, "empty_body",
                                                  redirects=redirects)
                                raise BailianVideoAPIError(resp.status, "empty body")
                            self.ledger.close(request_id, "ok",
                                              http_status=resp.status,
                                              redirects=redirects,
                                              bytes=len(data))
                            return bytes(data)
                    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                        if attempts < _http_max_attempts() \
                                and time.monotonic() <= deadline:
                            await asyncio.sleep(min(2 ** attempts, 8))
                            continue
                        self.ledger.error(request_id, type(exc).__name__,
                                          redirects=redirects)
                        raise
        except BailianVideoAPIError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.ledger.error(request_id, type(exc).__name__)
            raise
