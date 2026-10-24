#!/usr/bin/env python3
"""VIDEO-USE-VOLCANO-CAPABILITY-01: three bounded protocol/vision probes.

Verifies whether the REGISTERED Volcano gateway route (api_base +
deepseek-v4-flash + VOLCANO_API_KEY, read from existing plan-identity
registrations) supports:
  1. Responses API with a forced no-side-effect function tool call;
  2. function_call_output round-trip (receipt echo);
  3. real image understanding via input_image.

Scope guards (hard):
  - at most 3 real HTTP sends TOTAL, counted at the send boundary BEFORE
    dispatch; the gate raises on the 4th attempt;
  - no SDK, no retries (httpx HTTPTransport(retries=0)), redirects NOT
    followed (follow_redirects=False) so credentials can never be
    re-sent elsewhere;
  - the credential value is read from VOLCANO_API_KEY only right before a
    send, never stored, logged, hashed or fingerprinted;
  - authorization headers and key-shaped strings are redacted from any
    retained text;
  - per-request wall limit 90s, whole network phase 300s;
  - max_output_tokens <= 2048; no vendor-private parameters;
  - failure at any step STOPS the sequence; later probes are recorded
    not_executed. No parameter changes, no Chat Completions fallback.

Offline mode (default) runs nothing network-shaped; unit tests cover the
gate, URL building, SSE parsing, redaction, bodies and verification with
mock transports only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = ROOT / "env/video/video-use/api-probes/VIDEO-USE-VOLCANO-CAPABILITY-01"
MAX_SENDS = 3
MAX_OUTPUT_TOKENS = 1024
REQUEST_WALL_LIMIT_S = 90.0
PHASE_WALL_LIMIT_S = 300.0
CONNECT_TIMEOUT_S = 15.0
READ_TIMEOUT_S = 30.0

REGISTERED_ROUTE = {
    "api_base": "https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1",
    "request_model": "deepseek-v4-flash",
    "request_model_registered_alias": "openai/deepseek-v4-flash",
    "credential_env": "VOLCANO_API_KEY",
    "registration_sources": [
        "env/docops-measurement-volcano-02/plan-identity.json",
        "env/toolsandbox-measurement-volcano-01/plan-identity.json",
    ],
}

TERMINAL_SSE_EVENTS = ("response.completed", "response.failed",
                       "response.incomplete", "error")


class ProbeSendLimitExceeded(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# pure helpers (offline-testable)
# --------------------------------------------------------------------------- #

def build_responses_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/responses"):
        return base
    return base + "/responses"


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


class SendGate:
    """Counts at the actual HTTP send boundary; the cap is enforced on
    ATTEMPTS (a failed connect still consumed an attempt — otherwise error
    paths could bypass the limit). Client-side send observation only —
    gateway-internal or upstream retries are unknown and never claimed."""

    def __init__(self, max_sends: int = MAX_SENDS):
        self.max_sends = max_sends
        self.attempted = 0
        self.responses = 0
        self.errors = 0
        self.blocked = 0

    def before_send(self) -> None:
        if self.attempted >= self.max_sends:
            self.blocked += 1
            raise ProbeSendLimitExceeded(
                f"probe send cap reached ({self.max_sends}); attempt rejected")
        self.attempted += 1

    def after_response(self) -> None:
        self.responses += 1

    def after_error(self) -> None:
        self.errors += 1

    def snapshot(self) -> dict:
        return {"boundary": "client_http_send_function_entry",
                "basis": "client-side send observation; gateway/upstream "
                         "internal retries unknown",
                "sends_initiated": self.attempted,
                "responses_received": self.responses,
                "send_errors": self.errors, "attempts_blocked": self.blocked,
                "cap": self.max_sends}


def make_client_factory(verify_options: bool = True):
    """Build the httpx client. No retries, redirects never followed."""
    import httpx

    def factory():
        return httpx.Client(
            transport=httpx.HTTPTransport(retries=0),
            follow_redirects=False,
            timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
            trust_env=False,
        )
    if verify_options:  # offline assertion hook for tests
        factory.options = {"retries": 0, "follow_redirects": False,
                           "trust_env": False}
    return factory


def send_request(gate: SendGate, client, method: str, url: str, *,
                 headers: dict, body: dict, deadline_monotonic: float) -> dict:
    """One bounded send. The gate is checked BEFORE dispatch; every exit
    path records the known send count via the returned record (callers
    persist it even on exceptions)."""
    gate.before_send()  # raises on cap BEFORE any network action
    record = {"url": url, "method": method,
              "request_body_sha256": hashlib.sha256(
                  json.dumps(body, sort_keys=True).encode()).hexdigest(),
              "request_headers_logged": {k: v for k, v in headers.items()
                                         if k.lower() in ("content-type", "accept")},
              "t_start_monotonic": time.monotonic()}
    try:
        with client.stream(method, url, headers=headers,
                           json=body) as response:
            record["http_status"] = response.status_code
            record["content_type"] = response.headers.get("content-type", "")
            chunks: list[str] = []
            for line in response.iter_lines():
                if time.monotonic() > deadline_monotonic:
                    record["request_wall_exceeded"] = True
                    break
                chunks.append(line)
            gate.after_response()
        record["raw_lines"] = chunks
        record["t_end_monotonic"] = time.monotonic()
        record["ok"] = True
        return record
    except Exception as exc:  # noqa: BLE001 — always recorded, redacted
        gate.after_error()
        record["ok"] = False
        record["error_type"] = type(exc).__name__
        record["error_text_redacted"] = redact(str(exc))[:800]
        record["t_end_monotonic"] = time.monotonic()
        return record


def parse_sse(raw_lines: list[str]) -> dict:
    """Parse an SSE stream (or a plain JSON body) into events + verdicts."""
    events: list[dict] = []
    current_event = None
    for line in raw_lines:
        line = line.strip()
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            events.append({"event": "[DONE]", "data": None})
            current_event = None
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            events.append({"event": current_event or "unparseable_data",
                           "data": payload[:200]})
            current_event = None
            continue
        name = current_event
        if not name and isinstance(data, dict):
            name = data.get("type")
        events.append({"event": name or "message", "data": data})
        current_event = None
    completed = any(e["event"] == "response.completed" for e in events)
    failed = any(e["event"] in ("response.failed", "error") for e in events)
    incomplete = any(e["event"] == "response.incomplete" for e in events)
    return {"events": events, "is_sse": bool(events),
            "completed": completed, "failed": failed, "incomplete": incomplete,
            "terminal_seen": completed or failed or incomplete}


def parse_non_sse_json(raw_lines: list[str]) -> dict | None:
    """Some gateways ignore stream:true and return one JSON body. That is a
    COMPLETE response object (not SSE) — parsed here so endpoint/tool
    dimensions can still be judged while SSE integrity stays a separate
    FAIL/UNKNOWN outcome."""
    joined = "\n".join(raw_lines or [])
    try:
        obj = json.loads(joined)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not ("output" in obj or "error" in obj):
        return None
    if "output" in obj:
        return {"events": [{"event": "response.completed",
                            "data": {"type": "response.completed",
                                     "response": obj}}],
                "is_sse": False, "completed": True, "failed": False,
                "incomplete": False, "terminal_seen": True,
                "non_sse_json_body": True}
    return {"events": [{"event": "error", "data": {"type": "error",
                                                   "error": obj}}],
            "is_sse": False, "completed": False, "failed": True,
            "incomplete": False, "terminal_seen": True,
            "non_sse_json_body": True}


def final_response(events: list[dict]) -> dict | None:
    for e in events:
        if e.get("event") == "response.completed":
            return e["data"].get("response") or {}
    return None


def extract_function_call(events: list[dict]) -> dict | None:
    """Responses-API function_call extraction (NOT Chat Completions
    tool_calls). Checks both the completed snapshot and incremental
    output_item.done events."""
    candidates = []
    resp = final_response(events)
    if isinstance(resp, dict):
        candidates.extend(resp.get("output") or [])
    for e in events:
        if e.get("event") == "response.output_item.done":
            item = (e.get("data") or {}).get("item") or {}
            if item.get("type") == "function_call":
                candidates.append(item)
    for item in candidates:
        if item.get("type") == "function_call":
            return {"call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments_raw": item.get("arguments")}
    return None


def extract_final_text(events: list[dict]) -> str:
    """Extract the assistant's final text from Responses events.

    Handles both shapes seen in the wild: text nested in
    output[].content[].text (OpenAI Responses spec) and flat item.text;
    incremental output_item.done / output_text.delta as fallbacks."""
    def _item_text(item) -> list[str]:
        if not isinstance(item, dict) or item.get("type") != "message":
            return []
        parts = []
        if item.get("text"):
            parts.append(item["text"])
        for c in item.get("content") or []:
            if isinstance(c, dict) and c.get("text"):
                parts.append(c["text"])
        return parts

    resp = final_response(events)
    if isinstance(resp, dict):
        parts = [t for item in (resp.get("output") or []) for t in _item_text(item)]
        if parts:
            return "\n".join(parts)
    for e in reversed(events):
        if e.get("event") == "response.output_item.done":
            parts = _item_text((e.get("data") or {}).get("item"))
            if parts:
                return "\n".join(parts)
    deltas = [(e.get("data") or {}).get("delta", "") for e in events
              if e.get("event") == "response.output_text.delta"]
    return "".join(deltas)


def parse_function_arguments(raw) -> dict | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def probe1_body(model: str) -> dict:
    return {
        "model": model,
        "input": [{"role": "user", "content": [
            {"type": "input_text",
             "text": "Call the smoke_echo tool with value \"ok\"."}]}],
        "tools": [{
            "type": "function", "name": "smoke_echo",
            "description": "Echo a value back. No side effects.",
            "parameters": {"type": "object",
                           "properties": {"value": {"type": "string"}},
                           "required": ["value"]}}],
        "tool_choice": {"type": "function", "name": "smoke_echo"},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }


def smoke_echo(value: str) -> dict:
    """The ONLY tool executed. Locally predefined; model-generated code or
    shell is never executed. A fresh receipt is generated per call."""
    return {"echo": value, "receipt": uuid.uuid4().hex}


def probe2_body(model: str, call_id: str, arguments_raw: str,
                tool_output: dict) -> dict:
    return {
        "model": model,
        "input": [
            {"role": "user", "content": [
                {"type": "input_text",
                 "text": "Call the smoke_echo tool with value \"ok\"."}]},
            {"type": "function_call", "call_id": call_id,
             "name": "smoke_echo", "arguments": arguments_raw},
            {"type": "function_call_output", "call_id": call_id,
             "output": json.dumps(tool_output)},
            {"role": "user", "content": [
                {"type": "input_text",
                 "text": "What receipt did the smoke_echo tool return? "
                         "Reply with the receipt value only."}]},
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


def _write_png(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    """Minimal stdlib PNG encoder (RGB, 8-bit). No third-party deps."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in pixels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def generate_test_image() -> tuple[bytes, dict]:
    """Random red circles + blue squares on light background; pure stdlib.
    Ground truth kept LOCAL only — never embedded in the prompt, filename
    or PNG metadata (no textual chunks are written at all)."""
    n_circles = 2 + uuid.uuid4().int % 3          # 2..4
    n_squares = 1 + uuid.uuid4().int % 3          # 1..3
    width, height = 320, 240
    background = (250, 250, 250)
    pixels = [[background] * width for _ in range(height)]
    shapes = []
    for _ in range(n_circles):
        cx, cy = 30 + uuid.uuid4().int % 240, 30 + uuid.uuid4().int % 160
        r = 12 + uuid.uuid4().int % 14
        shapes.append({"shape": "circle", "color": "red", "cx": cx, "cy": cy, "r": r})
    for _ in range(n_squares):
        x, y = 30 + uuid.uuid4().int % 240, 30 + uuid.uuid4().int % 160
        w = 20 + uuid.uuid4().int % 18
        shapes.append({"shape": "square", "color": "blue", "x": x, "y": y, "w": w})
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
    png = _write_png(width, height, pixels)
    ground_truth = {"red_circles": n_circles, "blue_squares": n_squares,
                    "shapes": shapes, "image_size": [width, height]}
    return png, ground_truth


def probe3_body(model: str, png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "model": model,
        "input": [{"role": "user", "content": [
            {"type": "input_text",
             "text": "Look at the image. How many red circles and how many "
                     "blue squares are in it? Answer exactly in the form: "
                     "red circles: N, blue squares: M"},
            {"type": "input_image",
             "image_url": f"data:image/png;base64,{b64}"}]}],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }


def verify_probe3(text: str, ground_truth: dict) -> dict:
    circles = re.findall(r"red\s*circles?\s*[:=]?\s*(\d+)", text, re.I)
    squares = re.findall(r"blue\s*squares?\s*[:=]?\s*(\d+)", text, re.I)
    got_c = int(circles[0]) if circles else None
    got_s = int(squares[0]) if squares else None
    ok = (got_c == ground_truth["red_circles"]
          and got_s == ground_truth["blue_squares"])
    return {"answered_red_circles": got_c, "answered_blue_squares": got_s,
            "expected_red_circles": ground_truth["red_circles"],
            "expected_blue_squares": ground_truth["blue_squares"],
            "counts_correct": ok,
            "note": "HTTP 200 or a claim of image support never counts; the "
                    "actual counts must match the local ground truth"}


def verdict_probe1(send: dict, sse: dict, call: dict | None) -> dict:
    responses_api = (send.get("http_status") == 200 and sse.get("terminal_seen"))
    tool_call_ok = bool(
        call and call.get("call_id") and call.get("name") == "smoke_echo"
        and isinstance(parse_function_arguments(call.get("arguments_raw")),
                       dict))
    args = parse_function_arguments(
        call.get("arguments_raw")) if call else None
    value_ok = bool(args and args.get("value") == "ok")
    return {
        "responses_api_endpoint_ok": responses_api,
        "sse_is_sse": sse.get("is_sse"),
        "sse_terminal_event_seen": sse.get("terminal_seen"),
        "sse_completed": sse.get("completed"),
        "sse_non_sse_json_fallback": bool(sse.get("non_sse_json_body")),
        "function_call": call,
        "function_call_arguments_parsed": args,
        "function_call_value_ok": value_ok,
        # SSE integrity is a SEPARATE outcome; the tool-call verdict requires
        # a terminal response + verified function_call, never HTTP 200 alone
        "verdict": "PASS" if (responses_api and tool_call_ok and value_ok)
                   else "FAIL",
    }


def verdict_probe2(send: dict, sse: dict, text: str, receipt: str) -> dict:
    ok = (send.get("http_status") == 200 and sse.get("terminal_seen")
          and receipt and receipt in (text or ""))
    return {"http_status": send.get("http_status"),
            "sse_completed": sse.get("completed"),
            "final_text_excerpt": redact(text)[:400],
            "receipt_echoed": bool(receipt and receipt in (text or "")),
            "verdict": "PASS" if ok else "FAIL"}


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def execute() -> int:
    api_base = REGISTERED_ROUTE["api_base"]
    model = REGISTERED_ROUTE["request_model"]
    url = build_responses_url(api_base)
    phase_start = time.monotonic()
    gate = SendGate(MAX_SENDS)
    client_factory = make_client_factory()

    verification = {
        "schema": "video-use-volcano-capability-01-v1",
        "task": "VIDEO-USE-VOLCANO-CAPABILITY-01",
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "route": {"api_base": api_base, "request_model": model,
                  "request_model_registered_alias":
                      REGISTERED_ROUTE["request_model_registered_alias"],
                  "credential_env": REGISTERED_ROUTE["credential_env"],
                  "responses_url": url,
                  "registration_sources":
                      REGISTERED_ROUTE["registration_sources"],
                  "note": "model field uses the registered raw-client name "
                          "deepseek-v4-flash; the openai/ alias is the "
                          "SDK-side prefix in the registrations"},
        "limits": {"max_sends": MAX_SENDS,
                   "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
                   "request_wall_limit_s": REQUEST_WALL_LIMIT_S,
                   "phase_wall_limit_s": PHASE_WALL_LIMIT_S,
                   "retries": "disabled (httpx HTTPTransport retries=0)",
                   "redirects": "not followed (follow_redirects=False)",
                   "vendor_private_parameters": "none"},
        "probes": {}, "outcomes": {}, "client_sends": None,
    }

    def persist() -> None:
        verification["client_sends"] = gate.snapshot()
        _write_json(PROBE_DIR / "verification.json", verification)

    def remaining_phase_ok() -> bool:
        return time.monotonic() - phase_start < PHASE_WALL_LIMIT_S

    def do_send(body: dict) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        api_key = os.environ.get(REGISTERED_ROUTE["credential_env"], "")
        if not api_key:
            raise SystemExit("credential env var empty — refusing to send "
                             "(no probe dispatched)")
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            record = send_request(gate, client_factory(), "POST", url,
                                  headers=headers, body=body,
                                  deadline_monotonic=time.monotonic()
                                  + REQUEST_WALL_LIMIT_S)
        finally:
            # credential value leaves scope here; nothing retained it
            headers.pop("Authorization", None)
        sse = parse_sse(record.get("raw_lines") or [])
        if not sse.get("is_sse"):
            fallback = parse_non_sse_json(record.get("raw_lines") or [])
            if fallback is not None:
                sse = fallback
        record.pop("raw_lines", None)
        record["sse"] = {k: v for k, v in sse.items() if k != "events"}
        record["sse_events_redacted"] = [
            {"event": e.get("event"),
             "data": redact(json.dumps(e.get("data"), ensure_ascii=False))[:4000]}
            for e in sse.get("events", [])]
        return record, sse

    # ---- probe 1 -------------------------------------------------------- #
    if not remaining_phase_ok():
        verification["probes"]["probe1"] = {"status": "not_executed_phase_budget"}
    else:
        record, sse = do_send(probe1_body(model))
        call = extract_function_call(sse.get("events", []))
        result = verdict_probe1(record, sse, call)
        result["send"] = record
        result["status"] = "executed"
        verification["probes"]["probe1"] = result
        persist()
        if result["verdict"] != "PASS":
            verification["probes"]["probe2"] = {"status": "not_executed"}
            verification["probes"]["probe3"] = {"status": "not_executed"}
            return _finalize(verification, gate)

    # ---- probe 2 -------------------------------------------------------- #
    if "probe2" not in verification["probes"] and remaining_phase_ok():
        p1 = verification["probes"]["probe1"]
        call = p1["function_call"]
        tool_output = smoke_echo("ok")   # fresh receipt generated NOW
        receipt = tool_output["receipt"]
        record, sse = do_send(probe2_body(model, call["call_id"],
                                          call["arguments_raw"], tool_output))
        text = extract_final_text(sse.get("events", []))
        result = verdict_probe2(record, sse, text, receipt)
        result["send"] = record
        result["receipt_local_generated"] = True
        # archive the one-time receipt value (not a credential) so later
        # offline re-judgement can byte-compare without any re-send
        result["receipt_value_local"] = receipt
        result["status"] = "executed"
        verification["probes"]["probe2"] = result
        persist()
        if result["verdict"] != "PASS":
            verification["probes"]["probe3"] = {"status": "not_executed"}
            return _finalize(verification, gate)

    # ---- probe 3 -------------------------------------------------------- #
    if "probe3" not in verification["probes"] and remaining_phase_ok():
        png_bytes, ground_truth = generate_test_image()
        image_path = PROBE_DIR / "probe3_image.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(png_bytes)
        _write_json(PROBE_DIR / "probe3_ground_truth.json", ground_truth)
        record, sse = do_send(probe3_body(model, png_bytes))
        text = extract_final_text(sse.get("events", []))
        check = verify_probe3(text, ground_truth)
        verification["probes"]["probe3"] = {
            "status": "executed",
            "send": record,
            "image": {"path": str(image_path.relative_to(ROOT)),
                      "sha256": hashlib.sha256(png_bytes).hexdigest(),
                      "bytes": len(png_bytes),
                      "size_px": ground_truth["image_size"],
                      "metadata_note": "answer/counts not in prompt, filename "
                                       "or PNG metadata"},
            "final_text_excerpt": redact(text)[:400],
            "check": check,
            "verdict": "PASS" if check["counts_correct"]
                       and record.get("http_status") == 200
                       and sse.get("terminal_seen") else "FAIL",
        }
        persist()

    return _finalize(verification, gate)


def rejudge_probe2_from_saved(verification_path: Path) -> dict:
    """Offline re-judgement of probe 2 from the SAVED SSE evidence — never
    re-sends anything. Used when a client-side parser defect mis-extracted
    the final text at execution time."""
    verification = json.loads(Path(verification_path).read_text())
    p2 = verification["probes"]["probe2"]
    events = []
    for e in p2["send"]["sse_events_redacted"]:
        data = None
        if isinstance(e.get("data"), str):
            try:
                data = json.loads(e["data"])
            except json.JSONDecodeError:
                data = e["data"][:200]
        events.append({"event": e.get("event"), "data": data})
    text = extract_final_text(events)
    receipt = p2.get("receipt_value_local")
    analysis = {
        "rejudged_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "basis": "saved SSE events only; zero additional network sends",
        "final_text_extracted_after_parser_fix": text[:400],
        "parser_fix": "extract_final_text now reads text nested in "
                      "output[].content[].text (real gateway shape)",
        "receipt_archived": bool(receipt),
        "receipt_matches": (bool(receipt and text and receipt in text)
                            if receipt else None),
    }
    if not receipt:
        analysis["note"] = (
            "receipt value was not archived at execution time (probe "
            "defect); the model returned a 32-hex token matching the "
            "receipt format, but byte-level comparison is impossible from "
            "saved evidence. Original conservative verdict is kept; "
            "confirming requires a separately authorized re-run.")
    p2["rejudgement_after_parser_fix"] = analysis
    verification["client_sends"]["rejudgement_extra_sends"] = 0
    _write_json(Path(verification_path), verification)
    return analysis


def _finalize(verification: dict, gate: SendGate) -> int:
    probes = verification["probes"]
    p1, p2, p3 = (probes.get("probe1", {}), probes.get("probe2", {}),
                  probes.get("probe3", {}))
    executed = lambda p: p.get("status") == "executed"  # noqa: E731
    verification["outcomes"] = {
        "responses_api": ("PASS" if executed(p1) and p1.get("responses_api_endpoint_ok")
                          else "FAIL" if executed(p1) else "UNKNOWN"),
        "sse_integrity": ("PASS" if executed(p1) and p1.get("sse_completed")
                          and p1.get("sse_is_sse")
                          else "FAIL" if executed(p1) else "UNKNOWN"),
        "tool_call": p1.get("verdict") if executed(p1) else "NOT_EXECUTED",
        "tool_result_return": p2.get("verdict") if executed(p2) else "NOT_EXECUTED",
        "image_understanding": p3.get("verdict") if executed(p3) else "NOT_EXECUTED",
    }
    models_observed = set()
    usage = []
    for p in (p1, p2, p3):
        for e in (p.get("send", {}).get("sse_events_redacted") or []):
            if e.get("event") == "response.completed":
                try:
                    data = json.loads(e["data"])
                    resp = data.get("response", {})
                    if resp.get("model"):
                        models_observed.add(resp.get("model"))
                    if resp.get("usage"):
                        usage.append(resp["usage"])
                except json.JSONDecodeError:
                    pass
    verification["request_model_sent"] = REGISTERED_ROUTE["request_model"]
    verification["response_models_observed"] = sorted(models_observed) or ["unknown"]
    verification["usage_observed"] = usage or ["unknown"]
    verification["cost"] = "unknown; no independent billing evidence"
    verification["boundaries"] = (
        "Three bounded protocol/vision probes on the registered route only. "
        "PASS on all does NOT establish Codex CLI container compatibility, "
        "video-use full-flow readiness, or experiment READY.")
    verification["client_sends"] = gate.snapshot()
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
    ap.add_argument("--i-approve-video-use-volcano-capability-01",
                    action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_video_use_volcano_capability_01:
            print("refusing: --execute requires "
                  "--i-approve-video-use-volcano-capability-01")
            return 2
        if (PROBE_DIR / "verification.json").exists():
            print("refusing: existing results in target directory; "
                  "never overwrite prior probe evidence")
            return 3
        return execute()
    print("offline mode; unit tests cover gate/URL/SSE/redaction/bodies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
