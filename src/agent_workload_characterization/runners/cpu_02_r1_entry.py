"""CPU-02-R1: isolated retry gate over the accepted CPU-02 execution chain.

This module owns only the retry namespace and authorization/attempt gate.
Preparation, evaluator verification, perf protocol, sampling, reporting and
cleanup remain in cpu_02_entry.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid

from . import cpu_02_entry as base
from .container_runtime import DockerCliRuntime
from .g1_02_entry import local_docker_environment

PROJECT_ROOT = base.PROJECT_ROOT
RETRY_ID = 'R1'
ROOT = PROJECT_ROOT / 'reports/cpu/CPU-02/retries/R1'
APPROVAL = ROOT / 'APPROVAL.json'
ATTEMPT = ROOT / 'ATTEMPT_STARTED.json'
RUNTIME_FACTORY = lambda: DockerCliRuntime(authorized=True, collection='CPU-02-R1')
LOCAL_ENVIRONMENT = local_docker_environment
PROC_ROOT = None
GRADER = None


def build_plan():
    plan = base.build_plan()
    identity = json.loads(json.dumps(plan['identity']))
    identity['retry_id'] = RETRY_ID
    identity['collection'] = 'CPU-02-R1'
    identity['approval'] = 'reports/cpu/CPU-02/retries/R1/APPROVAL.json'
    identity['config']['collection_id'] = 'CPU-02-R1'
    identity['config']['authorization']['approval_path'] = identity['approval']
    identity['config']['authorization']['attempt_path'] = (
        'reports/cpu/CPU-02/retries/R1/ATTEMPT_STARTED.json')
    identity['config']['authorization']['report_root'] = (
        'reports/cpu/CPU-02/retries/R1')
    return dict(task='CPU-02', mode='plan_only', retry_id=RETRY_ID,
                identity=identity,
                b_command=(f'PYTHONPATH=src {base.shlex.quote(str(base.VENV_PYTHON))} -B '
                           '-m agent_workload_characterization.runners.cpu_02_r1_entry '
                           '--execute --i-approve-the-cpu-02-r1'),
                authorization={'user_approval': 'pending',
                               'tool_execution_permission': 'pending'},
                limits=identity['config']['limits'])


def _verify_approval(identity):
    record = json.loads(base.guarded(APPROVAL).read_text())
    if (record.get('checklist_identity') != identity
            or record.get('approved') is not True
            or not record.get('approved_by')
            or not record.get('approved_at_utc')):
        raise base.CPU02Error('r1_approval_identity_or_user_record')
    return record


def _register_attempt(identity):
    base.guarded(ATTEMPT, new=True).parent.mkdir(parents=True, exist_ok=True)
    base.write_json(ATTEMPT, dict(status='started', retry_id=RETRY_ID,
                                  identity=identity,
                                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                           time.gmtime())))


def _finish_attempt(status, detail):
    path = base.guarded(ATTEMPT)
    record = json.loads(path.read_text())
    record.update(status=status, detail=detail)
    tmp = path.with_name('ATTEMPT_FINISH-' + uuid.uuid4().hex + '.json')
    base.write_json(tmp, record)
    tmp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--i-approve-the-cpu-02-r1', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_cpu_02_r1:
        print(json.dumps(build_plan(), indent=2)); return 0
    if not (args.execute and args.i_approve_the_cpu_02_r1): return 2
    try:
        identity = build_plan()['identity']
        _verify_approval(identity)
        _register_attempt(identity)
    except Exception as exc:
        print('REFUSED:' + type(exc).__name__); return 3

    plan = build_plan(); limits = plan['limits']
    deadline = time.monotonic() + limits['batch_wall_s']
    rc, detail = 5, 'execution_failed'
    try:
        with LOCAL_ENVIRONMENT():
            preflight = base.preflight_checks(deadline=deadline)
            preflight['docker'] = base.docker_preflight(deadline=deadline)
            base.write_json(base.guarded(ROOT / 'PREFLIGHT.json', new=True), preflight)
            if preflight['status'] != 'READY' or preflight['docker']['status'] != 'READY':
                rc, detail = 4, 'preflight_failed'
            else:
                run_id = 'CPU-02-R1-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
                run_id += '-' + uuid.uuid4().hex[:8]
                result = base.run_batch(RUNTIME_FACTORY(), ROOT / run_id,
                                        config=plan['identity']['config'],
                                        deadline=deadline, run_id=run_id,
                                        identity=identity, preflight=preflight,
                                        proc_root=PROC_ROOT, grader=GRADER)
                rc = (0 if result['status'] in ('complete', 'unavailable')
                      and result['archive_status'] == 'complete' else 5)
                detail = ('eval_' + (result['phases'].get('eval') or {}).get('status', 'absent')
                          + '_grade_' + (result['phases'].get('grade') or {}).get('status', 'absent')
                          + '_sampling_' + (result['phases'].get('perf') or {}).get('status', 'absent')
                          + '_prepare_' + (result['phases'].get('prepare') or {}).get('detail',
                                                                   (result['phases'].get('prepare') or {}).get('status', 'absent')))
    except Exception as exc:
        detail = type(exc).__name__
    try:
        _finish_attempt('completed' if rc == 0 else 'failed', detail)
    except Exception:
        rc = 5
    print(json.dumps({'returncode': rc, 'detail': detail}))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
