#!/usr/bin/env python3
"""One fixed Excel measurement validation; reuse the existing DocOps attempt."""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
import docops_office_repeat_01_entry as office
import docops_word_resource_01_entry as shared

ROOT = office.ROOT
COLLECTION = 'DOCOPS-MEASUREMENT-VALIDATE-01'
TASK_KEY = 'atomic__excel_001_budget_bucket_totals_seed'
ENV_REL = Path('env/docops-measurement-validate-01')
REPORT_REL = Path('reports/resource') / COLLECTION
RAW_REL = Path('data/raw/generated') / COLLECTION
FLAG = '--i-approve-the-docops-measurement-validate-01'
COMMAND = ('PYTHONPATH=src LITELLM_LOCAL_MODEL_COST_MAP=True '
           '.venvs/docops-pilot-01/bin/python -B '
           'scripts/docops_measurement_validate_01_entry.py --execute ' + FLAG)


def build_identity(root: Path = ROOT) -> dict:
    """Bind current execution files; only the Excel task from the old freeze."""
    source = ROOT / office.ENV_DIR_REL / 'frozen-identity.json'
    frozen = json.loads(source.read_text())
    if office.identity_sha(frozen['identity']) != frozen['identity_sha256']:
        raise ValueError('source freeze digest mismatch')
    task = next(t for t in frozen['identity']['tasks'] if t['key'] == TASK_KEY)
    files = office.task_tree_records(TASK_KEY)
    if files != task['files']:
        raise ValueError('official Excel task files changed')
    restoration = ROOT / ENV_REL / 'image-restore.json'
    restored = json.loads(restoration.read_text())
    if (not restored['restored'] or restored['actual_image'] != restored['expected_image']
            or restored['actual_image']['id'] != task['image_id']
            or restored['actual_image']['reference'] != task['image_ref']
            or restored['base_image']['id'] != office.BASE_ID
            or restored['task_files'] != files):
        raise ValueError('restoration identity mismatch')
    evidence = [office.file_record(source, source.relative_to(ROOT)),
                office.file_record(restoration, restoration.relative_to(ROOT))]
    for row in [restored['log'], *restored['source_files']]:
        if office.file_record(ROOT / row['path'], Path(row['path'])) != row:
            raise ValueError('restoration evidence hash mismatch: ' + row['path'])
        if row not in evidence:
            evidence.append(row)
    code = office.fixed_code_records()
    extra = [Path(__file__), ROOT / 'docs/trace_contract.md',
             ROOT / '.venvs/docops-pilot-01/bin/python']
    # These are the installed, actually consumed Harbor files, not just source copies.
    harbor = ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages/harbor'
    extra += [harbor / p for p in ('environments/base.py', 'llms/base.py',
              'llms/lite_llm.py', 'verifier/verifier.py', 'models/task/task.py',
              'models/task/config.py', 'models/trial/paths.py',
              'environments/docker/__init__.py',
              'environments/docker/docker-compose-base.yaml',
              'environments/docker/docker-compose-prebuilt.yaml',
              'environments/docker/docker-compose-no-network.yaml')]
    for path in extra:
        row = office.file_record(path, path.relative_to(ROOT))
        if row not in code:
            code.append(row)
    config = {**office.run_config(TASK_KEY, 0, task['image_ref'], task['image_id']),
              'collection': COLLECTION, 'round': None}
    tools = office.actual_tool_names()
    if tools != office.TOOL_NAMES:
        raise ValueError('registered tool list drift')
    current_commit = subprocess.run(
        ['git', '-C', str(ROOT / 'references/repos/DocOps'), 'rev-parse', 'HEAD'],
        check=True, capture_output=True, text=True).stdout.strip()
    if current_commit != office.DOCOPS_COMMIT:
        raise ValueError('official task source commit drift')
    from agent_workload_characterization.collectors.execution_measurement import CONTRACT
    return {
        'schema': 'docops-single-measurement-identity-v1', 'collection': COLLECTION,
        'source_commit': office.DOCOPS_COMMIT, 'task': {**task, 'files': files},
        'code_and_runtime_files': code, 'preparation_evidence': evidence,
        'interpreter': {'path': str(ROOT / '.venvs/docops-pilot-01/bin/python'),
                        'version': sys.version},
        'installed_dependencies': dict(sorted((d.metadata['Name'], d.version)
                    for d in importlib.metadata.distributions()
                    if str(harbor.parent) in str(d.locate_file('')))),
        'docker_endpoint': office.ENDPOINT, 'base_image': restored['base_image'],
        'run_config': config, 'attempts': 1, 'attempt_retry': 0,
        'model': {'api_base': office.API_BASE, 'request_model': office.MODEL,
                  'response_model': 'record_from_response', 'immutable_version': False,
                  'stop': 'omitted', 'extra_body_none': 'omitted',
                  'framework_attempts_per_logical_call_max': 3,
                  'actual_transport_attempts': 'unknown_without_transport_evidence'},
        'tools': tools, 'word_only_tools_not_applicable_to_excel': office.WORD_ONLY_TOOLS,
        'cleanup': {'compose_delete_args': ['down', '--volumes', '--remove-orphans'],
                    'retain_images': True, 'verify_container_removal': True},
        'measurement_contract': {'contract': CONTRACT,
                    'source': 'docs/trace_contract.md#10-后续真实执行的必备记录real-run-measurement-01',
                    'outputs': ['environment.json', 'measurement.json', 'agent/events.jsonl'],
                    'tool_resource_attribution': 'shared_scope_window_only',
                    'post_cleanup_image_identity_required': task['image_id']},
        'monetary': {'actual_bill': 'unknown', 'hard_cap': None,
                    'explicit_acceptance_required_for_this_execution': True},
        'paths': {'output_root': str(root), 'approval': str(REPORT_REL / 'APPROVAL.json'),
                  'report': str(REPORT_REL / 'run-report.json'),
                  'attempt_root': str(RAW_REL / '<run_id>'),
                  'plan': str(ENV_REL / 'plan-identity.json'),
                  'frozen': str(ENV_REL / 'frozen-identity.json')},
        'approval_flag': FLAG, 'execute_command': COMMAND,
    }


def plan_mode(root: Path = ROOT) -> dict:
    identity = build_identity(root)
    digest = office.identity_sha(identity)
    env_dir = root / ENV_REL
    match = False
    if (env_dir / 'frozen-identity.json').is_file() and (env_dir / 'plan-identity.json').is_file():
        frozen = json.loads((env_dir / 'frozen-identity.json').read_text())
        saved = json.loads((env_dir / 'plan-identity.json').read_text())
        match = (frozen.get('identity') == saved.get('identity') == identity
                 and frozen.get('identity_sha256') == saved.get('identity_sha256') == digest)
    attempts = list((root / RAW_REL).iterdir()) if (root / RAW_REL).exists() else []
    reports = list((root / REPORT_REL).iterdir()) if (root / REPORT_REL).exists() else []
    existing = [p.name for p in reports if p.name != 'APPROVAL.json']
    approval_path = root / REPORT_REL / 'APPROVAL.json'
    approval_status = 'missing'
    if approval_path.exists():
        try:
            approval = json.loads(approval_path.read_text())
            approval_status = 'valid' if (
                approval.get('schema') == 'docops-single-run-approval-v1'
                and approval.get('collection') == COLLECTION
                and approval.get('user_approval') == 'approved'
                and approval.get('identity_sha256') == digest
                and approval.get('accept_unknown_cost_no_hard_cap') is True
                and 'entry_invocation' not in approval) else 'invalid_or_stale'
        except (OSError, ValueError, AttributeError):
            approval_status = 'invalid_or_stale'
    clean = not attempts and not existing
    return {'collection': COLLECTION, 'identity': identity, 'identity_sha256': digest,
            'identity_matches_frozen': match,
            'existing_attempts': [p.name for p in attempts],
            'existing_namespace_records': existing, 'approval_status': approval_status,
            'ready_for_approval': match and clean,
            'ready_for_execution': match and clean and approval_status == 'valid',
            'image_status': 'restoration_record_verified; live_inspect_required_before_execute'}


def freeze(root: Path = ROOT) -> dict:
    plan = plan_mode(root)
    if plan['existing_attempts'] or plan['existing_namespace_records']:
        raise ValueError('occupied execution namespace')
    env = root / ENV_REL
    destinations = [env / n for n in ('plan-identity.json', 'frozen-identity.json',
                                      'preparation-manifest.json')]
    if any(p.exists() for p in destinations):
        raise FileExistsError('preparation freeze already exists; never overwrite')
    env.mkdir(parents=True, exist_ok=True)
    record = {'schema': 'docops-measurement-freeze-v1',
              'identity': plan['identity'], 'identity_sha256': plan['identity_sha256']}
    for path in destinations[:2]:
        with path.open('x') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    manifest = {'schema': 'docops-measurement-preparation-manifest-v1',
                'identity_sha256': plan['identity_sha256'],
                'inputs': [*plan['identity']['code_and_runtime_files'],
                           *plan['identity']['preparation_evidence'], *plan['identity']['task']['files']],
                'outputs': [office.file_record(p, p.relative_to(root)) for p in destinations[:2]],
                'input_root': str(ROOT), 'output_root': str(root),
                'execution_authorized': False}
    with destinations[2].open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return plan_mode(root)


def execute(root: Path, plan: dict) -> int:
    if not plan['ready_for_execution']:
        raise ValueError('execution refused: identity/approval/attempt gate not satisfied')
    identity = plan['identity']
    task = identity['task']
    os.environ['DOCKER_HOST'] = office.ENDPOINT
    if office.inspect_image(task['image_ref']) != (task['image_id'], 'linux/arm64'):
        raise ValueError('fixed task image missing or identity drift; no automatic restoration')
    office.load_model_credential()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-excel001'
    run_plan = {**plan, 'run_id': run_id, 'run_config': identity['run_config'],
                'run_inputs': [*identity['code_and_runtime_files'],
                               *identity['preparation_evidence'], *identity['task']['files']]}
    summary = asyncio.run(shared.run_attempt(root, run_plan))
    run_dir = root / RAW_REL / run_id
    valid, bad = office.verify_run_archive(run_dir)
    # Reuse the shared attempt's actual, deadline-bounded post-stop query.
    # Do not add a second unbudgeted Docker query after its final archive.
    image_event = next(e for e in summary['events'] if e['phase'] == 'image_tag_after_stop')
    retained = image_event.get('id')
    retention_error = image_event.get('query_error')
    retention_verified = (retention_error is None and retained == task['image_id'])
    rc = shared.exit_code_for(summary)
    if not valid or not retention_verified:
        rc = rc or 7
    report = {'collection': COLLECTION, 'identity_sha256': plan['identity_sha256'],
              'run_id': run_id, 'summary': summary, 'exit_code': rc,
              'archive_valid': valid, 'archive_errors': bad,
              'image_after_cleanup': retained,
              'image_retention_check_error': retention_error,
              'image_retention_verified': retention_verified,
              'actual_bill': 'unknown'}
    report_path = root / REPORT_REL / 'run-report.json'
    with report_path.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    manifest = {'identity_sha256': plan['identity_sha256'],
                'inputs': [office.file_record(root / p, p) for p in
                           (REPORT_REL / 'APPROVAL.json', ENV_REL / 'plan-identity.json',
                            ENV_REL / 'frozen-identity.json', RAW_REL / run_id / 'manifest.json')],
                'outputs': [office.file_record(report_path, report_path.relative_to(root))]}
    with (root / REPORT_REL / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return rc


def main(argv=None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--freeze', action='store_true', help='offline preparation only; never overwrites')
    parser.add_argument(FLAG, action='store_true', dest='approved')
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not args.approved:
                raise ValueError('explicit collection-specific flag required')
            return execute(root, plan_mode(root))
        plan = freeze(root) if args.freeze else plan_mode(root)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, office.BatchError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
