#!/usr/bin/env python3
"""Directed tests for the DOCOPS-WORD-RESOURCE-01 official entry (v2).

Real-entry call chain with fake model/environment/runtime transports. v2 adds
the offline-review counter-examples: startup-failure cleanup/archive, real
VerifierResult.rewards interface, finish vs steps_exhausted classification,
identity/image gating, infra-failure exit codes, and archive completeness
(ATTEMPT_COMPLETED + llm_call_* in manifest, archive_done persisted on disk).
"""
import asyncio
import json
import os
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / '.venvs/docops_pilot_01_placeholder'.replace(
    'docops_pilot_01_placeholder', 'docops-pilot-01/lib/python3.12/site-packages')))
sys.path.insert(0, str(ROOT / 'references/repos/DocOps/harnesses'))
sys.path.insert(0, str(ROOT / 'src'))

import docops_word_resource_01_entry as entry  # noqa: E402
_ORIGINAL_FROZEN_IDENTITY_SHA = entry.frozen_identity_sha
from harbor.environments.base import ExecResult  # noqa: E402
from harbor.llms.base import LLMResponse  # noqa: E402
from harbor.models.metric.usage_info import UsageInfo  # noqa: E402
from harbor.models.verifier.result import VerifierResult  # noqa: E402
from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CounterSnapshot)

FAKE_CID = 'f' * 64
USAGE = UsageInfo(prompt_tokens=1, completion_tokens=1, cache_tokens=0, cost_usd=0.0)


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)

    async def call(self, *, prompt, message_history, logging_path=None, **kw):
        content = self.script.pop(0)
        if logging_path is not None:
            Path(logging_path).parent.mkdir(parents=True, exist_ok=True)
            Path(logging_path).write_text(json.dumps({'fake': True}))
        return LLMResponse(content=content, model_name='fake-model', usage=USAGE)


class FakeAgent:
    def __init__(self, logs_dir):
        self.logs_dir = Path(logs_dir)
        self.llm = FakeLLM([])
        self.max_steps = 12
        self.setup_called = False

    async def setup(self, environment):
        self.setup_called = True
        await environment.upload_file('document_tools_runtime.py', '/root/document_tools_runtime.py')

    async def run(self, instruction, environment, context):
        environment.run_order.append('run')
        context.n_input_tokens = 10
        context.n_output_tokens = 4
        context.n_cache_tokens = 0
        context.cost_usd = 0.0


class SlowAgent(FakeAgent):
    async def run(self, instruction, environment, context):
        await asyncio.sleep(30)


from agent_workload_characterization.runners.docops_word_agent import DocOpsWordAgent


class RealLoopAgent(DocOpsWordAgent):
    """The REAL DocumentToolsAgent with a scripted fake LLM."""

    def __init__(self, logs_dir):
        super().__init__(logs_dir=Path(logs_dir), model_name=entry.MODEL_REQUEST_ID,
                         api_base=entry.API_BASE,
                         metadata_path=entry.TASK_DIR / 'environment/task_metadata.json')

    def set_script(self, script):
        self.llm = FakeLLM(script)
        self.max_steps = 6

    async def run(self, instruction, environment, context):
        environment.run_order.append('run')
        await super().run(instruction, environment, context)


class FakeEnv:
    def __init__(self, fail_start=False):
        self.stopped = []
        self.uploads = []
        self.run_order = []
        self.fail_start = fail_start

    async def start(self, force_build=False):
        if self.fail_start:
            raise RuntimeError('startup exploded')

    async def exec(self, command, **kw):
        return ExecResult(stdout='{"ok": true}', stderr='', return_code=0)

    async def stop(self, delete):
        self.stopped.append(delete)

    async def upload_file(self, source, target):
        self.uploads.append((str(source), str(target)))
        self.run_order.append('upload')

    async def upload_dir(self, *a, **kw):
        pass

    async def download_dir(self, *a, **kw):
        pass


class FakeVerifierOk:
    async def verify(self):
        # REAL Harbor interface: VerifierResult(rewards={"reward": 1.0})
        return VerifierResult(rewards={'reward': 1.0})


class FakeVerifierBoom:
    async def verify(self):
        raise RuntimeError('verifier infra exploded')


class FakeRuntime:
    """Replaces DockerCliRuntime: no docker calls at all."""

    _name_prefix = 'awc-fake'

    def read_counters(self, handle, t):
        return CounterSnapshot(scope='agent_container', scope_kind='agent_container',
                               t_monotonic_ns=t, cpu_usage_usec=1, mem_current_bytes=1,
                               mem_peak_bytes=1, read_status={'fake': 'ok'})

    def _resolve_cgroup(self, handle):
        handle.cgroup_version = 'v1-fake'
        handle.cgroup_dir = None

    def verify_removal(self, handle, timeout_s=30.0):
        return 'removed'


def install_fakes(fake_agent=None, fake_verifier=None, fail_start=False):
    """fake_agent: RealLoopAgent with set_script, or a plain FakeAgent subclass."""
    env = FakeEnv(fail_start=fail_start)

    def fake_build_environment(session_id, trial_paths, config=None):
        return env

    holder = {}

    def fake_build_agent(logs_dir, config=None):
        if fake_agent is not None:
            a = fake_agent(logs_dir)
            holder['agent'] = a
            return a
        a = FakeAgent(logs_dir)
        holder['agent'] = a
        return a

    def fake_build_verifier(task, trial_paths, environment):
        return fake_verifier or FakeVerifierOk()

    def fake_compose_containers(project):
        return [(FAKE_CID, project + '-main-1')]

    def fake_docker_image_id(reference, timeout_s=30.0):
        return entry.TASK_IMAGE_ID_EXPECTED

    entry.build_environment = fake_build_environment
    entry.build_agent = fake_build_agent
    entry.build_verifier = fake_build_verifier
    entry.compose_containers = fake_compose_containers
    entry.docker_image_id = fake_docker_image_id
    entry.build_runtime = lambda config=None: FakeRuntime()
    return env, holder


_ORIG_BUDGETS = {k: getattr(entry, k) for k in (
    'AGENT_BUDGET_S', 'VERIFIER_BUDGET_S', 'START_BUDGET_S', 'STOP_BUDGET_S',
    'TOTAL_WALL_S', 'CLEANUP_RESERVE_S', 'SAMPLE_INTERVAL_S')}


def shrink_budgets():
    entry.AGENT_BUDGET_S = 2.0
    entry.VERIFIER_BUDGET_S = 2.0
    entry.START_BUDGET_S = 5.0
    entry.STOP_BUDGET_S = 5.0
    entry.TOTAL_WALL_S = 60.0
    entry.CLEANUP_RESERVE_S = 5.0
    entry.SAMPLE_INTERVAL_S = 0.05


def restore_budgets():
    for k, v in _ORIG_BUDGETS.items():
        setattr(entry, k, v)


def run_attempt(tmp, run_id='20260101T000000Z-test'):
    plan = {'run_id': run_id, 'identity_sha256': 'x' * 64,
            'identity': {'files': {
                'task_toml': {'sha256': 'a'},
                'instruction': {'sha256': 'b'},
                'task_metadata': {'sha256': 'd'},
                'input_docx': {'sha256': 'c'}}}}
    return asyncio.run(entry.run_attempt(Path(tmp), plan))


def run_dir_of(tmp, run_id='20260101T000000Z-test'):
    return Path(tmp) / 'data/raw/generated' / entry.COLLECTION / run_id


FINISH = ('{"thought":"done","action":"finish","tool_name":null,"arguments":{},'
          '"final_message":"ok"}')
STEP = ('{"thought":"again","action":"call_tool","tool_name":"get_task_metadata",'
        '"arguments":{},"final_message":null}')


def test_plan_mode_zero_side_effects():
    with tempfile.TemporaryDirectory() as tmp:
        p = entry.plan_mode(Path(tmp))
        assert len(p['identity']['files']) == 24
        # The shared entry has changed for explicit multi-task configuration;
        # the historical DOCOPS-04 freeze must not authorize the new code.
        assert not p['identity_matches_frozen']
        assert entry.COLLECTION == 'DOCOPS-WORD-RESOURCE-04'
        assert entry.MAX_STEPS == 40
        assert p['identity']['budget']['max_steps'] == 40
        assert p['identity']['execution_interface']['approval_flag'] == \
            '--i-approve-the-docops-word-resource-04'
        assert p['identity']['state_paths']['attempt_root'] == \
            'data/raw/generated/DOCOPS-WORD-RESOURCE-04/<run_id>/'
        assert p['identity']['state_paths']['approval'] == \
            'reports/resource/DOCOPS-WORD-RESOURCE-04/APPROVAL.json'
        assert p['existing_attempts'] == []
        assert not (Path(tmp) / "data/raw/generated" / entry.COLLECTION).exists()
        assert not (Path(tmp) / 'reports/resource' / entry.COLLECTION).exists()


def test_finish_real_rewards_and_archive():
    def make_agent(logs_dir):
        a = RealLoopAgent(logs_dir)
        a.set_script([STEP.replace('again', 'copy'), FINISH])
        return a

    with tempfile.TemporaryDirectory() as tmp:
        install_fakes(fake_agent=make_agent)
        shrink_budgets()
        s = run_attempt(tmp)
        rd = run_dir_of(tmp)
        # real rewards interface: reward non-null
        v = s['outcome']['phases']['verifier']
        assert v['status'] == 'completed' and v['reward'] == 1.0
        assert v['rewards'] == {'reward': 1.0}
        # finish classification
        assert s['outcome']['phases']['agent']['status'] == 'finish'
        # exactly 2 model calls, all hashed in manifest
        calls = list((rd / 'agent').glob('llm_call_*.json'))
        assert len(calls) == 2
        mf = json.loads((rd / 'manifest.json').read_text())
        mf_paths = {o['path'] for o in mf['outputs']}
        assert 'ATTEMPT_COMPLETED.json' in mf_paths
        assert 'ATTEMPT_STARTED.json' in mf_paths
        assert any(p.startswith('agent/llm_call_') for p in mf_paths)
        assert 'summary.json' in mf_paths
        # archive_done persisted in the ON-DISK summary events
        disk = json.loads((rd / 'summary.json').read_text())
        assert disk['events'][-1]['phase'] == 'archive_done'
        assert s['outcome']['infra_failures'] == []
        coverage = json.loads((rd / 'measurement.json').read_text())
        assert coverage['call_timing_status'] == 'complete'
        assert coverage['expected_requests'] == 2
        assert coverage['expected_tools_including_bootstrap'] == 2
        assert coverage['tool_spans']['spans']['tool_call']['bootstrap'] == 1
        assert 'agent/events.jsonl' in mf_paths and 'environment.json' in mf_paths
        assert 'measurement.json' in mf_paths


def test_steps_exhausted_classification():
    def make_agent(logs_dir):
        a = RealLoopAgent(logs_dir)
        a.set_script([STEP] * 6)  # never finish -> max_steps exhausted
        return a

    with tempfile.TemporaryDirectory() as tmp:
        install_fakes(fake_agent=make_agent)
        shrink_budgets()
        s = run_attempt(tmp)
        assert s['outcome']['phases']['agent']['status'] == 'steps_exhausted'


def test_startup_failure_still_cleans_and_archives():
    """Offline-review counter-example: startup exception must not skip cleanup,
    summary or manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        env, _ = install_fakes(fail_start=True)
        shrink_budgets()
        s = run_attempt(tmp)
        assert any(f.startswith('startup_or_run:') for f in s['outcome']['infra_failures'])
        # cleanup still executed
        assert env.stopped == [True]
        # summary + manifest + attempt files still produced
        rd = run_dir_of(tmp)
        assert (rd / 'summary.json').exists()
        assert (rd / 'manifest.json').exists()
        assert (rd / 'ATTEMPT_COMPLETED.json').exists()
        disk = json.loads((rd / 'summary.json').read_text())
        assert disk['events'][-1]['phase'] == 'archive_done'


def test_verifier_infra_error_separated():
    def make_agent(logs_dir):
        a = RealLoopAgent(logs_dir)
        a.set_script([STEP, FINISH])
        return a

    with tempfile.TemporaryDirectory() as tmp:
        install_fakes(fake_agent=make_agent, fake_verifier=FakeVerifierBoom())
        shrink_budgets()
        s = run_attempt(tmp)
        v = s['outcome']['phases']['verifier']
        assert v['status'] == 'verifier_infra_error'
        assert 'verifier:RuntimeError' in s['outcome']['infra_failures']
        assert s['outcome']['phases']['agent']['status'] == 'finish'


def test_agent_timeout_stops_and_cleans():
    with tempfile.TemporaryDirectory() as tmp:
        env, _ = install_fakes(fake_agent=SlowAgent)
        shrink_budgets()
        entry.AGENT_BUDGET_S = 0.5
        s = run_attempt(tmp)
        assert s['outcome']['phases']['agent']['status'] == 'agent_timeout'
        assert env.stopped == [True]
        assert (run_dir_of(tmp) / 'ATTEMPT_COMPLETED.json').exists()


def _run_main(argv, tmp):
    old = sys.argv
    sys.argv = ['entry'] + argv + ['--collection-root', tmp]
    original_frozen = entry.frozen_identity_sha
    if original_frozen is _ORIGINAL_FROZEN_IDENTITY_SHA:
        entry.frozen_identity_sha = lambda: entry.identity_digest(entry.build_identity())
    try:
        return entry.main()
    finally:
        entry.frozen_identity_sha = original_frozen
        sys.argv = old


def write_approval(tmp, **overrides):
    path = Path(tmp) / 'reports/resource' / entry.COLLECTION / 'APPROVAL.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    approval = {'schema': 'docops-single-run-approval-v1',
                'collection': entry.COLLECTION, 'user_approval': 'approved',
                'identity_sha256': entry.identity_digest(entry.build_identity())}
    approval.update(overrides)
    path.write_text(json.dumps(approval))
    return path


def test_approval_is_not_an_attempt_and_main_runs_with_fakes():
    restore_budgets()
    with tempfile.TemporaryDirectory() as tmp:
        env, _ = install_fakes()
        approval_path = write_approval(tmp)
        original = approval_path.read_bytes()
        p = entry.plan_mode(Path(tmp))
        assert p['existing_namespace_records'] == []
        assert p['approval_status'] == 'valid' and not p['ready_for_execution']
        os.environ['DEEPSEEK_API_KEY'] = 'test-key-for-gate'
        assert _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp) == 0
        assert env.stopped == [True]
        runs = list((Path(tmp) / 'data/raw/generated' / entry.COLLECTION).iterdir())
        assert len(runs) == 1 and (runs[0] / 'ATTEMPT_STARTED.json').exists()
        assert approval_path.read_bytes() == original
        assert _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp) == 3


def test_missing_invalid_stale_and_consumed_approval_refused_before_docker():
    from unittest.mock import patch
    restore_budgets()
    old_identity = json.loads((ROOT / 'env/docops-arm64-word001/frozen-identity-03.json').read_text())['identity_sha256']
    cases = (None, {'identity_sha256': '0' * 64},
             {'identity_sha256': old_identity},
             {'collection': 'DOCOPS-WORD-RESOURCE-02'},
             {'user_approval': 'pending'}, {'schema': 'wrong'},
             {'entry_invocation': {'attempt_started': False}}, 'malformed')
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(entry, 'docker_image_id') as image, \
                patch.object(entry, 'run_attempt') as attempt:
            if case == 'malformed':
                write_approval(tmp).write_text('{')
            elif case is not None:
                write_approval(tmp, **case)
            assert _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp) == 10
            image.assert_not_called()
            attempt.assert_not_called()
            assert not (Path(tmp) / 'data/raw/generated' / entry.COLLECTION).exists()


def test_approval_does_not_exempt_other_namespace_records():
    from unittest.mock import patch
    restore_budgets()
    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(entry, 'docker_image_id') as image:
        approval_path = write_approval(tmp)
        (approval_path.parent / 'run-report.json').write_text('{}')
        assert entry.plan_mode(Path(tmp))['existing_namespace_records'] == ['run-report.json']
        assert _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp) == 3
        image.assert_not_called()


def test_execute_gates_and_exit_codes():
    restore_budgets()  # identity binds budget constants: use frozen production values
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        # gate: missing approval flag
        assert _run_main(['--execute'], tmp) == 2
        # gate: existing attempt
        base = Path(tmp) / 'data/raw/generated' / entry.COLLECTION
        base.mkdir(parents=True)
        (base / 'old').mkdir()
        assert _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp) == 3
        (base / 'old').rmdir()
        # gate: identity mismatch
        real_frozen_reader = entry.frozen_identity_sha
        real_frozen = real_frozen_reader()
        entry.frozen_identity_sha = lambda: '0' * 64
        code = _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp)
        entry.frozen_identity_sha = real_frozen_reader
        assert code == 4
        write_approval(tmp)
        # gate: actual image id mismatch (identity matches, image doesn't)
        real_di = entry.docker_image_id
        entry.docker_image_id = lambda ref: 'sha256:' + 'b' * 64
        code = _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp)
        entry.docker_image_id = real_di
        assert code == 5
        # full run with fakes + a startup failure -> infra failure -> exit 7
        install_fakes(fail_start=True)
        os.environ['DEEPSEEK_API_KEY'] = 'test-key-for-gate'
        code = _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp)
        assert code == 7
    # clean run in a FRESH root (the failed run above left an attempt dir) -> exit 0
    with tempfile.TemporaryDirectory() as tmp2:
        install_fakes()
        write_approval(tmp2)
        code = _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp2)
        assert code == 0


def test_outputs_isolated_from_real_collection():
    import hashlib
    real_dir = ROOT / 'data/raw/generated' / entry.COLLECTION
    def snapshot(directory):
        if not directory.exists():
            return None
        return {p.relative_to(directory).as_posix():
                (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in directory.rglob('*') if p.is_file()}
    before = snapshot(real_dir)
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        shrink_budgets()
        run_attempt(tmp)
        assert snapshot(real_dir) == before


def test_manifest_hash_consistency():
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        shrink_budgets()
        run_attempt(tmp)
        rd = run_dir_of(tmp)
        mf = json.loads((rd / 'manifest.json').read_text())
        assert mf['schema'] == 'docops-word-resource-01-run-manifest-v2'
        for o in mf['outputs']:
            p = rd / o['path']
            assert p.stat().st_size == o['bytes'], o['path']
            assert hashlib.sha256(p.read_bytes()).hexdigest() == o['sha256'], o['path']


def test_setup_called_before_run():
    def make_agent(logs_dir):
        a = RealLoopAgent(logs_dir)
        a.set_script([FINISH])
        return a

    with tempfile.TemporaryDirectory() as tmp:
        env, holder = install_fakes(fake_agent=make_agent)
        shrink_budgets()
        s = run_attempt(tmp)
        # official setup ran and uploaded the runtime BEFORE the agent run
        assert env.uploads and env.uploads[0][1] == '/root/document_tools_runtime.py'
        assert env.run_order[-1] == 'run'
        assert env.run_order[:-1] == ['upload', 'upload', 'upload']
        assert s['outcome']['phases']['agent']['status'] == 'finish'


def test_work_budget_exhausted_cleanup_still_runs():
    """Offline-review counter-example: after the WORK deadline is exhausted the
    stop timeout must come from the cleanup (total-wall) deadline, not be 0."""
    with tempfile.TemporaryDirectory() as tmp:
        env, _ = install_fakes(fake_agent=SlowAgent)
        restore_budgets()
        # work deadline already ~exhausted: total == reserve + tiny margin
        entry.TOTAL_WALL_S = entry.CLEANUP_RESERVE_S + 0.5
        entry.AGENT_BUDGET_S = 1200.0
        entry.SAMPLE_INTERVAL_S = 0.02
        s = run_attempt(tmp)
        assert s['outcome']['phases']['agent']['status'] == 'agent_timeout'
        # cleanup executed with a nonzero window from the total-wall deadline
        assert env.stopped == [True]
        evs = [e['phase'] for e in s['events']]
        assert 'harbor_stop_done' in evs and 'removal_verified' in evs
        assert (run_dir_of(tmp) / 'summary.json').exists()


def test_container_mismatch_still_archives():
    """Offline-review counter-example: ownership mismatch after cid was obtained
    must still clean AND produce summary/manifest (no AttributeError)."""
    with tempfile.TemporaryDirectory() as tmp:
        env, _ = install_fakes()
        real_cc = entry.compose_containers
        entry.compose_containers = lambda project: [(FAKE_CID, 'someone-else-main-1')]
        try:
            shrink_budgets()
            s = run_attempt(tmp)
        finally:
            entry.compose_containers = real_cc
        assert any(f.startswith('startup_or_run:') for f in s['outcome']['infra_failures'])
        assert env.stopped == [True]
        rd = run_dir_of(tmp)
        assert (rd / 'summary.json').exists() and (rd / 'manifest.json').exists()
        assert (rd / 'ATTEMPT_COMPLETED.json').exists()
        disk = json.loads((rd / 'summary.json').read_text())
        assert disk['events'][-1]['phase'] == 'archive_done'
        assert disk['container'] is None  # handle never built; no crash


def test_exit_8_agent_error_and_verifier_timeout():
    class BoomAgent(FakeAgent):
        async def run(self, instruction, environment, context):
            raise RuntimeError('agent crashed')

    restore_budgets()
    os.environ['DEEPSEEK_API_KEY'] = 'test-key-for-gate'
    # agent_error path end-to-end (no budget constant touched: identity must match)
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes(fake_agent=BoomAgent)
        write_approval(tmp)
        code = _run_main(['--execute', '--i-approve-the-docops-word-resource-04'], tmp)
        assert code == 8
        base = Path(tmp) / 'data/raw/generated' / entry.COLLECTION
        rd = next(d for d in base.iterdir() if d.name.endswith('-word001'))
        disk = json.loads((rd / 'summary.json').read_text())
        assert disk['outcome']['phases']['agent']['status'] == 'agent_error'
        # verifier still ran after the agent error (guarded section)
        assert disk['outcome']['phases']['verifier']['status'] == 'completed'
    # verifier_timeout path: budgets are identity-bound, so exercise the pure
    # adjudicator directly with a real-shaped summary
    assert entry.exit_code_for({'outcome': {'infra_failures': [], 'phases': {
        'agent': {'status': 'finish'},
        'verifier': {'status': 'verifier_timeout'}}}}) == 8
    assert entry.exit_code_for({'outcome': {'infra_failures': [], 'phases': {
        'agent': {'status': 'agent_timeout'},
        'verifier': {'status': 'completed'}}}}) == 0
    assert entry.exit_code_for({'outcome': {'infra_failures': ['x'], 'phases': {}}}) == 7


def test_archive_wall_counts_on_normal_path_too():
    """Offline-review counter-example: with budget NOT exceeded, the final
    observed wall must still include archive time (5s injection, 60s budget)."""
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        restore_budgets()
        entry.TOTAL_WALL_S = 60.0
        entry.SAMPLE_INTERVAL_S = 0.02
        real_sha = entry.sha256_file

        def slow_sha(path):
            _time.sleep(0.3)
            return real_sha(path)

        entry.sha256_file = slow_sha
        try:
            s = run_attempt(tmp)
        finally:
            entry.sha256_file = real_sha
        assert s['within_total_budget'] is True
        assert s["wall_s"] >= 0.85, s["wall_s"]  # archive delay included, not 0 (3 hashed files x 0.3s)
        disk = json.loads((run_dir_of(tmp) / 'summary.json').read_text())
        assert disk['wall_s'] == s['wall_s'] and disk['within_total_budget'] is True
        att = json.loads((run_dir_of(tmp) / 'ATTEMPT_COMPLETED.json').read_text())
        assert att['wall_s'] == s['wall_s']
        # manifest hashes match the FINAL rewritten files
        import hashlib
        mf = json.loads((run_dir_of(tmp) / 'manifest.json').read_text())
        for o in mf['outputs']:
            f_ = run_dir_of(tmp) / o['path']
            assert f_.stat().st_size == o['bytes'], o['path']
            assert hashlib.sha256(f_.read_bytes()).hexdigest() == o['sha256'], o['path']
    restore_budgets()


def test_image_query_failure_never_skips_archive():
    """Offline-review counter-example: a docker image inspect timeout must not
    abort cleanup/archiving; result recorded unknown, archive complete; with no
    remaining budget the query is not attempted at all."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        shrink_budgets()
        real_di = entry.docker_image_id
        calls = {'n': 0}

        def boom_di(reference, timeout_s=30.0):
            calls['n'] += 1
            raise subprocess.TimeoutExpired(cmd='docker', timeout=timeout_s)

        entry.docker_image_id = boom_di
        try:
            s = run_attempt(tmp)
        finally:
            entry.docker_image_id = real_di
        assert calls['n'] == 1  # attempted (budget available), failed
        ev = {e['phase']: e for e in s['events']}
        assert ev['image_tag_after_stop']['query_error'] == 'TimeoutExpired'
        assert s['outcome'].get('image_tag_after_stop') == 'unknown:TimeoutExpired'
        rd = run_dir_of(tmp)
        assert (rd / 'summary.json').exists() and (rd / 'manifest.json').exists()
        assert (rd / 'ATTEMPT_COMPLETED.json').exists()

    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        entry.TOTAL_WALL_S = 0.0  # total wall already exhausted at cleanup; no query budget left
        entry.CLEANUP_RESERVE_S = 0.01
        entry.SAMPLE_INTERVAL_S = 0.02
        real_di = entry.docker_image_id
        calls2 = {'n': 0}

        def count_di(reference, timeout_s=30.0):
            calls2['n'] += 1
            return entry.TASK_IMAGE_ID_EXPECTED

        entry.docker_image_id = count_di
        try:
            s = run_attempt(tmp)
        finally:
            entry.docker_image_id = real_di
        assert calls2['n'] == 0  # NOT attempted with no remaining budget
        ev = {e['phase']: e for e in s['events']}
        assert ev['image_tag_after_stop']['query_error'] == 'skipped_no_remaining_budget'
        assert (run_dir_of(tmp) / 'summary.json').exists()
    restore_budgets()


def test_archive_overrun_recorded_and_exit_9():
    """Offline-review counter-example: time spent archiving must count toward
    the total wall; the persisted within_total_budget flips, and the exit code
    is non-zero (9)."""
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        install_fakes()
        restore_budgets()
        # small TOTAL so the (fast, faked) work finishes well inside, but the
        # injected archive delay crosses the line. TOTAL is identity-bound;
        # this test exercises run_attempt + exit_code_for directly (no main gate).
        entry.TOTAL_WALL_S = 1.0
        entry.CLEANUP_RESERVE_S = 0.2
        entry.SAMPLE_INTERVAL_S = 0.02
        real_sha = entry.sha256_file

        def slow_sha(path):
            _time.sleep(0.35)  # archive-time injection: several files hashed
            return real_sha(path)

        entry.sha256_file = slow_sha
        try:
            s = run_attempt(tmp)
        finally:
            entry.sha256_file = real_sha
        assert s['within_total_budget'] is False
        assert s['wall_s'] > 1.0
        assert entry.exit_code_for(s) == 9
        # persisted on disk with the same adjudication
        disk = json.loads((run_dir_of(tmp) / 'summary.json').read_text())
        assert disk['within_total_budget'] is False and disk['wall_s'] > 1.0
        att = json.loads((run_dir_of(tmp) / 'ATTEMPT_COMPLETED.json').read_text())
        assert att['within_total_budget'] is False
        # ATTEMPT_COMPLETED is hashed in the manifest with the final content
        mf = json.loads((run_dir_of(tmp) / 'manifest.json').read_text())
        att_entry = [o for o in mf['outputs'] if o['path'] == 'ATTEMPT_COMPLETED.json']
        assert att_entry and att_entry[0]['bytes'] == (run_dir_of(tmp) / 'ATTEMPT_COMPLETED.json').stat().st_size
    restore_budgets()


def test_json_action_llm_strips_stop():
    """The registered JSON action configuration omits stop sequences."""
    seen = {}

    class Inner:
        async def call(self, *, prompt, message_history, **kw):
            seen.update(kw)
            seen['prompt'] = prompt
            seen['history_len'] = len(message_history)
            return LLMResponse(content='{}', model_name='fake')

    import asyncio
    w = entry.JsonActionLLM(Inner())
    r = asyncio.run(w.call(prompt='p', message_history=[{'role': 'user', 'content': 'x'}],
                            stop=['</think>', '```'], extra_body=None,
                            max_tokens=5, logging_path=None))
    assert r.content == '{}'
    assert 'stop' not in seen          # stripped
    assert 'extra_body' not in seen    # Harbor cannot unpack None as a mapping
    assert seen['max_tokens'] == 5     # passthrough
    assert seen['history_len'] == 1


if __name__ == '__main__':
    test_plan_mode_zero_side_effects()
    test_finish_real_rewards_and_archive()
    test_steps_exhausted_classification()
    test_startup_failure_still_cleans_and_archives()
    test_verifier_infra_error_separated()
    test_agent_timeout_stops_and_cleans()
    test_execute_gates_and_exit_codes()
    test_outputs_isolated_from_real_collection()
    test_manifest_hash_consistency()
    test_setup_called_before_run()
    test_work_budget_exhausted_cleanup_still_runs()
    test_container_mismatch_still_archives()
    test_exit_8_agent_error_and_verifier_timeout()
    test_archive_overrun_recorded_and_exit_9()
    test_archive_wall_counts_on_normal_path_too()
    test_image_query_failure_never_skips_archive()
    test_json_action_llm_strips_stop()
    test_approval_is_not_an_attempt_and_main_runs_with_fakes()
    test_missing_invalid_stale_and_consumed_approval_refused_before_docker()
    test_approval_does_not_exempt_other_namespace_records()
    print('all 20 entry tests passed')
