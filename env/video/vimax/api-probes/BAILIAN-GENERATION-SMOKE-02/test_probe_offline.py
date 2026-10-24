#!/usr/bin/env python3
"""Offline regression for BAILIAN-GENERATION-SMOKE-02.

All network-shaped functions are tested through httpx.MockTransport only.
Nothing here may touch the real network, the real credential file, or the
probe evidence directory. Covers the route fixes required this round:

  1. final URLs are correct (no missing/doubled /v1);
  2. image editing uses the SAME /images/generations endpoint via the
     `image` extension field;
  3. /images/edits is never called and no multipart is ever used;
  4. image URL parsing + download wiring;
  5. video create / poll / download are counted separately;
  6. exceptions still persist actual send counts and redacted errors;
  7. a failing poll loop never re-creates the video task;
  8. a missing registered WorkspaceId blocks execute() before any network.
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe  # noqa: E402

WS = "llm-test-ws-12345"


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler),
                        follow_redirects=False, trust_env=False)


def far_deadline():
    return time.monotonic() + 1e9


class UrlBuildingTest(unittest.TestCase):
    def test_image_url(self):
        url = probe.build_image_url(WS)
        self.assertEqual(
            url,
            f"https://{WS}.cn-beijing.maas.aliyuncs.com"
            "/compatible-mode/v1/images/generations")

    def test_video_create_url_native_not_compatible(self):
        url = probe.build_video_create_url(WS)
        self.assertEqual(
            url,
            f"https://{WS}.cn-beijing.maas.aliyuncs.com"
            "/api/v1/services/aigc/video-generation/video-synthesis")
        self.assertNotIn("compatible-mode", url)

    def test_video_task_url(self):
        self.assertEqual(
            probe.build_video_task_url(WS),
            f"https://{WS}.cn-beijing.maas.aliyuncs.com/api/v1/tasks/")

    def test_no_doubled_or_missing_v1(self):
        for url in (probe.build_image_url(WS),
                    probe.build_video_create_url(WS),
                    probe.build_video_task_url(WS),
                    probe.CHAT_URL):
            self.assertNotIn("/v1/v1", url)
            self.assertNotIn("//v1", url.replace("https://", ""))
        self.assertIn("/compatible-mode/v1/", probe.build_image_url(WS))
        self.assertIn("/api/v1/", probe.build_video_create_url(WS))

    def test_chat_route_unchanged_registered_route(self):
        # C must stay on the registered, previously verified route — NOT
        # migrated to the workspace image/video domain
        self.assertEqual(probe.CHAT_URL,
                         "https://dashscope.aliyuncs.com/compatible-mode/v1"
                         "/chat/completions")
        self.assertNotIn("maas.aliyuncs.com", probe.CHAT_URL)


class WorkspaceIdTest(unittest.TestCase):
    def test_load_workspace_id_reads_registered_file_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "bailian.env"
            f.write_text("export DASHSCOPE_API_KEY=fake-key-not-real\n"
                         f"export {probe.WORKSPACE_ENV}={WS}\n")
            old = probe.CREDENTIAL_FILE
            probe.CREDENTIAL_FILE = f
            try:
                self.assertEqual(probe.load_workspace_id(), WS)
            finally:
                probe.CREDENTIAL_FILE = old

    def test_load_workspace_id_missing_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "bailian.env"
            f.write_text("export DASHSCOPE_API_KEY=fake-key-not-real\n")
            old = probe.CREDENTIAL_FILE
            probe.CREDENTIAL_FILE = f
            try:
                self.assertIsNone(probe.load_workspace_id())
            finally:
                probe.CREDENTIAL_FILE = old

    def test_load_workspace_id_unreadable_file_returns_none(self):
        old = probe.CREDENTIAL_FILE
        probe.CREDENTIAL_FILE = Path("/nonexistent/bailian.env")
        try:
            self.assertIsNone(probe.load_workspace_id())
        finally:
            probe.CREDENTIAL_FILE = old

    def test_blocked_message_mentions_console_and_no_guessing(self):
        msg = probe.BLOCKED_MSG.format(env=probe.WORKSPACE_ENV,
                                       file=probe.CREDENTIAL_FILE,
                                       region="cn-beijing")
        self.assertIn("业务空间详情", msg)
        self.assertIn(probe.WORKSPACE_ENV, msg)
        self.assertIn("No request was sent", msg)


class BodiesTest(unittest.TestCase):
    def test_A_has_no_image_field(self):
        b = probe.body_A()
        self.assertEqual(b["model"], "qwen-image-3.0")
        self.assertNotIn("image", b)
        self.assertEqual(b["size"], "1024x576")
        self.assertEqual(b["n"], 1)
        self.assertFalse(b["prompt_extend"])

    def test_B_same_endpoint_image_extension_field_base64(self):
        b = probe.body_B(b"\x89PNG-fake")
        # image editing = SAME /images/generations endpoint + `image` field
        self.assertTrue(b["image"].startswith("data:image/png;base64,"))
        self.assertNotIsInstance(b["image"], list)

    def test_C_tool_choice_and_no_thinking(self):
        b = probe.body_C(b"\x89PNG-fake")
        self.assertEqual(b["model"], "qwen3.7-plus")
        self.assertEqual(b["tool_choice"],
                         {"type": "function",
                          "function": {"name": "report_shapes"}})
        self.assertFalse(b["enable_thinking"])
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

    def test_first_frame_input_ok(self):
        ok = probe.first_frame_input_ok(b"x" * 1000, [1024, 576])
        self.assertTrue(all(v for v in ok.values() if isinstance(v, bool)))
        bad = probe.first_frame_input_ok(b"x" * 100, [100, 50])
        self.assertFalse(bad["dims_in_range"])
        self.assertFalse(bad["ratio_16_9"])


class EndpointContractTest(unittest.TestCase):
    """The actual HTTP calls must hit the right URLs with JSON bodies (no
    /images/edits, no multipart)."""

    def test_image_calls_never_hit_edits_and_use_json(self):
        seen = []
        c = probe.Counters()

        def handler(request):
            seen.append((request.method, str(request.url),
                         request.headers.get("content-type")))
            return httpx.Response(200, json={
                "created": 1,
                "data": [{"url": "https://oss.example.com/a.png?sig=1"}],
                "usage": {"input_image_count": 0,
                          "input_image_type": "qima_input_1k",
                          "output_image_count": 1,
                          "output_image_type": "qima_output_1k",
                          "output_width": 1024, "output_height": 576}})

        img_url = probe.build_image_url(WS)
        recA = probe.http_call(c, mock_client(handler), "POST", img_url,
                               counter_key="model", body=probe.body_A(),
                               deadline=far_deadline(), guard_model=True)
        recB = probe.http_call(c, mock_client(handler), "POST", img_url,
                               counter_key="model", body=probe.body_B(b"p"),
                               deadline=far_deadline(), guard_model=True)
        self.assertEqual(recA["http_status"], 200)
        self.assertEqual(recB["http_status"], 200)
        for method, url, ctype in seen:
            self.assertNotIn("/images/edits", url)
            self.assertEqual(method, "POST")
            self.assertTrue(ctype.startswith("application/json"),
                            f"multipart must never be used, got {ctype}")
        self.assertTrue(all(url.startswith(
            f"https://{WS}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/"
        ) for _, url, _ in seen))

    def test_video_create_url_and_async_header(self):
        seen = []
        c = probe.Counters()

        def handler(request):
            seen.append((request.method, str(request.url),
                         request.headers.get("X-DashScope-Async")))
            return httpx.Response(200, json={"output": {
                "task_id": "t-1", "task_status": "PENDING"},
                "request_id": "r-1"})

        probe.http_call(c, mock_client(handler), "POST",
                        probe.build_video_create_url(WS),
                        counter_key="create",
                        headers={"X-DashScope-Async": "enable"},
                        body=probe.body_D(b"p"),
                        deadline=far_deadline(), guard_model=True)
        method, url, async_hdr = seen[0]
        self.assertEqual(async_hdr, "enable")
        self.assertNotIn("compatible-mode", url)
        self.assertIn("/api/v1/services/aigc/video-generation/"
                      "video-synthesis", url)
        snap = c.snapshot()
        self.assertEqual(snap["model_operations"], 1)
        self.assertEqual(snap["create_task_requests"], 1)


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

    def test_http_error_path_counts_failure_and_returns_record(self):
        c = probe.Counters()

        def handler(request):
            raise httpx.ConnectError("boom")

        rec = probe.http_call(c, mock_client(handler), "POST",
                              probe.build_image_url(WS), counter_key="model",
                              body={}, deadline=far_deadline(),
                              guard_model=True)
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
            methods.append((request.method, str(request.url)))
            return httpx.Response(200, json={
                "output": {"task_id": "t-1", "task_status": "RUNNING"},
                "request_id": "r"})

        poll = probe.poll_video(c, mock_client(handler),
                                probe.build_video_task_url(WS), "t-1",
                                deadline=far_deadline(),
                                sleep_fn=lambda s: None)
        self.assertIsNone(poll["terminal"])
        self.assertEqual(poll["polls"], probe.POLL_MAX)
        self.assertTrue(all(m == "GET" for m, _ in methods))
        snap = c.snapshot()
        self.assertEqual(snap["create_task_requests"], 1)
        self.assertEqual(snap["model_operations"], 1)
        self.assertEqual(snap["poll_requests"], probe.POLL_MAX)

    def test_poll_error_stops_and_does_not_create(self):
        c = probe.Counters()
        c.bump("create_task_requests")
        c.bump("model_operations")

        def handler(request):
            raise httpx.ReadTimeout("poll timed out")

        poll = probe.poll_video(c, mock_client(handler),
                                probe.build_video_task_url(WS), "t-1",
                                deadline=far_deadline(),
                                sleep_fn=lambda s: None)
        self.assertEqual(poll["terminal"], "CLIENT_ERROR")
        snap = c.snapshot()
        self.assertEqual(snap["create_task_requests"], 1)
        self.assertEqual(snap["model_operations"], 1)
        self.assertEqual(snap["poll_requests"], 1)
        self.assertEqual(snap["send_failures"], 1)

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

        poll = probe.poll_video(c, mock_client(handler),
                                probe.build_video_task_url(WS), "t-1",
                                deadline=far_deadline(),
                                headers={"Authorization": "Bearer fake"},
                                sleep_fn=lambda s: None)
        self.assertEqual(poll["terminal"], "SUCCEEDED")
        self.assertEqual(poll["polls"], 3)
        self.assertEqual(c.snapshot()["poll_requests"], 3)

    def test_poll_sends_authorization_header(self):
        c = probe.Counters()
        seen_auth = []

        def handler(request):
            seen_auth.append(request.headers.get("authorization"))
            return httpx.Response(200, json={
                "output": {"task_id": "t-1", "task_status": "SUCCEEDED",
                           "video_url": "https://o.example.com/v.mp4?s=1"}})

        probe.poll_video(c, mock_client(handler),
                         probe.build_video_task_url(WS), "t-1",
                         deadline=far_deadline(),
                         headers={"Authorization": "Bearer fake-token"},
                         sleep_fn=lambda s: None)
        self.assertEqual(seen_auth, ["Bearer fake-token"])

    def test_poll_401_stops_immediately_not_burning_budget(self):
        c = probe.Counters()

        def handler(request):
            return httpx.Response(401, json={
                "code": "InvalidApiKey", "message": "No API-key provided.",
                "request_id": "r-x"})

        poll = probe.poll_video(c, mock_client(handler),
                                probe.build_video_task_url(WS), "t-1",
                                deadline=far_deadline(),
                                headers={"Authorization": "Bearer fake"},
                                sleep_fn=lambda s: None)
        self.assertEqual(poll["terminal"], "AUTH_ERROR")
        self.assertEqual(poll["polls"], 1)
        self.assertEqual(c.snapshot()["poll_requests"], 1)
        # top-level error code/message are captured for the evidence log
        self.assertEqual(poll["log"][0]["error_code"], "InvalidApiKey")
        self.assertIn("API-key", poll["log"][0]["error_message"])


class DownloadWiringTest(unittest.TestCase):
    def test_media_url_parsed_then_downloaded(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "https://oss.example.com/a.png?sig=1"}],
            "usage": {"input_image_count": 1}}}
        self.assertEqual(probe._media_url_from_images_response(rec),
                         "https://oss.example.com/a.png?sig=1")

        c = probe.Counters()

        def handler(request):
            return httpx.Response(200, content=b"png-bytes")

        tmp = Path("/tmp/opencode/bgs02-test/a.png")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        dl = probe.download_media(c, mock_client(handler),
                                  "https://oss.example.com/a.png?sig=1",
                                  tmp, 1000, deadline=far_deadline())
        self.assertTrue(dl["ok"])
        self.assertEqual(dl["bytes"], 9)
        self.assertEqual(dl["sha256"],
                         __import__("hashlib").sha256(b"png-bytes").hexdigest())
        self.assertEqual(c.snapshot()["download_requests"], 1)

    def test_download_no_auth_header_and_cap(self):
        c = probe.Counters()
        seen_headers = []

        def handler(request):
            seen_headers.append(dict(request.headers))
            return httpx.Response(200, content=b"x" * (probe.IMG_DL_CAP + 1))

        tmp = Path("/tmp/opencode/bgs02-test/b.png")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        dl = probe.download_media(c, mock_client(handler),
                                  "https://oss.example.com/b.png?sig=1",
                                  tmp, probe.IMG_DL_CAP, deadline=far_deadline())
        self.assertFalse(dl["ok"])
        self.assertEqual(dl["error_type"], "size_cap_exceeded")
        self.assertNotIn("authorization",
                         {k.lower() for k in seen_headers[0]})
        self.assertFalse(tmp.exists())

    def test_download_single_redirect_handled_without_auth(self):
        c = probe.Counters()

        def handler(request):
            path = str(request.url).split("?")[0]
            if path.endswith("/a.png"):
                return httpx.Response(
                    302,
                    headers={"location": "https://cdn.example.com/b.png?s=2"})
            return httpx.Response(200, content=b"pngdata")

        tmp = Path("/tmp/opencode/bgs02-test/c.png")
        dl = probe.download_media(c, mock_client(handler),
                                  "https://oss.example.com/a.png?sig=1",
                                  tmp, 1000, deadline=far_deadline())
        self.assertTrue(dl["ok"])
        snap = c.snapshot()
        self.assertEqual(snap["download_requests"], 2)
        self.assertEqual(snap["download_redirects"], 1)


class JudgesTest(unittest.TestCase):
    def _ev(self, left, right, white):
        return {"non_empty": True, "decodable": True, "format": "PNG",
                "size_px": [1024, 576],
                "region_stats": {"left": left, "right": right,
                                 "whole": {"white": white}}}

    def test_A_pass(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "u"}]}}
        ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        v = probe.judge_A(rec, ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["content_match"]["match"])

    def test_A_fail_http_error(self):
        rec = {"ok": True, "http_status": 400, "json": {
            "error": {"code": "InvalidParameter"}}}
        self.assertEqual(probe.judge_A(rec, {})[
            "verdict"], "FAIL")

    def test_B_separates_api_ok_from_content(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "data": [{"url": "u"}],
            "usage": {"input_image_count": 1}}}
        a_ev = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        # content correct -> PASS
        ev_ok = self._ev({"green": 0.3, "red": 0.01}, {"blue": 0.3}, 0.5)
        v = probe.judge_B(rec, ev_ok, a_ev)
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["api_call_ok"])
        self.assertTrue(v["content_ok"])
        # api ok but edit not applied -> FAIL with both dimensions recorded
        ev_bad = self._ev({"red": 0.3}, {"blue": 0.3}, 0.5)
        v2 = probe.judge_B(rec, ev_bad, a_ev)
        self.assertEqual(v2["verdict"], "FAIL")
        self.assertTrue(v2["api_call_ok"])
        self.assertFalse(v2["content_ok"])

    def test_C_pass_and_deviation_handling(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "choices": [{"finish_reason": "tool_calls", "message": {
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {
                                    "name": "report_shapes",
                                    "arguments": json.dumps({
                                        "left_color": "green",
                                        "left_shape": "circle",
                                        "right_color": "blue",
                                        "right_shape": "square"})}}]}}],
            "usage": {"input_tokens": 120, "output_tokens": 30}}}
        b_ev = self._ev({"green": 0.3}, {"blue": 0.3}, 0.5)
        v = probe.judge_C(rec, b_ev)
        self.assertEqual(v["verdict"], "PASS")
        # B actually still red; model reports red -> correct vs actual image
        rec2 = json.loads(json.dumps(rec))
        args = json.loads(rec2["json"]["choices"][0]["message"]["tool_calls"][
            0]["function"]["arguments"])
        args["left_color"] = "red"
        rec2["json"]["choices"][0]["message"]["tool_calls"][0]["function"][
            "arguments"] = json.dumps(args)
        b_ev2 = self._ev({"red": 0.3}, {"blue": 0.3}, 0.4)
        v2 = probe.judge_C(rec2, b_ev2)
        self.assertEqual(v2["verdict"], "PASS")
        self.assertIn("B actual left is red", v2["image_generation_deviation"])

    def test_C_unknown_paths(self):
        no_tool = {"ok": True, "http_status": 200, "json": {
            "choices": [{"finish_reason": "stop",
                         "message": {"content": "看不清"}}], "usage": {}}}
        self.assertEqual(probe.judge_C(no_tool, {})["verdict"], "UNKNOWN")
        bad_args = {"ok": True, "http_status": 200, "json": {
            "choices": [{"message": {"tool_calls": [
                {"id": "c", "type": "function", "function": {
                    "name": "report_shapes",
                    "arguments": "not-json"}}]}}], "usage": {}}}
        self.assertEqual(probe.judge_C(bad_args, {})["verdict"], "UNKNOWN")

    def test_D_create_and_video(self):
        rec = {"ok": True, "http_status": 200, "json": {
            "output": {"task_status": "PENDING", "task_id": "abc"},
            "request_id": "r-1"}}
        v = probe.judge_D_create(rec)
        self.assertEqual(v["verdict"], "PASS")
        self.assertEqual(v["task_id"], "abc")

        dl = {"ok": True, "bytes": 5}
        ffp = {"video_stream": {"codec_name": "h264", "width": 1280,
                                "height": 720, "r_frame_rate": "24/1"},
               "has_audio_stream": False, "duration_s": 5.0,
               "frame_stats": {"left_green_min_share": 0.05,
                               "right_blue_min_share": 0.05}}
        v = probe.judge_D_video(dl, ffp, True, ["f1", "f2"], 0.02)
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["technical_ok"])
        self.assertTrue(v["semantic_motion_ok"])
        # technical ok but no motion -> technical/semantic separated
        v2 = probe.judge_D_video(dl, ffp, True, ["f1", "f2"], 0.0)
        self.assertEqual(v2["verdict"], "FAIL")
        self.assertTrue(v2["technical_ok"])
        self.assertFalse(v2["semantic_motion_ok"])
        # audio present -> technical fail
        ffp_audio = dict(ffp, has_audio_stream=True)
        v3 = probe.judge_D_video(dl, ffp_audio, True, ["f1"], 0.02)
        self.assertEqual(v3["verdict"], "FAIL")
        self.assertFalse(v3["technical_ok"])
        self.assertIsNone(v3["semantic_motion_ok"])


class RedactionTest(unittest.TestCase):
    def test_redact_headers_and_keys(self):
        s = probe.redact("Authorization: Bearer sk-abc123456789\n"
                         "api_key=sk-xyz987654321")
        self.assertNotIn("abc123456789", s)
        self.assertNotIn("xyz987654321", s)

    def test_strip_url_query(self):
        self.assertEqual(
            probe.strip_url_query("https://o.com/a.png?Expires=1&Signature=Z"),
            "https://o.com/a.png")


class RegionStatsTest(unittest.TestCase):
    def test_region_stats_synthetic_image(self):
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (200, 100), "white")
        d = ImageDraw.Draw(im)
        d.ellipse([10, 25, 90, 95], fill=(0, 180, 0))
        d.rectangle([120, 20, 190, 90], fill=(0, 0, 220))
        st = probe.region_stats(im)
        self.assertGreater(st["left"]["green"], 0.1)
        self.assertGreater(st["right"]["blue"], 0.1)
        self.assertEqual(probe.dominant(st["left"]), "green")
        self.assertEqual(probe.dominant(st["right"]), "blue")


class ManifestTest(unittest.TestCase):
    def test_manifest_covers_files_and_skips_self(self):
        d = Path("/tmp/opencode/bgs02-manifest-test")
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.json").write_text("{}")
        (d / "x.part").write_text("partial")
        m = probe.build_manifest(d, inputs={"a": "b"})
        self.assertIn("plan.json", m["files"])
        self.assertNotIn("manifest.json", m["files"])
        self.assertNotIn("x.part", m["files"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
