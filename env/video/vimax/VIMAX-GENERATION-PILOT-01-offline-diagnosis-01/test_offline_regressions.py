"""Offline regressions against the production ViMax AgentLoop and tool registry.

All model and pipeline boundaries are faked. This module never reads API
credentials or opens a network connection.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_runtime.context_compactor import ContextCompactor
from agent_runtime.loop import AgentLoop
from agent_runtime.llm import AssistantMessage
from agent_runtime.models import ToolCall
from agent_runtime.prompts import PromptBuilder
from agent_runtime.session_index import SessionIndex
from agent_runtime.tool_executor import ToolExecutor
from agent_runtime.tools import ToolRegistry, ToolSpec, build_builtin_registry
from agent_runtime.request_ledger import BudgetExceeded
from agents.camera_image_generator import CameraImageGenerator, CameraTreeResponse
from agents.storyboard_artist import StoryboardArtist
from interfaces import Camera, ShotBriefDescription
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser
from langchain_core.exceptions import OutputParserException
from langchain_core.outputs import Generation
from tenacity import RetryError
from agent_runtime.vimax_adapters import build_vimax_adapter_specs, preflight_render_capability
from pipelines.idea2video_pipeline import Idea2VideoPipeline
from pipelines.script2video_pipeline import Script2VideoPipeline


class _Prompt:
    id = "request.user"
    title = "User request"
    body = "offline test"


class _PromptBuilder:
    def build_parts(self, _request):
        return [_Prompt()]

    def trace(self, _parts):
        return {"offline": True}


class _FakeOuterLLM:
    def __init__(self):
        self.calls = 0

    async def complete(self, _messages, tools):
        self.calls += 1
        if self.calls in (1, 3):
            args = {"session_id": "fixed-script-session"}
            if self.calls == 1:
                args["script"] = "Shot 1: sunrise roof."
        elif self.calls == 2:
            return AssistantMessage(text="Continue in a later turn.")
        else:
            # Mirrors the saved trajectory: the follow-up omitted script and
            # other source fields while keeping the session id.
            raise AssertionError("the Agent must stop after the repeated failure")
        return AssistantMessage(tool_calls=[ToolCall(
            id=f"call-{self.calls}", name="vimax_narrative_planning", arguments=args
        )])


class OfflineProductionEntryTests(unittest.TestCase):
    def test_script_mode_is_persisted_and_identical_failure_stops_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_index = SessionIndex(root)
            specs = build_vimax_adapter_specs(root, session_index)
            registry = build_builtin_registry(root, session_index, specs)
            llm = _FakeOuterLLM()
            loop = AgentLoop(
                session_index, _PromptBuilder(), registry,
                ToolExecutor(registry, session_index), llm,
                ContextCompactor(llm),
            )

            async def fail_plan(self, **_kwargs):
                raise ValueError("Invalid json output: ")

            with patch("agent_runtime.vimax_adapters._build_chat_model", return_value=object()), \
                 patch.object(Script2VideoPipeline, "plan_text_artifacts", fail_plan), \
                 patch.object(Idea2VideoPipeline, "develop_story", side_effect=AssertionError("script mode changed to idea mode")):
                first_turn = asyncio.run(_collect(loop.stream_events("offline planning test")))
                events = asyncio.run(_collect(loop.stream_events("continue planning in same session")))

            self.assertEqual(llm.calls, 3)
            self.assertTrue(any(e.get("type") == "done" and e.get("assistant") == "Continue in a later turn." for e in first_turn))
            self.assertTrue(any(e.get("type") == "error" and e.get("metadata", {}).get("error_type") == "bounded_recovery_stop" for e in events))
            session = session_index.get("fixed-script-session")
            self.assertEqual(session["planning_mode"], "script")
            self.assertEqual(session["script"], "Shot 1: sunrise roof.")
            self.assertEqual(session["idea"], "")

    def test_write_json_rejects_string_and_run_shell_is_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_index = SessionIndex(root)
            registry = build_builtin_registry(root, session_index, build_vimax_adapter_specs(root, session_index))
            normalized, error = registry.validate_arguments("write_json", {"path": "x.json", "data": "{\"x\":1}"})
            self.assertIsNone(normalized)
            self.assertIn("must be dict, list", error)

            old = os.environ.pop("VIMAX_ENABLE_RUN_SHELL", None)
            try:
                result = asyncio.run(registry.execute("run_shell", {"command": "true"}))
            finally:
                if old is not None:
                    os.environ["VIMAX_ENABLE_RUN_SHELL"] = old
            self.assertFalse(result.ok)
            self.assertEqual(result.metadata.get("error_type"), "disabled")
            self.assertIn("disabled by default", result.content)

    def test_incompatible_render_plan_is_rejected_before_generator_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = SessionIndex(root)
            session = index.create(script="Shot 1", planning_mode="script", session_id="preflight-session")
            work = index.working_dir(session["session_id"]) / "script2video"
            (work / "script.txt").write_text("Shot 1", encoding="utf-8")
            (work / "characters.json").write_text("[]", encoding="utf-8")
            (work / "storyboard.json").write_text('[{"idx":0}]', encoding="utf-8")
            (work / "shots/0").mkdir(parents=True)
            (work / "shots/0/shot_description.json").write_text('{"idx":0,"variation_type":"medium"}', encoding="utf-8")
            (work / "camera_tree.json").write_text('[{"idx":0,"active_shot_idxs":[0]}]', encoding="utf-8")
            preflight_ok, preflight_reasons = preflight_render_capability(work)
            self.assertFalse(preflight_ok, preflight_reasons)
            registry = build_builtin_registry(root, index, build_vimax_adapter_specs(root, index))
            old_capability = os.environ.get("VIMAX_BAILIAN_VIDEO_FIRST_LAST_SUPPORTED")
            os.environ["VIMAX_BAILIAN_VIDEO_FIRST_LAST_SUPPORTED"] = "false"
            try:
                with patch("agent_runtime.vimax_adapters._build_chat_model", return_value=object()), \
                     patch("agent_runtime.vimax_adapters._build_image_generator", return_value=object()), \
                     patch("agent_runtime.vimax_adapters._build_video_generator", return_value=object()):
                    result = asyncio.run(registry.execute("vimax_render_video", {"session_id": session["session_id"]}))
            finally:
                if old_capability is None:
                    os.environ.pop("VIMAX_BAILIAN_VIDEO_FIRST_LAST_SUPPORTED", None)
                else:
                    os.environ["VIMAX_BAILIAN_VIDEO_FIRST_LAST_SUPPORTED"] = old_capability
            self.assertFalse(result.ok)
            self.assertEqual(result.metadata.get("error_type"), "capability_preflight_failed", result.content)
            self.assertEqual(result.metadata.get("image_or_video_requests_sent"), 0)

    def test_budget_error_is_nonrecoverable_at_tool_boundary(self):
        async def fail(_args):
            raise BudgetExceeded("llm_calls", 2, "already_sent=2")

        registry = ToolRegistry([ToolSpec("budget_probe", "", fail, schema={})])
        result = asyncio.run(registry.execute("budget_probe", {}))
        self.assertFalse(result.ok)
        self.assertTrue(result.metadata.get("fatal_stop"))
        self.assertEqual(result.metadata.get("error_type"), "BudgetExceeded")

        class _LLM:
            def __init__(self):
                self.calls = 0

            async def complete(self, _messages, tools):
                self.calls += 1
                if self.calls > 1:
                    raise AssertionError("budget failure must stop before another model request")
                return AssistantMessage(tool_calls=[ToolCall(id="budget-1", name="budget_probe", arguments={})])

        with tempfile.TemporaryDirectory() as tmp:
            index = SessionIndex(tmp)
            llm = _LLM()
            loop = AgentLoop(index, _PromptBuilder(), registry, ToolExecutor(registry, index), llm, ContextCompactor(llm))
            events = asyncio.run(_collect(loop.stream_events("budget stop")))
        self.assertEqual(llm.calls, 1)
        self.assertTrue(any(event.get("type") == "error" and event.get("metadata", {}).get("error_type") == "bounded_recovery_stop" for event in events))

    def test_successful_staged_tool_flow_can_continue(self):
        class _LLM:
            def __init__(self):
                self.calls = 0

            async def complete(self, _messages, tools):
                self.calls += 1
                if self.calls == 1:
                    return AssistantMessage(tool_calls=[ToolCall(id="ok-1", name="stage", arguments={})])
                return AssistantMessage(text="done")

        async def success(_args):
            from agent_runtime.models import ToolResult
            return ToolResult("stage", True, "stage complete")

        with tempfile.TemporaryDirectory() as tmp:
            index = SessionIndex(tmp)
            registry = ToolRegistry([ToolSpec("stage", "", success, schema={})])
            llm = _LLM()
            loop = AgentLoop(index, _PromptBuilder(), registry, ToolExecutor(registry, index), llm, ContextCompactor(llm))
            events = asyncio.run(_collect(loop.stream_events("continue successful stages")))
        self.assertEqual(llm.calls, 2)
        self.assertTrue(any(event.get("type") == "done" and event.get("assistant") == "done" for event in events))

    def test_camera_tree_cardinality_is_camera_count_and_mismatch_is_not_filled(self):
        class _Chain:
            async def ainvoke(self, _messages):
                # Synthetic one-entry result based on the saved count mismatch;
                # the historical raw model content was not saved.
                return CameraTreeResponse(camera_parent_items=[None])

        class _Chat:
            def __or__(self, _parser):
                return _Chain()

        cameras = [Camera(idx=i, active_shot_idxs=[i]) for i in range(4)]
        shots = [ShotBriefDescription(idx=i, is_last=i == 3, cam_idx=i, visual_desc=f"shot {i}", audio_desc="") for i in range(4)]
        generator = CameraImageGenerator(_Chat(), None, None)
        with self.assertRaisesRegex(ValueError, "expected 4, got 1"):
            asyncio.run(generator.construct_camera_tree(cameras, shots))

    def test_empty_and_truncated_structured_output_are_rejected(self):
        parser = TrailingCommaTolerantPydanticOutputParser(pydantic_object=CameraTreeResponse)
        for candidate in ("", '{"camera_parent_items": ['):
            with self.assertRaises(Exception):
                parser.parse(candidate)
        with self.assertRaisesRegex(OutputParserException, "truncated"):
            parser.parse_result([Generation(text='{"camera_parent_items": [null]}', generation_info={"finish_reason": "length"})])
        parsed = parser.parse('```json\n{"camera_parent_items": [null,],}\n```')
        self.assertEqual(parsed.camera_parent_items, [None])

    def test_storyboard_structured_failure_is_retried_once_then_stops(self):
        class _Chain:
            def __init__(self):
                self.calls = 0

            async def ainvoke(self, _messages):
                self.calls += 1
                raise OutputParserException("synthetic malformed structured response")

        class _Chat:
            def __init__(self):
                self.chain = _Chain()

            def __or__(self, _parser):
                return self.chain

        chat = _Chat()
        artist = StoryboardArtist(chat)
        with self.assertRaises(RetryError):
            asyncio.run(artist.design_storyboard("script", [], None))
        self.assertEqual(chat.chain.calls, 2)


async def _collect(events):
    return [event async for event in events]


if __name__ == "__main__":
    unittest.main()
