from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_openai.chat_models import base as chat_base
from pydantic import BaseModel

from agent_runtime.request_ledger import RequestLedger
import agent_runtime.request_ledger as request_ledger_module
from agent_runtime.vimax_adapters import _build_chat_model
from agent_runtime.session_index import SessionIndex
from agent_runtime.tools import ToolRegistry
from agent_runtime.vimax_adapters import build_vimax_adapter_specs
from agents.storyboard_artist import StoryboardArtist
from utils.robust_json_parser import StructuredOutputTruncated


def completion(content: str | None, *, finish: str = "stop",
               model: str = "qwen3.7-plus") -> httpx.Response:
    return httpx.Response(200, json={
        "id": "chatcmpl-offline-planning", "object": "chat.completion",
        "created": 1, "model": model,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": content},
                     "finish_reason": finish}],
        "usage": {"prompt_tokens": 22, "completion_tokens": 17,
                  "total_tokens": 39},
    })


def valid_storyboard() -> str:
    return json.dumps({"storyboard": [
        {"idx": i, "is_last": i == 7, "cam_idx": i % 4,
         "visual_desc": f"Shot {i + 1} subject and setting",
         "audio_desc": ""}
        for i in range(8)
    ]})


def patch_openai_transport(transport):
    original = chat_base.openai.AsyncOpenAI

    def factory(*args, **kwargs):
        kwargs["http_client"] = httpx.AsyncClient(transport=transport)
        return original(*args, **kwargs)

    return patch.object(chat_base.openai, "AsyncOpenAI", side_effect=factory)


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.ledger = RequestLedger(str(path))

    def events(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()
                if line.strip()]


class TruncatedStoryboardPipeline:
    def __init__(self, *, chat_model, **_kwargs):
        self.chat_model = chat_model

    async def plan_text_artifacts(self, **kwargs):
        return await StoryboardArtist(self.chat_model).design_storyboard(
            kwargs["script"], [], kwargs["user_requirement"])


class PlanningConfigurationTests(unittest.TestCase):
    def _model_call(self, body_text: str, *, finish: str = "stop"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger_file = Path(tmp.name) / "model-events.jsonl"
        captured = []
        transport = httpx.MockTransport(
            lambda request: captured.append(json.loads(request.content))
            or completion(body_text, finish=finish))
        env = {
            "VIMAX_LLM_API_KEY": "synthetic-offline-only",
            "VIMAX_LLM_MODEL": "qwen3.7-plus",
            "VIMAX_LLM_MODEL_PROVIDER": "openai",
            "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
            "VIMAX_BAILIAN_EVENT_LOG": str(ledger_file),
            "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
            "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
            "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192",
            "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS": "1800",
        }
        request_ledger_module._LEDGER = None
        with patch.dict("os.environ", env, clear=False), \
                patch_openai_transport(transport):
            model = _build_chat_model()
        return asyncio.run(model.ainvoke("offline planning prompt")), captured, Ledger(ledger_file)

    def test_actual_sdk_wire_has_thinking_disabled_and_8192_limit(self):
        text = valid_storyboard()
        result, requests, ledger = self._model_call(text)
        self.assertIn(text, result.content)
        self.assertEqual(len(requests), 1)
        # OpenAI SDK consumes LangChain's extra_body kwarg and flattens
        # provider-specific fields into the actual HTTP JSON object.
        self.assertIs(requests[0]["enable_thinking"], False)
        self.assertEqual(requests[0]["max_completion_tokens"], 8192)
        closes = [row for row in ledger.events() if row.get("kind") == "close"]
        self.assertEqual(closes[0].get("response_model"), "qwen3.7-plus")
        self.assertEqual(closes[0]["usage"]["total_tokens"], 39)

    def test_real_storyboard_artist_uses_strict_parser_and_accepts_native_schema(self):
        text = valid_storyboard()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger_path = Path(tmp.name) / "model-events.jsonl"
        captured = []
        transport = httpx.MockTransport(
            lambda request: captured.append(json.loads(request.content))
            or completion(text))
        env = {"VIMAX_LLM_API_KEY": "synthetic-offline-only",
               "VIMAX_LLM_MODEL": "qwen3.7-plus",
               "VIMAX_LLM_MODEL_PROVIDER": "openai",
               "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
               "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
               "VIMAX_BAILIAN_EVENT_LOG": str(ledger_path),
               "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
               "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
               "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192"}
        request_ledger_module._LEDGER = None
        with patch.dict("os.environ", env, clear=False), \
                patch_openai_transport(transport):
            artist = StoryboardArtist(_build_chat_model())
            rows = asyncio.run(artist.design_storyboard(
                "frozen eight-shot script", [], "exactly eight shots"))
        self.assertEqual([row.idx for row in rows], list(range(8)))
        self.assertTrue(rows[-1].is_last)
        self.assertEqual(len(captured), 1)
        rows_ledger = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        self.assertTrue(any(row.get("parse_status") == "success"
                            and row.get("request_id")
                            for row in rows_ledger if row.get("kind") == "diagnostic"))

    def test_length_is_correlated_and_storyboard_retry_sends_once(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger_path = Path(tmp.name) / "model-events.jsonl"
        captured = []
        transport = httpx.MockTransport(
            lambda request: captured.append(json.loads(request.content))
            or completion("", finish="length"))
        env = {"VIMAX_LLM_API_KEY": "synthetic-offline-only",
               "VIMAX_LLM_MODEL": "qwen3.7-plus",
               "VIMAX_LLM_MODEL_PROVIDER": "openai",
               "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
               "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
               "VIMAX_BAILIAN_EVENT_LOG": str(ledger_path),
               "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
               "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
               "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192"}
        request_ledger_module._LEDGER = None
        with patch.dict("os.environ", env, clear=False), \
                patch_openai_transport(transport):
            artist = StoryboardArtist(_build_chat_model())
            with self.assertRaises(StructuredOutputTruncated):
                asyncio.run(artist.design_storyboard("script", [], ""))
        self.assertEqual(len(captured), 1)
        rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        diagnostic = next(row for row in rows if row.get("parse_status") == "error")
        opened = next(row for row in rows if row.get("kind") == "open")
        self.assertEqual(diagnostic["request_id"], opened["request_id"])
        self.assertEqual(diagnostic["finish_reason"], "length")
        self.assertEqual(diagnostic["response_chars"], 0)
        self.assertEqual(diagnostic["parse_error_type"], "StructuredOutputTruncated")

    def test_truncation_request_id_reaches_native_planning_tool_result(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        script_path = root / "registered-script.txt"
        script_path.write_text("The frozen script.", encoding="utf-8")
        session_id = "planning-validation-02"
        index = SessionIndex(root)
        index.create(script="The frozen script.", planning_mode="script",
                     user_requirement="eight-shot task", style="documentary",
                     session_id=session_id)
        ledger_path = root / "model-events.jsonl"
        sends = []
        transport = httpx.MockTransport(
            lambda request: sends.append(json.loads(request.content))
            or completion("", finish="length"))
        env = {"VIMAX_LLM_API_KEY": "synthetic-offline-only",
               "VIMAX_LLM_MODEL": "qwen3.7-plus",
               "VIMAX_LLM_MODEL_PROVIDER": "openai",
               "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
               "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
               "VIMAX_BAILIAN_EVENT_LOG": str(ledger_path),
               "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
               "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
               "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192",
               "VIMAX_FIXED_SCRIPT_SESSION_ID": session_id,
               "VIMAX_FIXED_SCRIPT_PATH": str(script_path)}
        request_ledger_module._LEDGER = None
        with patch.dict("os.environ", env, clear=False), \
                patch_openai_transport(transport):
            model = _build_chat_model()
        from agent_runtime import vimax_adapters
        with patch.object(vimax_adapters, "_build_chat_model", return_value=model), \
                patch.object(vimax_adapters, "Script2VideoPipeline",
                             TruncatedStoryboardPipeline):
            registry = ToolRegistry(build_vimax_adapter_specs(root, index))
            result = asyncio.run(registry.execute(
                "vimax_narrative_planning", {"session_id": session_id}))
        events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        opened = next(row for row in events if row.get("kind") == "open")
        diagnostic = next(row for row in events
                          if row.get("parse_error_type") == "StructuredOutputTruncated")
        self.assertEqual(len(sends), 1)
        self.assertFalse(result.ok)
        self.assertTrue(result.metadata["fatal_stop"])
        self.assertEqual(result.metadata["request_id"], opened["request_id"])
        self.assertEqual(result.metadata["request_id"], diagnostic["request_id"])
        self.assertEqual(result.metadata["finish_reason"], "length")

    def test_empty_and_malformed_storyboard_responses_are_classified_with_ids(self):
        for content, expected_type in (("", "OutputParserException"),
                                       ("{bad", "OutputParserException")):
            with self.subTest(content=content):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                ledger_path = Path(tmp.name) / "model-events.jsonl"
                captured = []
                transport = httpx.MockTransport(
                    lambda request: captured.append(json.loads(request.content))
                    or completion(content))
                env = {"VIMAX_LLM_API_KEY": "synthetic-offline-only",
                       "VIMAX_LLM_MODEL": "qwen3.7-plus",
                       "VIMAX_LLM_MODEL_PROVIDER": "openai",
                       "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                       "VIMAX_NARRATIVE_MAX_TOKENS": "8192",
                       "VIMAX_BAILIAN_EVENT_LOG": str(ledger_path),
                       "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "40",
                       "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "40",
                       "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192"}
                request_ledger_module._LEDGER = None
                with patch.dict("os.environ", env, clear=False), \
                        patch_openai_transport(transport):
                    artist = StoryboardArtist(_build_chat_model())
                    with self.assertRaises(Exception):
                        asyncio.run(artist.design_storyboard("script", [], ""))
                rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                diagnostics = [row for row in rows if row.get("parse_status") == "error"]
                self.assertEqual(len(diagnostics), 2)  # existing finite parser retry
                opens = {row["request_id"] for row in rows if row.get("kind") == "open"}
                self.assertEqual({row["request_id"] for row in diagnostics}, opens)
                self.assertTrue(all(row["parse_error_type"] == expected_type
                                    for row in diagnostics))
                self.assertEqual(len(captured), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
