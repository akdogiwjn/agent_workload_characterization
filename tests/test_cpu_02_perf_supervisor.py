import os
import signal
import subprocess
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from scripts import cpu_02_perf_supervisor as supervisor
from agent_workload_characterization.runners import cpu_02_entry as cpu02


class PerfSupervisorTests(unittest.TestCase):
    def test_fixed_argv_has_no_command_dispatch(self):
        argv=cpu02.build_perf_supervisor_argv(
            '/usr/local/libexec/cpu02-perf-supervisor',host_pid=17,
            starttime_ticks=19,pgid=23,data_path='/x/data',ctl_path='/x/c',
            ack_path='/x/a',deadline=42.5,owner_uid=1000)
        self.assertEqual(argv[:4],['sudo','--non-interactive','--',
                                   '/usr/local/libexec/cpu02-perf-supervisor'])
        self.assertIn('--event',argv);self.assertIn('cycles',argv)
        self.assertNotIn('sh',argv);self.assertNotIn('python', ' '.join(argv))

    def test_path_and_fixed_parameter_rejections_are_safe(self):
        with mock.patch.object(supervisor,'_target_identity',side_effect=AssertionError):
            args=Namespace(event='instructions',frequency=99,deadline=time.monotonic()+5,
                output='/tmp/no',control='/tmp/no',ack='/tmp/no',target_pid=1,
                target_starttime=1,target_pgid=1)
            self.assertEqual(supervisor.run(args),3)

    def test_target_identity_mismatch_rejected_before_perf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'control').write_text('');(root/'ack').write_text('')
            args=Namespace(event='cycles',frequency=99,deadline=time.monotonic()+5,
                output=str(root/'data'),control=str(root/'control'),ack=str(root/'ack'),
                target_pid=1,target_starttime=1,target_pgid=1)
            with mock.patch.object(supervisor,'ALLOWED_ROOT',root), \
                 mock.patch.object(supervisor,'_target_identity',side_effect=ValueError('target_identity_changed')), \
                 mock.patch.object(supervisor.subprocess,'Popen') as popen:
                self.assertEqual(supervisor.run(args),3)
        popen.assert_not_called()

    def test_watchdog_reaps_real_test_child(self):
        child=subprocess.Popen(['sleep','30'],start_new_session=True)
        events=supervisor._stop_and_reap(child,time.monotonic()+2)
        self.assertIsNotNone(child.poll())
        self.assertTrue(any('perf_exit:' in e for e in events))

    def test_disconnect_recovery_is_explicit_and_bounded(self):
        child=subprocess.Popen(['sleep','30'],start_new_session=True)
        class Proc:
            def __init__(self,p):self.p=p;self.pid=p.pid;self.returncode=None
            def poll(self):
                self.returncode=self.p.poll();return self.returncode
            def wait(self,timeout=None):
                self.returncode=self.p.wait(timeout=timeout);return self.returncode
        proc=Proc(child)
        events=supervisor._stop_and_reap(proc,time.monotonic()+2)
        self.assertIsNotNone(child.poll())
        self.assertTrue(events)


if __name__=='__main__': unittest.main()
