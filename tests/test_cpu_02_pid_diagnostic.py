import errno
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from agent_workload_characterization.runners import cpu_02_entry as cpu02
from agent_workload_characterization.runners import cpu_02_pid_diagnostic as diag
from agent_workload_characterization.runners.container_runtime import ContainerHandle
from tests.test_cpu_02 import make_proc_view


class DiagnosticRuntime:
    def __init__(self, proc_root):
        self.proc_root=proc_root;self.proc=None;self.last_proc=None;self.starts=0;self.stops=0

    def start(self,spec,timeout_s=15):
        self.starts+=1
        return ContainerHandle('diagnostic-container',spec)

    def open_interactive(self,handle,command,timeout_s):
        self.proc=subprocess.Popen(
            ['python3','-u','-c',
             "import json,os; print(json.dumps({'event':'supervisor_ready','pid':7,'starttime_ticks':222,'pid_namespace':'pid:[4026531234]'}),flush=True); input()"],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,bufsize=1)
        self.last_proc=self.proc
        make_proc_view(self.proc_root,[
            {'pid':900007,'nspid':[900007,7],'starttime':222,'ns':4026531234}])
        return self.proc

    def container_init_pid(self,handle,timeout_s=15): return 900001
    def stop(self,handle,timeout_s=15):
        self.stops+=1
    def verify_removal(self,handle,timeout_s=15): return 'removed'


class PIDDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.proc_root=self.root/'proc'
        make_proc_view(self.proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':111,'ns':4026531234}])

    def tearDown(self): self.tmp.cleanup()

    def test_proc_error_categories_are_safe_and_specific(self):
        for exc,category in ((PermissionError(errno.EPERM,'hidden'),'permission_denied'),
                             (FileNotFoundError(errno.ENOENT,'gone'),'process_missing_or_not_visible'),
                             (OSError(errno.EIO,'io'),'unknown')):
            result=cpu02.classify_proc_read_error('init_ns',900001,exc)
            self.assertEqual(result['category'],category)
            self.assertEqual(result['target_pid'],900001)
            self.assertNotIn('hidden',json.dumps(result))

    def test_mapping_keeps_unique_zero_and_multiple_gates(self):
        make_proc_view(self.proc_root,[
            {'pid':900007,'nspid':[900007,7],'starttime':222,'ns':4026531234}])
        self.assertEqual(cpu02.map_container_pid(7,222,900001,proc_root=self.proc_root)['status'],'ok')
        self.assertEqual(cpu02.map_container_pid(8,222,900001,proc_root=self.proc_root)['reason'],'no_unique_match')
        make_proc_view(self.proc_root,[
            {'pid':900008,'nspid':[900008,7],'starttime':222,'ns':4026531234}])
        self.assertEqual(cpu02.map_container_pid(7,222,900001,proc_root=self.proc_root)['reason'],'ambiguous_matches')

    def test_init_read_failure_is_classified_without_relaxing_mapping(self):
        with mock.patch('os.readlink',side_effect=PermissionError(errno.EACCES,'secret')):
            result=cpu02.map_container_pid(7,222,900001,proc_root=self.proc_root)
        self.assertEqual(result['read_error']['category'],'permission_denied')
        self.assertNotIn('secret',json.dumps(result))

    def test_default_plan_has_no_subprocess_and_is_independent(self):
        with mock.patch.object(diag.subprocess,'run',side_effect=AssertionError('NO PROC')) if hasattr(diag,'subprocess') else mock.patch('subprocess.run',side_effect=AssertionError('NO PROC')):
            with mock.patch('sys.stdout'):
                self.assertEqual(diag.main([]),0)
        self.assertFalse((self.root/'reports').exists())
        self.assertEqual(diag.DIAGNOSTIC_ID,'CPU-02-PID-DIAGNOSTIC-01')

    def test_success_path_runs_real_mapping_logic_and_archives(self):
        identity=diag.build_plan()['identity']
        runtime=DiagnosticRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/pid-diagnostic/diag-1'
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root):
            result=diag.run_diagnostic(runtime,output,identity=identity,
                                       deadline=__import__('time').monotonic()+20,
                                       proc_root=self.proc_root)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['mapping']['status'],'ok')
        self.assertTrue((output/'manifest.json').exists())
        self.assertEqual(runtime.starts,1);self.assertEqual(runtime.stops,1)
        self.assertIsNotNone(runtime.last_proc)
        self.assertIsNotNone(runtime.last_proc.poll())

    def test_failure_is_archived_and_cleaned(self):
        identity=diag.build_plan()['identity'];runtime=DiagnosticRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/pid-diagnostic/diag-fail'
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(runtime,'container_init_pid',return_value=None):
            result=diag.run_diagnostic(runtime,output,identity=identity,
                                       deadline=__import__('time').monotonic()+20,
                                       proc_root=self.proc_root)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue((output/'summary.json').exists())
        self.assertEqual(runtime.stops,1)

    def test_archive_overrun_updates_disk_state_and_hashes(self):
        identity=diag.build_plan()['identity'];runtime=DiagnosticRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/pid-diagnostic/diag-late'

        class Clock:
            value=100.0
            bumped=False
            def monotonic(self): return self.value
        clock=Clock();original_write=cpu02.write_json

        def write_with_archive_overrun(path,payload):
            original_write(path,payload)
            if Path(path).name=='manifest.json' and not clock.bumped:
                clock.value=121.0;clock.bumped=True

        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02.time,'monotonic',clock.monotonic), \
             mock.patch.object(cpu02,'write_json',write_with_archive_overrun):
            result=diag.run_diagnostic(runtime,output,identity=identity,
                                       deadline=120.0,proc_root=self.proc_root)

        summary=json.loads((output/'summary.json').read_text())
        manifest=json.loads((output/'manifest.json').read_text())
        summary_bytes=(output/'summary.json').read_bytes()
        summary_entry=manifest['outputs']['summary.json']
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['budget_overrun'])
        self.assertGreaterEqual(result['wall_s'],21.0)
        self.assertEqual(summary['status'],'FAIL')
        self.assertTrue(summary['budget_overrun'])
        self.assertEqual(manifest['status'],'FAIL')
        self.assertEqual(summary_entry['bytes'],len(summary_bytes))
        self.assertEqual(summary_entry['sha256'],hashlib.sha256(summary_bytes).hexdigest())

    def _main_with_temp_namespace(self, identity, runtime, argv):
        approval= self.root/'reports/cpu/CPU-02/pid-diagnostic/APPROVAL.json'
        attempt= self.root/'reports/cpu/CPU-02/pid-diagnostic/ATTEMPT_STARTED.json'
        approval.parent.mkdir(parents=True,exist_ok=True)
        approval.write_text(json.dumps({'approved':True,'approved_by':'synthetic',
                                        'approved_at_utc':'2026-09-16T00:00:00Z',
                                        'checklist_identity':identity}))
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(diag,'ROOT',approval.parent), \
             mock.patch.object(diag,'APPROVAL',approval), \
             mock.patch.object(diag,'ATTEMPT',attempt), \
             mock.patch.object(diag,'RUNTIME_FACTORY',lambda:runtime), \
             mock.patch.object(diag,'LOCAL_ENVIRONMENT',nullcontext), \
             mock.patch.object(diag,'PROC_ROOT',self.proc_root), \
             mock.patch.object(cpu02,'docker_preflight',return_value={'status':'READY'}):
            return diag.main(argv), attempt

    def test_main_rejects_identity_mismatch_without_start(self):
        runtime=DiagnosticRuntime(self.proc_root)
        identity=diag.build_plan()['identity'];drift=json.loads(json.dumps(identity))
        drift['image']='identity-drift'
        rc,attempt=self._main_with_temp_namespace(drift,runtime,
            ['--execute','--i-approve-the-cpu-02-pid-diagnostic'])
        self.assertEqual(rc,3);self.assertEqual(runtime.starts,0)
        self.assertFalse(attempt.exists())

    def test_main_rejects_duplicate_attempt_and_preserves_marker(self):
        runtime=DiagnosticRuntime(self.proc_root);identity=diag.build_plan()['identity']
        rc,attempt=self._main_with_temp_namespace(identity,runtime,
            ['--execute','--i-approve-the-cpu-02-pid-diagnostic'])
        self.assertEqual(rc,0);self.assertEqual(json.loads(attempt.read_text())['status'],'completed')
        # Re-enter the same namespace with the existing marker; no second
        # runtime is allowed and the original marker bytes remain unchanged.
        before=attempt.read_bytes()
        rc2,_=self._main_with_temp_namespace(identity,runtime,
            ['--execute','--i-approve-the-cpu-02-pid-diagnostic'])
        self.assertEqual(rc2,3);self.assertEqual(runtime.starts,1)
        self.assertEqual(attempt.read_bytes(),before)


if __name__=='__main__': unittest.main()
