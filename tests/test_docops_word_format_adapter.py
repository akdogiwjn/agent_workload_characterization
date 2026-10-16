#!/usr/bin/env python3
"""Offline tests for the project-owned DocOps Word formatting adapter."""
from __future__ import annotations

import asyncio
import hashlib
import json
import contextlib
import io
import shlex
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'references/repos/DocOps/harnesses'))
sys.path.insert(0, str(ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages'))

from agent_workload_characterization.runners import docops_word_runtime as runtime  # noqa: E402
from agent_workload_characterization.runners.docops_word_agent import DocOpsWordAgent  # noqa: E402
import docops_word_resource_01_entry as entry  # noqa: E402

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ET.register_namespace('w', W)
NS = {'w': W}
TASK = ROOT / 'references/repos/DocOps/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed'
OFFICIAL_METADATA = TASK / 'environment/task_metadata.json'


def make_docx(path: Path, lines=('Selected paragraph', 'Untouched paragraph')) -> None:
    body = ''.join(
        f'<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>{line}</w:t></w:r></w:p>'
        for line in lines)
    document = (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8"?>'
              f'<w:styles xmlns:w="{W}">'
              '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>'
              '</w:styles>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('word/document.xml', document)
        zf.writestr('word/styles.xml', styles)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FormatRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original_root = runtime.ROOT_DIR
        runtime.ROOT_DIR = self.root
        self.addCleanup(setattr, runtime, 'ROOT_DIR', self.original_root)
        self.metadata = json.loads(OFFICIAL_METADATA.read_text())
        (self.root / 'task_metadata.json').write_text(json.dumps(self.metadata))
        self.input = self.root / Path(self.metadata['input_path']).relative_to('/root')
        self.output = self.root / Path(self.metadata['output_path']).relative_to('/root')
        self.input.parent.mkdir(parents=True, exist_ok=True)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        make_docx(self.input)
        self.source_hash = digest(self.input)

    def test_read_reports_direct_and_unset_properties(self):
        doc = runtime.tool_word_inspect_format(self.metadata['input_path'], 0)
        self.assertEqual(doc['text'], 'Selected paragraph')
        self.assertEqual(doc['style']['name'], 'Normal')
        self.assertEqual(doc['paragraph_format_direct']['alignment']['status'], 'not_directly_set')
        self.assertEqual(doc['runs'][0]['font_direct']['font_names']['ascii']['status'], 'not_directly_set')
        self.assertEqual(doc['runs'][0]['font_direct']['size_pt']['status'], 'not_directly_set')
        self.assertIn('not resolved', doc['format_semantics'])

    def test_read_distinguishes_direct_font_size_color_bold(self):
        path = self.input
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read('word/document.xml'))
        run = root.find('.//w:body/w:p/w:r', NS)
        rpr = ET.SubElement(run, f'{{{W}}}rPr')
        fonts = ET.SubElement(rpr, f'{{{W}}}rFonts')
        fonts.set(f'{{{W}}}ascii', 'Arial')
        ET.SubElement(rpr, f'{{{W}}}sz').set(f'{{{W}}}val', '24')
        ET.SubElement(rpr, f'{{{W}}}color').set(f'{{{W}}}val', 'C00000')
        ET.SubElement(rpr, f'{{{W}}}b').set(f'{{{W}}}val', '1')
        replacement = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', replacement)
            zf.writestr('word/styles.xml', '<w:styles xmlns:w="%s"/>' % W)
        props = runtime.tool_word_inspect_format(self.metadata['input_path'], 0)['runs'][0]['font_direct']
        self.assertEqual(props['font_names']['ascii']['value'], 'Arial')
        self.assertEqual(props['size_pt']['value'], 12)
        self.assertEqual(props['color']['value']['val'], 'C00000')
        self.assertTrue(props['bold']['value'])

    def test_set_format_reopens_docx_and_preserves_other_content_and_input(self):
        import shutil
        shutil.copy2(self.input, self.output)
        result = runtime.dispatch('word_set_format', {
            'path': self.metadata['output_path'], 'paragraph_index': 0,
            'style_name': 'Heading 1', 'font_name': 'Cambria',
            'font_size_pt': 16, 'color': '1F4E79', 'bold': True,
            'alignment': 'center', 'space_after_pt': 8,
        })
        self.assertTrue(result['text_preserved'])
        checked = runtime.tool_word_inspect_format(self.metadata['output_path'], 0)
        self.assertEqual(checked['text'], 'Selected paragraph')
        self.assertEqual(checked['style']['name'], 'Heading 1')
        self.assertEqual(checked['runs'][0]['font_direct']['font_names']['ascii']['value'], 'Cambria')
        self.assertEqual(checked['runs'][0]['font_direct']['size_pt']['value'], 16)
        self.assertEqual(checked['runs'][0]['font_direct']['color']['value']['val'], '1F4E79')
        self.assertTrue(checked['runs'][0]['font_direct']['bold']['value'])
        other = runtime.tool_word_inspect_format(self.metadata['output_path'], 1)
        self.assertEqual(other['text'], 'Untouched paragraph')
        self.assertEqual(other['style']['name'], 'Normal')
        self.assertEqual(checked['paragraph_format_direct']['alignment']['value'], 'center')
        self.assertEqual(checked['paragraph_format_direct']['spacing_raw']['after']['value'], '160')
        self.assertEqual(digest(self.input), self.source_hash)

    def test_real_official_docx_justify_preserves_ignorable_namespaces(self):
        import shutil
        official_docx = TASK / 'environment/word_001_engineering_report_toc_hierarchy_seed.docx'
        original_hash = digest(official_docx)
        shutil.copy2(official_docx, self.output)
        with zipfile.ZipFile(official_docx) as source:
            original_xml = source.read('word/document.xml')
        original_namespaces = set(ET.iterparse(
            io.BytesIO(original_xml), events=('start-ns',)))
        # iterparse events contain (event, (prefix, URI)); retain only declarations.
        original_namespaces = {declaration for _, declaration in original_namespaces}
        with zipfile.ZipFile(official_docx) as source:
            root_before = ET.fromstring(source.read('word/document.xml'))
        mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
        ignorable = root_before.get(f'{{{mc}}}Ignorable', '').split()
        self.assertTrue({'w14', 'wp14'}.issubset(set(ignorable)))
        namespace_by_prefix = dict(original_namespaces)
        self.assertTrue(all(prefix in namespace_by_prefix for prefix in ignorable))

        result = runtime.dispatch('word_set_format', {
            'path': self.metadata['output_path'], 'paragraph_index': 0,
            'alignment': 'justify',
        })
        self.assertTrue(result['ok'])
        with zipfile.ZipFile(self.output) as modified:
            modified_xml = modified.read('word/document.xml')
        modified_namespaces = {declaration for _, declaration in ET.iterparse(
            io.BytesIO(modified_xml), events=('start-ns',))}
        self.assertTrue(original_namespaces.issubset(modified_namespaces))
        root_after = ET.fromstring(modified_xml)
        self.assertEqual(root_after.get(f'{{{mc}}}Ignorable'), 'w14 wp14')
        for prefix in ignorable:
            uri = namespace_by_prefix[prefix]
            self.assertIn((prefix, uri), modified_namespaces)
        checked = runtime.tool_word_inspect_format(self.metadata['output_path'], 0)
        self.assertEqual(checked['paragraph_format_direct']['alignment']['value'], 'both')
        self.assertTrue(checked['text'])
        self.assertEqual(digest(official_docx), original_hash)

    def test_set_format_rejects_input_path_and_invalid_values(self):
        with self.assertRaisesRegex(ValueError, 'restricted'):
            runtime.dispatch('word_set_format', {
                'path': self.metadata['input_path'], 'paragraph_index': 0, 'bold': True})
        import shutil
        shutil.copy2(self.input, self.output)
        with self.assertRaisesRegex(ValueError, 'finite number'):
            runtime.tool_word_set_format(self.metadata['output_path'], 0, font_size_pt=float('nan'))


class FakeModel:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    async def call(self, *, message_history, logging_path=None, **kwargs):
        self.calls.append(message_history)
        content = self.actions.pop(0)
        if logging_path:
            Path(logging_path).parent.mkdir(parents=True, exist_ok=True)
            Path(logging_path).write_text('{}')
        return SimpleNamespace(content=content, usage=None, model_name="fake", response_id=None)


class FakeEnvironment:
    def __init__(self, root):
        self.root = Path(root)
        self.uploads = []
        self.events = []
        self.tool_results = []

    async def upload_file(self, source, target):
        source = Path(source)
        self.uploads.append((source, target, source.read_bytes()))
        self.events.append(('upload', target))
        if target == '/root/task_metadata.json':
            path = self.root / 'task_metadata.json'
            path.write_bytes(source.read_bytes())

    async def exec(self, command, **kwargs):
        self.events.append(('exec', command))
        args = shlex.split(command)
        if args[0] == 'chmod' or args[:2] == ['mkdir', '-p']:
            return SimpleNamespace(stdout='', stderr='', return_code=0)
        tool = args[args.index('--tool') + 1]
        payload = json.loads(args[args.index('--args-json') + 1])
        if tool in ('get_task_metadata', 'word_inspect_format', 'word_set_format'):
            result = runtime.dispatch(tool, payload)
        elif tool == 'inspect_document':
            result = {'ok': True, 'type': 'docx', 'paragraphs': [], 'tables': []}
        elif tool == 'copy_file':
            source = self.root / Path(payload['src']).relative_to('/root')
            dest = self.root / Path(payload['dest']).relative_to('/root')
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(source, dest)
            result = {'ok': True, 'copied_to': payload['dest']}
        else:
            result = {'ok': False, 'error': 'unsupported fake boundary tool'}
        self.tool_results.append((tool, result))
        return SimpleNamespace(stdout=json.dumps(result), stderr='', return_code=0)


class AgentChainTests(unittest.TestCase):
    def test_actual_loop_cancellation_closes_last_tool_and_does_not_request_again(self):
        from agent_workload_characterization.collectors.execution_measurement import measurement_report
        class CancelEnv:
            async def exec(self, command, **kwargs):
                if '--tool copy_file ' in command:
                    raise asyncio.CancelledError()
                return SimpleNamespace(stdout='{"ok": false}', stderr='')
        with tempfile.TemporaryDirectory() as tmp:
            agent = entry.build_agent(Path(tmp) / 'agent')
            model = FakeModel([
                json.dumps({'thought': 'copy', 'action': 'call_tool', 'tool_name': 'copy_file', 'arguments': {}}),
                json.dumps({'thought': 'done', 'action': 'finish'})])
            agent.llm = model
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(agent.run('synthetic', CancelEnv(), SimpleNamespace()))
            self.assertEqual(len(model.calls), 1)
            report = measurement_report(Path(tmp) / 'agent/events.jsonl',
                expected_requests=agent.request_count, expected_tools=agent.tool_count)
            self.assertEqual(report['call_timing_status'], 'complete')
            self.assertEqual(report['tool_spans']['spans']['tool_call']['error_terminal'], 1)
            self.assertEqual(report['tool_spans']['spans']['tool_call']['bootstrap'], 1)

    def test_metadata_upload_then_actual_agent_runtime_format_chain_and_finish(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        original_root = runtime.ROOT_DIR
        runtime.ROOT_DIR = root
        self.addCleanup(setattr, runtime, 'ROOT_DIR', original_root)
        metadata = json.loads(OFFICIAL_METADATA.read_text())
        source = root / Path(metadata['input_path']).relative_to('/root')
        source.parent.mkdir(parents=True, exist_ok=True)
        make_docx(source)
        env = FakeEnvironment(root)
        model = FakeModel([
            json.dumps({'thought': 'copy', 'action': 'call_tool', 'tool_name': 'copy_file',
                        'arguments': {'src': metadata['input_path'], 'dest': metadata['output_path']}}),
            json.dumps({'thought': 'inspect', 'action': 'call_tool', 'tool_name': 'word_inspect_format',
                        'arguments': {'path': metadata['output_path'], 'paragraph_index': 0}}),
            json.dumps({'thought': 'format', 'action': 'call_tool', 'tool_name': 'word_set_format',
                        'arguments': {'path': metadata['output_path'], 'paragraph_index': 0,
                                      'style_name': 'Heading 1', 'font_name': 'Cambria',
                                      'font_size_pt': 16, 'color': '1F4E79', 'bold': True}}),
            json.dumps({'thought': 'verify', 'action': 'call_tool', 'tool_name': 'word_inspect_format',
                        'arguments': {'path': metadata['output_path'], 'paragraph_index': 0}}),
            json.dumps({'thought': 'done', 'action': 'finish', 'final_message': 'finished'}),
        ])
        agent = DocOpsWordAgent(logs_dir=root / 'logs', metadata_path=OFFICIAL_METADATA,
                                model_name='fake-model', max_steps=8)
        (root / 'logs').mkdir()
        agent.llm = model
        async def run():
            await agent.setup(env)
            before_call = len(env.events)
            await agent.run((TASK / 'instruction.md').read_text(), env, SimpleNamespace())
            return before_call
        setup_end = asyncio.run(run())
        targets = [target for _, target, _ in env.uploads]
        self.assertEqual(targets, ['/root/document_tools_runtime.py',
                                   '/root/docops_word_runtime.py',
                                   '/root/task_metadata.json'])
        metadata_upload = env.uploads[2]
        self.assertEqual(metadata_upload[2], OFFICIAL_METADATA.read_bytes())
        metadata_result = next(result for name, result in env.tool_results if name == 'get_task_metadata')
        self.assertEqual(metadata_result['metadata']['input_path'], metadata['input_path'])
        self.assertEqual(metadata_result['metadata']['output_path'], metadata['output_path'])
        self.assertLess(env.events.index(('upload', '/root/task_metadata.json')),
                        next(i for i, event in enumerate(env.events) if event[0] == 'exec' and '--tool get_task_metadata' in event[1]))
        self.assertEqual(model.calls[0][1]['content'], (TASK / 'instruction.md').read_text())
        prompt = model.calls[0][0]['content']
        self.assertIn('word_inspect_format', prompt)
        self.assertIn('word_set_format', prompt)
        self.assertEqual(len(model.calls), 5)  # finish is last; no sixth request
        self.assertTrue(any('Tool result for word_set_format' in item.get('content', '')
                            for item in model.calls[3]))
        self.assertTrue(any('Heading 1' in item.get('content', '')
                            for item in model.calls[4]))
        self.assertTrue(any(name == 'word_inspect_format' and result.get('ok') for name, result in env.tool_results))
        self.assertTrue(any(name == 'word_set_format' and result.get('text_preserved') for name, result in env.tool_results))
        final = runtime.tool_word_inspect_format(metadata['output_path'], 0)
        self.assertEqual(final['style']['name'], 'Heading 1')
        self.assertEqual(final['runs'][0]['font_direct']['size_pt']['value'], 16)


class PlanIdentityTests(unittest.TestCase):
    def test_no_extra_body_reaches_actual_harbor_transport(self):
        from unittest.mock import patch
        from harbor.llms.lite_llm import LiteLLM
        with tempfile.TemporaryDirectory() as tmp:
            agent = entry.build_agent(Path(tmp))
            inner = agent.llm._inner
            inner.call = LiteLLM.call.__wrapped__.__get__(inner, LiteLLM)
            seen = {}
            async def transport(**kwargs):
                seen.update(kwargs)
                raise AssertionError('offline transport reached')
            async def run():
                with patch('harbor.llms.lite_llm.litellm.acompletion', transport):
                    try:
                        await agent.llm.call(prompt='offline', message_history=[],
                                             extra_body=None, stop=['</think>'])
                    except AssertionError:
                        pass
            asyncio.run(run())
            self.assertEqual(seen['model'], entry.MODEL_REQUEST_ID)
            self.assertNotIn('extra_body', seen)
            self.assertNotIn('stop', seen)

    def test_official_route_refuses_old_gateway_credential_without_fallback(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {'VOLCANO_API_KEY': 'synthetic-old-key'}, clear=True), \
                patch.object(entry, 'docker_image_id', return_value=entry.TASK_IMAGE_ID_EXPECTED), \
                patch.object(entry, 'frozen_identity_sha', side_effect=lambda: entry.identity_digest(entry.build_identity())), \
                patch.object(entry, 'run_attempt') as attempt, \
                patch.object(sys, 'argv', ['entry', '--execute',
                    '--i-approve-the-docops-word-resource-04', '--collection-root', tmp]), \
                contextlib.redirect_stderr(io.StringIO()):
            approval = Path(tmp) / 'reports/resource' / entry.COLLECTION / 'APPROVAL.json'
            approval.parent.mkdir(parents=True)
            approval.write_text(json.dumps({
                'schema': 'docops-single-run-approval-v1', 'collection': entry.COLLECTION,
                'user_approval': 'approved',
                'identity_sha256': entry.identity_digest(entry.build_identity())}))
            self.assertEqual(entry.main(), 6)
            attempt.assert_not_called()
            self.assertFalse((Path(tmp) / 'data/raw/generated' / entry.COLLECTION).exists())

    def test_official_route_and_real_agent_use_registered_api_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = entry.build_agent(Path(tmp))
            self.assertEqual(agent.api_base, 'https://api.deepseek.com/v1')
            self.assertEqual(agent.model_name, 'openai/deepseek-v4-flash')
            self.assertIsNone(agent.thinking_mode)
            self.assertIsInstance(agent.llm, entry.JsonActionLLM)
            identity = entry.build_identity()
            self.assertEqual(identity['model_route']['api_base'], agent.api_base)
            self.assertIn('DEEPSEEK_API_KEY', identity['model_route']['credential'])
            self.assertNotIn('VOLCANO_API_KEY', identity['model_route']['credential'])
            self.assertEqual(identity['model_route']['documented_backend'], 'DeepSeek-V4.1-Flash')
            self.assertIn('does not prove full-task success',
                          identity['agent_api_configuration']['validation_scope'])

    def test_plan_binds_current_paths_and_rejects_historical_freeze_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = entry.plan_mode(Path(tmp))
            identity = plan['identity']
            self.assertEqual(identity['collection'], 'DOCOPS-WORD-RESOURCE-04')
            self.assertIn('task_metadata', identity['files'])
            self.assertIn('project_agent_adapter', identity['files'])
            self.assertIn('project_runtime_adapter', identity['files'])
            self.assertTrue(identity['state_paths']['approval'].endswith('/APPROVAL.json'))
            self.assertEqual(plan['existing_attempts'], [])
            self.assertFalse((Path(tmp) / 'data/raw/generated/DOCOPS-WORD-RESOURCE-04').exists())
            self.assertFalse(plan['identity_matches_frozen'])
            old = json.loads((ROOT / 'env/docops-arm64-word001/frozen-identity.json').read_text())
            self.assertNotEqual(plan['identity_sha256'], old['identity_sha256'])

    def test_old_approval_flag_is_rejected_before_any_execution(self):
        from unittest.mock import patch
        for old_flag in ('--i-approve-the-docops-word-resource-01',
                         '--i-approve-the-docops-word-resource-02'):
            with self.subTest(old_flag=old_flag), \
                    patch.object(sys, 'argv', ['entry', '--execute', old_flag]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    entry.main()
                self.assertEqual(raised.exception.code, 2)

    def test_any_existing_report_namespace_content_blocks_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            namespace = Path(tmp) / 'reports/resource/DOCOPS-WORD-RESOURCE-04'
            namespace.mkdir(parents=True)
            (namespace / 'old-report.json').write_text('{}')
            plan = entry.plan_mode(Path(tmp))
            self.assertFalse(plan['ready_for_approval'])
            self.assertEqual(plan['existing_namespace_records'], ['old-report.json'])


if __name__ == '__main__':
    unittest.main()
