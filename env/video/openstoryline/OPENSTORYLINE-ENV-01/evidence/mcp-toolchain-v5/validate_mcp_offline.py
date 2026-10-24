import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

OUT = Path("/validation")
OUT.mkdir(parents=True, exist_ok=True)
os.environ["OPENSTORYLINE_TRACE_DIR"] = str(OUT)
os.environ["OPENSTORYLINE_MAX_LOGICAL_REQUESTS"] = "2"
os.environ["OPENSTORYLINE_MAX_TOKENS"] = "5"


async def main():
    from open_storyline.mcp.request_ledger import begin_request, finish_request
    from open_storyline.mcp.request_ledger import RequestRecorder

    events = OUT / "model-requests.jsonl"
    events.unlink(missing_ok=True)
    p = subprocess.Popen([sys.executable, "/opt/openstoryline/openstoryline_mcp_server.py"],
                         cwd="/workspace", stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if p.poll() is not None:
                raise RuntimeError(f"MCP server exited with {p.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", 8001), timeout=.2):
                    break
            except OSError:
                await asyncio.sleep(.2)
        else:
            raise TimeoutError("MCP server did not become ready")

        async with streamablehttp_client(
            "http://127.0.0.1:8001/mcp",
            headers={"X-Storyline-Session-Id": "offline-mcp-validation"},
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                schemas = {t.name: t.inputSchema for t in listing.tools}
                required = ["load_media", "split_shots", "local_asr", "speech_rough_cut"]
                assert all(name in schemas for name in required), sorted(schemas)
                assert "artifact_id" not in schemas["load_media"].get("properties", {})
                rows = []
                for name in required:
                    result = await client.call_tool(name, {"mode": "skip"})
                    if getattr(result, "structuredContent", None):
                        payload = result.structuredContent
                    elif result.content and getattr(result.content[0], "text", None):
                        try:
                            payload = json.loads(result.content[0].text)
                        except json.JSONDecodeError as exc:
                            raise AssertionError({"tool": name, "isError": result.isError,
                                                  "text": result.content[0].text}) from exc
                    else:
                        raise AssertionError({"tool": name, "isError": result.isError,
                                              "content": str(result.content)})
                    assert payload.get("artifact_id"), (name, payload)
                    assert payload.get("isError") is False, (name, payload)
                    rows.append({"tool": name, "artifact_id": payload["artifact_id"],
                                 "isError": payload["isError"]})

        os.environ["OPENSTORYLINE_MAX_TOKENS"] = "100"
        callback_run = uuid.uuid4()
        recorder = RequestRecorder("callback_smoke")
        recorder.on_chat_model_start({"kwargs": {"model": "mock-model"}}, [], callback_run)
        fake_message = type("Message", (), {
            "usage_metadata": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            "response_metadata": {"finish_reason": "stop"}})()
        fake_response = type("Response", (), {
            "generations": [[type("Generation", (), {"message": fake_message})()]],
            "llm_output": {}})()
        recorder.on_llm_end(fake_response, callback_run)
        callback_events = [json.loads(line) for line in events.read_text().splitlines()]
        callback_logged = (any(e.get("event") == "request_started" and
                               e.get("phase") == "callback_smoke" for e in callback_events)
                           and any(e.get("event") == "request_finished" and
                                   e.get("usage", {}).get("total_tokens") == 5
                                   for e in callback_events))
        assert callback_logged, "LangChain callback did not save request usage"
        events.unlink(missing_ok=True)
        os.environ.pop("OPENSTORYLINE_BUDGET_EXHAUSTED", None)
        os.environ["OPENSTORYLINE_MAX_LOGICAL_REQUESTS"] = "2"
        first = begin_request(phase="ledger_smoke", model="mock-model")
        finish_request(first, status="completed", usage={"input_tokens": 2,
                                                           "output_tokens": 2,
                                                           "total_tokens": 4})
        second = begin_request(phase="ledger_smoke", model="mock-model")
        finish_request(second, status="completed", usage={"total_tokens": 2})
        blocked = False
        try:
            begin_request(phase="ledger_smoke", model="mock-model")
        except RuntimeError as exc:
            blocked = "budget exhausted" in str(exc)
        assert blocked, "request-count cap did not stop the next model call"
        events.unlink(missing_ok=True)
        os.environ.pop("OPENSTORYLINE_BUDGET_EXHAUSTED", None)
        os.environ["OPENSTORYLINE_MAX_LOGICAL_REQUESTS"] = "3"
        os.environ["OPENSTORYLINE_MAX_TOKENS"] = "5"
        token_call = begin_request(phase="ledger_smoke", model="mock-model")
        finish_request(token_call, status="completed", usage={"total_tokens": 6})
        token_blocked = False
        try:
            begin_request(phase="ledger_smoke", model="mock-model")
        except RuntimeError as exc:
            token_blocked = "budget exhausted" in str(exc)
        assert token_blocked, "observed-token cap did not stop the next model call"
        doc = {"verdict": "PASS", "network_mode": "none",
               "credentials_used": False, "model_api_calls": 0,
               "mcp_tools": rows, "request_budget_blocked": blocked,
               "token_budget_blocked": token_blocked,
               "langchain_usage_callback_recorded": callback_logged,
               "request_record": str(events)}
        (OUT / "validation.json").write_text(json.dumps(doc, indent=2) + "\n")
        print(json.dumps(doc))
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=5)


asyncio.run(main())
