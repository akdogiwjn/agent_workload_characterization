from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.outputs import Generation
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, PrivateAttr

from agent_runtime.request_ledger import BudgetExceeded, DeadlineExceeded, LedgerWriteError, RequestLedger
from agent_runtime.vimax_adapters import _LedgerChatCallbackHandler
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser


class Payload(BaseModel):
    ok: bool


def _completion(content: str | None, *, status: int = 200) -> httpx.Response:
    if status != 200:
        return httpx.Response(status, json={"error": {"message": "offline fake failure"}})
    return httpx.Response(200, json={
        "id": "chatcmpl-offline", "object": "chat.completion", "created": 1,
        "model": "fake-model", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    })


class RecordingParser(TrailingCommaTolerantPydanticOutputParser):
    _seen: list = PrivateAttr(default_factory=list)

    def __init__(self):
        super().__init__(pydantic_object=Payload)

    def parse_result(self, result, *, partial=False):
        generation = result[0] if result else None
        from utils.robust_json_parser import _request_id_for_generation
        self._seen.append((getattr(generation, "text", None), _request_id_for_generation(generation)))
        return super().parse_result(result, partial=partial)


class BlockingTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.sent = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def handle_async_request(self, request):
        self.sent += 1
        self.entered.set()
        await self.release.wait()
        return _completion('{"ok":true}')


class LangChainCallbackProductionTests(unittest.TestCase):
    def _runtime(self, ledger, send_handler):
        handler = _LedgerChatCallbackHandler()
        transport = httpx.MockTransport(send_handler)
        model = ChatOpenAI(
            model="fake-model", api_key="synthetic-test-only", base_url="http://mock.invalid/v1",
            max_retries=0, callbacks=[handler],
            http_client=httpx.Client(transport=transport),
            http_async_client=httpx.AsyncClient(transport=transport),
        )
        return handler, model

    @staticmethod
    def _events(path):
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_cap_zero_and_deadline_stop_before_mock_http(self):
        for kind in ("cap", "deadline"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "ledger.jsonl"
                ledger = RequestLedger(str(path))
                if kind == "cap":
                    ledger._caps["llm_calls"] = 0
                    expected = BudgetExceeded
                else:
                    ledger._deadline = 0
                    ledger._t0 = 0
                    expected = DeadlineExceeded
                sent = []
                with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                    _handler, model = self._runtime(ledger, lambda request: sent.append(request) or _completion('{"ok":true}'))
                    with self.assertRaises(expected):
                        asyncio.run(model.ainvoke("offline gate"))
                self.assertEqual(sent, [])
                self.assertEqual(ledger.counts()["llm_calls"], 0)

    def test_concurrent_requests_atomically_reserve_one_remaining_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = RequestLedger(str(Path(tmp) / "ledger.jsonl"))
            ledger._caps["llm_calls"] = 1
            ledger._caps["llm_attempts"] = 1
            sent = []
            lock = threading.Lock()
            def transport(request):
                with lock:
                    sent.append(request)
                return _completion('{"ok":true}')
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, transport)
                async def run_pair():
                    return await asyncio.gather(
                        asyncio.to_thread(model.invoke, "parallel one"),
                        asyncio.to_thread(model.invoke, "parallel two"),
                        return_exceptions=True)
                results = asyncio.run(run_pair())
            self.assertEqual(len(sent), 1)
            self.assertEqual(sum(not isinstance(item, BaseException) for item in results), 1)
            self.assertEqual(sum(isinstance(item, BudgetExceeded) for item in results), 1)
            self.assertEqual(ledger.counts()["llm_calls"], 1)
            self.assertEqual(ledger.counts()["llm_attempts"], 1)

    def test_ledger_write_failure_fails_closed_before_mock_http(self):
        ledger = RequestLedger("/proc/vimax-callback-test/ledger.jsonl")
        sent = []
        with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
            _handler, model = self._runtime(ledger, lambda request: sent.append(request) or _completion('{"ok":true}'))
            with self.assertRaises(LedgerWriteError):
                asyncio.run(model.ainvoke("ledger must persist"))
        self.assertEqual(sent, [])
        self.assertEqual(ledger.counts()["llm_calls"], 1)  # fail-closed reservation is consumed
        self.assertEqual(ledger.failure_state()["ledger_write_failures"], 1)

    def test_unconfigured_ledger_path_fails_closed_before_mock_http(self):
        ledger = RequestLedger()
        sent = []
        with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
            _handler, model = self._runtime(ledger, lambda request: sent.append(request) or _completion('{"ok":true}'))
            with self.assertRaises(LedgerWriteError):
                asyncio.run(model.ainvoke("ledger path is required"))
        self.assertEqual(sent, [])
        self.assertEqual(ledger.counts()["llm_calls"], 0)
        self.assertEqual(ledger.failure_state()["ledger_write_failures"], 1)

    def test_normal_async_model_call_persists_open_close_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = RequestLedger(str(path))
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, lambda request: _completion('{"ok":true}'))
                result = asyncio.run(model.ainvoke("normal call"))
            self.assertIn('{"ok":true}', result.content)
            events = self._events(path)
            self.assertEqual([event["kind"] for event in events if event["kind"] in {"open", "close"}], ["open", "close"])
            self.assertEqual(events[1]["request_id"], events[0]["request_id"])
            self.assertEqual(events[1]["usage"]["completion_tokens"], 2)

    def test_async_malformed_json_parse_error_is_correlated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = RequestLedger(str(path))
            parser = RecordingParser()
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, lambda request: _completion('{"ok":'))
                with self.assertRaises(OutputParserException):
                    asyncio.run((model | parser).ainvoke("malformed response"))
            events = self._events(path)
            opened = next(event for event in events if event["kind"] == "open")
            diagnostic = next(event for event in events if event["kind"] == "diagnostic" and event.get("parse_status") == "error")
            self.assertEqual(parser._seen[0][1], opened["request_id"])
            self.assertEqual(diagnostic["request_id"], opened["request_id"])
            self.assertEqual(diagnostic["parse_error_type"], "OutputParserException")
            close = next(event for event in events if event["kind"] == "close")
            self.assertEqual(close["structured_response_text"], '{"ok":')

    def test_interleaved_success_and_parse_error_keep_request_ids_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = RequestLedger(str(path))
            parser = RecordingParser()
            def transport(request):
                body = json.loads(request.content)
                text = body["messages"][-1]["content"]
                return _completion('{"ok":' if "bad" in text else '{"ok":true}')
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, transport)
                chain = model | parser
                async def run_both():
                    return await asyncio.gather(
                        chain.ainvoke("bad request"), chain.ainvoke("good request"),
                        return_exceptions=True)
                results = asyncio.run(run_both())
            self.assertEqual(sum(isinstance(value, BaseException) for value in results), 1)
            bad_id = next(rid for text, rid in parser._seen if text == '{"ok":')
            good_id = next(rid for text, rid in parser._seen if text == '{"ok":true}')
            self.assertIsNotNone(bad_id)
            self.assertIsNotNone(good_id)
            self.assertNotEqual(bad_id, good_id)
            diagnostics = [event for event in self._events(path) if event["kind"] == "diagnostic"]
            by_status = {event["parse_status"]: event["request_id"] for event in diagnostics if "parse_status" in event}
            self.assertEqual(by_status, {"error": bad_id, "success": good_id})

    def test_failed_request_then_success_does_not_inherit_previous_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = RequestLedger(str(path))
            parser = RecordingParser()
            calls = 0
            def transport(_request):
                nonlocal calls
                calls += 1
                return _completion('{"ok":' if calls == 1 else '{"ok":true}')
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, transport)
                chain = model | parser
                with self.assertRaises(OutputParserException):
                    asyncio.run(chain.ainvoke("first"))
                self.assertTrue(asyncio.run(chain.ainvoke("second")).ok)
            self.assertNotEqual(parser._seen[0][1], parser._seen[1][1])
            diagnostics = [event for event in self._events(path) if event["kind"] == "diagnostic"]
            self.assertEqual([event["request_id"] for event in diagnostics], [parser._seen[0][1], parser._seen[1][1]])

    def test_missing_response_and_cancelled_call_remain_explainable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = RequestLedger(str(path))
            with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                _handler, model = self._runtime(ledger, lambda request: _completion(None, status=503))
                with self.assertRaises(Exception):
                    asyncio.run(model.ainvoke("server returned no completion"))
            events = self._events(path)
            opened = next(event for event in events if event["kind"] == "open")
            error = next(event for event in events if event["kind"] == "error")
            self.assertEqual(error["request_id"], opened["request_id"])
            self.assertTrue(error["error_type"].endswith("Error"), error)

            with tempfile.TemporaryDirectory() as cancel_tmp:
                cancel_path = Path(cancel_tmp) / "ledger.jsonl"
                cancel_ledger = RequestLedger(str(cancel_path))
                transport = BlockingTransport()
                with patch("agent_runtime.request_ledger.get_ledger", return_value=cancel_ledger):
                    handler = _LedgerChatCallbackHandler()
                    model = ChatOpenAI(
                        model="fake-model", api_key="synthetic-test-only",
                        base_url="http://mock.invalid/v1", max_retries=0,
                        callbacks=[handler],
                        http_async_client=httpx.AsyncClient(transport=transport))
                    async def cancel():
                        task = asyncio.create_task(model.ainvoke("cancel me"))
                        await asyncio.wait_for(transport.entered.wait(), timeout=1)
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    asyncio.run(cancel())
                cancel_events = self._events(cancel_path)
                cancel_open = next(event for event in cancel_events if event["kind"] == "open")
                self.assertEqual(transport.sent, 1)
                cancel_error = next(event for event in cancel_events if event.get("request_id") == cancel_open["request_id"] and event["kind"] == "error")
                self.assertTrue(cancel_error["right_censored"])
                self.assertTrue(cancel_error["cancellation_observed"])
                self.assertEqual(handler._request_ids, {})

    def test_real_agent_tool_route_stops_after_langchain_pre_send_gate(self):
        from agent_runtime.context_compactor import ContextCompactor
        from agent_runtime.llm import AssistantMessage
        from agent_runtime.loop import AgentLoop
        from agent_runtime.models import ToolCall
        from agent_runtime.session_index import SessionIndex
        from agent_runtime.tool_executor import ToolExecutor
        from agent_runtime.tools import build_builtin_registry
        from agent_runtime.vimax_adapters import build_vimax_adapter_specs
        from test_offline_regressions import _PromptBuilder, _collect

        class Outer:
            calls = 0
            async def complete(self, _messages, tools):
                self.calls += 1
                return AssistantMessage(tool_calls=[ToolCall(
                    id="plan", name="vimax_narrative_planning",
                    arguments={"session_id": "real-lc-session", "script": "One scene."})])

        for failure in ("budget", "ledger_write"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                ledger_path = ("/proc/vimax-agentloop-callback/ledger.jsonl"
                               if failure == "ledger_write"
                               else str(Path(tmp) / "ledger.jsonl"))
                ledger = RequestLedger(ledger_path)
                if failure == "budget":
                    ledger._caps["llm_calls"] = 0
                    expected_error = "BudgetExceeded"
                else:
                    expected_error = "LedgerWriteError"
                sent = []
                with patch("agent_runtime.request_ledger.get_ledger", return_value=ledger):
                    handler = _LedgerChatCallbackHandler()
                    transport = httpx.MockTransport(
                        lambda request: sent.append(request) or _completion('{"ok":true}'))
                    inner = ChatOpenAI(model="fake-model", api_key="synthetic-test-only",
                        base_url="http://mock.invalid/v1", max_retries=0, callbacks=[handler],
                        http_async_client=httpx.AsyncClient(transport=transport))
                    index = SessionIndex(tmp)
                    registry = build_builtin_registry(tmp, index, build_vimax_adapter_specs(tmp, index))
                    outer = Outer()
                    loop = AgentLoop(index, _PromptBuilder(), registry,
                        ToolExecutor(registry, index), outer, ContextCompactor(outer))
                    with patch("agent_runtime.vimax_adapters._build_chat_model", return_value=inner):
                        events = asyncio.run(_collect(loop.stream_events("bounded planning")))
                self.assertEqual(sent, [])
                self.assertEqual(outer.calls, 1)
                fatal = [event for event in events if event.get("type") == "tool_result"]
                self.assertTrue(fatal)
                self.assertTrue(fatal[0]["tool_result"]["metadata"]["fatal_stop"])
                self.assertEqual(fatal[0]["tool_result"]["metadata"]["error_type"], expected_error)


if __name__ == "__main__":
    unittest.main()
