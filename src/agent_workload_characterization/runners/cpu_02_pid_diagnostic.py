"""CPU-02 PID mapping diagnostic preparation and one-shot entry.

The diagnostic has its own namespace and does not authorize or retry CPU-02.
It uses cpu_02_entry's mapping, guards and runtime lifecycle without changing
the three-way identity requirement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from . import cpu_02_entry as cpu02
from .container_runtime import ContainerSpec, DockerCliRuntime
from .g1_02_entry import local_docker_environment

PROJECT_ROOT=cpu02.PROJECT_ROOT
ROOT=PROJECT_ROOT/'reports/cpu/CPU-02/pid-diagnostic'
APPROVAL=ROOT/'APPROVAL.json'
ATTEMPT=ROOT/'ATTEMPT_STARTED.json'
DIAGNOSTIC_ID='CPU-02-PID-DIAGNOSTIC-01'
RUNTIME_FACTORY=lambda: DockerCliRuntime(authorized=True,collection=DIAGNOSTIC_ID)
LOCAL_ENVIRONMENT=local_docker_environment
PROC_ROOT=None


def _worker_command():
    code=("import json,os,time;"
          "s=open('/proc/self/stat').read().rsplit(')',1)[1].split();"
          "print(json.dumps({'event':'supervisor_ready','pid':os.getpid(),"
          "'starttime_ticks':int(s[19]),'pid_namespace':os.readlink('/proc/self/ns/pid')}),flush=True);"
          "input()")
    return 'python3 -u -c '+cpu02.shlex.quote(code)


def _host_proc_projection(pid):
    result={'pid':pid}
    try:
        status=(Path('/proc')/str(pid)/'status').read_text(encoding='ascii',errors='replace')
        nspid=next((line.split()[1:] for line in status.splitlines()
                    if line.startswith('NSpid:')),None)
        result['nspid']=nspid if nspid is not None else []
        result['nspid_read_status']='ok' if nspid is not None else 'missing'
    except OSError as exc:
        result['nspid_read_status']=cpu02.classify_proc_read_error('host_status',pid,exc)
    try:
        result['pid_namespace']=os.readlink(f'/proc/{pid}/ns/pid')
        result['pid_namespace_read_status']='ok'
    except OSError as exc:
        result['pid_namespace_read_status']=cpu02.classify_proc_read_error('host_ns',pid,exc)
    start=cpu02.read_starttime(pid)
    result['starttime_ticks']=start
    result['starttime_read_status']='ok' if start is not None else 'unavailable'
    return result


def _proc_mount_projection():
    try:
        lines=Path('/proc/mounts').read_text(encoding='ascii',errors='replace').splitlines()
        for line in lines:
            fields=line.split()
            if len(fields)>=4 and fields[1]=='/proc' and fields[2]=='proc':
                return {'filesystem':'proc','mountpoint':'/proc',
                        'options':sorted(set(fields[3].split(','))),
                        'read_status':'ok'}
    except OSError:
        pass
    return {'filesystem':'proc','mountpoint':'/proc','options':[],
            'read_status':'unknown'}


def build_plan():
    cfg=cpu02.load_config()
    base_identity=cpu02.build_plan()['identity']
    identity=json.loads(json.dumps(base_identity))
    identity.update(diagnostic_id=DIAGNOSTIC_ID,retry_id=None,
                    approval='reports/cpu/CPU-02/pid-diagnostic/APPROVAL.json')
    identity['collection']=DIAGNOSTIC_ID
    identity['config']['collection_id']=DIAGNOSTIC_ID
    identity['config']['limits']={'batch_wall_s':60,'cleanup_reserve_s':15,
                                  'container_cpu':1,'container_memory':'256m',
                                  'network':'none','pull':'never','retries':0}
    identity['config']['authorization']={'approval_path':identity['approval'],
                                         'attempt_path':'reports/cpu/CPU-02/pid-diagnostic/ATTEMPT_STARTED.json',
                                         'report_root':'reports/cpu/CPU-02/pid-diagnostic',
                                         'user_approval':'pending',
                                         'tool_execution_permission':'pending'}
    identity['diagnostic']={'worker':'one blocking owned Python process',
                            'mapping':'innermost_NSpid+pid_namespace+starttime',
                            'proc_projection':'whitelisted pid/NSpid/ns/pid/starttime/mount options only'}
    return dict(task='CPU-02',mode='plan_only',diagnostic_id=DIAGNOSTIC_ID,
                identity=identity,
                b_command=(f'PYTHONPATH=src {cpu02.shlex.quote(str(cpu02.VENV_PYTHON))} -B '
                           '-m agent_workload_characterization.runners.cpu_02_pid_diagnostic '
                           '--execute --i-approve-the-cpu-02-pid-diagnostic'),
                authorization={'user_approval':'pending','tool_execution_permission':'pending'},
                limits=identity['config']['limits'])


def _verify_approval(identity):
    record=json.loads(cpu02.guarded(APPROVAL).read_text())
    if (record.get('checklist_identity')!=identity or record.get('approved') is not True
            or not record.get('approved_by') or not record.get('approved_at_utc')):
        raise cpu02.CPU02Error('diagnostic_approval_identity_or_user_record')


def _finish(status,detail):
    path=cpu02.guarded(ATTEMPT);record=json.loads(path.read_text())
    record.update(status=status,detail=detail)
    tmp=path.with_name('ATTEMPT_FINISH-'+uuid.uuid4().hex+'.json')
    cpu02.write_json(tmp,record);os.replace(tmp,path)


def run_diagnostic(runtime,output_dir,*,identity,deadline,proc_root=None):
    started=time.monotonic()
    output_dir=cpu02.guarded(output_dir,new=True)
    output_dir.mkdir(parents=True)
    payload={'run_id':output_dir.name,'diagnostic_id':DIAGNOSTIC_ID,
             'status':'pending','archive_status':'pending','errors':[],
             'budget_overrun':False,'wall_cutoff':'after_final_archive_write',
             'identity':identity,'cleanup':{},'proc_projection':_proc_mount_projection(),
             'diagnostic_process':_host_proc_projection(os.getpid())}
    handle=proc=None
    work_deadline=deadline-15
    try:
        spec=ContainerSpec(output_dir.name,'cpu02-pid-diagnostic',identity['image'],
                           cpu_limit='1',mem_limit='256m',network='none',
                           pull='never',platform='linux/arm64')
        handle=runtime.start(spec,timeout_s=cpu02.remaining(work_deadline,15))
        payload['container_id']=handle.container_id
        proc=runtime.open_interactive(handle,_worker_command(),
                                      cpu02.remaining(work_deadline,15))
        ready=cpu02.read_supervisor_ready(proc,cpu02.remaining(work_deadline,15))
        payload['worker']=ready
        if ready['status']!='ok':raise cpu02.CPU02Error('diagnostic_worker_not_ready')
        init=runtime.container_init_pid(handle,timeout_s=cpu02.remaining(work_deadline,15))
        payload['container_init_pid']=init
        if not init:raise cpu02.CPU02Error('container_init_pid_unavailable')
        payload['host_init_proc']=_host_proc_projection(init)
        mapping=cpu02.map_container_pid(ready['container_pid'],ready['starttime_ticks'],init,
                                        proc_root=proc_root)
        payload['mapping']=mapping
        if mapping['status']!='ok':raise cpu02.CPU02Error('pid_mapping_failed')
        payload['status']='complete'
    except Exception as exc:
        payload['status']='FAIL';payload['errors'].append(type(exc).__name__)
    finally:
        if proc is not None:
            try:proc.stdin.close()
            except (OSError,ValueError):pass
            try:
                proc.wait(timeout=cpu02.remaining(deadline,15))
                payload['cleanup']['worker']='reaped'
            except Exception:
                payload['cleanup']['worker']='reap_failed'
                try:proc.kill()
                except (OSError,ValueError):pass
                try:
                    proc.wait(timeout=cpu02.remaining(deadline,15))
                    payload['cleanup']['worker']='reaped_after_kill'
                except Exception:pass
            for stream in (proc.stdout,proc.stderr):
                if stream is not None:
                    try:stream.close()
                    except (OSError,ValueError):pass
        if handle is not None:
            try:runtime.stop(handle,timeout_s=cpu02.remaining(deadline,15))
            except Exception as exc:payload['cleanup']['stop_error']=type(exc).__name__
            try:payload['cleanup']['container']=runtime.verify_removal(
                handle,timeout_s=cpu02.remaining(deadline,15))
            except Exception as exc:payload['cleanup']['container']='check_failed'
        try:
            pending=runtime.cleanup_pending(timeout_s=cpu02.remaining(deadline,15)) \
                if hasattr(runtime,'cleanup_pending') else []
            payload['cleanup']['pending']=pending
        except Exception as exc:
            payload['cleanup']['pending_error']=type(exc).__name__
            payload['cleanup']['pending']=[{'removed':False,'status':'not_checked'}]
        if payload['cleanup'].get('worker') not in ('reaped','reaped_after_kill'):
            payload['status']='FAIL'
        if payload['cleanup'].get('container')!='removed':payload['status']='FAIL'
        if any(p.get('removed') is not True for p in payload['cleanup'].get('pending',[])):
            payload['status']='FAIL'
    # Archive is part of the batch deadline.  Write a provisional state,
    # re-check after the manifest write, then rewrite both files together if
    # archiving itself consumed the remaining budget.  The manifest never
    # includes its own hash, but always describes the final summary bytes.
    payload['archive_status']='complete'
    summary=output_dir/'summary.json';manifest_path=output_dir/'manifest.json'
    created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    for attempt in range(3):
        now=time.monotonic()
        if now>deadline:
            payload['budget_overrun']=True;payload['status']='FAIL'
        payload['wall_s']=now-started
        if summary.exists():cpu02.rewrite_json(summary,payload)
        else:cpu02.write_json(summary,payload)
        manifest={'identity':identity,'created_at_utc':created_at,
                  'status':payload['status'],'outputs':{
                  str(summary.relative_to(output_dir)):
                  {'bytes':summary.stat().st_size,
                   'sha256':hashlib.sha256(summary.read_bytes()).hexdigest()}}}
        if manifest_path.exists():cpu02.rewrite_json(manifest_path,manifest)
        else:cpu02.write_json(manifest_path,manifest)
        after=time.monotonic()
        if after<=deadline:
            break
        payload['budget_overrun']=True;payload['status']='FAIL'
    # The last pass above synchronizes the final failure state to disk.  Keep
    # the reported cutoff explicit: it is after the final archive write.
    payload['wall_s']=time.monotonic()-started
    if time.monotonic()>deadline:
        payload['budget_overrun']=True;payload['status']='FAIL'
        cpu02.rewrite_json(summary,payload)
        manifest['status']=payload['status']
        manifest['outputs'][str(summary.relative_to(output_dir))]={
            'bytes':summary.stat().st_size,
            'sha256':hashlib.sha256(summary.read_bytes()).hexdigest()}
        cpu02.rewrite_json(manifest_path,manifest)
    return payload


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--i-approve-the-cpu-02-pid-diagnostic',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_cpu_02_pid_diagnostic:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (args.execute and args.i_approve_the_cpu_02_pid_diagnostic):return 2
    try:
        identity=build_plan()['identity'];_verify_approval(identity)
        cpu02.guarded(ATTEMPT,new=True).parent.mkdir(parents=True,exist_ok=True)
        cpu02.write_json(ATTEMPT,{'status':'started','diagnostic_id':DIAGNOSTIC_ID,
                                  'identity':identity,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    except Exception as exc:
        print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+60;work_deadline=deadline-15;rc=5;detail='execution_failed'
    try:
        with LOCAL_ENVIRONMENT():
            preflight=cpu02.docker_preflight(deadline=work_deadline)
            cpu02.write_json(cpu02.guarded(ROOT/'PREFLIGHT.json',new=True),preflight)
            if preflight.get('status')!='READY':rc,detail=4,'preflight_failed'
            else:
                plan=build_plan();run_id=DIAGNOSTIC_ID+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
                result=run_diagnostic(RUNTIME_FACTORY(),ROOT/run_id,identity=plan['identity'],
                                      deadline=deadline,proc_root=PROC_ROOT)
                rc=0 if result['status']=='complete' and result['archive_status']=='complete' else 5
                detail='mapping_'+(result.get('mapping') or {}).get('status','absent')
    except Exception as exc:detail=type(exc).__name__
    try:_finish('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}));return rc


if __name__=='__main__':raise SystemExit(main())
