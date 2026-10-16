#!/usr/bin/env python3
"""Fixed REPEAT-02 approval gate; reuse the existing nine-attempt execution loop."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
import docops_office_repeat_01_entry as office

ROOT = office.ROOT
COLLECTION = 'DOCOPS-OFFICE-REPEAT-02'
ENV_REL = Path('env/docops-office-repeat-02')
REPORT_REL = Path('reports/resource') / COLLECTION
RAW_REL = Path('data/raw/generated') / COLLECTION
FLAG = '--i-approve-the-docops-office-repeat-02'
COMMAND = ('PYTHONPATH=src LITELLM_LOCAL_MODEL_COST_MAP=True '
           '.venvs/docops-pilot-01/bin/python -B '
           'scripts/docops_office_repeat_02_entry.py --execute ' + FLAG)


def build_identity(root: Path = ROOT) -> dict:
    source = ROOT / office.ENV_DIR_REL / 'frozen-identity.json'
    frozen = json.loads(source.read_text())
    if office.identity_sha(frozen['identity']) != frozen['identity_sha256']:
        raise ValueError('historical image/task identity digest mismatch')
    preparation_path = ROOT / ENV_REL / 'image-preparation.json'
    prepared = json.loads(preparation_path.read_text())
    if (prepared['collection'] != COLLECTION or prepared['endpoint'] != office.ENDPOINT
            or prepared['base_image'] != frozen['identity']['base_image']):
        raise ValueError('image preparation identity conflict')
    ids = {}
    for task, observed in zip(frozen['identity']['tasks'], prepared['images'], strict=True):
        if (observed['task_key'] != task['key'] or observed['after'] != {
                'reference': task['image_ref'], 'id': task['image_id'], 'platform': 'linux/arm64'}
                or observed['task_files'] != task['files']
                or office.task_tree_records(task['key']) != task['files']):
            raise ValueError('task/image preparation drift: ' + task['key'])
        ids[task['key']] = task['image_id']
    evidence = [office.file_record(preparation_path, preparation_path.relative_to(ROOT))]
    for row in [*prepared['source_files'], *(r['log'] for r in prepared['images'] if 'log' in r)]:
        if office.file_record(ROOT / row['path'], Path(row['path'])) != row:
            raise ValueError('preparation evidence hash mismatch: ' + row['path'])
        if row not in evidence:
            evidence.append(row)
    identity = office.build_identity(ids)
    identity['collection'] = COLLECTION
    identity['preparation_evidence'] = evidence
    identity['paths'] = {'output_root': str(root), 'approval': str(REPORT_REL / 'APPROVAL.json'),
        'reports': str(REPORT_REL), 'raw': str(RAW_REL),
        'plan': str(ENV_REL / 'plan-identity.json'), 'frozen': str(ENV_REL / 'frozen-identity.json')}
    identity['budget']['batch_closeout_reserve_s'] = 2700.0
    identity['budget']['cost'] = 'unknown; no hard cap requires new explicit batch acceptance'
    identity['budget']['pre_execution_image_preparation_wall_s'] = prepared['wall_s']
    identity['deadline_policy'] = 'full attempt fits batch work window before start; every phase and cleanup capped by batch work deadline'
    identity['image_policy'] = 'inspect fixed IDs before each attempt and after cleanup; never rebuild during batch'
    identity['measurement_artifacts'] = {'environment': 'environment.json',
        'coverage_and_quality': 'measurement.json', 'request_and_tool_events': 'agent/events.jsonl',
        'resource_samples': 'summary.json#/samples', 'lifecycle_events': 'summary.json#/events'}
    identity['model']['actual_transport_attempts'] = 'unknown_without_transport_hook'
    identity['model']['immutable_version'] = False
    identity['monetary'] = {'actual_bill': 'unknown', 'hard_cap': None,
                          'explicit_batch_acceptance_required': True}
    identity['approval_flag'] = FLAG
    identity['execute_command'] = COMMAND
    harbor = ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages/harbor'
    extra = [Path(__file__), ROOT / 'docs/trace_contract.md',
             ROOT / '.venvs/docops-pilot-01/bin/python']
    extra += [harbor / p for p in ('environments/base.py', 'llms/base.py',
        'llms/lite_llm.py', 'verifier/verifier.py', 'models/task/task.py',
        'models/task/config.py', 'models/trial/paths.py', 'environments/docker/__init__.py',
        'environments/docker/docker-compose-base.yaml',
        'environments/docker/docker-compose-prebuilt.yaml',
        'environments/docker/docker-compose-no-network.yaml')]
    for path in extra:
        row = office.file_record(path, path.relative_to(ROOT))
        if row not in identity['code_and_runtime_files']:
            identity['code_and_runtime_files'].append(row)
    identity['interpreter'] = {'path': str(ROOT / '.venvs/docops-pilot-01/bin/python'),
                               'version': sys.version}
    identity['installed_dependencies'] = dict(sorted((d.metadata['Name'], d.version)
        for d in importlib.metadata.distributions()
        if str(harbor.parent) in str(d.locate_file(''))))
    return identity


def plan_mode(root: Path = ROOT) -> dict:
    identity = build_identity(root)
    digest = office.identity_sha(identity)
    env = root / ENV_REL
    match = False
    if (env / 'plan-identity.json').is_file() and (env / 'frozen-identity.json').is_file():
        plan = json.loads((env / 'plan-identity.json').read_text())
        frozen = json.loads((env / 'frozen-identity.json').read_text())
        match = (plan.get('identity') == frozen.get('identity') == identity
                 and plan.get('identity_sha256') == frozen.get('identity_sha256') == digest)
    attempts = list((root / RAW_REL).iterdir()) if (root / RAW_REL).exists() else []
    reports = list((root / REPORT_REL).iterdir()) if (root / REPORT_REL).exists() else []
    records = [p.name for p in reports if p.name != 'APPROVAL.json']
    approval_path = root / REPORT_REL / 'APPROVAL.json'
    approval_status = 'missing'
    if approval_path.exists():
        approval = json.loads(approval_path.read_text())
        scope = approval.get('scope', {})
        approval_status = 'valid' if (
            approval.get('schema') == 'docops-batch-approval-v1'
            and approval.get('collection') == COLLECTION
            and approval.get('user_approval') == 'approved'
            and approval.get('identity_sha256') == digest
            and isinstance(approval.get('approved_at_utc'), str)
            and approval.get('accept_unknown_cost_no_hard_cap') is True
            and scope.get('attempts') == 9 and scope.get('maximum_model_steps') == 360
            and scope.get('attempt_retry') == 0
            and 'entry_invocation' not in approval) else 'invalid_or_stale'
    clean = not attempts and not records
    return {'collection': COLLECTION, 'identity': identity, 'identity_sha256': digest,
        'identity_matches_frozen': match, 'existing_attempts': [p.name for p in attempts],
        'existing_namespace_records': records, 'approval_status': approval_status,
        'ready_for_approval': match and clean,
        'ready_for_execution': match and clean and approval_status == 'valid',
        'image_status': 'saved preparation verified; live inspect required before execution'}


def freeze(root: Path = ROOT) -> dict:
    plan = plan_mode(root)
    if plan['existing_attempts'] or plan['existing_namespace_records']:
        raise ValueError('occupied batch execution namespace')
    env = root / ENV_REL
    paths = [env / name for name in ('plan-identity.json', 'frozen-identity.json',
                                    'preparation-manifest.json')]
    if any(p.exists() for p in paths):
        raise FileExistsError('existing preparation freeze must not be overwritten')
    env.mkdir(parents=True, exist_ok=True)
    record = {'schema': 'docops-office-repeat-frozen-v1',
              'identity': plan['identity'], 'identity_sha256': plan['identity_sha256']}
    for path in paths[:2]:
        with path.open('x') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    identity = plan['identity']
    manifest = {'schema': 'docops-office-repeat-preparation-manifest-v1',
        'identity_sha256': plan['identity_sha256'], 'input_root': str(ROOT), 'output_root': str(root),
        'inputs': [*identity['code_and_runtime_files'], *identity['preparation_evidence'],
                   *(f for t in identity['tasks'] for f in t['files'])],
        'outputs': [office.file_record(p, p.relative_to(root)) for p in paths[:2]],
        'execution_authorized': False}
    with paths[2].open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return plan_mode(root)


def execute(root: Path, plan: dict) -> int:
    if not plan['ready_for_execution']:
        raise ValueError('full identity/approval/attempt gate refused execution')
    identity = plan['identity']
    started = time.monotonic() - identity['budget']['pre_execution_image_preparation_wall_s']
    os.environ.pop('DOCKER_CONTEXT', None)
    os.environ['DOCKER_HOST'] = office.ENDPOINT
    base = identity['base_image']
    if office.inspect_image(base['reference']) != (base['expected_id'], 'linux/arm64'):
        raise ValueError('fixed base image identity/platform mismatch')
    for task in identity['tasks']:
        if office.inspect_image(task['image_ref']) != (task['image_id'], 'linux/arm64'):
            raise ValueError('fixed task image missing/drift; no automatic restoration')
    office.load_model_credential()
    with (root / REPORT_REL / 'ATTEMPT_STARTED.json').open('x') as stream:
        json.dump({'collection': COLLECTION, 'identity_sha256': plan['identity_sha256'],
                   'started_at_utc': datetime.now(timezone.utc).isoformat(),
                   'attempt_retry': 0, 'scope': 'one sequential nine-attempt batch'}, stream)
    batch = office.run_batch(root, plan, identity, start_monotonic=started,
                             identity_builder=build_identity)
    return office.archive_batch(root, batch, identity, start_monotonic=started, build_logs=[])


def main(argv=None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--freeze', action='store_true')
    parser.add_argument(FLAG, action='store_true', dest='approved')
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not args.approved:
                raise ValueError('dedicated REPEAT-02 approval flag required')
            return execute(root, plan_mode(root))
        print(json.dumps(freeze(root) if args.freeze else plan_mode(root), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, office.BatchError) as exc:
        print(f'REFUSED: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
