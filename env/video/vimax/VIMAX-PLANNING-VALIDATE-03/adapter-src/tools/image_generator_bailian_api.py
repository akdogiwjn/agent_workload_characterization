"""Bailian (Aliyun Model Studio) image generator for ViMax.

Adapts ViMax's ImageGenerator protocol to the Bailian workspace-domain
OpenAI-compatible endpoint verified in BAILIAN-GENERATION-SMOKE-02:

  POST {base_url}/images/generations      (T2I: no `image`; I2I: `image`)

base_url example: https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1

Contract decisions (documented, no silent degradation):
- qwen-image-3.0 accepts at most 3 reference images -> more than 3 raises
  ValueError (rejected, never truncated);
- I2I uses the SAME /images/generations endpoint via the `image` extension
  field (base64 data URLs); /images/edits and multipart are never used;
- the response returns a signed URL; this generator downloads the real media
  itself (no Authorization header to the media host) and returns
  ImageOutput(fmt="pil", ext="png");

Retry policy (CORRECTED 2026-10-23 — audit fix):
- image generation is a PAID synchronous call whose outcome may be UNKNOWN
  on transport timeout / 5xx (the request may already have been accepted and
  billed server-side). Such failures are NOT retried here; the ledger marks
  them right-censored. ONLY an explicit HTTP 429 (server refused before
  accepting) is retried, bounded by VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS. The
  earlier claim "synchronous generation cannot double-bill" was WRONG and is
  withdrawn (see ADAPTATION-DIFF.md revision).
- the media DOWNLOAD is idempotent and free: bounded retries on 429/5xx and
  transport errors are safe and kept.

Media download hardening (audit fix):
- at most ONE redirect; a second redirect is an explicit failure;
- relative Location headers are resolved against the current URL;
- only http/https media URLs are followed (no scheme downgrade, no other
  protocols); the model API Authorization header is NEVER sent to the media
  host; retries never reset the per-call deadline.

Ledger & budget: every create/download is guarded (pre-send caps:
image_generations / media_downloads + shared wall deadline), opened before
the send and closed (or right-censored) after; all events go to the shared
VIMAX_BAILIAN_EVENT_LOG ledger.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from io import BytesIO
from typing import Any, List
from urllib.parse import urljoin, urlparse

import aiohttp
from PIL import Image

from agent_runtime.request_ledger import get_ledger
from interfaces.image_output import ImageOutput
from tools.image_orientation import ensure_not_portrait, landscape_guard_requested
from utils.image import image_path_to_b64

BAILIAN_MAX_REFERENCE_IMAGES = 3  # qwen-image-3.0 official limit (1-3)
_MEDIA_DOWNLOAD_CAP_BYTES = 20 * 1024 * 1024
_MAX_MEDIA_REDIRECTS = 1  # a second redirect is an explicit failure


class BailianImageAPIError(RuntimeError):
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        super().__init__(f"Bailian image generation failed with HTTP {status_code}: {payload}")


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


def _http_max_attempts() -> int:
    return _int_env("VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS", 2)


def _image_request_timeout() -> float:
    return _float_env("VIMAX_BAILIAN_IMAGE_REQUEST_TIMEOUT_SECONDS", 300.0)


def _download_timeout() -> float:
    return _float_env("VIMAX_BAILIAN_DOWNLOAD_TIMEOUT_SECONDS", 180.0)


def _redacted(url: str) -> str:
    return str(url).split("?", 1)[0]


def _media_url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class ImageGeneratorBailianAPI:
    """Generate images through Bailian's OpenAI-compatible Images API."""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-image-3.0",
        base_url: str = "",
        rate_limiter: Any = None,
    ) -> None:
        if not base_url:
            raise ValueError("Bailian image generator requires the workspace base_url "
                             "(https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.ledger = get_ledger()

    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] | None = None,
        aspect_ratio: str | None = "16:9",
        **kwargs: Any,
    ) -> ImageOutput:
        references = list(reference_image_paths or [])
        if len(references) > BAILIAN_MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"qwen-image-3.0 supports at most {BAILIAN_MAX_REFERENCE_IMAGES} "
                f"reference images; got {len(references)} (rejected, not truncated)")
        if self.rate_limiter is not None:
            await self.rate_limiter.acquire()

        self.ledger.guard("image_generations")
        self.ledger.bump("image_generations")
        request_id = self.ledger.open(
            "image_generation", model=self.model,
            reference_count=len(references),
            size=str(kwargs.get("size") or ""),
            url=_redacted(f"{self.base_url}/images/generations"))

        enforce_landscape = landscape_guard_requested(
            size=kwargs.get("size"),
            aspect_ratio=aspect_ratio,
            enforce_landscape=kwargs.get("enforce_landscape", True),
            allow_portrait=kwargs.get("allow_portrait", False),
        )
        request_prompt = prompt
        if enforce_landscape:
            ratio = aspect_ratio or "16:9"
            request_prompt = (
                f"{prompt}\n\n构图要求：横构图，宽高比约 {ratio}，宽必须大于高。"
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": request_prompt,
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
        }
        size = kwargs.get("size")
        if size:
            payload["size"] = str(size).replace("*", "x")  # Bailian uses letter x
        if references:
            payload["image"] = [
                image_path_to_b64(path, mime=True) for path in references
            ]

        progress = kwargs.get("progress")
        if progress is not None:
            progress("image_generation", f"Generating image with {self.model}",
                     {"model": self.model, "reference_count": len(references)})

        timeout = aiohttp.ClientTimeout(total=_image_request_timeout())
        deadline = time.monotonic() + _image_request_timeout()
        status: int
        response: Any
        attempts = 0
        try:
            while True:
                attempts += 1
                try:
                    status, response = await _post_json(
                        f"{self.base_url}/images/generations",
                        headers=self._headers(),
                        payload=payload,
                        timeout=timeout,
                    )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    # outcome UNKNOWN server-side: no auto-retry (audit fix);
                    # the ledger keeps the right-censored record
                    self.ledger.error(request_id, type(exc).__name__,
                                      right_censored=True,
                                      attempts=attempts)
                    raise
                if status == 429 and attempts < _http_max_attempts():
                    # 429 = refused before acceptance: a retry cannot
                    # double-bill, and it never resets the deadline
                    if time.monotonic() > deadline:
                        self.ledger.error(request_id, "DeadlineExceeded",
                                          attempts=attempts)
                        raise BailianImageAPIError(429, "per-call deadline exceeded")
                    await asyncio.sleep(min(2 ** attempts, 8))
                    continue
                if status >= 400:
                    self.ledger.error(request_id, f"http_{status}",
                                      attempts=attempts,
                                      error=_safe_error(response))
                    raise BailianImageAPIError(status, response)
                break

            usage = response.get("usage") if isinstance(response, dict) else None
            url = None
            if isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    url = data[0].get("url")
            if not url:
                self.ledger.error(request_id, "no_image_url_in_response",
                                  attempts=attempts)
                raise ValueError(f"Bailian image response missing data[0].url: {response}")
            self.ledger.close(request_id, "ok", attempts=attempts,
                              http_status=status, usage=usage)
        except BailianImageAPIError:
            raise
        except Exception as exc:  # noqa: BLE001 — ensure closure
            self.ledger.error(request_id, type(exc).__name__)
            raise

        image_bytes = await self._download(url)
        image = _decode_png(image_bytes)
        if enforce_landscape:
            ensure_not_portrait(image)
        if progress is not None:
            progress("image_completed", "Bailian image generation completed",
                     {"model": self.model, "width": image.width,
                      "height": image.height})
        return ImageOutput(fmt="pil", ext="png", data=image)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _download(self, url: str) -> bytes:
        """Download the real media WITHOUT the model API Authorization header.

        Hardened (audit fix): at most ONE redirect (a second is an explicit
        failure); relative Location resolved against the current URL; only
        http/https schemes; bounded idempotent retries that never reset the
        per-call deadline; 20 MB cap."""
        if not _media_url_allowed(url):
            raise BailianImageAPIError(400, f"media URL scheme/host not allowed: {_redacted(url)}")
        self.ledger.guard("media_downloads")
        self.ledger.bump("media_downloads")
        request_id = self.ledger.open("media_download",
                                      url=_redacted(url))
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
                        raise BailianImageAPIError(408, "download deadline exceeded")
                    attempts += 1
                    try:
                        async with session.get(current, allow_redirects=False) as resp:
                            if resp.status in (301, 302, 303, 307, 308):
                                location = resp.headers.get("Location", "")
                                if not location:
                                    raise BailianImageAPIError(
                                        resp.status, "redirect without Location")
                                target = urljoin(current, location)
                                if not _media_url_allowed(target):
                                    raise BailianImageAPIError(
                                        resp.status,
                                        f"redirect target not http/https: {_redacted(target)}")
                                if redirects + 1 > _MAX_MEDIA_REDIRECTS:
                                    self.ledger.error(
                                        request_id, "TooManyRedirects",
                                        redirects=redirects + 1)
                                    raise BailianImageAPIError(
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
                                raise BailianImageAPIError(resp.status, body[:400])
                            data = bytearray()
                            async for chunk in resp.content.iter_chunked(65536):
                                data.extend(chunk)
                                if len(data) > _MEDIA_DOWNLOAD_CAP_BYTES:
                                    self.ledger.error(request_id, "size_cap_exceeded",
                                                      redirects=redirects)
                                    raise BailianImageAPIError(
                                        413, "media exceeds 20 MB cap")
                            if not data:
                                self.ledger.error(request_id, "empty_body",
                                                  redirects=redirects)
                                raise BailianImageAPIError(resp.status, "empty body")
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
        except BailianImageAPIError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.ledger.error(request_id, type(exc).__name__)
            raise


def _safe_error(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: payload.get(k) for k in ("code", "message", "error")
                if k in payload}
    return str(payload)[:400]


def _decode_png(raw: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(raw)) as opened:
            opened.load()
            return opened.copy()
    except Exception as exc:
        raise ValueError("Bailian image download contained invalid image data") from exc


async def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: aiohttp.ClientTimeout,
) -> tuple[int, Any]:
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            text = await response.text()
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = {"message": text}
            return response.status, body
