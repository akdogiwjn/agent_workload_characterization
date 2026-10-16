import contextlib
import asyncio
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages'))
sys.path.insert(0, str(ROOT / 'references/repos/DocOps/harnesses'))
sys.path.insert(0, str(ROOT / 'src'))
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'

import docops_office_repeat_01_entry as batch  # noqa: E402
import docops_word_resource_01_entry as shared  # noqa: E402
from harbor.environments.base import ExecResult  # noqa: E402
from harbor.llms.base import LLMResponse  # noqa: E402
from harbor.models.metric.usage_info import UsageInfo  # noqa: E402
from harbor.models.verifier.result import VerifierResult  # noqa: E402
from harbor.environments.docker.docker import (  # noqa: E402
    _sanitize_docker_compose_project_name,
)
from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CounterSnapshot)


class FakeEnv:
    def __init__(self):
        self.stopped = 0
        self.uploads = []

    async def start(self, force_build=False):
        return None

    async def stop(self, delete):
        assert delete is True
        self.stopped += 1

    async def upload_file(self, source, target):
        self.uploads.append((str(source), target))

    async def exec(self, command, **kwargs):
        return ExecResult(stdout='{"ok":true}', stderr='', return_code=0)


class FakeLLM:
    def __init__(self, count_box):
        self.count_box = count_box

    async def call(self, *, logging_path=None, **kwargs):
        self.count_box[0] += 1
        if logging_path:
            Path(logging_path).parent.mkdir(parents=True, exist_ok=True)
            Path(logging_path).write_text('{"response_model":"fake"}')
        return LLMResponse(
            content='{"thought":"done","action":"finish","tool_name":null,'
                    '"arguments":{},"final_message":"done"}',
            model_name='fake-model',
            usage=UsageInfo(prompt_tokens=1, completion_tokens=1,
                            cache_tokens=0, cost_usd=0.0))


class FakeRuntime:
    _name_prefix = 'awc-fake'

    def __init__(self, fail_removal=False):
        self.fail_removal = fail_removal
        self.removal_calls = 0

    def _resolve_cgroup(self, handle):
        handle.cgroup_version = 'fake-v1'
        handle.cgroup_dir = None

    def read_counters(self, handle, t):
        return CounterSnapshot(scope='agent_container', scope_kind='agent_container',
            t_monotonic_ns=t, cpu_usage_usec=5, mem_current_bytes=10,
            mem_peak_bytes=11, read_status={'fake': 'ok'})

    def verify_removal(self, handle, timeout_s=30.0):
        self.removal_calls += 1
        return 'still_exists' if self.fail_removal else 'removed'


class FakeVerifier:
    async def verify(self):
        return VerifierResult(rewards={'reward': 0.0})


def fake_identity():
    return batch.build_identity({t['key']: 'sha256:' + str(i) * 64
                                 for i, t in enumerate(batch.TASKS, 1)})


def install_run_boundary_fakes(monkey_removal=False):
    envs = []
    call_counts = []
    runtime = FakeRuntime(fail_removal=monkey_removal)

    def build_env(session_id, trial_paths, config=None):
        env = FakeEnv()
        envs.append(env)
        return env

    real_build_agent = shared.build_agent

    def build_agent(logs_dir, config=None):
        box = [0]
        call_counts.append(box)
        agent = real_build_agent(logs_dir, config)
        agent.llm = FakeLLM(box)
        return agent

    patches = [
        patch.object(shared, 'build_environment', side_effect=build_env),
        patch.object(shared, 'build_agent', side_effect=build_agent),
        patch.object(shared, 'build_verifier', return_value=FakeVerifier()),
        patch.object(shared, 'build_runtime', return_value=runtime),
        patch.object(shared, 'compose_containers',
                     side_effect=lambda project: [('f' * 64, project + '-main-1')]),
        patch.object(shared, 'docker_image_id', side_effect=lambda ref, **kw:
                     fake_identity()['tasks'][next(i for i,t in enumerate(batch.TASKS)
                         if batch.image_ref(t['key']) == ref)]['image_id']),
    ]
    return patches, envs, call_counts, runtime


def test_plan_is_read_only_and_order_is_frozen():
    with tempfile.TemporaryDirectory() as tmp:
        real_plan = batch.plan_mode
        before = sorted(p.name for p in (ROOT / batch.RAW_DIR_REL).glob('*'))
        out = io.StringIO()
        old = sys.argv
        sys.argv = ['entry', '--plan']
        try:
            with contextlib.redirect_stdout(out), patch.object(batch, 'plan_mode',
                    side_effect=lambda: real_plan(Path(tmp))):
                assert batch.main() == 0
        finally:
            sys.argv = old
        plan = json.loads(out.getvalue())
        assert plan['registered_commit'] == batch.DOCOPS_COMMIT
        assert [row['tasks'] for row in plan['order']] == [list(x) for x in batch.ORDER]
        assert plan['attempt_count'] == 9
        assert plan['preserved_prior_stop_record'] is False
        assert plan['preparation_namespace_status'] == 'clear'
        assert plan['ready'] is True
        assert not list(Path(tmp).iterdir())
        assert before == sorted(p.name for p in (ROOT / batch.RAW_DIR_REL).glob('*'))


def test_registered_base_id_rejects_the_65_hex_typo_before_inspect():
    with patch.object(batch, 'BASE_ID', 'sha256:' + 'a' * 65), \
         patch.object(batch, 'inspect_image') as inspect:
        try:
            batch.verify_base()
        except batch.BatchError as exc:
            assert '64 lowercase hex' in str(exc)
        else:
            raise AssertionError('65-hex identity must be rejected')
        inspect.assert_not_called()


def test_batch_projection_uses_actual_events_for_embedded_json_and_last_return(tmp_path):
    from tests.test_docops_word_resource_01_entry import (
        FakeEnv, FakeLLM, FakeRuntime, FakeVerifierOk, STEP, FINISH)
    real_build = shared.build_agent
    def agent_factory(logs_dir, config=None):
        a = real_build(logs_dir, config)
        a.llm = FakeLLM(['extra text\n' + STEP, FINISH])
        return a
    cfg = batch.run_config(batch.TASKS[0]['key'], 0, 'fake:tag', 'sha256:' + 'f' * 64)
    plan = {'run_id': 'synthetic-measured', 'identity': {}, 'identity_sha256': 'a' * 64,
            'run_config': cfg, 'run_inputs': []}
    with patch.object(shared, 'build_environment', return_value=FakeEnv()), \
         patch.object(shared, 'build_runtime', return_value=FakeRuntime()), \
         patch.object(shared, 'build_agent', side_effect=agent_factory), \
         patch.object(shared, 'build_verifier', return_value=FakeVerifierOk()), \
         patch.object(shared, 'compose_containers', return_value=[('f'*64, 'synthetic-measured-main-1')]), \
         patch.object(shared, 'docker_image_id', return_value='sha256:' + 'f' * 64):
        summary = asyncio.run(shared.run_attempt(tmp_path, plan))
    rd = tmp_path / 'data/raw/generated' / cfg['collection'] / plan['run_id']
    evidence = batch.project_run_evidence(rd, summary)
    assert evidence['action_counts'] == {'call_tool': 1, 'finish': 1}
    assert evidence['tool_name_counts'] == {'get_task_metadata': 1}
    assert evidence['bootstrap_tool_counts_from_events'] == {'get_task_metadata': 1}
    assert evidence['tool_return_status_counts'] == {'ok_true': 1}
    assert evidence['measurement']['call_timing_status'] == 'complete'


def test_task_assets_and_shared_run_config_are_explicit():
    ids = {t['key']: 'sha256:' + ('a' if i == 0 else 'b' if i == 1 else 'c') * 64
           for i, t in enumerate(batch.TASKS)}
    identity = batch.build_identity(ids)
    assert identity['docops_commit'] == batch.DOCOPS_COMMIT
    assert len(identity['tasks']) == 3
    for task in identity['tasks']:
        paths = {f['path'] for f in task['files']}
        assert any(p.endswith('/instruction.md') for p in paths)
        assert any(p.endswith('/task.toml') for p in paths)
        assert any(p.endswith('/environment/Dockerfile') for p in paths)
        assert any(p.endswith('/tests/test.sh') for p in paths)
        assert any(p.endswith('/tests/test_outputs.py') for p in paths)
    assert identity['tools']['word_tools_not_applicable_to_excel_ppt_pdf'] == batch.WORD_ONLY_TOOLS
    cfg = batch.run_config(batch.TASKS[0]['key'], 0, 'image:tag', ids[batch.TASKS[0]['key']])
    assert Path(cfg['task_dir']).name == batch.TASKS[0]['key']
    assert cfg['input_asset'].endswith('.xlsx')
    assert cfg['max_steps'] == 40 and cfg['network'] == 'none'


def test_image_build_is_pull_free_and_network_is_disabled(tmp_path):
    class Completed:
        returncode = 0
        stdout = 'built'
        stderr = ''

    key = batch.TASKS[0]['key']
    ref = batch.image_ref(key)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(batch, 'ROOT', tmp_path))
        stack.enter_context(patch.object(batch, 'inspect_image',
                                          side_effect=[None, ('sha256:' + 'a' * 64,
                                                             'linux/arm64')]))
        run = stack.enter_context(patch.object(batch.subprocess, 'run',
                                               return_value=Completed()))
        info = batch.build_task_image(key, ref, tmp_path / 'env', timeout=600,
                                      log_label='test')
    argv = run.call_args.args[0]
    assert '--pull=false' in argv and '--network=none' in argv
    assert info['image']['platform'] == 'linux/arm64'


def test_create_approval_refuses_existing_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'APPROVAL.json'
        path.write_text('{}')
        try:
            batch.create_approval(path, 'a' * 64)
        except batch.BatchError:
            pass
        else:
            raise AssertionError('existing approval must not be overwritten')
        assert path.read_text() == '{}'


def test_batch_approval_current_identity_passes_and_stale_identity_fails(tmp_path):
    path = tmp_path / 'APPROVAL.json'
    approval = batch.create_approval(path, 'a' * 64)
    assert approval['user_approval'] == 'approved'
    assert batch.validate_approval(path, 'a' * 64)
    assert not batch.validate_approval(path, 'b' * 64)


def test_real_batch_entry_runs_nine_finish_loops_reward_zero_continues(tmp_path):
    before = sorted(p.name for p in (ROOT / batch.RAW_DIR_REL).glob('*'))
    patches, envs, calls, runtime = install_run_boundary_fakes()
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        identity = fake_identity()
        result = batch.run_batch(tmp_path, {}, identity,
                                 start_monotonic=time.monotonic(), docker_enabled=False)
    assert len(result['results']) == 9
    assert all(r['status'] == 'executed' and r['reward'] == 0.0 for r in result['results']), result
    assert [r['task_key'] for r in result['results']] == [k for row in batch.ORDER for k in row]
    assert len({r['run_id'] for r in result['results']}) == 9
    assert all(box[0] == 1 for box in calls)  # finish ends each actual Agent loop
    assert all(e.stopped == 1 for e in envs)
    assert runtime.removal_calls == 9
    for run in result['results']:
        run_dir = batch._run_dir(tmp_path, run['run_id'])
        disk = json.loads((run_dir / 'summary.json').read_text())
        assert disk['task_key'] == run['task_key']
        assert disk['max_steps'] == 40
        assert disk['outcome']['phases']['agent']['status'] == 'finish'
        assert disk['outcome']['phases']['verifier']['reward'] == 0.0
        assert batch.verify_run_archive(run_dir) == (True, [])
    assert before == sorted(p.name for p in (ROOT / batch.RAW_DIR_REL).glob('*'))


def test_cleanup_failure_stops_and_marks_remaining_not_executed(tmp_path):
    patches, envs, calls, runtime = install_run_boundary_fakes(monkey_removal=True)
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = batch.run_batch(tmp_path, {}, fake_identity(),
                                 start_monotonic=time.monotonic(), docker_enabled=False)
    assert len(result['results']) == 9
    assert result['results'][0]['status'] == 'failed'
    assert all(row['status'] == 'not_executed' for row in result['results'][1:])
    assert len(calls) == 1 and calls[0][0] == 1, {'calls': calls, 'results': result}


def test_input_hash_mismatch_is_not_accepted(tmp_path):
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    (run_dir / 'sample').write_text('changed')
    (run_dir / 'manifest.json').write_text(json.dumps({'outputs': [
        {'path': 'sample', 'bytes': 1, 'sha256': '0' * 64}]}))
    ok, bad = batch.verify_run_archive(run_dir)
    assert not ok and bad == ['sample']


def test_execute_entry_fake_runtime_keeps_all_outputs_in_temp_namespace(tmp_path):
    """Exercise execute -> approval -> batch loop -> shared run_attempt with
    only external image/preflight/model/container edges replaced."""
    original_root = batch.ROOT
    before = sorted(p.name for p in (original_root / batch.RAW_DIR_REL).glob('*'))
    identity = fake_identity()
    ids = {task['key']: task['image_id'] for task in identity['tasks']}
    env_dir = tmp_path / batch.ENV_DIR_REL
    env_dir.mkdir(parents=True)
    stop_path = env_dir / 'execution-stop.json'
    stop_path.write_text(json.dumps({'schema': 'docops-office-repeat-stop-v1',
        'status': 'stopped', 'detail': 'base image identity/platform mismatch: ' + batch.BASE_ID}))
    stop_bytes = stop_path.read_bytes()

    def fake_build(key, ref, env_root, *, timeout, log_label):
        log = env_root / 'image-builds' / f'{batch.task_spec(key)["short"]}-{log_label}.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('fake offline build record')
        return {'task_key': key, 'image': {'reference': ref, 'id': ids[key],
                                            'platform': 'linux/arm64'},
                'log': {'path': log.relative_to(tmp_path).as_posix(),
                        'bytes': log.stat().st_size, 'sha256': batch.sha256(log)}}

    async def fake_preflight(key, config, env_root, timeout_s=batch.PREFLIGHT_S):
        return {'task_key': key, 'status': 'passed',
                'container_removal': 'removed', 'asset_readable': config['input_asset'],
                'metadata_uploaded': True, 'runtime_uploaded': True}

    patches, envs, calls, runtime = install_run_boundary_fakes()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(batch, 'ROOT', tmp_path))
        stack.enter_context(patch.object(batch, 'plan_mode',
                                          return_value={'ready': True,
                                                        'preserved_prior_stop_record': True}))
        stack.enter_context(patch.object(batch, 'verify_base',
                                          return_value={'id': batch.BASE_ID,
                                                        'platform': 'linux/arm64'}))
        stack.enter_context(patch.object(batch, 'build_task_image', side_effect=fake_build))
        stack.enter_context(patch.object(batch, 'preflight_one', side_effect=fake_preflight))
        stack.enter_context(patch.object(batch, 'inspect_image',
                            side_effect=lambda ref: (next(t['image_id'] for t in identity['tasks']
                                if t['image_ref'] == ref), 'linux/arm64')))
        stack.enter_context(patch.object(batch, 'build_identity', return_value=identity))
        stack.enter_context(patch.object(batch, 'load_model_credential'))
        stack.enter_context(patch.dict(os.environ, {}, clear=False))
        for p in patches:
            stack.enter_context(p)
        result = batch.execute()
    assert result == 0
    report = tmp_path / batch.REPORT_DIR_REL
    raw = tmp_path / batch.RAW_DIR_REL
    env = tmp_path / batch.ENV_DIR_REL
    summary = json.loads((report / 'batch-summary.json').read_text())
    manifest = json.loads((report / 'batch-manifest.json').read_text())
    assert len(summary['results']) == 9
    assert all(row['status'] == 'executed' for row in summary['results'])
    assert all(row['reward'] == 0.0 for row in summary['results'])
    assert (report / 'APPROVAL.json').is_file()
    assert len(list(raw.iterdir())) == 9
    assert (env / 'frozen-identity.json').is_file()
    assert stop_path.read_bytes() == stop_bytes
    correction = json.loads((env / 'base-image-correction.json').read_text())
    assert correction['historical_files_modified'] is False
    assert correction['corrected_base_id'] == batch.BASE_ID
    for record in manifest['outputs']:
        path = tmp_path / record['path']
        assert path.stat().st_size == record['bytes']
        assert batch.sha256(path) == record['sha256']
    assert before == sorted(p.name for p in (original_root / batch.RAW_DIR_REL).glob('*'))
    assert len(calls) == 9 and all(count[0] == 1 for count in calls)


def test_preflight_one_real_path_imports_harbor_name_and_cleans_up(tmp_path):
    events = []
    model_calls = []
    task = batch.TASKS[0]
    project = _sanitize_docker_compose_project_name('preflight-' + task['short'])

    class PreflightEnv:
        async def start(self, force_build=False):
            events.append(('start', force_build))

        async def upload_file(self, source, target):
            assert Path(source).is_file()
            events.append(('upload', target))

        async def exec(self, command, **kwargs):
            if command.startswith('python3 -c '):
                events.append(('container_check', command))
                return ExecResult(stdout='preflight_ok\n', stderr='', return_code=0)
            events.append(('setup_exec', command))
            return ExecResult(stdout='', stderr='', return_code=0)

        async def stop(self, delete):
            assert delete is True
            events.append(('stop', delete))

    class PreflightRuntime:
        def _resolve_cgroup(self, handle):
            events.append(('container_handle', handle.container_id))
            handle.cgroup_version = 'fake-v1'
            handle.cgroup_dir = None

        def verify_removal(self, handle, timeout_s=30.0):
            events.append(('verify_removal', handle.container_id, timeout_s))
            return 'removed'

    env = PreflightEnv()
    config = batch.run_config(task['key'], 0, batch.image_ref(task['key']),
                              'sha256:' + 'a' * 64)
    real_build_agent = shared.build_agent

    def build_real_agent(logs_dir, config=None):
        events.append(('agent_build', str(logs_dir)))
        agent = real_build_agent(logs_dir, config)

        async def no_model_call(*args, **kwargs):
            model_calls.append((args, kwargs))
            raise AssertionError('preflight must not invoke the model')

        agent.llm.call = no_model_call
        return agent

    with patch.object(shared, 'build_environment', side_effect=lambda *a, **k: env), \
         patch.object(shared, 'compose_containers', side_effect=lambda name: (
             events.append(('ownership_query', name)) or
             [('c' * 64, name + '-main-1')])), \
         patch.object(shared, 'build_runtime', return_value=PreflightRuntime()), \
         patch.object(shared, 'build_agent', side_effect=build_real_agent):
        result = asyncio.run(batch.preflight_one(
            task['key'], config, tmp_path / 'isolated-env', timeout_s=10))

    names = [event[0] for event in events]
    assert result['status'] == 'passed', result
    assert result['container_removal'] == 'removed'
    assert result['container']['name'] == project + '-main-1'
    assert result['asset_readable'] == config['input_asset']
    assert result['metadata_uploaded'] and result['runtime_uploaded']
    assert model_calls == []
    assert names.index('start') < names.index('ownership_query')
    assert names.index('ownership_query') < names.index('container_handle')
    assert names.index('container_handle') < names.index('agent_build')
    assert names.index('agent_build') < names.index('container_check')
    assert names.index('container_check') < names.index('stop')
    assert names.index('stop') < names.index('verify_removal')
    assert events[names.index('ownership_query')][1] == project
    assert {p.name for p in (tmp_path / 'isolated-env').iterdir()} == {'preflight'}

