"""One-shot, read-only CPU-02 namespace/perf permission confirmation.

This is preparation for a future confirmation only.  It does not retry the
CPU-02 workload.  Production uses the existing Docker runtime and perf
control helpers; tests replace only those external boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import select
import signal
import time
import uuid

from . import cpu_02_entry as cpu02
from .container_runtime import ContainerSpec, DockerCliRuntime
from .g1_02_entry import local_docker_environment
from .cpu_02_pid_diagnostic import _host_proc_projection, _proc_mount_projection

PROJECT_ROOT=cpu02.PROJECT_ROOT
ROOT=PROJECT_ROOT/'reports/cpu/CPU-02/permission-confirmation'
APPROVAL=ROOT/'APPROVAL.json'
ATTEMPT=ROOT/'ATTEMPT_STARTED.json'
CHECK_ID='CPU-02-PERMISSION-CONFIRMATION-01'
RUNTIME_FACTORY=lambda: DockerCliRuntime(authorized=True,collection=CHECK_ID)
PERF_FACTORY=None
PROC_ROOT=None
PERF_BIN='/usr/bin/perf'
WORK_SECONDS=1.0
MAX_SAMPLE_SECONDS=5.0


def _self_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _worker_command(work_seconds=WORK_SECONDS):
    code=f"""import hashlib, json, os, sys, time
s=open('/proc/self/stat').read().rsplit(')', 1)[1].split()
reported_pid=int(os.environ.get('CONFIRM_CONTAINER_PID', os.getpid()))
ready={{'event':'ready', 'pid':reported_pid, 'container_process_pid':os.getpid(), 'starttime_ticks':int(s[19]),
        'pid_namespace':os.readlink('/proc/self/ns/pid')}}
print(json.dumps(ready), flush=True)
line=sys.stdin.readline()
if line.strip() != '{{"cmd":"release"}}':
    raise SystemExit(3)
start=time.monotonic()
print(json.dumps({{'event':'started', 'pid':reported_pid, 'container_process_pid':os.getpid(),
                   'started_monotonic':start}}), flush=True)
end=start+{float(work_seconds)!r}
i=0
h=hashlib.sha256()
while time.monotonic() < end:
    h.update(str(i).encode())
    i += 1
finish=time.monotonic()
print(json.dumps({{'event':'done', 'pid':reported_pid, 'container_process_pid':os.getpid(),
                   'finished_monotonic':finish, 'iterations':i,
                   'checksum':h.hexdigest()}}), flush=True)
sys.stdin.readline()
"""
    return 'python3 -u -c '+cpu02.shlex.quote(code)


def _read_event(proc, buffer, deadline, *, limit=65536):
    """Read one JSONL event without blocking on a partial/non-newline line."""
    fd=proc.stdout.fileno()
    while time.monotonic()<deadline:
        if b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1)
            if len(line)>limit: return None,buffer,'line_too_large'
            try:return json.loads(line.decode('utf-8')),buffer,None
            except (UnicodeDecodeError,json.JSONDecodeError):continue
        ready,_,_=select.select([fd],[],[],max(0.0,deadline-time.monotonic()))
        if not ready:break
        try:chunk=os.read(fd,4096)
        except OSError as exc:return None,buffer,type(exc).__name__
        if not chunk:return None,buffer,'eof'
        buffer+=chunk
        if len(buffer)>limit:return None,buffer,'buffer_limit'
    return None,buffer,'timeout'


def _finish_marker(status,detail):
    path=cpu02.guarded(ATTEMPT);record=json.loads(path.read_text())
    record.update(status=status,detail=detail)
    tmp=path.with_name('ATTEMPT_FINISH-'+uuid.uuid4().hex+'.json')
    cpu02.write_json(tmp,record);os.replace(tmp,path)


def build_plan():
    identity=json.loads(json.dumps(cpu02.build_plan()['identity']))
    identity.update(confirmation_id=CHECK_ID,
                    approval='reports/cpu/CPU-02/permission-confirmation/APPROVAL.json')
    identity['confirmation_entry']={'path':str(Path(__file__).relative_to(PROJECT_ROOT)),
                                    'sha256':_self_sha256(),
                                    'protocol':'ready -> release -> started -> bounded_cpu -> done',
                                    'same_pid':True}
    identity['perf_supervisor']={'source':str(cpu02.PERF_SUPERVISOR.relative_to(PROJECT_ROOT)),
        'sha256':hashlib.sha256(cpu02.PERF_SUPERVISOR.read_bytes()).hexdigest(),
        'installed_path':'/usr/local/libexec/cpu02-perf-supervisor',
        'fixed_perf':'/usr/bin/perf record cycles@99Hz',
        'status':'offline_source_only_not_installed'}
    identity['config']['confirmation']={'container_count':1,'cpu':'1','memory':'256m',
        'batch_wall_s':60,'cleanup_reserve_s':15,'sample_max_s':MAX_SAMPLE_SECONDS,
        'worker_seconds':WORK_SECONDS,'namespace_before_perf':True,
        'output_root':'reports/cpu/CPU-02/permission-confirmation'}
    identity['config']['authorization']={'approval_path':identity['approval'],
        'attempt_path':'reports/cpu/CPU-02/permission-confirmation/ATTEMPT_STARTED.json',
        'user_approval':'pending','tool_execution_permission':'pending'}
    return {'task':'CPU-02','mode':'plan_only','confirmation_id':CHECK_ID,
        'identity':identity,
        'b_command':('PYTHONPATH=src '+cpu02.shlex.quote(str(cpu02.VENV_PYTHON))+
          ' -B -m agent_workload_characterization.runners.cpu_02_permission_confirmation'
          ' --execute --i-approve-the-cpu-02-permission-confirmation'),
        'limits':identity['config']['confirmation'],
        'authorization':{'user_approval':'pending','tool_execution_permission':'pending'}}


def _verify_approval(identity):
    record=json.loads(cpu02.guarded(APPROVAL).read_text())
    if record.get('approved') is not True or record.get('approved_by')!='lcq' or \
       record.get('checklist_identity')!=identity:
        raise cpu02.CPU02Error('confirmation_approval_identity')


def _execution_context():
    """Whitelist only identity/sandbox fields; never read environ/cmdline."""
    fields={}
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            key,value=(line.split(':',1)+[''])[:2]
            if key in {'Uid','Gid','Groups','CapEff','NoNewPrivs','Seccomp','Seccomp_filters'}:
                fields[key]=value.strip()
        fields['read_status']='ok'
    except OSError as exc:
        fields={'read_status':'unavailable','error_type':type(exc).__name__,
                'errno':getattr(exc,'errno',None)}
    try: security=Path('/proc/self/attr/current').read_text().strip('\x00\n')
    except OSError: security=None
    return {'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid(),
            'groups':list(os.getgroups()),'status':fields,
            'security_domain':security if security is not None else 'unavailable'}


def _archive(output_dir,payload,identity):
    summary=output_dir/'summary.json';manifest=output_dir/'manifest.json'
    cpu02.write_json(output_dir/'report.json',payload.get('report',{}))
    cpu02.write_json(summary,payload)
    outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in output_dir.rglob('*') if p.is_file() and p.name!='manifest.json'}
    m={'identity':identity,'status':payload['status'],'created_at_utc':
       time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'outputs':{
       **outputs}}
    cpu02.write_json(manifest,m)
    return m


def _redact_perf_text(value):
    text=value if isinstance(value,str) else ''
    return re.sub(r'(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s]+',
                  r'\1=[REDACTED]', text)


def _persist_perf_logs(output_dir,payload):
    evidence=(payload.get('perf') or {}).get('output_evidence') or {}
    stdout=_redact_perf_text(evidence.get('stdout',''))
    stderr=_redact_perf_text(evidence.get('stderr',''))
    (output_dir/'perf_stdout.txt').write_text(
        stdout,encoding='utf-8')
    (output_dir/'perf_stderr.txt').write_text(
        stderr,encoding='utf-8')
    # Never leave the raw drain buffer reachable from the returned payload:
    # main() prints this structure and _archive() serializes it verbatim.
    perf=payload.setdefault('perf',{})
    perf.pop('output_evidence',None)
    perf['log_evidence']={
        'stdout_bytes':evidence.get('stdout_total_bytes',0),
        'stderr_bytes':evidence.get('stderr_total_bytes',0),
        'stdout_truncated':bool(evidence.get('stdout_truncated',False)),
        'stderr_truncated':bool(evidence.get('stderr_truncated',False)),
        'drain_complete':bool((payload.get('perf') or {}).get('drain_complete',False)),
        'files':['perf_stdout.txt','perf_stderr.txt']}


def _rewrite_archive_state(output_dir,payload,identity,created_at_utc):
    """Refresh summary and manifest after late cleanup/deadline decisions."""
    summary=output_dir/'summary.json'
    cpu02.rewrite_json(summary,payload)
    outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in output_dir.rglob('*') if p.is_file() and p.name!='manifest.json'}
    cpu02.rewrite_json(output_dir/'manifest.json',{
        'identity':identity,'status':payload['status'],
        'created_at_utc':created_at_utc,'outputs':outputs})


def _perf_stop_confirmed(events):
    return any(str(event).endswith('group_stopped') for event in (events or []))


def _perf_exit_success(perf):
    """A controlled stop must yield a normal perf exit, not partial data."""
    proc=perf.get('proc')
    if proc is None:
        return False
    try:
        return proc.poll()==0
    except (OSError,AttributeError):
        return False


def _check_perf_data_readable(path):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        os.close(fd)
        st=os.stat(path,follow_symlinks=False)
        return {'status':'readable','uid':st.st_uid,'mode':oct(st.st_mode & 0o777),
                'bytes':st.st_size}
    except OSError as exc:
        return {'status':'unavailable','error_type':type(exc).__name__,
                'errno':getattr(exc,'errno',None)}


def run_confirmation(runtime,output_dir,*,identity,deadline,proc_root=None,
                     perf_factory=None,report_runner=None,work_seconds=WORK_SECONDS,
                     init_namespace_reader=None, candidate_namespace_reader=None,
                     mapping_post_validator=None, perf_sudo=False,
                     perf_supervisor_path=None):
    started=time.monotonic();output_dir=cpu02.guarded(output_dir,new=True)
    output_dir.mkdir(parents=True)
    payload={'run_id':output_dir.name,'confirmation_id':CHECK_ID,'status':'FAIL',
        'archive_status':'pending','errors':[],'cleanup':{},'budget_overrun':False,
        'identity':identity,'wall_cutoff':'after_archive_write',
        'execution_context':_execution_context(),
        'proc_mount_projection':_proc_mount_projection(),
        'diagnostic_process':_host_proc_projection(os.getpid())}
    handle=proc=perf=None;perf_stopped=False;perf_cleanup_confirmed=False
    buffer=b''
    work_deadline=deadline-15
    sample_deadline=None
    try:
        spec=ContainerSpec(output_dir.name,'permission-confirmation',identity['image'],
            cpu_limit='1',mem_limit='256m',network='none',pull='never',platform='linux/arm64')
        handle=runtime.start(spec,timeout_s=cpu02.remaining(work_deadline,15))
        payload['container_id']=handle.container_id
        proc=runtime.open_interactive(handle,_worker_command(work_seconds),
                                      cpu02.remaining(work_deadline,15))
        event,buffer,error=_read_event(proc,buffer,min(work_deadline,time.monotonic()+15))
        if error or not event or event.get('event')!='ready':raise cpu02.CPU02Error('worker_ready_failed')
        payload['worker_ready']=event
        init=runtime.container_init_pid(handle,timeout_s=cpu02.remaining(work_deadline,15))
        payload['container_init_pid']=init
        if not init:raise cpu02.CPU02Error('container_init_pid_missing')
        init_namespace=None
        if init_namespace_reader is not None:
            init_namespace=init_namespace_reader(
                init, deadline=min(work_deadline, time.monotonic()+15))
            payload['init_namespace_read']='sudo_assisted'
        candidate_reads=[]
        payload['sudo_candidate_namespace_reads']=candidate_reads
        def read_candidate(host_pid, container_pid, expected_starttime):
            entry={'target_role':'worker_candidate','pid':host_pid,
                   'container_pid':container_pid,
                   'trigger':'ordinary_namespace_eacces_or_eperm'}
            try:
                value=candidate_namespace_reader(host_pid, container_pid, expected_starttime)
                entry['status']='ok'
                candidate_reads.append(entry)
                return value
            except Exception as exc:
                entry['status']='failed';entry['error_type']=type(exc).__name__
                candidate_reads.append(entry)
                raise
        mapping=cpu02.map_container_pid(event['pid'],event['starttime_ticks'],init,
                                        proc_root=proc_root,init_namespace=init_namespace,
                                        candidate_namespace_reader=(read_candidate if candidate_namespace_reader is not None else None))
        payload['mapping']=mapping
        if mapping.get('status')!='ok':raise cpu02.CPU02Error('namespace_mapping_failed')
        if mapping_post_validator is not None:
            mapping_post_validator(mapping, init, handle, payload['container_id'])
        payload['namespace_status']='confirmed'
        factory=perf_factory or (lambda **kw: cpu02.start_perf_controlled(**kw))
        perf_kwargs={'perf_bin':PERF_BIN,'host_pid':mapping['host_pid'],
                     'data_path':output_dir/'perf.data','cfg':cpu02.load_config(),
                     'output_dir':output_dir}
        if perf_sudo and perf_factory is None:perf_kwargs['sudo']=True
        if perf_supervisor_path is not None and perf_factory is None:
            perf_kwargs.update(supervisor_path=perf_supervisor_path,
                               target_starttime=int(event.get('starttime_ticks',
                                                               mapping.get('starttime_ticks',0))),
                               target_pgid=int(os.getpgid(mapping['host_pid'])),
                               deadline=sample_deadline if sample_deadline is not None else work_deadline)
        perf=factory(**perf_kwargs)
        payload['perf']={k:v for k,v in perf.items() if k not in ('proc','drains','ctl_fd','ack_fd')}
        if perf.get('status')!='started':raise cpu02.CPU02Error('perf_attach_failed')
        sample_deadline=min(work_deadline,time.monotonic()+MAX_SAMPLE_SECONDS)
        command=(lambda name: cpu02.control_cmd(perf,name,deadline=sample_deadline,
                                                 on_exhausted=lambda:payload.__setitem__('budget_overrun',True)))
        enable=command('enable');payload['perf']['enable_ack']=enable
        if not enable.get('ack'):
            payload['perf']['exit_observed_during_enable']=perf.get('proc').poll()
            raise cpu02.CPU02Error('perf_enable_unconfirmed')
        proc.stdin.write('{"cmd":"release"}\n');proc.stdin.flush()
        event,buffer,error=_read_event(proc,buffer,sample_deadline)
        if error or not event or event.get('event')!='started':raise cpu02.CPU02Error('worker_started_missing')
        payload['worker_started']=event
        if event.get('pid')!=payload['worker_ready'].get('pid'):
            raise cpu02.CPU02Error('worker_pid_changed')
        event,buffer,error=_read_event(proc,buffer,sample_deadline)
        if error or not event or event.get('event')!='done':raise cpu02.CPU02Error('worker_done_missing')
        payload['worker_done']=event
        if event.get('pid')!=payload['worker_ready'].get('pid'):
            raise cpu02.CPU02Error('worker_pid_changed')
        if event.get('finished_monotonic',0)<payload['worker_started'].get('started_monotonic',0):
            raise cpu02.CPU02Error('worker_time_order_invalid')
        if not isinstance(event.get('iterations'),int) or event.get('iterations')<=0 or \
           not isinstance(event.get('checksum'),str) or len(event['checksum'])!=64:
            raise cpu02.CPU02Error('worker_completion_evidence_invalid')
        if event.get('finished_monotonic',0)-payload['worker_started'].get('started_monotonic',0)>MAX_SAMPLE_SECONDS:
            raise cpu02.CPU02Error('sample_window_exceeded')
        disable=command('disable');payload['perf']['disable_ack']=disable
        if not disable.get('ack'):raise cpu02.CPU02Error('perf_disable_unconfirmed')
        stop=cpu02.stop_perf(perf,deadline=deadline,limit_s=15,
            on_exhausted=lambda:payload.__setitem__('budget_overrun',True))
        payload['perf']['stop_events']=stop
        perf_stopped=True
        perf_cleanup_confirmed=_perf_stop_confirmed(stop)
        payload['perf']['group_stop_confirmed']=perf_cleanup_confirmed
        pproc=perf.get('proc')
        payload['perf']['process_exit_code']=pproc.poll() if pproc is not None else 'unavailable'
        report=cpu02.run_report_phase(PERF_BIN,output_dir/'perf.data',runner=report_runner,
            timeout_s=cpu02.remaining(deadline,15))
        payload['perf']['data_access']=_check_perf_data_readable(output_dir/'perf.data')
        if payload['perf']['data_access']['status']!='readable':
            raise cpu02.CPU02Error('perf_data_unreadable')
        payload['report']=report
        parsed=report.get('parsed') or {}
        valid=(report.get('status')=='parsed' and parsed.get('evidence_status')=='header_and_rows'
               and isinstance(parsed.get('total_samples'),int) and parsed['total_samples']>0
               and parsed.get('n_rows',0)>0)
        payload['perf']['sample_status']='available' if valid else 'unavailable'
        if not perf_cleanup_confirmed:raise cpu02.CPU02Error('perf_cleanup_unconfirmed')
        if not _perf_exit_success(perf):raise cpu02.CPU02Error('perf_exit_invalid')
        if valid:payload['status']='complete'
        else:raise cpu02.CPU02Error('perf_samples_unavailable')
    except Exception as exc:
        if perf is not None:
            payload.setdefault('perf',{})['exit_observed_before_cleanup']=getattr(
                perf.get('proc'),'poll',lambda:None)()
        payload['errors'].append(type(exc).__name__)
    finally:
        if perf is not None and not perf_stopped:
            try:
                payload['cleanup']['perf_stop_events']=cpu02.stop_perf(
                    perf,deadline=deadline,limit_s=15,
                    on_exhausted=lambda:payload.__setitem__('budget_overrun',True))
                perf_stopped=True
                perf_cleanup_confirmed=_perf_stop_confirmed(payload['cleanup']['perf_stop_events'])
                payload['cleanup']['perf_group_stop_confirmed']=perf_cleanup_confirmed
            except Exception as exc:
                payload['cleanup']['perf_stop_error']=type(exc).__name__
        if perf is not None and not perf_cleanup_confirmed:
            payload['status']='FAIL'
            payload.setdefault('cleanup',{})['perf_recovery']={
                'status':'unconfirmed','signal_policy':'no_privileged_signal_sent',
                'reason':'FIFO stop or ordinary process-group verification did not confirm removal'}
        elif perf is not None:
            payload.setdefault('cleanup',{})['perf_recovery']={
                'status':'confirmed','signal_policy':'fifo_stop_and_group_verification'}
        if perf is not None:
            for t in perf.get('drains') or []:
                try:t.join(timeout=max(0.0,min(1.0,deadline-time.monotonic())))
                except Exception:pass
            payload.setdefault('perf',{})['drain_complete']=all(
                not t.is_alive() for t in (perf.get('drains') or []))
            for stream in (getattr(perf.get('proc'),'stdout',None),
                           getattr(perf.get('proc'),'stderr',None)):
                if stream is not None:
                    try:stream.close()
                    except (OSError,ValueError):pass
            for key in ('ctl_fd','ack_fd'):
                if perf.get(key) is not None:
                    try:os.close(perf[key])
                    except OSError:pass
            payload.setdefault('perf',{})['exit_observed_after_cleanup']=getattr(
                perf.get('proc'),'poll',lambda:None)()
        if proc is not None:
            try:proc.stdin.close()
            except (OSError,ValueError):pass
            # A failed protocol must not spend the entire remaining budget
            # waiting for a worker that is deliberately blocked on input.
            if payload['status']!='complete' and proc.poll() is None:
                try:proc.kill()
                except (OSError,ProcessLookupError):pass
            try:
                proc.wait(timeout=cpu02.remaining(deadline,15));payload['cleanup']['worker']='reaped'
            except Exception:
                try:proc.kill();proc.wait(timeout=cpu02.remaining(deadline,15));payload['cleanup']['worker']='reaped_after_kill'
                except Exception:payload['cleanup']['worker']='reap_failed'
            try:proc.stdout.close()
            except (OSError,ValueError):pass
        if handle is not None:
            try:runtime.stop(handle,timeout_s=cpu02.remaining(deadline,15))
            except Exception as exc:payload['cleanup']['stop_error']=type(exc).__name__
            try:payload['cleanup']['container']=runtime.verify_removal(handle,timeout_s=cpu02.remaining(deadline,15))
            except Exception:payload['cleanup']['container']='check_failed'
            if payload['cleanup'].get('container')!='removed':payload['status']='FAIL'
        if payload['cleanup'].get('worker') not in ('reaped','reaped_after_kill'):payload['status']='FAIL'
        payload['wall_s']=time.monotonic()-started
        if time.monotonic()>deadline:payload['budget_overrun']=True;payload['status']='FAIL'
        try:pending=runtime.cleanup_pending(timeout_s=cpu02.remaining(deadline,15)) if hasattr(runtime,'cleanup_pending') else []
        except Exception:pending=[{'removed':False,'status':'not_checked'}]
        payload['cleanup']['pending']=pending
        if any(x.get('removed') is not True for x in pending):payload['status']='FAIL'
    payload['archive_status']='complete'
    payload['wall_s']=time.monotonic()-started
    if time.monotonic()>deadline:payload['budget_overrun']=True;payload['status']='FAIL'
    if perf is not None:
        _persist_perf_logs(output_dir,payload)
    manifest=_archive(output_dir,payload,identity)
    # Archive is part of the accounting boundary; late overrun must update all
    # disk-visible status and output hashes, not only the return value.
    payload['wall_s']=time.monotonic()-started
    if time.monotonic()>deadline:
        payload['budget_overrun']=True;payload['status']='FAIL'
    _rewrite_archive_state(output_dir,payload,identity,manifest['created_at_utc'])
    return payload


def main(argv=None):
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--execute',action='store_true')
    p.add_argument('--i-approve-the-cpu-02-permission-confirmation',action='store_true');a=p.parse_args(argv)
    if not a.execute and not a.i_approve_the_cpu_02_permission_confirmation:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (a.execute and a.i_approve_the_cpu_02_permission_confirmation):return 2
    try:
        identity=build_plan()['identity'];_verify_approval(identity)
        cpu02.guarded(ATTEMPT,new=True).parent.mkdir(parents=True,exist_ok=True)
        cpu02.write_json(ATTEMPT,{'status':'started','confirmation_id':CHECK_ID,'identity':identity,
            'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    except Exception as exc:print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+60;rc=5;detail='execution_failed'
    try:
        with local_docker_environment():
            pre=cpu02.docker_preflight(deadline=deadline)
            cpu02.write_json(cpu02.guarded(ROOT/'PREFLIGHT.json',new=True),pre)
            if pre.get('status')!='READY':detail='preflight_failed';rc=4
            else:
                run_id=CHECK_ID+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
                result=run_confirmation(RUNTIME_FACTORY(),ROOT/run_id,identity=identity,deadline=deadline,proc_root=PROC_ROOT,perf_factory=PERF_FACTORY)
                rc=0 if result['status']=='complete' and not result['budget_overrun'] else 5
                detail=result['status']
    except Exception as exc:detail=type(exc).__name__
    try:_finish_marker('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}));return rc


if __name__=='__main__':raise SystemExit(main())
