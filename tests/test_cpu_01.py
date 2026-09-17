"""CPU-01 bounded OFFLINE tests: real entry, fake perf executable, short
owned target process. No real perf/PMU probe, no Docker, no network, no
production config. Subprocess walls stay seconds; every child is killed and
reaped in tearDown.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import yaml

from agent_workload_characterization.runners import cpu_01_entry as entry

FAKE_PERF = r'''#!/usr/bin/python3.11
import json, os, signal, subprocess, sys, time

MODE = os.environ.get('FAKE_PERF_MODE', 'normal')
args = sys.argv[1:]

def normal_csv():
    return "\n".join([
        "150.123;msec;task-clock;150123000;100.00;;",
        "1234;;context-switches;150123000;100.00;;",
        "2;;cpu-migrations;150123000;100.00;;",
        "400;;page-faults;150123000;100.00;;",
        "2000000;;cycles;150123000;100.00;;",
        "4000000;;instructions;150123000;100.00;;",
        "500000;;branches;150123000;100.00;;",
        "10000;;branch-misses;150123000;100.00;;",
        "60000;;cache-references;150123000;100.00;;",
        "3000;;cache-misses;150123000;100.00;;",
    ]) + "\n"

def csv_for_mode():
    if MODE == 'mixed':
        return "\n".join([
            "150.123;msec;task-clock;150123000;50.00;;",
            "1234;;context-switches;150123000;100.00;;",
            "2;;cpu-migrations;150123000;100.00;;",
            "400;;page-faults;150123000;100.00;;",
            "<not supported>;;cycles;150123000;100.00;;",
            "<not counted>;;instructions;150123000;100.00;;",
            "500000;;branches;150123000;100.00;;",
            "10000;;branch-misses;150123000;100.00;;",
            "60000;;cache-references;150123000;100.00;;",
            ";;cache-misses;150123000;100.00;;",
        ]) + "\n"
    if MODE == 'zero_cycles':
        return normal_csv().replace("2000000;;cycles", "0;;cycles")
    if MODE == 'metric_tail':
        base = [l for l in normal_csv().splitlines()
                if not l.startswith("4000000;;instructions")]
        base.append("4000000;;instructions;150123000;100.00;2.00;insn per cycle")
        return "\n".join(base) + "\n"
    return normal_csv()

if args[0] == 'stat':
    csv_path = args[args.index('-o') + 1]
    targv = args[args.index('--') + 1:]
    if MODE == 'hang':
        subprocess.Popen(targv)
        time.sleep(60)
        sys.exit(9)
    if MODE == 'grow':
        p = subprocess.Popen(targv)
        end = time.time() + 30
        with open(csv_path, 'w') as f:
            while time.time() < end:
                f.write('x' * 200 + '\n'); f.flush()
                time.sleep(0.05)
        p.wait()
        sys.exit(0)
    if MODE == 'term_immune':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        p = subprocess.Popen(targv); p.wait()
        open(csv_path, 'w').write(normal_csv())
        time.sleep(30)
        sys.exit(0)
    if MODE == 'leak_grandchild':
        subprocess.Popen(['sleep', '30'])  # holds the stdout pipe open
        p = subprocess.Popen(targv); p.wait()
        open(csv_path, 'w').write(normal_csv())
        sys.exit(0)
    if MODE == 'empty_csv':
        p = subprocess.Popen(targv); p.wait()
        open(csv_path, 'w').close()
        sys.exit(0)
    if MODE == 'metric_only':
        p = subprocess.Popen(targv); p.wait()
        # no counter lines at all: metric-only output must not count as stat
        open(csv_path, 'w').write(";;;;2.00;insn per cycle\n")
        sys.exit(0)
    if MODE == 'short_over':
        # finishes "successfully" but outlives a 0.01 s phase budget
        time.sleep(0.066)
        open(csv_path, 'w').write(normal_csv())
        sys.exit(0)
    if MODE == 'daemon_child':
        # background child with CLOSED stdio: perf itself exits normally,
        # the process group stays alive (review repro)
        subprocess.Popen(['sleep', '30'], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        p = subprocess.Popen(targv); p.wait()
        open(csv_path, 'w').write(normal_csv())
        sys.exit(0)
    if MODE == 'stat_rc7':
        p = subprocess.Popen(targv); p.wait()
        open(csv_path, 'w').write(normal_csv())
        sys.exit(7)
    if MODE == 'fake_pid':
        p = subprocess.Popen(targv); p.wait()
        fake = int(os.environ['FAKE_FAKE_PID'])
        st = int(open('/proc/%d/stat' % fake).read().rsplit(')', 1)[1].split()[19])
        print(json.dumps({"event": "target_started", "pid": fake,
                          "starttime_ticks": st, "iterations": 1}), flush=True)
        print(json.dumps({"event": "target_done", "pid": fake,
                          "checksum": "fake", "cpu_seconds": 0.01}), flush=True)
        open(csv_path, 'w').write(normal_csv())
        sys.exit(0)
    p = subprocess.Popen(targv)
    rc = p.wait()
    if MODE == 'big_output':
        sys.stdout.write('x' * (3 * 1024 * 1024)); sys.stdout.flush()
    if MODE == 'no_csv':
        sys.exit(rc)
    if MODE == 'bad_checksum':
        print(json.dumps({"event": "target_done", "pid": p.pid,
                          "checksum": "0" * 64, "cpu_seconds": 0.01}), flush=True)
    elif MODE == 'bad_iterations':
        print(json.dumps({"event": "target_started", "pid": p.pid,
                          "starttime_ticks": 123, "iterations": 1}), flush=True)
    open(csv_path, 'w').write(csv_for_mode())
    sys.exit(rc)
if args[0] == 'record':
    data_path = args[args.index('-o') + 1]
    targv = args[args.index('--') + 1:]
    if MODE == 'record_unavailable':
        sys.stderr.write("Error: access to performance events is denied\n")
        sys.exit(1)
    p = subprocess.Popen(targv)
    rc = p.wait()
    if MODE == 'record_no_output':
        sys.exit(0)
    samples = 0 if MODE == 'record_zero_samples' else 20
    open(data_path, 'w').write(json.dumps({"samples": samples, "event": "cycles"}))
    sys.exit(rc)
if args[0] == 'report':
    data_path = args[args.index('-i') + 1]
    d = json.loads(open(data_path).read())
    n = d.get('samples', 0)
    if MODE == 'report_hang':
        time.sleep(60)
    if MODE == 'report_empty':
        sys.exit(0)
    if MODE == 'report_rc7':
        sys.exit(7)
    if MODE == 'report_no_rows':
        print("#")
        print("# nothing reported")
        sys.exit(0)
    if MODE != 'report_no_header':
        print("# Samples: %d of event 'cycles'" % n)
        print("# Event count (approx.): %d" % (n * 100000))
    print("#")
    print("# Overhead  Command  Shared Object  Symbol")
    print("# ........  .......  .............  ......")
    if n:
        print("    62.50%  python3.11  python3.11  [.] main")
        print("    25.00%  python3.11  python3.11  [.] <module>")
        if MODE == 'report_unknown':
            print("    12.50%  python3.11  [unknown]  [unknown]")
        else:
            print("    12.50%  python3.11  libc.so.6  [.] memset@plt")
    if MODE == 'report_broken':
        # a data-looking line the parser cannot classify (review repro)
        print("    25.00%  broken")
    sys.exit(0)
sys.exit(64)
'''


class CPU01Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.perf=self.root/'fake_perf';self.perf.write_text(FAKE_PERF)
        self.perf.chmod(0o755)
        self.paranoid=self.root/'paranoid';self.paranoid.write_text('2\n')
        cfg=entry.load_config()
        cfg['workload'].update(work_iterations=2000000)
        cfg['perf']['binary']=str(self.perf)
        cfg['limits'].update(batch_wall_s=10,cleanup_reserve_s=1,operation_s=3,
                             target_wall_s=4,report_threshold_mib=20)
        self.catalog=self.root/'cpu_01.yaml'
        self.catalog.write_text(yaml.safe_dump(cfg))
        self.namespace=self.root/'reports/cpu/CPU-01'
        self.patches=mock.patch.multiple(entry,PROJECT_ROOT=self.root,CATALOG=self.catalog,
            APPROVAL=self.namespace/'APPROVAL.json',ATTEMPT=self.namespace/'ATTEMPT_STARTED.json',
            PARANOID_PATH=str(self.paranoid))
        self.patches.start()
        self.extra_children=[]
    def tearDown(self):
        for proc in self.extra_children:
            if proc.poll() is None:proc.kill();proc.wait(timeout=1)
        self.patches.stop();self.tmp.cleanup()
    def approve(self):
        self.namespace.mkdir(parents=True,exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(approved=True,approved_by='synthetic-test',
            approved_at_utc='fixture',checklist_identity=entry.build_plan()['identity'])))
    def run_batch(self,mode='normal',name='batch',**kw):
        with mock.patch.dict(os.environ,{'FAKE_PERF_MODE':mode}):
            kw.setdefault('config',entry.load_config())
            return entry.run_batch(self.namespace/name,**kw)
    def run_main(self,mode='normal'):
        with mock.patch.dict(os.environ,{'FAKE_PERF_MODE':mode}),context_output():
            return entry.main(['--execute','--i-approve-the-cpu-01-b'])

    # ---- gates ---------------------------------------------------------
    def test_default_plan_no_subprocess_no_write(self):
        before={p for p in self.root.rglob('*')}
        with mock.patch.object(entry.subprocess,'Popen',side_effect=AssertionError('NO PROC')), \
             mock.patch.object(entry.subprocess,'run',side_effect=AssertionError('NO PROC')):
            with context_output():self.assertEqual(entry.main([]),0)
        self.assertEqual({p for p in self.root.rglob('*')},before)
    def test_single_flag_returns_2(self):
        self.assertEqual(entry.main(['--execute']),2)
        self.assertEqual(entry.main(['--i-approve-the-cpu-01-b']),2)
    def test_no_approval_returns_3(self):
        self.assertEqual(self.run_main(),3)
        self.assertFalse(entry.ATTEMPT.exists())
    def test_identity_drift_and_old_collection_refused(self):
        self.approve()
        for mutate in (lambda r:r['checklist_identity'].update(collection='G1-02'),
                       lambda r:r['checklist_identity'].update(catalog_sha256='0'*64)):
            record=json.loads(entry.APPROVAL.read_text());mutate(record)
            entry.APPROVAL.write_text(json.dumps(record))
            self.assertEqual(self.run_main(),3)
        self.assertFalse(entry.ATTEMPT.exists())
    def test_marker_exists_refuses_second_attempt(self):
        self.approve();entry.register_attempt(entry.build_plan()['identity'])
        self.assertEqual(self.run_main(),3)
    def test_symlink_approval_refused(self):
        self.approve();target=self.root/'real.json';target.write_text('{}')
        entry.APPROVAL.unlink();entry.APPROVAL.symlink_to(target)
        with self.assertRaises(entry.CPU01Error):entry.verify_approval(entry.APPROVAL)
    def test_paths_symlink_and_protected_rejected(self):
        self.namespace.mkdir(parents=True);redirect=self.namespace/'redirect'
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(entry.CPU01Error):entry.guarded(redirect/'batch',new=True)
        with self.assertRaises(entry.CPU01Error):entry.guarded(self.root/'data/raw/x',new=True)

    # ---- stat ----------------------------------------------------------
    def test_stat_complete_chain_via_main(self):
        self.approve()
        self.assertEqual(self.run_main(),0)
        preflight=json.loads((self.namespace/'PREFLIGHT.json').read_text())
        self.assertEqual(preflight['status'],'READY')
        self.assertEqual(preflight['perf_event_paranoid']['value'],2)
        batch=next(self.namespace.glob('CPU-01-*'))
        summary=json.loads((batch/'summary.json').read_text())
        self.assertEqual(summary['status'],'complete')
        stat=summary['phases']['stat']
        self.assertEqual(stat['status'],'parsed')
        self.assertEqual(stat['parsed']['n_events'],10)
        self.assertEqual(stat['target_check']['status'],'ok')
        self.assertEqual(stat['n_supported'],10)
        self.assertAlmostEqual(stat['ipc']['ipc'],2.0)
        self.assertTrue(stat['target_completed'])
        self.assertEqual(summary['cleanup']['after_stat']['status'],'exited')
        record=summary['phases']['record']
        self.assertEqual(record['status'],'data_present')
        self.assertEqual(record['target_check']['status'],'ok')
        self.assertEqual(summary['phases']['report']['status'],'parsed')
        self.assertEqual(summary['phases']['report']['parsed']['n_rows'],3)
        self.assertEqual(summary['phases']['report']['parsed']['total_samples'],20)
        self.assertEqual(summary['phases']['report']['parsed']['event_count_approx'],2000000)
        manifest=json.loads((batch/'manifest.json').read_text())
        for name,value in manifest['outputs'].items():
            self.assertEqual(entry.sha(batch/name),value['sha256'])
        self.assertIn('catalog',manifest['inputs'])
        self.assertEqual(manifest['inputs']['perf_binary'],
                         entry.sha(self.perf))
        marker=json.loads(entry.ATTEMPT.read_text())
        self.assertEqual(marker['status'],'completed')
    def test_stat_mixed_support_states(self):
        result=self.run_batch('mixed')
        self.assertEqual(result['status'],'complete')
        stat=result['phases']['stat'];by={r['event']:r for r in stat['parsed']['events']}
        self.assertEqual(by['cycles']['status'],'not_supported')
        self.assertEqual(by['instructions']['status'],'not_counted')
        self.assertEqual(by['branches']['status'],'ok')
        self.assertEqual(by['cache-misses']['status'],'missing')
        self.assertEqual(by['cache-misses']['value'],None)
        self.assertEqual(by['task-clock']['percent_running'],50.0)
        self.assertIsNone(stat['ipc']['ipc'])
        self.assertEqual(stat['ipc']['reason'],'cycles_or_instructions_not_valid')
        self.assertGreaterEqual(stat['n_not_supported'],1)
    def test_stat_zero_cycles_no_ipc(self):
        result=self.run_batch('zero_cycles')
        self.assertEqual(result['phases']['stat']['ipc']['reason'],'cycles_not_positive')
        cycles=[r for r in result['phases']['stat']['parsed']['events']
                if r['event']=='cycles'][0]
        self.assertEqual(cycles['status'],'zero')
        self.assertEqual(cycles['value'],0.0)
    def test_stat_metric_tail_not_second_time_column(self):
        # Review repro: "4000000;;instructions;150123000;100.00;2.00;insn per cycle"
        # must NOT be read as running=100ns / 2% — per perf-stat(1) only ONE
        # time column exists; the tail is optional metric value/unit.
        result=self.run_batch('metric_tail')
        self.assertEqual(result['status'],'complete')
        ins=[r for r in result['phases']['stat']['parsed']['events']
             if r['event']=='instructions'][0]
        self.assertEqual(ins['run_time_ns'],150123000.0)
        self.assertEqual(ins['percent_running'],100.0)
        self.assertIsNone(ins['time_enabled_ns'])
        self.assertIsNone(ins['time_running_ns'])
        self.assertEqual(ins['time_fields_interpretation'],'single_run_time_percent')
        self.assertEqual(ins['extra_fields'],['2.00','insn per cycle'])
        self.assertEqual(ins['value'],4000000.0)
    def test_stat_csv_missing_rc0_fails(self):
        result=self.run_batch('no_csv')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['stat']['status'],'output_missing')
        self.assertTrue((self.namespace/'batch/summary.json').exists())
    def test_parse_short_line_error(self):
        parsed=entry.perf_adapter.parse_stat_csv("1234;;cycles\n\n# comment\n")
        self.assertEqual(len(parsed['events']),1)
        self.assertEqual(parsed['events'][0]['status'],'parse_error')

    # ---- review group 1: failures must not be complete ------------------
    def test_stat_empty_output_not_complete(self):
        result=self.run_batch('empty_csv')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['stat']['status'],'no_counter_lines')
        self.assertEqual(result['phases']['stat']['parsed']['n_counters'],0)
    def test_stat_metric_only_not_complete(self):
        # review repro: a stat file with ONLY metric-only lines is not a
        # valid counter set, yet previously judged complete
        result=self.run_batch('metric_only')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['stat']['status'],'no_counter_lines')
        parsed=result['phases']['stat']['parsed']
        self.assertEqual(parsed['n_metric_only'],1)
        self.assertEqual(parsed['n_counters'],0)
    def test_report_unparsed_line_not_complete(self):
        # review repro: a '25.00% broken' line must affect validity, not
        # silently pass as a complete profile
        result=self.run_batch('report_broken')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['report']['status'],'parsed_with_errors')
        self.assertTrue(result['phases']['report']['parsed']['unparsed_percent_lines'])
        self.assertEqual(result['phases']['report']['parsed']['n_rows'],3)
    def test_stat_nonzero_rc_with_output_not_complete(self):
        result=self.run_batch('stat_rc7')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['stat']['status'],'nonzero_rc_with_output')
        self.assertEqual(result['phases']['stat']['returncode'],7)
    def test_report_empty_output_not_complete(self):
        result=self.run_batch('report_empty')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['report']['status'],'empty_output')
    def test_report_nonzero_rc_not_complete(self):
        result=self.run_batch('report_rc7')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['report']['status'],'nonzero_rc')
        self.assertEqual(result['phases']['report']['returncode'],7)
    def test_report_unknown_output_not_complete(self):
        # no header and no rows is UNKNOWN, not a genuine zero-sample profile
        result=self.run_batch('report_no_rows')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['report']['status'],'unknown_output')
        self.assertFalse(result['phases']['report']['parsed']['zero_samples'])
    def test_target_identity_mismatch_fails(self):
        for mode,problem in (('bad_checksum','checksum_mismatch'),
                             ('bad_iterations','iterations_mismatch')):
            with self.subTest(mode=mode):
                result=self.run_batch(mode,name='batch-'+mode)
                self.assertEqual(result['status'],'FAIL')
                self.assertEqual(result['phases']['stat']['status'],'target_identity_mismatch')
                self.assertIn(problem,result['phases']['stat']['target_check']['problems'])
    def test_stat_parse_error_lines_not_complete(self):
        # a CSV with an unparseable counter line is a parsing failure, not success
        result=self.run_batch('normal')
        raw=(self.namespace/'batch/stat.csv')
        csv_lines=raw.read_text().splitlines()
        csv_lines.append("999;;cycles")
        raw.write_text("\n".join(csv_lines)+"\n")
        parsed=entry.perf_adapter.parse_stat_csv(raw.read_text())
        self.assertGreater(parsed['n_parse_errors'],0)
        self.assertEqual(parsed['events'][-1]['status'],'parse_error')

    # ---- record / report -----------------------------------------------
    def test_record_no_output_rc0_not_success(self):
        result=self.run_batch('record_no_output')
        self.assertEqual(result['phases']['record']['status'],'rc0_output_missing')
        self.assertEqual(result['status'],'FAIL')
    def test_record_unavailable_archives_unavailable(self):
        result=self.run_batch('record_unavailable')
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['phases']['record']['status'],'unavailable')
        self.assertNotIn('report',result['phases'])  # stopped after refusal
        self.assertEqual(result['archive_status'],'complete')
    def test_report_unknown_symbols(self):
        result=self.run_batch('report_unknown')
        report=result['phases']['report']
        self.assertEqual(report['status'],'parsed')
        self.assertEqual(report['parsed']['unknown_symbol_rows'],1)
        self.assertEqual(report['parsed']['total_samples'],20)
    def test_report_zero_samples(self):
        result=self.run_batch('record_zero_samples')
        report=result['phases']['report']
        self.assertTrue(report['parsed']['zero_samples'])
        self.assertEqual(report['parsed']['n_rows'],0)
        self.assertEqual(result['status'],'complete')
    def test_report_no_header_denominator_null(self):
        result=self.run_batch('report_no_header')
        report=result['phases']['report']
        self.assertEqual(report['status'],'parsed')
        self.assertIsNone(report['parsed']['total_samples'])
        self.assertIn('period-weighted',report['parsed']['denominator_note'])
        self.assertEqual(report['parsed']['evidence_status'],'no_header_rows')
        self.assertFalse(report['parsed']['zero_samples'])

    # ---- processes ------------------------------------------------------
    def test_phase_timeout_kills_group_and_reaps(self):
        t=time.monotonic()
        result=self.run_batch('hang',deadline=t+1.2)
        self.assertEqual(result['status'],'FAIL')
        self.assertLess(time.monotonic()-t,4)
        stat=result['phases']['stat']
        self.assertTrue(stat['timed_out'])
        self.assertTrue(stat['target']['target_started'])  # target really started
        self.assertIn('stopped',str(stat['stop_events']))
        self.assertIn(result['cleanup']['after_stat']['status'],
                      ('exited','exited_zombie_pending_reap'))
        self.assertFalse(Path(f"/proc/{stat['perf_pid']}").exists())
    def test_phase_budget_is_not_summed(self):
        # review repro: target budget 0.05 s must abort in ~0.05 s, not after
        # target_wall + operation had been summed
        cfg=entry.load_config();cfg['limits']['target_wall_s']=0.05
        t=time.monotonic()
        result=self.run_batch('hang',config=cfg,deadline=t+10)
        self.assertEqual(result['status'],'FAIL')
        stat=result['phases']['stat']
        self.assertTrue(stat['timed_out'])
        self.assertLess(stat['phase_wall_s'],1.5)
        self.assertFalse(result['budget_overrun'])
    def test_short_process_cannot_evade_budget(self):
        # review repro: 0.01 s budget, ~0.066 s "successful" runtime — the
        # phase must still be judged timed out, and cleanup/join recompute
        # the remaining budget each time
        cfg=entry.load_config();cfg['limits']['target_wall_s']=0.01
        t=time.monotonic()
        result=self.run_batch('short_over',config=cfg)
        self.assertEqual(result['status'],'FAIL')
        stat=result['phases']['stat']
        self.assertTrue(stat['timed_out'])
        self.assertLess(stat['phase_wall_s'],1.5)
        self.assertFalse(result['budget_overrun'])
    def test_no_popen_after_deadline(self):
        with mock.patch.object(entry.subprocess,'Popen',side_effect=AssertionError('NO POPEN')):
            result=self.run_batch('normal',deadline=time.monotonic()-1)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['budget_overrun'])
        self.assertNotIn('AssertionError',result['errors'])
        self.assertNotIn('stat',result['phases'])
    def test_threshold_aborts_growing_output(self):
        # review repro: the 20 MiB check must fire WHILE the file grows,
        # not only after the phase ends
        cfg=entry.load_config();cfg['limits']['report_threshold_mib']=0.001
        t=time.monotonic()
        result=self.run_batch('grow',config=cfg)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result.get('report_threshold_exceeded'))
        self.assertTrue(result['phases']['stat']['threshold_aborted'])
        self.assertLess(time.monotonic()-t,10)
    def test_launch_failure_fails(self):
        result=self.run_batch(perf_bin='/nonexistent/perf-bin')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['phases']['stat']['status'],'launch_failed')
    def test_big_output_bounded_no_deadlock(self):
        t=time.monotonic()
        result=self.run_batch('big_output')
        self.assertLess(time.monotonic()-t,15)
        self.assertEqual(result['status'],'complete')
        stat=result['phases']['stat']
        self.assertTrue(stat['stdout_truncated'])
        self.assertGreater(stat['stdout_total_bytes'],2*1024*1024)
        self.assertTrue(stat['target']['target_done'])
    def test_cleanup_survivor_cannot_pass(self):
        survivor=subprocess.Popen(['sleep','8']);self.extra_children.append(survivor)
        with mock.patch.dict(os.environ,{'FAKE_PERF_MODE':'fake_pid',
                                         'FAKE_FAKE_PID':str(survivor.pid)}):
            result=entry.run_batch(self.namespace/'batch',config=entry.load_config())
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['cleanup']['after_stat']['status'],'still_present')
        self.assertIn('CPU01Error',result['errors'])

    # ---- review group 4: stop confirmation & failure evidence -----------
    def test_stop_escalates_while_group_alive(self):
        # perf main exiting (or ignoring TERM) must NOT end the stop chain;
        # escalation continues until the WHOLE group is confirmed gone
        cfg=entry.load_config();cfg['limits'].update(target_wall_s=1,operation_s=1)
        result=self.run_batch('term_immune',config=cfg)
        self.assertEqual(result['status'],'FAIL')
        stat=result['phases']['stat']
        self.assertTrue(stat['timed_out'])
        events=str(stat['stop_events'])
        self.assertIn('SIGTERM:group_alive_after_wait',events)
        self.assertIn('SIGKILL:group_stopped',events)
        self.assertIn(result['cleanup']['after_stat']['status'],
                      ('exited','exited_zombie_pending_reap'))
    def test_survivor_permission_denied_is_check_failed(self):
        root=self.root/'proc';(root/'123').mkdir(parents=True)
        stat_file=root/'123'/'stat';stat_file.write_text('x (1) R 1')
        stat_file.chmod(0)
        outcome=entry._survivor_check(123,expected_starttime=1,proc_root=root)
        self.assertEqual(outcome['status'],'check_failed')
    def test_cleanup_check_failed_cannot_pass(self):
        with mock.patch.object(entry,'_survivor_check',
                return_value={'target_pid':1,'status':'check_failed'}):
            result=self.run_batch('normal')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['cleanup']['after_stat']['status'],'check_failed')
        self.assertIn('CPU01Error',result['errors'])
    def test_report_timeout_preserves_phase_evidence(self):
        # a failed report phase must still be archived with its evidence
        cfg=entry.load_config();cfg['limits']['operation_s']=1
        result=self.run_batch('report_hang',config=cfg)
        self.assertEqual(result['status'],'FAIL')
        report=result['phases']['report']
        self.assertEqual(report['status'],'timeout')
        self.assertTrue(report['timed_out'])
        self.assertTrue(report['stop_events'])
        self.assertTrue((self.namespace/'batch/report_raw.txt').exists())
    def test_drain_group_release_no_lingering_descendant(self):
        # a grandchild holding the stdout pipe must be cleared via the group
        # before the phase may count as complete
        cfg=entry.load_config();cfg['limits'].update(operation_s=1,target_wall_s=4)
        t=time.monotonic()
        result=self.run_batch('leak_grandchild',config=cfg)
        self.assertLess(time.monotonic()-t,12)
        self.assertFalse(result['phases']['stat']['drain_incomplete'])
        self.assertEqual(result['status'],'complete')
        with self.assertRaises(ProcessLookupError):
            os.killpg(result['phases']['stat']['perf_pid'],0)  # group is empty
    def test_normal_exit_group_leftover_is_cleaned(self):
        # review repro: perf exits normally after starting a background child
        # with closed stdio — the group must be verified and cleaned at EVERY
        # phase end, and an unconfirmed cleanup forbids complete
        result=self.run_batch('daemon_child')
        self.assertEqual(result['status'],'complete')
        stat=result['phases']['stat']
        self.assertTrue(stat['group_leftover'])
        self.assertIn('group_stopped',str(stat['stop_events']))
        with self.assertRaises(ProcessLookupError):
            os.killpg(stat['perf_pid'],0)  # group confirmed empty

    # ---- evidence -------------------------------------------------------
    def test_success_and_failure_both_archive(self):
        ok=self.run_batch('normal',name='ok')
        self.assertEqual(ok['status'],'complete')
        self.assertEqual(ok['archive_status'],'complete')
        bad=self.run_batch('no_csv',name='bad')
        self.assertEqual(bad['status'],'FAIL')
        self.assertEqual(bad['archive_status'],'complete')
        for name in ('ok','bad'):
            manifest=json.loads((self.namespace/name/'manifest.json').read_text())
            self.assertTrue(manifest['outputs'])
    def test_archive_failure_writes_marker_file(self):
        original=entry.write_json
        def write(path,payload):
            if Path(path).name=='manifest.json':raise OSError('fake archive failure')
            return original(path,payload)
        with mock.patch.object(entry,'write_json',side_effect=write):
            result=self.run_batch('normal')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['archive_status'],'failed')
        self.assertTrue((self.namespace/'batch/archive_failure.json').exists())
    def test_threshold_stops_batch(self):
        cfg=entry.load_config();cfg['limits']['report_threshold_mib']=0.000001
        result=self.run_batch('normal',config=cfg)
        self.assertEqual(result['status'],'FAIL')
    def test_budget_exhausted_fails(self):
        result=self.run_batch('normal',deadline=time.monotonic()-0.1)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['budget_overrun'])


def context_output():
    return mock.patch('sys.stdout',new_callable=io.StringIO)


if __name__=='__main__':
    unittest.main()
