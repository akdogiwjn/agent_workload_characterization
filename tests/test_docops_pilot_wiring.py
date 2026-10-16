#!/usr/bin/env python3
"""Directed wiring tests for the DocOps pilot: DocumentToolsAgent orchestration
with a FAKE model transport and FAKE environment (no model calls, no Docker).

Covers: event production (transcript + llm_call logs), call/result association
via the tool protocol, usage accounting into AgentContext, normal finish,
invalid-JSON recovery path, and archive-into-temp-dir isolation.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'references' / 'repos' / 'DocOps' / 'harnesses'))
sys.path.insert(0, str(ROOT / '.venvs' / 'docops-pilot-01' / 'lib' / 'python3.12' / 'site-packages'))

from document_tools_agent import DocumentToolsAgent  # noqa: E402
from harbor.environments.base import ExecResult  # noqa: E402
from harbor.llms.base import LLMResponse  # noqa: E402
from harbor.models.agent.context import AgentContext  # noqa: E402
from harbor.models.metric.usage_info import UsageInfo  # noqa: E402


class FakeLLM:
    """Deterministic transport: replays scripted responses, one per call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.model_name = 'fake-model'

    async def call(self, *, prompt, message_history, logging_path=None,
                   extra_headers=None, extra_body=None, max_tokens=None,
                   stop=None, **kw):
        self.calls.append({'prompt': prompt, 'history_len': len(message_history),
                           'logging_path': str(logging_path) if logging_path else None,
                           'max_tokens': max_tokens, 'stop': stop})
        content, usage = self.script.pop(0)
        if logging_path is not None:
            Path(logging_path).write_text(json.dumps(
                {'fake': True, 'content': content}, ensure_ascii=False))
        return LLMResponse(content=content, model_name=self.model_name, usage=usage)


class FakeEnvironment:
    """Records exec commands; returns the last JSON line as tool output."""

    def __init__(self, tool_outputs):
        self.tool_outputs = tool_outputs
        self.commands = []

    async def exec(self, command, timeout=None, **kw):
        self.commands.append(command)
        out = self.tool_outputs.get(command, {'ok': True, 'note': 'default'})
        return ExecResult(stdout=json.dumps(out), stderr='', return_code=0)


def make_agent(tmp, script):
    agent = DocumentToolsAgent(logs_dir=Path(tmp))
    agent.llm = FakeLLM(script)
    agent.max_steps = 6
    return agent


META = {'ok': True, 'metadata': {
    'task_id': 'word_001', 'input_path': '/root/in.docx',
    'output_path': '/root/submission/out.docx'}}
INSPECT = {'ok': True, 'paragraphs': 5, 'tables': 0, 'type': 'docx'}
COPY = {'ok': True}


def test_normal_finish_with_events_and_usage():
    with tempfile.TemporaryDirectory() as tmp:
        script = [
            ('{"thought":"copy","action":"call_tool","tool_name":"copy_file",'
             '"arguments":{"src":"/root/in.docx","dest":"/root/submission/out.docx"},"final_message":null}',
             UsageInfo(prompt_tokens=100, completion_tokens=10, cache_tokens=20, cost_usd=0.0)),
            ('{"thought":"done","action":"finish","tool_name":null,'
             '"arguments":{},"final_message":"edited"}',
             UsageInfo(prompt_tokens=110, completion_tokens=5, cache_tokens=0, cost_usd=0.0)),
        ]
        agent = make_agent(tmp, script)
        env = FakeEnvironment({
            "python3 /root/document_tools_runtime.py --tool get_task_metadata --args-json '{}'": META,
            "python3 /root/document_tools_runtime.py --tool inspect_document --args-json "
            + "'{\"path\": \"/root/in.docx\"}'": INSPECT,
        })
        ctx = AgentContext()
        asyncio.run(agent.run('do the task', env, AgentContext.__construct__ if False else ctx))
        # transcript + llm logs written into temp dir (archive isolation)
        tr = Path(tmp) / 'document-tools-agent.txt'
        assert tr.exists() and 'STEP 1' in tr.read_text() and 'FINAL' in tr.read_text()
        assert 'copy_file' in tr.read_text() and 'finish' in tr.read_text()
        for n in (1, 2):
            assert (Path(tmp) / f'llm_call_{n}.json').exists()
        # tool call/result association: bootstrap(2) + scripted copy(1) commands
        assert len(env.commands) == 3
        assert 'get_task_metadata' in env.commands[0]
        assert 'inspect_document' in env.commands[1]
        assert 'copy_file' in env.commands[2]
        # usage accounting into context
        assert ctx.n_input_tokens == 210 and ctx.n_output_tokens == 15 and ctx.n_cache_tokens == 20
        # llm call parameters recorded (max_tokens/stop passed through)
        assert agent.llm.calls[0]['max_tokens'] == agent.max_tokens


def test_invalid_json_recovers_then_finishes():
    with tempfile.TemporaryDirectory() as tmp:
        script = [
            ('NOT JSON AT ALL <<', UsageInfo(prompt_tokens=50, completion_tokens=3, cache_tokens=0, cost_usd=0.0)),
            ('{"thought":"finish now","action":"finish","tool_name":null,'
             '"arguments":{},"final_message":"ok"}',
             UsageInfo(prompt_tokens=60, completion_tokens=2, cache_tokens=0, cost_usd=0.0)),
        ]
        agent = make_agent(tmp, script)
        env = FakeEnvironment({})
        ctx = AgentContext()
        asyncio.run(agent.run('t', env, ctx))
        tr = (Path(tmp) / 'document-tools-agent.txt').read_text()
        assert 'STEP 1 INVALID' in tr and 'FINAL' in tr
        assert ctx.n_output_tokens == 5  # 3 + 2 across both calls


def test_max_steps_exhaustion_is_not_finish():
    with tempfile.TemporaryDirectory() as tmp:
        # every step asks for a tool; never finish -> bounded by max_steps
        step = ('{"thought":"again","action":"call_tool","tool_name":"get_task_metadata",'
                '"arguments":{},"final_message":null}')
        script = [(step, UsageInfo(prompt_tokens=10, completion_tokens=1, cache_tokens=0, cost_usd=0.0))] * 6
        agent = make_agent(tmp, script)
        env = FakeEnvironment({})
        ctx = AgentContext()
        asyncio.run(agent.run('t', env, ctx))
        tr = (Path(tmp) / 'document-tools-agent.txt').read_text()
        assert 'FINAL' in tr and 'Task ended without an explicit finish.' in tr
        assert len(agent.llm.calls) == 6  # bounded


if __name__ == '__main__':
    test_normal_finish_with_events_and_usage()
    test_invalid_json_recovers_then_finishes()
    test_max_steps_exhaustion_is_not_finish()
    print('all 3 wiring tests passed')
