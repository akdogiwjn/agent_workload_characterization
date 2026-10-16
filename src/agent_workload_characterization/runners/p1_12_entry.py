"""P1-12 pilot batch entry: 3 SWE-bench Verified tasks x 3 controlled repeats.

Thin batch coordinator over the EXISTING CodingPilotRunner chain (shared
harness/verifier/runtime/sampler/archive); no second runner framework. Each
attempt binds one task's record/image/verifier spec; per-attempt run
directories are independent; the agent container is removed and verified
before the verifier starts (runner semantics). The batch enforces ONE
shared wall deadline that is propagated INTO every attempt's budget
(remaining work time, cleanup reserve preserved), a pre-registered block
order, and the registered failure policy: resolved=false / no_candidate are
task results, infrastructure / budget / cleanup / archive failures stop the
batch with remaining attempts recorded as not_executed.

Gates are real: preflight requires FULL image digests (repo@sha256:<64hex>)
and an enforced monetary budget or pilot-specific risk acceptance;
a missing digest or unsatisfied monetary gate yields NOT READY
and main() refuses to execute — identical to the plan-mode readiness.
Production wiring reuses the RUN-02-R2-proven
fixed local Docker endpoint / proxy isolation and official DeepSeek credential
resolution, executed only after preflight passes. Default plan mode has
zero side effects; execution requires BOTH flags AND a real approval bound
to the live identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import sys
import time
import uuid

from .report_writer import guard_resource_root, guard_resource_report, _catalog_protected_roots

PROJECT_ROOT=Path(__file__).resolve().parents[3]
CODE_ROOT=PROJECT_ROOT
CATALOG=PROJECT_ROOT/'workload_catalog/p1_12_deepseek_official.yaml'
APPROVAL=PROJECT_ROOT/'reports/resource/P1-12/APPROVAL.json'
ATTEMPT=PROJECT_ROOT/'reports/resource/P1-12/ATTEMPT_STARTED.json'
MINI_VENV_PY=PROJECT_ROOT/'.venvs/mini-swe-agent-2.4.6-env01/bin/python'
EVAL_VENV_PY=PROJECT_ROOT/'.venvs/swebench-eval-02e7a74/bin/python'
DIGEST_RE=re.compile(r'^[^@\s]+@sha256:[0-9a-f]{64}$')


class P112Error(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_is_full(value):
    """A usable image identity is repo@sha256:<64 hex>. Anything else —
    None, a tag, a truncated digest, a placeholder — is NOT."""
    return bool(value) and bool(DIGEST_RE.match(value))


def load_config():
    import yaml
    cfg=yaml.safe_load(CATALOG.read_text())
    if not isinstance(cfg,dict) or cfg.get('execution_authorized') is not False:
        raise P112Error('catalog_not_offline_registered')
    tasks=cfg.get('tasks') or []
    if len(tasks)!=3 or len({t['instance_id'] for t in tasks})!=3:
        raise P112Error('invalid_task_set')
    for t in tasks:
        record=PROJECT_ROOT/t['record_locator']
        if not record.is_file():raise P112Error('record_missing:'+t['instance_id'])
        if sha(record)!=t['record_sha256']:
            raise P112Error('record_hash_drift:'+t['instance_id'])
    d=cfg['design']
    if d['rounds']!=3 or d['repeats_per_task']!=3 or not isinstance(d['block_seed'],int):
        raise P112Error('invalid_design')
    ba=cfg['budget_per_attempt']
    for key in ('max_model_requests','max_steps','max_output_tokens_per_request'):
        if type(ba[key]) is not int or ba[key]<=0:raise P112Error('invalid_attempt_budget')
    for key in ('agent_wall_min','verifier_wall_min','total_wall_min','max_new_artifact_bytes_gib'):
        v=ba[key]
        if type(v) not in (int,float) or not math.isfinite(v) or v<=0:
            raise P112Error('invalid_attempt_budget')
    bb=cfg['budget_batch']
    if type(bb['batch_wall_min']) not in (int,float) or bb['batch_wall_min']<=0:
        raise P112Error('invalid_batch_budget')
    if bb['batch_wall_min']<9*ba['total_wall_min']:
        raise P112Error('batch_budget_below_planned_attempts')
    return cfg


def monetary_bound(cfg):
    """Report a planning estimate; never turn it into a spend guarantee.

    The registered input cap is not enforced by the current execution chain,
    so even a numerically conservative estimate cannot close the monetary
    readiness gate.  Configuration labels such as ``closed`` or
    ``enforced`` are metadata, not evidence of an enforcement mechanism.
    """
    m=(cfg.get('budget_batch') or {}).get('monetary')
    base={'closed':False,'enforced':False,'bound_kind':'planning_estimate',
          'currency':m.get('currency') if isinstance(m,dict) else None}
    if not isinstance(m,dict):
        base['reason']='missing_monetary_registration'
        return base
    for k in ('input_price_per_mtok','output_price_per_mtok',
              'max_input_tokens_per_request','batch_cap'):
        v=m.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not v>0:
            base['reason']='missing_or_invalid:'+k
            return base
    if not isinstance(m.get('currency'),str) or not m['currency'].strip():
        base['reason']='missing_or_invalid_currency'
        return base
    ba=cfg['budget_per_attempt']
    # Count the registered block table, not two fields which happen to both
    # equal three.  Each registered attempt may consume the request cap.
    attempts=len(block_order(cfg))
    requests=attempts*ba['max_model_requests']
    in_tok=requests*m['max_input_tokens_per_request']
    out_tok=requests*ba['max_output_tokens_per_request']
    bound=(in_tok*m['input_price_per_mtok']
           +out_tok*m['output_price_per_mtok'])/1e6
    base.update(estimated_cost=round(bound,4),computed_bound=round(bound,4),
        cap=m['batch_cap'],
        request_count= requests,
        bound_basis=(f'{attempts} registered attempts x '
            f'{ba["max_model_requests"]} requests/attempt; input cap '
            f"{m['max_input_tokens_per_request']} tok/request is planning-only; "
            f'output cap {ba["max_output_tokens_per_request"]} tok/request'),
        reason='no_execution_time_input_token_or_spend_enforcement')
    return base


def monetary_closed(cfg):
    return monetary_bound(cfg)['closed']


def cost_risk_acceptance_valid(cfg):
    """The user's explicit decision to run THIS pilot without a hard
    monetary cap. Valid only when the registered decision carries the exact
    marker, the pilot-only scope, and the acknowledged gaps; it is an
    execution-condition change recorded by the user — never a license
    verification, a pricing confirmation, or proof that costs are low.
    monetary_bound() stays a pure planning estimate either way; all request
    /token/wall/resource limits and the stop-on-failure policy remain."""
    a=(cfg.get('budget_batch') or {}).get('user_cost_risk_acceptance')
    return (isinstance(a,dict)
        and a.get('decision')=='user_accepted_no_hard_monetary_cap_for_this_pilot'
        and a.get('scope')=='this_pilot_only'
        and isinstance(a.get('registered_at'),str) and bool(a['registered_at'].strip())
        and isinstance(a.get('acknowledged_gaps'),list)
        and 'dataset_terms_unresolved' in a['acknowledged_gaps']
        and 'pricing_unknown' in a['acknowledged_gaps'])


def readiness(cfg):
    missing=[]
    for t in cfg['tasks']:
        if not digest_is_full(t['image_arm64_digest']):
            missing.append('image_digest:'+t['instance_id'])
    if not monetary_closed(cfg) and not cost_risk_acceptance_valid(cfg):
        missing.append('monetary_budget_not_closed')
    return {'ready':not missing,'missing':missing,
            'monetary_bound':monetary_bound(cfg),
            'cost_risk_acceptance':(
                {'registered':True,'decision':'no_hard_monetary_cap_accepted',
                 'scope':'this_pilot_only',
                 'note':'user execution-condition decision; not a license '
                        'verification or cost proof; monetary_bound remains '
                        'a planning estimate with unknown prices'}
                if cost_risk_acceptance_valid(cfg)
                else {'registered':False})}


def block_order(cfg):
    """Pre-registered deterministic block table: round r orders the tasks by
    sha256('<seed>:<r>:<instance_id>') ascending. Every task runs exactly
    once per round."""
    seed=cfg['design']['block_seed']
    ids=sorted(t['instance_id'] for t in cfg['tasks'])
    table=[]
    for r in range(cfg['design']['rounds']):
        order=sorted(ids,key=lambda i:hashlib.sha256(f'{seed}:{r}:{i}'.encode()).hexdigest())
        table.extend((r,i) for i in order)
    return table


def task_config(cfg, instance_id):
    for t in cfg['tasks']:
        if t['instance_id']==instance_id:return t
    raise P112Error('unknown_task:'+instance_id)


def _attempt_limits(cfg, *, total_wall_s=None):
    from .coding_pilot import BudgetLimits
    ba=cfg['budget_per_attempt']
    total=ba['total_wall_min']*60
    agent=ba['agent_wall_min']*60
    verifier=ba['verifier_wall_min']*60
    if total_wall_s is not None:
        # shared batch deadline propagated INTO this attempt: the attempt may
        # never claim more than the remaining batch work budget
        total=min(total,total_wall_s)
        agent=min(agent,total)
        verifier=min(verifier,max(0.0,total-agent))
    return BudgetLimits(
        max_model_requests=ba['max_model_requests'],
        max_steps=ba['max_steps'],
        max_output_tokens_per_request=ba['max_output_tokens_per_request'],
        agent_wall_s=agent,verifier_wall_s=verifier,total_wall_s=total,
        max_new_artifact_bytes=int(ba['max_new_artifact_bytes_gib']*2**30))


def build_task_runner(cfg, instance_id, *, authorized, runtime, harness,
                      verifier, credentials=None, project_root=None,
                      limits=None, collection='P1-12'):

    """Assemble the EXISTING runner chain for one task (no new framework)."""
    from .coding_pilot import CodingPilotRunner, VerifierSpec
    from .mini_agent_adapter import AgentTask
    tc=task_config(cfg,instance_id)
    record=json.loads((PROJECT_ROOT/tc['record_locator']).read_bytes())
    image=tc['image_arm64_digest']
    if not digest_is_full(image):
        raise P112Error('image_digest_not_full:'+instance_id)
    runner=CodingPilotRunner(
        project_root=project_root or PROJECT_ROOT,collection=collection,
        harness=harness,verifier=verifier,runtime=runtime,
        limits=limits or _attempt_limits(cfg),
        # whitelist projection: the agent ONLY ever sees instance_id and
        # problem_statement; reference patch/test_patch/eval_script never
        # enter agent inputs
        task=AgentTask(instance_id=record['instance_id'],
                       problem_statement=record['problem_statement'],
                       image=image,source_type='benchmark_real'),
        verifier_spec=VerifierSpec(
            instance_id=record['instance_id'],image=image,
            eval_script_ref='record.json',log_parser=record['log_parser'],
            eval_type=record['eval_type'],
            record_locator=str(PROJECT_ROOT/tc['record_locator'])),
        image=image,source_type='benchmark_real',credentials=credentials,
        agent_container_cpu='4',agent_container_mem='8g',
        verifier_container_cpu='4',verifier_container_mem='8g')
    return runner


def build_plan():
    cfg=load_config()
    paths=sorted((CODE_ROOT/'src/agent_workload_characterization').rglob('*.py'))
    identity=dict(catalog_sha256=sha(CATALOG),
        code_sha256={str(p.relative_to(CODE_ROOT)):sha(p) for p in paths},
        interpreter={'entry':str(Path(sys.executable).resolve()),
                     'version':sys.version.split()[0],
                     'mini_venv':str(MINI_VENV_PY),'eval_venv':str(EVAL_VENV_PY)},
        collection='P1-12',approval='reports/resource/P1-12/APPROVAL.json',
        dataset=cfg['dataset'],
        agent=cfg['agent'],
        tasks={t['instance_id']:{'record_sha256':t['record_sha256'],
                                 'image_arm64_digest':t['image_arm64_digest'],
                                 'image_status':t['image_status']}
               for t in cfg['tasks']},
        design=dict(rounds=cfg['design']['rounds'],
                    repeats_per_task=cfg['design']['repeats_per_task'],
                    block_seed=cfg['design']['block_seed'],
                    order_rule=cfg['design']['order_rule'],
                    block_table=[{'round':r,'instance_id':i} for r,i in block_order(cfg)]),
        budget_per_attempt=cfg['budget_per_attempt'],
        budget_batch=cfg['budget_batch'],
        failure_policy=cfg['failure_policy'],
        readiness=readiness(cfg))
    return dict(task='P1-12',mode='plan_only',identity=identity,
        b_command=(f'PYTHONPATH=src {shlex.quote(str(EVAL_VENV_PY))} -B '
                   '-m agent_workload_characterization.runners.p1_12_entry '
                   '--execute --i-approve-the-p1-12-b'),
        authorization={'user_approval':'pending','tool_execution_permission':'pending'},
        limits=dict(batch_wall_min=cfg['budget_batch']['batch_wall_min']))


def guarded(path, *, new=False):
    root=guard_resource_root(PROJECT_ROOT,'P1-12')
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if '..' in path.parts or not path.is_relative_to(root):raise P112Error('output_outside_namespace')
    current=PROJECT_ROOT.resolve()
    for part in path.relative_to(current).parts:
        current=current/part
        if current.is_symlink():raise P112Error('output_symlink')
    real=path.resolve()
    for p in [PROJECT_ROOT/'references',PROJECT_ROOT/'data/raw',*_catalog_protected_roots(PROJECT_ROOT)]:
        p=p.resolve()
        if real==p or real.is_relative_to(p) or p.is_relative_to(real):raise P112Error('protected_output')
    if new and path.exists():raise P112Error('output_exists')
    return path


def write_json(path,payload):
    guarded(path,new=True)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x',encoding='utf-8') as fh:
        json.dump(payload,fh,indent=2,allow_nan=False);fh.write('\n')


def rewrite_json(path,payload):
    """Replace an already-written report atomically (tmp + os.replace) so
    the on-disk summary never lags the final verdict."""
    guarded(path)
    tmp=Path(path).with_name(Path(path).name+'.tmp-'+uuid.uuid4().hex[:8])
    tmp.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def verify_approval(path,identity=None):
    path=guarded(path)
    if path!=APPROVAL:raise P112Error('approval_wrong_namespace')
    record=json.loads(path.read_text())
    if (record.get('checklist_identity')!=(identity or build_plan()['identity']) or
        record.get('approved') is not True or not record.get('approved_by') or not record.get('approved_at_utc')):
        raise P112Error('approval_identity_or_user_record')
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


def preflight_checks(cfg):
    """The SAME gate the plan reports: full digests, the monetary gate
    (closed pricing structure OR the user's registered cost-risk acceptance
    for this pilot), interpreters, records. Placeholder digests can never
    yield READY, and neither can an unregistered monetary condition."""
    checks={'mini_venv':MINI_VENV_PY.is_file(),
            'eval_venv':EVAL_VENV_PY.is_file(),
            'records_sha':True,
            'image_digests_full':all(digest_is_full(t['image_arm64_digest']) for t in cfg['tasks']),
            'monetary_gate_satisfied':(monetary_closed(cfg)
                                       or cost_risk_acceptance_valid(cfg))}
    for t in cfg['tasks']:
        try:
            if sha(PROJECT_ROOT/t['record_locator'])!=t['record_sha256']:
                checks['records_sha']=False
        except OSError:
            checks['records_sha']=False
    return dict(status='READY' if all(checks.values()) else 'NOT_READY',
        checks=checks,
        readiness=readiness(cfg),
        notes={'image_digests':'identities must be repo@sha256:<64hex>; tags and truncated digests are refused',
               'local_image_presence':'NOT verified by this offline preflight; a Docker read-only preflight is a separately-authorized step'})


def docker_image_preflight(cfg, *, runner=None, deadline=None):
    """Read-only verification that each pinned image exists LOCALLY with the
    exact digest and arm64/linux platform (RUN-02-style check; no pull, no
    container start). Reached only after the offline preflight is READY.
    Budget discipline: an expired deadline REFUSES to start any docker call
    (no max(1,...) floor); every call uses min(15, remaining) as a float."""
    runner=runner or subprocess.run
    results={}
    for t in cfg['tasks']:
        remaining=None if deadline is None else deadline-time.monotonic()
        if remaining is not None and remaining<=0:
            results[t['instance_id']]={'present':False,'detail':'budget_exhausted'}
            continue
        timeout=15.0 if remaining is None else min(15.0,remaining)
        ref=t['image_arm64_digest']
        try:
            proc=runner(['docker','image','inspect',ref,'--format',
                         '{{.Os}}/{{.Architecture}} {{index .RepoDigests 0}}'],
                        capture_output=True,text=True,timeout=timeout)
            if proc.returncode!=0:
                results[t['instance_id']]={'present':False,'detail':'inspect_failed'}
                continue
            fields=proc.stdout.strip().split()
            os_arch=fields[0] if fields else ''
            repo_digest=fields[1] if len(fields)>1 else ''
            ok=(os_arch in ('linux/arm64','linux/arm64/v8')
                and repo_digest==ref)
            results[t['instance_id']]={'present':True,'os_arch':os_arch,
                'repo_digest':repo_digest,'matches_pinned_digest':ok}
        except (OSError,subprocess.TimeoutExpired) as exc:
            results[t['instance_id']]={'present':False,'detail':type(exc).__name__}
    ready=all(r.get('matches_pinned_digest') for r in results.values())
    return {'status':'READY' if ready else 'NOT_READY','images':results,
            'note':'local presence + digest match verified read-only; no pull, no container start'}


def resolve_credentials():
    """Read the registered official provider after preflight, never in plan mode.

    Literal local keys are supported; no fallback to the historical gateway.
    Neither secrets nor their hashes enter the execution identity.
    """
    from . import smoke_launcher
    from .run_02_entry import SDK_BASE_ENV, SDK_KEY_ENV
    agent=load_config()['agent']
    try:
        api_base,api_key=smoke_launcher.load_credentials(
            smoke_launcher.DEFAULT_CONFIG,
            provider_name=agent['provider'],model_key=agent['model_key'],
            model_display_name=agent['config_model_display_name'])
    except smoke_launcher.LauncherError as exc:
        raise P112Error('credentials_unavailable') from exc
    if api_base != agent['api_base']:
        raise P112Error('api_base_identity_mismatch')
    restricted=smoke_launcher.build_restricted_env(api_base,api_key)
    return {SDK_BASE_ENV:restricted['PILOT_API_BASE'],
            SDK_KEY_ENV:restricted['PILOT_API_KEY']}


def production_factories(collection='P1-12'):
    """Real factories, assembled lazily and only reached when preflight is
    READY. Reuses the same harness/verifier/runtime classes RUN-02 used.
    `harness_factory(image)` binds the per-task digest."""
    from .mini_agent_adapter import MiniSweAgentHarness
    from .coding_pilot import SwebenchVerifierRunner
    from .container_runtime import DockerCliRuntime
    bundled=MiniSweAgentHarness.load_bundled_config(MINI_VENV_PY)
    model_cfg=bundled.get('model') or {}
    mini_config={'agent':dict(bundled.get('agent') or {}),
                 'model':{'model_name':load_config()['agent']['model_request_id'],
                          'model_kwargs':{k:v for k,v in (model_cfg.get('model_kwargs') or {}).items()
                                          if k not in ('num_retries','max_tokens')}},
                 'environment':dict(bundled.get('environment') or {})}
    def runtime_factory():
        return DockerCliRuntime(authorized=True,collection=collection)
    def harness_factory(image):
        return MiniSweAgentHarness(MINI_VENV_PY,authorized=True,
                                   mini_config=mini_config,target_image_ref=image,
                                   poll_interval_s=0.2)
    def verifier_factory():
        return SwebenchVerifierRunner(authorized=True,
                                      model_name='mini-SWE-agent-2.4.6')
    return runtime_factory,harness_factory,verifier_factory


def median_iqr(values):
    """Median and IQR (linear interpolation quartiles), or Nones."""
    if not values:return {'n':0,'median':None,'iqr':None,'min':None,'max':None}
    vs=sorted(values);n=len(vs)
    def q(p):
        pos=p*(n-1);lo=int(pos);hi=min(lo+1,n-1)
        return vs[lo]+(vs[hi]-vs[lo])*(pos-lo)
    q1,q3=q(.25),q(.75)
    return {'n':n,'median':statistics.median(vs),'iqr':q3-q1,
            'min':vs[0],'max':vs[-1]}


def downgrade_and_rearchive(payload, output_dir, *, identity, config):
    """Post-archive downgrade path: the summary is REWRITTEN first, then the
    outputs table is REBUILT from disk and the manifest rewritten, so the
    manifest's bytes/SHA always describe the FINAL on-disk content. The
    manifest itself is never self-hashed (project convention), matching the
    first-pass archive where the scan happens before the manifest exists."""
    rewrite_json(output_dir/'summary.json',payload)
    outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,'sha256':sha(p)}
             for p in output_dir.rglob('*')
             if p.is_file() and p.name!='manifest.json'}
    manifest=dict(identity=identity or build_plan()['identity'],
        outputs=outputs,
        inputs=dict(catalog={'bytes':CATALOG.stat().st_size,'sha256':sha(CATALOG)},
            records={t['instance_id']:{'bytes':(PROJECT_ROOT/t['record_locator']).stat().st_size,
                                       'sha256':t['record_sha256']}
                     for t in config['tasks']}),
        created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        status=payload['status'],archive_status=payload.get('archive_status','complete'))
    rewrite_json(output_dir/'manifest.json',manifest)
    actual=json.loads((output_dir/'manifest.json').read_text())['outputs']
    if actual!=outputs or any(sha(output_dir/p)!=v['sha256'] or
            (output_dir/p).stat().st_size!=v['bytes'] for p,v in actual.items()):
        raise P112Error('archive_hash_mismatch')


def _invalidate_manifest(output_dir, payload, error_category):
    """Ensure an old success manifest cannot survive an archive failure.

    This is deliberately a single best-effort invalidation operation.  If
    the directory is no longer writable, the old file is removed when
    possible; the caller still returns a failed/incomplete archive result and
    does not claim that a valid manifest exists.
    """
    path=Path(output_dir)/'manifest.json'
    invalid=dict(status=payload.get('status','stopped'),
        archive_status='failed',archive_integrity='invalid',outputs={},
        error_category=error_category)
    try:
        if path.exists():
            rewrite_json(path,invalid)
            return 'invalidated'
    except Exception:
        pass
    try:
        if path.exists():
            path.unlink()
        return 'removed_or_absent'
    except Exception:
        return 'unresolved_old_manifest'


def run_batch(runtime_factory, harness_factory, verifier_factory, output_dir, *,
              config=None, deadline=None, run_id=None, identity=None,
              credentials=None, project_root=None, collection='P1-12'):
    config=json.loads(json.dumps(config or load_config()))
    bb=config['budget_batch']
    deadline=deadline if deadline is not None else time.monotonic()+bb['batch_wall_min']*60
    reserve_s=bb['cleanup_and_summary_reserve_min']*60
    output_dir=guarded(output_dir,new=True)
    guard_resource_report(PROJECT_ROOT,output_dir,'P1-12');output_dir.mkdir(parents=True)
    run_id=run_id or 'P1-12-'+uuid.uuid4().hex[:8]
    table=block_order(config)
    payload=dict(run_id=run_id,status='pending',
        planned_attempts=[{'round':r,'instance_id':i} for r,i in table],
        attempts=[],per_task={},errors=[],budget_overrun=False,
        clock_anchor={'monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),
                      'domain':'same_host_CLOCK_MONOTONIC'})
    stop_reason=None
    def remaining_work_s():
        return deadline-reserve_s-time.monotonic()
    for idx,(rnd,inst) in enumerate(table):
        if stop_reason is not None:
            payload['attempts'].append({'round':rnd,'instance_id':inst,
                'status':'not_executed','reason':stop_reason})
            continue
        work_left=remaining_work_s()
        if work_left<=0:
            payload['budget_overrun']=True
            stop_reason='batch_deadline_exhausted'
            payload['attempts'].append({'round':rnd,'instance_id':inst,
                'status':'not_executed','reason':stop_reason})
            continue
        tc=task_config(config,inst)
        attempt={'round':rnd,'instance_id':inst,'status':'started'}
        payload['attempts'].append(attempt)
        try:
            # propagate the SHARED deadline into this attempt's budget
            limits=_attempt_limits(config,total_wall_s=work_left)
            runner=build_task_runner(config,inst,authorized=True,
                collection=collection,
                runtime=runtime_factory(),
                harness=harness_factory(tc['image_arm64_digest']),
                verifier=verifier_factory(),credentials=credentials,
                project_root=project_root,limits=limits)
            attempt['runner_image']=runner.image
            attempt['attempt_budget_total_wall_s']=limits.total_wall_s
            outcome=runner.run()
            attempt.update(status='executed',run_id=outcome.run_id,
                execution_status=outcome.execution_status,
                evaluation_status=outcome.evaluation_status,
                archive_status=outcome.archive_status,
                cleanup_status=outcome.cleanup_status,
                cleanup_errors=outcome.cleanup_errors,
                resolved=outcome.resolved,
                run_dir=outcome.run_dir,
                budget_usage=outcome.budget_usage)
            # registered failure policy: resolved=false and no_candidate are
            # task results; infrastructure, budget (wall/timeout), safety or
            # cleanup/archive failures stop the batch
            stop=(outcome.execution_status not in ('ok','no_candidate')
                  or outcome.evaluation_status in ('infra_failure','verifier_timeout')
                  or outcome.cleanup_status!='ok'
                  or outcome.archive_status not in ('complete','ok'))
            if stop:
                # ONE status vocabulary everywhere: an attempt that ran and
                # failed is 'failed' (not executed+outcome); CLI counters and
                # per-task grouping read the same field
                attempt['status']='failed'
                attempt['batch_stop_reason']='infrastructure_or_cleanup_or_archive_failure'
                stop_reason='batch_stopped_after_infrastructure_failure'
        except Exception as exc:
            attempt.update(status='failed',error=type(exc).__name__)
            payload['errors'].append(type(exc).__name__)
            stop_reason='batch_stopped_after_infrastructure_failure'
    # per-task grouping: raw points, resolved counts, median/IQR; repeats are
    # NEVER independent tasks; executed / failed / not_executed are distinct
    for t in config['tasks']:
        inst=t['instance_id']
        rows=[a for a in payload['attempts'] if a['instance_id']==inst]
        executed=[a for a in rows if a.get('status')=='executed']
        failed=[a for a in rows if a.get('status')=='failed']
        def nums(field):
            return [a['budget_usage'].get(field) for a in executed
                    if isinstance(a.get('budget_usage'),dict)
                    and isinstance(a['budget_usage'].get(field),(int,float))]
        payload['per_task'][inst]={
            'planned':len(rows),'executed':len(executed),'failed':len(failed),
            'not_executed':len(rows)-len(executed)-len(failed),
            'resolved_true':sum(1 for a in executed if a.get('resolved') is True),
            'resolved_false':sum(1 for a in executed if a.get('resolved') is False),
            'resolved_none':sum(1 for a in executed if a.get('resolved') is None),
            'raw_points':[{'round':a['round'],'run_id':a.get('run_id'),
                           'status':a.get('status'),
                           'resolved':a.get('resolved'),
                           'execution_status':a.get('execution_status'),
                           'evaluation_status':a.get('evaluation_status')}
                          for a in rows],
            'wall_s_stats':median_iqr(nums('elapsed_total_s')),
            'model_requests_stats':median_iqr(nums('requests')),
            'note':'repeats within a task are not independent samples; no P95/P99 claims'}
    payload['statistics_note']=('median/IQR use linear interpolation; grouped by '
        'task; 3x3 is a pilot proposal, not statistical sufficiency')
    # unified final verdict: complete ONLY when every planned attempt
    # executed without a stop reason and the batch budget held
    payload['budget_overrun'] |= time.monotonic()>deadline
    n_executed=sum(1 for a in payload['attempts'] if a.get('status')=='executed')
    if payload['status']=='pending':
        if payload['budget_overrun']:
            payload['status']='stopped'
        elif n_executed==len(table) and not stop_reason:
            payload['status']='complete'
        else:
            payload['status']='stopped'
    payload['wall_min']=bb['batch_wall_min']-((deadline-time.monotonic())/60)

    def _archive_once():
        """One consistent archive pass: write the summary, REBUILD the
        outputs table from disk (so any summary rewrite refreshes bytes and
        hashes), write the manifest, read both back and verify."""
        write_json(output_dir/'summary.json',payload)
        outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,'sha256':sha(p)}
                 for p in output_dir.rglob('*') if p.is_file()}
        manifest=dict(identity=identity or build_plan()['identity'],
            outputs=outputs,
            inputs=dict(catalog={'bytes':CATALOG.stat().st_size,'sha256':sha(CATALOG)},
                records={t['instance_id']:{'bytes':(PROJECT_ROOT/t['record_locator']).stat().st_size,
                                           'sha256':t['record_sha256']}
                         for t in config['tasks']}),
            created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            status=payload['status'],archive_status=payload.get('archive_status','complete'))
        write_json(output_dir/'manifest.json',manifest)
        actual=json.loads((output_dir/'manifest.json').read_text())['outputs']
        if actual!=outputs or any(sha(output_dir/p)!=v['sha256'] or
                (output_dir/p).stat().st_size!=v['bytes'] for p,v in actual.items()):
            raise P112Error('archive_hash_mismatch')

    try:
        payload['archive_status']='complete'
        _archive_once()
        # post-archive budget verdict: if archiving itself pushed the batch
        # past the deadline, downgrade and RE-ARCHIVE so the on-disk summary
        # and the manifest's outputs table (hashes included) stay consistent
        payload['budget_overrun'] |= time.monotonic()>deadline
        if payload['budget_overrun']:
            payload['status']='stopped'
            downgrade_and_rearchive(payload,output_dir,identity=identity,
                                    config=config)
        payload['archive_status']='complete'
    except Exception as exc:
        payload.update(status='stopped',archive_status='failed')
        payload['budget_overrun'] |= time.monotonic()>deadline
        payload['errors'].append(type(exc).__name__)
        payload['archive_integrity']=_invalidate_manifest(
            output_dir,payload,type(exc).__name__)
        try:
            rewrite_json(output_dir/'summary.json',payload)
            write_json(output_dir/'archive_failure.json',{
                'status':'FAIL','category':type(exc).__name__,
                'manifest_status':payload['archive_integrity']})
        except Exception:pass
    return payload


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--i-approve-the-p1-12-b',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_p1_12_b:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (args.execute and args.i_approve_the_p1_12_b):return 2
    try:
        plan=build_plan();identity=plan['identity']
        verify_approval(APPROVAL,identity);register_attempt(identity)
    except Exception as exc:
        print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+plan['limits']['batch_wall_min']*60
    rc=5;detail='execution_failed'
    try:
        from .g1_02_entry import local_docker_environment
        with local_docker_environment():
            # one pinned local endpoint covers the docker preflight AND every
            # runtime call in this process; no remote context/env override
            cfg=load_config()
            preflight=preflight_checks(cfg)
            detail='preflight_not_ready:'+','.join(preflight['readiness']['missing'])
            if preflight['status']!='READY':
                write_json(guarded(APPROVAL.parent/'PREFLIGHT.json',new=True),preflight)
                rc=4
            else:
                docker_pre=docker_image_preflight(cfg,deadline=deadline)
                preflight['docker_images']=docker_pre
                write_json(guarded(APPROVAL.parent/'PREFLIGHT.json',new=True),preflight)
                if docker_pre['status']!='READY':
                    rc=4;detail='docker_image_preflight_not_ready'
                else:
                    credentials=resolve_credentials()
                    batch=('P1-12-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
                           +'-'+uuid.uuid4().hex[:8])
                    runtime_factory,harness_factory,verifier_factory=production_factories()
                    result=run_batch(runtime_factory,harness_factory,verifier_factory,
                        APPROVAL.parent/batch,config=cfg,deadline=deadline,
                        identity=identity,credentials=credentials)
                    rc=0 if (result['status']=='complete'
                             and result.get('archive_status')=='complete') else 5
                    detail=(f"batch_{result['status']}_executed_"
                            f"{sum(1 for a in result['attempts'] if a.get('status')=='executed')}"
                            f"_failed_{sum(1 for a in result['attempts'] if a.get('status')=='failed')}"
                            f"_not_executed_{sum(1 for a in result['attempts'] if a.get('status')=='not_executed')}")
    except Exception as exc:detail=type(exc).__name__
    try:finish_marker('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
