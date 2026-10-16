"""Fixed single-run entry through real Harbor/Agent, external boundaries only."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
import docops_measurement_validate_01_entry as entry
from tests.test_docops_cleanup import ComposeTransport, assert_archive
from tests.test_docops_office_repeat_01_entry import FakeRuntime, FakeVerifier
from harbor.llms.lite_llm import LiteLLM
from harbor.llms.base import LLMResponse
from harbor.models.metric.usage_info import UsageInfo
from agent_workload_characterization.runners.docops_environment import DocOpsDockerEnvironment


def approve(root, **overrides):
    plan = entry.plan_mode(root)
    path = root / entry.REPORT_REL / 'APPROVAL.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {'schema': 'docops-single-run-approval-v1', 'collection': entry.COLLECTION,
              'user_approval': 'approved', 'identity_sha256': plan['identity_sha256'],
              'accept_unknown_cost_no_hard_cap': True,
              'source': 'synthetic test only; not a real experiment authorization'}
    path.write_text(json.dumps({**record, **overrides}))


def quiet_main(root, argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return entry.main(argv, root=root)


@contextlib.contextmanager
def external_boundaries(test, *, cleanup_mode='ok', removal='removed', image_ok=True):
    transport = ComposeTransport(cleanup_mode)
    requests = []
    returned_before_next_request = []
    expected = entry.build_identity()['task']['image_id']

    class Runtime(FakeRuntime):
        def verify_removal(self, handle, timeout_s=30.0):
            self.removal_calls += 1
            transport.order.append('verify_removal')
            return removal

    runtime = Runtime()

    async def llm_call(llm, *, logging_path=None, **kwargs):
        requests.append(logging_path)
        test.assertNotIn('stop', kwargs)
        test.assertNotIn('extra_body', kwargs)
        test.assertEqual(kwargs['max_tokens'], 32768)
        if len(requests) == 1:
            action = {'thought': 'synthetic', 'action': 'call_tool',
                      'tool_name': 'copy_file', 'arguments': {
                          'src': '/root/excel_001_budget_bucket_totals_seed.xlsx',
                          'dest': '/root/submission/test.xlsx'}}
        elif len(requests) == 2:
            # Last return is already on disk before any following LLM response.
            events_path = Path(logging_path).parent / 'events.jsonl'
            events = [json.loads(s) for s in events_path.read_text().splitlines()]
            opened = [e for e in events if e['kind'] == 'tool_call'
                      and e['status'] == 'open' and e['attrs']['role'] == 'agent']
            test.assertEqual(len(opened), 1)
            closed = [e for e in events if e['event_id'] == opened[0]['event_id']
                      and e['status'] == 'closed']
            test.assertEqual(len(closed), 1)
            test.assertIs(closed[0]['attrs']['ok'], True)
            returned_before_next_request.append(True)
            action = {'thought': 'synthetic done', 'action': 'finish', 'arguments': {}}
        else:
            raise AssertionError('model called after finish')
        return LLMResponse(content=json.dumps(action), model_name='synthetic-response-model',
                           usage=UsageInfo(prompt_tokens=0, completion_tokens=1,
                                           cache_tokens=0, cost_usd=0.0))

    with patch('asyncio.create_subprocess_exec', side_effect=transport.spawn), \
         patch('asyncio.create_subprocess_shell', side_effect=AssertionError('shell transport forbidden')), \
         patch.object(LiteLLM, 'call', new=llm_call), \
         patch.object(entry.shared, 'build_verifier', return_value=FakeVerifier()), \
         patch.object(entry.shared, 'build_runtime', return_value=runtime), \
         patch.object(entry.shared, 'compose_containers', side_effect=lambda p: [('f' * 64, p + '-main-1')]), \
         patch.object(entry.shared, 'docker_image_id', return_value=expected), \
         patch.object(entry.office, 'inspect_image', return_value=(expected, 'linux/arm64') if image_ok else None), \
         patch.object(entry.office, 'load_model_credential') as credential:
        yield transport, runtime, requests, returned_before_next_request, credential


class MeasurementEntryTests(unittest.TestCase):
    def test_fixed_configuration_and_actual_code_identity(self):
        identity = entry.build_identity()
        config = identity['run_config']
        self.assertEqual(config['collection'], entry.COLLECTION)
        self.assertEqual(config['task_key'], entry.TASK_KEY)
        self.assertEqual(config['input_asset'], 'excel_001_budget_bucket_totals_seed.xlsx')
        self.assertEqual([config[k] for k in ('max_steps', 'max_tokens', 'total_wall_s',
                         'cleanup_reserve_s', 'agent_budget_s', 'verifier_budget_s',
                         'cpu_limit', 'memory_mb', 'network', 'sample_interval_s')],
                         [40, 32768, 2700, 300, 1200, 600, 1, 4096, 'none', 0.5])
        files = {r['path'] for r in identity['code_and_runtime_files']}
        for path in ('scripts/docops_measurement_validate_01_entry.py',
                     'src/agent_workload_characterization/runners/docops_environment.py',
                     'src/agent_workload_characterization/collectors/execution_measurement.py',
                     '.venvs/docops-pilot-01/lib/python3.12/site-packages/harbor/environments/docker/docker.py'):
            self.assertIn(path, files)
        self.assertEqual(identity['cleanup']['compose_delete_args'],
                         ['down', '--volumes', '--remove-orphans'])
        self.assertEqual(identity['attempts'], 1)
        self.assertEqual(identity['measurement_contract']['contract']['version'], 'real-run-measurement-v1')

    def test_default_plan_zero_external_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(entry.office, 'inspect_image', side_effect=AssertionError('Docker')), \
                 patch.object(entry.office, 'load_model_credential', side_effect=AssertionError('credentials')), \
                 patch.object(LiteLLM, 'call', side_effect=AssertionError('model')):
                self.assertEqual(quiet_main(root, []), 0)
            self.assertEqual(list(root.iterdir()), [])
        self.assertFalse(root.exists())

    def test_approval_cost_identity_and_attempt_gates(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self) as (_, _, requests, _, key):
            root = Path(tmp)
            entry.freeze(root)
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 2)
            for changes in ({'collection': 'DOCOPS-OFFICE-REPEAT-01'},
                            {'identity_sha256': '0' * 64},
                            {'accept_unknown_cost_no_hard_cap': False},
                            {'entry_invocation': 'old rejected invocation'}):
                approve(root, **changes)
                self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 2)
            approve(root)
            self.assertTrue(entry.plan_mode(root)['ready_for_execution'])
            self.assertEqual(quiet_main(root, ['--execute']), 2)
            (root / entry.RAW_REL / 'prior' ).mkdir(parents=True)
            (root / entry.RAW_REL / 'prior' / 'ATTEMPT_STARTED.json').write_text('{}')
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 2)
            key.assert_not_called()
            self.assertEqual(requests, [])

    def test_freeze_no_overwrite_and_full_identity_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry.freeze(root)
            self.assertRaises(FileExistsError, entry.freeze, root)
            path = root / entry.ENV_REL / 'plan-identity.json'
            record = json.loads(path.read_text())
            record['identity']['run_config']['max_steps'] = 41
            path.write_text(json.dumps(record))
            self.assertFalse(entry.plan_mode(root)['identity_matches_frozen'])
            approve(root)
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 2)

    def test_real_entry_agent_cleanup_and_archive_in_temporary_root(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self) as (transport, runtime, calls, saved, key):
            root = Path(tmp)
            entry.freeze(root)
            approve(root)
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 0)
            self.assertEqual(len(calls), 2)
            self.assertEqual(saved, [True])
            key.assert_called_once()
            report = json.loads((root / entry.REPORT_REL / 'run-report.json').read_text())
            summary = report['summary']
            self.assertEqual(summary['outcome']['phases']['agent']['status'], 'finish')
            self.assertEqual(summary['outcome']['phases']['verifier']['rewards'], {'reward': 0.0})
            self.assertTrue(report['archive_valid'])
            self.assertTrue(report['image_retention_verified'])
            self.assertEqual(runtime.removal_calls, 1)
            self.assertEqual(transport.order, ['cleanup', 'verify_removal'])
            self.assertTrue(all('--rmi' not in argv for argv in transport.argv))
            cleanups = [argv for argv in transport.argv if '--volumes' in argv]
            self.assertEqual(cleanups[0][-3:], ('down', '--volumes', '--remove-orphans'))
            run_dir = root / entry.RAW_REL / report['run_id']
            self.assertEqual(run_dir.parent, root / entry.RAW_REL)
            assert_archive(self, root, summary)
            raw = json.loads((run_dir / 'manifest.json').read_text())
            self.assertTrue({'environment.json', 'measurement.json', 'agent/events.jsonl'}
                            <= {r['path'] for r in raw['outputs']})
            m = json.loads((run_dir / 'measurement.json').read_text())
            self.assertEqual(m['call_timing_status'], 'complete')
            self.assertEqual(m['expected_requests'], 2)
            self.assertIsNone(m['transport_attempts']['value'])
            for manifest_path in (root / entry.ENV_REL / 'preparation-manifest.json',
                                  root / entry.REPORT_REL / 'manifest.json'):
                manifest = json.loads(manifest_path.read_text())
                for row in manifest['outputs']:
                    self.assertEqual(entry.office.file_record(root / row['path'], Path(row['path'])), row)
                self.assertNotIn(manifest_path.relative_to(root).as_posix(),
                                 [r['path'] for r in manifest['outputs']])
        self.assertFalse(root.exists())

    def test_missing_image_refuses_before_credentials_and_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self, image_ok=False) as (_, _, calls, _, key):
            root = Path(tmp)
            entry.freeze(root)
            approve(root)
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 2)
            key.assert_not_called()
            self.assertEqual(calls, [])
            self.assertFalse((root / entry.RAW_REL).exists())

    def test_cleanup_failure_preserves_failed_archive(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self, cleanup_mode='failure') as (_, runtime, _, _, _):
            root = Path(tmp)
            entry.freeze(root)
            approve(root)
            self.assertEqual(quiet_main(root, ['--execute', entry.FLAG]), 7)
            report = json.loads((root / entry.REPORT_REL / 'run-report.json').read_text())
            self.assertIn('harbor_stop:RuntimeError', report['summary']['outcome']['infra_failures'])
            self.assertEqual(runtime.removal_calls, 1)
            assert_archive(self, root, report['summary'])

    def test_builder_is_real_image_retaining_environment(self):
        from harbor.models.trial.paths import TrialPaths
        with tempfile.TemporaryDirectory() as tmp:
            paths = TrialPaths(trial_dir=Path(tmp) / 'run')
            paths.mkdir()
            env = entry.shared.build_environment('synthetic-measurement', paths,
                                                  entry.build_identity()['run_config'])
            self.assertIs(type(env), DocOpsDockerEnvironment)


if __name__ == '__main__':
    unittest.main()
