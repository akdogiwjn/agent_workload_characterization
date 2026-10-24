import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

SESSION = "offline-full-chain-dc10a6e09dbc46dda132c22d174f2345"
OUT = Path("/workspace/output")
VALIDATION = Path("/workspace/validation")


class FakeRoughCutLLM:
    async def complete(self, **kwargs):
        prompt = kwargs.get("user_prompt") or ""
        payload = prompt.split("Current:", 1)[1].split("\nPreceding Context:", 1)[0].strip()
        current = json.loads(payload)
        response = {"reason": "deterministic offline wiring response; retain this ASR sentence",
                    "res": [{"text": current["text"],
                             "start": current["start"], "end": current["end"]}]}
        with (OUT / "fake-model-events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": "fake_model_response",
                                     "boundary": "SpeechRoughCutNode llm.complete",
                                     "input_sentence": current,
                                     "response": response}, ensure_ascii=False) + "\n")
        return json.dumps(response, ensure_ascii=False)


def server_main():
    sys.path.insert(0, "/opt/openstoryline/src")
    os.environ["OPENSTORYLINE_CONFIG"] = str(VALIDATION / "config.toml")
    from open_storyline.config import default_config_path, load_settings
    from open_storyline.mcp import register_tools
    from open_storyline.mcp.server import create_server

    register_tools.make_llm = lambda _ctx: FakeRoughCutLLM()
    cfg = load_settings(default_config_path())
    server = create_server(cfg)
    server.settings.host = cfg.local_mcp_server.connect_host
    server.settings.port = cfg.local_mcp_server.port
    server.run(transport=cfg.local_mcp_server.server_transport)


async def client_main():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from open_storyline.storage.agent_memory import ArtifactStore

    store = ArtifactStore(OUT, SESSION)
    prior = {}
    for node_id in ("load_media", "split_shots", "local_asr"):
        meta = store.get_latest_meta(node_id=node_id, session_id=SESSION)
        assert meta, f"missing same-session prerequisite {node_id}"
        _, data = store.load_result(meta.artifact_id)
        prior[node_id] = data["payload"]
    asr_infos = prior["local_asr"].get("asr_infos", [])
    assert asr_infos and asr_infos[0].get("asr_sentence_info")
    assert len(asr_infos[0]["asr_timestamps"]) > 0

    log = (OUT / "mcp-server.log").open("x", encoding="utf-8")
    server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "server"],
                              cwd="/workspace", stdout=subprocess.DEVNULL,
                              stderr=log, start_new_session=True)
    events = []
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
                assert "artifact_id" not in tools["load_media"].get("properties", {})

                async def call(name, args):
                    tool_event_id = uuid.uuid4().hex
                    result = await client.call_tool(name, args)
                    data = result.structuredContent or json.loads(result.content[0].text)
                    event = {"tool_event_id": tool_event_id, "count": 1, "tool": name,
                             "arguments": args, "is_error": bool(result.isError), "result": data}
                    events.append(event)
                    assert not result.isError and data.get("isError") is False, (name, data)
                    store.save_result(SESSION, name, data, Path("/workspace/input"))
                    return data

                rough = await call("speech_rough_cut", {
                    "mode": "auto", "gap_threshold": 400,
                    "user_request": "Offline interface check: preserve all real ASR sentences.",
                })
                rough_payload = rough["tool_excute_result"]
                rough_clips = rough_payload.get("clips", [])
                assert rough_clips, rough_payload
                assert len(rough_payload.get("rough_cut_jsons", [])) == 1

                plan = await call("plan_timeline_pro", {
                    "mode": "auto", "use_beats": False, "is_speech_rough_cut": True,
                    "is_ai_transition": False, "image_duration_ms": 3000,
                })
                timeline = plan["tool_excute_result"].get("tracks", {}).get("video", [])
                assert timeline and all(Path(item["source_path"]).is_file() for item in timeline), plan
                await call("elementrec_transition", {"mode": "skip"})
                await call("elementrec_text", {"mode": "skip"})
                render = await call("render_video", {
                    "mode": "auto", "aspect_ratio": "16:9", "output_max_dimension_px": 320,
                    "clip_compose_mode": "padding", "crf": 23,
                    "font_color": [255, 255, 255, 255], "font_size": 28,
                    "margin_bottom": 20, "stroke_width": 0,
                    "stroke_color": [0, 0, 0, 255],
                })

        rendered = Path(render["tool_excute_result"]["output_path"])
        assert rendered.is_file() and rendered.stat().st_size > 0
        rough_by_path = {str(Path(c["path"]).resolve()): c for c in rough_clips}
        retained = []
        for item in timeline:
            clip = rough_by_path[str(Path(item["source_path"]).resolve())]
            origin = int(clip["source_ref"]["start"])
            retained.append([origin + int(item["source_window"]["start"]),
                             origin + int(item["source_window"]["end"])])
        retained.sort()
        duration = int(prior["load_media"]["media"][0]["metadata"]["duration"])
        cuts, cursor = [], 0
        for start, end in retained:
            if start > cursor:
                cuts.append({"start_ms": cursor, "end_ms": start, "reason": "offline_test_gap"})
            cursor = max(cursor, end)
        if cursor < duration:
            cuts.append({"start_ms": cursor, "end_ms": duration, "reason": "offline_test_gap"})

        final_video = OUT / "output.mp4"
        shutil.copy2(rendered, final_video)
        (OUT / "cuts.json").write_text(json.dumps({"cuts": cuts}, indent=2) + "\n")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate,duration",
                                "-of", "json", str(final_video)], check=True, capture_output=True, text=True)
        streams = json.loads(probe.stdout)["streams"]
        video = next(x for x in streams if x["codec_type"] == "video")
        audio = next(x for x in streams if x["codec_type"] == "audio")
        assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p", video
        assert audio["codec_name"] == "aac", audio
        assert abs(float(video["duration"]) - float(audio["duration"])) <= .05, streams
        assert len(events) == len({x["tool_event_id"] for x in events}) == 5
        fake_count = sum(1 for _ in (OUT / "fake-model-events.jsonl").read_text().splitlines())
        report = {
            "verdict": "PASS", "continued_same_session": SESSION,
            "prior_actual_nodes": ["load_media", "split_shots", "local_asr"],
            "continued_tools": [x["tool"] for x in events],
            "tool_call_count": len(events), "fake_model_calls": fake_count,
            "fake_scope": "SpeechRoughCutNode llm.complete only",
            "asr_sentence_count": len(asr_infos[0]["asr_sentence_info"]),
            "asr_word_timestamp_count": len(asr_infos[0]["asr_timestamps"]),
            "timeline_retained_source_ranges_ms": retained,
            "cuts_derived_from_rendered_timeline_ms": cuts,
            "output": {"path": str(final_video), "bytes": final_video.stat().st_size,
                       "video": video, "audio": audio},
            "real_model_requests": 0,
        }
        (OUT / "tool-events.json").write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n")
        (OUT / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"verdict": "PASS", "tools": report["continued_tools"],
                          "fake_model_calls": report["fake_model_calls"], "output_bytes": final_video.stat().st_size}))
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
        asyncio.run(client_main())
