#!/usr/bin/env python3
"""BAILIAN-VISION-SMOKE-01: one-shot image understanding probe on the
registered Aliyun Bailian (DashScope) route via the Responses API.

Fixed configuration (from task; official docs confirmed 2026-10-21):
  base_url https://dashscope.aliyuncs.com/compatible-mode/v1 (Beijing;
  legacy domain officially still valid), model qwen3.7-plus, POST
  /compatible-mode/v1/responses, credential DASHSCOPE_API_KEY loaded from
  /home/lcq/.config/agent-workload-characterization/bailian.env (value
  never echoed, stored, hashed or logged).

Guards: exactly ONE send max (counted at the send boundary including
failures); no retries; redirects never followed; no model/provider switch;
max_output_tokens 2048 (<=4096; for qwen3.7 it caps REPLY tokens only,
thinking is NOT counted per official docs); 90s request wall; no
reasoning/enable_thinking parameter (official effort tiers for qwen3.7-plus
are not explicitly listed — per the task, unconfirmed private parameters
are NOT guessed; thinking stays at its default which does not consume
max_output_tokens for this model family).

Judgement rules (fixed BEFORE the send):
  PASS    = red-circle count, blue-square count, red-side location and the
            color/shape binding all correct; extra explanatory words never
            fail vision;
  FAIL    = a clearly parsed fact is wrong, or the model explicitly states
            it cannot process the image;
  UNKNOWN = ambiguous/unparseable answer, no final answer, incomplete,
            timeout, auth or transport failure — each recorded distinctly,
            never lumped together as "model cannot see images".

Evidence: SSE terminal state and usage are saved IN FULL — no display
length cap truncates the unique evidence (fixes the CAPABILITY/VISION-01
recording defect)."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import video_use_volcano_capability_01 as v01  # noqa: E402
import video_use_volcano_vision_01 as vision01  # noqa: E402  (image generator reuse)

PROBE_DIR = ROOT / "env/video/video-use/api-probes/BAILIAN-VISION-SMOKE-01"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.7-plus"
CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
CREDENTIAL_ENV = "DASHSCOPE_API_KEY"
MAX_SENDS = 1
MAX_OUTPUT_TOKENS = 2048
REQUEST_WALL_LIMIT_S = 90.0

QUESTION = "请说明图片中两类图形的颜色、形状、各自数量和左右位置。"


def load_credential() -> str:
    """Load DASHSCOPE_API_KEY from the designated file without echoing it.
    Called only right before the send; the value is never returned to any
    record."""
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
                     "(names only were inspected; no values printed)")


def image_body(png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "model": MODEL,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": QUESTION},
            {"type": "input_image",
             "image_url": f"data:image/png;base64,{b64}"}]}],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }


# --------------------------------------------------------------------------- #
# fixed judgement rules for free-form Chinese replies (defined pre-send)
# --------------------------------------------------------------------------- #

_NUM = r"(\d+)\s*个"
# color+shape words with a count inside a small window, both orders
_RE_COUNT_COLOR_FIRST = re.compile(
    r"(红色|蓝色)[的]?\s*(圆形|圆形图案|圆|正方形|方形|方)[^。,;、]{0,12}?" + _NUM)
_RE_COUNT_NUM_FIRST = re.compile(
    _NUM + r"[^。,;、]{0,10}?(红色|蓝色)[的]?\s*(圆形|圆|正方形|方形|方)")
# location statements, both directions
_RE_COLOR_AT_SIDE = re.compile(
    r"(红色|蓝色)[的]?(?:圆形|圆|正方形|方形|方|图形|形状)[^。,;、]{0,12}?"
    r"[在位][于]?(左|右)(?:侧|边|半边|半部分)?")
_RE_SIDE_HAS_COLOR = re.compile(
    r"(?:左|右)(?:侧|边)[是为有][^。,;、]{0,16}?(红色|蓝色)")
_CANNOT_SEE_RES = re.compile(
    r"(无法|不能|不可以|看不到|无法看到|无法识别|无法处理|不能处理)"
    r"[^。,;]{0,12}(图片|图像|画面|内容)")


def normalize_truth(gt: dict) -> dict:
    """Adapt vision01's left/right ground-truth shape to flat fields."""
    red_side = gt["red_side"]
    red = gt["left"] if red_side == "left" else gt["right"]
    blue = gt["right"] if red_side == "left" else gt["left"]
    return {"red_circles": red["count"], "blue_squares": blue["count"],
            "red_side": red_side}


def _side_block(reply: str, side: str) -> str | None:
    """Extract the text block describing one side: from the first mention
    of this side up to the next mention of the OPPOSITE side (or 160
    chars). Handles both prose and markdown list layouts."""
    opposite = "右" if side == "左" else "左"
    m = re.search(side + r"(?:侧|边|半边|半部分)", reply)
    if not m:
        return None
    rest = reply[m.end():]
    nxt = re.search(opposite + r"(?:侧|边|半边|半部分)", rest)
    end = m.end() + (nxt.start() if nxt else 160)
    return reply[m.start():min(len(reply), end)]


def _block_facts(block: str) -> dict | None:
    if not block:
        return None
    color_m = re.search(r"(红色|蓝色)", block)
    shape_m = re.search(r"(圆形|圆|正方形|方形|方)", block)
    count_m = re.search(r"(\d+)\s*个", block)
    if not (color_m and shape_m and count_m):
        return None
    return {"color": color_m.group(1), "shape": shape_m.group(1),
            "count": int(count_m.group(1))}


def parse_chinese_reply(reply: str) -> dict:
    parsed = {"red": None, "blue": None, "red_side": None,
              "shape_binding": {}}
    # primary strategy: side blocks (handles prose AND markdown lists where
    # color/shape/count appear on separate lines)
    left = _block_facts(_side_block(reply, "左"))
    right = _block_facts(_side_block(reply, "右"))
    if left and right:
        for facts, side_name in ((left, "left"), (right, "right")):
            key = "red" if facts["color"] == "红色" else "blue"
            if parsed[key] is None:
                parsed[key] = facts["count"]
                parsed["shape_binding"][key] = facts["shape"]
        if left["color"] == "红色":
            parsed["red_side"] = "left"
        elif left["color"] == "蓝色":
            parsed["red_side"] = "right"
        if parsed["red"] is not None and parsed["blue"] is not None:
            # an EXPLICIT position statement overrides the block inference:
            # it is the model's direct answer to the location question
            m = _RE_COLOR_AT_SIDE.search(reply)
            if m:
                declared = ("left" if ((m.group(1) == "红色")
                                       == (m.group(2) == "左")) else "right")
                parsed["red_side"] = declared
            return parsed
    # fallback: co-occurrence regexes (single-phrase layouts)
    for m in _RE_COUNT_COLOR_FIRST.finditer(reply):
        color = m.group(1)
        count = int(m.group(3))
        if color == "红色" and parsed["red"] is None:
            parsed["red"] = count
            parsed["shape_binding"]["red"] = m.group(2)
        elif color == "蓝色" and parsed["blue"] is None:
            parsed["blue"] = count
            parsed["shape_binding"]["blue"] = m.group(2)
    if parsed["red"] is None or parsed["blue"] is None:
        for m in _RE_COUNT_NUM_FIRST.finditer(reply):
            # groups: 1=count, 2=color, 3=shape
            count, color, shape = int(m.group(1)), m.group(2), m.group(3)
            if color == "红色" and parsed["red"] is None:
                parsed["red"] = count
                parsed["shape_binding"]["red"] = shape
            elif color == "蓝色" and parsed["blue"] is None:
                parsed["blue"] = count
                parsed["shape_binding"]["blue"] = shape
    m = _RE_COLOR_AT_SIDE.search(reply)
    if m:
        parsed["red_side"] = "left" if (
            (m.group(1) == "红色") == (m.group(2) == "左")) else "right"
    if parsed["red_side"] is None:
        m = _RE_SIDE_HAS_COLOR.search(reply)
        if m:
            # the match STARTS with the side word (左/右)
            side = "left" if reply[m.start()] == "左" else "right"
            parsed["red_side"] = side if m.group(1) == "红色" else (
                "right" if side == "left" else "left")
    return parsed


def verdict(send: dict, sse: dict, reply: str, truth: dict) -> dict:
    if send.get("http_status") == 401:
        return {"verdict": "UNKNOWN", "reason": "auth_error", "facts": {}}
    if send.get("request_wall_exceeded"):
        return {"verdict": "UNKNOWN", "reason": "request_timeout",
                "facts": {}}
    if not send.get("ok") or send.get("http_status") != 200:
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "facts": {}, "http_status": send.get("http_status"),
                "error_type": send.get("error_type")}
    if not sse.get("terminal_seen"):
        return {"verdict": "UNKNOWN", "reason": "no_terminal_event", "facts": {}}
    if sse.get("incomplete"):
        return {"verdict": "UNKNOWN", "reason": "response_incomplete",
                "facts": {}}
    text = reply or ""
    if _CANNOT_SEE_RES.search(text):
        return {"verdict": "FAIL",
                "reason": "model_states_it_cannot_process_image",
                "facts": {}, "reply_excerpt": text.strip()[:400]}
    parsed = parse_chinese_reply(text)
    checks = {
        "red_count": (parsed["red"] == truth["red_circles"]
                      if parsed["red"] is not None else None),
        "blue_count": (parsed["blue"] == truth["blue_squares"]
                       if parsed["blue"] is not None else None),
        "red_side": (parsed["red_side"] == truth["red_side"]
                     if parsed["red_side"] is not None else None),
        "shape_binding": (
            (parsed["shape_binding"].get("red", "").startswith("圆")
             and parsed["shape_binding"].get("blue", "").find("方") >= 0)
            if (parsed["shape_binding"].get("red")
                and parsed["shape_binding"].get("blue")) else None),
    }
    values = list(checks.values())
    if any(v is False for v in values):
        result, reason = "FAIL", "clearly_parsed_fact_is_wrong"
    elif all(v is True for v in values):
        result, reason = "PASS", "all_facts_correct"
    else:
        result, reason = "UNKNOWN", "ambiguous_or_unparseable_answer"
    return {"verdict": result, "reason": reason,
            "facts": {"parsed": parsed, "expected": {
                "red_circles": truth["red_circles"],
                "blue_squares": truth["blue_squares"],
                "red_side": truth["red_side"]}},
            "fact_checks": checks,
            "reply_excerpt": text.strip()[:400],
            "note": "extra explanatory words never fail vision"}


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def execute() -> int:
    url = v01.build_responses_url(BASE_URL)
    gate = v01.SendGate(MAX_SENDS)

    png, gt = vision01.generate_test_image()
    truth = normalize_truth(gt)
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    (PROBE_DIR / "neutral-test.png").write_bytes(png)
    _write_json(PROBE_DIR / "expected-answer.json", {
        "task": "BAILIAN-VISION-SMOKE-01",
        "red_circles": truth["red_circles"], "blue_squares": truth["blue_squares"],
        "red_side": truth["red_side"],
        "image": {"path": "neutral-test.png",
                  "sha256": hashlib.sha256(png).hexdigest(),
                  "bytes": len(png), "size_px": gt["image_size"]},
        "question": QUESTION,
        "judgement_rules_fixed_pre_send": {
            "PASS": "red count, blue count, red-side location and color/shape "
                    "binding all correct; extra words never fail vision",
            "FAIL": "a clearly parsed fact is wrong, or the model states it "
                    "cannot process the image",
            "UNKNOWN": "ambiguous/unparseable, no final answer, incomplete, "
                       "timeout, auth or transport failure — recorded "
                       "distinctly, never lumped as vision failure"},
        "note": "not sent to the model; never modified after the send"})

    verification = {
        "schema": "bailian-vision-smoke-01-v1",
        "task": "BAILIAN-VISION-SMOKE-01",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "route": {"base_url": BASE_URL, "request_model": MODEL,
                  "responses_url": url, "protocol": "OpenAI Responses API",
                  "credential_env": CREDENTIAL_ENV,
                  "credential_file": str(CREDENTIAL_FILE),
                  "region_note": "Beijing; legacy dashscope domain "
                                 "officially still valid (docs 2026-10-21)"},
        "limits": {"max_sends": MAX_SENDS,
                   "max_output_tokens": MAX_OUTPUT_TOKENS,
                   "request_wall_limit_s": REQUEST_WALL_LIMIT_S,
                   "retries": "disabled", "redirects": "not followed",
                   "reasoning_param": "not sent — qwen3.7-plus effort tiers "
                                      "not explicitly listed in official "
                                      "docs; unconfirmed private parameters "
                                      "are not guessed. For qwen3.7 the "
                                      "max_output_tokens caps reply tokens "
                                      "only (thinking not counted, per docs)"},
        "official_doc_evidence_2026_10_21": [
            "help.aliyun.com/zh/model-studio/compatibility-with-openai-responses-api",
            "help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses",
            "help.aliyun.com/zh/model-studio/deep-thinking"],
        "probes": {}, "client_sends": None,
    }

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    api_key = load_credential()  # only now; value never leaves this scope
    headers["Authorization"] = f"Bearer {api_key}"
    try:
        record = v01.send_request(
            gate, v01.make_client_factory()(), "POST", url, headers=headers,
            body=image_body(png),
            deadline_monotonic=time.monotonic() + REQUEST_WALL_LIMIT_S)
    finally:
        headers.pop("Authorization", None)

    sse = v01.parse_sse(record.get("raw_lines") or [])
    if not sse.get("is_sse"):
        fallback = v01.parse_non_sse_json(record.get("raw_lines") or [])
        if fallback is not None:
            sse = fallback
    record.pop("raw_lines", None)
    record["sse"] = {k: v for k, v in sse.items() if k != "events"}
    # FULL retention — no display-length truncation of the unique evidence
    record["sse_events_redacted_full"] = [
        {"event": e.get("event"),
         "data": v01.redact(json.dumps(e.get("data"), ensure_ascii=False))}
        for e in sse.get("events", [])]

    reply = v01.extract_final_text(sse.get("events", []))
    result = verdict(record, sse, reply, truth)
    result["status"] = "executed"
    result["send"] = record

    models, usage, status = set(), [], None
    for e in sse.get("events", []):
        data = e.get("data") or {}
        if e.get("event") in ("response.completed", "response.incomplete",
                              "response.failed"):
            resp = data.get("response") or {}
            status = resp.get("status", status)
            if resp.get("model"):
                models.add(resp["model"])
            if resp.get("usage"):
                usage.append(resp["usage"])
    verification["probes"]["vision"] = result
    verification["response_status"] = status
    verification["request_model_sent"] = MODEL
    verification["response_models_observed"] = sorted(models) or ["unknown"]
    verification["usage_observed"] = usage or ["unknown"]
    verification["cost"] = "unknown; no independent billing evidence"
    verification["client_sends"] = gate.snapshot()
    verification["boundaries"] = (
        "One image probe on the registered Bailian route. Even PASS only "
        "proves THIS probe — not full Codex/video-us readiness, not "
        "comprehensive vision reliability.")
    _write_json(PROBE_DIR / "verification.json", verification)
    print(json.dumps({"vision": result["verdict"], "reason": result["reason"],
                      "status": status, "sends": gate.snapshot()["sends_initiated"],
                      "report": str(PROBE_DIR / "verification.json")},
                     ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--i-approve-bailian-vision-smoke-01", action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_bailian_vision_smoke_01:
            print("refusing: --execute requires "
                  "--i-approve-bailian-vision-smoke-01")
            return 2
        if (PROBE_DIR / "verification.json").exists():
            print("refusing: existing results in target directory; never "
                  "overwrite prior probe evidence")
            return 3
        return execute()
    print("offline mode; unit tests cover image/body/parsing/verdict/gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
