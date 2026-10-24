import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path('/workspace/validation')
OUT = Path('/workspace/output')
SESSION = 'offline-full-chain-' + uuid.uuid4().hex


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def payload_of(result):
    if getattr(result, 'structuredContent', None):
        return result.structuredContent
    if result.content and getattr(result.content[0], 'text', None):
        return json.loads(result.content[0].text)
    raise AssertionError({'isError': result.isError, 'content': str(result.content)})


class FakeRoughCutLLM:
    async def complete(self, **kwargs):
        event = {
            'kind': 'deterministic_fake_model_response',
            'boundary': 'speech_rough_cut node_state.llm.complete',
            'system_prompt_present': bool(kwargs.get('system_prompt')),
            'user_prompt_bytes': len((kwargs.get('user_prompt') or '').encode()),
            'media': kwargs.get('media'),
            'response': {
                'res': [
                    {'text': 'offline chain first retained segment', 'start': 0, 'end': 2500},
                    {'text': 'offline chain second retained segment', 'start': 3100, 'end': 6000},
                ]
            },
        }
        with (OUT / 'fake-model-events.jsonl').open('a') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
        return json.dumps(event['response'])


def run_server():
    sys.path.insert(0, '/opt/openstoryline/src')
    os.environ['OPENSTORYLINE_CONFIG'] = str(ROOT / 'config.toml')
    from open_storyline.config import default_config_path, load_settings
    from open_storyline.mcp import register_tools
    from open_storyline.mcp.server import create_server

    register_tools.make_llm = lambda _ctx: FakeRoughCutLLM()
    cfg = load_settings(default_config_path())
    server = create_server(cfg)
    server.settings.host = cfg.local_mcp_server.connect_host
    server.settings.port = cfg.local_mcp_server.port
    server.run(transport=cfg.local_mcp_server.server_transport)


async def run_client():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from open_storyline.storage.agent_memory import ArtifactStore

    OUT.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(OUT, SESSION)
    child_log = (OUT / 'mcp-server.log').open('x', encoding='utf-8')
    server = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), 'server'],
        cwd='/workspace', stdout=subprocess.DEVNULL, stderr=child_log,
        start_new_session=True,
    )
    events = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f'MCP server exited rc={server.returncode}')
            try:
                with socket.create_connection(('127.0.0.1', 8001), timeout=.2):
                    break
            except OSError:
                await asyncio.sleep(.2)
        else:
            raise TimeoutError('MCP server startup timed out')

        async with streamablehttp_client(
            'http://127.0.0.1:8001/mcp',
            headers={'X-Storyline-Session-Id': SESSION},
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = {tool.name: tool.inputSchema for tool in (await client.list_tools()).tools}
                assert 'artifact_id' not in tools['load_media'].get('properties', {})
                assert set(tools['load_media'].get('properties', {})) == {'mode'}

                async def call(name, args):
                    event_id = str(uuid.uuid4())
                    result = await client.call_tool(name, args)
                    data = payload_of(result)
                    events.append({
                        'tool_event_id': event_id,
                        'mcp_call_count': 1,
                        'tool': name,
                        'arguments': args,
                        'is_error': bool(result.isError),
                        'result': data,
                    })
                    assert not result.isError and data.get('isError') is False, (name, data)
                    store.save_result(SESSION, name, data, Path('/workspace/input'))
                    return data

                load = await call('load_media', {'mode': 'auto'})
                media = load['tool_excute_result']['media']
                media_path = Path(media[0]['path'])
                resolved_media_path = media_path if media_path.is_absolute() else Path('/workspace/input') / media_path
                assert len(media) > 0 and resolved_media_path.is_relative_to(Path('/workspace/input'))
                assert resolved_media_path.is_file()
                assert media[0]['metadata']['has_audio'] is True

                split = await call('split_shots', {'mode': 'skip'})
                clips = split['tool_excute_result'].get('clips', [])
                assert clips and Path(clips[0]['path']).is_file()
                asr = await call('local_asr', {'mode': 'auto'})
                asr_infos = asr['tool_excute_result'].get('asr_infos', [])
                asr_path = Path(asr_infos[0]['path'])
                resolved_asr_path = asr_path if asr_path.is_absolute() else Path('/workspace/input') / asr_path
                assert asr_infos and resolved_asr_path.resolve() == resolved_media_path.resolve()
                assert asr_infos[0].get('asr_sentence_info'), 'ASR returned no sentence timestamps'

                rough = await call('speech_rough_cut', {
                    'mode': 'auto', 'gap_threshold': 400,
                    'user_request': 'Offline wiring verification only; preserve the deterministic test ranges.',
                })
                rough_payload = rough['tool_excute_result']
                rough_clips = rough_payload.get('clips', [])
                assert len(rough_clips) == 2, rough_payload
                assert rough_clips[0]['source_ref']['end'] == 2500
                assert rough_clips[1]['source_ref']['start'] == 3100

                plan = await call('plan_timeline_pro', {
                    'mode': 'auto', 'use_beats': False,
                    'is_speech_rough_cut': True, 'is_ai_transition': False,
                    'image_duration_ms': 3000,
                })
                timeline = plan['tool_excute_result'].get('tracks', {}).get('video', [])
                assert len(timeline) == 2 and all(x.get('source_path') for x in timeline), plan
                assert all(Path(x['source_path']).is_file() for x in timeline)

                transition = await call('elementrec_transition', {'mode': 'skip'})
                text = await call('elementrec_text', {'mode': 'skip'})
                render = await call('render_video', {
                    'mode': 'auto', 'aspect_ratio': '16:9',
                    'output_max_dimension_px': 320,
                    'clip_compose_mode': 'padding', 'crf': 23,
                    'font_color': [255, 255, 255, 255], 'font_size': 28,
                    'margin_bottom': 20, 'stroke_width': 0,
                    'stroke_color': [0, 0, 0, 255],
                })

        render_meta = render['tool_excute_result']
        rendered = Path(render_meta['output_path'])
        assert rendered.is_file() and rendered.stat().st_size > 0

        # Derive retained source intervals from the actual rendered timeline
        # windows, mapped through the final rough-cut clip source references.
        rough_by_path = {str(Path(c['path']).resolve()): c for c in rough_clips}
        retained = []
        for item in timeline:
            source_clip = rough_by_path[str(Path(item['source_path']).resolve())]
            origin = int(source_clip['source_ref']['start'])
            local_start = int(item['source_window']['start'])
            local_end = int(item['source_window']['end'])
            retained.append([origin + local_start, origin + local_end])
        retained.sort()
        source_duration = int(media[0]['metadata']['duration'])
        cuts = []
        cursor = 0
        for start, end in retained:
            if start > cursor:
                cuts.append({'start_ms': cursor, 'end_ms': start, 'reason': 'offline_test_gap'})
            cursor = max(cursor, end)
        if cursor < source_duration:
            cuts.append({'start_ms': cursor, 'end_ms': source_duration, 'reason': 'offline_test_gap'})

        final_video = OUT / 'output.mp4'
        shutil.copy2(rendered, final_video)
        (OUT / 'cuts.json').write_text(json.dumps({'cuts': cuts}, indent=2) + '\n')
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate',
             '-of', 'json', str(final_video)], check=True, capture_output=True, text=True,
        )
        streams = json.loads(probe.stdout)['streams']
        assert any(s.get('codec_type') == 'video' for s in streams), streams
        assert any(s.get('codec_type') == 'audio' for s in streams), streams
        assert len(events) == len({e['tool_event_id'] for e in events})
        assert len(events) == 8
        report = {
            'verdict': 'PASS', 'network': 'none', 'session_id': SESSION,
            'credentials_used': False, 'real_model_requests': 0,
            'fake_model_calls': 1, 'fake_scope': 'SpeechRoughCutNode llm.complete only',
            'tool_call_count': len(events), 'tools': [e['tool'] for e in events],
            'same_session_artifact_store': True,
            'indexed_media_path': str(resolved_media_path),
            'asr_media_path': str(resolved_asr_path),
            'asr_sentence_count': len(asr_infos[0]['asr_sentence_info']),
            'timeline_retained_source_ranges_ms': retained,
            'cuts_derived_from_final_timeline_ms': cuts,
            'rendered_video': str(final_video), 'rendered_bytes': final_video.stat().st_size,
            'render_streams': streams,
            'transition_skip_result': transition['tool_excute_result'],
            'text_skip_result': text['tool_excute_result'],
        }
        write_json(OUT / 'tool-events.json', events)
        write_json(OUT / 'result.json', report)
        print(json.dumps({'verdict': report['verdict'], 'tools': report['tools'],
                          'fake_model_calls': 1, 'rendered_bytes': report['rendered_bytes']}))
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
        child_log.close()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'server':
        run_server()
    else:
        asyncio.run(run_client())
