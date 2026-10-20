#!/usr/bin/env python3
"""Two bounded protocol checks, each launched in its production interpreter."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from types import MethodType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
INTERPRETERS = {'office': ROOT / '.venvs/docops-pilot-01/bin/python',
                'assistant': ROOT / '.venvs/toolsandbox-pilot-01/bin/python'}


class ProbeSendLimitExceeded(RuntimeError):
    pass


def http_modules():
    """The installed SDK exposes httpx in v1 and httpx2 in the Office v3 SDK."""
    import httpx
    import openai._base_client as base
    sdk_http = getattr(base, 'httpx2', None) or getattr(base, 'httpx', None)
    if sdk_http is None:
        raise RuntimeError('sdk_http_module_not_exposed')
    return list(dict.fromkeys((httpx, sdk_http)))


def environment_record(probe):
    import openai
    modules = [openai, *http_modules()]
    if probe == 'office':
        import litellm
        import harbor.llms.lite_llm as harbor_llm
        modules += [litellm, harbor_llm]
    versions = {}
    for name in ('openai', 'httpx', 'httpx2', 'litellm', 'harbor'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'probe': probe, 'sys_executable': sys.executable,
            'python_version': platform.python_version(), 'versions': versions,
            'module_files': {m.__name__: m.__file__ for m in modules}}


class SendCounter:
    """One boundary per single HTTP request, including SDK retries/redirects.

    _send_single_request dispatches to the selected HTTP transport. Blocking
    happens before that method forwards the request. No response bodies or
    headers are inspected here. The two HTTP modules are distinct client paths,
    not nested wrappers of the same request.
    """
    def __init__(self, host, checkpoint=lambda: None):
        self.host = host
        self.checkpoint = checkpoint
        self.entered = self.forwarded = self.blocked = self.responses = 0
        self.coverage = []
        self.restored = False
        self.stack = ExitStack()

    def before(self, request):
        self.entered += 1
        if request.url.host != self.host or self.forwarded >= 1:
            self.blocked += 1
            self.checkpoint()
            raise ProbeSendLimitExceeded('probe_network_forwarding_blocked')
        self.forwarded += 1
        # Save the allowance before entering a potentially failing send.
        self.checkpoint()

    def __enter__(self):
        for module in http_modules():
            for cls, asynchronous in ((module.Client, False), (module.AsyncClient, True)):
                original = cls._send_single_request
                if asynchronous:
                    async def counted(client, request, _original=original):
                        self.before(request)
                        response = await _original(client, request)
                        self.responses += 1
                        self.checkpoint()
                        return response
                else:
                    def counted(client, request, _original=original):
                        self.before(request)
                        response = _original(client, request)
                        self.responses += 1
                        self.checkpoint()
                        return response
                self.stack.enter_context(patch.object(cls, '_send_single_request', counted))
                self.coverage.append(module.__name__ + ('.AsyncClient' if asynchronous else '.Client'))
        return self

    def __exit__(self, *exc):
        self.stack.__exit__(*exc)
        self.restored = True

    def snapshot(self):
        return {'boundary': 'http_client_single_request_transport_dispatch',
                'covered_clients': self.coverage, 'boundary_entries': self.entered,
                'forwarded_attempts': self.forwarded, 'blocked_attempts': self.blocked,
                'responses_received': self.responses,
                'remote_service_receipt': 'unknown', 'wrappers_restored': self.restored}


def safe_error(exc, stage):
    def locations(error):
        return [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno}
                for f in traceback.extract_tb(error.__traceback__)]
    result = {'stage': stage, 'exception_type': type(exc).__name__, 'stack': locations(exc)}
    if exc.__cause__ is not None:
        result['cause'] = {'exception_type': type(exc.__cause__).__name__,
                           'stack': locations(exc.__cause__)}
    return result


def load_credentials():
    from agent_workload_characterization.runners.smoke_launcher import load_credentials as load
    return load(provider_name='火山AI网关', model_key='deepseek-v4-flash',
                model_display_name='DeepSeek-V4-Flash')


def _probe(output, probe, *, credential_loader=None, route=None, progress=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema': 'volcano-protocol-probe-v2', 'probe': probe, 'status': 'partial',
              'stage': 'module_import', 'stages': [], 'parse_status': 'not_started',
              'log_directory': str(output.parent / 'probe-log'),
              'send_observation': None, 'timeout_s': 30, 'max_tokens': 1024,
              'business_tools_executed': 0, 'clients_closed': False}
    # An existing result is never permission for another request.
    with output.open('x') as stream:
        json.dump(result, stream)
    counter = None
    api_key = None
    start = time.monotonic()

    def save():
        if counter is not None:
            result['send_observation'] = counter.snapshot()
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if api_key:
            text = text.replace(api_key, '[REDACTED]')
        output.write_text(text + '\n')

    def stage(name):
        result['stage'] = name
        result['stages'].append({'name': name, 't_monotonic_ns': time.monotonic_ns()})
        save()
        if progress:
            progress(name)

    try:
        expected_prefix = INTERPRETERS[probe].parent.parent.resolve()
        if Path(sys.prefix).resolve() != expected_prefix:
            raise RuntimeError('probe_requires_its_production_interpreter')
        result['environment'] = environment_record(probe)
        stage('route_and_credentials')
        if route is None:
            if probe == 'office':
                from docops_measurement_validate_01_entry import configured_route, VOLCANO_PROFILE
                route = configured_route(VOLCANO_PROFILE)
            else:
                from toolsandbox_resource_pilot_01_entry import volcano_route
                route = volcano_route()
        api_base, api_key = (credential_loader or load_credentials)()
        if api_base != route['api_base']:
            raise ValueError('route_identity_changed')
        result['api_base'] = api_base
        result['request_model'] = ('openai/deepseek-v4-flash' if probe == 'office'
                                   else 'deepseek-v4-flash')
        import httpx
        counter = SendCounter(httpx.URL(api_base).host, checkpoint=save)
        with counter:
            if probe == 'office':
                _office(result, api_base, api_key, stage)
            else:
                _assistant(result, api_base, api_key, stage)
        if not result['clients_closed']:
            raise RuntimeError('probe_client_cleanup_not_confirmed')
        if counter.forwarded != 1 or counter.responses != 1 or counter.blocked:
            raise ValueError('protocol_send_evidence_not_exactly_one')
        result['status'] = 'passed'
        stage('complete')
    except BaseException as exc:
        result['status'] = 'failed'
        result['error'] = safe_error(exc, result.get('failure_stage', result['stage']))
        if result['parse_status'] == 'started':
            result['parse_status'] = 'failed'
    finally:
        result['wall_s'] = time.monotonic() - start
        if counter is None:
            # No request code is reachable until the boundary has been installed.
            result['send_observation'] = {'boundary_entries': 0, 'forwarded_attempts': 0,
                'blocked_attempts': 0, 'responses_received': 0,
                'remote_service_receipt': 'unknown',
                'zero_basis': 'failed_before_any_request_phase'}
        save()
    return result


def _office(result, api_base, api_key, stage):
    import litellm
    from tenacity import stop_after_attempt
    import docops_word_resource_01_entry as word
    old_env = {k: os.environ.get(k) for k in ('OPENAI_API_KEY', 'OPENAI_API_BASE')}
    original_completion = litellm.acompletion
    old_retries, old_suppress = litellm.num_retries, litellm.suppress_debug_info
    inner = None
    original_instance_call = None
    had_instance_call = False
    shared_stop = bound_call = None
    try:
        os.environ['OPENAI_API_KEY'], os.environ['OPENAI_API_BASE'] = api_key, api_base
        stage('agent_construction')
        agent = word.build_agent(Path(result['log_directory']), {
            'task_dir': str(ROOT / 'references/repos/DocOps/tasks/atomic__excel_001_budget_bucket_totals_seed'),
            'max_steps': 40, 'max_tokens': 1024,
            'model_route': {'api_base': api_base, 'request_model': 'openai/deepseek-v4-flash'}})
        inner = agent.llm._inner
        had_instance_call = 'call' in inner.__dict__
        original_instance_call = inner.__dict__.get('call')
        bound_call = inner.call
        shared_stop = bound_call.retry.stop
        # retry_with copies the retry controller; MethodType restores self.
        inner.call = MethodType(bound_call.retry_with(stop=stop_after_attempt(1)), inner)
        result['retry_policy'] = {'framework_attempts': 1, 'sdk_max_retries': 0}
        result['shared_retry_unchanged_during_probe'] = bound_call.retry.stop is shared_stop
        litellm.num_retries, litellm.suppress_debug_info = 0, True

        class RecorderContext:
            def point(self, name, attrs=None):
                if name == 'agent_action':
                    result['recorder_action'] = (attrs or {}).get('action')
        agent.recorder = RecorderContext()

        async def observe(*args, **kwargs):
            response = await original_completion(*args, **kwargs)
            choice = response['choices'][0]
            usage = getattr(response, 'usage', None)
            result['response_evidence'] = {
                'response_model': response.get('model'),
                'finish_reason': choice.get('finish_reason'),
                'content': choice['message'].get('content'),
                'usage': usage.model_dump() if usage is not None else None}
            stage('sdk_response_converted')
            return response
        litellm.acompletion = observe

        async def invoke():
            try:
                stage('LLM.call')
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    response = await agent.llm.call(
                        prompt=('Return one JSON action object with thought="protocol probe", '
                                'action="finish", tool_name=null, arguments={}, '
                                'final_message="protocol probe".'),
                        message_history=[], max_tokens=1024, timeout=30,
                        num_retries=0, max_retries=0, temperature=0)
                stage('harbor_response_converted')
                result['parse_status'] = 'started'
                stage('agent_action_parse')
                action = agent._parse_action(response.content)
                result['parsed_action'] = action.action
                if action.action != 'finish':
                    raise ValueError('unexpected_probe_action')
                result['parse_status'] = 'complete'
            except BaseException:
                result['failure_stage'] = result['stage']
                raise
            finally:
                stage('client_close')
                from litellm.llms.custom_httpx.async_client_cleanup import close_litellm_async_clients
                import openai
                try:
                    await close_litellm_async_clients()
                    cached = list(litellm.in_memory_llm_clients_cache.cache_dict.values())
                    sdk_clients = [c for c in cached if isinstance(c, openai.AsyncOpenAI)]
                    for client in sdk_clients:
                        if not client.is_closed():
                            await client.close()
                    result['clients_closed'] = all(c.is_closed() for c in sdk_clients)
                    result['cached_sdk_clients_closed'] = len(sdk_clients)
                except Exception as exc:
                    result['cleanup_error'] = safe_error(exc, 'client_close')
        asyncio.run(invoke())
        result['shared_retry_restored'] = bound_call.retry.stop is shared_stop
    except BaseException:
        result.setdefault('failure_stage', result['stage'])
        raise
    finally:
        if inner is not None:
            if had_instance_call:
                inner.call = original_instance_call
            else:
                inner.__dict__.pop('call', None)
            result['retry_instance_binding_restored'] = 'call' not in inner.__dict__ if not had_instance_call else inner.call is original_instance_call
        if bound_call is not None:
            result['shared_retry_restored'] = bound_call.retry.stop is shared_stop
        litellm.acompletion = original_completion
        litellm.num_retries, litellm.suppress_debug_info = old_retries, old_suppress
        for k, value in old_env.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value


def _assistant(result, api_base, api_key, stage):
    import openai
    from agent_workload_characterization.runners.toolsandbox_worker import construct_openai_role_clients
    clients = ()
    try:
        stage('client_construction')
        clients = construct_openai_role_clients(openai, base_url=api_base, api_key=api_key)
        result['retry_policy'] = {'sdk_max_retries': clients[0].max_retries, 'framework_attempts': 1}
        stage('SDK.create')
        response = clients[0].chat.completions.create(
            model='deepseek-v4-flash', max_tokens=1024, timeout=30,
            messages=[{'role': 'user', 'content': 'Protocol-only check. Call probe_noop with {"ok":true}.'}],
            tools=[{'type': 'function', 'function': {'name': 'probe_noop',
                'description': 'Synthetic protocol check; never executed.',
                'parameters': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                               'required': ['ok'], 'additionalProperties': False}}}],
            tool_choice={'type': 'function', 'function': {'name': 'probe_noop'}})
        stage('sdk_response_converted')
        choice = response.choices[0]
        calls = choice.message.tool_calls or []
        result['response_evidence'] = {'response_model': response.model,
            'finish_reason': choice.finish_reason,
            'usage': response.usage.model_dump() if response.usage else None,
            'tool_calls': [{'id': c.id, 'name': c.function.name, 'arguments': c.function.arguments} for c in calls]}
        result['parse_status'] = 'started'
        stage('tool_call_parse')
        if len(calls) != 1 or choice.finish_reason != 'tool_calls':
            raise ValueError('expected_one_tool_call')
        call = calls[0]
        arguments = json.loads(call.function.arguments)
        if not call.id or call.function.name != 'probe_noop' or arguments != {'ok': True}:
            raise ValueError('unexpected_tool_call')
        result['tool_call'] = {'id': call.id, 'function_name': call.function.name, 'arguments': arguments}
        result['parse_status'] = 'complete'
    except BaseException:
        result['failure_stage'] = result['stage']
        raise
    finally:
        stage('client_close')
        for client in clients:
            client.close()
        result['clients_closed'] = bool(clients) and all(c.is_closed() for c in clients)


def office_probe(output, **kwargs):
    return _probe(output, 'office', **kwargs)


def assistant_probe(output, **kwargs):
    return _probe(output, 'assistant', **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('probe', choices=('office', 'assistant'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = _probe(args.output, args.probe)
    except FileExistsError:
        print(json.dumps({'status': 'refused', 'reason': 'probe_record_already_exists'}))
        return 2
    print(json.dumps({k: result.get(k) for k in ('probe', 'status', 'stage', 'send_observation', 'error')}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
