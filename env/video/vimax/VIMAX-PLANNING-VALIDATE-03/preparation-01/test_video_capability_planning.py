from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from langchain_openai.chat_models import base as chat_base

from agent_runtime.request_ledger import get_ledger
import agent_runtime.request_ledger as ledger_module
from agent_runtime.vimax_adapters import preflight_render_capability
from pipelines.script2video_pipeline import Script2VideoPipeline
from utils.video_generation_capabilities import configured_video_generation_capabilities

REPO = Path('/workspace')
PREVIOUS_PLAN = Path('/tests02/execution-01/workspace/.working_dir/planning-validation-02/script2video')


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        'id': 'chatcmpl-capability-fixture', 'object': 'chat.completion',
        'created': 1, 'model': 'qwen3.7-plus',
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                     'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 15, 'completion_tokens': 24, 'total_tokens': 39},
    })


def response_for(messages: list[dict]) -> str:
    text = '\n'.join(str(m.get('content', '')) for m in messages)
    if '<SCRIPT>' in text:
        return json.dumps({'storyboard': [
            {'idx': i, 'is_last': i == 7, 'cam_idx': 0,
             'visual_desc': f'The photographer moves through location {i + 1} and performs the specified action.',
             'audio_desc': ''} for i in range(8)
        ]})
    if '<VISUAL_DESC>' in text:
        # Keep a meaningful moving action while producing the native small enum.
        return json.dumps({
            'ff_desc': 'The photographer begins the supplied action in the described place.',
            'ff_vis_char_idxs': [],
            'lf_desc': 'Textual ending state: the photographer has progressed through the supplied action.',
            'lf_vis_char_idxs': [],
            'motion_desc': 'The photographer walks, turns, and adjusts the camera while the camera tracks gently.',
            'variation_type': 'small',
            'variation_reason': 'The action and camera move naturally while the framing changes only modestly.',
        })
    if '<CAMERA_SEQ>' in text:
        return json.dumps({'camera_parent_items': [
            {'parent_cam_idx': None, 'parent_shot_idx': None, 'reason': 'Root camera.',
             'is_parent_fully_covers_child': None, 'missing_info': None}
        ]})
    raise AssertionError('Unexpected production prompt type')


class CapabilityPlanningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.ledger_path = self.out / 'request-ledger.jsonl'
        self.requests = []
        self.transport = httpx.MockTransport(self._handle)
        self.env = {
            'VIMAX_VIDEO_CAPABILITY_PROFILE': 'bailian-wan26-i2v-first-frame',
            'VIMAX_VIDEO_MODEL': 'wan2.6-i2v-flash',
            'VIMAX_LLM_API_KEY': 'synthetic-offline-only',
            'VIMAX_LLM_MODEL': 'qwen3.7-plus',
            'VIMAX_LLM_MODEL_PROVIDER': 'openai',
            'VIMAX_LLM_BASE_URL': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'VIMAX_NARRATIVE_MAX_TOKENS': '8192',
            'VIMAX_BAILIAN_EVENT_LOG': str(self.ledger_path),
            'VIMAX_BAILIAN_BUDGET_LLM_CALLS': '40',
            'VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS': '40',
            'VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS': '8192',
            'VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS': '250000',
            'VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS': '1800',
            'VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS': '0',
            'VIMAX_BAILIAN_BUDGET_VIDEO_CREATES': '0',
            'VIMAX_BAILIAN_REQUIRED_SHOTS': '8',
            'VIMAX_BAILIAN_BUDGET_TRANSITIONS': '4',
        }
        ledger_module._LEDGER = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        return completion(response_for(body['messages']))

    def _patch_sdk(self):
        original = chat_base.openai.AsyncOpenAI

        def factory(*args, **kwargs):
            kwargs['http_client'] = httpx.AsyncClient(transport=self.transport)
            return original(*args, **kwargs)

        return patch.object(chat_base.openai, 'AsyncOpenAI', side_effect=factory)

    def test_saved_previous_plan_fails_exactly_three_shots_before_any_media_call(self):
        destination = self.out / 'old-plan-copy'
        shutil.copytree(PREVIOUS_PLAN, destination)
        ledger_module._LEDGER = None
        with patch.dict(os.environ, self.env, clear=False):
            ok, reasons = preflight_render_capability(
                destination, video_capabilities=configured_video_generation_capabilities())
            ledger = get_ledger()
        joined = '\n'.join(reasons)
        self.assertFalse(ok)
        self.assertIn('shot 2 (variation_type=large)', joined)
        self.assertIn('shot 4 (variation_type=medium)', joined)
        self.assertIn('shot 5 (variation_type=medium)', joined)
        self.assertEqual(ledger.counts().get('image_generations', 0), 0)
        self.assertEqual(ledger.counts().get('video_creates', 0), 0)
        # Historical fixture remains byte-identical after being used read-only.
        self.assertEqual(json.loads((destination / 'shots/4/shot_description.json').read_text())['variation_type'], 'medium')

    def test_real_pipeline_storyboard_decomposition_and_camera_tree_receive_capability(self):
        original = chat_base.openai.AsyncOpenAI
        with patch.dict(os.environ, self.env, clear=False), self._patch_sdk():
            from agent_runtime.vimax_adapters import _build_chat_model
            model = _build_chat_model()
            pipeline = Script2VideoPipeline(
                chat_model=model, image_generator=object(), video_generator=object(),
                working_dir=str(self.out / 'script2video'),
                video_capabilities=configured_video_generation_capabilities())
            result = asyncio.run(pipeline.plan_text_artifacts(
                script='Eight frozen actions in order.',
                user_requirement='Keep all eight shots and preserve the supplied actions.',
                style='Documentary, natural light, 16:9.',
                characters=[], quiet=True))
            ok, reasons = preflight_render_capability(
                self.out / 'script2video',
                video_capabilities=configured_video_generation_capabilities())
        self.assertTrue(ok, reasons)
        self.assertEqual(len(result['storyboard']), 8)
        self.assertEqual(len(result['shot_descriptions']), 8)
        self.assertEqual([s.variation_type for s in result['shot_descriptions']], ['small'] * 8)
        self.assertTrue(all(s.lf_desc.startswith('Textual ending state:') for s in result['shot_descriptions']))
        self.assertTrue(all('walks' in s.motion_desc for s in result['shot_descriptions']))
        self.assertEqual(len(self.requests), 10)
        serialized = [json.dumps(row['messages'], ensure_ascii=False) for row in self.requests]
        self.assertTrue(all('Configured video capability' in messages for messages in serialized))
        self.assertTrue(all('last-frame image' in messages for messages in serialized))
        self.assertTrue(all(row.get('enable_thinking') is False for row in self.requests))
        self.assertTrue(all(row.get('max_completion_tokens') == 8192 for row in self.requests))
        events = [json.loads(line) for line in self.ledger_path.read_text().splitlines()]
        closes = [row for row in events if row.get('kind') == 'close']
        self.assertEqual(len(closes), 10)
        self.assertTrue(all(row.get('response_model') == 'qwen3.7-plus' for row in closes))
        ledger = get_ledger()
        self.assertEqual(ledger.counts().get('image_generations', 0), 0)
        self.assertEqual(ledger.counts().get('video_creates', 0), 0)

    def test_capability_profile_mismatch_fails_closed(self):
        with patch.dict(os.environ, {**self.env, 'VIMAX_VIDEO_MODEL': 'other-model'}, clear=False):
            with self.assertRaisesRegex(RuntimeError, 'profile/model mismatch'):
                configured_video_generation_capabilities()


if __name__ == '__main__':
    unittest.main(verbosity=2)
