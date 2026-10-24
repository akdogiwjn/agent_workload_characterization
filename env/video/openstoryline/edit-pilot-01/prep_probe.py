"""Bailian Chat Completions chain verification through the REAL OpenStoryline
path (<=6 logical requests)."""
import asyncio, json, os, sys
sys.path.insert(0, "/opt/openstoryline/src")
sys.path.insert(0, "/opt/openstoryline")
os.environ.setdefault("OPENSTORYLINE_CONFIG", "/opt/openstoryline/config.toml")
REQUESTS = {"count": 0, "detail": []}

async def main():
    out = {}
    from open_storyline.agent import build_agent
    from open_storyline.config import load_settings
    from open_storyline.storage.agent_memory import ArtifactStore
    cfg = load_settings("/opt/openstoryline/config.toml")
    secret = os.environ["DASHSCOPE_API_KEY"]
    store = ArtifactStore("/workspace/output", "prep")
    import subprocess, socket, time as _t
    env = os.environ.copy(); env.pop("DASHSCOPE_API_KEY", None)
    log = open("/workspace/output/prep_mcp.log", "w")
    mcp = subprocess.Popen([sys.executable, "/opt/openstoryline/openstoryline_mcp_server.py"],
                           cwd="/workspace", env=env, stdout=log, stderr=subprocess.STDOUT,
                           start_new_session=True)
    mcp_ok = False
    deadline = _t.monotonic() + 25
    while _t.monotonic() < deadline:
        if mcp.poll() is not None:
            break
        try:
            with socket.create_connection(("127.0.0.1", 8001), timeout=0.3):
                mcp_ok = True; break
        except OSError:
            await asyncio.sleep(0.2)
    if not mcp_ok:
        out = {"verdict": "FAIL_mcp_not_started",
               "mcp_log_tail": log.read()[-500:]}
        json.dump(out, open("/workspace/output/prep_probe.json", "w"), indent=1)
        print(json.dumps(out)); return 1
    agent, nm = await build_agent(
        cfg, "prep", store,
        llm_override={"model": "qwen3.7-plus",
                      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                      "api_key": secret, "max_retries": 0, "timeout": 60.0},
        vlm_override={"model": "qwen3.7-plus",
                      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                      "api_key": secret, "max_retries": 0, "timeout": 60.0})
    REQUESTS["count"] += 2; REQUESTS["detail"] += ["build_agent_llm", "build_agent_vlm"]
    out["build_agent"] = {"ok": True}
    print("build_agent OK (2 validation requests)")

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, ToolMessage
    @tool
    def probe_tool(value: str) -> str:
        """Echo the value back with a marker."""
        return f"probe_ok:{value}"
    llm = ChatOpenAI(model="qwen3.7-plus",
                     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                     api_key=secret, max_retries=0, timeout=60.0,
                     max_tokens=32768)
    resp1 = await llm.bind_tools([probe_tool]).ainvoke(
        [HumanMessage(content="Call probe_tool with value 'chain'. Reply with the tool result only.")])
    REQUESTS["count"] += 1; REQUESTS["detail"].append("toolcall_step1")
    tool_calls = resp1.tool_calls or []
    out["tool_call_received"] = {"ok": bool(tool_calls),
                                 "name": tool_calls[0]["name"] if tool_calls else None,
                                 "args": tool_calls[0]["args"] if tool_calls else None}
    if tool_calls:
        result = probe_tool.invoke(tool_calls[0]["args"])
        resp2 = await llm.bind_tools([probe_tool]).ainvoke(
            [HumanMessage(content="Call probe_tool with value 'chain'. Reply with the tool result only."),
             resp1, ToolMessage(content=str(result), tool_call_id=tool_calls[0]["id"])])
        REQUESTS["count"] += 1; REQUESTS["detail"].append("toolcall_step2")
        out["tool_result_roundtrip"] = {"ok": "probe_ok:chain" in (resp2.content or ""),
                                        "final_excerpt": (resp2.content or "")[:120]}
        print("tool round trip:", out["tool_result_roundtrip"])

    out["mcp_server"] = {"started": True}
    if True:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        try:
            async with streamablehttp_client("http://127.0.0.1:8001/mcp") as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = await s.list_tools()
                    names = sorted(t.name for t in tools.tools)
                    out["mcp_server"]["tools"] = names
                    out["mcp_server"]["asr_adapter_present"] = "local_asr" in names
        except Exception as e:
            out["mcp_server"]["list_error"] = f"{type(e).__name__}: {e}"
    try:
        os.killpg(mcp.pid, 15); mcp.wait(5)
    except Exception:
        try: os.killpg(mcp.pid, 9)
        except Exception: pass
    log.close()
    print("mcp tools:", out["mcp_server"].get("tools"))

    out["requests_total"] = REQUESTS["count"]
    out["request_detail"] = REQUESTS["detail"]
    out["verdict"] = ("PASS" if out.get("tool_call_received", {}).get("ok")
                      and out.get("tool_result_roundtrip", {}).get("ok")
                      and out["mcp_server"].get("asr_adapter_present") else "FAIL")
    out["vlm_usage_note"] = ("this task does NOT use VLM image input; the VLM init "
                             "validation request is text-only and counted above")
    json.dump(out, open("/workspace/output/prep_probe.json", "w"), indent=1, default=str)
    print("VERDICT:", out["verdict"], "| requests:", REQUESTS["count"])
    return 0 if out["verdict"] == "PASS" else 1

asyncio.run(main())
