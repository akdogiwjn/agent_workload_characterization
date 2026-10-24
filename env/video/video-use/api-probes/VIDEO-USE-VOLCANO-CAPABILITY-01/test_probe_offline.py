"""VIDEO-USE-VOLCANO-CAPABILITY-01 offline tests.

All network interaction goes through httpx.MockTransport — no real socket
is opened; no real credential is read (a fake placeholder env value is set
only inside the guarded execute test and removed afterwards)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import video_use_volcano_capability_01 as v  # noqa: E402


class UrlTests(unittest.TestCase):
    def test_url_built_from_registered_base(self):
        self.assertEqual(
            v.build_responses_url(v.REGISTERED_ROUTE["api_base"]),
            "https://st8tp3ajl0df3n8b8l8qu.apigateway-cn-beijing.volceapi.com/v1/responses")

    def test_no_duplicate_v1_or_responses(self):
        self.assertEqual(v.build_responses_url("https://h/v1"), "https://h/v1/responses")
        self.assertEqual(v.build_responses_url("https://h/v1/"), "https://h/v1/responses")
        self.assertEqual(v.build_responses_url("https://h/v1/responses"),
                         "https://h/v1/responses")
        self.assertNotIn("/v1/v1", v.build_responses_url("https://h/v1"))
        self.assertNotIn("/responses/responses",
                         v.build_responses_url("https://h/v1/responses"))

    def test_registered_route_matches_plan_identities(self):
        for rel in v.REGISTERED_ROUTE["registration_sources"]:
            d = json.loads((ROOT / rel).read_text())
            text = json.dumps(d)
            self.assertIn("st8tp3ajl0df3n8b8l8qu", text)
            self.assertIn("VOLCANO_API_KEY", text)


class RedactTests(unittest.TestCase):
    def test_authorization_and_keys_redacted(self):
        self.assertNotIn("secret123", v.redact("Authorization: Bearer secret123"))
        self.assertIn("[REDACTED]", v.redact("Authorization: Bearer secret123"))
        self.assertNotIn("abc123def", v.redact("api_key = abc123def"))
        self.assertNotIn("sk-abcdefgh12345", v.redact("err sk-abcdefgh12345 failed"))

    def test_normal_sse_text_untouched(self):
        text = '{"type":"response.completed","response":{"model":"m"}}'
        self.assertEqual(v.redact(text), text)


class SendGateTests(unittest.TestCase):
    def test_fourth_attempt_blocked_before_dispatch(self):
        gate = v.SendGate(3)
        for _ in range(3):
            gate.before_send()
        with self.assertRaises(v.ProbeSendLimitExceeded):
            gate.before_send()
        snap = gate.snapshot()
        self.assertEqual(snap["sends_initiated"], 3)
        self.assertEqual(snap["attempts_blocked"], 1)

    def test_failed_connect_still_consumes_the_cap(self):
        # regression: error paths must not bypass the send limit
        gate = v.SendGate(1)
        gate.before_send()
        gate.after_error()
        with self.assertRaises(v.ProbeSendLimitExceeded):
            gate.before_send()
        snap = gate.snapshot()
        self.assertEqual(snap["sends_initiated"], 1)
        self.assertEqual(snap["send_errors"], 1)
        self.assertEqual(snap["attempts_blocked"], 1)

    def test_snapshot_after_error_records_known_sends(self):
        gate = v.SendGate(3)
        gate.before_send(); gate.after_response()
        snap = gate.snapshot()
        self.assertEqual(snap["sends_initiated"], 1)
        self.assertEqual(snap["responses_received"], 1)

    def test_send_basis_is_client_observation_only(self):
        self.assertIn("unknown", v.SendGate(1).snapshot()["basis"])


class ClientConfigTests(unittest.TestCase):
    def test_no_retries_no_redirects_no_trust_env(self):
        options = v.make_client_factory(verify_options=True).options
        self.assertEqual(options["retries"], 0)
        self.assertFalse(options["follow_redirects"])
        self.assertFalse(options["trust_env"])

    def test_redirect_not_followed_and_counted_once(self):
        import httpx
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://elsewhere.example/x"})

        gate = v.SendGate(3)
        client = httpx.Client(transport=httpx.MockTransport(handler),
                              follow_redirects=False)
        record = v.send_request(gate, client, "POST",
                                "https://gw.example/v1/responses",
                                headers={"Authorization": "Bearer x",
                                         "Content-Type": "application/json"},
                                body={"a": 1}, deadline_monotonic=float("inf"))
        self.assertEqual(record["http_status"], 302)
        self.assertEqual(gate.snapshot()["sends_initiated"], 1)
        self.assertEqual(len(calls), 1)  # credential NOT re-sent elsewhere

    def test_transport_error_recorded_redacted(self):
        import httpx

        def handler(request):
            raise httpx.ConnectError("boom sk-topsecret1234 refused")

        gate = v.SendGate(3)
        client = httpx.Client(transport=httpx.MockTransport(handler),
                              follow_redirects=False)
        record = v.send_request(gate, client, "POST", "https://gw.example/v1/responses",
                                headers={}, body={},
                                deadline_monotonic=float("inf"))
        self.assertFalse(record["ok"])
        self.assertEqual(record["error_type"], "ConnectError")
        self.assertNotIn("sk-topsecret1234", record["error_text_redacted"])
        self.assertEqual(gate.snapshot()["send_errors"], 1)


def sse_stream(call_id="call_1", value="ok", model="deepseek-v4-flash"):
    return [
        "event: response.output_item.added",
        'data: {"type":"response.output_item.added"}',
        "",
        "event: response.output_item.done",
        'data: {"type":"response.output_item.done","item":{"type":"function_call",'
        '"call_id":"%s","name":"smoke_echo","arguments":"{\\"value\\": \\"%s\\"}"}}' % (call_id, value),
        "",
        "event: response.completed",
        'data: {"type":"response.completed","response":{"id":"resp_1","model":"%s",'
        '"output":[{"type":"function_call","call_id":"%s","name":"smoke_echo",'
        '"arguments":"{\\"value\\": \\"%s\\"}"}],'
        '"usage":{"input_tokens":11,"output_tokens":7}}}' % (model, call_id, value),
        "",
        "data: [DONE]",
    ]


class ParseTests(unittest.TestCase):
    def test_full_sse_stream_parsed_with_completed(self):
        sse = v.parse_sse(sse_stream())
        self.assertTrue(sse["is_sse"])
        self.assertTrue(sse["completed"])
        self.assertTrue(sse["terminal_seen"])
        names = [e["event"] for e in sse["events"]]
        self.assertIn("response.completed", names)
        self.assertIn("[DONE]", names)

    def test_missing_completed_means_no_sse_pass(self):
        lines = ["event: response.output_item.added",
                 'data: {"type":"response.output_item.added"}']
        sse = v.parse_sse(lines)
        self.assertFalse(sse["completed"])
        self.assertFalse(sse["terminal_seen"])

    def test_function_call_extraction_from_completed_and_incremental(self):
        sse = v.parse_sse(sse_stream(call_id="call_9"))
        for events in (sse["events"],
                       [e for e in sse["events"]
                        if e["event"] == "response.output_item.done"]):
            call = v.extract_function_call(events)
            self.assertEqual(call["call_id"], "call_9")
            self.assertEqual(call["name"], "smoke_echo")
            self.assertEqual(v.parse_function_arguments(call["arguments_raw"]),
                             {"value": "ok"})

    def test_chat_completions_style_tool_calls_not_confused(self):
        # a Chat-Completions shaped payload must NOT be parsed as a
        # Responses function_call
        events = [{"event": "response.completed", "data": {"type": "x", "response": {
            "output": [{"type": "message",
                        "content": "", "tool_calls": [{"id": "t1"}]}]}}}]
        self.assertIsNone(v.extract_function_call(events))

    def test_non_sse_json_body_fallback(self):
        body = json.dumps({"id": "resp_2", "model": "deepseek-v4-flash",
                           "output": [{"type": "function_call", "call_id": "c1",
                                       "name": "smoke_echo",
                                       "arguments": "{\"value\": \"ok\"}"}],
                           "usage": {"input_tokens": 5, "output_tokens": 3}})
        sse = v.parse_sse(body.splitlines())
        self.assertFalse(sse["is_sse"])
        fallback = v.parse_non_sse_json(body.splitlines())
        self.assertTrue(fallback["completed"])
        self.assertFalse(fallback["is_sse"])
        call = v.extract_function_call(fallback["events"])
        self.assertEqual(call["call_id"], "c1")

    def test_final_text_from_completed_and_deltas(self):
        events = [{"event": "response.completed", "data": {"response": {
            "output": [{"type": "message", "text": "receipt is abc"}]}}}]
        self.assertIn("abc", v.extract_final_text(events))
        deltas = [{"event": "response.output_text.delta",
                   "data": {"delta": "abc"}}] * 2
        self.assertEqual(v.extract_final_text(deltas), "abcabc")

    def test_final_text_nested_content_shape(self):
        # regression: real gateway returned text nested in content[].text
        events = [{"event": "response.completed", "data": {"response": {
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text",
                                     "text": "cc9506a1"}]}]}}}]
        self.assertEqual(v.extract_final_text(events), "cc9506a1")
        done = [{"event": "response.output_item.done", "data": {
            "item": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "cc9506a1"}]}}}]
        self.assertEqual(v.extract_final_text(done), "cc9506a1")


class BodyTests(unittest.TestCase):
    def test_probe1_body_shape(self):
        body = v.probe1_body("deepseek-v4-flash")
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["tools"][0]["name"], "smoke_echo")
        self.assertEqual(body["tool_choice"], {"type": "function", "name": "smoke_echo"})
        self.assertTrue(body["stream"])
        self.assertLessEqual(body["max_output_tokens"], 2048)
        # no vendor-private parameters beyond the standard set
        self.assertEqual(set(body), {"model", "input", "tools", "tool_choice",
                                     "max_output_tokens", "stream"})
        schema = body["tools"][0]["parameters"]
        self.assertEqual(set(schema["properties"]), {"value"})

    def test_probe2_body_roundtrip_context(self):
        out = v.smoke_echo("ok")
        body = v.probe2_body("deepseek-v4-flash", "call_7", '{"value": "ok"}', out)
        kinds = [item.get("type") for item in body["input"]]
        self.assertIn("function_call", kinds)
        self.assertIn("function_call_output", kinds)
        fc = next(i for i in body["input"] if i.get("type") == "function_call")
        fco = next(i for i in body["input"] if i.get("type") == "function_call_output")
        self.assertEqual(fc["call_id"], "call_7")
        self.assertEqual(fco["call_id"], "call_7")  # must match
        self.assertIn("receipt", fco["output"])
        # the original user turn is retained as context
        self.assertEqual(body["input"][0]["role"], "user")

    def test_probe3_body_image_inlined_no_answer_leak(self):
        png, gt = v.generate_test_image()
        body = v.probe3_body("deepseek-v4-flash", png)
        content = body["input"][0]["content"]
        image_item = next(c for c in content if c["type"] == "input_image")
        self.assertTrue(image_item["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("http", image_item["image_url"])  # no external URL
        text_item = next(c for c in content if c["type"] == "input_text")
        # the counts must NOT be in the prompt
        self.assertNotIn(str(gt["red_circles"]), text_item["text"])
        self.assertNotIn(str(gt["blue_squares"]), text_item["text"])


class ImageTests(unittest.TestCase):
    def test_image_png_valid_no_metadata_no_answer_in_name(self):
        import struct
        png, gt = v.generate_test_image()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        # walk chunks: IHDR dims match, no textual chunks at all
        pos, chunks = 8, []
        while pos < len(png):
            length = struct.unpack(">I", png[pos:pos + 4])[0]
            tag = png[pos + 4:pos + 8]
            chunks.append(tag)
            pos += 12 + length
        self.assertEqual(chunks[0], b"IHDR")
        self.assertEqual(chunks[-1], b"IEND")
        self.assertNotIn(b"tEXt", chunks)
        self.assertNotIn(b"iTXt", chunks)
        self.assertNotIn(b"zTXt", chunks)
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual([width, height], gt["image_size"])

    def test_verify_probe3_counts(self):
        gt = {"red_circles": 3, "blue_squares": 2}
        ok = v.verify_probe3("red circles: 3, blue squares: 2", gt)
        self.assertTrue(ok["counts_correct"])
        wrong = v.verify_probe3("red circles: 2, blue squares: 2", gt)
        self.assertFalse(wrong["counts_correct"])
        self.assertEqual(wrong["answered_red_circles"], 2)
        none = v.verify_probe3("I cannot see any image.", gt)
        self.assertFalse(none["counts_correct"])
        self.assertIsNone(none["answered_red_circles"])


class ExecuteOfflineTests(unittest.TestCase):
    """Run execute() against a failing MockTransport with a FAKE credential;
    asserts the stop-on-failure and exception-persist contracts."""

    def test_probe1_failure_persists_and_stops(self):
        import httpx

        def handler(request):
            raise httpx.ConnectError("connection refused")

        def factory():
            return httpx.Client(transport=httpx.MockTransport(handler),
                                follow_redirects=False)

        old_key = os.environ.pop("VOLCANO_API_KEY", None)
        os.environ["VOLCANO_API_KEY"] = "fake-offline-not-a-real-key"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(v, "PROBE_DIR", Path(tmp)), \
                     patch.object(v, "make_client_factory",
                                  lambda *a, **k: (lambda: factory())):
                    rc = v.execute()
                verification = json.loads((Path(tmp) / "verification.json").read_text())
        finally:
            os.environ.pop("VOLCANO_API_KEY", None)
            if old_key is not None:
                os.environ["VOLCANO_API_KEY"] = old_key
        self.assertEqual(rc, 7)
        self.assertEqual(verification["probes"]["probe1"]["send"]["error_type"],
                         "ConnectError")
        self.assertEqual(verification["probes"]["probe2"]["status"], "not_executed")
        self.assertEqual(verification["probes"]["probe3"]["status"], "not_executed")
        self.assertEqual(verification["outcomes"]["tool_call"], "FAIL")
        self.assertEqual(verification["outcomes"]["tool_result_return"], "NOT_EXECUTED")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        self.assertEqual(verification["client_sends"]["send_errors"], 1)

    def test_missing_credential_refuses_without_sending(self):
        old_key = os.environ.pop("VOLCANO_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(v, "PROBE_DIR", Path(tmp)):
                    with self.assertRaises(SystemExit):
                        v.execute()
                self.assertFalse((Path(tmp) / "verification.json").exists())
        finally:
            if old_key is not None:
                os.environ["VOLCANO_API_KEY"] = old_key

    def test_execute_refuses_to_overwrite_existing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "verification.json").write_text("{}")
            with patch.object(v, "PROBE_DIR", Path(tmp)):
                self.assertEqual(v.main(["--execute",
                                         "--i-approve-video-use-volcano-capability-01"]), 3)


if __name__ == "__main__":
    unittest.main()
