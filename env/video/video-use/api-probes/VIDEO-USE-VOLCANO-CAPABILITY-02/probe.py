#!/usr/bin/env python3
"""VIDEO-USE-VOLCANO-CAPABILITY-02: verify tool-result return + image
understanding on the registered Volcano route (max 2 real sends).

Reuses VIDEO-USE-VOLCANO-CAPABILITY-01's already-verified context:
  - probe1 (Responses endpoint + forced tool call) PASSED and is NOT
    re-tested; its saved function_call (call_id/arguments) plus the
    reconstructable original input rebuild the full request history.
  - the old probe2 is evidence-insufficient (receipt not archived) — this
    round re-verifies with the expected receipt persisted BEFORE sending
    and an EXACT (whitespace-stripped) comparison.

Budget guards (hard):
  - at most 2 real sends, counted at the send boundary including failures;
  - no retries, redirects never followed, same endpoint/model/protocol;
  - credential read from VOLCANO_API_KEY only right before each send,
    never stored/hashed/printed; retained text redacted;
  - per-request wall 90s, whole network phase 200s;
  - max_output_tokens <= 2048; no model listing; no ElevenLabs/CLI/agent.

Judgement rules (fixed BEFORE any send):
  tool-result return:
    PASS   = HTTP ok + protocol terminal + receipt archived pre-send
             + model reply.strip() == expected receipt exactly;
    FAIL   = request answered but the receipt differs, or the protocol
             response violates requirements;
    UNKNOWN= transport/HTTP failure or probe-side defect (insufficient
             evidence) — never auto-attributed to the service.
  image understanding:
    PASS   = all three fixed questions (red circle count, blue square
             count, topmost shape color) answered correctly;
    FAIL   = a clearly parsed answer is wrong, or the model explicitly
             states it cannot see the image;
    UNKNOWN= answer present but ambiguous/unparseable;
    NOT_EXECUTED = request 1 not passed.
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
import video_use_volcano_capability_01 as v01  # noqa: E402  (reused, fixed components)

PROBE_DIR = ROOT / "env/video/video-use/api-probes/VIDEO-USE-VOLCANO-CAPABILITY-02"
V01_VERIFICATION = (ROOT / "env/video/video-use/api-probes"
                    / "VIDEO-USE-VOLCANO-CAPABILITY-01" / "verification.json")
MAX_SENDS = 2
MAX_OUTPUT_TOKENS = 1024
REQUEST_WALL_LIMIT_S = 90.0
PHASE_WALL_LIMIT_S = 200.0
REGISTERED_ROUTE = v01.REGISTERED_ROUTE

IMAGE_PROMPT = (
    "Look at the image. Answer in exactly this format and nothing else:\n"
    "red circles: N\nblue squares: M\ntopmost shape: COLOR\n"
    "where N and M are the counts of red circles and blue squares, and "
    "COLOR is the color (red or blue) of the shape closest to the top of "
    "the image.")


def load_verified_call_context() -> dict:
    """Rebuild the request history from CAPABILITY-01's SAVED evidence —
    no new tool-call request is made."""
    v1 = json.loads(Path(V01_VERIFICATION).read_text())
    p1 = v1["probes"]["probe1"]
    if p1.get("verdict") != "PASS" or not p1.get("function_call"):
        raise RuntimeError("CAPABILITY-01 probe1 evidence not usable")
    fc = p1["function_call"]
    if not fc.get("call_id") or not fc.get("arguments_raw"):
        raise RuntimeError("saved function_call lacks call_id/arguments")
    # the original user input is a pure function of the model (fixed text)
    original_input_text = v01.probe1_body(
        REGISTERED_ROUTE["request_model"])["input"][0]["content"][0]["text"]
    return {"call_id": fc["call_id"], "name": fc["name"],
            "arguments_raw": fc["arguments_raw"],
            "original_input_text": original_input_text,
            "source": str(V01_VERIFICATION.relative_to(ROOT))}


def receipt_body(model: str, context: dict, receipt: str) -> dict:
    """Full Responses history rebuild: original input + original function
    call item (matching call_id) + function_call_output + final question.
    The receipt appears ONLY inside the tool output, never in user text."""
    tool_output = {"echo": "ok", "receipt": receipt}
    return {
        "model": model,
        "input": [
            {"role": "user", "content": [
                {"type": "input_text", "text": context["original_input_text"]}]},
            {"type": "function_call", "call_id": context["call_id"],
             "name": context["name"], "arguments": context["arguments_raw"]},
            {"type": "function_call_output", "call_id": context["call_id"],
             "output": json.dumps(tool_output)},
            {"role": "user", "content": [
                {"type": "input_text",
                 "text": "Reply with the receipt value from the smoke_echo "
                         "tool result only."}]},
        ],
        "tools": [{
            "type": "function", "name": "smoke_echo",
            "description": "Echo a value back. No side effects.",
            "parameters": {"type": "object",
                           "properties": {"value": {"type": "string"}},
                           "required": ["value"]}}],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }


def new_receipt() -> str:
    return uuid.uuid4().hex  # 32 lowercase hex, test data not a credential


def verdict_receipt(send: dict, sse: dict, text: str, receipt: str,
                    archived_pre_send: bool) -> dict:
    """Exact comparison only: reply.strip() == receipt. Format/length
    similarity NEVER counts as a pass."""
    if not send.get("ok") or send.get("http_status") != 200:
        return {"verdict": "UNKNOWN",
                "reason": "transport_or_http_failure",
                "http_status": send.get("http_status"),
                "error_type": send.get("error_type"),
                "receipt_matches_exactly": None}
    if not sse.get("terminal_seen"):
        return {"verdict": "FAIL", "reason": "protocol_response_not_terminal",
                "receipt_matches_exactly": None}
    reply = (text or "").strip()
    matches = reply == receipt
    return {"verdict": "PASS" if (matches and archived_pre_send) else "FAIL",
            "reason": ("exact_match" if matches
                       else "reply_differs_from_expected_receipt"),
            "reply_value": reply[:200],
            "expected_receipt": receipt,
            "archived_pre_send": archived_pre_send,
            "receipt_matches_exactly": matches}


# --------------------------------------------------------------------------- #
# image generation (stdlib PNG, reused minimal encoder from 01)
# --------------------------------------------------------------------------- #

def generate_test_image() -> tuple[bytes, dict]:
    """Random red circles + blue squares with a CLEARLY separated topmost
    shape (>= 40px above the next shape). Ground truth stays local: never
    in the prompt, filename or PNG metadata (no text chunks are written)."""
    rng = uuid.uuid4
    n_circles = 1 + rng().int % 3          # 1..3
    n_squares = 1 + rng().int % 3          # 1..3
    width, height = 320, 240
    shapes = []
    for _ in range(n_circles):
        shapes.append({"shape": "circle", "color": "red",
                       "cx": 20 + rng().int % 240,
                       "cy": 20 + rng().int % 170, "r": 14 + rng().int % 10})
    for _ in range(n_squares):
        shapes.append({"shape": "square", "color": "blue",
                       "x": 20 + rng().int % 240, "y": 20 + rng().int % 170,
                       "w": 24 + rng().int % 12})
    # enforce a clearly separated topmost shape: move the topmost one up
    # and everything else down, guaranteeing >= 40px vertical separation
    shapes_sorted = sorted(
        shapes, key=lambda s: s.get("cy", s.get("y", 0)) + (s.get("r", 0)))
    topmost = shapes_sorted[0]
    if "cy" in topmost:
        topmost["cy"] = 24
        topmost["r"] = min(topmost["r"], 18)
    else:
        topmost["y"] = 24
        topmost["w"] = min(topmost["w"], 22)
    top_y = topmost.get("cy", topmost.get("y"))
    for s in shapes_sorted[1:]:
        if "cy" in s:
            s["cy"] = max(s["cy"], top_y + 60 + s["r"])
            s["cy"] = min(s["cy"], height - 20 - s["r"])
        else:
            s["y"] = max(s["y"], top_y + 60)
            s["y"] = min(s["y"], height - 20 - s["w"])
    pixels = [[(250, 250, 250)] * width for _ in range(height)]
    for shape in shapes:
        if shape["shape"] == "circle":
            cx, cy, r = shape["cx"], shape["cy"], shape["r"]
            for yy in range(max(0, cy - r), min(height, cy + r + 1)):
                for xx in range(max(0, cx - r), min(width, cx + r + 1)):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                        pixels[yy][xx] = (220, 20, 20)
        else:
            x, y, w = shape["x"], shape["y"], shape["w"]
            for yy in range(max(0, y), min(height, y + w + 1)):
                for xx in range(max(0, x), min(width, x + w + 1)):
                    pixels[yy][xx] = (20, 20, 220)
    png = v01._write_png(width, height, pixels)
    top_color = topmost["color"]
    ground_truth = {"red_circles": n_circles, "blue_squares": n_squares,
                    "topmost_color": top_color,
                    "topmost_shape": topmost["shape"],
                    "topmost_center": [topmost.get("cx", topmost.get("x")),
                                       topmost.get("cy", topmost.get("y"))],
                    "shapes": shapes, "image_size": [width, height],
                    "separation_note": "topmost shape kept >=40px above all others"}
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


def verdict_image(send: dict, sse: dict, text: str, ground_truth: dict) -> dict:
    """Fixed judgement rules (defined before any send)."""
    if not send.get("ok") or send.get("http_status") != 200:
        return {"verdict": "UNKNOWN", "reason": "transport_or_http_failure",
                "questions": {}, "counts_correct": None}
    if not sse.get("terminal_seen"):
        return {"verdict": "FAIL", "reason": "protocol_response_not_terminal",
                "questions": {}, "counts_correct": None}
    reply = (text or "").strip()
    circles = re.findall(r"red\s*circles?\s*[:=]?\s*(\d+)", reply, re.I)
    squares = re.findall(r"blue\s*squares?\s*[:=]?\s*(\d+)", reply, re.I)
    topmost = re.findall(r"topmost\s*shape\s*[:=]?\s*(red|blue)", reply, re.I)
    questions = {}
    if circles:
        got = int(circles[0])
        questions["red_circles"] = {
            "answered": got, "expected": ground_truth["red_circles"],
            "correct": got == ground_truth["red_circles"]}
    else:
        questions["red_circles"] = {"answered": None,
                                    "expected": ground_truth["red_circles"],
                                    "correct": None, "status": "unparseable"}
    if squares:
        got = int(squares[0])
        questions["blue_squares"] = {
            "answered": got, "expected": ground_truth["blue_squares"],
            "correct": got == ground_truth["blue_squares"]}
    else:
        questions["blue_squares"] = {"answered": None,
                                     "expected": ground_truth["blue_squares"],
                                     "correct": None, "status": "unparseable"}
    if topmost:
        got = topmost[0].lower()
        questions["topmost_color"] = {
            "answered": got, "expected": ground_truth["topmost_color"],
            "correct": got == ground_truth["topmost_color"]}
    else:
        questions["topmost_color"] = {"answered": None,
                                      "expected": ground_truth["topmost_color"],
                                      "correct": None, "status": "unparseable"}
    values = [q["correct"] for q in questions.values()]
    if any(v is False for v in values):
        verdict = "FAIL"   # a clearly parsed answer is wrong
    elif all(v is True for v in values):
        verdict = "PASS"
    else:
        verdict = "UNKNOWN"  # ambiguous / unparseable — never forced to PASS
    refuses = re.search(r"(?i)(cannot|can't|unable to)\s+(see|view|process|access)"
                        r".{0,30}(image|picture)|no image", reply)
    if refuses and verdict != "PASS":
        verdict = "FAIL"
        reason = "model_explicitly_states_it_cannot_see_the_image"
    else:
        reason = ("all_questions_correct" if verdict == "PASS"
                  else "wrong_parsed_answer" if verdict == "FAIL"
                  else "ambiguous_or_unparseable_answer")
    return {"verdict": verdict, "reason": reason,
            "reply_excerpt": reply[:400], "questions": questions}


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
    phase_start = time.monotonic()
    gate = v01.SendGate(MAX_SENDS)
    client_factory = v01.make_client_factory()

    verification = {
        "schema": "video-use-volcano-capability-02-v1",
        "task": "VIDEO-USE-VOLCANO-CAPABILITY-02",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "route": {"api_base": api_base, "request_model": model,
                  "credential_env": REGISTERED_ROUTE["credential_env"],
                  "responses_url": url,
                  "note": "same endpoint/model/protocol as CAPABILITY-01; "
                          "probe1 (Responses + tool call) already PASSED "
                          "and was NOT re-tested"},
        "limits": {"max_sends": MAX_SENDS,
                   "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
                   "request_wall_limit_s": REQUEST_WALL_LIMIT_S,
                   "phase_wall_limit_s": PHASE_WALL_LIMIT_S,
                   "retries": "disabled", "redirects": "not followed",
                   "previous_round_leftover_quota_used": False},
        "probes": {}, "outcomes": {}, "client_sends": None,
    }

    def persist() -> None:
        verification["client_sends"] = gate.snapshot()
        _write_json(PROBE_DIR / "verification.json", verification)

    def remaining_phase_ok() -> bool:
        return time.monotonic() - phase_start < PHASE_WALL_LIMIT_S

    def do_send(body: dict) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json",
                   "Accept": "text/event-stream"}
        api_key = os.environ.get(REGISTERED_ROUTE["credential_env"], "")
        if not api_key:
            raise SystemExit("credential env var empty — refusing to send "
                             "(no probe dispatched)")
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            record = v01.send_request(
                gate, client_factory(), "POST", url, headers=headers, body=body,
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
        return record, sse

    context = load_verified_call_context()
    verification["reused_context"] = context

    # ---- request 1: tool-result return re-verification ------------------ #
    if not remaining_phase_ok():
        verification["probes"]["receipt"] = {"verdict": "NOT_EXECUTED",
                                             "reason": "phase_budget_exhausted"}
        verification["probes"]["image"] = {"verdict": "NOT_EXECUTED",
                                            "reason": "phase_budget_exhausted"}
        return _finalize(verification, gate)
    receipt = new_receipt()
    # persist the expected receipt BEFORE sending (exact-comparison basis)
    _write_json(PROBE_DIR / "expected-receipt.json", {
        "task": "VIDEO-USE-VOLCANO-CAPABILITY-02",
        "call_id": context["call_id"],
        "expected_receipt": receipt,
        "note": "written before the request was dispatched; receipt is test "
                "data, not a credential"})
    archived = (PROBE_DIR / "expected-receipt.json").is_file()
    record, sse = do_send(receipt_body(model, context, receipt))
    text = v01.extract_final_text(sse.get("events", []))
    result = verdict_receipt(record, sse, text, receipt, archived)
    result.update({"status": "executed", "send": record,
                   "final_text_excerpt": v01.redact(text)[:400],
                   "request_context": {
                       "original_input_text": context["original_input_text"],
                       "function_call_call_id": context["call_id"],
                       "function_call_name": context["name"],
                       "function_call_arguments": context["arguments_raw"],
                       "receipt_delivery": "function_call_output only"}})
    verification["probes"]["receipt"] = result
    persist()
    if result["verdict"] != "PASS":
        verification["probes"]["image"] = {"verdict": "NOT_EXECUTED",
                                           "reason": "request_1_not_passed"}
        return _finalize(verification, gate)

    # ---- request 2: image understanding --------------------------------- #
    if not remaining_phase_ok():
        verification["probes"]["image"] = {"verdict": "NOT_EXECUTED",
                                           "reason": "phase_budget_exhausted"}
        return _finalize(verification, gate)
    png_bytes, ground_truth = generate_test_image()
    (PROBE_DIR / "probe2_image.png").write_bytes(png_bytes)
    _write_json(PROBE_DIR / "probe2_ground_truth.json", ground_truth)
    record, sse = do_send(image_body(model, png_bytes))
    text = v01.extract_final_text(sse.get("events", []))
    result = verdict_image(record, sse, text, ground_truth)
    result.update({
        "status": "executed", "send": record,
        "image": {"path": "probe2_image.png",
                  "sha256": hashlib.sha256(png_bytes).hexdigest(),
                  "bytes": len(png_bytes), "size_px": ground_truth["image_size"],
                  "metadata_note": "answer not in prompt, filename or PNG "
                                   "metadata (no text chunks)"},
        "judgement_rules_fixed_pre_send": {
            "format": IMAGE_PROMPT,
            "rules": "counts and topmost color parsed from the fixed reply "
                     "format; wrong parsed answer=FAIL; unparseable/ambiguous="
                     "UNKNOWN; explicit cannot-see statement=FAIL"}})
    verification["probes"]["image"] = result
    persist()
    return _finalize(verification, gate)


def _finalize(verification: dict, gate) -> int:
    receipt_probe = verification["probes"].get("receipt", {})
    image_probe = verification["probes"].get("image", {})
    verification["outcomes"] = {
        "tool_result_return": receipt_probe.get("verdict", "NOT_EXECUTED"),
        "image_understanding": image_probe.get("verdict", "NOT_EXECUTED"),
    }
    models, usage = set(), []
    for p in (receipt_probe, image_probe):
        for e in (p.get("send", {}).get("sse_events_redacted") or []):
            if e.get("event") == "response.completed":
                try:
                    resp = (json.loads(e["data"]) or {}).get("response", {})
                    if resp.get("model"):
                        models.add(resp["model"])
                    if resp.get("usage"):
                        usage.append(resp["usage"])
                except json.JSONDecodeError:
                    pass
    verification["request_model_sent"] = REGISTERED_ROUTE["request_model"]
    verification["response_models_observed"] = sorted(models) or ["unknown"]
    verification["usage_observed"] = usage or ["unknown"]
    verification["cost"] = "unknown; no independent billing evidence"
    verification["client_sends"] = gate.snapshot()
    verification["boundaries"] = (
        "Two bounded probes on the registered route only. Even PASS on both "
        "does NOT establish Codex CLI container compatibility, video-use "
        "full-flow readiness, or experiment READY.")
    _write_json(PROBE_DIR / "verification.json", verification)
    print(json.dumps({"outcomes": verification["outcomes"],
                      "sends": gate.snapshot()["sends_initiated"],
                      "report": str(PROBE_DIR / "verification.json")},
                     ensure_ascii=False))
    ok = all(v == "PASS" for v in verification["outcomes"].values())
    return 0 if ok else 7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--i-approve-video-use-volcano-capability-02",
                    action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_video_use_volcano_capability_02:
            print("refusing: --execute requires "
                  "--i-approve-video-use-volcano-capability-02")
            return 2
        if (PROBE_DIR / "verification.json").exists():
            print("refusing: existing results in target directory; never "
                  "overwrite prior probe evidence")
            return 3
        return execute()
    print("offline mode; unit tests cover context rebuild, bodies, "
          "pre-send archiving, verdicts and gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
