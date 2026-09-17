"""Offline R1 gate tests: isolated namespace, real entry and shared batch."""
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

import yaml

from agent_workload_characterization.runners import cpu_02_entry as base
from agent_workload_characterization.runners import cpu_02_r1_entry as r1
from tests.test_cpu_02 import FakeCPU02Runtime, fake_grade, make_proc_view


class CPU02R1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = self.root / 'cpu_02.yaml'
        cfg = base.load_config()
        cfg['perf']['binary'] = str(self.root / 'fake_perf')
        self.catalog.write_text(yaml.safe_dump(cfg))
        self.namespace = self.root / 'reports/cpu/CPU-02/retries/R1'
        self.proc_root = self.root / 'proc'
        make_proc_view(self.proc_root, [
            {'pid': 900001, 'nspid': [900001, 1],
             'starttime': 111, 'ns': 4026531234}])
        self.eval_file = self.root / 'eval.sh'
        self.eval_file.write_text('#!/bin/bash\n'
                                  'echo ">>>>> Start Test Output"\n'
                                  'echo "test_floatformat ... ok"\n'
                                  'echo ">>>>> End Test Output"\n')
        self.fake_perf = self.root / 'fake_perf'
        # The real FakeCPU02Runtime uses the test module's fake perf through
        # the temporary catalog; its script is copied from the fixture.
        from tests.test_cpu_02 import FAKE_PERF
        self.fake_perf.write_text(FAKE_PERF); self.fake_perf.chmod(0o755)
        self.runtime = None
        self.patches = mock.patch.multiple(
            base, PROJECT_ROOT=self.root, CATALOG=self.catalog,
            APPROVAL=self.namespace / 'unused-old-approval.json',
            ATTEMPT=self.namespace / 'unused-old-attempt.json'),
        self.patches = self.patches[0]
        self.patches.start()
        self.r1patch = mock.patch.multiple(
            r1, PROJECT_ROOT=self.root, ROOT=self.namespace,
            APPROVAL=self.namespace / 'APPROVAL.json',
            ATTEMPT=self.namespace / 'ATTEMPT_STARTED.json',
            LOCAL_ENVIRONMENT=nullcontext,
            PROC_ROOT=self.proc_root)
        self.r1patch.start()

    def tearDown(self):
        if self.runtime:
            for proc in self.runtime.children:
                if proc.poll() is None:
                    proc.kill(); proc.wait(timeout=1)
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
        self.r1patch.stop(); self.patches.stop(); self.tmp.cleanup()

    def plan(self):
        return r1.build_plan()

    def approve(self, identity=None):
        self.namespace.mkdir(parents=True, exist_ok=True)
        self.base_identity = identity or self.plan()['identity']
        r1.APPROVAL.write_text(json.dumps({
            'approved': True, 'approved_by': 'synthetic-user',
            'approved_at_utc': '2026-09-16T00:00:00Z',
            'checklist_identity': self.base_identity}))

    def configure_entry(self, runtime=None, *, preflight=True):
        self.runtime = runtime or FakeCPU02Runtime(
            eval_file=self.eval_file, proc_root=self.proc_root, init_pid=900001)
        runtime_factory = mock.patch.object(r1, 'RUNTIME_FACTORY',
                                            lambda: self.runtime)
        grader = mock.patch.object(r1, 'GRADER', fake_grade)
        runtime_factory.start(); grader.start()
        self.addCleanup(runtime_factory.stop)
        self.addCleanup(grader.stop)
        if preflight:
            self.preflight = mock.patch.object(
                base, 'preflight_checks',
                return_value={'status': 'READY'})
            self.docker = mock.patch.object(
                base, 'docker_preflight',
                return_value={'status': 'READY'})
        else:
            self.preflight = mock.patch.object(
                base, 'preflight_checks',
                return_value={'status': 'NOT_READY'})
            self.docker = mock.patch.object(
                base, 'docker_preflight',
                return_value={'status': 'NOT_READY'})
        self.preflight.start(); self.docker.start()
        self.addCleanup(self.preflight.stop)
        self.addCleanup(self.docker.stop)

    def test_default_plan_is_r1_and_side_effect_free(self):
        with mock.patch('sys.stdout'):
            self.assertEqual(r1.main([]), 0)
        self.assertEqual(r1.build_plan()['retry_id'], 'R1')
        self.assertEqual(r1.build_plan()['identity']['approval'],
                         'reports/cpu/CPU-02/retries/R1/APPROVAL.json')
        self.assertFalse(self.namespace.exists())

    def test_missing_approval_rejects_without_runner(self):
        self.configure_entry()
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 3)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertFalse(r1.ATTEMPT.exists())

    def test_old_approval_rejects_without_runner(self):
        self.configure_entry(); self.approve(self.plan()['identity'])
        old = json.loads(json.dumps(self.plan()['identity']))
        old.pop('retry_id'); old['collection'] = 'CPU-02'
        r1.APPROVAL.write_text(json.dumps({'approved': True, 'approved_by': 'x',
                                           'approved_at_utc': 'x',
                                           'checklist_identity': old}))
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 3)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertFalse(r1.ATTEMPT.exists())

    def test_identity_drift_rejects_without_runner(self):
        self.configure_entry()
        drifted = json.loads(json.dumps(self.plan()['identity']))
        drifted['image'] = 'drifted-image'
        self.approve(drifted)
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 3)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertFalse(r1.ATTEMPT.exists())

    def test_r1_approval_allows_once_and_second_marker_rejects(self):
        self.configure_entry(); self.approve()
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 0)
        self.assertTrue(r1.ATTEMPT.exists())
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 3)
        self.assertEqual(self.runtime.start_calls, 1)

    def test_preflight_failure_writes_r1_evidence_without_start(self):
        self.configure_entry(preflight=False); self.approve()
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 4)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertEqual(json.loads(r1.ATTEMPT.read_text())['status'], 'failed')
        self.assertEqual(json.loads((self.namespace / 'PREFLIGHT.json').read_text())['status'],
                         'NOT_READY')

    def test_evaluator_unavailable_fails_before_runtime_start(self):
        self.configure_entry(); self.approve()
        with mock.patch.object(base, '_load_generated_eval_script',
                               side_effect=base.CPU02Error(
                                   'evaluator_unavailable')):
            rc = r1.main(['--execute', '--i-approve-the-cpu-02-r1'])
        self.assertEqual(rc, 5)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertEqual(json.loads(r1.ATTEMPT.read_text())['status'], 'failed')

    def test_generated_script_drift_fails_before_runtime_start(self):
        self.configure_entry(); self.approve()
        with mock.patch.object(base, '_load_generated_eval_script',
                               side_effect=base.CPU02Error(
                                   'eval_script_unregistered_diff')):
            rc = r1.main(['--execute', '--i-approve-the-cpu-02-r1'])
        self.assertEqual(rc, 5)
        self.assertEqual(self.runtime.start_calls, 0)
        self.assertEqual(json.loads(r1.ATTEMPT.read_text())['status'], 'failed')

    def test_success_path_uses_shared_run_batch_in_r1_namespace(self):
        self.configure_entry(); self.approve()
        self.assertEqual(r1.main(['--execute', '--i-approve-the-cpu-02-r1']), 0)
        batches = [p for p in self.namespace.iterdir() if p.is_dir()]
        self.assertEqual(len(batches), 1)
        self.assertTrue((batches[0] / 'manifest.json').exists())
        self.assertEqual(json.loads(r1.ATTEMPT.read_text())['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
