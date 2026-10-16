"""Project-side DocumentToolsAgent extension for the Word resource pilot."""
from __future__ import annotations

import json
import shlex
import hashlib
from pathlib import Path
from typing import Any

from document_tools_agent import DocumentToolsAgent
from ..collectors.semantic_recorder import SemanticRecorder, SystemClock
from ..collectors.execution_measurement import MeasuredLLM

RUNTIME_TARGET = '/root/docops_word_runtime.py'
OFFICIAL_RUNTIME_TARGET = '/root/document_tools_runtime.py'
METADATA_TARGET = '/root/task_metadata.json'


class DocOpsWordAgent(DocumentToolsAgent):
    """Extends the fixed DocOps harness with explicit DOCX format tools."""

    def __init__(self, *args, metadata_path: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata_path = Path(metadata_path)
        self.recorder = None
        self.request_count = self.tool_count = 0
        self.request_event_id = None
        self.resource_read = None

    async def run(self, instruction, environment, context):
        # Observe the official loop, including bootstrap and the last tool return.
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.recorder = SemanticRecorder(
            self.logs_dir, SystemClock(), run_id=self.logs_dir.parent.name,
            attempt_id=self.logs_dir.parent.name, task_id=self.metadata_path.parent.parent.name,
            source_type='benchmark_real')
        self.recorder.begin_run()
        original = self.llm
        self.llm = MeasuredLLM(original, self.recorder, self)
        try:
            return await super().run(instruction, environment, context)
        finally:
            self.recorder.seal()
            self.llm = original

    def _parse_action(self, raw):
        try:
            action = super()._parse_action(raw)
        except Exception as exc:
            self.recorder.point('agent_action', {
                'request_event_id': self.request_event_id, 'step_index': self.request_count,
                'action': 'invalid', 'error': type(exc).__name__})
            raise
        self.recorder.point('agent_action', {
            'request_event_id': self.request_event_id, 'step_index': self.request_count,
            'action': action.action, 'tool_name': action.tool_name})
        return action

    async def setup(self, environment) -> None:
        harness_runtime = Path(__file__).resolve().parents[3] / 'references/repos/DocOps/harnesses/document_tools_runtime.py'
        project_runtime = Path(__file__).with_name('docops_word_runtime.py')
        await environment.upload_file(harness_runtime, OFFICIAL_RUNTIME_TARGET)
        await environment.upload_file(project_runtime, RUNTIME_TARGET)
        await environment.upload_file(self.metadata_path, METADATA_TARGET)
        await environment.exec(command=f'chmod +x {shlex.quote(OFFICIAL_RUNTIME_TARGET)} {shlex.quote(RUNTIME_TARGET)}')
        await environment.exec(command='mkdir -p /root/submission')

    def _tool_specs(self) -> list[dict[str, Any]]:
        tools = super()._tool_specs()
        tools.extend([
            {'name': 'word_inspect_format',
             'description': 'Args: {path: string, paragraph_index: integer}. Read paragraph text, applied paragraph style, direct run font name/size/color/bold, and direct paragraph-format values. Unset direct values are reported as not_directly_set; inherited/rendered Word formatting is not resolved.'},
            {'name': 'word_set_format',
             'description': 'Args: {path: string, paragraph_index: integer, style_name?: string, font_name?: string, font_size_pt?: number, color?: six-digit RGB string, bold?: boolean, alignment?: left|center|right|justify|distribute, left_indent_pt?: number, right_indent_pt?: number, first_line_indent_pt?: number, space_before_pt?: number, space_after_pt?: number, line_spacing?: number}. Set only the specified formatting on the selected paragraph in the submitted output document. It does not change text or unrelated paragraphs.'},
        ])
        return tools

    async def _exec_tool(self, environment, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.recorder is None:
            raise RuntimeError('tool execution requires the measured Agent loop')
        self.tool_count += 1
        args_json = json.dumps(arguments, ensure_ascii=False)
        args_bytes = args_json.encode('utf-8')
        before = self.resource_read() if self.resource_read else None
        event_id = self.recorder.begin('tool_call', {
            'tool_index': self.tool_count, 'tool_name': tool_name,
            'role': 'bootstrap' if self.request_count == 0 else 'agent',
            'request_event_id': self.request_event_id,
            'argument_sha256': hashlib.sha256(args_bytes).hexdigest(),
            'argument_bytes': len(args_bytes), 'resource_before': before,
            'attribution_method': 'shared_scope_window_only'})
        try:
            payload = await self._execute_tool(environment, tool_name, args_json)
        except BaseException as exc:
            self.recorder.end(event_id, attrs={
                'ok': False, 'resource_after': self.resource_read() if self.resource_read else None},
                error=type(exc).__name__)
            raise
        result_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.recorder.end(event_id, attrs={
            'ok': payload.get('ok'), 'result_sha256': hashlib.sha256(result_bytes).hexdigest(),
            'result_bytes': len(result_bytes),
            'resource_after': self.resource_read() if self.resource_read else None})
        return payload

    async def _execute_tool(self, environment, tool_name, args_json):
        command = (f"python3 {shlex.quote(RUNTIME_TARGET)} "
                   f"--tool {shlex.quote(tool_name)} "
                   f"--args-json {shlex.quote(args_json)}")
        result = await environment.exec(command=command)
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        try:
            payload = json.loads(stdout.splitlines()[-1]) if stdout else {'ok': False, 'error': 'empty stdout'}
        except Exception:
            payload = {'ok': False, 'error': 'failed to parse tool output'}
        if stderr:
            payload.setdefault('stderr', stderr)
        return payload
