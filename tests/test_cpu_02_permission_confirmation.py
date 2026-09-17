import json
import io
import os
import stat
import subprocess
import sys
import time
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from agent_workload_characterization.runners import cpu_02_entry as cpu02
from agent_workload_characterization.runners import cpu_02_permission_confirmation as confirm
from agent_workload_characterization.runners.container_runtime import ContainerHandle
from tests.test_cpu_02 import make_proc_view


class LocalWorkerRuntime:
    def __init__(self, proc_root):
        self.proc_root=proc_root;self.proc=None;self.starts=0;self.stops=0

    def start(self,spec,timeout_s=15):
        self.starts+=1
        return ContainerHandle('fake-confirmation',spec)

    def open_interactive(self,handle,command,timeout_s):
        command='CONFIRM_CONTAINER_PID=7 '+command
        self.proc=subprocess.Popen(['bash','-lc',command],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True)
        stat_text=Path(f'/proc/{self.proc.pid}/stat').read_text()
        start=int(stat_text.rsplit(')',1)[1].split()[19])
        ns=int(os.readlink(f'/proc/{self.proc.pid}/ns/pid').split('[')[1][:-1])
        make_proc_view(self.proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':ns},
            {'pid':self.proc.pid,'nspid':[self.proc.pid,7],
             'starttime':start,'ns':ns}])
        return self.proc

    def container_init_pid(self,handle,timeout_s=15): return 900001
    def stop(self,handle,timeout_s=15): self.stops+=1
    def verify_removal(self,handle,timeout_s=15): return 'removed'
    def cleanup_pending(self,timeout_s=15): return []


class NoDoneRuntime(LocalWorkerRuntime):
    """A real local JSONL worker which reaches perf and then omits done."""
    def open_interactive(self,handle,command,timeout_s):
        code=("import json,os,sys,time;"
              "s=open('/proc/self/stat').read().rsplit(')',1)[1].split();"
              "p=os.getpid(); t=int(s[19]); n=os.readlink('/proc/self/ns/pid');"
              "print(json.dumps({'event':'ready','pid':p,'container_process_pid':p,'starttime_ticks':t,'pid_namespace':n}),flush=True);"
              "sys.stdin.readline();"
              "print(json.dumps({'event':'started','pid':p,'container_process_pid':p,'started_monotonic':time.monotonic()}),flush=True);"
              "time.sleep(60)")
        self.proc=subprocess.Popen(['python3','-u','-c',code],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True)
        stat_text=Path(f'/proc/{self.proc.pid}/stat').read_text()
        start=int(stat_text.rsplit(')',1)[1].split()[19])
        ns=int(os.readlink(f'/proc/{self.proc.pid}/ns/pid').split('[')[1][:-1])
        make_proc_view(self.proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':ns},
            {'pid':self.proc.pid,'nspid':[self.proc.pid],'starttime':start,'ns':ns}])
        return self.proc


class FakePerf:
    class Proc:
        def __init__(self,returncode): self.returncode=returncode
        def poll(self): return self.returncode

    def __init__(self,returncode=0):
        self.commands=[];self.status='started';self.sample=True;self.returncode=returncode

    def factory(self,**kwargs):
        self.host_pid=kwargs['host_pid'];self.data_path=Path(kwargs['data_path'])
        self.data_path.write_bytes(b'synthetic-perf-sample')
        return {'status':'started','host_pid':self.host_pid,'perf_pid':1234,
                'ack_timeout_s':1,'proc':self.Proc(self.returncode)}


def fake_report_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv,0,
        stdout="# Samples: 3 of event 'cycles'\n"
               "# Overhead Command Shared Object Symbol\n"
               "  100.00% worker libfake.so [.] work\n",stderr='')


def zero_sample_report_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv,0,
        stdout="# Samples: 0 of event 'cycles'\n",stderr='')


class PermissionConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.proc_root=self.root/'proc';make_proc_view(self.proc_root,[
            {'pid':900001,'nspid':[900001,1],'starttime':1,'ns':4026531234}])

    def tearDown(self): self.tmp.cleanup()

    def _fake_perf(self, mode):
        path=self.root/f'fake-perf-{mode}.py'
        body="""#!/usr/bin/env python3
import sys, time
mode=__file__.split('fake-perf-',1)[1].split('.py',1)[0]
if mode == 'early':
    sys.stderr.write('synthetic perf startup failure\\n'); sys.stderr.flush(); raise SystemExit(7)
if mode == 'early-secret':
    sys.stderr.write('API_KEY=CANARY_SECRET\\n'); sys.stderr.flush(); raise SystemExit(7)
if mode == 'flood':
    sys.stdout.write('O'*400000); sys.stdout.flush()
    sys.stderr.write('E'*400000); sys.stderr.flush(); raise SystemExit(0)
time.sleep(30)
"""
        path.write_text(body);path.chmod(0o755)
        return path

    def _close_fake_perf(self, perf):
        for t in perf.get('drains') or []: t.join(timeout=2)
        proc=perf.get('proc')
        if proc is not None and proc.poll() is None:
            proc.kill();proc.wait(timeout=2)
        for fd in ('ctl_fd','ack_fd'):
            if perf.get(fd) is not None:
                try: os.close(perf[fd])
                except OSError: pass

    def test_perf_early_nonzero_exit_is_retained(self):
        path=self._fake_perf('early');output=self.root/'perf-early';output.mkdir()
        perf=cpu02.start_perf_controlled(str(path),123,output/'perf.data',
                                         cfg=cpu02.load_config(),output_dir=output)
        self._close_fake_perf(perf)
        self.assertEqual(perf['proc'].returncode,7)
        self.assertIn('synthetic perf startup failure',perf['output_evidence']['stderr'])
        self.assertEqual(perf['output_evidence']['stderr_total_bytes'],31)

    def test_perf_alive_without_ack_records_timeout_then_cleanup(self):
        path=self._fake_perf('alive');output=self.root/'perf-alive';output.mkdir()
        perf=cpu02.start_perf_controlled(str(path),123,output/'perf.data',
                                         cfg=cpu02.load_config(),output_dir=output)
        result=cpu02.control_cmd(perf,'enable',deadline=time.monotonic()+.05)
        self.assertEqual(result['error'],'ack_timeout')
        events=cpu02.stop_perf(perf,deadline=time.monotonic()+2,limit_s=.5,
                                on_exhausted=lambda:None)
        self.assertTrue(any('group_stopped' in str(x) for x in events))
        self._close_fake_perf(perf)

    def test_perf_output_is_bounded_and_marked_truncated(self):
        path=self._fake_perf('flood');output=self.root/'perf-flood';output.mkdir()
        perf=cpu02.start_perf_controlled(str(path),123,output/'perf.data',
                                         cfg=cpu02.load_config(),output_dir=output)
        self._close_fake_perf(perf)
        evidence=perf['output_evidence']
        self.assertTrue(evidence['stdout_truncated'])
        self.assertTrue(evidence['stderr_truncated'])
        self.assertGreater(evidence['stdout_total_bytes'],1<<18)
        self.assertGreater(evidence['stderr_total_bytes'],1<<18)

    def test_perf_normal_ack_path_uses_real_control_pipe(self):
        path=self._fake_perf('alive');output=self.root/'perf-ack';output.mkdir()
        perf=cpu02.start_perf_controlled(str(path),123,output/'perf.data',
                                         cfg=cpu02.load_config(),output_dir=output)
        os.write(perf['ack_fd'],b'ack\n')
        result=cpu02.control_cmd(perf,'enable',deadline=time.monotonic()+1)
        self.assertTrue(result['ack'])
        events=cpu02.stop_perf(perf,deadline=time.monotonic()+2,limit_s=.5,
                                on_exhausted=lambda:None)
        self.assertTrue(any('group_stopped' in str(x) for x in events))
        self._close_fake_perf(perf)

    def test_identity_change_refuses_process_group_signal(self):
        class Proc:
            pid=4242
            def poll(self): return None
        perf={'proc':Proc(),'perf_pid':4242,'perf_starttime_ticks':11,
              'perf_pgid':4242,'ctl_fd':-1,'ack_fd':-1,'ack_timeout_s':0.01}
        with mock.patch.object(cpu02,'control_cmd',return_value={'ack':False}), \
             mock.patch.object(cpu02,'read_starttime',return_value=12), \
             mock.patch.object(cpu02,'_group_alive',return_value=True), \
             mock.patch.object(cpu02.os,'killpg') as killpg:
            events=cpu02.stop_perf(perf,deadline=time.monotonic()+.2,
                                   limit_s=.05,on_exhausted=lambda:None)
        self.assertIn('identity_changed_no_signal',events)
        killpg.assert_not_called()

    def test_permission_denied_stop_is_unconfirmed_and_reaps(self):
        path=self._fake_perf('alive');output=self.root/'perf-stop-denied';output.mkdir()
        perf=cpu02.start_perf_controlled(str(path),123,output/'perf.data',
                                         cfg=cpu02.load_config(),output_dir=output)
        with mock.patch.object(cpu02,'control_cmd',return_value={'ack':False}), \
             mock.patch.object(cpu02.os,'killpg',side_effect=PermissionError(1,'denied')):
            events=cpu02.stop_perf(perf,deadline=time.monotonic()+.35,
                                   limit_s=.05,on_exhausted=lambda:None)
        self.assertFalse(any(str(x).endswith('group_stopped') for x in events))
        self.assertTrue(any('PermissionError' in str(x) for x in events))
        self._close_fake_perf(perf)

    def test_confirmation_records_unconfirmed_recovery_not_just_fail(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-recovery-denied'
        fake=FakePerf()
        def stop_denied(perf,**kwargs):
            return ['stop_cmd_ack=False','SIGINT:PermissionError',
                    'SIGKILL:PermissionError','SIGKILL:group_alive_after_wait']
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':False,'error':'ack_timeout'}), \
             mock.patch.object(cpu02,'stop_perf',stop_denied):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=time.monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['cleanup']['perf_recovery']['status'],'unconfirmed')
        self.assertIn('no_privileged_signal_sent',
                      result['cleanup']['perf_recovery']['signal_policy'])
        self.assertEqual(result['cleanup']['worker'],'reaped')

    def test_sudo_record_argv_is_narrow_and_data_file_is_user_owned(self):
        output=self.root/'perf-sudo';output.mkdir()
        class Proc:
            pid=321
            stdout=io.StringIO('')
            stderr=io.StringIO('')
            def poll(self): return None
            def kill(self): pass
            def wait(self,timeout=None): pass
        proc=Proc()
        with mock.patch.object(cpu02.subprocess,'Popen',return_value=proc) as popen:
            perf=cpu02.start_perf_controlled('/usr/bin/perf',321,output/'perf.data',
                cfg=cpu02.load_config(),output_dir=output,sudo=True)
        argv=popen.call_args.args[0]
        self.assertEqual(argv[:4],['sudo','--non-interactive','--','/usr/bin/perf'])
        self.assertIn('-D',argv);self.assertIn('-1',argv)
        self.assertNotIn('sh',argv);self.assertTrue((output/'perf.data').is_file())
        self._close_fake_perf(perf)

    def test_sudo_record_rejection_cleans_control_files(self):
        output=self.root/'perf-sudo-reject';output.mkdir()
        with mock.patch.object(cpu02.subprocess,'Popen',
                               side_effect=PermissionError(13,'denied')) as popen:
            result=cpu02.start_perf_controlled('/usr/bin/perf',321,output/'perf.data',
                cfg=cpu02.load_config(),output_dir=output,sudo=True)
        self.assertEqual(result['status'],'launch_failed')
        self.assertEqual(popen.call_args.args[0][:4],
                         ['sudo','--non-interactive','--','/usr/bin/perf'])
        self.assertFalse((output/'perf_ctl.fifo').exists())
        self.assertFalse((output/'perf_ack.fifo').exists())
        self.assertFalse((output/'perf.data').exists())

    def test_early_exit_runs_confirmation_archive_without_raw_canary(self):
        runtime=LocalWorkerRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-early'
        identity=confirm.build_plan()['identity']
        class LoggedEarlyPerf(FakePerf):
            def factory(self,**kwargs):
                return {'status':'started','host_pid':kwargs['host_pid'],
                        'perf_pid':1234,'ack_timeout_s':1,
                        'proc':self.Proc(7),'output_evidence':{
                            'stdout':'', 'stderr':'API_KEY=CANARY_SECRET\n',
                            'stdout_total_bytes':0,'stderr_total_bytes':22,
                            'stdout_truncated':False,'stderr_truncated':False}}
        fake=LoggedEarlyPerf()
        def control(perf,name,**kwargs):
            return {'cmd':name,'ack':False,'error':'perf_exited_before_ack',
                    'process_exit_code':7}
        def stop(perf,**kwargs): return ['stop_cmd:group_stopped']
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root):
            with mock.patch.object(cpu02,'control_cmd',control), \
                 mock.patch.object(cpu02,'stop_perf',stop), \
                 mock.patch.object(cpu02,'guarded',side_effect=lambda path,new=False: Path(path)):
                result=confirm.run_confirmation(runtime,output,
                    identity=identity,deadline=time.monotonic()+20,
                    proc_root=self.proc_root,perf_factory=fake.factory,
                    work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('perf',result,f'starts={runtime.starts} cleanup={result.get("cleanup")}')
        self.assertEqual(result['perf']['enable_ack']['error'],
                         'perf_exited_before_ack')
        self.assertNotIn('output_evidence',result['perf'])
        stderr=(output/'perf_stderr.txt').read_text()
        self.assertIn('API_KEY=[REDACTED]',stderr)
        summary=(output/'summary.json').read_text()
        self.assertNotIn('CANARY_SECRET',summary)
        manifest=json.loads((output/'manifest.json').read_text())
        for name in ('perf_stdout.txt','perf_stderr.txt'):
            item=manifest['outputs'][name];file=output/name
            self.assertEqual(item['bytes'],file.stat().st_size)
            self.assertEqual(item['sha256'],__import__('hashlib').sha256(
                file.read_bytes()).hexdigest())

    def test_real_local_jsonl_worker_and_fake_perf_use_same_pid(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        fake=FakePerf();output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-1'
        def command(perf,name,**kwargs):
            fake.commands.append(name)
            return {'cmd':name,'ack':True}
        def stop(perf,**kwargs): return ['stop_cmd_ack=True','stop_cmd:group_stopped']
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',command), \
             mock.patch.object(cpu02,'stop_perf',stop):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,report_runner=fake_report_runner,work_seconds=.02)
        self.assertEqual(result['status'],'complete',result)
        self.assertEqual(result['namespace_status'],'confirmed')
        self.assertEqual(result['mapping']['host_pid'],result['worker_ready']['container_process_pid'])
        self.assertEqual(result['worker_ready']['pid'],result['worker_started']['pid'])
        self.assertEqual(result['worker_started']['pid'],result['worker_done']['pid'])
        self.assertEqual(fake.commands,['enable','disable'])
        self.assertEqual(result['cleanup']['worker'],'reaped')
        self.assertEqual(result['cleanup']['container'],'removed')
        manifest=json.loads((output/'manifest.json').read_text())
        self.assertEqual(manifest['status'],'complete')
        self.assertEqual(manifest['outputs']['summary.json']['bytes'],
                         (output/'summary.json').stat().st_size)
        self.assertIn('perf.data',manifest['outputs'])
        self.assertIn('report.json',manifest['outputs'])

    def test_zero_samples_fail_even_when_perf_data_exists(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        fake=FakePerf();output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-zero'
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,report_runner=zero_sample_report_runner,
                work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['perf']['sample_status'],'unavailable')
        self.assertEqual(result['report']['parsed']['evidence_status'],'header_zero')

    def test_nonzero_perf_exit_fails_even_with_report_samples(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        fake=FakePerf(returncode=2);output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-perf-fail'
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,report_runner=fake_report_runner,work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['perf']['process_exit_code'],2)
        self.assertEqual(result['report']['parsed']['total_samples'],3)

    def test_started_pid_mismatch_fails_after_perf_start(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        fake=FakePerf();output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-started-pid-fail'
        original=confirm._worker_command
        def bad_started(seconds):
            command=original(seconds)
            # Alter only the started event in the real worker protocol.
            return command.replace("'event':'started', 'pid':reported_pid", "'event':'started', 'pid':reported_pid+1")
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(confirm,'_worker_command',bad_started), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('CPU02Error',result['errors'])
        self.assertEqual(result['cleanup']['worker'],'reaped')

    def test_enable_failure_stops_perf_in_exception_cleanup(self):
        identity=confirm.build_plan()['identity'];runtime=LocalWorkerRuntime(self.proc_root)
        fake=FakePerf();output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-enable-fail'
        stops=[]
        def command(perf,name,**kwargs): return {'cmd':name,'ack':False}
        def stop(perf,**kwargs): stops.append(True);return ['stop_cmd:group_stopped']
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',command),mock.patch.object(cpu02,'stop_perf',stop):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=fake.factory,work_seconds=.01)
        self.assertEqual(result['status'],'FAIL');self.assertEqual(stops,[True])
        self.assertIn('perf_stop_events',result['cleanup'])

    def test_protocol_missing_done_fails_and_reaps(self):
        identity=confirm.build_plan()['identity'];runtime=NoDoneRuntime(self.proc_root)
        output=self.root/'reports/cpu/CPU-02/permission-confirmation/run-fail'
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(cpu02,'control_cmd',lambda *a,**k:{'ack':True}), \
             mock.patch.object(cpu02,'stop_perf',lambda *a,**k:['stop_cmd:group_stopped']):
            result=confirm.run_confirmation(runtime,output,identity=identity,
                deadline=__import__('time').monotonic()+20,proc_root=self.proc_root,
                perf_factory=lambda **kwargs: {'status':'started','proc':None},work_seconds=.01)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['cleanup']['worker'],'reaped')
        self.assertEqual(runtime.stops,1)

    def test_plan_is_side_effect_free_and_has_protocol_identity(self):
        plan=confirm.build_plan()
        self.assertEqual(plan['mode'],'plan_only')
        self.assertEqual(plan['identity']['confirmation_entry']['protocol'],
                         'ready -> release -> started -> bounded_cpu -> done')
        self.assertTrue(plan['identity']['confirmation_entry']['sha256'])
        self.assertFalse((self.root/'reports').exists())

    def test_main_rejects_identity_drift_before_runtime_start(self):
        identity=confirm.build_plan()['identity'];drift=json.loads(json.dumps(identity));drift['image']='drift'
        namespace=self.root/'reports/cpu/CPU-02/permission-confirmation'
        approval=namespace/'APPROVAL.json';attempt=namespace/'ATTEMPT_STARTED.json';namespace.mkdir(parents=True)
        approval.write_text(json.dumps({
            'approved':True,'approved_by':'lcq','checklist_identity':drift}))
        runtime=mock.Mock()
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(confirm,'build_plan',return_value={'identity':identity}), \
             mock.patch.object(confirm,'APPROVAL',approval),mock.patch.object(confirm,'ATTEMPT',attempt), \
             mock.patch.object(confirm,'ROOT',namespace),mock.patch.object(confirm,'RUNTIME_FACTORY',lambda:runtime):
            rc=confirm.main(['--execute','--i-approve-the-cpu-02-permission-confirmation'])
        self.assertEqual(rc,3);runtime.start.assert_not_called();self.assertFalse(attempt.exists())

    def test_main_refuses_second_attempt_without_starting_runtime(self):
        identity=confirm.build_plan()['identity']
        namespace=self.root/'reports/cpu/CPU-02/permission-confirmation'
        approval=namespace/'APPROVAL.json';attempt=namespace/'ATTEMPT_STARTED.json'
        approval.parent.mkdir(parents=True)
        approval.write_text(json.dumps({'approved':True,'approved_by':'lcq',
            'checklist_identity':identity}))
        runtime=mock.Mock()
        with mock.patch.object(cpu02,'PROJECT_ROOT',self.root), \
             mock.patch.object(confirm,'build_plan',return_value={'identity':identity}), \
             mock.patch.object(confirm,'APPROVAL',approval),mock.patch.object(confirm,'ATTEMPT',attempt), \
             mock.patch.object(confirm,'ROOT',namespace), \
             mock.patch.object(confirm,'local_docker_environment',nullcontext), \
             mock.patch.object(cpu02,'docker_preflight',return_value={'status':'NOT_READY'}), \
             mock.patch.object(confirm,'RUNTIME_FACTORY',lambda:runtime):
            self.assertEqual(confirm.main(['--execute','--i-approve-the-cpu-02-permission-confirmation']),4)
            before=attempt.read_bytes()
            self.assertEqual(confirm.main(['--execute','--i-approve-the-cpu-02-permission-confirmation']),3)
        runtime.start.assert_not_called()
        self.assertEqual(attempt.read_bytes(),before)

if __name__=='__main__': unittest.main()
