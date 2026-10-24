"""VIDEO-USE-VOLCANO-CAPABILITY-02 offline tests.

All network interaction goes through httpx.MockTransport — no real socket,
no real credential (a fake placeholder env value is set only inside the
guarded execute tests and removed afterwards)."""
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

import video_use_volcano_capability_01 as v01  # noqa: E402
import video_use_volcano_capability_02 as v02  # noqa: E402


class ContextRebuildTests(unittest.TestCase):
    def test_saved_context_is_sufficient(self):
        context = v02.load_verified_call_context()
        self.assertTrue(context["call_id"].startswith("call_"))
        self.assertEqual(context["name"], "smoke_echo")
        self.assertIn("value", context["arguments_raw"])
        self.assertIn("smoke_echo", context["original_input_text"])

    def test_receipt_body_rebuilds_full_history(self):
        context = v02.load_verified_call_context()
        receipt = "a" * 32
        body = v02.receipt_body("deepseek-v4-flash", context, receipt)
        kinds = [i.get("type") for i in body["input"]]
        self.assertIn("function_call", kinds)
        self.assertIn("function_call_output", kinds)
        fc = next(i for i in body["input"] if i.get("type") == "function_call")
        fco = next(i for i in body["input"]
                   if i.get("type") == "function_call_output")
        # function_call_output is associated with the ORIGINAL call_id
        self.assertEqual(fc["call_id"], context["call_id"])
        self.assertEqual(fco["call_id"], context["call_id"])
        # the original user input is retained as context (not isolated)
        self.assertEqual(body["input"][0]["role"], "user")
        # receipt travels ONLY through the tool output, never user text
        texts = [c["text"] for i in body["input"] if i.get("role") == "user"
                 for c in i["content"] if c.get("type") == "input_text"]
        self.assertNotIn(receipt, " ".join(texts))
        self.assertIn(receipt, fco["output"])
        self.assertTrue(body["stream"])
        self.assertLessEqual(body["max_output_tokens"], 2048)


class TextExtractionTests(unittest.TestCase):
    def test_nested_content_text_extracted(self):
        events = [{"event": "response.completed", "data": {"response": {
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text",
                                     "text": "deadbeef"}]}]}}}]
        self.assertEqual(v01.extract_final_text(events), "deadbeef")

    def test_incremental_and_final_not_double_concatenated(self):
        # deltas say "AB" twice, completed says "AB" once -> exactly "AB"
        events = [
            {"event": "response.output_text.delta", "data": {"delta": "A"}},
            {"event": "response.output_text.delta", "data": {"delta": "B"}},
            {"event": "response.completed", "data": {"response": {
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text",
                                         "text": "AB"}]}]}}}]
        self.assertEqual(v01.extract_final_text(events), "AB")

    def test_deltas_used_only_when_no_final(self):
        events = [{"event": "response.output_text.delta",
                   "data": {"delta": "AB"}}]
        self.assertEqual(v01.extract_final_text(events), "AB")


class ReceiptVerdictTests(unittest.TestCase):
    def _send(self, **kw):
        base = {"ok": True, "http_status": 200}
        base.update(kw)
        return base

    def _sse(self, **kw):
        base = {"terminal_seen": True, "completed": True}
        base.update(kw)
        return base

    def test_exact_match_passes(self):
        r = v02.verdict_receipt(self._send(), self._sse(), "  deadbeef  \n",
                                "deadbeef", archived_pre_send=True)
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["receipt_matches_exactly"])

    def test_mismatch_is_fail_not_pass(self):
        r = v02.verdict_receipt(self._send(), self._sse(), "deadbeef",
                                "deadbeef0", archived_pre_send=True)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertFalse(r["receipt_matches_exactly"])

    def test_same_format_or_length_never_passes(self):
        # 32-hex look-alike but different value must FAIL
        r = v02.verdict_receipt(self._send(), self._sse(), "a" * 32,
                                "b" * 32, archived_pre_send=True)
        self.assertEqual(r["verdict"], "FAIL")

    def test_transport_failure_is_unknown_not_fail(self):
        r = v02.verdict_receipt({"ok": False, "http_status": None,
                                 "error_type": "ConnectError"},
                                self._sse(), "", "x" * 32, True)
        self.assertEqual(r["verdict"], "UNKNOWN")

    def test_non_terminal_protocol_is_fail(self):
        r = v02.verdict_receipt(self._send(), self._sse(terminal_seen=False),
                                "x" * 32, "x" * 32, True)
        self.assertEqual(r["verdict"], "FAIL")

    def test_missing_pre_send_archive_cannot_pass(self):
        r = v02.verdict_receipt(self._send(), self._sse(), "x" * 32,
                                "x" * 32, archived_pre_send=False)
        self.assertEqual(r["verdict"], "FAIL")


class ImageTests(unittest.TestCase):
    def test_image_generation_clear_topmost_no_leaks(self):
        import struct
        png, gt = v02.generate_test_image()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        pos, chunks = 8, []
        while pos < len(png):
            length = struct.unpack(">I", png[pos:pos + 4])[0]
            chunks.append(png[pos + 4:pos + 8])
            pos += 12 + length
        for banned in (b"tEXt", b"iTXt", b"zTXt"):
            self.assertNotIn(banned, chunks)
        self.assertEqual([gt["red_circles"], gt["blue_squares"]],
                         [sum(1 for s in gt["shapes"] if s["color"] == "red"),
                          sum(1 for s in gt["shapes"] if s["color"] == "blue")])
        top = min(gt["shapes"], key=lambda s: s.get("cy", s.get("y")))
        self.assertEqual(top["color"], gt["topmost_color"])
        top_y = top.get("cy", top.get("y"))
        for s in gt["shapes"]:
            if s is top:
                continue
            # circle top edge = cy - r; square top edge = y (already the edge)
            other_y = (s["cy"] - s["r"]) if "cy" in s else s["y"]
            self.assertGreaterEqual(other_y - top_y, 40)
        # prompt never contains the COUNT answers (color/shape words are
        # part of the question itself, not leaks; the asked answer for the
        # topmost is its COLOR, which the question necessarily enumerates)
        for value in (str(gt["red_circles"]), str(gt["blue_squares"])):
            self.assertNotIn(value, v02.IMAGE_PROMPT)

    def test_image_body_inlines_base64_only(self):
        png, gt = v02.generate_test_image()
        body = v02.image_body("deepseek-v4-flash", png)
        img = next(c for c in body["input"][0]["content"]
                   if c["type"] == "input_image")
        self.assertTrue(img["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("http", img["image_url"])

    def test_image_verdicts(self):
        gt = {"red_circles": 2, "blue_squares": 3, "topmost_color": "red"}
        send = {"ok": True, "http_status": 200}
        sse = {"terminal_seen": True, "completed": True}
        ok = v02.verdict_image(send, sse, "red circles: 2\nblue squares: 3\ntopmost shape: red", gt)
        self.assertEqual(ok["verdict"], "PASS")
        wrong = v02.verdict_image(send, sse, "red circles: 5\nblue squares: 3\ntopmost shape: red", gt)
        self.assertEqual(wrong["verdict"], "FAIL")
        wrong_top = v02.verdict_image(send, sse, "red circles: 2\nblue squares: 3\ntopmost shape: blue", gt)
        self.assertEqual(wrong_top["verdict"], "FAIL")
        ambiguous = v02.verdict_image(send, sse, "There are some shapes.", gt)
        self.assertEqual(ambiguous["verdict"], "UNKNOWN")
        refuse = v02.verdict_image(send, sse, "I cannot see any image.", gt)
        self.assertEqual(refuse["verdict"], "FAIL")
        transport = v02.verdict_image({"ok": False, "http_status": None}, sse, "", gt)
        self.assertEqual(transport["verdict"], "UNKNOWN")


class ClientGuardTests(unittest.TestCase):
    def test_retries_and_redirects_disabled(self):
        options = v01.make_client_factory(verify_options=True).options
        self.assertEqual(options["retries"], 0)
        self.assertFalse(options["follow_redirects"])

    def test_budget_cap_is_two(self):
        gate = v01.SendGate(v02.MAX_SENDS)
        self.assertEqual(gate.max_sends, 2)
        gate.before_send(); gate.before_send()
        with self.assertRaises(v01.ProbeSendLimitExceeded):
            gate.before_send()


def sse_text_response(text, model="deepseek-v4-flash-ga-260731"):
    item = {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}
    return "\n".join([
        "event: response.output_item.done",
        "data: " + json.dumps({"type": "response.output_item.done", "item": item}),
        "",
        "event: response.completed",
        "data: " + json.dumps({"type": "response.completed", "response": {
            "model": model, "output": [item],
            "usage": {"input_tokens": 100, "output_tokens": 5}}}),
        "",
        "data: [DONE]", "",
    ])


class ExecuteOfflineTests(unittest.TestCase):
    """execute() against MockTransport with a FAKE credential; verifies
    pre-send receipt archiving, stop-on-failure and persistence."""

    def _run(self, handler):
        import httpx
        observations = {"receipt_archived_at_send": None, "requests": []}

        def wrapped(request):
            observations["requests"].append(json.loads(request.content.decode()))
            return handler(request, observations)

        def factory():
            return httpx.Client(transport=httpx.MockTransport(wrapped),
                                follow_redirects=False)

        old_key = os.environ.pop("VOLCANO_API_KEY", None)
        os.environ["VOLCANO_API_KEY"] = "fake-offline-not-a-real-key"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                probe_dir = Path(tmp)
                observations["probe_dir"] = probe_dir
                with patch.object(v02, "PROBE_DIR", probe_dir), \
                     patch.object(v01, "make_client_factory",
                                  lambda *a, **k: (lambda: factory())):
                    rc = v02.execute()
                verification = json.loads(
                    (probe_dir / "verification.json").read_text())
        finally:
            os.environ.pop("VOLCANO_API_KEY", None)
            if old_key is not None:
                os.environ["VOLCANO_API_KEY"] = old_key
        return rc, verification, observations

    def test_full_receipt_pass_then_image_handled(self):
        def handler(request, observations):
            body = observations["requests"][-1]
            if any(i.get("type") == "function_call_output"
                   for i in body.get("input", [])):
                # at the moment the request leaves, the expected receipt
                # must ALREADY be persisted on disk
                observations["receipt_archived_at_send"] = (
                    observations["probe_dir"] / "expected-receipt.json").is_file()
                receipt = json.loads(next(
                    i for i in body["input"]
                    if i.get("type") == "function_call_output")["output"])["receipt"]
                import httpx
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"},
                    text=sse_text_response(receipt))
            import httpx
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                text=sse_text_response("I cannot see any image."))
        rc, verification, observations = self._run(handler)
        self.assertEqual(verification["outcomes"]["tool_result_return"], "PASS")
        self.assertEqual(verification["outcomes"]["image_understanding"], "FAIL")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 2)
        self.assertTrue(verification["probes"]["receipt"]["archived_pre_send"])
        # the handler observed the archive file existing BEFORE dispatch
        self.assertTrue(observations["receipt_archived_at_send"])
        self.assertEqual(verification["probes"]["receipt"]["final_text_excerpt"],
                         verification["probes"]["receipt"]["expected_receipt"])

    def test_transport_failure_unknown_and_stop(self):
        import httpx

        def handler(request, observations):
            raise httpx.ConnectError("refused")
        rc, verification, observations = self._run(handler)
        self.assertEqual(verification["outcomes"]["tool_result_return"], "UNKNOWN")
        self.assertEqual(verification["outcomes"]["image_understanding"], "NOT_EXECUTED")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        self.assertEqual(verification["client_sends"]["send_errors"], 1)
        self.assertEqual(rc, 7)

    def test_execute_refuses_to_overwrite_existing_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "verification.json").write_text("{}")
            with patch.object(v02, "PROBE_DIR", Path(tmp)):
                self.assertEqual(v02.main(
                    ["--execute",
                     "--i-approve-video-use-volcano-capability-02"]), 3)


if __name__ == "__main__":
    unittest.main()
