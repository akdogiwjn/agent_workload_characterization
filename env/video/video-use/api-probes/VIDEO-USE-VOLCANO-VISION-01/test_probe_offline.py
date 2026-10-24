"""VIDEO-USE-VOLCANO-VISION-01 offline tests.

All network interaction via httpx.MockTransport — no real socket, no real
credential (fake placeholder env value only inside guarded execute tests)."""
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
import video_use_volcano_vision_01 as v  # noqa: E402


def _truth():
    return {"left": {"color": "red", "shape": "circle", "count": 2},
            "right": {"color": "blue", "shape": "square", "count": 1},
            "red_side": "left"}


def _send_ok():
    return {"ok": True, "http_status": 200}


def _sse_ok():
    return {"terminal_seen": True, "completed": True}


class ImageGenerationTests(unittest.TestCase):
    def test_image_shape_and_no_leaks(self):
        import struct
        png, gt = v.generate_test_image()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        pos, chunks = 8, []
        while pos < len(png):
            length = struct.unpack(">I", png[pos:pos + 4])[0]
            chunks.append(png[pos + 4:pos + 8])
            pos += 12 + length
        for banned in (b"tEXt", b"iTXt", b"zTXt"):
            self.assertNotIn(banned, chunks)
        self.assertEqual(gt["image_size"], [512, 256])
        # counts and side consistency
        left_shapes = [s for s in gt["shapes"] if s["side"] == "left"]
        right_shapes = [s for s in gt["shapes"] if s["side"] == "right"]
        self.assertEqual(len(left_shapes), gt["left"]["count"])
        self.assertEqual(len(right_shapes), gt["right"]["count"])
        for s in left_shapes:
            self.assertEqual((s["color"], s["shape"]),
                             (gt["left"]["color"], gt["left"]["shape"]))
        for s in right_shapes:
            self.assertEqual((s["color"], s["shape"]),
                             (gt["right"]["color"], gt["right"]["shape"]))
        self.assertEqual(gt["red_side"],
                         "left" if gt["left"]["color"] == "red" else "right")
        # shapes never overlap (bounding boxes of distinct shapes disjoint
        # in x within a side thanks to column slots)
        for side in ("left", "right"):
            boxes = sorted(
                ([s["cx"] - s.get("r", s.get("w", 0) // 2),
                  s["cx"] + s.get("r", s.get("w", 0) // 2)]
                 for s in gt["shapes"] if s["side"] == side))
            for (a0, a1), (b0, b1) in zip(boxes, boxes[1:]):
                self.assertGreaterEqual(b0 - a1, 8,
                                        "shapes overlap or too close")
        # left/right halves actually disjoint horizontally
        for s in gt["shapes"]:
            if s["side"] == "left":
                self.assertLess(s["cx"] + s.get("r", s.get("w", 0) // 2), 256)
            else:
                self.assertGreater(s["cx"] - s.get("r", s.get("w", 0) // 2), 256)

    def test_prompt_and_filename_neutral(self):
        png, gt = v.generate_test_image()
        # the COUNT answers must not be in the prompt; left/right words are
        # inherently part of the question (it asks about both sides)
        for value in (str(gt["left"]["count"]), str(gt["right"]["count"])):
            self.assertNotIn(value, v.IMAGE_PROMPT)
        self.assertNotIn("answer", "neutral-test.png")

    def test_image_body_carries_base64_data_url(self):
        png, gt = v.generate_test_image()
        body = v.image_body("deepseek-v4-flash", png)
        img = next(c for c in body["input"][0]["content"]
                   if c["type"] == "input_image")
        self.assertTrue(img["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("http", img["image_url"])
        # the local answer is nowhere in the request
        self.assertNotIn(json.dumps(gt["left"]), json.dumps(body))
        self.assertTrue(body["stream"])
        self.assertLessEqual(body["max_output_tokens"], 2048)
        # no tools in the request
        self.assertNotIn("tools", body)


class VerdictTests(unittest.TestCase):
    def test_correct_content_with_extra_words_passes(self):
        reply = ("Sure! Here's what I see:\nleft side: 2 red circles\n"
                 "right side: 1 blue square\nred shapes are on the left side."
                 "\nHope that helps!")
        r = v.verdict_vision(_send_ok(), _sse_ok(), reply, _truth())
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["format_ok"])

    def test_exact_format_passes(self):
        reply = ("left side: 2 red circles\nright side: 1 blue squares\n"
                 "red shapes are on the left side")
        r = v.verdict_vision(_send_ok(), _sse_ok(), reply, _truth())
        self.assertEqual(r["verdict"], "PASS")

    def test_wrong_count_is_fail(self):
        reply = ("left side: 3 red circles\nright side: 1 blue squares\n"
                 "red shapes are on the left side")
        r = v.verdict_vision(_send_ok(), _sse_ok(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["reason"], "clearly_parsed_fact_is_wrong")

    def test_wrong_side_is_fail(self):
        reply = ("left side: 2 red circles\nright side: 1 blue squares\n"
                 "red shapes are on the right side")
        r = v.verdict_vision(_send_ok(), _sse_ok(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")

    def test_wrong_shape_is_fail(self):
        reply = ("left side: 2 red squares\nright side: 1 blue squares\n"
                 "red shapes are on the left side")
        r = v.verdict_vision(_send_ok(), _sse_ok(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")

    def test_empty_or_vague_answer_is_unknown(self):
        self.assertEqual(
            v.verdict_vision(_send_ok(), _sse_ok(), "", _truth())["verdict"],
            "UNKNOWN")
        self.assertEqual(
            v.verdict_vision(_send_ok(), _sse_ok(),
                             "There are some shapes.", _truth())["verdict"],
            "UNKNOWN")

    def test_cannot_see_statement_is_fail_not_unknown(self):
        r = v.verdict_vision(_send_ok(), _sse_ok(),
                             "I cannot see the image.", _truth())
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["reason"], "model_states_it_cannot_process_image")

    def test_transport_failure_is_unknown_not_vision_fail(self):
        r = v.verdict_vision({"ok": False, "http_status": None},
                             _sse_ok(), "", _truth())
        self.assertEqual(r["verdict"], "UNKNOWN")
        self.assertEqual(r["reason"], "transport_or_http_failure")

    def test_timeout_is_unknown(self):
        r = v.verdict_vision({"ok": True, "http_status": 200,
                              "request_wall_exceeded": True},
                             _sse_ok(), "", _truth())
        self.assertEqual(r["verdict"], "UNKNOWN")


class TextExtractionTests(unittest.TestCase):
    def test_nested_and_delta_no_double_concat(self):
        events = [
            {"event": "response.output_text.delta", "data": {"delta": "AB"}},
            {"event": "response.completed", "data": {"response": {
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text",
                                         "text": "AB"}]}]}}}]
        self.assertEqual(v01.extract_final_text(events), "AB")


class GateTests(unittest.TestCase):
    def test_exactly_one_send_allowed(self):
        gate = v01.SendGate(v.MAX_SENDS)
        self.assertEqual(gate.max_sends, 1)
        gate.before_send()
        with self.assertRaises(v01.ProbeSendLimitExceeded):
            gate.before_send()
        snap = gate.snapshot()
        self.assertEqual(snap["sends_initiated"], 1)
        self.assertEqual(snap["attempts_blocked"], 1)

    def test_failed_connect_still_consumes_the_single_send(self):
        gate = v01.SendGate(1)
        gate.before_send()
        gate.after_error()
        with self.assertRaises(v01.ProbeSendLimitExceeded):
            gate.before_send()
        self.assertEqual(gate.snapshot()["send_errors"], 1)

    def test_retries_and_redirects_disabled(self):
        options = v01.make_client_factory(verify_options=True).options
        self.assertEqual(options["retries"], 0)
        self.assertFalse(options["follow_redirects"])


class ExecuteOfflineTests(unittest.TestCase):
    def _run(self, handler):
        import httpx
        observations = {"requests": [], "probe_dir": None}

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
                with patch.object(v, "PROBE_DIR", probe_dir), \
                     patch.object(v01, "make_client_factory",
                                  lambda *a, **k: (lambda: factory())):
                    rc = v.execute()
                verification = json.loads(
                    (probe_dir / "verification.json").read_text())
                expected = json.loads(
                    (probe_dir / "expected-answer.json").read_text())
                png = (probe_dir / "neutral-test.png").read_bytes()
        finally:
            os.environ.pop("VOLCANO_API_KEY", None)
            if old_key is not None:
                os.environ["VOLCANO_API_KEY"] = old_key
        return rc, verification, observations, expected, png

    @staticmethod
    def _sse(text):
        item = {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": text}]}
        return "\n".join([
            "event: response.output_item.done",
            "data: " + json.dumps({"type": "response.output_item.done",
                                   "item": item}),
            "",
            "event: response.completed",
            "data: " + json.dumps({"type": "response.completed", "response": {
                "model": "deepseek-v4-flash-ga-260731", "output": [item],
                "usage": {"input_tokens": 900, "output_tokens": 40}}}),
            "", "data: [DONE]", ""])

    def test_full_pass_path_offline(self):
        import httpx

        def handler(request, observations):
            body = observations["requests"][-1]
            # base64 image really entered input_image
            content = body["input"][0]["content"]
            img = next(c for c in content if c["type"] == "input_image")
            self.assertTrue(img["image_url"].startswith("data:image/png;base64,"))
            # the request carries no local answer
            self.assertNotIn("expected", json.dumps(body).lower())
            truth = json.loads((observations["probe_dir"]
                                / "expected-answer.json").read_text())
            reply = (f"left side: {truth['left']['count']} "
                     f"{truth['left']['color']} {truth['left']['shape']}s\n"
                     f"right side: {truth['right']['count']} "
                     f"{truth['right']['color']} {truth['right']['shape']}s\n"
                     f"red shapes are on the {truth['red_side']} side")
            return httpx.Response(200,
                                  headers={"content-type": "text/event-stream"},
                                  text=self._sse(reply))
        rc, verification, observations, expected, png = self._run(handler)
        self.assertEqual(verification["vision"]["verdict"], "PASS")
        self.assertTrue(verification["vision"]["format_ok"])
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        self.assertEqual(verification["response_models_observed"],
                         ["deepseek-v4-flash-ga-260731"])
        self.assertEqual(verification["usage_observed"][0]["input_tokens"], 900)
        self.assertEqual(expected["image"]["sha256"],
                         __import__("hashlib").sha256(png).hexdigest())

    def test_transport_error_saves_counts_and_report(self):
        import httpx

        def handler(request, observations):
            raise httpx.ConnectError("refused")
        rc, verification, observations, expected, png = self._run(handler)
        self.assertEqual(verification["vision"]["verdict"], "UNKNOWN")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        self.assertEqual(verification["client_sends"]["send_errors"], 1)
        self.assertEqual(rc, 7)

    def test_execute_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "verification.json").write_text("{}")
            with patch.object(v, "PROBE_DIR", Path(tmp)):
                self.assertEqual(v.main(
                    ["--execute",
                     "--i-approve-video-use-volcano-vision-01"]), 3)


if __name__ == "__main__":
    unittest.main()
