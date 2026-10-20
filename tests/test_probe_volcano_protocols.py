"""Each case uses its real venv, synthetic endpoint, and fake HTTP transport."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VENV = {'office': ROOT / '.venvs/docops-pilot-01/bin/python',
        'assistant': ROOT / '.venvs/toolsandbox-pilot-01/bin/python'}


def child_case(probe, case, directory):
    # Install isolation before importing a model SDK or project entry.
    import socket
    import faulthandler
    from contextlib import ExitStack
    from unittest.mock import patch
    os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
    os.environ.pop('VOLCANO_API_KEY', None)
    os.environ.pop('DEEPSEEK_API_KEY', None)
    os.environ['OPENAI_API_KEY'] = 'synthetic-existing-environment'
    blocked_network = []
    def deny(*_args, **_kwargs):
        blocked_network.append('attempt')
        raise RuntimeError('offline_socket_access_blocked')
    socket.getaddrinfo = deny
    socket.create_connection = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    faulthandler.enable()
    faulthandler.dump_traceback_later(12, repeat=True)
    sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
    print('STAGE module_import', flush=True)
    import probe_volcano_protocols as p
    modules = p.http_modules()
    result_path = Path(directory) / 'probe.json'
    secret = 'synthetic-canary-never-persist'
    route = {'api_base': 'https://probe.invalid/v1'}
    traces = []
    clients = []
    agents = []
    before_methods = {(m.__name__, c.__name__): c._send_single_request
                      for m in modules for c in (m.Client, m.AsyncClient)}

    def response(module, request):
        traces.append({'stage': 'fake_transport_enter', 'module': module.__name__})
        if case == 'connection':
            raise module.ConnectError('synthetic_connection_failure', request=request)
        content = json.dumps({'thought': 'probe', 'action': 'finish', 'tool_name': None,
                              'arguments': {}, 'final_message': 'protocol probe'})
        if case in ('parse', 'restore'):
            content = 'invalid-json'
        if case == 'empty':
            content = ''
        message = {'role': 'assistant', 'content': content}
        finish = 'stop'
        if probe == 'assistant':
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'call_synthetic', 'type': 'function', 'function': {
                    'name': 'probe_noop', 'arguments': ('invalid-json' if case in ('parse', 'restore')
                                                      else '{"ok":true}')}}]}
            finish = 'tool_calls'
        response = module.Response(200, request=request, json={
            'id': 'chatcmpl-synthetic', 'object': 'chat.completion', 'created': 1,
            'model': 'synthetic-response-model',
            'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
            'usage': {'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18}})
        traces.append({'stage': 'fake_response_return', 'module': module.__name__})
        return response

    with ExitStack() as stack:
        for module in modules:
            def sync(_transport, request, _module=module):
                return response(_module, request)
            async def async_(_transport, request, _module=module):
                return response(_module, request)
            stack.enter_context(patch.object(module.HTTPTransport, 'handle_request', sync))
            stack.enter_context(patch.object(module.AsyncHTTPTransport, 'handle_async_request', async_))
        if probe == 'office':
            import httpx
            from litellm.llms.custom_httpx.aiohttp_transport import LiteLLMAiohttpTransport
            async def aiohttp_transport(_transport, request):
                return response(httpx, request)
            stack.enter_context(patch.object(LiteLLMAiohttpTransport, 'handle_async_request', aiohttp_transport))
            import docops_word_resource_01_entry as word
            other = word.build_agent(Path(directory) / 'other-agent', {
                'task_dir': str(ROOT / 'references/repos/DocOps/tasks/atomic__excel_001_budget_bucket_totals_seed'),
                'max_steps': 40, 'max_tokens': 1024,
                'model_route': {'api_base': route['api_base'], 'request_model': 'openai/deepseek-v4-flash'}})
            original_stop = other.llm._inner.call.retry.stop
            original_builder = word.build_agent
            def build(*args, **kwargs):
                agent = original_builder(*args, **kwargs)
                agents.append(agent)
                return agent
            stack.enter_context(patch.object(word, 'build_agent', build))
        else:
            from agent_workload_characterization.runners import toolsandbox_worker as worker
            original_builder = worker.construct_openai_role_clients
            def build(*args, **kwargs):
                pair = original_builder(*args, **kwargs)
                clients.extend(pair)
                return pair
            stack.enter_context(patch.object(worker, 'construct_openai_role_clients', build))

        def credential_loader():
            if case == 'presend':
                raise TypeError('synthetic_local_error')
            return route['api_base'], secret
        function = p.office_probe if probe == 'office' else p.assistant_probe
        result = function(result_path, credential_loader=credential_loader, route=route,
                          progress=lambda name: print('STAGE ' + name, flush=True))
        saved = json.loads(result_path.read_text())
        assert saved == result
        send = result['send_observation']
        if case == 'presend':
            assert result['status'] == 'failed' and send['forwarded_attempts'] == 0, result
        elif case == 'connection':
            assert result['status'] == 'failed', result
            assert send['forwarded_attempts'] == 1 and send['responses_received'] == 0, result
            assert send['blocked_attempts'] == 0, result
        elif case in ('parse', 'restore', 'empty'):
            assert result['status'] == 'failed' and result['parse_status'] == 'failed', result
            assert send['forwarded_attempts'] == send['responses_received'] == 1, result
        else:
            assert result['status'] == 'passed' and result['parse_status'] == 'complete', result
            assert send['forwarded_attempts'] == send['responses_received'] == 1, result
            assert result['response_evidence']['response_model'] == 'synthetic-response-model'
            if probe == 'assistant':
                assert result['tool_call']['id'] == 'call_synthetic'
                assert result['tool_call']['arguments'] == {'ok': True}
            else:
                assert result['parsed_action'] == result['recorder_action'] == 'finish'
        if case != 'presend':
            assert result['clients_closed'], result
        if probe == 'office':
            assert other.llm._inner.call.retry.stop is original_stop
            assert original_stop.max_attempt_number == 3
            assert all('call' not in a.llm._inner.__dict__ for a in agents)
        else:
            assert all(c.max_retries == 0 and c.is_closed() for c in clients)
        assert os.environ['OPENAI_API_KEY'] == 'synthetic-existing-environment'
        for m in modules:
            for c in (m.Client, m.AsyncClient):
                assert c._send_single_request is before_methods[(m.__name__, c.__name__)]
        if case == 'second':
            # Exercise another send with the same Request object too: no text/ID dedup.
            module = modules[0]
            counter = p.SendCounter('probe.invalid')
            if probe == 'office':
                import asyncio
                async def twice():
                    async with module.AsyncClient() as client:
                        request = client.build_request('GET', 'https://probe.invalid/once')
                        with counter:
                            await client.send(request)
                            try:
                                await client.send(request)
                            except p.ProbeSendLimitExceeded:
                                pass
                            else:
                                raise AssertionError('second forwarding was not blocked')
                asyncio.run(twice())
            else:
                with module.Client() as client, counter:
                    request = client.build_request('GET', 'https://probe.invalid/once')
                    client.send(request)
                    try:
                        client.send(request)
                    except p.ProbeSendLimitExceeded:
                        pass
                    else:
                        raise AssertionError('second forwarding was not blocked')
            assert counter.entered == 2 and counter.forwarded == 1 and counter.blocked == 1
        assert not blocked_network, blocked_network
        assert secret not in result_path.read_text()
        assert not any('authorization' in str(k).lower() for k in saved)
        assert Path(result['environment']['sys_executable']) == VENV[probe]
        assert all(Path(f).is_relative_to(directory) for f in Path(directory).rglob('*'))
        print('CASE_RESULT ' + json.dumps({'probe': probe, 'case': case, 'status': 'passed',
            'environment': result['environment'], 'send_observation': send, 'transport_trace': traces}), flush=True)
    faulthandler.cancel_dump_traceback_later()
    print('STAGE process_exit', flush=True)


class ProbeCases:
    def run_case(self, case):
        with tempfile.TemporaryDirectory(prefix='volcano-probe-offline-') as td:
            child_env = {k: v for k, v in os.environ.items()
                         if k in ('PATH', 'LANG', 'LC_ALL', 'TZ')}
            child_env['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
            process = subprocess.Popen([str(VENV[self.probe]), '-B', str(Path(__file__).resolve()),
                '--child', self.probe, case, td], cwd=ROOT, env=child_env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                out, err = process.communicate(timeout=48)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                out, err = process.communicate()
                self.fail('child timeout; reaped=%s\n%s\n%s' % (process.returncode, out, err))
            self.assertEqual(process.returncode, 0, out + '\n' + err)
            self.assertIn('STAGE process_exit', out)
            result = json.loads(next(line[12:] for line in out.splitlines() if line.startswith('CASE_RESULT ')))
            self.assertEqual(result['status'], 'passed')

    def test_success(self): self.run_case('success')
    def test_presend_error(self): self.run_case('presend')
    def test_connection_error(self): self.run_case('connection')
    def test_parse_error(self): self.run_case('parse')
    def test_second_send_blocked(self): self.run_case('second')
    def test_state_restored_after_error(self): self.run_case('restore')
    def test_temporary_output_and_secret_isolation(self): self.run_case('isolation')


class OfficeProbeTests(ProbeCases, unittest.TestCase):
    probe = 'office'
    def test_empty_content(self): self.run_case('empty')


class AssistantProbeTests(ProbeCases, unittest.TestCase):
    probe = 'assistant'


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child_case(*sys.argv[2:])
    else:
        unittest.main()
