#!/usr/bin/env python3
"""One fixed, sequential, explicitly authorized batch over existing runners."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
COLLECTION = 'LOCAL-THREE-CLASS-REPEAT-01'
ENV = Path('env/local-three-class-repeat-01')
REPORT = Path('reports/resource') / COLLECTION
RAW = Path('data/raw/generated') / COLLECTION
ENTRY = Path('scripts/local_three_class_repeat_01_entry.py')
FLAG = '--i-approve-the-local-three-class-repeat-01'
ENDPOINT = 'unix:///var/run/docker.sock'
PYTHONS = {'Coding': '.venvs/swebench-eval-02e7a74/bin/python',
           'Office': '.venvs/docops-pilot-01/bin/python',
           'Assistant': '.venvs/toolsandbox-pilot-01/bin/python'}
TASKS = {
 'Coding': ('django__django-16485', 'astropy__astropy-13236', 'astropy__astropy-13398'),
 'Office': ('atomic__excel_001_budget_bucket_totals_seed',
            'atomic__ppt_008_bullet_editing_seed', 'atomic__pdf_004_audit_pages_reorder_seed'),
 'Assistant': ('send_message_with_contact_content_cellular_off',
               'add_reminder_content_and_week_delta_and_time',
               'modify_contact_with_message_recency_multiple_user_turn')}
CAPS = {'Coding': 1800, 'Office': 2700, 'Assistant': 480}
TOTAL = 50400
# This is inside the 14h ceiling, not extra work time.
RESERVE = 300


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def record(path, root=ROOT):
    p = root / path
    data = p.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path, root=ROOT):
    return json.loads((root / path).read_text())


def write(path, obj, root=ROOT):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def schedule():
    return [{'sequence': seq, 'chain': chain, 'round': r, 'task': tasks[k]}
            for seq, (chain, tasks, r, k) in enumerate(
                (chain, tasks, r, k) for chain, tasks in TASKS.items()
                for r in range(3) for k in ((r % 3), ((r+1) % 3), ((r+2) % 3)))]


def command():
    return 'PYTHONPATH=src python3 -B ' + str(ENTRY) + ' --execute ' + FLAG


def assistant_profile():
    import toolsandbox_resource_pilot_01_entry as ts
    return ts.VOLCANO_PROFILE._replace(
        collection=COLLECTION, env_rel=ENV, report_rel=REPORT, raw_rel=RAW,
        approval_flag=FLAG, entry_script=str(ENTRY), run_suffix='localassistant01',
        scenario_names=TASKS['Assistant'], batch_schedule=None, batch_budget=None)


def component(chain):
    """Executed only by that chain's existing interpreter; never mixes venvs."""
    if chain == 'Assistant':
        import toolsandbox_resource_pilot_01_entry as ts
        return ts.build_identity(ROOT, profile=assistant_profile())
    if chain == 'Coding':
        import coding_measurement_volcano_01_entry as coding
        import yaml
        result = coding.build_identity()
        catalog = yaml.safe_load((ROOT / 'workload_catalog/p1_12_deepseek_official.yaml').read_text())
        result['task_records'] = catalog['tasks']
        result['collection'] = COLLECTION
        result['task_input_files'] = [record(t['record_locator']) for t in catalog['tasks']]
        for t, f in zip(catalog['tasks'], result['task_input_files'], strict=True):
            if f['sha256'] != t['record_sha256']:
                raise ValueError('Coding task record drift')
        return result
    import docops_office_repeat_01_entry as office
    import docops_measurement_validate_01_entry as single
    import importlib.metadata
    old = read('env/docops-office-repeat-01/frozen-identity.json')
    if office.identity_sha(old['identity']) != old['identity_sha256']:
        raise ValueError('source task/image freeze mismatch')
    ids = {t['key']: t['image_id'] for t in old['identity']['tasks']}
    result = office.build_identity(ids)
    for t, before in zip(result['tasks'], old['identity']['tasks'], strict=True):
        if t['files'] != before['files'] or t['image_id'] != before['image_id']:
            raise ValueError('official Office task/image drift')
    route = single.configured_route(single.VOLCANO_02_PROFILE)
    # Reuse the already validated installed Harbor identity coverage.
    actual = single.build_identity(profile=single.VOLCANO_02_PROFILE)
    result.update(collection=COLLECTION, model=actual['model'],
                  interpreter=actual['interpreter'], installed_dependencies=actual['installed_dependencies'],
                  code_and_runtime_files=actual['code_and_runtime_files'])
    result['run_configs'] = {t['key']: {
        **office.run_config(t['key'], 0, t['image_ref'], t['image_id'], collection=COLLECTION),
        'model_route': {k: route[k] for k in ('api_base', 'request_model', 'credential_env')}}
        for t in result['tasks']}
    result['paths'] = {'raw': str(RAW), 'reports': str(REPORT), 'env': str(ENV)}
    result['budget'] = {'attempt_caps_s': CAPS['Office'], 'attempt_retry': 0,
                        'batch_deadline': 'parent 14h including closeout, full attempt must fit'}
    return result


def component_process(chain):
    p = subprocess.run([str(ROOT / PYTHONS[chain]), '-B', str(ENTRY),
                        '--component', chain], cwd=ROOT, capture_output=True,
                       text=True, timeout=180)
    if p.returncode:
        raise RuntimeError('component preparation failed: ' + chain + ' rc=' + str(p.returncode))
    return json.loads(p.stdout)


def files_in_identity(obj):
    if isinstance(obj, dict):
        if {'path', 'bytes', 'sha256'} <= obj.keys():
            yield {k: obj[k] for k in ('path', 'bytes', 'sha256')}
        else:
            for v in obj.values():
                yield from files_in_identity(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from files_in_identity(v)


def namespace_clean(root=ROOT):
    if (root / RAW).exists() and any((root / RAW).iterdir()):
        return False
    return not ((root / REPORT).exists() and any(
        p.name != 'APPROVAL.json' for p in (root / REPORT).iterdir()))


def verify_identity(frozen, root=ROOT):
    if digest(frozen['identity']) != frozen['identity_sha256']:
        raise ValueError('full identity digest mismatch')
    for row in files_in_identity(frozen['identity']):
        if record(row['path'], root) != row:
            raise ValueError('frozen input/code drift: ' + row['path'])


def plan(root=ROOT):
    p = read(ENV / 'plan-identity.json', root)
    if p != read(ENV / 'frozen-identity.json', root):
        raise ValueError('full saved plan/freeze structure mismatch')
    verify_identity(p, root)
    return {**p, 'namespace_clean': namespace_clean(root), 'execute_command': command()}


def inspect(reference):
    p = subprocess.run(['docker', '--host', ENDPOINT, 'image', 'inspect', reference,
                        '--format', '{{.Id}} {{.Os}}/{{.Architecture}}'],
                       capture_output=True, text=True, timeout=30)
    return {'reference': reference, 'returncode': p.returncode,
            'observed': p.stdout.strip().split() if p.returncode == 0 else None}


def historical_records():
    """Limited to the predecessor experiments and analyses used in this task."""
    names = ('CODING-MEASUREMENT-VOLCANO-01', 'DOCOPS-MEASUREMENT-VOLCANO-01',
             'DOCOPS-MEASUREMENT-VOLCANO-02', 'TOOLSANDBOX-MEASUREMENT-VOLCANO-01',
             'DOCOPS-OFFICE-REPEAT-01', 'DOCOPS-OFFICE-REPEAT-02',
             'TOOLSANDBOX-ASSISTANT-REPEAT-01', 'TOOLSANDBOX-RESOURCE-PILOT-01',
             'TOOLSANDBOX-RESOURCE-PILOT-02')
    dirs = [Path(base)/name for base in ('data/raw/generated','reports/resource') for name in names]
    dirs += [Path('env')/name.lower() for name in names]
    dirs += [Path('reports/resource/P1-12/repeats/CODING-REPEAT-01'),
             Path('data/raw/generated/P1-12'),
             Path('reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1')]
    return {str(d): [record(p.relative_to(ROOT)) for p in sorted((ROOT/d).rglob('*'))
                     if p.is_file() and '__pycache__' not in p.parts]
            for d in dirs if (ROOT/d).is_dir()}


def prepare():
    if not namespace_clean() or (ROOT / ENV / 'plan-identity.json').exists():
        raise ValueError('occupied namespace/freeze')
    write(ENV / 'history-before.json', historical_records())
    comps = {k: component_process(k) for k in TASKS}
    source = read(ENV / 'source-manifest.json')
    source_base = Path(comps['Assistant']['official_source']['frozen_copy'])
    source_files = []
    for row in source['files']:
        actual = record(source_base / row['path'])
        if actual['sha256'] != row['sha256'] or actual['bytes'] != row['bytes']:
            raise ValueError('frozen official ToolSandbox source drift')
        source_files.append(actual)
    freezes = []
    for chain, python in PYTHONS.items():
        p = subprocess.run([str(ROOT / python), '-m', 'pip', 'freeze', '--disable-pip-version-check'],
                           capture_output=True, text=True, check=True, timeout=60)
        path = ROOT / ENV / (chain.lower() + '-current-freeze.txt')
        with path.open('x') as f:
            f.write(p.stdout)
        freezes.append(record(path.relative_to(ROOT)))
    images = []
    for t in comps['Coding']['task_records']:
        ref = t['image_arm64_digest']
        manifest = Path('data/catalog/p1_12_closure_evidence') / (
            'registry_manifest_' + ref.split('/')[1].split('@')[0] + '.json')
        expected = read(manifest)['config']['digest']
        observed = inspect(ref)
        images.append({'chain': 'Coding', 'task': t['instance_id'],
                       'expected_id': expected, 'platform': 'linux/arm64',
                       'registry_evidence': record(manifest), **observed})
    base = comps['Office']['base_image']
    for t in [{'key': 'base', 'image_ref': base['reference'], 'image_id': base['expected_id']},
              *comps['Office']['tasks']]:
        images.append({'chain': 'Office', 'task': t['key'], 'expected_id': t['image_id'],
                       'platform': 'linux/arm64', **inspect(t['image_ref'])})
    for row in images:
        if row['observed'] is not None and row['observed'] != [row['expected_id'], row['platform']]:
            raise ValueError('unexpected live image ID/architecture: ' + row['task'])
    blocked = {}
    for chain in ('Coding', 'Office'):
        missing = [x['task'] for x in images if x['chain'] == chain and x['observed'] is None]
        if missing:
            blocked[chain] = {'reason': 'required_fixed_image_missing_no_registered_local_recovery',
                              'missing_tasks': missing, 'policy': 'all nine class slots not_executed; no pull or substitution'}
    identity = {'schema': 'local-three-class-fixed-batch-v1', 'collection': COLLECTION,
        'components': comps, 'schedule': schedule(), 'images': images,
        'official_assistant_files': source_files, 'actual_dependency_freezes': freezes,
        'preflight_blocked_classes': blocked, 'attempt_retry': 0,
        'batch': {'wall_s': TOTAL, 'closeout_reserve_s': RESERVE,
                  'start_basis': 'formal batch start; preparation and offline analysis excluded',
                  'full_next_attempt_must_fit': True},
        'per_attempt_wall_s': CAPS, 'sample_interval_s': .5,
        'paths': {'env': str(ENV), 'reports': str(REPORT), 'raw': str(RAW)},
        'approval_flag': FLAG, 'execute_command': command(),
        'entry': record(ENTRY), 'coding_status_fix': record('scripts/coding_measurement_volcano_01_entry.py'),
        'history_protection_baseline': record(ENV / 'history-before.json'),
        'source_snapshot': record(ENV / 'source-before/coding_measurement_volcano_01_entry.py'),
        'cost': {'actual_bill': 'unknown', 'hard_cap': None},
        'network': 'shared netns per-interface, not task/API traffic'}
    frozen = {'identity': identity, 'identity_sha256': digest(identity)}
    write(ENV / 'plan-identity.json', frozen)
    write(ENV / 'frozen-identity.json', frozen)
    write(ENV / 'preparation-manifest.json', {
        'inputs': list(files_in_identity(identity)),
        'outputs': [record(ENV / n) for n in ('plan-identity.json', 'frozen-identity.json')]})
    return plan()


def verify_raw(run_dir, chain):
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    rows = manifest['outputs'] if chain == 'Office' else manifest['files']
    expected = {x['path'] for x in rows}
    actual = {str(p.relative_to(run_dir)) for p in run_dir.rglob('*')
              if p.is_file() and p.name != 'manifest.json'}
    if expected != actual:
        raise ValueError('raw file set mismatch')
    for row in rows:
        if record(row['path'], run_dir) != {k: row[k] for k in ('path','bytes','sha256')}:
            raise ValueError('raw hash mismatch: ' + row['path'])
    return len(rows)


def office_run(slot, frozen, run_id, deadline):
    import docops_office_repeat_01_entry as office
    import docops_word_resource_01_entry as shared
    c = frozen['identity']['components']['Office']
    task = next(t for t in c['tasks'] if t['key'] == slot['task'])
    cfg = {**c['run_configs'][slot['task']], 'round': slot['round']}
    inputs = [*c['code_and_runtime_files'], *task['files'], record(ENTRY)]
    hashes = {'task_toml': '/task.toml', 'instruction': '/instruction.md',
              'task_metadata': '/environment/task_metadata.json'}
    rp = {'run_id': run_id, 'identity_sha256': frozen['identity_sha256'],
          'run_config': cfg, 'run_inputs': inputs,
          'identity': {'files': {k: next(x for x in inputs if x['path'].endswith(s))
                                  for k,s in hashes.items()}},
          'batch_work_deadline_monotonic': deadline}
    summary = asyncio.run(shared.run_attempt(ROOT, rp))
    life = {x['phase']: x for x in summary['events']}
    return {'collection': COLLECTION, 'run_id': run_id, 'identity_sha256': frozen['identity_sha256'],
            'summary': summary, 'exit_code': shared.exit_code_for(summary),
            'image_retention_verified': life.get('image_tag_after_stop', {}).get('id') == task['image_id'],
            'removal_verified': life.get('removal_verified', {}).get('result')}


def child(slot_index, run_id, deadline):
    frozen = plan()
    slot = frozen['identity']['schedule'][slot_index]
    # Child entry is usable only for a slot already allocated by the approved parent.
    allocation = read(REPORT / run_id / 'ATTEMPT_STARTED.json')
    approval = read(REPORT / 'APPROVAL.json')
    if (allocation['slot'] != slot or allocation['identity_sha256'] != frozen['identity_sha256']
            or approval['identity_sha256'] != frozen['identity_sha256']):
        raise ValueError('slot approval/identity mismatch')
    report_path = REPORT / run_id / 'run-report.json'
    if slot['chain'] == 'Office':
        result = office_run(slot, frozen, run_id, deadline)
        write(report_path, result)
        return result['exit_code']
    if slot['chain'] != 'Assistant':
        raise ValueError('Coding class failed required all-task image preflight; execution prohibited')
    import toolsandbox_resource_pilot_01_entry as ts
    p = {'ready_for_execution': True, 'identity': frozen['identity']['components']['Assistant'],
         'identity_sha256': frozen['identity_sha256']}
    return ts.execute(ROOT, p, profile=assistant_profile(), scenario_name=slot['task'],
        run_id=run_id, run_metadata=slot, batch_deadline_ns=int(deadline*1e9),
        batch_work_deadline_ns=int((deadline-120)*1e9),
        report_path=ROOT / report_path, outer_manifest_path=ROOT / REPORT / run_id / 'manifest.json')


def adjudicate(chain, report, archive_ok):
    """(stop class, stop batch, reason); task scores are never used."""
    if chain == 'Office':
        failures = report['summary']['outcome']['infra_failures']
        clean = report.get('removal_verified') == 'removed'
        if not clean:
            return True, True, 'container_removal_unconfirmed'
        if not report.get('image_retention_verified'):
            return True, False, 'task_image_not_retained'
        bad = bool(failures) or report['exit_code'] != 0
    else:
        cleanup = report['cleanup']
        if not all(cleanup.get(k) for k in ('wait_reaped', 'original_process_gone', 'sampler_stopped')):
            return True, True, 'worker_or_sampler_reap_unconfirmed'
        bad = report.get('killed_by_deadline') or report.get('exit_code') not in (0, 3)
    if not archive_ok:
        return True, False, 'archive_failure'
    return bool(bad), False, 'chain_infrastructure_or_deadline_failure' if bad else None


def key_measurements(run_dir, chain, report):
    """Check key observations before launching another sample, not cache completeness."""
    s = json.loads((run_dir / 'supplemental_measurements.json').read_text())
    gaps = []
    if len(s['network']['samples']) < 2:
        gaps.append('shared_netns_samples_missing')
    if chain == 'Office':
        m = report['summary']['measurement']
        if m['call_timing_status'] != 'complete':
            gaps.append('request_tool_timing_partial')
        for scope in ('container', 'host_agent_process'):
            rows = m['resource_intervals'][scope]
            if not any(r['metrics']['cpu']['status'] == 'valid' for r in rows):
                gaps.append(scope + '_cpu_intervals_missing')
        if not s['container_disk_footprints'] or any(
                v['footprint']['status'] != 'complete' for v in s['container_disk_footprints'].values()):
            gaps.append('container_task_footprint_partial')
    else:
        if report['measurement']['right_censored_event_ids']:
            gaps.append('unclosed_semantic_events')
        rows = report['host_sampling']['resource_intervals']
        if not any(r['metrics']['cpu']['status'] == 'valid' for r in rows):
            gaps.append('worker_cpu_intervals_missing')
    return gaps


def shared_protocol_failure(run_dir, chain):
    path = run_dir / ('agent/events.jsonl' if chain == 'Office' else 'events.jsonl')
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    unsafe = {'AuthenticationError', 'PermissionDeniedError', 'NotFoundError'}
    for event in rows:
        if event.get('kind') != 'llm_request':
            continue
        attrs = event.get('attrs', {})
        if any(str(attrs.get(k)) in unsafe for k in ('error_type', 'exception_type', 'error_class')):
            return True
    return False


def execute():
    frozen = plan()
    if not frozen['namespace_clean']:
        raise ValueError('existing batch attempt/run')
    for x in frozen['identity']['images']:
        if x['observed'] is not None and inspect(x['reference'])['observed'] != x['observed']:
            raise ValueError('live image drift')
    from agent_workload_characterization.runners.smoke_launcher import load_credentials
    base, key = load_credentials()
    route = frozen['identity']['components']['Office']['model']
    if base != route['api_base']:
        raise ValueError('route drift')
    os.environ.update(VOLCANO_API_KEY=key, OPENAI_API_KEY=key, OPENAI_API_BASE=base,
                      DOCKER_HOST=ENDPOINT)
    os.environ.pop('DOCKER_CONTEXT', None)
    write(REPORT / 'APPROVAL.json', {'collection': COLLECTION,
        'identity_sha256': frozen['identity_sha256'], 'user_approval': 'approved',
        'scope': frozen['identity']['schedule'], 'attempt_retry': 0,
        'accept_unknown_cost_no_hard_cap': True,
        'source': 'current user attachment explicitly approves final verified configuration',
        'approved_at_utc': datetime.now(timezone.utc).isoformat()})
    started = time.monotonic()
    deadline = started + TOTAL - RESERVE
    write(REPORT / 'ATTEMPT_STARTED.json', {'collection': COLLECTION,
        'identity_sha256': frozen['identity_sha256'], 'started_monotonic': started,
        'meaning': 'batch authorization consumed; per-run markers identify actual attempts'})
    results = []
    blocked = dict(frozen['identity']['preflight_blocked_classes'])
    global_stop = None
    for slot in schedule():
        chain = slot['chain']
        reason = global_stop or blocked.get(chain)
        if deadline - time.monotonic() < CAPS[chain]:
            reason = 'insufficient_remaining_batch_budget_for_full_attempt'
        if reason:
            results.append({**slot, 'status': 'not_executed', 'reason': reason})
            continue
        verify_identity(frozen)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + f'-{slot["sequence"]:02d}-r{slot["round"]}-{chain.lower()}'
        write(REPORT / run_id / 'ATTEMPT_STARTED.json', {
            'slot': slot, 'identity_sha256': frozen['identity_sha256'], 'run_id': run_id})
        t = time.monotonic()
        logpath = ROOT / REPORT / run_id / 'entry.log'
        # Existing chain deadlines do the stopping; parent never kills a child
        # without its cleanup. A missed outer deadline is a global safety stop.
        with logpath.open('x') as log:
            p = subprocess.run([str(ROOT / PYTHONS[chain]), '-B', str(ENTRY), '--child',
                                str(slot['sequence']), '--run-id', run_id, '--deadline', str(deadline)],
                               cwd=ROOT, stdout=log, stderr=log)
        row = {**slot, 'run_id': run_id, 'identity_sha256': frozen['identity_sha256'],
               'returncode': p.returncode, 'parent_wall_s': time.monotonic()-t,
               'report_path': str(REPORT / run_id / 'run-report.json'), 'raw_path': str(RAW / run_id)}
        try:
            report = read(row['report_path'])
            nfiles = verify_raw(ROOT / RAW / run_id, chain)
            stop_class, stop_all, reason = adjudicate(chain, report, True)
            gaps = key_measurements(ROOT / RAW / run_id, chain, report)
            if gaps and not stop_class:
                stop_class, reason = True, 'key_measurement_gap'
            if shared_protocol_failure(ROOT / RAW / run_id, chain):
                stop_class, stop_all, reason = True, True, 'shared_gateway_authentication_or_route_failure'
            row.update(status='failed' if stop_class else 'executed', archive_files=nfiles,
                       archive_verified=True, stop_reason=reason, measurement_gaps=gaps)
            if stop_class:
                blocked[chain] = reason
            if stop_all:
                global_stop = reason
        except Exception as exc:
            row.update(status='failed', archive_verified=False, error_type=type(exc).__name__)
            # Without a readable terminal report cleanup cannot be confirmed.
            global_stop = 'acceptance_or_cleanup_unconfirmed:' + type(exc).__name__
        results.append(row)
        write(REPORT / run_id / 'VALIDATION.json', row)
        print(json.dumps({k: row.get(k) for k in ('sequence','chain','task','run_id','status','stop_reason')}, ensure_ascii=False), flush=True)
    summary = {'collection': COLLECTION, 'identity_sha256': frozen['identity_sha256'],
               'wall_s': time.monotonic()-started, 'within_batch_budget': time.monotonic()-started <= TOTAL,
               'class_stops': blocked, 'global_stop': global_stop, 'runs': results,
               'counts': {k: sum(r['status']==k for r in results) for k in ('executed','failed','not_executed')}}
    write(REPORT / 'batch-summary.json', summary)
    write(REPORT / 'ATTEMPT_COMPLETED.json', {k: v for k,v in summary.items() if k != 'runs'})
    outputs = [record(p.relative_to(ROOT)) for p in sorted((ROOT / REPORT).rglob('*')) if p.is_file()]
    write(REPORT / 'manifest.json', {'identity_sha256': frozen['identity_sha256'],
        'inputs': [record(ENV / n) for n in ('plan-identity.json','frozen-identity.json')],
        'raw_manifests': [record(RAW / r['run_id'] / 'manifest.json') for r in results if r.get('archive_verified')],
        'outputs': outputs})
    return 0 if not any(r['status']=='failed' for r in results) else 7


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--component', choices=TASKS)
    ap.add_argument('--prepare', action='store_true')
    ap.add_argument('--prepare-assistant-source', action='store_true')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument(FLAG, action='store_true')
    ap.add_argument('--child', type=int)
    ap.add_argument('--run-id')
    ap.add_argument('--deadline', type=float)
    a = ap.parse_args()
    if a.component:
        print(json.dumps(component(a.component), ensure_ascii=False)); return 0
    if a.prepare_assistant_source:
        import toolsandbox_resource_pilot_01_entry as ts
        print(json.dumps(ts.prepare_source(ROOT, profile=assistant_profile()))); return 0
    if a.child is not None:
        return child(a.child, a.run_id, a.deadline)
    if a.execute:
        if not getattr(a, FLAG[2:].replace('-', '_')):
            raise ValueError('specific approval flag required')
        return execute()
    p = prepare() if a.prepare else plan()
    print(json.dumps({k: v for k,v in p.items() if k != 'identity'}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
