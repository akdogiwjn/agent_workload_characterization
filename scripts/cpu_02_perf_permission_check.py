#!/usr/bin/env python3
"""Prepare/run one manual ordinary-user perf permission check.

This thin entry supplies only the privileged init-namespace read required by
the existing CPU-02 confirmation chain.  Docker, perf, and Python remain
ordinary-user operations; the default mode has no external side effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import time
import uuid

from agent_workload_characterization.runners import cpu_02_entry as cpu02
from agent_workload_characterization.runners import cpu_02_permission_confirmation as base
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
from agent_workload_characterization.runners.g1_02_entry import local_docker_environment

PROJECT_ROOT = cpu02.PROJECT_ROOT
ROOT = PROJECT_ROOT / 'reports/cpu/CPU-02/perf-permission-check'
CHECK_ID = 'CPU-02-PERF-PERMISSION-CHECK-01'
IMAGE = base.build_plan()['identity']['image']
WORK_SECONDS = 1.0
TOTAL_S = 60.0
CLEANUP_RESERVE_S = 15.0
MAX_CANDIDATE_SUDO_READS = 1


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_plan():
    identity=json.loads(json.dumps(base.build_plan()['identity']))
    identity.update(confirmation_id=CHECK_ID,
                    approval='manual-user-confirmation-not-an-execution-approval')
    identity['confirmation_entry']={
        'path':str(Path(__file__).relative_to(PROJECT_ROOT)),
        'sha256':_sha(__file__),
        'protocol':'ready -> release -> bounded_cpu -> done -> perf_report',
        'same_pid':True,
        'namespace_read':'ordinary_proc_scan_plus_sudo_readlink_of_validated_init_pid'}
    identity['config']['permission_check']={
        'container_count':1,'cpu':'1','memory':'256m','network':'none','pull':'never',
        'batch_wall_s':TOTAL_S,'cleanup_reserve_s':CLEANUP_RESERVE_S,
        'worker_seconds':WORK_SECONDS,'sample_max_s':5.0,
        'endpoint':'unix:///var/run/docker.sock',
        'candidate_sudo_read_limit':MAX_CANDIDATE_SUDO_READS,
        'candidate_sudo_trigger':'ordinary candidate namespace read EACCES or EPERM only',
        'perf_record_sudo':True,
        'perf_record_sudo_trigger':'after identity checks; fixed /usr/bin/perf record only',
        'perf_record_sudo_stop':'ordinary-user FIFO stop and process-group verification only'}
    return {'task':'CPU-02','mode':'plan_only','check_id':CHECK_ID,
            'identity':identity,
            'command':('PYTHONPATH=src '+str(cpu02.VENV_PYTHON)+
              ' -B scripts/cpu_02_perf_permission_check.py --execute'),
            'sudo_allowlist':[
                {'role':'init_namespace','argv':'sudo --non-interactive -- /usr/bin/readlink /proc/<validated_init_pid>/ns/pid','trigger':'validated positive init PID','max_calls':1},
                {'role':'worker_candidate_namespace','argv':'sudo --non-interactive -- /usr/bin/readlink /proc/<validated_candidate_pid>/ns/pid','trigger':'ordinary candidate read EACCES or EPERM after NSpid/starttime match','max_calls':MAX_CANDIDATE_SUDO_READS},
                {'role':'perf_record','argv':'sudo --non-interactive -- /usr/bin/perf record -D -1 -F 99 -e cycles -p <validated_host_pid> -o <user_owned_perf_data> --control fifo:<user_owned_ctl>,<user_owned_ack>','trigger':'all identity checks passed; ordinary perf attach denied','max_calls':1,'stop':'ordinary-user FIFO stop only; no sudo kill or sudo shell'}],
            'authorization':{'user_approval':'pending','tool_execution_permission':'pending'}}


def _sudo_init_namespace(pid, *, runner=subprocess.run, deadline):
    if type(pid) is not int or pid <= 0:
        raise cpu02.CPU02Error('invalid_validated_init_pid')
    argv=['sudo','--non-interactive','--','/usr/bin/readlink',f'/proc/{pid}/ns/pid']
    try:
        proc=runner(argv,capture_output=True,text=True,
                    timeout=cpu02.remaining(deadline,5.0))
    except subprocess.TimeoutExpired:
        raise cpu02.CPU02Error('sudo_namespace_timeout')
    except OSError as exc:
        if getattr(exc,'errno',None) in (1,13):
            raise cpu02.CPU02Error('sudo_namespace_permission_denied')
        raise cpu02.CPU02Error('sudo_namespace_unknown')
    if proc.returncode != 0:
        raise cpu02.CPU02Error('sudo_namespace_read_failed')
    value=(proc.stdout or '').strip()
    if not (value.startswith('pid:[') and value.endswith(']')):
        raise cpu02.CPU02Error('sudo_namespace_invalid_output')
    return value


def _proc_identity(proc_root, pid, container_pid=None):
    root=Path(proc_root or '/proc')
    status=(root/str(pid)/'status').read_text(encoding='ascii',errors='replace')
    nspid=next((line.split()[1:] for line in status.splitlines()
                if line.startswith('NSpid:')),None)
    if not nspid or (container_pid is not None and nspid[-1]!=str(container_pid)):
        raise cpu02.CPU02Error('candidate_nspid_changed_or_invalid')
    stat=(root/str(pid)/'stat').read_text(encoding='ascii',errors='replace')
    starttime=int(stat.rsplit(')',1)[1].split()[19])
    return {'nspid':nspid,'starttime_ticks':starttime}


def run_once(*, runtime, output_dir, deadline, sudo_reader=_sudo_init_namespace,
             proc_root=None, perf_factory=None, report_runner=None):
    init_identity={}
    candidate_sudo_calls=0
    work_deadline=deadline-CLEANUP_RESERVE_S
    def read_init(pid, *, deadline):
        before=_proc_identity(proc_root,pid,container_pid=None)
        value=sudo_reader(pid,deadline=min(work_deadline,time.monotonic()+15.0))
        after=_proc_identity(proc_root,pid,container_pid=None)
        if before['starttime_ticks']!=after['starttime_ticks']:
            raise cpu02.CPU02Error('init_identity_changed')
        init_identity.update(before)
        return value

    def read_candidate(host_pid, container_pid, expected_starttime):
        nonlocal candidate_sudo_calls
        base_event['pid']=container_pid
        before=_proc_identity(proc_root,host_pid,container_pid)
        if before['starttime_ticks']!=expected_starttime:
            raise cpu02.CPU02Error('candidate_starttime_changed')
        if candidate_sudo_calls>=MAX_CANDIDATE_SUDO_READS:
            raise cpu02.CPU02Error('candidate_sudo_call_limit')
        candidate_sudo_calls+=1
        value=sudo_reader(host_pid,deadline=min(work_deadline,time.monotonic()+5.0))
        after=_proc_identity(proc_root,host_pid,container_pid)
        if after!=before:
            raise cpu02.CPU02Error('candidate_identity_changed')
        return value

    def validate_mapping(mapping, init, handle, initial_container_id):
        current_init=_proc_identity(proc_root,init,container_pid=None)
        if current_init!=init_identity:
            raise cpu02.CPU02Error('init_identity_changed_after_mapping')
        current_candidate=_proc_identity(proc_root,mapping['host_pid'],
                                         container_pid=mapping['container_pid'])
        if current_candidate['starttime_ticks']!=mapping['starttime_ticks']:
            raise cpu02.CPU02Error('candidate_identity_changed_after_mapping')
        if runtime.container_init_pid(handle,timeout_s=cpu02.remaining(work_deadline,5))!=init:
            raise cpu02.CPU02Error('container_init_pid_changed_after_mapping')
        if handle.container_id != initial_container_id:
            raise cpu02.CPU02Error('container_id_changed_after_mapping')
        if not handle.container_id:
            raise cpu02.CPU02Error('container_id_missing_after_mapping')

    base_event={}
    # The validator closes over the identities captured immediately around the
    # sudo reads; the event is filled before the shared mapper is entered.
    original_read_candidate=read_candidate
    def read_candidate_checked(host_pid, container_pid, expected_starttime):
        value=original_read_candidate(host_pid,container_pid,expected_starttime)
        return value
    read_candidate=read_candidate_checked
    def read_init_checked(pid, *, deadline):
        value=read_init(pid,deadline=deadline)
        return value

    return base.run_confirmation(runtime,output_dir,identity=build_plan()['identity'],
        deadline=deadline,work_seconds=WORK_SECONDS,
        init_namespace_reader=read_init_checked, candidate_namespace_reader=read_candidate,
        mapping_post_validator=validate_mapping,
        proc_root=proc_root,perf_factory=perf_factory,report_runner=report_runner,
        perf_sudo=True)


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(build_plan(),indent=2)); return 0
    started=time.monotonic(); deadline=started+TOTAL_S
    run_id=CHECK_ID+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    output=ROOT/run_id
    result={'run_id':run_id,'status':'FAIL','errors':[],'execution_identity':{
        'uid':os.getuid(),'gid':os.getgid()}}
    try:
        with local_docker_environment():
            pre=cpu02.docker_preflight(deadline=deadline,image=IMAGE)
            result['preflight']=pre
            if pre.get('status')!='READY':
                result['errors'].append('preflight_failed')
            else:
                result.update(run_once(runtime=DockerCliRuntime(authorized=True,collection=CHECK_ID),
                                       output_dir=output,deadline=deadline))
    except Exception as exc:
        result['errors'].append(type(exc).__name__)
        result['status']='FAIL'
    result['wall_s']=time.monotonic()-started
    result['budget_overrun']=result['wall_s']>TOTAL_S
    if result['budget_overrun']: result['status']='FAIL'
    print(json.dumps(result,sort_keys=True))
    return 0 if result.get('status')=='complete' and not result['budget_overrun'] else 5


if __name__=='__main__':
    raise SystemExit(main())
