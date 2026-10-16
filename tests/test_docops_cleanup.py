"""Real DocOps environment/entry cleanup, with subprocess/model boundaries faked."""
import asyncio
import contextlib
import hashlib
import inspect
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages'))
sys.path.insert(0, str(ROOT / 'src'))

import docops_word_resource_01_entry as shared
import docops_office_repeat_01_entry as batch
from tests.test_docops_office_repeat_01_entry import FakeLLM, FakeRuntime, FakeVerifier
from agent_workload_characterization.runners.docops_environment import DocOpsDockerEnvironment
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.trial.paths import TrialPaths


class ComposeTransport:
    def __init__(self, mode='ok'):
        self.mode = mode
        self.argv = []
        self.order = []

    async def spawn(self, *argv, **kwargs):
        assert argv[:2] == ('docker', 'compose')
        self.argv.append(argv)  # Never retain the subprocess environment.
        transport = self
        cleanup = 'down' in argv and '--volumes' in argv

        class Process:
            returncode = 1 if cleanup and transport.mode == 'failure' else 0

            async def communicate(self):
                if cleanup:
                    transport.order.append('cleanup')
                    if transport.mode == 'timeout':
                        await asyncio.Event().wait()
                if self.returncode:
                    return b'synthetic compose down failure', None
                if 'exec' in argv and argv[-1].startswith('python3 -c '):
                    return b'preflight_ok\n', None
                return b'{"ok":true}', None

        return Process()


@contextlib.contextmanager
def external_fakes(mode='ok', removal='removed'):
    transport = ComposeTransport(mode)
    calls = []
    original_build_agent = shared.build_agent

    def build_agent(logs_dir, config=None):
        agent = original_build_agent(logs_dir, config)
        count = [0]
        calls.append(count)
        agent.llm = FakeLLM(count)
        return agent

    class Runtime(FakeRuntime):
        def verify_removal(self, handle, timeout_s=30.0):
            self.removal_calls += 1
            transport.order.append('verify_removal')
            return removal

    runtime = Runtime()
    with patch('asyncio.create_subprocess_exec', side_effect=transport.spawn), \
         patch('asyncio.create_subprocess_shell', side_effect=AssertionError('unexpected shell transport')), \
         patch.object(shared, 'build_agent', side_effect=build_agent), \
         patch.object(shared, 'build_verifier', return_value=FakeVerifier()), \
         patch.object(shared, 'compose_containers', side_effect=lambda name: [
             ('f' * 64, name + '-main-1')]), \
         patch.object(shared, 'build_runtime', return_value=runtime), \
         patch.object(shared, 'docker_image_id', return_value=None):
        yield transport, runtime, calls


def word_attempt(root, **limits):
    identity = shared.build_identity()
    config = {**shared.run_config({}), **limits}
    plan = {'run_id': 'offline-cleanup-word', 'identity': identity,
            'identity_sha256': shared.identity_digest(identity), 'run_config': config}
    return asyncio.run(shared.run_attempt(root, plan))


def assert_archive(test, root, summary):
    path = root / 'data/raw/generated' / summary['collection'] / summary['run_id']
    test.assertEqual(json.loads((path / 'summary.json').read_text()), summary)
    manifest = json.loads((path / 'manifest.json').read_text())
    test.assertNotIn('manifest.json', [row['path'] for row in manifest['outputs']])
    for row in manifest['outputs']:
        file = path / row['path']
        test.assertEqual(file.stat().st_size, row['bytes'])
        test.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), row['sha256'])


class DocOpsCleanupTests(unittest.TestCase):
    def assert_cleanup_argv(self, transport, count):
        self.assertTrue(transport.argv)
        self.assertTrue(all('--rmi' not in argv for argv in transport.argv))
        cleanups = [argv for argv in transport.argv if '--volumes' in argv]
        self.assertEqual(len(cleanups), count)
        for argv in cleanups:
            self.assertEqual(argv[-3:], ('down', '--volumes', '--remove-orphans'))
            self.assertIn('--project-name', argv)

    def test_builder_uses_adapter_and_actual_compose_argv(self):
        with tempfile.TemporaryDirectory() as tmp, external_fakes() as (transport, _, _):
            paths = TrialPaths(trial_dir=Path(tmp) / 'trial')
            paths.mkdir()
            env = shared.build_environment('offline-cleanup-direct', paths)
            self.assertIs(type(env), DocOpsDockerEnvironment)
            asyncio.run(env.stop(delete=True))
            self.assert_cleanup_argv(transport, 1)
            self.assertEqual(transport.argv[-1][transport.argv[-1].index('--project-name') + 1],
                             'offline-cleanup-direct')
            # Harbor's existing best-effort log ownership operation is retained.
            self.assertTrue(any('exec' in argv and 'chown' in argv[-1] for argv in transport.argv))

    def test_word_real_attempt_cleans_verifies_and_archives(self):
        with tempfile.TemporaryDirectory() as tmp, external_fakes() as (transport, runtime, calls):
            summary = word_attempt(Path(tmp))
            self.assertEqual(shared.exit_code_for(summary), 0)
            self.assertEqual(summary['outcome']['phases']['agent']['status'], 'finish')
            self.assertEqual(calls, [[1]])
            self.assert_cleanup_argv(transport, 1)
            self.assertEqual(transport.order, ['cleanup', 'verify_removal'])
            self.assertEqual(runtime.removal_calls, 1)
            self.assertEqual(summary['outcome']['image_tag_after_stop'], 'not_present')
            self.assertNotIn('harbor_removed_task_image_tag', summary['outcome'])
            assert_archive(self, Path(tmp), summary)

    def test_office_real_batch_uses_adapter_for_every_attempt(self):
        identity = batch.build_identity({t['key']: 'sha256:' + str(i) * 64
                                        for i, t in enumerate(batch.TASKS, 1)})
        with tempfile.TemporaryDirectory() as tmp, external_fakes() as (transport, runtime, calls):
            with patch.object(shared, 'docker_image_id', side_effect=lambda ref, **kw:
                              next(t['image_id'] for t in identity['tasks'] if t['image_ref'] == ref)):
                result = batch.run_batch(Path(tmp), {}, identity,
                                         start_monotonic=time.monotonic(), docker_enabled=False)
            self.assertEqual([row['status'] for row in result['results']], ['executed'] * 9)
            self.assert_cleanup_argv(transport, 9)
            self.assertEqual(transport.order, ['cleanup', 'verify_removal'] * 9)
            self.assertEqual(runtime.removal_calls, 9)
            self.assertEqual(calls, [[1]] * 9)
            for row in result['results']:
                path = batch._run_dir(Path(tmp), row['run_id'])
                assert_archive(self, Path(tmp), json.loads((path / 'summary.json').read_text()))

    def test_office_real_preflight_uses_adapter_without_model_call(self):
        task = batch.TASKS[0]
        config = batch.run_config(task['key'], 0, batch.image_ref(task['key']), 'sha256:' + 'a' * 64)
        with tempfile.TemporaryDirectory() as tmp, external_fakes() as (transport, runtime, calls):
            result = asyncio.run(batch.preflight_one(task['key'], config, Path(tmp), timeout_s=1))
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(result['container_removal'], 'removed')
            self.assertEqual(calls, [[0]])
            self.assert_cleanup_argv(transport, 1)
            self.assertEqual(transport.order, ['cleanup', 'verify_removal'])
            self.assertEqual(runtime.removal_calls, 1)

    def test_compose_failure_not_swallowed_even_when_removal_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp, external_fakes('failure') as (transport, runtime, _):
            summary = word_attempt(Path(tmp))
            self.assertIn('harbor_stop:RuntimeError', summary['outcome']['infra_failures'])
            self.assertEqual(shared.exit_code_for(summary), 7)
            self.assertEqual(runtime.removal_calls, 1)
            assert_archive(self, Path(tmp), summary)
        task = batch.TASKS[0]
        config = batch.run_config(task['key'], 0, batch.image_ref(task['key']), 'sha256:' + 'a' * 64)
        with tempfile.TemporaryDirectory() as tmp, external_fakes('failure'):
            result = asyncio.run(batch.preflight_one(task['key'], config, Path(tmp), timeout_s=1))
            self.assertEqual(result['container_removal'], 'removed')
            self.assertEqual(result['stop_error'], 'RuntimeError')
            self.assertEqual(result['status'], 'failed')

    def test_cleanup_timeout_uses_remaining_total_budget_and_archives(self):
        with tempfile.TemporaryDirectory() as tmp, external_fakes('timeout') as (transport, runtime, _):
            summary = word_attempt(Path(tmp), total_wall_s=0.35,
                                   cleanup_reserve_s=0.15, stop_budget_s=5)
            events = {e['phase']: e for e in summary['events']}
            self.assertEqual(events['harbor_stop_done']['stop_error'], 'TimeoutError')
            self.assertIn('harbor_stop:TimeoutError', summary['outcome']['infra_failures'])
            elapsed = (events['harbor_stop_done']['t_monotonic_ns'] -
                       events['harbor_stop_begin']['t_monotonic_ns']) / 1e9
            before_stop = (events['harbor_stop_begin']['t_monotonic_ns'] -
                           events['attempt_started']['t_monotonic_ns']) / 1e9
            self.assertGreater(elapsed, 0.02)
            self.assertLessEqual(elapsed, max(0, 0.35 - before_stop) + 0.08)
            self.assertEqual(transport.order, ['cleanup', 'verify_removal'])
            self.assertEqual(runtime.removal_calls, 1)
            self.assertEqual(shared.exit_code_for(summary), 7)
            assert_archive(self, Path(tmp), summary)

    def test_unconfirmed_removal_stops_batch_and_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp, external_fakes(removal='still_exists'):
            summary = word_attempt(Path(tmp))
            self.assertIn('removal:still_exists', summary['outcome']['infra_failures'])
            self.assertEqual(shared.exit_code_for(summary), 7)
            assert_archive(self, Path(tmp), summary)
        identity = batch.build_identity({t['key']: 'sha256:' + str(i) * 64
                                        for i, t in enumerate(batch.TASKS, 1)})
        with tempfile.TemporaryDirectory() as tmp, external_fakes(removal='still_exists') as (transport, _, _):
            result = batch.run_batch(Path(tmp), {}, identity,
                                     start_monotonic=time.monotonic(), docker_enabled=False)
            self.assertEqual([row['status'] for row in result['results']],
                             ['failed'] + ['not_executed'] * 8)
            self.assert_cleanup_argv(transport, 1)

    def test_both_identities_bind_actual_cleanup_code_and_reject_old_freezes(self):
        word = shared.build_identity()
        office = batch.build_identity({t['key']: 'sha256:' + str(i) * 64
                                      for i, t in enumerate(batch.TASKS, 1)})
        loaded_paths = [Path(inspect.getfile(DocOpsDockerEnvironment)),
                        Path(inspect.getfile(DockerEnvironment))]
        word_files = {row['path']: row for row in word['files'].values()}
        office_files = {str(ROOT / row['path']): row for row in office['code_and_runtime_files']}
        for path in loaded_paths:
            for files in (word_files, office_files):
                self.assertEqual(files[str(path)]['sha256'], shared.sha256_file(path))
                self.assertEqual(files[str(path)]['bytes'], path.stat().st_size)
        for identity in (word, office):
            self.assertEqual(identity['cleanup']['compose_delete_args'],
                             ['down', '--volumes', '--remove-orphans'])
            self.assertTrue(identity['cleanup']['retain_images'])
        self.assertNotEqual(shared.identity_digest(word), shared.frozen_identity_sha())
        old = json.loads((ROOT / batch.ENV_DIR_REL / 'frozen-identity.json').read_text())
        self.assertNotEqual(batch.identity_sha(office), old['identity_sha256'])


if __name__ == '__main__':
    unittest.main()
