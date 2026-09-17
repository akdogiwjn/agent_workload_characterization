"""CPU-02 bounded OFFLINE tests: real entry, fake Docker runtime, fake perf,
real short owned supervisor process on the host, fake /proc view for the
PID mapping. No real Docker/perf/network/model; single test subprocesses
stay seconds and are killed and reaped in tearDown.
"""
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import yaml

from agent_workload_characterization.runners import cpu_02_entry as entry
from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, ScopeReader)

FAKE_PERF = r'''#!/usr/bin/python3.11
import base64, json, os, select, signal, sys, threading, time
args = sys.argv[1:]
MODE = os.environ.get('FAKE_PERF_MODE', 'normal')
META = os.environ.get('FAKE_PERF_META', '')
if args[0] == 'record':
    data_path = args[args.index('-o') + 1]
    if META:
        open(META, 'w').write(json.dumps({'argv': args, 'mode': MODE}))
    if MODE == 'exit_early':
        sys.exit(1)
    # documented control protocol (perf-record(1)): listen on ctl fifo for
    # enable/disable/stop, acknowledge each with "ack\n" on the ack fifo
    # (the HOST side created the fifos before launching perf)
    ctl_fd = ack_fd = None
    if '--control' in args:
        spec = args[args.index('--control') + 1]
        if spec.startswith('fifo:'):
            ctl_path, ack_path = spec[len('fifo:'):].split(',')
            ctl_fd = os.open(ctl_path, os.O_RDWR | os.O_NONBLOCK)
            ack_fd = os.open(ack_path, os.O_RDWR | os.O_NONBLOCK)
    if ctl_fd is None:
        time.sleep(30); sys.exit(9)
    enabled = False
    while True:
        r, _, _ = select.select([ctl_fd], [], [], 0.05)
        if r:
            cmd = os.read(ctl_fd, 64).decode().strip()
            if cmd == 'enable':
                enabled = True
                if MODE != 'no_ack':
                    os.write(ack_fd, b'ack\n')
                if MODE == 'exit_midway':
                    time.sleep(0.5); sys.exit(9)
            elif cmd == 'disable':
                enabled = False
                if MODE != 'no_ack':
                    os.write(ack_fd, b'ack\n')
            elif cmd == 'stop':
                if MODE != 'no_ack':
                    os.write(ack_fd, b'ack\n')
                sys.exit(0)
        if enabled:
            with open(data_path, 'ab') as f:
                f.write(b'x' * 512); f.flush()
        time.sleep(0.02)
if args[0] == 'report':
    data_path = args[args.index('-i') + 1]
    symfs = args[args.index('--symfs') + 1] if '--symfs' in args else None
    if MODE == 'zero_samples':
        print("# Samples: 0 of event 'cycles'"); sys.exit(0)
    if MODE == 'report_empty':
        sys.exit(0)
    print("# Samples: 30 of event 'cycles'")
    print("# Event count (approx.): 3000000")
    print("#")
    print("# Overhead  Command  Shared Object  Symbol")
    if MODE == 'short_dso':
        rows = [("libc.so.6", "[.] short_dso_func")]
    else:
        rows = [("/opt/testbed/bin/python", "[.] main"),
                ("/opt/testbed/lib/libpy.so", "[.] 0x0000000000012345")]
    for dso, sym in rows:
        name = sym
        if symfs and '0x' in sym and os.path.isfile(
                os.path.join(symfs, dso.lstrip('/'))):
            name = "[.] resolved_from_container"
        print(f"    50.00%  python  {dso}  {name}")
    if MODE == 'unknown_symbols':
        print("    25.00%  python  [unknown]  [unknown]")
    sys.exit(0)
sys.exit(64)
'''


def make_proc_view(root, entries):
    """Fake host /proc: entries are dicts with pid/nspid list/starttime/ns."""
    for e in entries:
        d = root / str(e['pid']); (d / 'ns').mkdir(parents=True, exist_ok=True)
        link = d / 'ns' / 'pid'
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(f"pid:[{e['ns']}]")
        nspid = 'NSpid:\t' + '\t'.join(str(x) for x in e['nspid'])
        (d / 'status').write_text(f"Name:\tproc\nPid:\t{e['pid']}\n{nspid}\n")
        # /proc/<pid>/stat fields after the last ')': rest[19] = field 22
        # (starttime), same indexing as the production reader
        rest = ['S'] + ['1'] * 18 + [str(e['starttime'])] + ['1'] * 4
        (d / 'stat').write_text(f"proc ({e['pid']}) " + ' '.join(rest) + '\n')


class FixedReader(ScopeReader):
    def __init__(self, cpu_seq):
        self.cpu_seq = list(cpu_seq); self.i = 0
    def read(self, t):
        cpu = self.cpu_seq[min(self.i, len(self.cpu_seq) - 1)]
        self.i += 1
        return CounterSnapshot('x', 'agent_container', t,
                               cpu_usage_usec=cpu, mem_current_bytes=4096,
                               read_status={'cpuacct.usage': 'ok'})


def fake_grade(log_text, record, candidate, *, model_name):
    if ('>>>>> Start Test Output' not in log_text
            or '>>>>> End Test Output' not in log_text):
        return {'status': 'tests_not_run', 'resolved': None,
                'infra_failure': None}
    return {'status': 'ok', 'resolved': 'FAILED' not in log_text,
            'infra_failure': False}


class FakeCPU02Runtime:
    """Duck-typed runtime facade over FakeContainerRuntime pieces the CPU-02
    entry actually uses (start/execute/open_interactive/read_counters/
    container_init_pid/stop/verify_removal/cleanup_pending)."""

    def __init__(self, *, eval_file, proc_root, init_pid, supervisor_mode='real',
                 reader=None, host_target_pid=900007):
        from agent_workload_characterization.runners.container_runtime import (
            FakeContainerRuntime)
        from agent_workload_characterization.collectors.semantic_recorder import FakeClock
        self._rt = FakeContainerRuntime(FakeClock())
        self.eval_file = Path(eval_file)
        self.proc_root = proc_root
        self.init_pid = init_pid
        self.host_target_pid = host_target_pid
        self.supervisor_mode = supervisor_mode
        self.children = []
        self.start_calls = 0
        self.eval_script_commands = []
        self._rt.readers[entry.SCOPE] = reader or FixedReader([100, 100, 200, 250])
        self._binary_payload = bytes(range(256)) * 4 + b'\x00\xff\xfe binary'
        import base64 as _b
        for dso in ('/opt/testbed/bin/python', '/opt/testbed/lib/libpy.so'):
            self._rt.execute_script[
                f'python3 -c "import os,sys;print(\'ok\' if os.path.isfile(sys.argv[1]) else \'no\')" {dso}'
            ] = {'returncode': 0, 'output': 'ok'}
            self._rt.execute_script[
                f'python3 -c "import base64,sys;sys.stdout.write(base64.b64encode(open(sys.argv[1],\'rb\').read()).decode())" {dso}'
            ] = {'returncode': 0,
                 'output': _b.b64encode(self._binary_payload).decode()}
            self._rt.execute_script[
                f'python3 -c "import hashlib,os,sys;d=open(sys.argv[1],\'rb\').read();print(str(len(d))+\' \'+hashlib.sha256(d).hexdigest())" {dso}'
            ] = {'returncode': 0,
                 'output': f'{len(self._binary_payload)} {__import__("hashlib").sha256(self._binary_payload).hexdigest()}'}

    def start(self, spec, timeout_s=60):
        self.start_calls += 1
        handle = self._rt.start(spec, timeout_s)
        self._rt.init_pids[handle.container_id] = self.init_pid
        return handle

    def execute(self, handle, command, timeout_s, **kw):
        if 'cat > /eval.sh' in command:
            self.eval_script_commands.append(command)
        return self._rt.execute(handle, command, timeout_s, **kw)

    def read_counters(self, handle, t):
        return self._rt.read_counters(handle, t)

    def container_init_pid(self, handle, timeout_s=10.0):
        return self._rt.container_init_pid(handle, timeout_s)

    def open_interactive(self, handle, command, timeout_s):
        if self.supervisor_mode == 'no_ready':
            proc = subprocess.Popen(['sleep', '10'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            self.children.append(proc); return proc
        command = command.replace(repr('/eval.sh'), repr(str(self.eval_file)))
        # bash -c (NOT -lc): a login shell would print profile noise into
        # the supervisor's stdout and pollute the ready protocol; the real
        # chain's read_supervisor_ready tolerates noise but the fake must
        # not depend on the host's login configuration either
        # start_new_session mirrors the docker-exec isolation: the supervisor
        # chain lives in its own group so the fake terminate_workload can
        # clear lingering descendants exactly like the real one
        proc = subprocess.Popen(['bash', '-c', command], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                start_new_session=True)
        self.children.append(proc)
        # The fake scene runs the supervisor on the HOST, so it self-reports
        # its real host PID as the "container" identity. Register the fake
        # proc-view entry that the mapping must resolve: host 900007, innermost
        # NSpid = the reported pid, same pidns as the fake init, real starttime.
        try:
            with open(f'/proc/{proc.pid}/stat') as stat_file:
                st = int(stat_file.read().rsplit(')', 1)[1].split()[19])
        except (OSError, IndexError, ValueError):
            st = 222
        make_proc_view(self.proc_root, [
            {'pid': self.host_target_pid,
             'nspid': [self.host_target_pid, proc.pid],
             'starttime': st, 'ns': 4026531234}])
        return proc

    def stop(self, handle, timeout_s=60.0):
        self._rt.stop(handle, timeout_s)

    def verify_removal(self, handle, timeout_s=30.0):
        return self._rt.verify_removal(handle, timeout_s)

    def cleanup_pending(self, timeout_s=10.0):
        return []

    def terminate_workload(self, handle, timeout_s=15.0, step_share_deadline=None):
        # fake equivalent of the real in-container workload stop: kill the
        # WHOLE supervisor session group (the chain runs on the host here),
        # so lingering eval descendants release the pipes
        import signal as _signal
        for proc in self.children:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, _signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    proc.wait(timeout=max(0.5, timeout_s))
                except Exception:
                    pass
        self._rt.terminated.append(handle.container_id)
        return {'confirmed': True, 'container_alive': True,
                'method': 'fake_session_kill'}


def write_eval_script(path, failed=False):
    status = 'FAILED' if failed else 'ok'
    path.write_text('#!/bin/bash\n'
                    'echo ">>>>> Start Test Output"\n'
                    f'echo "test_floatformat ... {status}"\n'
                    'echo ">>>>> End Test Output"\n', encoding='utf-8')


class CPU02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        # fake host /proc: init 900001 (ns A), target 900007 host pid with
        # container pid 7, a docker-exec client lookalike 42 in the HOST ns
        self.proc_root = self.root / 'proc'
        make_proc_view(self.proc_root, [
            {'pid': 900001, 'nspid': [900001, 1], 'starttime': 111, 'ns': 4026531234},
            {'pid': 900007, 'nspid': [900007, 7], 'starttime': 222, 'ns': 4026531234},
            {'pid': 42, 'nspid': [42], 'starttime': 222, 'ns': 4026539999},
        ])
        self.perf = self.root / 'fake_perf'; self.perf.write_text(FAKE_PERF)
        self.perf.chmod(0o755)
        self.paranoid = self.root / 'paranoid'; self.paranoid.write_text('2\n')
        self.eval_file = self.root / 'eval.sh'; write_eval_script(self.eval_file)
        self.meta_path = self.root / 'perf_meta.json'
        cfg = entry.load_config()
        cfg['perf']['binary'] = str(self.perf)
        cfg['perf']['readiness'].update(ack_timeout_s=2)
        cfg['limits'].update(batch_wall_s=20, cleanup_reserve_s=3,
                             prepare_wall_s=10, eval_wall_s=8, operation_s=3,
                             report_threshold_mib=100)
        self.catalog = self.root / 'cpu_02.yaml'
        self.catalog.write_text(yaml.safe_dump(cfg))
        self.namespace = self.root / 'reports/cpu/CPU-02'
        self.patches = mock.patch.multiple(
            entry, PROJECT_ROOT=self.root, CATALOG=self.catalog,
            APPROVAL=self.namespace / 'APPROVAL.json',
            ATTEMPT=self.namespace / 'ATTEMPT_STARTED.json',
            PARANOID_PATH=str(self.paranoid))
        self.patches.start()
        self.runtime = FakeCPU02Runtime(eval_file=self.eval_file,
                                        proc_root=self.proc_root,
                                        init_pid=900001)
    def tearDown(self):
        for proc in self.runtime.children:
            if proc.poll() is None:
                proc.kill(); proc.wait(timeout=1)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
        self.patches.stop(); self.tmp.cleanup()

    def make_runtime(self, **kw):
        kw.setdefault('eval_file', self.eval_file)
        kw.setdefault('proc_root', self.proc_root)
        kw.setdefault('init_pid', 900001)
        return FakeCPU02Runtime(**kw)

    def run_batch(self, mode='normal', name='batch', runtime=None, **kw):
        env = {'FAKE_PERF_MODE': mode, 'FAKE_PERF_META': str(self.meta_path)}
        if kw.pop('env', None) is not None:
            env.update(kw.pop('env'))
        with mock.patch.dict(os.environ, env):
            kw.setdefault('config', entry.load_config())
            kw.setdefault('proc_root', self.proc_root)
            kw.setdefault('grader', fake_grade)
            rt = runtime or self.runtime
            return entry.run_batch(rt, self.namespace / name, **kw)

    # ---- gates ---------------------------------------------------------
    def test_default_plan_no_subprocess_no_write(self):
        before = {p for p in self.root.rglob('*')}
        with mock.patch.object(entry.subprocess, 'Popen',
                               side_effect=AssertionError('NO PROC')), \
             mock.patch.object(entry.subprocess, 'run',
                               side_effect=AssertionError('NO PROC')):
            with context_output():
                self.assertEqual(entry.main([]), 0)
        self.assertEqual({p for p in self.root.rglob('*')}, before)
    def test_single_flag_returns_2(self):
        self.assertEqual(entry.main(['--execute']), 2)
    def test_identity_drift_refused(self):
        self.namespace.mkdir(parents=True, exist_ok=True)
        ident = entry.build_plan()['identity']; ident['collection'] = 'CPU-01'
        entry.APPROVAL.write_text(json.dumps(dict(approved=True,
            approved_by='t', approved_at_utc='x', checklist_identity=ident)))
        with mock.patch.object(entry, 'docker_preflight',
                               side_effect=AssertionError), context_output():
            self.assertEqual(entry.main(['--execute', '--i-approve-the-cpu-02-b']), 3)
        self.assertFalse(entry.ATTEMPT.exists())
    def test_marker_once_refuses_second_attempt(self):
        self.namespace.mkdir(parents=True, exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(approved=True,
            approved_by='t', approved_at_utc='x',
            checklist_identity=entry.build_plan()['identity'])))
        entry.register_attempt(entry.build_plan()['identity'])
        with context_output():
            self.assertEqual(entry.main(['--execute', '--i-approve-the-cpu-02-b']), 3)
    def test_output_guards(self):
        self.namespace.mkdir(parents=True)
        redirect = self.namespace / 'redirect'
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(entry.CPU02Error):
            entry.guarded(redirect / 'batch', new=True)
        with self.assertRaises(entry.CPU02Error):
            entry.guarded(self.root / 'data/raw/x', new=True)

    # ---- mapping -------------------------------------------------------
    def test_map_happy_path_and_rejections(self):
        ok = entry.map_container_pid(7, 222, 900001, proc_root=self.proc_root)
        self.assertEqual(ok['status'], 'ok')
        self.assertEqual(ok['host_pid'], 900007)
        ambiguous_root = self.root / 'proc2'
        make_proc_view(ambiguous_root, [
            {'pid': 900001, 'nspid': [900001, 1], 'starttime': 111, 'ns': 4026531234},
            {'pid': 900007, 'nspid': [900007, 7], 'starttime': 222, 'ns': 4026531234},
            {'pid': 900008, 'nspid': [900008, 7], 'starttime': 222, 'ns': 4026531234},
        ])
        amb = entry.map_container_pid(7, 222, 900001, proc_root=ambiguous_root)
        self.assertEqual(amb['status'], 'map_failed')
        self.assertEqual(amb['reason'], 'ambiguous_matches')
        reuse = entry.map_container_pid(7, 999, 900001, proc_root=self.proc_root)
        self.assertEqual(reuse['reason'], 'no_unique_match')
        # container pid 42 exists only as a HOST-ns client lookalike
        wrong_ns = entry.map_container_pid(42, 222, 900001, proc_root=self.proc_root)
        self.assertEqual(wrong_ns['reason'], 'no_unique_match')
    def test_perf_attaches_to_mapped_host_pid(self):
        result = self.run_batch('normal')
        self.assertEqual(result['status'], 'complete', result['errors'])
        argv = json.loads(self.meta_path.read_text())['argv']
        pid = argv[argv.index('-p') + 1]
        self.assertEqual(pid, '900007')          # the mapped HOST pid
        self.assertNotEqual(pid, '7')            # never the container pid
        self.assertNotEqual(pid, '42')           # never the docker client
        self.assertEqual(result['phases']['supervisor']['mapping']['host_pid'], 900007)

    # ---- barrier -------------------------------------------------------
    def test_full_chain_barrier_and_archive(self):
        t0 = time.monotonic()
        result = self.run_batch('normal')
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['archive_status'], 'complete')
        sup = result['phases']['supervisor']
        self.assertEqual(sup['status'], 'ready')
        self.assertEqual(sup['container_pid'], sup['identity']['pid'])
        perf = result['phases']['perf']
        self.assertEqual(perf['status'], 'ready')
        # the barrier is a real control-protocol ACK, not growth observation
        self.assertTrue(perf['enable_ack']['ack'])
        self.assertTrue(perf['disable_ack']['ack'])
        self.assertIn('stop_cmd:group_stopped', perf['stop_events'])
        self.assertLess(perf['window_open_monotonic_ns'],
                        result['phases']['eval']['release_monotonic_ns'])
        self.assertGreater(perf['window_close_monotonic_ns'],
                           result['phases']['eval']['eval_end_monotonic_ns'])
        ev = result['phases']['eval']
        self.assertEqual(ev['status'], 'executed')
        self.assertEqual(ev['eval_rc'], 0)
        grade = result['phases']['grade']
        self.assertEqual(grade['status'], 'ok')
        self.assertTrue(grade['resolved'])
        rep = result['phases']['report']
        self.assertEqual(rep['status'], 'parsed_with_symfs')
        sym_files = result['phases']['symbols']['files']
        self.assertIn('/opt/testbed/bin/python', sym_files)
        bare = rep['parsed']
        symfs = rep['symfs_parsed']
        self.assertTrue(any('0x' in r['symbol'] for r in bare['rows']))
        self.assertTrue(any('resolved_from_container' in r['symbol']
                            for r in symfs['rows']))
        resource = result['phases']['resource']
        self.assertIsNotNone(resource['boundary_start'])
        self.assertIsNotNone(resource['boundary_end'])
        manifest = json.loads((self.namespace / 'batch/manifest.json').read_text())
        for name_, value in manifest['outputs'].items():
            self.assertEqual(entry.sha(self.namespace / 'batch' / name_),
                             value['sha256'])
        self.assertEqual(manifest['inputs']['record']['sha256'],
                         '762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a')
        self.assertEqual(result['cleanup']['container'], 'removed')
        self.assertEqual(result['cleanup']['supervisor'], 'reaped')
    def test_no_release_without_control_ack(self):
        # review repro: perf.data growth may be metadata; the barrier must be
        # the documented enable ACK. Without it the eval must NOT start.
        result = self.run_batch('no_ack')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('eval', result['phases'])  # eval never started
        self.assertFalse((self.namespace / 'batch/eval_output.txt').exists())
        self.assertFalse(result['phases']['perf']['enable_ack']['ack'])
        self.assertEqual(result['cleanup']['container'], 'removed')
    def test_bare_report_isolated_from_host_symbols(self):
        # review repro: the first bare report could silently use HOST
        # symbols — it must run against an empty --symfs root instead
        result = self.run_batch('normal')
        rep = result['phases']['report']
        self.assertEqual(rep['status'], 'parsed_with_symfs')
        self.assertIn('empty_symfs', ' '.join(rep.get('argv') or []))
        self.assertIn('host symbols isolated', rep['bare_pass_note'])
        self.assertTrue((self.namespace / 'batch' / 'empty_symfs').is_dir())

    # ---- execution / grading -------------------------------------------
    def test_resolved_false_still_complete_and_infra_distinct(self):
        write_eval_script(self.eval_file, failed=True)
        result = self.run_batch('normal')
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(result['phases']['grade']['resolved'])
        result = self.run_batch('normal', name='infra',
                                grader=lambda *a, **k: (_ for _ in ()).throw(
                                    OSError('boom')))
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['grade']['status'], 'infra_failure')
    def test_tests_not_run_is_not_validation_success(self):
        # review repro: tests_not_run (official semantics: suite never ran)
        # must NOT count as a validation success
        self.eval_file.write_text('#!/bin/bash\necho nothing\n')
        result = self.run_batch('normal')
        self.assertEqual(result['phases']['grade']['status'], 'tests_not_run')
        self.assertIsNone(result['phases']['grade']['resolved'])
        self.assertEqual(result['status'], 'FAIL')
    def test_grade_infra_failure_flag_fails(self):
        # review repro: the official report's infra_failure flag must be
        # consumed, not only exceptions from the grader
        result = self.run_batch('normal', grader=lambda *a, **k: {
            'status': 'ok', 'resolved': None, 'infra_failure': True})
        self.assertEqual(result['phases']['grade']['infra_failure'], True)
        self.assertEqual(result['status'], 'FAIL')

    # ---- measurement / symbols -----------------------------------------
    def test_cgroup_boundary_missing_and_reset(self):
        rt = self.make_runtime(reader=FixedReader([None, 100, 100]))
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['eval']['status'], 'cgroup_boundary_missing')
        rt = self.make_runtime(reader=FixedReader([300, 100, 50]))
        result = self.run_batch('normal', name='reset', runtime=rt)
        self.assertEqual(result['phases']['eval']['status'], 'cgroup_counter_reset')
    def test_symbol_copy_is_binary_safe(self):
        # review repro: a text decode/re-encode round trip corrupts ELF
        # data. The copy path must preserve arbitrary bytes exactly.
        result = self.run_batch('normal')
        symbols = result['phases']['symbols']['files']
        self.assertEqual(symbols['/opt/testbed/bin/python']['bytes'],
                         len(self.runtime._binary_payload))
        extracted = (self.namespace / 'batch' /
                     'symbols/opt/testbed/bin/python').read_bytes()
        self.assertEqual(extracted, self.runtime._binary_payload)

    def test_truncated_symbol_transport_is_unresolved(self):
        rt = self.make_runtime()
        original = rt.execute
        def truncated(handle, command, timeout_s, **kw):
            result = original(handle, command, timeout_s, **kw)
            if 'base64.b64encode' in command:
                result['output_truncated'] = True
            return result
        rt.execute = truncated
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['phases']['symbols']['files'], {})
        self.assertTrue(all(x['reason'] == 'container_read_failed'
                            for x in result['phases']['symbols']['unresolved_dsos']))
    def test_short_dso_not_substituted(self):
        # review repro: report DSOs are often short names; only absolute
        # paths VERIFIED inside this container may be copied — a short name
        # must stay unresolved, never guessed or host-substituted
        result = self.run_batch('short_dso')
        self.assertEqual(result['status'], 'complete')
        symbols = result['phases']['symbols']
        self.assertEqual(symbols['files'], {})
        self.assertEqual(symbols['unresolved_dsos'],
                         [{'dso': 'libc.so.6', 'reason': 'not_absolute_path'}])
    def test_zero_samples_reported_honestly(self):
        result = self.run_batch('zero_samples')
        rep = result['phases']['report']
        self.assertTrue(rep['parsed']['zero_samples'])
        self.assertEqual(rep['parsed']['evidence_status'], 'header_zero')
        self.assertEqual(result['status'], 'complete')
    def test_unknown_symbols_kept(self):
        result = self.run_batch('unknown_symbols')
        rep = result['phases']['report']
        self.assertEqual(rep['parsed']['unknown_symbol_rows'], 1)
    def test_container_binary_unreadable_keeps_bare_addresses(self):
        # review repro: a failed container read must leave symbols
        # unavailable — the host never substitutes a same-named library
        rt = self.make_runtime()
        for dso in ('/opt/testbed/bin/python', '/opt/testbed/lib/libpy.so'):
            rt._rt.execute_script[
                f'python3 -c "import os,sys;print(\'ok\' if os.path.isfile(sys.argv[1]) else \'no\')" {dso}'
            ] = {'returncode': 0, 'output': 'no'}
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['status'], 'complete')
        symbols = result['phases']['symbols']
        self.assertEqual(symbols['status'], 'no_container_dsos')
        self.assertEqual(symbols['files'], {})
        reasons = {u['reason'] for u in symbols['unresolved_dsos']}
        self.assertEqual(reasons, {'not_verified_in_container'})
        symfs_rows = result['phases']['report']['symfs_parsed']['rows']
        self.assertTrue(all('0x' in r['symbol'] or r['symbol'] == '[.] main'
                            for r in symfs_rows))
        self.assertFalse((self.namespace / 'batch/symbols').exists())
    def test_report_empty_output_is_not_parsed(self):
        # review repro: rc=0 with EMPTY report output returned complete
        result = self.run_batch('report_empty')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['report']['status'], 'empty_output')

    # ---- teardown -------------------------------------------------------
    def test_container_removal_check_failed_fails(self):
        # review repro: verify_removal returning check_failed still yielded
        # complete — the final state must consume the cleanup result
        rt = self.make_runtime()
        rt._rt.next_verify_result = 'check_failed'
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['cleanup']['container'], 'check_failed')
    def test_pending_cleanup_unconfirmed_fails(self):
        rt = self.make_runtime()
        rt.cleanup_pending = lambda timeout_s=10: [{'name': 'cpu02-x', 'removed': False}]
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['cleanup']['pending'],
                         [{'name': 'cpu02-x', 'removed': False}])
    def test_eval_log_tail_not_lost(self):
        # review repro: writing the log before joining the reader could lose
        # tail lines — assemble only after a bounded drain
        marker = 'LAST_LINE_OF_EVAL'
        self.eval_file.write_text('#!/bin/bash\n'
                                  'echo ">>>>> Start Test Output"\n'
                                  'for i in $(seq 1 50); do echo "line $i"; done\n'
                                  f'echo "test ... ok"\n'
                                  f'echo "{marker}"\n'
                                  'echo ">>>>> End Test Output"\n')
        result = self.run_batch('normal')
        self.assertEqual(result['status'], 'complete')
        log = (self.namespace / 'batch/eval_output.txt').read_text()
        self.assertIn(marker, log)
        self.assertIn('>>>>> End Test Output', log)
    def test_local_docker_env_fixed_for_whole_execution(self):
        # review repro: preflight REPORTED a fixed endpoint but the calls
        # never set it — the whole execution must run under one pinned
        # local environment, and the outer env is restored afterwards
        self.namespace.mkdir(parents=True, exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(approved=True,
            approved_by='t', approved_at_utc='x',
            checklist_identity=entry.build_plan()['identity'])))
        seen = {}
        def fake_docker_preflight(*, deadline):
            seen['host'] = os.environ.get('DOCKER_HOST')
            seen['context'] = os.environ.get('DOCKER_CONTEXT')
            return {'status': 'NOT_READY'}  # stop before any runtime use
        with mock.patch.dict(os.environ, {'DOCKER_HOST': 'tcp://remote:1',
                                          'DOCKER_CONTEXT': 'evil'}):
            with mock.patch.object(entry, 'preflight_checks',
                                   return_value={'status': 'READY'}), \
                 mock.patch.object(entry, 'docker_preflight',
                                   side_effect=fake_docker_preflight), \
                 mock.patch('sys.stdout', new_callable=io.StringIO) as out:
                rc = entry.main(['--execute', '--i-approve-the-cpu-02-b'])
            # inside the outer patch scope: local_docker_environment already
            # RESTORED the pinned outer values after its with-block ended
            self.assertEqual(os.environ.get('DOCKER_HOST'), 'tcp://remote:1')
            self.assertEqual(os.environ.get('DOCKER_CONTEXT'), 'evil')
        self.assertEqual(seen.get('host'), 'unix:///var/run/docker.sock')
        self.assertIsNone(seen.get('context'))
        self.assertEqual(rc, 4)  # stopped at preflight, nothing executed
    def test_supervisor_no_ready(self):
        rt = self.make_runtime(supervisor_mode='no_ready')
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['supervisor']['status'], 'no_ready')
        self.assertEqual(result['cleanup']['container'], 'removed')
    def test_perf_exits_early_during_eval(self):
        # slow eval so the sampler outlives it and dies mid-window
        self.eval_file.write_text('#!/bin/bash\nsleep 0.6\n'
                                  'echo ">>>>> Start Test Output"\n'
                                  'echo "test ... ok"\n'
                                  'echo ">>>>> End Test Output"\n')
        result = self.run_batch('exit_midway')
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['phases']['perf']['exited_before_stop'])
        self.assertEqual(result['cleanup']['container'], 'removed')
    def test_perf_exits_before_control(self):
        result = self.run_batch('exit_early')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['phases']['perf']['detail'],
                         'perf_exited_before_control')
        self.assertNotIn('eval', result['phases'])
    def test_eval_timeout_cleans_everything(self):
        self.eval_file.write_text('#!/bin/bash\nsleep 30\n')
        cfg = entry.load_config(); cfg['limits']['eval_wall_s'] = 1
        t0 = time.monotonic()
        result = self.run_batch('normal', config=cfg)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['eval']['status'], 'timeout')
        self.assertEqual(result['cleanup']['container'], 'removed')
        perf_events = result['phases']['perf']['stop_events']
        self.assertTrue(any(e.endswith(':group_stopped') for e in perf_events))
    def test_threshold_abort_leaves_minimal_evidence(self):
        cfg = entry.load_config(); cfg['limits']['report_threshold_mib'] = .00005
        result = self.run_batch('normal', config=cfg)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result.get('report_threshold_exceeded'))
        self.assertEqual(result['cleanup']['container'], 'removed')
    def test_archive_failure_writes_marker(self):
        original = entry.write_json
        def write(path, payload):
            if Path(path).name == 'manifest.json':
                raise OSError('fake archive failure')
            return original(path, payload)
        with mock.patch.object(entry, 'write_json', side_effect=write):
            result = self.run_batch('normal')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['archive_status'], 'failed')
        summary = json.loads((self.namespace / 'batch/summary.json').read_text())
        self.assertEqual(summary['status'], 'FAIL')
        self.assertEqual(summary['archive_status'], 'failed')
        self.assertTrue((self.namespace / 'batch/archive_failure.json').exists())

    def test_symbol_source_integrity_mismatch_is_unresolved(self):
        rt = self.make_runtime()
        original = rt.execute
        def mismatched(handle, command, timeout_s, **kw):
            result = original(handle, command, timeout_s, **kw)
            if 'hashlib.sha256' in command:
                result['output'] = '1034 ' + '0' * 64
            return result
        rt.execute = mismatched
        result = self.run_batch('normal', runtime=rt)
        self.assertEqual(result['phases']['symbols']['files'], {})
        self.assertTrue(any(x['reason'] == 'source_integrity_mismatch'
                            for x in result['phases']['symbols']['unresolved_dsos']))
    def test_budget_exhausted_never_starts(self):
        result = self.run_batch('normal', deadline=time.monotonic() - 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['budget_overrun'])
        self.assertEqual(result['phases']['prepare']['status'], 'pending')

    def test_verified_generated_eval_script_is_written(self):
        result = self.run_batch('normal')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(self.runtime.eval_script_commands), 1)
        script_command = self.runtime.eval_script_commands[0]
        self.assertIn('SWEBENCH_TEST_EXIT_CODE=$?', script_command)
        self.assertIn('>>>>> Test Exit Code: $SWEBENCH_TEST_EXIT_CODE',
                      script_command)
        self.assertEqual(result['phases']['prepare']['eval_script']['generated_sha256'],
                         entry.EVAL_SCRIPT_GENERATED_SHA256)

    def test_generated_eval_script_drift_rejects_before_start(self):
        rt = self.make_runtime()
        with mock.patch.object(entry, '_load_generated_eval_script',
                               side_effect=entry.CPU02Error(
                                   'eval_script_generated_hash_drift')):
            result = self.run_batch('normal', runtime=rt)
        self.assertEqual(rt.start_calls, 0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['prepare']['status'], 'pending')

    def test_evaluator_unavailable_rejects_before_start(self):
        rt = self.make_runtime()
        missing = self.root / 'missing-evaluator-python'
        with mock.patch.object(entry, 'VENV_PYTHON', missing):
            result = self.run_batch('normal', runtime=rt)
        self.assertEqual(rt.start_calls, 0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('CPU02Error', result['errors'])


def context_output():
    return mock.patch('sys.stdout', new_callable=io.StringIO)


if __name__ == '__main__':
    unittest.main()
