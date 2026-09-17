"""CPU-01 single production entry: minimal perf measurability path.

Default plan is side-effect free (no subprocess, no file writes). Execution
requires BOTH flags AND a real approval file whose checklist_identity equals
the live build_plan identity; an attempt marker is registered exclusively
and never reused. The managed scope is this batch's own perf + target
process group only: no system-wide mode, no attach to unrelated PIDs, no
Docker, no network. Tests inject a fake perf executable, a fake paranoid
source and a shortened catalog; production never reads credentials or the
environment of other processes.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid

from ..collectors import perf_adapter
from ..collectors.host_process import read_starttime
from .report_writer import guard_cpu_report, guard_cpu_root, _catalog_protected_roots

PROJECT_ROOT=Path(__file__).resolve().parents[3]
CODE_ROOT=PROJECT_ROOT
CATALOG=PROJECT_ROOT/'workload_catalog/cpu_01.yaml'
TARGET=PROJECT_ROOT/'scripts/cpu_01_target.py'
APPROVAL=PROJECT_ROOT/'reports/cpu/CPU-01/APPROVAL.json'
ATTEMPT=PROJECT_ROOT/'reports/cpu/CPU-01/ATTEMPT_STARTED.json'
PARANOID_PATH='/proc/sys/kernel/perf_event_paranoid'


class CPU01Error(RuntimeError):
    pass


class UnavailableSignal(Exception):
    """Internal: perf refused/unavailable before the workload ran. The batch
    archives an honest 'unavailable' result; it is NOT an infra failure."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config():
    import yaml
    cfg=yaml.safe_load(CATALOG.read_text())
    if not isinstance(cfg,dict) or cfg.get('execution_authorized') is not False:
        raise CPU01Error('catalog_not_offline_registered')
    w=cfg['workload']
    if type(w['work_iterations']) is not int or w['work_iterations']<=0:
        raise CPU01Error('invalid_work_iterations')
    perf=cfg['perf']
    if not perf.get('binary') or not perf.get('stat',{}).get('events'):
        raise CPU01Error('invalid_perf_config')
    freq=perf['record']['frequency_hz']
    if type(freq) is not int or not 1<=freq<=cfg['limits']['record_frequency_hz_max']:
        raise CPU01Error('invalid_record_frequency')
    if perf['record']['frequency_hz']!=freq or perf['record']['event']!='cycles':
        raise CPU01Error('record_config_drift')
    lim=cfg['limits']
    for key,maximum in {'batch_wall_s':120,'cleanup_reserve_s':20,'operation_s':15,
                        'target_wall_s':10,'report_threshold_mib':20}.items():
        v=lim[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=maximum:
            raise CPU01Error('invalid_budget')
    if lim['retries']!=0:raise CPU01Error('retries_must_be_zero')
    if lim['batch_wall_s']<=lim['cleanup_reserve_s']:raise CPU01Error('invalid_reserve')
    return cfg


def target_argv(config):
    w=config['workload']
    return [str(Path(w['interpreter']).resolve()),'-B',str(TARGET),str(w['work_iterations'])]


def build_plan():
    cfg=load_config()
    paths=sorted((CODE_ROOT/'src/agent_workload_characterization').rglob('*.py'))+[TARGET]
    identity=dict(catalog_sha256=sha(CATALOG),config=cfg,
        code_sha256={str(p.relative_to(CODE_ROOT)):sha(p) for p in paths},
        interpreter={'path':str(Path(sys.executable).resolve()),'version':sys.version.split()[0]},
        collection='CPU-01',approval='reports/cpu/CPU-01/APPROVAL.json',
        target={'script':str(TARGET.relative_to(CODE_ROOT)),'interpreter':w_interp(cfg),
                'argv':target_argv(cfg),'work_iterations':cfg['workload']['work_iterations']},
        perf={'binary':cfg['perf']['binary'],'stat_events':cfg['perf']['stat']['events'].split(','),
              'record_event':cfg['perf']['record']['event'],
              'record_frequency_hz':cfg['perf']['record']['frequency_hz'],
              'report_mode':'--stdio --no-children'})
    return dict(task='CPU-01',mode='plan_only',identity=identity,
        b_command=f'PYTHONPATH=src {shlex.quote(str(Path(sys.executable).resolve()))} -B -m agent_workload_characterization.runners.cpu_01_entry --execute --i-approve-the-cpu-01-b',
        authorization={'user_approval':'pending','tool_execution_permission':'pending'},
        limits=cfg['limits'])


def w_interp(cfg):
    return cfg['workload']['interpreter']


def guarded(path, *, new=False):
    root=guard_cpu_root(PROJECT_ROOT,'CPU-01')
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if '..' in path.parts or not path.is_relative_to(root):raise CPU01Error('output_outside_namespace')
    current=PROJECT_ROOT.resolve()
    for part in path.relative_to(current).parts:
        current=current/part
        if current.is_symlink():raise CPU01Error('output_symlink')
    real=path.resolve()
    for p in [PROJECT_ROOT/'references',PROJECT_ROOT/'data/raw',*_catalog_protected_roots(PROJECT_ROOT)]:
        p=p.resolve()
        if real==p or real.is_relative_to(p) or p.is_relative_to(real):raise CPU01Error('protected_output')
    if new and path.exists():raise CPU01Error('output_exists')
    return path


def write_json(path,payload):
    guarded(path,new=True)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x',encoding='utf-8') as fh:
        json.dump(payload,fh,indent=2,allow_nan=False);fh.write('\n')


def verify_approval(path,identity=None):
    path=guarded(path)
    if path!=APPROVAL:raise CPU01Error('approval_wrong_namespace')
    record=json.loads(path.read_text())
    if (record.get('checklist_identity')!=(identity or build_plan()['identity']) or
        record.get('approved') is not True or not record.get('approved_by') or not record.get('approved_at_utc')):
        raise CPU01Error('approval_identity_or_user_record')
    return record


def register_attempt(identity):
    guarded(ATTEMPT,new=True).parent.mkdir(parents=True,exist_ok=True)
    write_json(ATTEMPT,dict(status='started',identity=identity,
        started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))


def finish_marker(status,detail):
    path=guarded(ATTEMPT);record=json.loads(path.read_text())
    record.update(status=status,detail=detail)
    tmp=path.with_name('ATTEMPT_FINISH-'+uuid.uuid4().hex+'.json')
    write_json(tmp,record);os.replace(tmp,path)


def remaining(deadline, ceiling):
    rem=min(ceiling,deadline-time.monotonic())
    if rem<=0:raise CPU01Error('budget_exhausted')
    return rem


def cleanup_timeout(deadline, *, limit_s, on_exhausted):
    rem=deadline-time.monotonic()
    if rem<=0:
        on_exhausted()
        return .1  # bounded best-effort safety cleanup, never a success
    return min(limit_s,rem)


def preflight_checks(*, deadline, perf_bin=None, target=None,
                     paranoid_path=None, starter=None):
    """B preflight, restricted to the items this batch actually needs.
    Nothing here executes perf: existence/X_OK is a filesystem check and the
    paranoid sysctl is only read (value recorded, not turned into a pass/fail
    verdict — real permission is a runtime result)."""
    perf_bin=perf_bin if perf_bin is not None else load_config()['perf']['binary']
    target=target if target is not None else TARGET
    paranoid_path=paranoid_path if paranoid_path is not None else PARANOID_PATH
    checks={}
    checks['perf_binary']=Path(perf_bin).is_file() and os.access(perf_bin,os.X_OK)
    checks['target_script']=Path(target).is_file()
    paranoid_value=None;paranoid_status='unreadable'
    try:
        paranoid_value=int(Path(paranoid_path).read_text().strip())
        paranoid_status='ok'
    except (OSError,ValueError):
        paranoid_value=None
    return dict(status='READY' if all(checks.values()) else 'NOT_READY',
        checks=checks,perf_binary=perf_bin,
        perf_event_paranoid={'value':paranoid_value,'read_status':paranoid_status,
            'note':'recorded only; actual permission is a runtime result, not pre-judged'},
        target_script=str(target))


def _drain(pipe,key,limit,store):
    chunks=[];total=0
    try:
        while True:
            chunk=pipe.read(4096)
            if not chunk:break
            total+=len(chunk)
            if total<=limit:chunks.append(chunk)
    finally:
        try:pipe.close()
        except OSError:pass
    store[key]=''.join(chunks) if total<=limit else ''.join(chunks)[:limit]
    store[key+'_truncated']=total>limit
    store[key+'_total_bytes']=total


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but is not ours to signal — treat as alive


def stop_process_group(proc, *, deadline, limit_s, on_exhausted):
    """Terminate the whole session (perf + target share the group). For each
    signal level, wait until BOTH the perf process has exited AND the process
    group is empty — perf exiting alone does NOT mean the target is gone.
    TERM first, bounded wait, KILL as last resort; returns the stop evidence."""
    events=[]
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try:os.killpg(proc.pid,sig)
        except (ProcessLookupError,PermissionError) as exc:
            events.append(f'{sig.name}:{type(exc).__name__}')
        wait_s=cleanup_timeout(deadline,limit_s=limit_s,on_exhausted=on_exhausted)
        wait_end=time.monotonic()+wait_s
        while time.monotonic()<wait_end:
            if proc.poll() is not None and not _group_alive(proc.pid):
                events.append(f'{sig.name}:group_stopped');return events
            time.sleep(.05)
        events.append(f'{sig.name}:group_alive_after_wait')
    return events


def run_phase(argv, *, deadline, limits, on_exhausted, phase_budget_s,
              mid_check=None):
    """Run one perf phase with a fresh process group.

    Budget rules: the deadline is checked BEFORE launch (no Popen after the
    budget is gone); during execution a polling loop enforces (a) the shared
    deadline, (b) this phase's OWN budget (target_wall_s for stat/record,
    operation_s for report — never their sum), and (c) a mid-phase artifact
    threshold callback so a growing output file aborts the phase instead of
    being caught only after it ends. stdout/stderr are drained continuously
    with a cap; drain threads are joined and verified, with a final group
    kill to release any fd-holding descendant before declaring completion."""
    start=time.monotonic()
    remaining(deadline,limits['operation_s'])  # raises when budget exhausted: never launch
    try:
        proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            start_new_session=True,text=True)
    except OSError as exc:
        return dict(argv=argv,launch_error=type(exc).__name__,phase_wall_s=time.monotonic()-start)
    outputs={}
    drains=[threading.Thread(target=_drain,args=(proc.stdout,'stdout',1<<20,outputs)),
            threading.Thread(target=_drain,args=(proc.stderr,'stderr',1<<20,outputs))]
    for t in drains:t.start()
    timed_out=False;stop_events=[];threshold_aborted=False;group_leftover=False
    rc=None
    try:
        while True:
            now=time.monotonic()
            # wait() timeout takes the REMAINING budget, never a fixed poll:
            # a 0.01 s budget must abort at ~0.01 s even if the process would
            # finish naturally at 0.066 s.
            poll=min(.1,phase_budget_s-(now-start),deadline-now)
            if poll<=0:poll=.001
            try:
                rc=proc.wait(timeout=poll);break
            except subprocess.TimeoutExpired:pass
            now=time.monotonic()
            if now>=deadline:
                timed_out=True;on_exhausted();break
            if now-start>=phase_budget_s:
                timed_out=True;break
            if mid_check is not None and mid_check():
                threshold_aborted=True;break
        if rc is not None and not timed_out and not threshold_aborted:
            # returned successfully — the phase budget/deadline still apply
            now=time.monotonic()
            if now>=deadline:
                timed_out=True;on_exhausted()
            elif now-start>=phase_budget_s:
                timed_out=True
        if timed_out or threshold_aborted:
            stop_events=stop_process_group(proc,deadline=deadline,
                limit_s=limits['operation_s'],on_exhausted=on_exhausted)
            rc=proc.poll()
        elif _group_alive(proc.pid):
            # NORMAL exit can still leave descendants in this batch's group
            # (e.g. a backgrounded child with closed stdio). Verify by
            # cleaning the group now — an unconfirmed cleanup forbids
            # declaring the phase complete.
            group_leftover=True
            stop_events=stop_process_group(proc,deadline=deadline,
                limit_s=limits['operation_s'],on_exhausted=on_exhausted)
    except BaseException:
        stop_process_group(proc,deadline=deadline,limit_s=limits['operation_s'],
                           on_exhausted=on_exhausted)
        for t in drains:t.join(timeout=1)
        raise
    join_s=cleanup_timeout(deadline,limit_s=limits['operation_s'],
                           on_exhausted=on_exhausted)
    for t in drains:t.join(timeout=join_s)
    drain_incomplete=any(t.is_alive() for t in drains)
    if drain_incomplete:
        # A descendant may still hold the pipe open; clear the whole group
        # before deciding this phase is complete.
        try:os.killpg(proc.pid,signal.SIGKILL)
        except (ProcessLookupError,PermissionError):pass
        for t in drains:t.join(timeout=min(2,cleanup_timeout(deadline,
                limit_s=limits['operation_s'],on_exhausted=on_exhausted)))
        drain_incomplete=any(t.is_alive() for t in drains)
    return dict(argv=argv,perf_pid=proc.pid,returncode=rc,timed_out=timed_out,
        stop_events=stop_events,threshold_aborted=threshold_aborted,
        group_leftover=group_leftover,
        drain_incomplete=drain_incomplete,phase_wall_s=time.monotonic()-start,
        stdout=outputs.get('stdout',''),stdout_truncated=outputs.get('stdout_truncated',False),
        stdout_total_bytes=outputs.get('stdout_total_bytes',0),
        stderr=outputs.get('stderr',''),stderr_truncated=outputs.get('stderr_truncated',False),
        stderr_total_bytes=outputs.get('stderr_total_bytes',0))


def _target_check(phase_result):
    view=perf_adapter.parse_target_lines(phase_result.get('stdout',''))
    return view


def _confirm_group_cleanup(phase):
    """If any stop was attempted in this phase, it must have ended with the
    whole process group confirmed gone; an unconfirmed cleanup forbids
    declaring the batch complete."""
    events=phase.get('stop_events') or []
    if events and not any(e.endswith(':group_stopped') for e in events):
        raise CPU01Error('group_cleanup_unconfirmed')


def _survivor_check(target_pid, *, expected_starttime=None, proc_root=None):
    """After the group stop, verify the known target identity is really gone
    (only the recorded PID is inspected; unrelated processes are untouched).
    A zombie (state Z) has already exited and is only awaiting reap by its
    new parent — that is NOT a survivor still running. An unreadable /proc
    entry (permission etc.) is 'check_failed', never mistaken for 'exited'."""
    if target_pid is None:return {'target_pid':None,'status':'unknown_pid'}
    root=Path(proc_root) if proc_root is not None else Path('/proc')
    try:
        stat=(root/f'{target_pid}/stat').read_text(encoding='ascii',errors='replace')
    except FileNotFoundError:
        return {'target_pid':target_pid,'status':'exited'}
    except OSError:
        return {'target_pid':target_pid,'status':'check_failed'}
    try:
        fields=stat.rsplit(')',1)[1].split()
        if fields[0]=='Z':
            return {'target_pid':target_pid,'status':'exited_zombie_pending_reap'}
        current=int(fields[19])
    except (IndexError,ValueError):
        return {'target_pid':target_pid,'status':'check_failed'}
    if expected_starttime is not None and current!=expected_starttime:
        return {'target_pid':target_pid,'status':'pid_reuse_original_exited'}
    return {'target_pid':target_pid,'status':'still_present'}


_SURVIVOR_CONFIRMED=('exited','exited_zombie_pending_reap','pid_reuse_original_exited')


def stat_survivor(view, *, proc_root=None):
    started=view.get('target_started') if view else None
    return _survivor_check(started.get('pid') if started else None,
        expected_starttime=started.get('starttime_ticks') if started else None,
        proc_root=proc_root)


def check_target(view, config):
    """Verify the target's self-reported lifecycle against this batch's
    registered workload: same PID across started/done, the configured
    iteration count, and the closed-form checksum. A done line alone proves
    nothing; mismatches fail the phase."""
    started=view.get('target_started');done=view.get('target_done')
    if not started or not done:
        return {'status':'incomplete','reason':'started_or_done_missing'}
    problems=[]
    if started.get('pid')!=done.get('pid'):problems.append('pid_mismatch')
    if started.get('iterations')!=config['workload']['work_iterations']:
        problems.append('iterations_mismatch')
    expected=perf_adapter.expected_checksum(config['workload']['work_iterations'])
    if done.get('checksum')!=expected:problems.append('checksum_mismatch')
    if problems:
        return {'status':'mismatch','problems':problems,'expected_checksum':expected}
    return {'status':'ok','expected_checksum':expected}


def run_batch(output_dir,*,config=None,deadline=None,run_id=None,identity=None,
              preflight=None,perf_bin=None):
    config=json.loads(json.dumps(config or load_config()))  # deep copy
    lim=config['limits']
    deadline=deadline if deadline is not None else time.monotonic()+lim['batch_wall_s']
    perf_bin=perf_bin if perf_bin is not None else config['perf']['binary']
    output_dir=guarded(output_dir,new=True)
    guard_cpu_report(PROJECT_ROOT,output_dir,'CPU-01');output_dir.mkdir(parents=True)
    run_id=run_id or 'CPU-01-'+uuid.uuid4().hex
    payload=dict(run_id=run_id,status='pending',phases={},cleanup={},preflight=preflight,
        errors=[],budget_overrun=False,archive_status='pending')
    payload['clock_anchor']={'monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),
        'domain':'same_host_CLOCK_MONOTONIC',
        'assumption':'native perf and target share host clocks'}
    payload['config_limits']=dict(lim)
    payload['perf_binary_sha256']=_file_sha_if_exists(perf_bin)
    payload['collection_semantics']=('owned synthetic target only; NOT an Agent '
        'workload; hotspots are NOT Agent hotspots; software events are not '
        'hardware support; sample ratios are not CPU seconds')
    overrun=lambda: payload.__setitem__('budget_overrun',True)
    work_deadline=deadline-lim['cleanup_reserve_s']
    def bytes_now():return sum(p.stat().st_size for p in output_dir.rglob('*') if p.is_file())
    def threshold_breach():
        try:return bytes_now()>lim['report_threshold_mib']*2**20
        except OSError:return False
    def check():
        if bytes_now()>lim['report_threshold_mib']*2**20:
            raise CPU01Error('report_threshold_exceeded')
        remaining(work_deadline,lim['operation_s'])
    try:
        targv=target_argv(config)
        # ---- stat phase ---------------------------------------------------
        stat_csv=output_dir/'stat.csv'
        argv=perf_adapter.stat_argv(perf_bin,stat_csv,config['perf']['stat']['events'],targv)
        phase=run_phase(argv,deadline=work_deadline,limits=lim,on_exhausted=overrun,
                        phase_budget_s=lim['target_wall_s'],mid_check=threshold_breach)
        view=_target_check(phase)
        tcheck=check_target(view,config)
        stat_result=dict(phase,status='FAIL',target=view,target_check=tcheck)
        stat_result['target_completed']=view['target_done'] is not None
        payload['phases']['stat']=stat_result  # evidence saved before any raise
        if phase.get('launch_error'):
            stat_result['status']='launch_failed'
            raise CPU01Error('stat_launch_failed')
        if phase['timed_out']:
            stat_result['status']='timeout'
            payload['cleanup']['after_stat']=stat_survivor(view)
            raise CPU01Error('stat_timeout')
        if phase.get('threshold_aborted'):
            stat_result['status']='threshold_aborted'
            payload['report_threshold_exceeded']=True
            raise CPU01Error('report_threshold_exceeded')
        if phase.get('drain_incomplete'):
            stat_result['status']='drain_incomplete'
            raise CPU01Error('stat_drain_incomplete')
        _confirm_group_cleanup(phase)
        raw=None
        if stat_csv.is_file():raw=stat_csv.read_text(errors='replace')
        stat_result['stat_raw_retained']=raw is not None
        if raw is None:
            if view['target_started'] is None and phase['returncode']!=0:
                # perf refused before even running the workload
                stat_result['status']='unavailable'
                stat_result['parse_status']='perf_refused'
            elif phase['returncode']!=0:
                stat_result['status']='nonzero_rc_no_output'
            else:
                stat_result['status']='output_missing'
                stat_result['parse_status']='stat_csv_missing'
        else:
            parsed=perf_adapter.parse_stat_csv(raw)
            stat_result.update(parsed=parsed,ipc=perf_adapter.compute_ipc(parsed),
                n_supported=sum(1 for r in parsed['events'] if r['status']=='ok'),
                n_not_supported=sum(1 for r in parsed['events'] if r['status']=='not_supported'))
            if phase['returncode']!=0:
                stat_result['status']='nonzero_rc_with_output'
            elif parsed['n_counters']==0:
                # metric-only lines are not counters: an empty counter set
                # cannot pass as a valid stat
                stat_result['status']='no_counter_lines'
            elif parsed['n_parse_errors']>0:
                stat_result['status']='parsed_with_errors'
            else:
                stat_result['status']='parsed'
        if tcheck['status']!='ok' and stat_result['status'] in ('parsed','parsed_with_errors'):
            stat_result['status']='target_identity_mismatch'
        payload['phases']['stat']=stat_result
        check()
        if stat_result['status']=='unavailable':
            raise UnavailableSignal('stat_unavailable')
        payload['cleanup']['after_stat']=stat_survivor(view)
        if payload['cleanup']['after_stat']['status'] not in _SURVIVOR_CONFIRMED:
            raise CPU01Error('target_stop_unconfirmed')
        if stat_result['status']!='parsed':
            raise CPU01Error('stat_'+stat_result['status'])
        # ---- record phase -------------------------------------------------
        data_path=output_dir/'perf.data'
        argv=perf_adapter.record_argv(perf_bin,data_path,
            config['perf']['record']['event'],config['perf']['record']['frequency_hz'],targv)
        phase=run_phase(argv,deadline=work_deadline,limits=lim,on_exhausted=overrun,
                        phase_budget_s=lim['target_wall_s'],mid_check=threshold_breach)
        view=_target_check(phase)
        tcheck=check_target(view,config)
        record=dict(phase,status='FAIL',target=view,target_check=tcheck)
        record['target_completed']=view['target_done'] is not None
        payload['phases']['record']=record  # evidence saved before any raise
        if phase.get('launch_error'):
            record['status']='launch_failed'
            raise CPU01Error('record_launch_failed')
        if phase['timed_out']:
            record['status']='timeout'
            payload['cleanup']['after_record']=stat_survivor(view)
            raise CPU01Error('record_timeout')
        if phase.get('threshold_aborted'):
            record['status']='threshold_aborted'
            payload['report_threshold_exceeded']=True
            raise CPU01Error('report_threshold_exceeded')
        if phase.get('drain_incomplete'):
            record['status']='drain_incomplete'
            raise CPU01Error('record_drain_incomplete')
        _confirm_group_cleanup(phase)
        data_exists=data_path.is_file()
        record['perf_data_present']=data_exists
        if data_exists:
            record['perf_data_bytes']=data_path.stat().st_size
            record['perf_data_sha256']=sha(data_path)
        if view['target_started'] is None and phase['returncode']!=0:
            record['status']='unavailable'  # perf refused, not an infra failure
        elif phase['returncode']!=0 and not data_exists:
            record['status']='nonzero_rc_no_output'
        elif phase['returncode']!=0:
            record['status']='data_with_nonzero_rc'
        elif not data_exists:
            record['status']='rc0_output_missing'  # cannot claim a profile
        else:
            record['status']='data_present'
        if tcheck['status']!='ok' and record['status']=='data_present':
            record['status']='target_identity_mismatch'
        payload['phases']['record']=record
        check()
        if record['status']=='unavailable':
            raise UnavailableSignal('record_unavailable')
        if view['target_started'] is None:
            raise CPU01Error('record_target_missing')
        payload['cleanup']['after_record']=stat_survivor(view)
        if payload['cleanup']['after_record']['status'] not in _SURVIVOR_CONFIRMED:
            raise CPU01Error('target_stop_unconfirmed')
        if record['status']!='data_present':
            raise CPU01Error('record_'+record['status'])
        # ---- report phase -------------------------------------------------
        report=dict(argv=None,status='skipped')
        if data_exists:
            argv=perf_adapter.report_argv(perf_bin,data_path)
            phase=run_phase(argv,deadline=work_deadline,limits=lim,on_exhausted=overrun,
                            phase_budget_s=lim['operation_s'],mid_check=threshold_breach)
            report.update(phase)
            report['report_raw_retained']=True
            # raw output persisted BEFORE any raise so failed phases keep evidence
            (output_dir/'report_raw.txt').write_text(phase.get('stdout',''))
            payload['phases']['report']=report
            if phase.get('launch_error'):
                report['status']='failed'
                raise CPU01Error('report_launch_failed')
            if phase['timed_out']:
                report['status']='timeout'
                raise CPU01Error('report_timeout')
            if phase.get('threshold_aborted'):
                report['status']='threshold_aborted'
                payload['report_threshold_exceeded']=True
                raise CPU01Error('report_threshold_exceeded')
            if phase.get('drain_incomplete'):
                report['status']='drain_incomplete'
                raise CPU01Error('report_drain_incomplete')
            _confirm_group_cleanup(phase)
            parsed=perf_adapter.parse_report(phase.get('stdout',''))
            report['parsed']=parsed
            if phase['returncode']!=0:
                report['status']='nonzero_rc'
                raise CPU01Error('report_nonzero_rc')
            if parsed['evidence_status']=='empty_output':
                report['status']='empty_output'
                raise CPU01Error('report_empty_output')
            if parsed['unparsed_percent_lines']:
                # a data-looking line we failed to parse must affect validity,
                # never silently pass as a complete profile
                report['status']='parsed_with_errors'
                raise CPU01Error('report_parsed_with_errors')
            if parsed['evidence_status'] in ('no_header_no_rows','header_no_rows'):
                report['status']='unknown_output'
                raise CPU01Error('report_unknown_output')
            report['status']='parsed'  # header_zero is an honest zero-sample profile
        else:
            report['skip_reason']='perf_data_missing'
        payload['phases']['report']=report
        check()
    except UnavailableSignal:
        pass  # environment result, archived honestly below
    except Exception as exc:
        payload['errors'].append(type(exc).__name__)
        payload['status']='FAIL'
    finally:
        payload['budget_overrun'] |= time.monotonic()>deadline
        if payload['budget_overrun']:payload['status']='FAIL'
        payload['wall_s']=lim['batch_wall_s']-(deadline-time.monotonic())
    if payload['status']=='pending':
        stat_status=payload['phases'].get('stat',{}).get('status')
        record_status=payload['phases'].get('record',{}).get('status','absent')
        report_status=payload['phases'].get('report',{}).get('status','absent')
        if stat_status=='unavailable' or record_status=='unavailable':
            payload['status']='unavailable'
        elif (stat_status=='parsed' and record_status=='data_present'
              and report_status=='parsed'):
            payload['status']='complete'
        else:
            payload['status']='fail'
    try:
        payload['archive_status']='complete'
        projected=bytes_now()+len(json.dumps(payload,indent=2).encode())
        if projected>lim['report_threshold_mib']*2**20:
            payload['status']='FAIL';payload['report_threshold_exceeded']=True
        write_json(output_dir/'summary.json',payload)
        outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,'sha256':sha(p)}
                 for p in output_dir.rglob('*') if p.is_file()}
        manifest=dict(identity=identity or build_plan()['identity'],outputs=outputs,
            inputs=dict(catalog={'bytes':CATALOG.stat().st_size,'sha256':sha(CATALOG)},
                        target_script={'bytes':TARGET.stat().st_size,'sha256':sha(TARGET)},
                        perf_binary=payload['perf_binary_sha256']),
            created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            status=payload['status'])
        write_json(output_dir/'manifest.json',manifest)
        actual=json.loads((output_dir/'manifest.json').read_text())['outputs']
        if actual!=outputs or any(sha(output_dir/p)!=v['sha256'] or
                (output_dir/p).stat().st_size!=v['bytes'] for p,v in actual.items()):
            raise CPU01Error('archive_hash_mismatch')
    except Exception as exc:
        payload.update(status='FAIL',archive_status='failed')
        payload['errors'].append(type(exc).__name__)
        try:write_json(output_dir/'archive_failure.json',{'status':'FAIL','category':type(exc).__name__})
        except Exception:pass
    return payload


def _file_sha_if_exists(path):
    try:return sha(path)
    except OSError:return None


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--i-approve-the-cpu-01-b',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_cpu_01_b:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (args.execute and args.i_approve_the_cpu_01_b):return 2
    try:
        plan=build_plan();identity=plan['identity']
        verify_approval(APPROVAL,identity);register_attempt(identity)
    except Exception as exc:
        print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+plan['limits']['batch_wall_s']
    rc=5;detail='execution_failed'
    try:
        preflight=preflight_checks(deadline=deadline)
        write_json(guarded(APPROVAL.parent/'PREFLIGHT.json',new=True),preflight)
        if preflight['status']!='READY':rc=4;detail='preflight_failed'
        else:
            batch='CPU-01-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
            result=run_batch(APPROVAL.parent/batch,config=identity['config'],
                deadline=deadline,run_id=batch,identity=identity,preflight=preflight)
            rc=0 if result['status'] in ('complete','unavailable') and result['archive_status']=='complete' else 5
            detail=(f"stat_{result['phases'].get('stat',{}).get('status','absent')}"
                    f"_record_{result['phases'].get('record',{}).get('status','absent')}")
    except Exception as exc:detail=type(exc).__name__
    try:finish_marker('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
