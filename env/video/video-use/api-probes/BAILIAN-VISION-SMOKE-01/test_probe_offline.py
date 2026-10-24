"""BAILIAN-VISION-SMOKE-01 offline tests (no network, no real credential)."""
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
import bailian_vision_smoke_01 as v  # noqa: E402


def _truth():
    return {"red_circles": 2, "blue_squares": 3, "red_side": "left"}


def _send_ok():
    return {"ok": True, "http_status": 200}


def _sse_completed():
    return {"terminal_seen": True, "completed": True, "incomplete": False}


class ImageBodyTests(unittest.TestCase):
    def test_base64_image_enters_input_image(self):
        png, gt = v.vision01.generate_test_image()
        truth = v.normalize_truth(gt)
        body = v.image_body(png)
        img = next(c for c in body["input"][0]["content"]
                   if c["type"] == "input_image")
        self.assertTrue(img["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("http", img["image_url"])
        self.assertEqual(body["model"], "qwen3.7-plus")
        self.assertTrue(body["stream"])
        self.assertLessEqual(body["max_output_tokens"], 4096)
        # no tools, no reasoning parameter (unconfirmed for qwen3.7-plus)
        self.assertNotIn("tools", body)
        self.assertNotIn("reasoning", body)
        self.assertNotIn("enable_thinking", body)
        # counts not leaked into the question text
        self.assertNotIn(str(truth["red_circles"]), v.QUESTION)
        self.assertNotIn(str(truth["blue_squares"]), v.QUESTION)

    def test_url_is_registered_base_plus_responses(self):
        self.assertEqual(v.v01.build_responses_url(v.BASE_URL),
                         "https://dashscope.aliyuncs.com/compatible-mode/v1/responses")

    def test_png_has_no_text_chunks(self):
        import struct
        png, gt = v.vision01.generate_test_image()
        pos, chunks = 8, []
        while pos < len(png):
            length = struct.unpack(">I", png[pos:pos + 4])[0]
            chunks.append(png[pos + 4:pos + 8])
            pos += 12 + length
        for banned in (b"tEXt", b"iTXt", b"zTXt"):
            self.assertNotIn(banned, chunks)


class ParseTests(unittest.TestCase):
    def test_markdown_list_layout_parsed(self):
        # regression: the REAL qwen3.7-plus reply used a markdown list with
        # color/shape/count on separate lines inside per-side blocks
        reply = ("根据图片内容，两类图形的具体特征如下：\n\n"
                 "1.  **左侧图形**：\n    *   **颜色**：红色\n"
                 "    *   **形状**：圆形\n    *   **数量**：3个\n"
                 "    *   **位置**：位于图片的左侧（呈从左下到右上的斜线排列）。\n\n"
                 "2.  **右侧图形**：\n    *   **颜色**：蓝色\n"
                 "    *   **形状**：正方形\n    *   **数量**：3个\n"
                 "    *   **位置**：位于图片的右侧（呈不规则分布）。")
        parsed = v.parse_chinese_reply(reply)
        self.assertEqual(parsed["red"], 3)
        self.assertEqual(parsed["blue"], 3)
        self.assertEqual(parsed["red_side"], "left")
        self.assertTrue(parsed["shape_binding"]["red"].startswith("圆"))
        self.assertIn("方", parsed["shape_binding"]["blue"])

    def test_markdown_list_reversed_side_parsed(self):
        reply = ("1. **左侧**：颜色：蓝色，形状：正方形，数量：2个\n"
                 "2. **右侧**：颜色：红色，形状：圆形，数量：1个")
        parsed = v.parse_chinese_reply(reply)
        self.assertEqual(parsed["blue"], 2)
        self.assertEqual(parsed["red"], 1)
        self.assertEqual(parsed["red_side"], "right")

    def test_typical_chinese_reply_parsed(self):
        reply = ("图片中有两类图形:左侧有2个红色圆形,右侧有3个蓝色方形。"
                 "红色圆形位于图片左侧,蓝色方形位于右侧。")
        parsed = v.parse_chinese_reply(reply)
        self.assertEqual(parsed["red"], 2)
        self.assertEqual(parsed["blue"], 3)
        self.assertEqual(parsed["red_side"], "left")

    def test_reversed_side_parsed(self):
        reply = "左侧有 3 个蓝色方形,右侧有 2 个红色圆形,红色图形在右侧。"
        parsed = v.parse_chinese_reply(reply)
        self.assertEqual(parsed["blue"], 3)
        self.assertEqual(parsed["red"], 2)
        self.assertEqual(parsed["red_side"], "right")

    def test_number_first_order_parsed(self):
        reply = "图片左半部分是 2 个红色圆,右半部分是 3 个蓝色的方。"
        parsed = v.parse_chinese_reply(reply)
        self.assertEqual(parsed["red"], 2)
        self.assertEqual(parsed["blue"], 3)

    def test_vague_reply_not_parsed(self):
        parsed = v.parse_chinese_reply("图中是一些图形。")
        self.assertIsNone(parsed["red"])
        self.assertIsNone(parsed["red_side"])


class VerdictTests(unittest.TestCase):
    def test_correct_with_extra_words_passes(self):
        reply = ("当然可以!左侧有2个红色圆形,右侧有3个蓝色方形,"
                 "红色圆形在左侧。希望这个回答对你有帮助!")
        r = v.verdict(_send_ok(), _sse_completed(), reply, _truth())
        self.assertEqual(r["verdict"], "PASS", r)

    def test_wrong_count_fails(self):
        reply = "左侧有5个红色圆形,右侧有3个蓝色方形,红色圆形在左侧。"
        r = v.verdict(_send_ok(), _sse_completed(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")

    def test_wrong_side_fails(self):
        reply = "左侧有2个红色圆形,右侧有3个蓝色方形,红色圆形在右侧。"
        r = v.verdict(_send_ok(), _sse_completed(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")

    def test_wrong_shape_binding_fails(self):
        reply = "左侧有2个红色方形,右侧有3个蓝色方形,红色方形在左侧。"
        r = v.verdict(_send_ok(), _sse_completed(), reply, _truth())
        self.assertEqual(r["verdict"], "FAIL")

    def test_empty_reply_unknown(self):
        r = v.verdict(_send_ok(), _sse_completed(), "", _truth())
        self.assertEqual(r["verdict"], "UNKNOWN")

    def test_cannot_see_statement_is_fail(self):
        r = v.verdict(_send_ok(), _sse_completed(),
                      "抱歉,我无法看到图片内容。", _truth())
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["reason"], "model_states_it_cannot_process_image")

    def test_failure_reasons_recorded_distinctly(self):
        cases = [
            ({"ok": False, "http_status": None, "error_type": "ConnectError"},
             _sse_completed(), "", "transport_or_http_failure"),
            ({"ok": True, "http_status": 200, "request_wall_exceeded": True},
             _sse_completed(), "", "request_timeout"),
            ({"ok": True, "http_status": 401}, _sse_completed(), "", "auth_error"),
            (_send_ok(), {"terminal_seen": False, "completed": False,
                          "incomplete": False}, "", "no_terminal_event"),
            (_send_ok(), {"terminal_seen": True, "completed": False,
                          "incomplete": True}, "", "response_incomplete"),
        ]
        for send, sse, reply, expected in cases:
            r = v.verdict(send, sse, reply, _truth())
            self.assertEqual(r["verdict"], "UNKNOWN", expected)
            self.assertEqual(r["reason"], expected)


class GateTests(unittest.TestCase):
    def test_exactly_one_send(self):
        gate = v01.SendGate(v.MAX_SENDS)
        self.assertEqual(gate.max_sends, 1)
        gate.before_send()
        with self.assertRaises(v01.ProbeSendLimitExceeded):
            gate.before_send()

    def test_retries_and_redirects_disabled(self):
        options = v01.make_client_factory(verify_options=True).options
        self.assertEqual(options["retries"], 0)
        self.assertFalse(options["follow_redirects"])


class TextExtractionTests(unittest.TestCase):
    def test_nested_text_and_no_double_concat(self):
        events = [
            {"event": "response.output_text.delta", "data": {"delta": "答"}},
            {"event": "response.completed", "data": {"response": {
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text",
                                         "text": "答案"}]}]}}}]
        self.assertEqual(v01.extract_final_text(events), "答案")


class ExecuteOfflineTests(unittest.TestCase):
    def _run(self, handler):
        import httpx
        observations = {"requests": [], "probe_dir": None,
                        "events_truncated": []}

        def wrapped(request):
            observations["requests"].append(json.loads(request.content.decode()))
            return handler(request, observations)

        def factory():
            return httpx.Client(transport=httpx.MockTransport(wrapped),
                                follow_redirects=False)

        cred = Path(tempfile.mkdtemp()) / "bailian.env"
        cred.write_text("# comment\nDASHSCOPE_API_KEY=fake-offline-not-real\n")
        with tempfile.TemporaryDirectory() as tmp:
            probe_dir = Path(tmp)
            observations["probe_dir"] = probe_dir
            with patch.object(v, "PROBE_DIR", probe_dir), \
                 patch.object(v, "CREDENTIAL_FILE", cred), \
                 patch.object(v01, "make_client_factory",
                              lambda *a, **k: (lambda: factory())):
                rc = v.execute()
            verification = json.loads(
                (probe_dir / "verification.json").read_text())
        return rc, verification, observations

    @staticmethod
    def _sse(text, status="completed"):
        item = {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": text}]}
        resp = {"model": "qwen3.7-plus", "status": status, "output": [item],
                "usage": {"input_tokens": 800, "output_tokens": 60,
                          "output_tokens_details": {"reasoning_tokens": 40}}}
        terminal = ("response.completed" if status == "completed"
                    else "response.incomplete")
        return "\n".join([
            "event: " + terminal,
            "data: " + json.dumps({"type": terminal, "response": resp}),
            "", "data: [DONE]", ""])

    def test_full_pass_path_offline(self):
        import httpx

        def handler(request, observations):
            body = observations["requests"][-1]
            content = body["input"][0]["content"]
            img = next(c for c in content if c["type"] == "input_image")
            self.assertTrue(img["image_url"].startswith("data:image/png;base64,"))
            truth = json.loads((observations["probe_dir"]
                                / "expected-answer.json").read_text())
            reply = (f"左侧有{truth['red_circles']}个红色圆形,"
                     f"右侧有{truth['blue_squares']}个蓝色方形,"
                     f"红色圆形在{'左' if truth['red_side']=='left' else '右'}侧。")
            return httpx.Response(200,
                                  headers={"content-type": "text/event-stream"},
                                  text=self._sse(reply))
        rc, verification, observations = self._run(handler)
        probe = verification["probes"]["vision"]
        self.assertEqual(probe["verdict"], "PASS")
        self.assertEqual(verification["response_models_observed"],
                         ["qwen3.7-plus"])
        self.assertEqual(verification["usage_observed"][0]["input_tokens"], 800)
        self.assertEqual(verification["response_status"], "completed")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        # SSE terminal state and usage retained IN FULL (no truncation)
        full_events = probe["send"]["sse_events_redacted_full"]
        self.assertTrue(full_events)
        terminal = [e for e in full_events
                    if e["event"] == "response.completed"]
        self.assertTrue(terminal)
        self.assertIn("usage", terminal[0]["data"])
        self.assertIn("reasoning_tokens", terminal[0]["data"])

    def test_transport_error_saves_counts_and_report(self):
        import httpx

        def handler(request, observations):
            raise httpx.ConnectError("refused")
        rc, verification, observations = self._run(handler)
        self.assertEqual(verification["probes"]["vision"]["verdict"], "UNKNOWN")
        self.assertEqual(verification["client_sends"]["sends_initiated"], 1)
        self.assertEqual(verification["client_sends"]["send_errors"], 1)
        self.assertEqual(rc, 7)

    def test_missing_credential_file_refuses(self):
        with patch.object(v, "CREDENTIAL_FILE", Path("/nonexistent/bailian.env")), \
             tempfile.TemporaryDirectory() as tmp:
            with patch.object(v, "PROBE_DIR", Path(tmp)):
                with self.assertRaises(SystemExit):
                    v.execute()
            self.assertFalse((Path(tmp) / "verification.json").exists())

    def test_execute_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "verification.json").write_text("{}")
            with patch.object(v, "PROBE_DIR", Path(tmp)):
                self.assertEqual(v.main(
                    ["--execute", "--i-approve-bailian-vision-smoke-01"]), 3)


if __name__ == "__main__":
    unittest.main()
