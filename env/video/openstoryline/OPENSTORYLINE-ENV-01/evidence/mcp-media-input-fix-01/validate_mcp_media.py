import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

OUT = Path("/workspace/output")
OUT.mkdir(parents=True, exist_ok=True)


def payload_of(result):
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    if result.content and getattr(result.content[0], "text", None):
        return json.loads(result.content[0].text)
    raise AssertionError({"isError": result.isError, "content": str(result.content)})


async def main():
    from open_storyline.storage.agent_memory import ArtifactStore

    session_id = "media-input-fix-01c"
    store = ArtifactStore(OUT, session_id)
    p = subprocess.Popen([sys.executable, "/opt/openstoryline/openstoryline_mcp_server.py"],
                         cwd="/workspace", stdout=subprocess.DEVNULL,
                         stderr=open(OUT / "mcp-server.log", "w"), start_new_session=True)
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if p.poll() is not None:
                raise RuntimeError(f"MCP exited: {p.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", 8001), timeout=.2):
                    break
            except OSError:
                await asyncio.sleep(.2)
        else:
            raise TimeoutError("MCP did not become ready")

        async with streamablehttp_client(
            "http://127.0.0.1:8001/mcp",
            headers={"X-Storyline-Session-Id": session_id},
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                schemas = {tool.name: tool.inputSchema for tool in listing.tools}
                assert schemas["load_media"].get("properties", {}).keys() == {"mode"}
                assert "artifact_id" not in schemas["load_media"].get("properties", {})
                results = []
                for name, args in (("load_media", {"mode": "auto"}),
                                   ("split_shots", {"mode": "skip"}),
                                   ("local_asr", {"mode": "auto"})):
                    result = await client.call_tool(name, args)
                    data = payload_of(result)
                    assert not result.isError and data.get("isError") is False, (name, data)
                    results.append({"tool": name, "artifact_id": data.get("artifact_id"),
                                    "summary": data.get("summary"),
                                    "tool_execute_result": data.get("tool_excute_result")})
                    if name == "load_media":
                        media = data.get("tool_excute_result", {}).get("media", [])
                        assert len(media) == 1, media
                        assert media[0]["metadata"]["duration"] == 6000, media[0]
                    # Reproduce LangChain's save_media_content_after interceptor:
                    # following nodes resolve prerequisites from this session store.
                    store.save_result(session_id, name, data, Path("/workspace/input"))
        report = {"verdict": "PASS", "network": "none", "credentials": False,
                  "model_api_calls": 0, "tools": results}
        (OUT / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"verdict": "PASS", "tools": [r["tool"] for r in results]}))
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=5)


asyncio.run(main())
