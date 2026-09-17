import subprocess
import unittest
from unittest import mock

from scripts import cpu_02_namespace_sudo_compare as check


class FakeDocker:
    def __init__(self, name, *, state_pid=123, label_ok=True):
        self.name=name; self.state_pid=state_pid; self.label_ok=label_ok
        self.calls=[]; self.removed=False

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[0]=='docker':
            op=argv[3]
            if op=='ps':
                # Initial name lookup refuses pre-existing containers; final ID
                # lookup observes removal after rm.
                if 'id=' in ' '.join(argv):
                    return subprocess.CompletedProcess(argv,0,stdout='' if self.removed else self.name,stderr='')
                return subprocess.CompletedProcess(argv,0,stdout='',stderr='')
            if op=='run':
                return subprocess.CompletedProcess(argv,0,stdout='cid-1\n',stderr='')
            if op=='inspect':
                fmt=argv[5]
                label=self.name if self.label_ok else 'other-batch'
                if 'State.Pid' in fmt:
                    return subprocess.CompletedProcess(argv,0,
                        stdout=f'cid-1|{label}|{self.state_pid}\n',stderr='')
                return subprocess.CompletedProcess(argv,0,stdout=f'cid-1|{label}\n',stderr='')
            if op=='rm':
                self.removed=True
                return subprocess.CompletedProcess(argv,0,stdout='',stderr='')
        if argv[0]=='sudo':
            return subprocess.CompletedProcess(argv,0,stdout='pid:[4026539999]\n',stderr='')
        raise AssertionError(argv)


class NamespaceCompareTests(unittest.TestCase):
    def _run(self, fake, *, readlinker=lambda target: 'pid:[4026539999]'):
        with mock.patch.object(check, '_pid_starttime', return_value=77):
            return check.run_check(runner=fake, readlinker=readlinker,
                                   container_name=fake.name)

    def test_permission_denied_uses_direct_os_readlink_and_is_observed(self):
        fake=FakeDocker('compare-permission')
        def denied(target): raise PermissionError(13, 'denied')
        result=self._run(fake, readlinker=denied)
        self.assertEqual(result['comparison'], 'ordinary_failed_sudo_success')
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(any(argv[0]=='/usr/bin/readlink' for argv in fake.calls))
        self.assertTrue(any(argv[0]=='sudo' and '/usr/bin/readlink' in argv for argv in fake.calls))

    def test_ordinary_timeout_is_inconclusive(self):
        fake=FakeDocker('compare-timeout')
        def timed_out(target): raise subprocess.TimeoutExpired(['readlink'], 1)
        result=self._run(fake, readlinker=timed_out)
        self.assertEqual(result['comparison'], 'indeterminate')
        self.assertEqual(result['status'], 'inconclusive')

    def test_exited_container_is_removed_after_ownership_check(self):
        fake=FakeDocker('compare-exited', state_pid=0)
        result=self._run(fake)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['cleanup_stop'], 'ok')
        self.assertEqual(result['cleanup_container_id'], 'cid-1')
        self.assertTrue(any(argv[3:5]==['rm','-f'] and argv[-1]=='cid-1' for argv in fake.calls))

    def test_label_mismatch_never_deletes(self):
        fake=FakeDocker('compare-label', label_ok=False)
        result=self._run(fake)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['cleanup_verify'], 'identity_check_failed')
        self.assertFalse(any(argv[3]=='rm' for argv in fake.calls))


if __name__=='__main__': unittest.main()
