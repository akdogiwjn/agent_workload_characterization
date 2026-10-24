#!/usr/bin/env python3
"""Offline regression for BAILIAN-GENERATION-SMOKE-01.

All network-shaped functions are tested through httpx.MockTransport only.
Nothing here may touch the real network, the credential file, or the probe
evidence directory.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe  # noqa: E402


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler),
                        follow_redirects=False, trust_env=False)


class BodiesTest(unittest.TestCase):
    def test_A_has_no_image_field(self):
        b = probe.body_A()
        self.assertEqual(b["model"], "qwen-image-3.0")
        self.assertNotIn("image", b)
        self.assertEqual(b["size"], "1024x576")
        self.assertEqual(b["n"], 1)
        self.assertFalse(b["prompt_extend"])

    def test_B_carries_single_reference_image_data_url(self):
        b = probe.body_B(b"\x89PNG-fake")
        self.assertTrue(b["image"].startswith("data:image/png;base64,"))
        self.assertNotIsInstance(b["image"], list)

    def test_C_tool_choice_and_no_thinking(self):
        b = probe.body_C(b"\x89PNG-fake")
        self.assertEqual(b["model"], "qwen3.7-plus")
        self.assertEqual(b["tool_choice"],
                         {"type": "function",
                          "function": {"name": "report_shapes"}})
        self.assertFalse(b["enable_thinking"])
        tool = b["tools"][0]["function"]
        self.assertEqual(tool["name"], "report_shapes")
        self.assertEqual(sorted(tool["parameters"]["required"]),
                         ["left_color", "left_shape",
                          "right_color", "right_shape"])
        kinds = [p["type"] for p in b["messages"][0]["content"]]
        self.assertEqual(kinds, ["text", "image_url"])

    def test_D_first_frame_and_params(self):
        b = probe.body_D(b"\x89PNG-fake")
        self.assertEqual(b["model"], "wan2.6-i2v-flash")
        self.assertTrue(b["input"]["img_url"].startswith(
            "data:image/png;base64,"))
        self.assertEqual(b["parameters"],
                         {"resolution": "720P", "duration": 5, "audio": False,
                          "prompt_extend": False, "watermark": False})
        self.assertNotIn("shot_type", b["parameters"])


class CountersTest(unittest.TestCase):
    def test_model_cap_blocks_fifth_operation(self):
        c = probe.Counters(model_cap=4)
        for _ in range(4):
            c.guard_model()
            c.bump("model_operations")
        with self.assertRaises(probe.SendLimitExceeded):
            c.guard_model()
        snap = c.snapshot()
        self.assertEqual(snap["model_operations"], 4)
        self.assertEqual(snap["model_ops_blocked"], 1)

    def test_create_counts_model_and_create(self):
        c = probe.Counters()
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"output": {
                "task_id": "t-1", "task_status": "PENDING"}})

        rec = probe.http_call(c, mock_client(handler), "POST",
                              probe.VIDEO_CREATE_URL, counter_key="create",
                              body={"model": "wan2.6-i2v-flash"},
                              deadline=1e18, guard_model=True)
        self.assertTrue(rec["ok"])
        self.assertEqual(c.snapshot()["model_operations"], 1)
        self.assertEqual(c.snapshot()["create_task_requests"], 1)

    def test_http_error_path_counts_failure_and_returns_record(self):
        c = probe.Counters()

        def handler(request):
            raise httpx.ConnectError("boom")

        rec = probe.http_call(c, mock_client(handler), "POST",
                              probe.IMAGES_URL, counter_key="model",
                              body={}, deadline=1e18, guard_model=True)
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["error_type"], "ConnectError")
        self.assertEqual(c.snapshot()["model_operations"], 1)
        self.assertEqual(c.snapshot()["send_failures"], 1)


class PollNeverCreatesTest(unittest.TestCase):
    def test_poll_only_gets_and_never_recreates(self):
        c = probe.Counters()
        c.bump("create_task_requests")
        c.bump("model_operations")
        methods = []

        def handler(request):
            methods.append((request.method, request.url.path))
            return httpx.Response(200, json={
                "output": {"task_id": "t-1", "task_status": "RUNNING"},
                "request_id": "r"})

        poll = probe.poll_video(c, mock_client(handler), "t-1",
                                deadline=time_deadline_far(),
                                sleep_fn=lambda s: None)
        self.assertIsNone(poll["terminal"])
        self.assertEqual(poll["polls"], probe.POLL_MAX)
        self.assertEqual(len(methods), probe.POLL_MAX)
        self.assertTrue(all(m == "GET" for m, _ in methods))
        snap = c.snapshot()
        # create/model counters untouched by polling
        self.assertEqual(snap["create_task_requests"], 1)
        self.assertEqual(snap["model_operations"], 1)
        self.assertEqual(snap["poll_requests"], probe.POLL_MAX)

    def test_poll_stops_on_succeeded(self):
        c = probe.Counters()
        calls = []

        def handler(request):
            calls.append(1)
            status = "RUNNING" if len(calls) < 3 else "SUCCEEDED"
            out = {"task_id": "t-1", "task_status": status}
            if status == "SUCCEEDED":
                out["video_url"] = "https://oss.example.com/v.mp4?Expires=1&Signature=XYZ"
            return httpx.Response(200, json={"output": out})

        poll = probe.poll_video(c, mock_client(handler), "t-1",
                                deadline=time_deadline_far(),
                                sleep_fn=lambda s: None)
        self.assertEqual(poll["terminal"], "SUCCEEDED")
        self.assertEqual(poll["polls"], 3)
        self.assertEqual(c.snapshot()["poll_requests"], 3)


def time_deadline_far():
    import time
    return time.monotonic() + 1e9


class NestedParseTest(unittest.TestCase):
    def test_images_response_usage_nested(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "created": 1,
            "data": [{"url": "https://oss.example.com/a.png?sig=1"}],
            "usage": {"output_width": 1024, "output_height": 576,
                      "input_image_count": 1,
                      "input_image_type": "qima_input_1k",
                      "output_image_count": 1,
                      "output_image_type": "qima_output_1k"}}}
        self.assertEqual(
            probe._media_url_from_images_response(rec),
            "https://oss.example.com/a.png?sig=1")
        self.assertEqual(rec["json"]["usage"]["input_image_count"], 1)

    def test_video_create_task_id_nested(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "output": {"task_status": "PENDING", "task_id": "abc-123"},
            "request_id": "req-1"}}
        v = probe.judge_D_create(rec)
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["task_id"], "abc-123")

    def test_chat_tool_calls_arguments_parsed(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "model": "qwen3.7-plus", "id": "chatcmpl-1",
            "choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {
                                    "name": "report_shapes",
                                    "arguments": json.dumps({
                                        "left_color": "green",
                                        "left_shape": "circle",
                                        "right_color": "blue",
                                        "right_shape": "square"})}}]}}],
            "usage": {"input_tokens": 100, "output_tokens": 20,
                      "total_tokens": 120}}}
        b_ev = {"region_stats": {"left": {"green": 0.2}, "right": {
            "blue": 0.2}, "whole": {"white": 0.5}}}
        v = probe.judge_C(rec, b_ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["field_checks"]["left_color"], "green")
        self.assertIn("input_tokens", v["image_input_evidence"][
            "usage_fields_present"])

    def test_chinese_words_accepted_in_tool_args(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"finish_reason": "tool_calls", "message": {
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {
                                    "name": "report_shapes",
                                    "arguments": json.dumps({
                                        "left_color": "绿色",
                                        "left_shape": "圆形",
                                        "right_color": "蓝色",
                                        "right_shape": "正方形"})}}]}}],
            "usage": {}}}
        v = probe.judge_C(rec, {"region_stats": {}})
        self.assertEqual(v["field_checks"], {
            "left_color": "green", "left_shape": "circle",
            "right_color": "blue", "right_shape": "square"})

    def test_C_image_generation_deviation_not_vision_fail(self):
        # B actually still red on the left (edit deviation); model reports
        # red: recognized the REAL image correctly
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"finish_reason": "tool_calls", "message": {
                "tool_calls": [{"id": "c", "type": "function",
                                "function": {
                                    "name": "report_shapes",
                                    "arguments": json.dumps({
                                        "left_color": "red",
                                        "left_shape": "circle",
                                        "right_color": "blue",
                                        "right_shape": "square"})}}]}}],
            "usage": {}}}
        b_ev = {"region_stats": {"left": {"red": 0.3}, "right": {
            "blue": 0.3}, "whole": {"white": 0.4}}}
        v = probe.judge_C(rec, b_ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertIn("B actual left is red", v["image_generation_deviation"])


class JudgesTest(unittest.TestCase):
    def _ev(self, left, right, white):
        return {"non_empty": True, "decodable": True, "format": "PNG",
                "size_px": [1024, 576],
                "region_stats": {"left": left, "right": right,
                                 "whole": {"white": white}}}

    def test_A_pass(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "https://x/a.png?sig=1"}]}}
        ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        v = probe.judge_A(rec, ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["content_match"]["match"])

    def test_A_fail_http_error(self):
        rec = {"ok": True, "http_status": 400, "json": {
            "error": {"code": "InvalidParameter"}}}
        self.assertEqual(probe.judge_A(rec, {})[
            "verdict"], "FAIL")

    def test_A_fail_undecodable(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "u"}]}}
        ev = {"non_empty": True, "decodable": False}
        self.assertEqual(probe.judge_A(rec, ev)["verdict"], "FAIL")

    def test_B_pass_edit_applied(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "u"}],
            "usage": {"input_image_count": 1}}}
        ev = self._ev({"green": 0.3, "red": 0.01}, {"blue": 0.3}, 0.5)
        a_ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        v = probe.judge_B(rec, ev, a_ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["single_ref_accepted"])

    def test_B_fail_edit_not_applied(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "u"}], "usage": {"input_image_count": 1}}}
        ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)  # still red
        a_ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        v = probe.judge_B(rec, ev, a_ev)
        self.assertEqual(v["verdict"], "FAIL")
        self.assertEqual(v["reason"], "edit_not_applied_or_layout_broken")

    def test_C_unknown_no_tool_call(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"finish_reason": "stop", "message": {
                "content": "我看不清"}}], "usage": {}}}
        v = probe.judge_C(rec, {})
        self.assertEqual(v["verdict"], "UNKNOWN")

    def test_C_unknown_bad_arguments_json(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"message": {"tool_calls": [
                {"id": "c", "type": "function", "function": {
                    "name": "report_shapes",
                    "arguments": "not-json"}}]}}], "usage": {}}}
        self.assertEqual(probe.judge_C(rec, {})["verdict"], "UNKNOWN")

    def test_C_fail_wrong_field(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"message": {"tool_calls": [
                {"id": "c", "type": "function", "function": {
                    "name": "report_shapes",
                    "arguments": json.dumps({
                        "left_color": "purple", "left_shape": "circle",
                        "right_color": "blue", "right_shape": "square"})}}]}}],
            "usage": {}}}
        b_ev = {"region_stats": {"left": {"green": 0.3}, "right": {
            "blue": 0.3}, "whole": {"white": 0.4}}}
        v = probe.judge_C(rec, b_ev)
        self.assertEqual(v["verdict"], "UNKNOWN")  # purple -> unparseable enum
        rec2 = json.loads(json.dumps(rec))
        args = json.loads(rec2["json"]["choices"][0]["message"]["tool_calls"][
            0]["function"]["arguments"])
        args["left_color"] = "red"
        rec2["json"]["choices"][0]["message"]["tool_calls"][0]["function"][
            "arguments"] = json.dumps(args)
        v2 = probe.judge_C(rec2, b_ev)
        self.assertEqual(v2["verdict"], "FAIL")

    def test_D_video_pass_and_fail(self):
        dl = {"ok": True, "sha256": "x", "bytes": 5}
        ffp = {"video_stream": {"codec_name": "h264", "width": 1280,
                                "height": 720, "r_frame_rate": "24/1"},
               "has_audio_stream": False, "duration_s": 5.0,
               "frame_stats": {"left_green_min_share": 0.05,
                               "right_blue_min_share": 0.05}}
        v = probe.judge_D_video(dl, ffp, True, ["f1", "f2", "f3"], 0.02)
        self.assertEqual(v["verdict"], "PASS")
        ffp_bad = dict(ffp, duration_s=8.0)
        self.assertEqual(
            probe.judge_D_video(dl, ffp_bad, True, ["f1"], 0.02)["verdict"],
            "FAIL")
        ffp_audio = dict(ffp, has_audio_stream=True)
        self.assertEqual(
            probe.judge_D_video(dl, ffp_audio, True, ["f1"], 0.02)["verdict"],
            "FAIL")
        self.assertEqual(
            probe.judge_D_video(dl, ffp, True, ["f1"], 0.0)["verdict"],
            "FAIL")  # no motion
        self.assertEqual(
            probe.judge_D_video({"ok": False}, None, None, [], None)[
                "verdict"], "FAIL")


class RedactionTest(unittest.TestCase):
    def test_redact_headers_and_keys(self):
        s = probe.redact("Authorization: Bearer sk-abc123456789\n"
                         "api_key=sk-xyz987654321")
        self.assertNotIn("abc123456789", s)
        self.assertNotIn("xyz987654321", s)
        self.assertIn("[REDACTED]", s)

    def test_strip_url_query(self):
        self.assertEqual(
            probe.strip_url_query("https://o.com/a.png?Expires=1&Signature=Z"),
            "https://o.com/a.png")


class DownloadTest(unittest.TestCase):
    def test_download_no_auth_header_and_cap(self):
        c = probe.Counters()
        seen_headers = []

        def handler(request):
            seen_headers.append(dict(request.headers))
            return httpx.Response(200, content=b"x" * (probe.IMG_DL_CAP + 1))

        tmp = Path("/tmp/opencode/bgs01-test/a.png")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        dl = probe.download_media(c, mock_client(handler),
                                  "https://oss.example.com/a.png?sig=1",
                                  tmp, probe.IMG_DL_CAP, deadline=1e18)
        self.assertFalse(dl["ok"])
        self.assertEqual(dl["error_type"], "size_cap_exceeded")
        self.assertEqual(c.snapshot()["download_requests"], 1)
        self.assertNotIn("authorization",
                         {k.lower() for k in seen_headers[0]})
        self.assertFalse(tmp.exists())
        self.assertFalse(tmp.with_suffix(".png.part").exists())

    def test_download_single_redirect_handled_without_auth(self):
        c = probe.Counters()
        hosts = []

        def handler(request):
            hosts.append(str(request.url).split("?")[0])
            if "oss.example.com/a.png" == str(request.url).split("?")[0].removeprefix(
                    "https://"):
                return httpx.Response(
                    302, headers={"location": "https://cdn.example.com/b.png?s=2"})
            return httpx.Response(200, content=b"pngdata")

        tmp = Path("/tmp/opencode/bgs01-test/b.png")
        dl = probe.download_media(c, mock_client(handler),
                                  "https://oss.example.com/a.png?sig=1",
                                  tmp, 1000, deadline=1e18)
        self.assertTrue(dl["ok"])
        self.assertEqual(dl["bytes"], 7)
        snap = c.snapshot()
        self.assertEqual(snap["download_requests"], 2)
        self.assertEqual(snap["download_redirects"], 1)

    def test_download_empty_body_fails(self):
        c = probe.Counters()

        def handler(request):
            return httpx.Response(200, content=b"")

        tmp = Path("/tmp/opencode/bgs01-test/c.png")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        dl = probe.download_media(c, mock_client(handler),
                                  "https://o.example.com/c.png", tmp, 1000,
                                  deadline=1e18)
        self.assertFalse(dl["ok"])
        self.assertEqual(dl["error_type"], "empty_body")


class RegionStatsTest(unittest.TestCase):
    def test_region_stats_synthetic_image(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (200, 100), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 25, 90, 95], fill=(0, 180, 0))    # left green circle
        d.rectangle([120, 20, 190, 90], fill=(0, 0, 220))  # right blue square
        st = probe.region_stats(im)
        self.assertGreater(st["left"]["green"], 0.1)
        self.assertGreater(st["right"]["blue"], 0.1)
        self.assertGreater(st["whole"]["white"], 0.3)
        self.assertEqual(probe.dominant(st["left"]), "green")
        self.assertEqual(probe.dominant(st["right"]), "blue")

    def test_dominant_returns_none_when_absent(self):
        self.assertIsNone(probe.dominant({"white": 0.9, "other": 0.1}))


class ManifestTest(unittest.TestCase):
    def test_manifest_covers_files_and_skips_self(self):
        d = Path("/tmp/opencode/bgs01-manifest-test")
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.json").write_text("{}")
        (d / "x.part").write_text("partial")
        m = probe.build_manifest(d, inputs={"a": "b"})
        self.assertIn("plan.json", m["files"])
        self.assertNotIn("manifest.json", m["files"])
        self.assertNotIn("x.part", m["files"])
        self.assertIn("sha256", m["files"]["plan.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
