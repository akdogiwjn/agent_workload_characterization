#!/usr/bin/env python3
"""VIDEO-USE-VOLCANO-VISION-01: one-shot image understanding probe on the
registered Volcano route (exactly max ONE real send).

Prior facts (VIDEO-USE-VOLCANO-CAPABILITY-01/02, NOT re-tested here):
  - Responses endpoint + first tool call PASSED;
  - tool-result return: model echoed a character-identical random receipt
    (content-level evidence); the strict bare-value FAIL verdicts stand,
    untouched;
  - image understanding was NOT executed — this probe covers exactly that.

Guards (hard):
  - at most ONE send, counted at the send boundary including failures;
    no retries, redirects never followed, no Chat Completions fallback,
    no model listing, no image-generation API, no ElevenLabs, no CLI/docker;
  - credential read from VOLCANO_API_KEY only right before the send, never
    stored/hashed/printed; retained text redacted;
  - per-request wall 90s; max_output_tokens <= 2048;
  - the image, expected answer and judgement rules are persisted BEFORE
    the send and never modified afterwards.

Judgement rules (fixed before any send):
  PASS    = every fact (left-side color/shape/count, right-side
            color/shape/count, red-side location) is correctly identified;
            extra explanatory words do NOT fail vision (format is judged
            separately);
  FAIL    = a clearly parsed fact is wrong, or the model explicitly says
            it cannot see/process images (gateway-reported no image
            support — kept distinct from transport faults);
  UNKNOWN = ambiguous / unparseable / insufficient answer, or
            transport/HTTP/protocol failure (never auto-attributed to
            vision capability).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import video_use_volcano_capability_01 as v01  # noqa: E402

PROBE_DIR = ROOT / "env/video/video-use/api-probes/VIDEO-USE-VOLCANO-VISION-01"
REGISTERED_ROUTE = v01.REGISTERED_ROUTE
MAX_SENDS = 1
MAX_OUTPUT_TOKENS = 1024
REQUEST_WALL_LIMIT_S = 90.0

IMAGE_PROMPT = (
    "Look at the image. It shows shapes on a white background split into a "
    "left side and a right side. Answer using exactly these three lines:\n"
    "left side: <count> <color> <shape>s\n"
    "right side: <count> <color> <shape>s\n"
    "red shapes are on the <left/right> side\n"
    "Use color words red or blue, shape words circle or circle(s), square "
    "or square(s), and replace <count> with the number.")


# --------------------------------------------------------------------------- #
# image generation (stdlib PNG via the reused minimal encoder)
# --------------------------------------------------------------------------- #

def generate_test_image() -> tuple[bytes, dict]:
    """White background ~512x256; red circles on one side, blue squares on
    the other; counts 1..3 each; side assignment random; shapes placed in
    per-side column slots so they never overlap; no text drawn."""
    rng = uuid.uuid4
    width, height = 512, 256
    n_circles = 1 + rng().int % 3          # 1..3
    n_squares = 1 + rng().int % 3          # 1..3
    red_on_left = bool(rng().int % 2)
    pixels = [[(255, 255, 255)] * width for _ in range(height)]
    shapes = []

    def draw_circle(cx, cy, r, color):
        for yy in range(max(0, cy - r), min(height, cy + r + 1)):
            for xx in range(max(0, cx - r), min(width, cx + r + 1)):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    pixels[yy][xx] = color

    def draw_square(x, y, w, color):
        for yy in range(max(0, y), min(height, y + w + 1)):
            for xx in range(max(0, x), min(width, x + w + 1)):
                pixels[yy][xx] = color

    def side_slots(x0, x1, count):
        """Non-overlapping column slots with generous spacing."""
        slot_w = (x1 - x0) // 3
        slots = []
        for i in range(count):
            cx = x0 + slot_w * i + slot_w // 2 + (rng().int % 9 - 4)
            slots.append(cx)
        return slots

    def place(side_name, x0, x1, count, kind):
        for cx in side_slots(x0, x1, count):
            if kind == "circle":
                r = 18 + rng().int % 9
                cy = 60 + rng().int % (height - 120)
                draw_circle(cx, cy, r, (220, 20, 20))
                shapes.append({"side": side_name, "shape": "circle",
                               "color": "red", "cx": cx, "cy": cy, "r": r})
            else:
                w = 34 + rng().int % 16
                cy = 60 + rng().int % (height - 120 - w)
                draw_square(cx - w // 2, cy, w, (20, 20, 220))
                shapes.append({"side": side_name, "shape": "square",
                               "color": "blue", "cx": cx, "cy": cy, "w": w})

    if red_on_left:
        place("left", 40, 232, n_circles, "circle")
        place("right", 280, 472, n_squares, "square")
    else:
        place("left", 40, 232, n_squares, "square")
        place("right", 280, 472, n_circles, "circle")

    png = v01._write_png(width, height, pixels)
    left = {"color": "red" if red_on_left else "blue",
            "shape": "circle" if red_on_left else "square",
            "count": n_circles if red_on_left else n_squares}
    right = {"color": "blue" if red_on_left else "red",
             "shape": "square" if red_on_left else "circle",
             "count": n_squares if red_on_left else n_circles}
    ground_truth = {"left": left, "right": right,
                    "red_side": "left" if red_on_left else "right",
                    "shapes": shapes, "image_size": [width, height]}
    return png, ground_truth


def image_body(model: str, png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "model": model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": IMAGE_PROMPT},
            {"type": "input_image",
             "image_url": f"data:image/png;base64,{b64}"}]}],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }


# --------------------------------------------------------------------------- #
# fixed judgement (defined before any send; extra words never fail vision)
# --------------------------------------------------------------------------- #

_LINE_RES = {
    "left": re.compile(r"(?i)left\s*side\s*[:\-]?\s*(\d+)\s*(red|blue)\s*"
                       r"(circle|square)s?"),
    "right": re.compile(r"(?i)right\s*side\s*[:\-]?\s*(\d+)\s*(red|blue)\s*"
                        r"(circle|square)s?"),
}
_RED_SIDE_RES = re.compile(r"(?i)red\s*shapes?\s+are\s+on\s+the\s+(left|right)"
                           r"\s*side")
_CANNOT_SEE_RES = re.compile(
    r"(?i)(cannot|can't|unable to|do not|don't)\s+(see|view|process|access|"
    r"handle|receive|detect)\s*(any\s+)?(the\s+)?(image|picture|photo)")


def parse_answer(reply: str) -> dict:
    parsed = {}
    for side, pattern in _LINE_RES.items():
        m = pattern.search(reply)
        parsed[side] = ({"count": int(m.group(1)),
                         "color": m.group(2).lower(),
                         "shape": m.group(3).lower()} if m else None)
    m = _RED_SIDE_RES.search(reply)
    parsed["red_side"] = m.group(1).lower() if m else None
    return parsed


def verdict_vision(send: dict, sse: dict, reply: str, truth: dict) -> dict:
    if not send.get("ok") or send.get("http_status") != 200:
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "facts": {}, "format_ok": None}
    if not sse.get("terminal_seen"):
        return {"verdict": "UNKNOWN", "reason": "protocol_not_terminal",
                "facts": {}, "format_ok": None}
    text = reply or ""
    if _CANNOT_SEE_RES.search(text):
        # gateway/model states it cannot handle the image — a MODEL
        # capability outcome, kept distinct from transport faults
        return {"verdict": "FAIL",
                "reason": "model_states_it_cannot_process_image",
                "facts": {}, "format_ok": False}
    parsed = parse_answer(text)
    checks = {
        "left_count": (parsed["left"] or {}).get("count") == truth["left"]["count"]
        if parsed["left"] else None,
        "left_color_shape": (
            parsed["left"] or {}).get("color") == truth["left"]["color"]
        and (parsed["left"] or {}).get("shape") == truth["left"]["shape"]
        if parsed["left"] else None,
        "right_count": (parsed["right"] or {}).get("count") == truth["right"]["count"]
        if parsed["right"] else None,
        "right_color_shape": (
            parsed["right"] or {}).get("color") == truth["right"]["color"]
        and (parsed["right"] or {}).get("shape") == truth["right"]["shape"]
        if parsed["right"] else None,
        "red_side": parsed["red_side"] == truth["red_side"]
        if parsed["red_side"] else None,
    }
    format_ok = all(v is not None for v in checks.values())
    values = list(checks.values())
    if any(v is False for v in values):
        verdict, reason = "FAIL", "clearly_parsed_fact_is_wrong"
    elif all(v is True for v in values):
        verdict, reason = "PASS", "all_facts_correct"
    else:
        verdict, reason = "UNKNOWN", "ambiguous_or_unparseable_answer"
    return {"verdict": verdict, "reason": reason,
            "facts": {"parsed": parsed, "expected": {
                "left": truth["left"], "right": truth["right"],
                "red_side": truth["red_side"]}},
            "fact_checks": checks, "format_ok": format_ok,
            "reply_excerpt": text.strip()[:400],
            "note": "extra explanatory words never fail vision; format is "
                    "judged separately as format_ok"}


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def execute() -> int:
    api_base = REGISTERED_ROUTE["api_base"]
    model = REGISTERED_ROUTE["request_model"]
    url = v01.build_responses_url(api_base)
    gate = v01.SendGate(MAX_SENDS)

    png, truth = generate_test_image()
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    (PROBE_DIR / "neutral-test.png").write_bytes(png)
    _write_json(PROBE_DIR / "expected-answer.json", {
        "task": "VIDEO-USE-VOLCANO-VISION-01",
        "left": truth["left"], "right": truth["right"],
        "red_side": truth["red_side"],
        "image": {"path": "neutral-test.png",
                  "sha256": hashlib.sha256(png).hexdigest(),
                  "bytes": len(png), "size_px": truth["image_size"]},
        "question": IMAGE_PROMPT,
        "judgement_rules_fixed_pre_send": {
            "PASS": "left/right color+shape+count and red-side location all "
                    "correct; extra words never fail vision",
            "FAIL": "a clearly parsed fact is wrong, or the model states it "
                    "cannot process the image",
            "UNKNOWN": "ambiguous/unparseable answer, or transport/HTTP/"
                       "protocol failure (not attributed to vision)",
            "format": "judged separately as format_ok; a bare 'I can see "
                      "images' claim or HTTP 200 never counts"},
        "note": "not sent to the model; never modified after the send"})

    verification = {
        "schema": "video-use-volcano-vision-01-v1",
        "task": "VIDEO-USE-VOLCANO-VISION-01",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "route": {"api_base": api_base, "request_model": model,
                  "credential_env": REGISTERED_ROUTE["credential_env"],
                  "responses_url": url,
                  "prior_facts": "CAPABILITY-01/02 responses+tool-call PASS "
                                 "and receipt echo stand; not re-tested here"},
        "limits": {"max_sends": MAX_SENDS,
                   "max_output_tokens": MAX_OUTPUT_TOKENS,
                   "request_wall_limit_s": REQUEST_WALL_LIMIT_S,
                   "retries": "disabled", "redirects": "not followed"},
        "image_delivered": None, "vision": None, "client_sends": None,
    }

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    api_key = os.environ.get(REGISTERED_ROUTE["credential_env"], "")
    if not api_key:
        raise SystemExit("credential env var empty — refusing to send "
                         "(no probe dispatched)")
    headers["Authorization"] = f"Bearer {api_key}"
    try:
        record = v01.send_request(
            gate, v01.make_client_factory()(), "POST", url, headers=headers,
            body=image_body(model, png),
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
    record["sse_events_redacted"] = [
        {"event": e.get("event"),
         "data": v01.redact(json.dumps(e.get("data"), ensure_ascii=False))[:4000]}
        for e in sse.get("events", [])]

    reply = v01.extract_final_text(sse.get("events", []))
    vision = verdict_vision(record, sse, reply, truth)
    verification["image_delivered"] = {
        "input_image_in_request": True,  # constructed locally, base64 data URL
        "image_sha256": hashlib.sha256(png).hexdigest(),
        "transport_ok": record.get("ok") and record.get("http_status") == 200}
    verification["responses_sse"] = {
        "http_status": record.get("http_status"),
        "sse_terminal": sse.get("terminal_seen"),
        "sse_completed": sse.get("completed")}
    verification["vision"] = vision
    verification["send"] = record

    models, usage = set(), []
    for e in record["sse_events_redacted"]:
        if e.get("event") == "response.completed":
            try:
                resp = (json.loads(e["data"]) or {}).get("response", {})
                if resp.get("model"):
                    models.add(resp["model"])
                if resp.get("usage"):
                    usage.append(resp["usage"])
            except json.JSONDecodeError:
                pass
    verification["request_model_sent"] = model
    verification["response_models_observed"] = sorted(models) or ["unknown"]
    verification["usage_observed"] = usage or ["unknown"]
    verification["cost"] = "unknown; no independent billing evidence"
    verification["client_sends"] = gate.snapshot()
    verification["boundaries"] = (
        "One image probe on the registered route. Even PASS only proves THIS "
        "probe passed — not comprehensive vision reliability, not full "
        "video-use readiness, not Codex CLI compatibility.")
    _write_json(PROBE_DIR / "verification.json", verification)
    print(json.dumps({"vision": vision["verdict"], "reason": vision["reason"],
                      "sends": gate.snapshot()["sends_initiated"],
                      "report": str(PROBE_DIR / "verification.json")},
                     ensure_ascii=False))
    return 0 if vision["verdict"] == "PASS" else 7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--i-approve-video-use-volcano-vision-01", action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_video_use_volcano_vision_01:
            print("refusing: --execute requires "
                  "--i-approve-video-use-volcano-vision-01")
            return 2
        if (PROBE_DIR / "verification.json").exists():
            print("refusing: existing results in target directory; never "
                  "overwrite prior probe evidence")
            return 3
        return execute()
    print("offline mode; unit tests cover image/body/verdict/gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
