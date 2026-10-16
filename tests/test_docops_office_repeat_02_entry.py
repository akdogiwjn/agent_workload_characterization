"""REPEAT-02 real batch/Agent/environment, only external boundaries faked."""
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import docops_office_repeat_02_entry as entry
from tests.test_docops_cleanup import ComposeTransport, assert_archive
from tests.test_docops_office_repeat_01_entry import FakeRuntime, FakeVerifier
from harbor.llms.lite_llm import LiteLLM
from harbor.llms.base import LLMResponse
from harbor.models.metric.usage_info import UsageInfo
from agent_workload_characterization.runners.docops_environment import DocOpsDockerEnvironment


def approve(root, **changes):
    p = root / entry.REPORT_REL / 'APPROVAL.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    a = {'schema': 'docops-batch-approval-v1', 'collection': entry.COLLECTION,
         'identity_sha256': entry.plan_mode(root)['identity_sha256'],
         'user_approval': 'approved', 'approved_at_utc': 'synthetic timestamp',
         'accept_unknown_cost_no_hard_cap': True,
         'scope': {'attempts': 9, 'maximum_model_steps': 360, 'attempt_retry': 0},
         'source': 'temporary fixture only; not a real user authorization'}
    p.write_text(json.dumps({**a, **changes}))


def main(root, argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return entry.main(argv, root=root)


@contextlib.contextmanager
def external_boundaries(test, *, cleanup='ok', removal='removed', image_after=True):
    office, shared = entry.office, entry.office.shared
    identity = entry.build_identity()
    image_ids = {t['image_ref']: t['image_id'] for t in identity['tasks']}
    image_ids[identity['base_image']['reference']] = identity['base_image']['expected_id']
    transport = ComposeTransport(cleanup)
    configs = []
    calls = Counter()
    observed_returns = []
    original_builder = shared.build_environment

    def environment(run_id, paths, config=None):
        configs.append(config)
        env = original_builder(run_id, paths, config)
        test.assertIs(type(env), DocOpsDockerEnvironment)
        return env

    class Runtime(FakeRuntime):
        def verify_removal(self, handle, timeout_s=30):
            self.removal_calls += 1
            transport.order.append('verify_removal')
            return removal

    runtime = Runtime()

    async def call(llm, *, logging_path=None, **kw):
        key = Path(logging_path).parent
        calls[str(key)] += 1
        test.assertNotIn('stop', kw)
        test.assertNotIn('extra_body', kw)
        test.assertEqual(kw['max_tokens'], 32768)
        count = calls[str(key)]
        if count == 1:
            config = configs[-1]
            action = {'thought': 'synthetic', 'action': 'call_tool', 'tool_name': 'copy_file',
                      'arguments': {'src': '/root/' + config['input_asset'],
                                    'dest': '/root/submission/' + config['input_asset']}}
        elif count == 2:
            rows = [json.loads(s) for s in (key / 'events.jsonl').read_text().splitlines()]
            opened = [e for e in rows if e['kind'] == 'tool_call' and e['status'] == 'open'
                      and e['attrs']['role'] == 'agent']
            test.assertEqual(len(opened), 1)
            terminal = [e for e in rows if e['event_id'] == opened[0]['event_id'] and e['status'] == 'closed']
            test.assertEqual(len(terminal), 1)
            test.assertIs(terminal[0]['attrs']['ok'], True)
            observed_returns.append(str(key))
            action = {'thought': 'synthetic', 'action': 'finish', 'arguments': {}}
        else:
            raise AssertionError('model requested after finish')
        return LLMResponse(content=json.dumps(action), model_name='synthetic-model',
            usage=UsageInfo(prompt_tokens=0, completion_tokens=1, cache_tokens=0, cost_usd=0.0))

    with patch('asyncio.create_subprocess_exec', side_effect=transport.spawn), \
         patch('asyncio.create_subprocess_shell', side_effect=AssertionError('unexpected shell')), \
         patch.object(LiteLLM, 'call', new=call), \
         patch.object(shared, 'build_environment', side_effect=environment), \
         patch.object(shared, 'build_runtime', return_value=runtime), \
         patch.object(shared, 'build_verifier', return_value=FakeVerifier()), \
         patch.object(shared, 'compose_containers', side_effect=lambda p: [('f'*64, p+'-main-1')]), \
         patch.object(shared, 'docker_image_id', side_effect=lambda ref, **kw: image_ids[ref] if image_after else None), \
         patch.object(office, 'inspect_image', side_effect=lambda ref: (image_ids[ref], 'linux/arm64')), \
         patch.object(office, 'restore_or_build', side_effect=AssertionError('no runtime restoration')), \
         patch.object(office, 'load_model_credential') as credential:
        yield transport, runtime, calls, observed_returns, configs, credential


class Repeat02Tests(unittest.TestCase):
    def test_plan_is_read_only_and_fixed_identity_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (patch.object(entry.office, 'inspect_image', side_effect=AssertionError('Docker')),
                  patch.object(entry.office, 'load_model_credential', side_effect=AssertionError('key')),
                  patch.object(LiteLLM, 'call', side_effect=AssertionError('API'))):
                self.assertEqual(main(root, []), 0)
            self.assertEqual(list(root.iterdir()), [])
            identity = entry.build_identity(root)
            self.assertEqual(identity['schedule'], [{'round': i, 'tasks': list(row)} for i,row in enumerate(entry.office.ORDER)])
            self.assertEqual(identity['budget']['batch_wall_s'], 27000)
            self.assertEqual(identity['budget']['batch_closeout_reserve_s'], 2700)
            self.assertEqual(identity['budget']['per_attempt']['max_steps'], 40)
            self.assertEqual(identity['paths']['raw'], str(entry.RAW_REL))
            self.assertEqual(identity['approval_flag'], entry.FLAG)
            files = {r['path'] for r in identity['code_and_runtime_files']}
            for p in ('scripts/docops_office_repeat_02_entry.py',
                'scripts/docops_office_repeat_01_entry.py', 'scripts/docops_word_resource_01_entry.py',
                'src/agent_workload_characterization/runners/docops_environment.py',
                'src/agent_workload_characterization/collectors/execution_measurement.py',
                'docs/trace_contract.md', '.venvs/docops-pilot-01/lib/python3.12/site-packages/harbor/llms/lite_llm.py'):
                self.assertIn(p, files)
        self.assertFalse(root.exists())

    def test_gates_missing_old_cost_drift_flag_and_existing_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self) as (_,_,calls,_,_,credential):
            root = Path(tmp)
            entry.freeze(root)
            self.assertEqual(main(root, ['--execute', entry.FLAG]), 2)
            for change in ({'collection':'DOCOPS-OFFICE-REPEAT-01'},
                           {'identity_sha256':'a'*64}, {'accept_unknown_cost_no_hard_cap':False},
                           {'entry_invocation':'old invocation'}):
                approve(root, **change)
                self.assertEqual(main(root, ['--execute', entry.FLAG]), 2)
            approve(root)
            self.assertTrue(entry.plan_mode(root)['ready_for_execution'])
            self.assertEqual(main(root, ['--execute']), 2)
            (root / entry.REPORT_REL / 'ATTEMPT_STARTED.json').write_text('{}')
            self.assertEqual(main(root, ['--execute', entry.FLAG]), 2)
            (root / entry.REPORT_REL / 'ATTEMPT_STARTED.json').unlink()
            (root / entry.RAW_REL / 'existing').mkdir(parents=True)
            self.assertEqual(main(root, ['--execute', entry.FLAG]), 2)
            credential.assert_not_called()
            self.assertFalse(calls)

    def test_freeze_no_overwrite_and_full_structure_drift_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry.freeze(root)
            self.assertRaises(FileExistsError, entry.freeze, root)
            path = root / entry.ENV_REL / 'plan-identity.json'
            plan = json.loads(path.read_text())
            plan['identity']['budget']['per_attempt']['max_steps'] = 41
            path.write_text(json.dumps(plan))
            approve(root)
            self.assertFalse(entry.plan_mode(root)['ready_for_execution'])

    def test_real_entry_nine_agent_loops_new_cleanup_and_final_manifests(self):
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self) as (transport,runtime,calls,saved,configs,_):
            root = Path(tmp)
            entry.freeze(root)
            approve(root)
            self.assertEqual(main(root, ['--execute', entry.FLAG]), 0)
            batch = json.loads((root/entry.REPORT_REL/'batch-summary.json').read_text())
            self.assertEqual([r['status'] for r in batch['results']], ['executed']*9)
            self.assertEqual([(r['round'],r['task_key']) for r in batch['results']],
                             [(i,k) for i,row in enumerate(entry.office.ORDER) for k in row])
            self.assertEqual(len({r['run_id'] for r in batch['results']}), 9)
            self.assertEqual(list(calls.values()), [2]*9)
            self.assertEqual(len(saved), 9)
            self.assertEqual(runtime.removal_calls, 9)
            self.assertEqual(transport.order, ['cleanup','verify_removal']*9)
            self.assertTrue(all('--rmi' not in a for a in transport.argv))
            self.assertEqual(len(list((root/entry.RAW_REL).iterdir())), 9)
            self.assertFalse((root/entry.office.RAW_DIR_REL).exists())
            for cfg,row in zip(configs,batch['results'],strict=True):
                self.assertEqual(cfg['collection'], entry.COLLECTION)
                self.assertEqual(Path(cfg['task_dir']).name, row['task_key'])
                self.assertEqual(cfg['input_asset'], entry.office.task_spec(row['task_key'])['asset'])
                self.assertEqual(row['model_requests_logged'], 2)
                self.assertEqual(row['tool_name_counts'], {'copy_file':1})
                # The synthetic metadata response contains only ok=true, so
                # the official loop does not request a bootstrap document read.
                self.assertEqual(row['bootstrap_tool_counts_from_events'], {'get_task_metadata':1})
                self.assertEqual(row['tool_return_status_counts'], {'ok_true':1})
                self.assertEqual(row['reward'], 0.0)
                self.assertEqual(row['termination'], 'finish')
                self.assertEqual(row['requests_after_finish'], 0)
                self.assertTrue(row['identity_after_attempt_verified'])
                self.assertTrue(row['image_retention_verified'])
                rd=root/entry.RAW_REL/row['run_id']
                summary=json.loads((rd/'summary.json').read_text())
                assert_archive(self,root,summary)
                manifest=json.loads((rd/'manifest.json').read_text())
                self.assertTrue({'environment.json','measurement.json','summary.json','agent/events.jsonl'}
                                <= {r['path'] for r in manifest['outputs']})
                self.assertTrue(summary['samples'])
                self.assertTrue(summary['events'])
                self.assertEqual(row['measurement']['call_timing_status'], 'complete')
            for relative in (entry.ENV_REL/'preparation-manifest.json',entry.REPORT_REL/'batch-manifest.json'):
                m=json.loads((root/relative).read_text())
                for record in m['outputs']:
                    self.assertEqual(entry.office.file_record(root/record['path'],Path(record['path'])),record)
                self.assertNotIn(str(relative),[r['path'] for r in m['outputs']])
            self.assertFalse(entry.plan_mode(root)['ready_for_execution'])
        self.assertFalse(root.exists())

    def test_cleanup_failure_stops_remaining_and_keeps_failed_archive(self):
        for mode,removed in (('failure','removed'),('ok','still_exists')):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp, \
                 external_boundaries(self,cleanup=mode,removal=removed) as (_,runtime,calls,_,_,_):
                root=Path(tmp);entry.freeze(root);approve(root)
                self.assertEqual(main(root,['--execute',entry.FLAG]),7)
                batch=json.loads((root/entry.REPORT_REL/'batch-summary.json').read_text())
                self.assertEqual([r['status'] for r in batch['results']],['failed']+['not_executed']*8)
                self.assertEqual(sum(calls.values()),2)
                self.assertEqual(runtime.removal_calls,1)
                self.assertTrue(batch['results'][0]['archive_verified'])

    def test_image_loss_stops_without_restoring(self):
        with tempfile.TemporaryDirectory() as tmp,external_boundaries(self,image_after=False) as (_,_,calls,_,_,_):
            root=Path(tmp);entry.freeze(root);approve(root)
            self.assertEqual(main(root,['--execute',entry.FLAG]),7)
            batch=json.loads((root/entry.REPORT_REL/'batch-summary.json').read_text())
            self.assertFalse(batch['results'][0]['image_retention_verified'])
            self.assertEqual([r['status'] for r in batch['results']],['failed']+['not_executed']*8)
            self.assertEqual(sum(calls.values()),2)

    def test_batch_reserve_prevents_start_and_all_remaining_are_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp,external_boundaries(self) as (_,_,calls,_,_,_):
            root=Path(tmp);identity=entry.build_identity(root)
            result=entry.office.run_batch(root,{},identity,
                start_monotonic=time.monotonic()-22000,identity_builder=entry.build_identity)
            self.assertEqual([r['status'] for r in result['results']],['not_executed']*9)
            self.assertEqual(result['stopped_reason'],'insufficient_remaining_budget_for_full_attempt')
            self.assertFalse(calls)
            self.assertFalse((root/entry.RAW_REL).exists())

    def test_shared_phase_timeouts_capped_by_batch_work_deadline(self):
        with tempfile.TemporaryDirectory() as tmp,external_boundaries(self) as (_,_,calls,_,_,_):
            root=Path(tmp);identity=entry.build_identity(root);task=identity['tasks'][0]
            config=entry.office.run_config(task['key'],0,task['image_ref'],task['image_id'],collection=entry.COLLECTION)
            plan={'run_id':'deadline-fixture','identity':identity,'identity_sha256':entry.office.identity_sha(identity),
                  'run_config':config,'run_inputs':[], 'batch_work_deadline_monotonic':time.monotonic()+.03}
            original=asyncio.wait_for
            limits=[]
            async def capture(awaitable,timeout):
                limits.append(timeout)
                return await original(awaitable,timeout=timeout)
            with patch('asyncio.wait_for',new=capture):
                summary=asyncio.run(entry.office.shared.run_attempt(root,plan))
            self.assertEqual(limits[0],0)
            self.assertTrue(all(0<=t<=.03 for t in limits))
            self.assertFalse(calls)
            self.assertTrue(summary['outcome']['infra_failures'])
            assert_archive(self,root,summary)


if __name__ == '__main__':
    unittest.main()
