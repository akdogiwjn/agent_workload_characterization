from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

SESSION = "offline-full-chain-dc10a6e09dbc46dda132c22d174f2345"
OUT = Path("/workspace/output")
VALIDATION = Path("/workspace/validation")


def server_main() -> None:
    sys.path.insert(0, "/opt/openstoryline/src")
    os.environ["OPENSTORYLINE_CONFIG"] = str(VALIDATION / "config.toml")
    from open_storyline.config import default_config_path, load_settings
    from open_storyline.mcp.server import create_server

    cfg = load_settings(default_config_path())
    server = create_server(cfg)
    server.settings.host = cfg.local_mcp_server.connect_host
    server.settings.port = cfg.local_mcp_server.port
    server.run(transport=cfg.local_mcp_server.server_transport)


async def main() -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from open_storyline.storage.agent_memory import ArtifactStore

    store = ArtifactStore(OUT, SESSION)
    plan_meta = store.get_latest_meta(node_id="plan_timeline_pro", session_id=SESSION)
    assert plan_meta, "preserved same-session plan_timeline_pro artifact missing"
    _, plan_result = store.load_result(plan_meta.artifact_id)
    video_items = plan_result["payload"]["tracks"]["video"]
    assert video_items, "saved timeline has no video items"

    log = (OUT / "mcp-render-only.log").open("x", encoding="utf-8")
    server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "server"],
                              cwd="/workspace", stdout=subprocess.DEVNULL,
                              stderr=log, start_new_session=True)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f"MCP server exited rc={server.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", 8001), timeout=.2):
                    break
            except OSError:
                await asyncio.sleep(.2)
        else:
            raise TimeoutError("MCP server startup timed out")

        async with streamablehttp_client("http://127.0.0.1:8001/mcp",
                                         headers={"X-Storyline-Session-Id": SESSION}) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = {t.name: t.inputSchema for t in (await client.list_tools()).tools}
                properties = tools["render_video"].get("properties", {})
                assert "include_video_audio" in properties
                assert "video_volume_scale" in properties
                result = await client.call_tool("render_video", {
                    "mode": "auto",
                    "output_max_dimension_px": 320,
                    "clip_compose_mode": "padding",
                    "crf": 23,
                    "font_color": [255, 255, 255, 255],
                    "font_size": 28,
                    "margin_bottom": 20,
                    "stroke_width": 0,
                    "stroke_color": [0, 0, 0, 255],
                    "include_video_audio": True,
                    "video_volume_scale": 1.0,
                })
                payload = result.structuredContent or json.loads(result.content[0].text)
                assert not result.isError and payload.get("isError") is False, payload
                store.save_result(SESSION, "render_video", payload, Path("/workspace/input"))

        rendered = Path(payload["tool_excute_result"]["output_path"])
        assert rendered.is_file() and rendered.stat().st_size > 0
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate,start_time,duration",
            "-of", "json", str(rendered),
        ], check=True, capture_output=True, text=True)
        streams = json.loads(probe.stdout)["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        audio = next(s for s in streams if s["codec_type"] == "audio")
        assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p", video
        assert (video["width"], video["height"]) == (320, 240), video
        assert audio["codec_name"] == "aac", audio
        assert abs(float(video["start_time"]) - float(audio["start_time"])) <= .05, streams
        assert abs(float(video["duration"]) - float(audio["duration"])) <= .05, streams

        sound = subprocess.run([
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(rendered),
            "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-",
        ], capture_output=True, text=True, check=True)
        vol_lines = [line.strip() for line in sound.stderr.splitlines()
                     if "mean_volume:" in line or "max_volume:" in line]
        assert any("mean_volume:" in line and "-inf" not in line for line in vol_lines), vol_lines
        report = {
            "status": "PASS",
            "session_id": SESSION,
            "reused_artifact": {"node_id": "plan_timeline_pro", "artifact_id": plan_meta.artifact_id},
            "mcp_tool_calls": 1,
            "real_model_requests": 0,
            "local_asr_invocations": 0,
            "render_arguments": {"include_video_audio": True, "video_volume_scale": 1.0,
                                 "aspect_ratio": "omitted; infer source 4:3",
                                 "output_max_dimension_px": 320},
            "source_timeline_video_items": len(video_items),
            "rendered_path": str(rendered),
            "rendered_bytes": rendered.stat().st_size,
            "streams": {"video": video, "audio": audio},
            "audio_volumedetect": vol_lines,
            "audio_present_non_silent": True,
            "av_start_and_duration_within_s": 0.05,
        }
        (OUT / "render-audio-result.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "streams": report["streams"],
                          "audio_volumedetect": vol_lines}, ensure_ascii=False))
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        server_main()
    else:
        asyncio.run(main())
