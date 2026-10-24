from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.context_compactor import ContextCompactor
from agent_runtime.llm import AssistantMessage
from agent_runtime.loop import AgentLoop
from agent_runtime.models import ToolCall, ToolResult
from agent_runtime.request_ledger import BudgetExceeded, DeadlineExceeded, RequestLedger
from agent_runtime.session_index import SessionIndex
from agent_runtime.tool_executor import ToolExecutor
from agent_runtime.tools import build_builtin_registry
from agent_runtime.vimax_adapters import build_vimax_adapter_specs
from agents.storyboard_artist import StoryboardArtist
from langchain_core.exceptions import OutputParserException
from langchain_core.outputs import Generation
from pipelines.script2video_pipeline import Script2VideoPipeline
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser
from pydantic import BaseModel, create_model

from test_offline_regressions import _PromptBuilder, _collect


class _ScriptedLLM:
    def __init__(self, calls):
        self.calls = calls
        self.count = 0

    async def complete(self, _messages, tools):
        self.count += 1
        if self.count > len(self.calls):
            raise AssertionError("unexpected additional model request")
        return self.calls[self.count - 1]


class ViMaxOfflineDiagnosticTests(unittest.TestCase):
    def _make_loop(self, root, llm):
        index = SessionIndex(root)
        registry = build_builtin_registry(root, index, build_vimax_adapter_specs(root, index))
        loop = AgentLoop(index, _PromptBuilder(), registry, ToolExecutor(registry, index), llm, ContextCompactor(llm))
        return index, loop

    def test_budget_and_deadline_propagate_from_production_planning_chain_and_stop(self):
        for exception in (BudgetExceeded("llm_calls", 1), DeadlineExceeded("offline deadline")):
            with self.subTest(error=type(exception).__name__), tempfile.TemporaryDirectory() as tmp:
                first = AssistantMessage(tool_calls=[ToolCall(
                    id="plan-1", name="vimax_narrative_planning",
                    arguments={"session_id": "fixed-session", "script": "Shot 1"},
                )])
                llm = _ScriptedLLM([first])
                _index, loop = self._make_loop(tmp, llm)
                sends = {"count": 0}
                ledger = RequestLedger()
                if isinstance(exception, BudgetExceeded):
                    ledger._caps["llm_calls"] = 0

                async def pipeline_plan(_self, **_kwargs):
                    # This is the inner send boundary: the pre-send gate runs
                    # before the fake transport counter can move.
                    try:
                        if isinstance(exception, BudgetExceeded):
                            ledger.guard("llm_calls")
                        raise exception
                    except (BudgetExceeded, DeadlineExceeded) as control_error:
                        raise RuntimeError("pipeline wrapper") from control_error
                    sends["count"] += 1

                with patch("agent_runtime.vimax_adapters._build_chat_model", return_value=object()), \
                     patch.object(Script2VideoPipeline, "plan_text_artifacts", pipeline_plan):
                    events = asyncio.run(_collect(loop.stream_events("offline budget propagation")))

                self.assertEqual(llm.count, 1, repr(events))
                self.assertEqual(sends["count"], 0)
                stop = [event for event in events if event.get("type") == "error"]
                self.assertTrue(stop)
                result = next(event["tool_result"] for event in events if event.get("type") == "tool_result")
                self.assertTrue(result["metadata"]["fatal_stop"])
                self.assertEqual(result["metadata"]["error_type"], type(exception).__name__)

    def test_actual_storyboard_tenacity_does_not_retry_budget_error(self):
        class Chain:
            calls = 0
            async def ainvoke(self, _messages):
                self.calls += 1
                raise BudgetExceeded("llm_calls", 1)

        class Chat:
            def __init__(self):
                self.chain = Chain()
            def __or__(self, _parser):
                return self.chain

        chat = Chat()
        with self.assertRaises(BudgetExceeded):
            asyncio.run(StoryboardArtist(chat).design_storyboard("script", [], None))
        self.assertEqual(chat.chain.calls, 1)

    def test_actual_storyboard_tenacity_does_not_retry_cancellation(self):
        class Chain:
            calls = 0
            async def ainvoke(self, _messages):
                self.calls += 1
                raise asyncio.CancelledError("offline cancellation")

        class Chat:
            def __init__(self): self.chain = Chain()
            def __or__(self, _parser): return self.chain

        chat = Chat()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(StoryboardArtist(chat).design_storyboard("script", [], None))
        self.assertEqual(chat.chain.calls, 1)

    def test_partial_revision_does_not_reset_same_stage_failure_limit(self):
        plan = lambda ident: AssistantMessage(tool_calls=[ToolCall(
            id=ident, name="vimax_narrative_planning",
            arguments={"session_id": "fixed-session", "script": "Shot 1"},
        )])
        revise = AssistantMessage(tool_calls=[ToolCall(
            id="revise", name="vimax_narrative_planning",
            arguments={"session_id": "fixed-session", "revision_target": "script2video/script.txt", "revision_instruction": "minor edit"},
        )])
        llm = _ScriptedLLM([plan("plan-1"), revise, plan("plan-2")])
        with tempfile.TemporaryDirectory() as tmp:
            _index, loop = self._make_loop(tmp, llm)
            async def bad_plan(**_kwargs):
                raise OutputParserException("same structured failure")
            async def partial_revision(*_args, **_kwargs):
                return ToolResult("vimax_narrative_planning", True, "partial", {"session_id": "fixed-session", "ready_for_render": False})
            with patch("agent_runtime.vimax_adapters._build_chat_model", return_value=object()), \
                 patch.object(Script2VideoPipeline, "plan_text_artifacts", bad_plan), \
                 patch("agent_runtime.vimax_adapters.ViMaxAdapters._revise_narrative_artifact", partial_revision):
                events = asyncio.run(_collect(loop.stream_events("bounded recovery")))
        self.assertEqual(llm.count, 3)
        self.assertTrue(any(event.get("type") == "error" and event.get("metadata", {}).get("error_type") == "bounded_recovery_stop" for event in events))

    def test_json_parser_preserves_string_content_and_repairs_only_real_trailing_commas(self):
        class Payload(BaseModel):
            nested: dict
            values: list
        parser = TrailingCommaTolerantPydanticOutputParser(pydantic_object=Payload)
        expected = {"nested": {"a": "x,}", "b": "y,]", "q": "quote: " + chr(34) + " and slash " + chr(92)}, "values": [1, {"z": 2}]}
        import json
        raw = json.dumps(expected)
        self.assertEqual(parser.parse(raw).model_dump(), expected)
        repaired = parser.parse('{"nested":{"a":"ok",},"values":[1,2,],}')
        self.assertEqual(repaired.model_dump(), {"nested": {"a": "ok"}, "values": [1, 2]})
        for raw_bad in ("", '{"nested": [', '{"values":[]}'):
            with self.assertRaises(OutputParserException):
                parser.parse(raw_bad)
        with self.assertRaises(OutputParserException):
            parser.parse('{"nested":{},"values":"wrong"}')
        with self.assertRaises(OutputParserException):
            parser.parse_result([Generation(text='{"nested":{},"values":[]}', generation_info={"finish_reason": "length"})])

    def test_callback_saves_correlated_bounded_response_metadata_and_redacts_secrets(self):
        class Ledger:
            def __init__(self): self.events = []
            def reserve_and_open(self, *_args, **_kwargs): return "req-offline-1"
            def close(self, request_id, status, **fields): self.events.append((request_id, status, fields))
            def observe_usage(self, *_args, **_kwargs): pass
            def diagnostic(self, request_id, **fields): self.events.append((request_id, "diagnostic", fields))

        ledger = Ledger()
        with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
            from agent_runtime.vimax_adapters import _LedgerChatCallbackHandler
            handler = _LedgerChatCallbackHandler()
            handler.on_chat_model_start({}, ["prompt"], run_id="offline-run")
            response = type("Response", (), {
                "llm_output": {"token_usage": {"prompt_tokens": 5, "completion_tokens": 2}},
                "generations": [[Generation(text='{"api_key":"do-not-save","ok":true}', generation_info={"finish_reason": "stop"})]],
            })()
            handler.on_llm_end(response, run_id="offline-run")
            parser = TrailingCommaTolerantPydanticOutputParser(pydantic_object=create_model("Payload", ok=(bool, ...)))
            with self.assertRaises(OutputParserException):
                parser.parse_result([Generation(text="{broken", generation_info={"vimax_request_id": "req-offline-1"})])
        request_id, status, fields = ledger.events[0]
        self.assertEqual(request_id, "req-offline-1")
        self.assertEqual(fields["finish_reason"], "stop")
        self.assertIn("<redacted>", fields["structured_response_text"])
        self.assertNotIn("do-not-save", fields["structured_response_text"])
        self.assertFalse(fields["structured_response_text_truncated"])
        diagnostic_id, kind, diagnostic = ledger.events[1]
        self.assertEqual(diagnostic_id, request_id)
        self.assertEqual(kind, "diagnostic")
        self.assertEqual(diagnostic["parse_error_type"], "OutputParserException")
        from agent_runtime.vimax_adapters import _bounded_safe_response_text
        _saved, truncated = _bounded_safe_response_text("x" * 20, limit=10)
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
