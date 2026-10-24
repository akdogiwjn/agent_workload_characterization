#!/usr/bin/env python3
"""BAILIAN-GENERATION-SMOKE-01: bounded Bailian generation API smoke.

Verifies, for the ViMax preparation effort, whether the registered Aliyun
Bailian (DashScope, cn-beijing) route can serve:
  A. image generation        qwen-image-3.0   (OpenAI-compat /images/generations, T2I)
  B. image editing           qwen-image-3.0   (same endpoint, image field = I2I, 1 ref image)
  C. chat vision + tool call qwen3.7-plus     (OpenAI-compat /chat/completions, tool_choice)
  D. video creation          wan2.6-i2v-flash (native async video-synthesis, first frame)

Budget: EXACTLY at most 4 model operations (1 each); video polls (max 40,
10 s target) and media downloads are counted separately. No retries at any
layer. Any necessary-step failure stops the sequence; later steps are
recorded NOT_EXECUTED. Shared wall deadline 1200 s from execute() start.

Security: DASHSCOPE_API_KEY is read from the registered file only right
before sends; never stored, echoed, hashed or fingerprinted. Authorization
headers, key-shaped strings and signed-URL query strings are redacted from
all retained evidence. Official media URLs are downloaded by a separate
client WITHOUT the model API Authorization header (redirects handled
separately, never re-sending credentials).

Offline mode (default) runs nothing network-shaped; unit tests use
httpx.MockTransport only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

PROBE_DIR = Path(__file__).resolve().parent

CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
CREDENTIAL_ENV = "DASHSCOPE_API_KEY"

COMPAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1"
IMAGES_URL = COMPAT_BASE + "/images/generations"
CHAT_URL = COMPAT_BASE + "/chat/completions"
VIDEO_CREATE_URL = NATIVE_BASE + "/services/aigc/video-generation/video-synthesis"
VIDEO_TASK_URL = NATIVE_BASE + "/tasks/"

MODEL_IMAGE = "qwen-image-3.0"
MODEL_CHAT = "qwen3.7-plus"
MODEL_VIDEO = "wan2.6-i2v-flash"

MAX_MODEL_OPS = 4
DEADLINE_S = 1200.0
POLL_MAX = 40
POLL_INTERVAL_S = 10.0
RESERVE_FOR_FINISH_S = 150.0  # poll loop must leave this much deadline for download+checks
IMG_DL_CAP = 20 * 1024 * 1024
VIDEO_DL_CAP = 200 * 1024 * 1024
MAX_DL_REDIRECTS = 1
API_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
DL_TIMEOUT = httpx.Timeout(180.0, connect=15.0)

PROMPT_A = "白色背景，左侧一个红色圆形，右侧一个蓝色正方形，无文字。"
PROMPT_B = "保持白色背景和左右布局，将左侧红色圆形改成绿色，右侧蓝色正方形保持不变。"
PROMPT_C_TEXT = ("识别这张图片，并通过工具提交结果。图片中左侧和右侧各有一个图形，"
                 "请用 report_shapes 工具报告它们的颜色和形状。")
PROMPT_D = ("固定机位，左侧绿色圆形缓慢上下移动，右侧蓝色正方形保持静止；"
            "背景纯白；全程单镜头，无文字。")
SIZE_A = "1024x576"  # 16:9, 589,824 px -> 1k billing tier, lowest cost

EXPECTED_A = {"background": "white", "left": {"color": "red", "shape": "circle"},
              "right": {"color": "blue", "shape": "square"}, "text": "none"}
EXPECTED_C_PRE = {"left_color": "green", "left_shape": "circle",
                  "right_color": "blue", "right_shape": "square"}


class SendLimitExceeded(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# redaction helpers
# --------------------------------------------------------------------------- #

_KEY_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(\bsk-)[A-Za-z0-9_-]{6,}"),
)


def redact(text) -> str:
    out = str(text)
    for pattern in _KEY_PATTERNS:
        out = pattern.sub(r"\1[REDACTED]", out)
    return out


def strip_url_query(url: str) -> str:
    """Signed media URLs must never be retained with their query string."""
    return str(url).split("?", 1)[0]


# --------------------------------------------------------------------------- #
# counters (persisted on every exit path by the caller)
# --------------------------------------------------------------------------- #

class Counters:
    """All counts increment at the actual HTTP send function entry."""

    KEYS = ("model_operations", "create_task_requests", "poll_requests",
            "download_requests", "download_redirects", "send_failures",
            "client_resends")

    def __init__(self, model_cap: int = MAX_MODEL_OPS):
        self.model_cap = model_cap
        self._d = {k: 0 for k in self.KEYS}
        self._blocked = 0

    def bump(self, key: str, n: int = 1) -> None:
        self._d[key] = self._d.get(key, 0) + n

    def guard_model(self) -> None:
        """Raise BEFORE any network action when the 4-op cap is reached."""
        if self._d["model_operations"] >= self.model_cap:
            self._blocked += 1
            raise SendLimitExceeded(
                f"model operation cap reached ({self.model_cap}); rejected")

    def snapshot(self) -> dict:
        return {"boundary": "client_http_send_function_entry",
                "basis": "client-side observation only; gateway/upstream "
                         "internal retries unknown",
                **{k: self._d[k] for k in self.KEYS},
                "model_ops_blocked": self._blocked,
                "model_op_cap": self.model_cap,
                "client_resends_note": "retries disabled at every layer by "
                                       "design; resends stay 0"}


# --------------------------------------------------------------------------- #
# credential (value never leaves this function's caller scope)
# --------------------------------------------------------------------------- #

def load_credential() -> str:
    try:
        text = CREDENTIAL_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"credential file unreadable: {type(exc).__name__}")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == CREDENTIAL_ENV:
            value = value.strip().strip('"').strip("'")
            if not value:
                raise SystemExit(f"{CREDENTIAL_ENV} empty in credential file")
            return value
    raise SystemExit(f"{CREDENTIAL_ENV} not found in credential file "
                     "(names only inspected; no values printed)")


# --------------------------------------------------------------------------- #
# clients (no retries, redirects never followed automatically)
# --------------------------------------------------------------------------- #

def make_api_client() -> httpx.Client:
    return httpx.Client(transport=httpx.HTTPTransport(retries=0),
                        follow_redirects=False, timeout=API_TIMEOUT,
                        trust_env=False)


def make_media_client() -> httpx.Client:
    """Separate client for official media URLs: NO Authorization is ever
    attached; redirects are handled manually (max 1) without credentials."""
    return httpx.Client(transport=httpx.HTTPTransport(retries=0),
                        follow_redirects=False, timeout=DL_TIMEOUT,
                        trust_env=False)


# --------------------------------------------------------------------------- #
# request bodies (pure; offline-testable)
# --------------------------------------------------------------------------- #

def b64_data_url(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def body_A() -> dict:
    return {"model": MODEL_IMAGE, "prompt": PROMPT_A, "size": SIZE_A,
            "n": 1, "prompt_extend": False, "watermark": False}


def body_B(reference_png: bytes) -> dict:
    return {"model": MODEL_IMAGE, "prompt": PROMPT_B,
            "image": b64_data_url(reference_png), "size": SIZE_A,
            "n": 1, "prompt_extend": False, "watermark": False}


REPORT_SHAPES_TOOL = {
    "type": "function",
    "function": {
        "name": "report_shapes",
        "description": "报告图片左右两侧图形的颜色与形状",
        "parameters": {
            "type": "object",
            "properties": {
                "left_color": {"type": "string",
                               "enum": ["red", "green", "blue", "yellow",
                                        "black", "white", "other"]},
                "left_shape": {"type": "string",
                               "enum": ["circle", "square", "triangle", "other"]},
                "right_color": {"type": "string",
                                "enum": ["red", "green", "blue", "yellow",
                                         "black", "white", "other"]},
                "right_shape": {"type": "string",
                                "enum": ["circle", "square", "triangle", "other"]},
            },
            "required": ["left_color", "left_shape",
                         "right_color", "right_shape"],
        },
    },
}


def body_C(image_png: bytes) -> dict:
    return {
        "model": MODEL_CHAT,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT_C_TEXT},
            {"type": "image_url",
             "image_url": {"url": b64_data_url(image_png)}},
        ]}],
        "tools": [REPORT_SHAPES_TOOL],
        "tool_choice": {"type": "function",
                        "function": {"name": "report_shapes"}},
        "enable_thinking": False,
        "max_completion_tokens": 1024,
    }


def body_D(first_frame_png: bytes) -> dict:
    return {
        "model": MODEL_VIDEO,
        "input": {"prompt": PROMPT_D,
                  "img_url": b64_data_url(first_frame_png)},
        "parameters": {"resolution": "720P", "duration": 5, "audio": False,
                       "prompt_extend": False, "watermark": False},
    }


# --------------------------------------------------------------------------- #
# one bounded HTTP call (counts at entry; record returned even on error)
# --------------------------------------------------------------------------- #

def http_call(counters: Counters, client: httpx.Client, method: str, url: str,
              *, counter_key: str, headers: dict | None = None,
              body: dict | None = None, deadline: float,
              guard_model: bool = False) -> dict:
    if guard_model:
        counters.guard_model()
    # counter_key semantics:
    #   "model"   -> one model operation (A / B / C)
    #   "create"  -> the video create: one model operation AND one create-task
    #                request (both counted, kept in sync)
    #   "poll" / "download" / "download_redirect" -> never model operations
    if counter_key == "model":
        counters.bump("model_operations")
    elif counter_key == "create":
        counters.bump("create_task_requests")
        counters.bump("model_operations")
    elif counter_key == "poll":
        counters.bump("poll_requests")
    elif counter_key == "download":
        counters.bump("download_requests")
    elif counter_key == "download_redirect":
        counters.bump("download_redirects")
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown counter_key {counter_key!r}")
    record = {"url": strip_url_query(url), "method": method,
              "counter_key": counter_key,
              "t_start_monotonic": time.monotonic()}
    if body is not None:
        record["request_body_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()).hexdigest()
    try:
        resp = client.request(method, url, headers=headers, json=body)
        record["http_status"] = resp.status_code
        record["content_type"] = resp.headers.get("content-type", "")
        record["x_request_id"] = resp.headers.get("x-request-id")
        text = resp.text
        record["response_len"] = len(text)
        try:
            record["json"] = resp.json()
        except Exception:  # noqa: BLE001
            record["json"] = None
            record["body_excerpt_redacted"] = redact(text[:800])
        record["ok"] = True
    except Exception as exc:  # noqa: BLE001 — always recorded, redacted
        counters.bump("send_failures")
        record["ok"] = False
        record["error_type"] = type(exc).__name__
        record["error_text_redacted"] = redact(str(exc))[:800]
    record["t_end_monotonic"] = time.monotonic()
    record["wall_s"] = round(record["t_end_monotonic"]
                             - record["t_start_monotonic"], 3)
    return record


# --------------------------------------------------------------------------- #
# media download (no Authorization; manual single redirect; size cap)
# --------------------------------------------------------------------------- #

def download_media(counters: Counters, client: httpx.Client, url: str,
                   dest: Path, cap: int, deadline: float) -> dict:
    record = {"url": strip_url_query(url), "dest": dest.name, "cap_bytes": cap}
    current = url
    try:
        for hop in range(MAX_DL_REDIRECTS + 1):
            counters.bump("download_requests")
            with client.stream("GET", current) as resp:
                record["http_status"] = resp.status_code
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location", "")
                    record.setdefault("redirect_hosts", []).append(
                        strip_url_query(loc))
                    if hop >= MAX_DL_REDIRECTS or not loc:
                        record["ok"] = False
                        record["error_type"] = "TooManyRedirectsOrMissingLocation"
                        return record
                    counters.bump("download_redirects")
                    current = loc
                    continue
                if resp.status_code != 200:
                    record["ok"] = False
                    record["error_type"] = f"http_{resp.status_code}"
                    return record
                size = 0
                sha = hashlib.sha256()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_bytes(65536):
                        size += len(chunk)
                        if size > cap:
                            fh.close()
                            tmp.unlink(missing_ok=True)
                            record["ok"] = False
                            record["error_type"] = "size_cap_exceeded"
                            record["bytes_seen_over_cap"] = size
                            return record
                        sha.update(chunk)
                        fh.write(chunk)
                if size == 0:
                    tmp.unlink(missing_ok=True)
                    record["ok"] = False
                    record["error_type"] = "empty_body"
                    return record
                tmp.rename(dest)
                record["ok"] = True
                record["bytes"] = size
                record["sha256"] = sha.hexdigest()
                return record
    except Exception as exc:  # noqa: BLE001
        counters.bump("send_failures")
        record["ok"] = False
        record["error_type"] = type(exc).__name__
        record["error_text_redacted"] = redact(str(exc))[:800]
        return record


# --------------------------------------------------------------------------- #
# image evidence: decode + per-half color statistics (human-checkable)
# --------------------------------------------------------------------------- #

def _color_class(r: int, g: int, b: int) -> str:
    if r > 150 and g < 110 and b < 110:
        return "red"
    if g > 110 and r < 130 and b < 130:
        return "green"
    if b > 130 and r < 120 and g < 120:
        return "blue"
    if r > 220 and g > 220 and b > 220:
        return "white"
    return "other"


def region_stats(pil_img) -> dict:
    """Sampled per-half color shares. Coarse but deterministic; retained as
    human-checkable evidence, not as a perceptual judgement."""
    img = pil_img.convert("RGB")
    w, h = img.size
    px = img.load()
    shares = {"left": {}, "right": {}, "whole": {}}
    counts = {"left": 0, "right": 0, "whole": 0}
    step = max(1, min(w, h) // 200)
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = _color_class(*px[x, y])
            for region in ("whole", "left" if x < w // 2 else "right"):
                counts[region] += 1
                shares[region][c] = shares[region].get(c, 0) + 1
    out = {}
    for region, n in counts.items():
        if n:
            out[region] = {k: round(v / n, 4)
                           for k, v in sorted(shares[region].items(),
                                              key=lambda kv: -kv[1])}
    return out


def image_evidence(path: Path) -> dict:
    """Read the real media file; never judge from a URL alone."""
    ev = {"path": path.name}
    data = path.read_bytes()
    ev["bytes"] = len(data)
    ev["sha256"] = hashlib.sha256(data).hexdigest()
    ev["non_empty"] = len(data) > 0
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            ev["decodable"] = True
            ev["format"] = im.format
            ev["size_px"] = list(im.size)
            ev["region_stats"] = region_stats(im)
    except Exception as exc:  # noqa: BLE001
        ev["decodable"] = False
        ev["decode_error_type"] = type(exc).__name__
    return ev


def dominant(region: dict) -> str | None:
    """Dominant non-white color share of a half-region, if clearly present."""
    if not region:
        return None
    best, best_share = None, 0.0
    for color, share in region.items():
        if color in ("white", "other"):
            continue
        if share > best_share:
            best, best_share = color, share
    return best if best_share >= 0.05 else None


# --------------------------------------------------------------------------- #
# verdict rules (fixed pre-send; pure functions; offline-testable)
# --------------------------------------------------------------------------- #

def judge_A(rec: dict, ev: dict) -> dict:
    if not rec.get("ok"):
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "details": rec}
    if rec.get("http_status") != 200:
        return {"verdict": "FAIL", "reason": f"http_{rec.get('http_status')}",
                "error": (rec.get("json") or {}).get("error"), "details": rec}
    url = ((rec.get("json") or {}).get("data") or [{}])[0].get("url")
    if not url:
        return {"verdict": "FAIL", "reason": "no_image_url_in_response",
                "details": rec}
    if not ev.get("non_empty") or not ev.get("decodable"):
        return {"verdict": "FAIL", "reason": "media_not_valid_image",
                "evidence": ev}
    stats = ev.get("region_stats") or {}
    left, right, whole = (stats.get("left") or {}, stats.get("right") or {},
                          stats.get("whole") or {})
    content_match = {
        "left_dominant": dominant(left),
        "right_dominant": dominant(right),
        "white_bg_share": whole.get("white", 0.0),
        "expected": {"left": "red", "right": "blue"},
        "match": dominant(left) == "red" and dominant(right) == "blue"
                 and whole.get("white", 0.0) >= 0.3,
    }
    return {"verdict": "PASS",
            "reason": "http200_url_downloaded_decoded",
            "content_match": content_match,
            "note": "content_match is recorded evidence; a mismatch is "
                    "carried into B/C interpretation, not silently ignored"}


def judge_B(rec: dict, ev: dict, a_ev: dict) -> dict:
    if not rec.get("ok"):
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "details": rec}
    if rec.get("http_status") != 200:
        return {"verdict": "FAIL", "reason": f"http_{rec.get('http_status')}",
                "error": (rec.get("json") or {}).get("error"), "details": rec}
    url = ((rec.get("json") or {}).get("data") or [{}])[0].get("url")
    if not url:
        return {"verdict": "FAIL", "reason": "no_image_url_in_response",
                "details": rec}
    if not ev.get("non_empty") or not ev.get("decodable"):
        return {"verdict": "FAIL", "reason": "media_not_valid_image",
                "evidence": ev}
    stats = ev.get("region_stats") or {}
    a_stats = a_ev.get("region_stats") or {}
    left = stats.get("left") or {}
    right = stats.get("right") or {}
    whole = stats.get("whole") or {}
    left_green = left.get("green", 0.0)
    left_red = left.get("red", 0.0)
    a_left_red = (a_stats.get("left") or {}).get("red", 0.0)
    edit_applied = (left_green >= 0.05
                    and left_red <= max(0.02, 0.5 * a_left_red)
                    and right.get("blue", 0.0) >= 0.05
                    and whole.get("white", 0.0) >= 0.3)
    usage = (rec.get("json") or {}).get("usage") or {}
    input_count = usage.get("input_image_count")
    return {"verdict": "PASS" if edit_applied else "FAIL",
            "reason": "http200_media_valid_edit_applied" if edit_applied
                      else "edit_not_applied_or_layout_broken",
            "pixel_evidence": {
                "left_green_share": left_green, "left_red_share": left_red,
                "A_left_red_share": a_left_red,
                "right_blue_share": right.get("blue", 0.0),
                "white_bg_share": whole.get("white", 0.0)},
            "usage_input_image_count": input_count,
            "single_ref_accepted": True if input_count == 1 else
                                   (None if input_count is None else False),
            "note": "one reference image only; proves nothing about "
                    "multi-image consistency"}


_COLOR_WORDS = {
    "red": {"red", "红", "红色"},
    "green": {"green", "绿", "绿色"},
    "blue": {"blue", "蓝", "蓝色"},
    "yellow": {"yellow", "黄", "黄色"},
    "black": {"black", "黑", "黑色"},
    "white": {"white", "白", "白色"},
}
_SHAPE_WORDS = {
    "circle": {"circle", "圆", "圆形"},
    "square": {"square", "方", "正方形", "方形"},
    "triangle": {"triangle", "三角", "三角形"},
}


def _word_match(value, table) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    for canonical, words in table.items():
        if v in words or any(w in v for w in words):
            return canonical
    return None


def judge_C(rec: dict, b_ev: dict) -> dict:
    out = {"pre_registered_expected": EXPECTED_C_PRE}
    if not rec.get("ok"):
        out.update(verdict="UNKNOWN", reason="transport_or_http_failure",
                   details=rec)
        return out
    if rec.get("http_status") != 200:
        out.update(verdict="FAIL", reason=f"http_{rec.get('http_status')}",
                   error=(rec.get("json") or {}).get("error"))
        return out
    j = rec.get("json") or {}
    choices = j.get("choices") or []
    if not choices:
        out.update(verdict="UNKNOWN", reason="no_choices_in_response")
        return out
    msg = (choices[0].get("message") or {})
    finish = choices[0].get("finish_reason")
    out["finish_reason"] = finish
    out["request_completed"] = True
    usage = j.get("usage")
    out["usage"] = usage
    out["image_input_evidence"] = {
        "usage_fields_present": sorted(usage.keys()) if isinstance(usage, dict)
        else [],
        "note": "missing image-specific usage field does NOT prove the "
                "image was not passed; full usage retained",
    }
    tcs = msg.get("tool_calls") or []
    if not tcs:
        out.update(verdict="UNKNOWN",
                   reason="no_tool_call_returned",
                   content_excerpt=(msg.get("content") or "")[:300])
        return out
    tc = tcs[0]
    fn = tc.get("function") or {}
    out["tool_call"] = {"id": tc.get("id"), "type": tc.get("type"),
                        "name": fn.get("name")}
    id_valid = bool(tc.get("id"))
    name_valid = fn.get("name") == "report_shapes"
    try:
        args = json.loads(fn.get("arguments") or "")
    except Exception:  # noqa: BLE001
        out.update(verdict="UNKNOWN",
                   reason="tool_arguments_not_valid_json")
        return out
    out["tool_arguments_parsed"] = args
    tool_valid = id_valid and name_valid
    # cross-check against B's ACTUAL pixels (image-generation deviation must
    # not be counted as a vision error)
    b_stats = b_ev.get("region_stats") or {}
    b_actual = {"left_color": dominant(b_stats.get("left") or {}),
                "right_color": dominant(b_stats.get("right") or {})}
    out["b_actual_dominant_colors"] = b_actual
    expected = dict(EXPECTED_C_PRE)
    deviation = None
    if b_actual["left_color"] and b_actual["left_color"] != expected["left_color"]:
        deviation = (f"B actual left is {b_actual['left_color']}, "
                     f"pre-registered expected green")
        expected["left_color"] = b_actual["left_color"]
    if b_actual["right_color"] and b_actual["right_color"] != expected["right_color"]:
        deviation = (deviation or "") + (
            f"; B actual right is {b_actual['right_color']}")
        expected["right_color"] = b_actual["right_color"]
    out["expected_used"] = expected
    out["image_generation_deviation"] = deviation
    checks = {
        "left_color": _word_match(args.get("left_color"), _COLOR_WORDS),
        "left_shape": _word_match(args.get("left_shape"), _SHAPE_WORDS),
        "right_color": _word_match(args.get("right_color"), _COLOR_WORDS),
        "right_shape": _word_match(args.get("right_shape"), _SHAPE_WORDS),
    }
    out["field_checks"] = checks
    if not tool_valid:
        out.update(verdict="UNKNOWN", reason="tool_call_id_or_name_invalid")
        return out
    if any(v is None for v in checks.values()):
        out.update(verdict="UNKNOWN",
                   reason="tool_arguments_fields_unparseable")
        return out
    correct = (checks["left_color"] == expected["left_color"]
               and checks["left_shape"] == expected["left_shape"]
               and checks["right_color"] == expected["right_color"]
               and checks["right_shape"] == expected["right_shape"])
    out.update(verdict="PASS" if correct else "FAIL",
               reason="all_fields_match_expected" if correct
                      else "parsed_field_is_wrong")
    return out


def judge_D_create(rec: dict) -> dict:
    if not rec.get("ok"):
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "details": rec}
    if rec.get("http_status") != 200:
        return {"verdict": "FAIL", "reason": f"http_{rec.get('http_status')}",
                "error": rec.get("json"), "details": rec}
    out = (rec.get("json") or {}).get("output") or {}
    task_id = out.get("task_id")
    if not task_id:
        return {"verdict": "FAIL", "reason": "no_task_id", "details": rec}
    return {"verdict": "PASS", "reason": "task_created",
            "task_id": task_id, "task_status": out.get("task_status"),
            "request_id": (rec.get("json") or {}).get("request_id")}


def judge_D_video(dl: dict, ffprobe: dict | None, decode_ok: bool | None,
                  frames: list, first_last_diff: float | None) -> dict:
    if not dl.get("ok"):
        return {"verdict": "FAIL", "reason": f"download_failed_{dl.get('error_type')}",
                "details": dl}
    if ffprobe is None:
        return {"verdict": "FAIL", "reason": "ffprobe_failed"}
    v = ffprobe.get("video_stream") or {}
    checks = {
        "codec_h264": v.get("codec_name") == "h264",
        "has_audio_stream": ffprobe.get("has_audio_stream", True),
        "duration_about_5s": abs((ffprobe.get("duration_s") or 0) - 5) <= 0.75,
        "ratio_about_16_9": (v.get("width") and v.get("height")
                             and 1.6 <= v["width"] / v["height"] <= 1.85),
        "decode_ok": decode_ok is True,
        "frames_extracted": len(frames) >= 2,
        "motion_seen": (first_last_diff is not None and first_last_diff > 0.005),
        "layout_left_green": ffprobe.get("frame_stats", {}).get(
            "left_green_min_share", 0.0) >= 0.02,
        "layout_right_blue": ffprobe.get("frame_stats", {}).get(
            "right_blue_min_share", 0.0) >= 0.02,
    }
    hard = ["codec_h264", "duration_about_5s", "ratio_about_16_9", "decode_ok"]
    layout_hard = [k for k in checks if k.startswith("layout_")]
    if all(checks[k] for k in hard) and not checks["has_audio_stream"]:
        if checks["motion_seen"] and all(checks[k] for k in layout_hard):
            verdict = "PASS"
        elif not checks["motion_seen"]:
            verdict = "FAIL"
            checks["motion_note"] = "frames show no measurable difference"
        else:
            verdict = "FAIL"
        return {"verdict": verdict, "checks": checks,
                "note": "successful MP4 download alone proves nothing; no "
                        "strict video quality scoring is claimed"}
    return {"verdict": "FAIL", "checks": checks,
            "reason": "technical_check_failed"}


# --------------------------------------------------------------------------- #
# video poll loop (never creates a second task; injectable sleep for tests)
# --------------------------------------------------------------------------- #

def poll_video(counters: Counters, client: httpx.Client, task_id: str,
               deadline: float, sleep_fn=time.sleep) -> dict:
    """Poll the ONE task until terminal state, 40 polls, or deadline.
    Only GET requests are issued here; creation never re-runs."""
    log = []
    url = VIDEO_TASK_URL + task_id
    last = None
    for i in range(POLL_MAX):
        if time.monotonic() > deadline - RESERVE_FOR_FINISH_S:
            last = {"stop": "deadline_reserve_reached",
                    "polls_done": i, "task_status": (log[-1] or {}).get(
                        "task_status") if log else None}
            log.append(last)
            return {"terminal": None, "polls": i, "log": log}
        rec = http_call(counters, client, "GET", url,
                        counter_key="poll", deadline=deadline)
        out = (rec.get("json") or {}).get("output") or {}
        status = out.get("task_status")
        entry = {"poll_index": i, "ok": rec.get("ok"),
                 "http_status": rec.get("http_status"),
                 "task_status": status,
                 "request_id": (rec.get("json") or {}).get("request_id"),
                 "error_code": out.get("code"),
                 "error_message": out.get("message")}
        log.append(entry)
        if not rec.get("ok"):
            return {"terminal": "CLIENT_ERROR", "polls": i + 1, "log": log}
        if status == "SUCCEEDED":
            return {"terminal": "SUCCEEDED", "polls": i + 1, "log": log,
                    "video_url": out.get("video_url"),
                    "usage": (rec.get("json") or {}).get("usage"),
                    "final_output": out}
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            return {"terminal": status, "polls": i + 1, "log": log,
                    "final_output": out}
        sleep_fn(POLL_INTERVAL_S)
    last = {"stop": "poll_budget_exhausted",
            "task_status": (log[-1] or {}).get("task_status") if log else None}
    log.append(last)
    return {"terminal": None, "polls": POLL_MAX, "log": log}


# --------------------------------------------------------------------------- #
# ffprobe / ffmpeg helpers (subprocess, offline-testable via injection)
# --------------------------------------------------------------------------- #

def run_cmd(argv: list) -> dict:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return {"returncode": p.returncode, "stdout": p.stdout,
                "stderr": p.stderr[:2000]}
    except Exception as exc:  # noqa: BLE001
        return {"returncode": -1, "stdout": "", "stderr": str(exc)[:500],
                "error_type": type(exc).__name__}


def ffprobe_video(path: Path) -> dict | None:
    r = run_cmd(["ffprobe", "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", str(path)])
    if r["returncode"] != 0:
        return None
    try:
        j = json.loads(r["stdout"])
    except Exception:  # noqa: BLE001
        return None
    streams = j.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        return None
    return {"video_stream": {k: video.get(k) for k in
                             ("codec_name", "width", "height",
                              "r_frame_rate", "pix_fmt")},
            "has_audio_stream": any(s.get("codec_type") == "audio"
                                    for s in streams),
            "duration_s": float((j.get("format") or {}).get("duration", 0))}


def decode_check(path: Path) -> bool | None:
    r = run_cmd(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])
    return r["returncode"] == 0 and not r["stderr"].strip()


def extract_frames(path: Path, dest_dir: Path) -> list:
    dest_dir.mkdir(parents=True, exist_ok=True)
    r = run_cmd(["ffmpeg", "-y", "-v", "error", "-i", str(path),
                 "-vf", "fps=1", str(dest_dir / "f%02d.png")])
    if r["returncode"] != 0:
        return []
    return sorted(dest_dir.glob("f*.png"))


def frame_motion_and_layout(frames: list) -> tuple[float | None, dict]:
    """First-vs-last sampled pixel difference ratio + per-frame layout stats."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None, {}
    if len(frames) < 2:
        return None, {}
    stats = []
    opened = []
    for f in frames:
        with Image.open(f) as im:
            opened.append(im.convert("RGB").copy())
    for im in opened:
        st = region_stats(im)
        stats.append(st)
    a, b = opened[0], opened[-1]
    if a.size != b.size:
        return None, {"frame_stats_list": stats}
    pa, pb = a.load(), b.load()
    w, h = a.size
    step = max(1, min(w, h) // 200)
    diff = 0
    total = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            total += 1
            ra, ga, ba_ = pa[x, y]
            rb, gb, bb = pb[x, y]
            if abs(ra - rb) + abs(ga - gb) + abs(ba_ - bb) > 45:
                diff += 1
    layout = {
        "left_green_min_share": min(
            (s.get("left") or {}).get("green", 0.0) for s in stats),
        "right_blue_min_share": min(
            (s.get("right") or {}).get("blue", 0.0) for s in stats),
        "white_bg_min_share": min(
            (s.get("whole") or {}).get("white", 0.0) for s in stats),
    }
    return (diff / total if total else 0.0), {"layout": layout,
                                              "frame_stats_list": stats}


# --------------------------------------------------------------------------- #
# atomic persistence
# --------------------------------------------------------------------------- #

def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
    tmp.rename(path)


def file_record(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build_manifest(probe_dir: Path, inputs: dict) -> dict:
    files = {}
    for p in sorted(probe_dir.rglob("*")):
        if not p.is_file() or p.name in ("manifest.json",):
            continue
        rel = str(p.relative_to(probe_dir))
        if p.suffix == ".part":
            continue
        files[rel] = file_record(p)
    return {"task": "BAILIAN-GENERATION-SMOKE-01",
            "note": "manifest does not self-hash; .part temporaries excluded",
            "inputs": inputs, "files": files}


# --------------------------------------------------------------------------- #
# execution (the only network-bearing path; --execute gated)
# --------------------------------------------------------------------------- #

def _media_url_from_images_response(rec: dict) -> str | None:
    try:
        return ((rec.get("json") or {}).get("data") or [{}])[0].get("url")
    except Exception:  # noqa: BLE001
        return None


def execute() -> int:
    t0 = time.monotonic()
    deadline = t0 + DEADLINE_S
    counters = Counters()
    state = {
        "schema": "bailian-generation-smoke-01-v1",
        "task": "BAILIAN-GENERATION-SMOKE-01",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "route": {"region": "cn-beijing",
                  "base_url_compatible": COMPAT_BASE,
                  "base_url_native": NATIVE_BASE,
                  "credential_env": CREDENTIAL_ENV,
                  "credential_file": str(CREDENTIAL_FILE),
                  "credential_value_stored": False},
        "models": {"image": MODEL_IMAGE, "chat": MODEL_CHAT,
                   "video": MODEL_VIDEO},
        "steps": {},
        "timings": {},
        "verdicts": {},
    }
    vpath = PROBE_DIR / "verification.json"
    cpath = PROBE_DIR / "counts.json"

    def persist() -> None:
        state["counters"] = counters.snapshot()
        state["timings"]["total_wall_s"] = round(time.monotonic() - t0, 3)
        write_json(vpath, state)
        write_json(cpath, counters.snapshot())

    persist()  # counts live even if everything below crashes
    api_key = load_credential()  # only now; never enters any record
    auth = {"Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"}
    api = make_api_client()
    media = make_media_client()
    exit_code = 0
    try:
        # ---------------- A: image generation (1 model op) ----------------
        ta = time.monotonic()
        recA = http_call(counters, api, "POST", IMAGES_URL,
                         counter_key="model", headers=auth, body=body_A(),
                         deadline=deadline, guard_model=True)
        # FULL record retention (post-run fix 2026-10-23: the first run kept
        # only selected fields and lost the empty 404 body evidence; the fix
        # stores the complete redacted record; no re-send was performed)
        state["steps"]["A_image_generation"] = {
            "request": recA,
            "response_usage": (recA.get("json") or {}).get("usage"),
            "response_error": (recA.get("json") or {}).get("error"),
            "model_sent": MODEL_IMAGE,
            "model_in_response": None,
        }
        evA = None
        urlA = _media_url_from_images_response(recA)
        if urlA:
            dlA = download_media(counters, media, urlA,
                                 PROBE_DIR / "A-generated.png", IMG_DL_CAP,
                                 deadline)
            state["steps"]["A_image_generation"]["download"] = dlA
            if dlA.get("ok"):
                evA = image_evidence(PROBE_DIR / "A-generated.png")
                state["steps"]["A_image_generation"]["media"] = evA
        vA = judge_A(recA, evA or {})
        state["verdicts"]["A_image_generation"] = vA
        state["timings"]["A_wait_s"] = round(time.monotonic() - ta, 3)
        persist()
        if vA["verdict"] != "PASS":
            exit_code = 7
            raise SendLimitExceeded(
                f"A did not PASS ({vA['verdict']}/{vA['reason']}); "
                "sequence stops; B/C/D recorded NOT_EXECUTED")

        # ---------------- B: image edit with A as single reference ----------
        tb = time.monotonic()
        ref_png = (PROBE_DIR / "A-generated.png").read_bytes()
        recB = http_call(counters, api, "POST", IMAGES_URL,
                         counter_key="model", headers=auth,
                         body=body_B(ref_png), deadline=deadline,
                         guard_model=True)
        state["steps"]["B_image_edit"] = {
            "request": recB,
            "response_usage": (recB.get("json") or {}).get("usage"),
            "response_error": (recB.get("json") or {}).get("error"),
            "reference_images": 1,
        }
        evB = None
        urlB = _media_url_from_images_response(recB)
        if urlB:
            dlB = download_media(counters, media, urlB,
                                 PROBE_DIR / "B-edited.png", IMG_DL_CAP,
                                 deadline)
            state["steps"]["B_image_edit"]["download"] = dlB
            if dlB.get("ok"):
                evB = image_evidence(PROBE_DIR / "B-edited.png")
                state["steps"]["B_image_edit"]["media"] = evB
        vB = judge_B(recB, evB or {}, evA or {})
        state["verdicts"]["B_image_edit"] = vB
        state["timings"]["B_wait_s"] = round(time.monotonic() - tb, 3)
        persist()
        if vB["verdict"] != "PASS":
            exit_code = 7
            raise SendLimitExceeded(
                f"B did not PASS ({vB['verdict']}/{vB['reason']}); "
                "sequence stops; C/D recorded NOT_EXECUTED")

        # ---------------- C: chat vision + forced tool call ----------------
        tc = time.monotonic()
        b_png = (PROBE_DIR / "B-edited.png").read_bytes()
        recC = http_call(counters, api, "POST", CHAT_URL, counter_key="model",
                         headers=auth, body=body_C(b_png),
                         deadline=deadline, guard_model=True)
        jc = recC.get("json") or {}
        state["steps"]["C_chat_vision_tool"] = {
            "request": recC,
            "response_model": jc.get("model"),
            "response_id": jc.get("id"),
            "finish_reason": ((jc.get("choices") or [{}])[0]
                              .get("finish_reason")),
            "usage": jc.get("usage"),
            "error": jc.get("error"),
            "not_retested_this_round": ["tool result round-trip "
                                        "(tool message send-back)"],
        }
        vC = judge_C(recC, evB or {})
        state["verdicts"]["C_chat_vision_tool"] = vC
        state["timings"]["C_request_s"] = round(time.monotonic() - tc, 3)
        persist()
        if vC["verdict"] != "PASS":
            exit_code = 7
            raise SendLimitExceeded(
                f"C did not PASS ({vC['verdict']}/{vC['reason']}); "
                "sequence stops; D recorded NOT_EXECUTED")

        # ---------------- D: video create -> poll -> download ---------------
        td = time.monotonic()
        recD = http_call(counters, api, "POST", VIDEO_CREATE_URL,
                         counter_key="create",
                         headers={**auth, "X-DashScope-Async": "enable"},
                         body=body_D(b_png), deadline=deadline,
                         guard_model=True)
        vDc = judge_D_create(recD)
        state["steps"]["D_video"] = {
            "create_request": recD,
            "create_verdict": vDc,
            "parameters": {"resolution": "720P", "duration": 5,
                           "audio": False, "prompt_extend": False,
                           "watermark": False,
                           "img_url_role": "first_frame"},
        }
        state["timings"]["D_create_wall_s"] = round(time.monotonic() - td, 3)
        persist()
        if vDc["verdict"] != "PASS":
            exit_code = 7
            raise SendLimitExceeded(
                f"D create did not PASS ({vDc['verdict']}/{vDc['reason']}); "
                "sequence stops")
        task_id = vDc["task_id"]
        write_json(PROBE_DIR / "d-task-id.json",
                   {"task_id": task_id, "created_at_local":
                    time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "validity_note": "task_id valid 24h; video_url 24h"})

        tsubmit = time.monotonic()
        poll = poll_video(counters, api, task_id, deadline)
        state["steps"]["D_video"]["poll"] = {
            "terminal": poll.get("terminal"), "polls": poll.get("polls"),
            "log": poll.get("log"), "usage": poll.get("usage")}
        state["timings"]["D_submit_to_terminal_s"] = round(
            time.monotonic() - tsubmit, 3)
        persist()
        if poll.get("terminal") == "SUCCEEDED":
            state["timings"]["D_submit_to_first_success_s"] = round(
                time.monotonic() - tsubmit, 3)
            tdl = time.monotonic()
            dlV = download_media(counters, media, poll["video_url"],
                                 PROBE_DIR / "D-video.mp4", VIDEO_DL_CAP,
                                 deadline)
            state["steps"]["D_video"]["download"] = dlV
            state["timings"]["D_video_download_s"] = round(
                time.monotonic() - tdl, 3)
            persist()
            if dlV.get("ok"):
                ffp = ffprobe_video(PROBE_DIR / "D-video.mp4")
                dec = decode_check(PROBE_DIR / "D-video.mp4")
                frames = extract_frames(PROBE_DIR / "D-video.mp4",
                                        PROBE_DIR / "frames")
                diff, fstats = frame_motion_and_layout(frames)
                if ffp:
                    ffp["frame_stats"] = fstats.get("layout")
                state["steps"]["D_video"]["media"] = {
                    "ffprobe": ffp, "decode_ok": dec,
                    "frames": [f.name for f in frames],
                    "first_last_diff_ratio": diff,
                    "frame_stats_list": fstats.get("frame_stats_list"),
                }
                vDv = judge_D_video(dlV, ffp, dec, frames, diff)
                state["verdicts"]["D_video"] = {
                    "verdict": vDv["verdict"], "reason": vDv.get("reason"),
                    "checks": vDv.get("checks"), "note": vDv.get("note"),
                    "create": "PASS"}
                if vDv["verdict"] != "PASS":
                    exit_code = 7
            else:
                state["verdicts"]["D_video"] = {
                    "verdict": "FAIL", "reason": "video_download_failed",
                    "create": "PASS"}
                exit_code = 7
        else:
            # FAILED / CANCELED / UNKNOWN / not-finished
            term = poll.get("terminal")
            if term in ("FAILED", "CANCELED", "UNKNOWN"):
                state["verdicts"]["D_video"] = {
                    "verdict": "FAIL", "reason": f"task_{term}",
                    "create": "PASS",
                    "final_output": poll.get("final_output")}
                exit_code = 7
            else:
                state["verdicts"]["D_video"] = {
                    "verdict": "UNKNOWN", "reason": "timeout_task_still_running",
                    "create": "PASS",
                    "task_id": task_id,
                    "note": "polls/deadline exhausted while task still "
                            "PENDING/RUNNING; the remote task may keep "
                            "running and may still incur cost; the cancel "
                            "API was NOT verified and no cancellation is "
                            "claimed"}
                exit_code = 7
        persist()
    except SendLimitExceeded as exc:
        # necessary-step failure: stop, record which steps were not executed
        done = set(state["verdicts"].keys())
        order = ["A_image_generation", "B_image_edit", "C_chat_vision_tool",
                 "D_video"]
        for step in order:
            if step not in done:
                state["verdicts"][step] = {"verdict": "NOT_EXECUTED",
                                           "reason": "stopped_after_"
                                                     "earlier_step_failure",
                                           "stop_cause": str(exc)[:300]}
        state["stop_cause"] = str(exc)[:300]
        persist()
    except Exception as exc:  # noqa: BLE001 — everything lands on disk
        state["unexpected_error"] = {"type": type(exc).__name__,
                                     "redacted": redact(str(exc))[:800]}
        done = set(state["verdicts"].keys())
        for step in ("A_image_generation", "B_image_edit",
                     "C_chat_vision_tool", "D_video"):
            if step not in done:
                state["verdicts"][step] = {"verdict": "NOT_EXECUTED",
                                           "reason": "unexpected_error"}
        exit_code = 7
        persist()
    finally:
        api.close()
        media.close()
        persist()
        auth.pop("Authorization", None)
        write_json(PROBE_DIR / "manifest.json",
                   build_manifest(PROBE_DIR, inputs={
                       "plan": "plan.json", "probe_code": "probe.py",
                       "credential": {"file": str(CREDENTIAL_FILE),
                                      "env": CREDENTIAL_ENV,
                                      "value_stored": False}}))
    summary = {
        "A_image_generation": state["verdicts"].get(
            "A_image_generation", {}).get("verdict"),
        "B_image_edit": state["verdicts"].get("B_image_edit", {}).get("verdict"),
        "C_chat_vision_tool": state["verdicts"].get(
            "C_chat_vision_tool", {}).get("verdict"),
        "D_video": state["verdicts"].get("D_video", {}).get("verdict"),
        "counters": counters.snapshot(),
        "report": str(vpath),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return exit_code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--i-approve-bailian-generation-smoke-01", action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_bailian_generation_smoke_01:
            print("refusing: --execute requires "
                  "--i-approve-bailian-generation-smoke-01")
            return 2
        if (PROBE_DIR / "verification.json").exists():
            print("refusing: existing verification.json in target directory; "
                  "prior probe evidence is never overwritten")
            return 3
        return execute()
    print("offline mode; unit tests cover bodies, counters, judges, "
          "redaction, polling and parsing with MockTransport only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
