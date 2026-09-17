"""G1-02 single production entry. Default plan never probes Docker.

Tests inject only runtime/preflight and a small, separately identified catalog.
No alternative synthetic controller, no model or credential path.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time
import uuid

from ..collectors.resource_sampler import ResourceSampler, ScopeReader
from .container_runtime import ContainerSpec, DockerCliRuntime
from .report_writer import guard_resource_report, guard_resource_root, _catalog_protected_roots

PROJECT_ROOT=Path(__file__).resolve().parents[3]
CODE_ROOT=PROJECT_ROOT
CATALOG=PROJECT_ROOT/'workload_catalog/g1_02.yaml'
WORKER=PROJECT_ROOT/'scripts/g1_02_worker.py'
CONTROLLER=PROJECT_ROOT/'scripts/g1_02_controller.py'
APPROVAL=PROJECT_ROOT/'reports/resource/G1-02/APPROVAL.json'
ATTEMPT=PROJECT_ROOT/'reports/resource/G1-02/ATTEMPT_STARTED.json'
IMAGE='swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2'


class G102Error(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config():
    import yaml
    cfg=yaml.safe_load(CATALOG.read_text())
    if not isinstance(cfg,dict) or cfg.get('execution_authorized') is not False:
        raise G102Error('catalog_not_offline_registered')
    for group,key in [('workload','work_iterations'),('workload','service_iterations'),
                      ('measurement','sampling_interval_s'),('comparison','minimum_worker_cpu_s'),
                      ('comparison','minimum_samples_per_interval'),('comparison','boundary_read_max_s')]:
        value=cfg[group][key]
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise G102Error('invalid_measurement_config')
    for key in ('work_iterations','service_iterations'):
        if type(cfg['workload'][key]) is not int:raise G102Error('iterations_not_integer')
    lim=cfg['limits']
    for key,maximum in {'batch_wall_s':300,'cleanup_reserve_s':30,'operation_s':15,
                        'work_interval_s':8,'report_threshold_mib':20,
                        'max_containers':2,'per_container_cpu':2}.items():
        v=lim[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=maximum:raise G102Error('invalid_budget')
    if (lim['cleanup_reserve_s']>=lim['batch_wall_s'] or lim['max_containers']!=2 or
        lim['network']!='none' or lim['pull']!='never' or lim['per_container_memory']!='256MiB' or lim['retries']!=0):
        raise G102Error('invalid_isolation_or_budget')
    order=cfg['comparison']['order']
    if order!=['OFF','ON','ON','OFF','OFF','ON','ON','OFF','OFF','ON','ON','OFF'] or cfg['comparison']['pairs']!=6:
        raise G102Error('invalid_pair_design')
    return cfg


def build_plan():
    cfg=load_config()
    paths=sorted((CODE_ROOT/'src/agent_workload_characterization').rglob('*.py'))+[WORKER,CONTROLLER]
    identity=dict(catalog_sha256=sha(CATALOG),config=cfg,image=IMAGE,
        code_sha256={str(p.relative_to(CODE_ROOT)):sha(p) for p in paths},
        interpreter={'path':str(Path(sys.executable).resolve()),'version':sys.version.split()[0]},
        collection='G1-02',approval='reports/resource/G1-02/APPROVAL.json')
    return dict(task='G1-02',mode='plan_only',identity=identity,
        b_command=f'PYTHONPATH=src {shlex.quote(str(Path(sys.executable).resolve()))} -B -m agent_workload_characterization.runners.g1_02_entry --execute --i-approve-the-g1-02-b',
        authorization={'user_approval':'pending','tool_execution_permission':'pending'},
        limits=cfg['limits'])


def guarded(path, *, new=False):
    root=guard_resource_root(PROJECT_ROOT,'G1-02')
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if '..' in path.parts or not path.is_relative_to(root):raise G102Error('output_outside_namespace')
    current=PROJECT_ROOT.resolve()
    for part in path.relative_to(current).parts:
        current=current/part
        if current.is_symlink():raise G102Error('output_symlink')
    real=path.resolve()
    for p in [PROJECT_ROOT/'references',PROJECT_ROOT/'data/raw',*_catalog_protected_roots(PROJECT_ROOT)]:
        p=p.resolve()
        if real==p or real.is_relative_to(p) or p.is_relative_to(real):raise G102Error('protected_output')
    if new and path.exists():raise G102Error('output_exists')
    return path


def write_json(path,payload):
    guarded(path,new=True)
    with Path(path).open('x',encoding='utf-8') as fh:
        json.dump(payload,fh,indent=2,allow_nan=False);fh.write('\n')


def verify_approval(path,identity=None):
    path=guarded(path)
    if path!=APPROVAL:raise G102Error('approval_wrong_namespace')
    record=json.loads(path.read_text())
    if (record.get('checklist_identity')!=(identity or build_plan()['identity']) or
        record.get('approved') is not True or not record.get('approved_by') or not record.get('approved_at_utc')):
        raise G102Error('approval_identity_or_user_record')
    return record


def register_attempt(identity):
    guarded(ATTEMPT,new=True).parent.mkdir(parents=True,exist_ok=True)
    write_json(ATTEMPT,dict(status='started',identity=identity,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))


def finish_marker(status,detail):
    path=guarded(ATTEMPT);record=json.loads(path.read_text())
    record.update(status=status,detail=detail)
    tmp=path.with_name('ATTEMPT_FINISH-'+uuid.uuid4().hex+'.json')
    write_json(tmp,record);os.replace(tmp,path)


@contextlib.contextmanager
def local_docker_environment():
    # Only inspect/restore selected routing keys; no credential lookup.
    keys=('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH',
          'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')
    saved={k:os.environ.get(k) for k in keys}
    try:
        for k in keys:os.environ.pop(k,None)
        os.environ['DOCKER_HOST']='unix:///var/run/docker.sock'
        yield
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def remaining(deadline, ceiling):
    rem=min(ceiling,deadline-time.monotonic())
    if rem<=0:raise G102Error('budget_exhausted')
    return rem


def docker_preflight(*, deadline, runner=None):
    runner=runner or subprocess.run
    checks={}
    for name,args in [('context',['context','show']),('image',['image','inspect',IMAGE,'--format','{{.Os}}/{{.Architecture}}'])]:
        try:
            proc=runner(['docker',*args],capture_output=True,text=True,timeout=remaining(deadline,15))
            checks[name]=proc.returncode==0 and proc.stdout.strip()==('default' if name=='context' else 'linux/arm64')
        except Exception as exc:
            return dict(status='NOT_READY',checks=checks,category=type(exc).__name__)
        if not checks[name]:return dict(status='NOT_READY',checks=checks,category=name+'_unverified')
    return dict(status='READY',checks=checks,endpoint='unix:///var/run/docker.sock',image=IMAGE)


def worker_command(run_id):
    # shlex, not Python repr as shell quoting. Only owned source enters container.
    source=WORKER.read_text()
    program='ns={"__name__":"owned_worker"};exec('+repr(source)+',ns);ns["main"]('+repr(run_id)+')'
    return 'python3 -u -c '+shlex.quote(program)


class ContainerReader(ScopeReader):
    def __init__(self,runtime,handle,scope):self.runtime,self.handle,self.scope=runtime,handle,scope
    def read(self,t):
        start=time.monotonic_ns();snap=self.runtime.read_counters(self.handle,t)
        snap.scope=self.scope;snap.scope_kind='agent_container'
        snap.read_status['read_latency_s']=str((time.monotonic_ns()-start)/1e9)
        return snap


def run_runtime_batch(runtime,output_dir,*,config=None,deadline=None,run_id=None,identity=None,preflight=None):
    config=copy.deepcopy(config or load_config());lim=config['limits']
    deadline=deadline if deadline is not None else time.monotonic()+lim['batch_wall_s']
    work_deadline=deadline-lim['cleanup_reserve_s']
    output_dir=guarded(output_dir,new=True)
    guard_resource_report(PROJECT_ROOT,output_dir,'G1-02');output_dir.mkdir(parents=True)
    run_id=run_id or 'G1-02-'+uuid.uuid4().hex
    payload=dict(run_id=run_id,status='FAIL',cases=[],cleanup=[],preflight=preflight,errors=[],
                 comparison={'sufficiency':'not_applicable'},budget_overrun=False)
    payload['clock_anchor']={'monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),
        'domain':'same_host_CLOCK_MONOTONIC','assumption':'native Docker without separate time namespace'}
    controller=runpy.run_path(str(CONTROLLER))['run_controller']
    def bytes_now():return sum(p.stat().st_size for p in output_dir.rglob('*') if p.is_file())
    def check():
        if bytes_now()>lim['report_threshold_mib']*2**20:raise G102Error('report_threshold_exceeded')
        remaining(work_deadline,lim['operation_s'])
    def cleanup_timeout():
        rem=deadline-time.monotonic()
        if rem<=0:
            payload['budget_overrun']=True
            return .1  # bounded best-effort safety cleanup, never a success.
        return min(lim['operation_s'],rem)
    try:
        for case in ('service','overhead'):
            handle=None;proc=None;row={'case':case,'status':'FAIL'}
            payload['cases'].append(row)
            try:
                check()
                spec=ContainerSpec(run_id,case,IMAGE,cpu_limit=str(lim['per_container_cpu']),mem_limit='256m',
                    network='none',pull='never',platform='linux/arm64')
                handle=runtime.start(spec,timeout_s=remaining(work_deadline,lim['operation_s']))
                row['container_id']=handle.container_id
                proc=runtime.open_interactive(handle,worker_command(run_id),remaining(work_deadline,lim['operation_s']))
                def sampler_factory(scope):
                    sampler=ResourceSampler(interval_s=config['measurement']['sampling_interval_s'])
                    sampler.register(scope,'agent_container',ContainerReader(runtime,handle,scope))
                    return sampler
                result=controller(proc=proc,case=case,config=config,deadline=work_deadline,
                    sampler_factory=sampler_factory,events_path=output_dir/(case+'.events.jsonl'),
                    hook_path=output_dir/(case+'.tool_events.jsonl'),check=check,run_id=run_id)
                row['evidence']=result;row['status']=result['status']
                if case=='overhead':payload['comparison']=result['comparison']
            except Exception as exc:
                row['error']=type(exc).__name__
            finally:
                # Persist measured boundaries before container deletion. A
                # writer error must never bypass the independent cleanup below.
                try:
                    evidence=row.get('evidence')
                    if evidence is not None:
                        encoded_size=len(json.dumps(evidence).encode())
                        if bytes_now()+encoded_size>lim['report_threshold_mib']*2**20:
                            row['status']='FAIL'
                            row['evidence_archive']='threshold_exceeded; protocol stream retained'
                        else:
                            write_json(output_dir/(case+'.evidence.json'),evidence)
                            row['evidence_archive']=case+'.evidence.json'
                except Exception as exc:
                    row['evidence_archive_error']=type(exc).__name__;row['status']='FAIL'
                if proc is not None:
                    try:
                        if proc.poll() is None:proc.kill();proc.wait(timeout=cleanup_timeout())
                        proc.stdin.close();proc.stdout.close()
                    except Exception as exc:row['process_cleanup_error']=type(exc).__name__;row['status']='FAIL'
                if handle is not None:
                    try:runtime.stop(handle,timeout_s=cleanup_timeout())
                    except Exception as exc:row['stop_error']=type(exc).__name__
                    try:row['cleanup']=runtime.verify_removal(handle,timeout_s=cleanup_timeout())
                    except Exception:row['cleanup']='check_failed'
                else:row['cleanup']='not_started'
                # Production registers names before create, including lost responses.
                try:
                    pending=runtime.cleanup_pending(timeout_s=cleanup_timeout()) if hasattr(runtime,'cleanup_pending') else []
                    payload['cleanup'].extend(pending)
                    if any(p.get('removed') is not True for p in pending):row['status']='FAIL'
                except Exception as exc:row['pending_cleanup_error']=type(exc).__name__;row['status']='FAIL'
            if row['status']!='PASS' or row['cleanup']!='removed' or 'stop_error' in row:break
        if len(payload['cases'])==2 and all(r['status']=='PASS' and r['cleanup']=='removed' and 'stop_error' not in r for r in payload['cases']):
            payload['status']='PASS'
    except Exception as exc:payload['errors'].append(type(exc).__name__)
    payload['budget_overrun'] |= time.monotonic()>deadline
    if payload['budget_overrun']:payload['status']='FAIL'
    payload['wall_s']=lim['batch_wall_s']-(deadline-time.monotonic())
    if bytes_now()>lim['report_threshold_mib']*2**20:
        payload['status']='FAIL';payload['report_threshold_exceeded']=True
    try:
        payload['archive_status']='complete'
        projected=bytes_now()+len(json.dumps(payload,indent=2).encode())
        if projected>lim['report_threshold_mib']*2**20:
            payload['status']='FAIL';payload['report_threshold_exceeded']=True
            # Keep stream files, but don't duplicate large evidence into summary.
            for row in payload['cases']:
                if 'evidence' in row:
                    row['evidence_omitted']='report_threshold; raw protocol streams retained'
                    del row['evidence']
        write_json(output_dir/'summary.json',payload)
        outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in output_dir.rglob('*') if p.is_file()}
        manifest=dict(identity=identity or build_plan()['identity'],outputs=outputs,
                      created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),status=payload['status'])
        write_json(output_dir/'manifest.json',manifest)
        actual=json.loads((output_dir/'manifest.json').read_text())['outputs']
        if actual!=outputs or any(sha(output_dir/p)!=v['sha256'] or (output_dir/p).stat().st_size!=v['bytes'] for p,v in actual.items()):raise G102Error('archive_hash_mismatch')
        payload['archive_status']='complete'
    except Exception as exc:
        payload.update(status='FAIL',archive_status='failed');payload['errors'].append(type(exc).__name__)
        try:write_json(output_dir/'archive_failure.json',{'status':'FAIL','category':type(exc).__name__})
        except Exception:pass  # Return code and attempt marker remain non-success.
    return payload


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--i-approve-the-g1-02-b',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_g1_02_b:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (args.execute and args.i_approve_the_g1_02_b):return 2
    try:
        plan=build_plan();identity=plan['identity']
        verify_approval(APPROVAL,identity);register_attempt(identity)
    except Exception as exc:
        print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+plan['limits']['batch_wall_s']
    rc=5;detail='execution_failed'
    try:
        with local_docker_environment():
            preflight=docker_preflight(deadline=deadline-plan['limits']['cleanup_reserve_s'])
            write_json(guarded(APPROVAL.parent/'PREFLIGHT.json',new=True),preflight)
            if preflight['status']!='READY':rc=4;detail='preflight_failed'
            else:
                batch='G1-02-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
                result=run_runtime_batch(DockerCliRuntime(authorized=True,collection='G1-02'),
                    APPROVAL.parent/batch,config=identity['config'],deadline=deadline,run_id=batch,
                    identity=identity,preflight=preflight)
                rc=0 if result['status']=='PASS' and result['archive_status']=='complete' else 5
                detail='mechanism_'+result['status']+'_comparison_'+result['comparison']['sufficiency']
    except Exception as exc:detail=type(exc).__name__
    try:finish_marker('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
