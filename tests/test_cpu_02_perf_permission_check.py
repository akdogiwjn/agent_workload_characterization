import subprocess
import unittest
from pathlib import Path
from unittest import mock

from scripts import cpu_02_perf_permission_check as check
from tests.test_cpu_02_permission_confirmation import (
    FakePerf, LocalWorkerRuntime, fake_report_runner,
)
from tests.test_cpu_02 import make_proc_view
from agent_workload_characterization.runners import cpu_02_entry as cpu02


class PerfPermissionPreparationTests(unittest.TestCase):
    def test_plan_is_side_effect_free_and_has_only_readlink_sudo(self):
        runner=mock.Mock(side_effect=AssertionError('external operation'))
        with mock.patch.object(subprocess,'run',runner):
            plan=check.build_plan()
        self.assertEqual(plan['mode'],'plan_only')
        self.assertEqual(len(plan['sudo_allowlist']),3)
        self.assertTrue(all('/usr/bin/readlink' in item['argv']
                            for item in plan['sudo_allowlist'][:2]))
        self.assertEqual(plan['sudo_allowlist'][1]['role'],'worker_candidate_namespace')
        self.assertEqual(plan['sudo_allowlist'][1]['max_calls'],1)
        self.assertEqual(plan['sudo_allowlist'][2]['role'],'perf_record')
        self.assertEqual(plan['sudo_allowlist'][2]['max_calls'],1)
        runner.assert_not_called()

    def test_sudo_reader_requires_positive_pid_and_valid_namespace(self):
        calls=[]
        def runner(argv,**kwargs):
            calls.append((argv,kwargs))
            return subprocess.CompletedProcess(argv,0,stdout='pid:[4026539999]\n',stderr='')
        value=check._sudo_init_namespace(123,runner=runner,deadline=__import__('time').monotonic()+5)
        self.assertEqual(value,'pid:[4026539999]')
        self.assertEqual(calls[0][0],['sudo','--non-interactive','--','/usr/bin/readlink','/proc/123/ns/pid'])
        with self.assertRaises(Exception):
            check._sudo_init_namespace(0,runner=runner,deadline=__import__('time').monotonic()+5)
        self.assertEqual(len(calls),1)

    def test_sudo_reader_nonzero_and_invalid_output_are_rejected(self):
        def failed(argv,**kwargs): return subprocess.CompletedProcess(argv,1,stdout='',stderr='')
        with self.assertRaises(Exception):
            check._sudo_init_namespace(123,runner=failed,deadline=__import__('time').monotonic()+5)
        def invalid(argv,**kwargs): return subprocess.CompletedProcess(argv,0,stdout='not-a-namespace\n',stderr='')
        with self.assertRaises(Exception):
            check._sudo_init_namespace(123,runner=invalid,deadline=__import__('time').monotonic()+5)

    def test_sudo_reader_timeout_is_classified_without_error_text(self):
        def timed(argv,**kwargs): raise subprocess.TimeoutExpired(argv,1)
        with self.assertRaisesRegex(Exception,'sudo_namespace_timeout'):
            check._sudo_init_namespace(123,runner=timed,deadline=__import__('time').monotonic()+5)

    def test_run_once_uses_absolute_deadline_and_real_sudo_reader(self):
        import tempfile
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)
        proc_root=root/'proc'; make_proc_view(proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':4026531234}])
        runtime=LocalWorkerRuntime(proc_root); fake=FakePerf(); sudo_calls=[]
        def sudo_runner(argv,**kwargs):
            sudo_calls.append((argv,kwargs))
            ns=__import__('os').readlink(f'/proc/{runtime.proc.pid}/ns/pid')
            return subprocess.CompletedProcess(argv,0,stdout=ns+'\n',stderr='')
        def sudo_reader(pid, *, deadline):
            self.assertGreater(deadline,__import__('time').monotonic())
            return check._sudo_init_namespace(pid,runner=sudo_runner,deadline=deadline)
        def command(perf,name,**kwargs): return {'cmd':name,'ack':True}
        with mock.patch.object(check.cpu02,'PROJECT_ROOT',root), \
             mock.patch.object(check.cpu02,'control_cmd',command), \
             mock.patch.object(check.cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=check.run_once(runtime=runtime,
                output_dir=root/'reports/cpu/CPU-02/perf-permission-check/run-1',
                deadline=__import__('time').monotonic()+20,sudo_reader=sudo_reader,
                proc_root=proc_root,perf_factory=fake.factory,report_runner=fake_report_runner)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(sudo_calls),1)
        self.assertEqual(sudo_calls[0][0][:4],['sudo','--non-interactive','--','/usr/bin/readlink'])
        tmp.cleanup()

    def test_run_once_falls_back_to_sudo_for_candidate_eacces(self):
        import os
        import tempfile
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)
        proc_root=root/'proc'; make_proc_view(proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':4026531234}])
        runtime=LocalWorkerRuntime(proc_root); fake=FakePerf(); sudo_calls=[]
        original_readlink=os.readlink
        def readlink(path):
            if str(proc_root) in str(path) and str(path).endswith('/ns/pid'):
                raise PermissionError(13,'candidate namespace denied')
            return original_readlink(path)
        def sudo_runner(argv,**kwargs):
            sudo_calls.append(argv)
            return subprocess.CompletedProcess(argv,0,stdout='pid:[4026531234]\n',stderr='')
        def sudo_reader(pid, *, deadline):
            return check._sudo_init_namespace(pid,runner=sudo_runner,deadline=deadline)
        with mock.patch.object(cpu02,'PROJECT_ROOT',root), \
             mock.patch.object(cpu02.os,'readlink',side_effect=readlink), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=check.run_once(runtime=runtime,
                output_dir=root/'reports/cpu/CPU-02/perf-permission-check/run-eacces',
                deadline=__import__('time').monotonic()+20,sudo_reader=sudo_reader,
                proc_root=proc_root,perf_factory=fake.factory,report_runner=fake_report_runner)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['mapping']['host_pid'],runtime.proc.pid)
        self.assertTrue(any('/proc/%s/ns/pid' % runtime.proc.pid in ' '.join(a) for a in sudo_calls))
        self.assertTrue(result['sudo_candidate_namespace_reads'][0]['status']=='ok')
        tmp.cleanup()

    def test_mapping_identity_change_blocks_perf(self):
        import tempfile
        class ChangingRuntime(LocalWorkerRuntime):
            def __init__(self, proc_root):
                super().__init__(proc_root); self.init_calls=0
            def container_init_pid(self, handle, timeout_s=15):
                self.init_calls += 1
                return 900001 if self.init_calls == 1 else 900002
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)
        proc_root=root/'proc'; make_proc_view(proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':4026531234}])
        runtime=ChangingRuntime(proc_root); fake=FakePerf(); perf_calls=[]
        def sudo_reader(pid, *, deadline): return 'pid:[4026531234]'
        def perf_factory(**kwargs): perf_calls.append(kwargs); return fake.factory(**kwargs)
        with mock.patch.object(check.cpu02,'PROJECT_ROOT',root), \
             mock.patch.object(check.cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(check.cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=check.run_once(runtime=runtime,
                output_dir=root/'reports/cpu/CPU-02/perf-permission-check/run-id-change',
                deadline=__import__('time').monotonic()+20,sudo_reader=sudo_reader,
                proc_root=proc_root,perf_factory=perf_factory,report_runner=fake_report_runner)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('CPU02Error',result['errors'])
        self.assertEqual(perf_calls,[])
        tmp.cleanup()

    def test_sampling_work_deadline_exhaustion_blocks_perf(self):
        import tempfile
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)
        runtime=mock.Mock(); runtime.cleanup_pending.return_value=[]; perf_calls=[]
        with mock.patch.object(check.cpu02,'PROJECT_ROOT',root):
            result=check.run_once(runtime=runtime,
                output_dir=root/'reports/cpu/CPU-02/perf-permission-check/run-budget',
                deadline=__import__('time').monotonic()+15,
                sudo_reader=lambda *a,**k:'pid:[1]',
                perf_factory=lambda **kw: perf_calls.append(kw))
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(perf_calls,[])
        runtime.start.assert_not_called()
        tmp.cleanup()

    def test_candidate_sudo_call_limit_blocks_second_candidate_and_perf(self):
        import os
        import tempfile
        original_readlink=os.readlink
        class TwoCandidateRuntime(LocalWorkerRuntime):
            def open_interactive(self, handle, command, timeout_s):
                proc=super().open_interactive(handle,command,timeout_s)
                stat_text=Path(f'/proc/{proc.pid}/stat').read_text()
                start=int(stat_text.rsplit(')',1)[1].split()[19])
                ns=int(os.readlink(f'/proc/{proc.pid}/ns/pid').split('[')[1][:-1])
                make_proc_view(self.proc_root,[
                    {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':ns},
                    {'pid':proc.pid,'nspid':[proc.pid,7],'starttime':start,'ns':ns},
                    {'pid':999999,'nspid':[999999,7],'starttime':start,'ns':ns}])
                return proc
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name); proc_root=root/'proc'
        make_proc_view(proc_root,[{'pid':900001,'nspid':[900001,1],'starttime':1,'ns':4026531234}])
        runtime=TwoCandidateRuntime(proc_root); fake=FakePerf(); sudo_calls=[]; perf_calls=[]
        def sudo_reader(pid, *, deadline): sudo_calls.append(pid); return 'pid:[4026531234]'
        def perf_factory(**kwargs): perf_calls.append(kwargs); return fake.factory(**kwargs)
        def readlink(path):
            if str(proc_root) in str(path) and str(path).endswith('/ns/pid'):
                raise PermissionError(13,'denied')
            return original_readlink(path)
        with mock.patch.object(check.cpu02,'PROJECT_ROOT',root), \
             mock.patch.object(check.cpu02.os,'readlink',side_effect=readlink), \
             mock.patch.object(check.cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(check.cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=check.run_once(runtime=runtime,
                output_dir=root/'reports/cpu/CPU-02/perf-permission-check/run-limit',
                deadline=__import__('time').monotonic()+20,sudo_reader=sudo_reader,
                proc_root=proc_root,perf_factory=perf_factory,report_runner=fake_report_runner)
        self.assertEqual(result['status'],'FAIL')
        # One init read plus one candidate read; the second candidate is
        # rejected by the fixed candidate-only limit before another sudo call.
        self.assertEqual(len(sudo_calls),2)
        self.assertEqual(perf_calls,[])
        tmp.cleanup()

    def test_candidate_identity_mismatch_never_escalates(self):
        import tempfile
        from agent_workload_characterization.runners import cpu_02_entry as cpu02
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)/'proc'
        make_proc_view(root,[{'pid':111,'nspid':[111,8],'starttime':9,'ns':1}])
        calls=[]
        result=cpu02.map_container_pid(7,9,900,proc_root=root,
            init_namespace='pid:[1]',candidate_namespace_reader=lambda *a:calls.append(a))
        self.assertEqual(result['status'],'map_failed'); self.assertEqual(calls,[])
        tmp.cleanup()

    def test_nonpermission_candidate_read_error_never_escalates(self):
        import os
        import tempfile
        from agent_workload_characterization.runners import cpu_02_entry as cpu02
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)/'proc'
        make_proc_view(root,[{'pid':111,'nspid':[111,7],'starttime':9,'ns':1}])
        original=os.readlink; calls=[]
        def readlink(path):
            if str(root) in str(path) and str(path).endswith('/ns/pid'):
                raise FileNotFoundError(2,'missing')
            return original(path)
        with mock.patch.object(cpu02.os,'readlink',side_effect=readlink):
            result=cpu02.map_container_pid(7,9,900,proc_root=root,
                init_namespace='pid:[1]',candidate_namespace_reader=lambda *a:calls.append(a))
        self.assertEqual(result['status'],'map_failed'); self.assertEqual(calls,[])
        tmp.cleanup()

    def test_namespace_difference_and_multiple_matches_refuse_perf_boundary(self):
        import os
        import tempfile
        from agent_workload_characterization.runners import cpu_02_entry as cpu02
        tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)/'proc'
        make_proc_view(root,[
            {'pid':111,'nspid':[111,7],'starttime':9,'ns':1},
            {'pid':112,'nspid':[112,7],'starttime':9,'ns':1}])
        original=os.readlink; calls=[]
        def readlink(path):
            if str(root) in str(path) and str(path).endswith('/ns/pid'):
                raise PermissionError(13,'denied')
            return original(path)
        with mock.patch.object(cpu02.os,'readlink',side_effect=readlink):
            result=cpu02.map_container_pid(7,9,900,proc_root=root,
                init_namespace='pid:[1]',candidate_namespace_reader=lambda *a:(calls.append(a) or 'pid:[2]'))
        self.assertEqual(result['status'],'map_failed')
        self.assertEqual(result['reason'],'no_unique_match')
        self.assertEqual(len(calls),2)
        tmp.cleanup()


if __name__=='__main__': unittest.main()
