#!/usr/bin/env python3
"""One fixed, sequential nine-attempt DocOps Office batch (offline-first)."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/lcq/agent_workload_characterization')
sys.path.insert(0, str(ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages'))
sys.path.insert(0, str(ROOT / 'references/repos/DocOps/harnesses'))
sys.path.insert(0, str(ROOT / 'src'))
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')

import docops_word_resource_01_entry as shared  # noqa: E402

COLLECTION = 'DOCOPS-OFFICE-REPEAT-01'
ENDPOINT = 'unix:///var/run/docker.sock'
DOCOPS_COMMIT = 'ccf7a751bc5c8a69c1cdd0400125d53455b33be3'
BASE_REF = 'harbor-claude-code-base:2.1.114'
BASE_ID = 'sha256:062bf50871c0e9d7d4a175643343746f27c785732596252d7ebe9ae0c08fe9b1'
PRIOR_ERRONEOUS_BASE_ID = 'sha256:062bf50871c0e9d7d4a175643343746f27c7857325962525d7ebe9ae0c08fe9b1'
MODEL = 'openai/deepseek-v4-flash'
API_BASE = 'https://api.deepseek.com/v1'
TASKS = (
    {'key': 'atomic__excel_001_budget_bucket_totals_seed', 'short': 'excel001',
     'rounds': (0, 2), 'asset': 'excel_001_budget_bucket_totals_seed.xlsx',
     'task_id': 'excel_001', 'doc_type': 'excel',
     'operation': 'formula-driven budget bucket aggregation'},
    {'key': 'atomic__ppt_008_bullet_editing_seed', 'short': 'ppt008',
     'rounds': (0, 1), 'asset': 'ppt_008_bullet_editing_seed.pptx',
     'task_id': 'ppt_008', 'doc_type': 'ppt',
     'operation': 'professional copy editing while preserving meaning'},
    {'key': 'atomic__pdf_004_audit_pages_reorder_seed', 'short': 'pdf004',
     'rounds': (0, 1, 2), 'asset': 'pdf_004_audit_pages_reorder_seed.pdf',
     'task_id': 'pdf_004', 'doc_type': 'pdf',
     'operation': 'audit PDF page reordering'},
)
ORDER = (
    ('atomic__excel_001_budget_bucket_totals_seed',
     'atomic__ppt_008_bullet_editing_seed',
     'atomic__pdf_004_audit_pages_reorder_seed'),
    ('atomic__ppt_008_bullet_editing_seed',
     'atomic__pdf_004_audit_pages_reorder_seed',
     'atomic__excel_001_budget_bucket_totals_seed'),
    ('atomic__pdf_004_audit_pages_reorder_seed',
     'atomic__excel_001_budget_bucket_totals_seed',
     'atomic__ppt_008_bullet_editing_seed'),
)
MAX_STEPS = 40
MAX_TOKENS = 32768
AGENT_S = 1200.0
VERIFIER_S = 600.0
TOTAL_WALL_S = 2700.0
CLEANUP_S = 300.0
SAMPLE_S = 0.5
BATCH_WALL_S = 450 * 60.0
BATCH_RESERVE_S = 15 * 60.0
PER_BUILD_S = 600.0
PREFLIGHT_S = 600.0
APPROVAL_REL = Path('reports/resource') / COLLECTION / 'APPROVAL.json'
REPORT_DIR_REL = Path('reports/resource') / COLLECTION
RAW_DIR_REL = Path('data/raw/generated') / COLLECTION
ENV_DIR_REL = Path('env/docops-office-repeat-01')
TASKS_ROOT = ROOT / 'references/repos/DocOps/tasks'
TOOL_NAMES = [
    'get_task_metadata', 'copy_file', 'inspect_document', 'word_replace_text',
    'word_insert_table_column', 'xlsx_read_sheet', 'xlsx_write_cells',
    'xlsx_set_formula', 'xlsx_highlight_cells', 'xlsx_delete_sheet',
    'xlsx_reorder_sheets', 'ppt_list_slides', 'ppt_replace_text',
    'ppt_reorder_slides', 'ppt_delete_slides', 'ppt_set_bullets',
    'pdf_extract_text', 'pdf_reorder_pages', 'pdf_delete_pages',
    'word_inspect_format', 'word_set_format',
]
WORD_ONLY_TOOLS = ['word_replace_text', 'word_insert_table_column',
                   'word_inspect_format', 'word_set_format']


class BatchError(RuntimeError):
    pass


def load_model_credential() -> None:
    """Use the inherited key, or read only a simple literal assignment for
    DEEPSEEK_API_KEY from .bashrc; never execute shell configuration."""
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        bashrc = Path('/home/lcq/.bashrc')
        try:
            lines = bashrc.read_text().splitlines()
        except OSError as exc:
            raise BatchError('DEEPSEEK_API_KEY unavailable; allowed literal source unreadable') from exc
        assignment = re.compile(
            r'''^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(['"])([^'"\n]*)\1\s*(?:#.*)?$''')
        found = []
        for line in lines:
            if not re.match(r'^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=', line):
                continue
            match = assignment.match(line)
            if not match:
                raise BatchError('DEEPSEEK_API_KEY is not a simple literal assignment')
            quote, value = match.groups()
            if quote == '"' and any(ch in value for ch in ('$','\\','`')):
                raise BatchError('DEEPSEEK_API_KEY double-quoted value is not literal')
            if value:
                found.append(value)
        if not found or any(value != found[0] for value in found[1:]):
            raise BatchError('DEEPSEEK_API_KEY literal assignment missing or ambiguous')
        key = found[0]
    os.environ['DEEPSEEK_API_KEY'] = key
    os.environ['OPENAI_API_KEY'] = key


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def file_record(path: Path, relative: Path) -> dict:
    return {'path': relative.as_posix(), 'bytes': path.stat().st_size,
            'sha256': sha256(path)}


def task_dir(key: str) -> Path:
    if key not in {t['key'] for t in TASKS}:
        raise BatchError('unregistered task key')
    return TASKS_ROOT / key


def task_spec(key: str) -> dict:
    return next(t for t in TASKS if t['key'] == key)


def task_tree_records(key: str) -> list[dict]:
    base = task_dir(key)
    files = sorted(p for p in base.rglob('*') if p.is_file())
    if not files:
        raise BatchError(f'task tree empty: {key}')
    spec = task_spec(key)
    required = {'task.toml', 'instruction.md', 'environment/Dockerfile',
                f'environment/{spec["asset"]}', 'environment/task_metadata.json',
                'tests/task_metadata.json', 'tests/test.sh',
                'tests/test_outputs.py', 'tests/verifier_utils.py'}
    present = {p.relative_to(base).as_posix() for p in files}
    if not required.issubset(present):
        raise BatchError(f'task inputs missing for {key}: {sorted(required - present)}')
    metadata = json.loads((base / 'environment/task_metadata.json').read_text())
    if (metadata.get('task_id') != spec['task_id'] or
            metadata.get('doc_type') != spec['doc_type'] or
            Path(metadata.get('input_path', '')).name != spec['asset']):
        raise BatchError(f'task metadata identity mismatch for {key}')
    with (base / 'task.toml').open('rb') as stream:
        task_toml = tomllib.load(stream)
    task_metadata = task_toml.get('metadata', {})
    if (task_metadata.get('task_id') != spec['task_id'] or
            task_metadata.get('doc_type') != spec['doc_type']):
        raise BatchError(f'task.toml identity mismatch for {key}')
    if (base / 'environment/Dockerfile').read_text().splitlines()[0].strip() != f'FROM {BASE_REF}':
        raise BatchError(f'task Dockerfile base mismatch for {key}')
    return [file_record(p, Path('references/repos/DocOps/tasks') / key / p.relative_to(base))
            for p in files]


def fixed_code_records() -> list[dict]:
    paths = [
        ROOT / 'scripts/docops_office_repeat_01_entry.py',
        ROOT / 'scripts/docops_word_resource_01_entry.py',
        ROOT / 'src/agent_workload_characterization/runners/docops_word_agent.py',
        ROOT / 'src/agent_workload_characterization/runners/docops_word_runtime.py',
        ROOT / 'src/agent_workload_characterization/runners/docops_environment.py',
        ROOT / 'src/agent_workload_characterization/runners/container_runtime.py',
        ROOT / 'src/agent_workload_characterization/collectors/host_process.py',
        ROOT / 'src/agent_workload_characterization/collectors/resource_sampler.py',
        ROOT / 'src/agent_workload_characterization/collectors/semantic_recorder.py',
        ROOT / 'src/agent_workload_characterization/collectors/execution_measurement.py',
        ROOT / 'references/repos/DocOps/harnesses/document_tools_agent.py',
        ROOT / 'references/repos/DocOps/harnesses/document_tools_runtime.py',
        ROOT / 'env/docops-arm64-word001/harbor-src/pyproject.toml',
        ROOT / 'env/docops-arm64-word001/harbor-src/src/harbor/environments/docker/docker.py',
        ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages/harbor/environments/docker/docker.py',
        ROOT / 'env/docops-arm64-word001/harbor-src/src/harbor/llms/lite_llm.py',
        ROOT / 'env/docops-arm64-word001/harbor-src/src/harbor/verifier/verifier.py',
        ROOT / 'env/docops-arm64-word001/harbor-venv-freeze.txt',
    ]
    return [file_record(p, p.relative_to(ROOT)) for p in paths]


def actual_tool_names() -> list[str]:
    from agent_workload_characterization.runners.docops_word_agent import DocOpsWordAgent
    agent = object.__new__(DocOpsWordAgent)
    return [item['name'] for item in agent._tool_specs()]


def run_config(key: str, round_index: int, image_ref: str, image_id: str, *,
               collection: str = COLLECTION) -> dict:
    spec = task_spec(key)
    return {
        'collection': collection, 'task_dir': str(task_dir(key)), 'task_key': key,
        'round': round_index, 'image_ref': image_ref, 'image_id': image_id,
        'input_asset': spec['asset'], 'max_steps': MAX_STEPS,
        'max_tokens': MAX_TOKENS, 'agent_budget_s': AGENT_S,
        'verifier_budget_s': VERIFIER_S, 'start_budget_s': 300.0,
        'setup_budget_s': 60.0, 'stop_budget_s': CLEANUP_S,
        'total_wall_s': TOTAL_WALL_S, 'cleanup_reserve_s': CLEANUP_S,
        'sample_interval_s': SAMPLE_S, 'cpu_limit': 1, 'memory_mb': 4096,
        'storage_mb': 10240, 'network': 'none',
    }


def attempt_order() -> list[dict]:
    return [{'round': i, 'task_key': key}
            for i, row in enumerate(ORDER) for key in row]


def load_initial_builds(env_dir: Path, root: Path = ROOT) -> list[dict] | None:
    """Read the already recorded first builds without rewriting their evidence."""
    path = env_dir / 'image-builds.json'
    if not path.exists():
        return None
    try:
        builds = json.loads(path.read_text())['builds']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BatchError('existing image-builds.json is unreadable') from exc
    if not isinstance(builds, list):
        raise BatchError('existing image-builds.json has invalid build list')
    by_key = {row.get('task_key'): row for row in builds if isinstance(row, dict)}
    if len(builds) != len(TASKS) or set(by_key) != {task['key'] for task in TASKS}:
        raise BatchError('existing initial image build record is incomplete or duplicated')
    for task in TASKS:
        row = by_key[task['key']]
        image = row.get('image', {})
        log = row.get('log', {})
        log_path = root / log.get('path', '')
        expected_context = task_dir(task['key']) / 'environment'
        expected_command = ['docker', '--host', ENDPOINT, 'build', '--pull=false',
                            '--network=none', '--platform=linux/arm64', '-t',
                            image_ref(task['key']), '.']
        if (row.get('returncode') != 0 or image.get('reference') != image_ref(task['key'])
                or not is_full_image_id(image.get('id', ''))
                or image.get('platform') != 'linux/arm64'
                or row.get('cwd') != str(expected_context)
                or row.get('command') != expected_command
                or not log_path.is_file()
                or log_path.stat().st_size != log.get('bytes')
                or sha256(log_path) != log.get('sha256')):
            raise BatchError(f'existing initial build evidence mismatch for {task["key"]}')
    return [by_key[task['key']] for task in TASKS]


def resumable_preparation_namespace(env_dir: Path, root: Path = ROOT) -> bool:
    """Accept only the known pre-attempt records left by the two stops."""
    try:
        original = json.loads((env_dir / 'execution-stop.json').read_text())
        if (original.get('schema') != 'docops-office-repeat-stop-v1'
                or original.get('status') != 'stopped'
                or original.get('error_type') != 'BatchError'
                or 'base image identity/platform mismatch' not in original.get('detail', '')
                or BASE_ID not in original.get('detail', '')):
            return False
        for path in env_dir.glob('execution-stop*.json'):
            stop = json.loads(path.read_text())
            if stop.get('schema') != 'docops-office-repeat-stop-v1' or stop.get('status') != 'stopped':
                return False
        base = json.loads((env_dir / 'base-image.json').read_text())
        correction = json.loads((env_dir / 'base-image-correction.json').read_text())
        if (base != {'reference': BASE_REF, 'id': BASE_ID, 'platform': 'linux/arm64'}
                or correction.get('historical_erroneous_base_id') != PRIOR_ERRONEOUS_BASE_ID
                or correction.get('corrected_base_id') != BASE_ID
                or correction.get('historical_files_modified') is not False):
            return False
        builds = load_initial_builds(env_dir, root)
        if builds is None:
            return False
        allowed_files = {'execution-stop.json', 'base-image.json',
                         'base-image-correction.json', 'image-builds.json'}
        for path in env_dir.iterdir():
            if path.is_file() and path.name not in allowed_files:
                if not (path.name.startswith('execution-stop-') and path.suffix == '.json'):
                    return False
            elif path.is_dir() and path.name not in {'image-builds', 'preflight'}:
                return False
        expected_logs = {Path(row['log']['path']).relative_to(ENV_DIR_REL).as_posix()
                         for row in builds}
        actual_logs = {path.relative_to(env_dir).as_posix()
                       for path in (env_dir / 'image-builds').rglob('*') if path.is_file()}
        if expected_logs != actual_logs:
            return False
        for path in (env_dir / 'preflight').rglob('*'):
            if path.is_file():
                return False
            relative = path.relative_to(env_dir / 'preflight').parts
            if (len(relative) > 4 or not relative
                    or relative[0] not in {task['short'] for task in TASKS}
                    or (len(relative) > 1 and relative[1] != 'trial')
                    or (len(relative) > 2 and relative[2] not in {'agent', 'artifacts', 'verifier'})):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def image_ref(key: str) -> str:
    return f'docops-office-repeat-01:{task_spec(key)["short"]}'


def build_identity(image_ids: dict[str, str]) -> dict:
    from agent_workload_characterization.collectors.execution_measurement import CONTRACT
    commit = subprocess.run(['git', '-C', str(ROOT / 'references/repos/DocOps'),
                             'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True, timeout=10).stdout.strip()
    if commit != DOCOPS_COMMIT:
        raise BatchError(f'DocOps commit mismatch: {commit}')
    dirty = subprocess.run(['git', '-C', str(ROOT / 'references/repos/DocOps'),
                            'status', '--porcelain'], capture_output=True, text=True,
                           check=True, timeout=10).stdout.strip()
    if dirty:
        raise BatchError('DocOps source tree is not clean at the registered commit')
    tool_names = actual_tool_names()
    if tool_names != TOOL_NAMES:
        raise BatchError('registered tool list does not match production Agent tool specs')
    code = fixed_code_records()
    task_records = {task['key']: task_tree_records(task['key']) for task in TASKS}
    return {
        'schema': 'docops-office-repeat-identity-v1', 'collection': COLLECTION,
        'measurement_contract': CONTRACT,
        'docops_commit': commit,
        'docker_endpoint': ENDPOINT,
        'base_image': {'reference': BASE_REF, 'expected_id': BASE_ID,
                       'platform': 'linux/arm64'},
        'tasks': [{**{k: task[k] for k in ('key', 'short', 'task_id', 'doc_type', 'asset', 'operation')},
                   'task_dir': str(task_dir(task['key'])),
                   'image_ref': image_ref(task['key']),
                   'image_id': image_ids[task['key']],
                   'files': task_records[task['key']]} for task in TASKS],
        'code_and_runtime_files': code,
        'model': {'api_base': API_BASE, 'request_model': MODEL,
                  'response_model': 'record_actual_per_request',
                  'credential_name': 'DEEPSEEK_API_KEY',
                  'json_action': {'stop_omitted': True, 'extra_body_none_omitted': True,
                                  'thinking_mode': 'provider_default'}},
        'tools': {'same_tool_names_all_tasks': tool_names,
                  'word_tools_not_applicable_to_excel_ppt_pdf': WORD_ONLY_TOOLS,
                  'tool_source': 'fixed project DocOpsWordAgent tool specs'},
        'schedule': [{'round': i, 'tasks': list(row)} for i, row in enumerate(ORDER)],
        'attempt_count': 9, 'attempt_retry': 0,
        'cleanup': {'compose_delete_args': ['down', '--volumes', '--remove-orphans'],
                    'retain_images': True, 'errors': 'propagate_to_entry_and_verify_removal'},
        'budget': {'per_attempt': {'max_steps': MAX_STEPS,
                    'max_tokens_per_request': MAX_TOKENS, 'agent_s': AGENT_S,
                    'verifier_s': VERIFIER_S, 'wall_s': TOTAL_WALL_S,
                    'cleanup_reserve_s': CLEANUP_S, 'cpu': 1, 'memory_gib': 4,
                    'storage_gib': 10, 'network': 'none', 'sample_s': SAMPLE_S},
                   'batch_wall_s': BATCH_WALL_S,
                   'batch_closeout_reserve_s': BATCH_RESERVE_S,
                   'framework_retry': 'up to 3 actual tries per logical call',
                   'maximum_model_steps': 360,
                   'cost': 'unknown; no hard amount cap approved for this batch'},
        'paths': {'approval': APPROVAL_REL.as_posix(),
                  'reports': REPORT_DIR_REL.as_posix(),
                  'raw': RAW_DIR_REL.as_posix(),
                  'plan': (ENV_DIR_REL / 'plan-identity.json').as_posix(),
                  'frozen': (ENV_DIR_REL / 'frozen-identity.json').as_posix()},
        'identity_limits': ['request alias is not immutable model version',
                            'not representative of all Office tasks'],
    }


def identity_sha(identity: dict) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def docker(args: list[str], *, cwd: Path | None = None, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(['docker', '--host', ENDPOINT, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=timeout)


def inspect_image(ref: str) -> tuple[str, str] | None:
    result = docker(['image', 'inspect', ref, '--format', '{{.Id}} {{.Os}}/{{.Architecture}}'])
    if result.returncode:
        message = (result.stderr or '') + (result.stdout or '')
        if 'No such image' in message or 'no such image' in message:
            return None
        raise BatchError(f'image inspection failed for {ref}: {message[:240]}')
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        raise BatchError(f'image inspect returned malformed identity for {ref}')
    return parts[0], parts[1]


def is_full_image_id(value: str) -> bool:
    return re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None


def build_task_image(key: str, ref: str, env_root: Path, *, timeout: float,
                     log_label: str) -> dict:
    context = task_dir(key) / 'environment'
    log_path = env_root / 'image-builds' / f'{task_spec(key)["short"]}-{log_label}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if inspect_image(ref) is not None:
        raise BatchError(f'refusing to overwrite existing image tag {ref}')
    argv = ['docker', '--host', ENDPOINT, 'build', '--pull=false',
            '--network=none',
            '--platform=linux/arm64', '-t', ref, '.']
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=context, capture_output=True, text=True,
                                timeout=min(PER_BUILD_S, timeout))
        output = (result.stdout or '') + (result.stderr or '')
        rc = result.returncode
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ''
        err = exc.stderr or ''
        if isinstance(out, bytes): out = out.decode('utf-8', 'replace')
        if isinstance(err, bytes): err = err.decode('utf-8', 'replace')
        output, rc = str(out) + str(err), 124
    log_path.write_text(output, encoding='utf-8')
    info = {'task_key': key, 'command': argv, 'cwd': str(context),
            'duration_s': round(time.monotonic() - started, 3), 'returncode': rc,
            'log': {'path': log_path.relative_to(ROOT).as_posix(),
                    'bytes': log_path.stat().st_size, 'sha256': sha256(log_path)}}
    if rc != 0:
        raise BatchError(f'image build failed for {key} with code {rc}')
    image = inspect_image(ref)
    if image is None or image[1] != 'linux/arm64':
        raise BatchError(f'built image missing or wrong architecture for {key}: {image}')
    info['image'] = {'reference': ref, 'id': image[0], 'platform': image[1]}
    return info


def verify_base() -> dict:
    if not is_full_image_id(BASE_ID):
        raise BatchError('registered base image ID must be sha256 plus 64 lowercase hex characters')
    info = inspect_image(BASE_REF)
    if info is not None and not is_full_image_id(info[0]):
        raise BatchError('inspected base image ID is not a full sha256 identity')
    if info != (BASE_ID, 'linux/arm64'):
        raise BatchError(f'base image identity/platform mismatch: {info}')
    return {'reference': BASE_REF, 'id': info[0], 'platform': info[1]}


def restore_or_build(key: str, expected_id: str, env_root: Path,
                     *, allow_initial_build: bool, timeout: float,
                     log_label: str) -> dict:
    ref = image_ref(key)
    image = inspect_image(ref)
    if image is not None:
        if image != (expected_id, 'linux/arm64'):
            raise BatchError(f'tag identity drift for {key}: {image}')
        return {'status': 'already_tagged', 'id': image[0]}
    by_id = inspect_image(expected_id)
    if by_id is not None:
        if by_id != (expected_id, 'linux/arm64'):
            raise BatchError(f'image ID platform mismatch for {key}: {by_id}')
        result = docker(['image', 'tag', expected_id, ref], timeout=30)
        if result.returncode:
            raise BatchError(f'could not restore image tag for {key}')
        return {'status': 'retagged_exact_id', 'id': expected_id}
    if not allow_initial_build:
        raise BatchError(f'no frozen task image available for {key}')
    if time.monotonic() + PER_BUILD_S > timeout:
        raise BatchError(f'insufficient batch time for bounded build: {key}')
    info = build_task_image(key, ref, env_root, timeout=timeout,
                            log_label=log_label)
    if info['image']['id'] != expected_id:
        raise BatchError(f'restored image differs from frozen ID for {key}')
    return {'status': f'built_{log_label}', 'id': expected_id,
            'build': info}


async def preflight_one(key: str, config: dict, env_root: Path,
                        timeout_s: float = PREFLIGHT_S) -> dict:
    from harbor.environments.docker.docker import _sanitize_docker_compose_project_name
    from harbor.models.trial.paths import TrialPaths
    from agent_workload_characterization.runners.container_runtime import ContainerHandle, ContainerSpec
    stamp = task_spec(key)['short']
    trial = TrialPaths(trial_dir=env_root / 'preflight' / stamp / 'trial')
    trial.mkdir()
    env = None
    handle = None
    project = _sanitize_docker_compose_project_name('preflight-' + stamp)
    result = {'task_key': key, 'status': 'incomplete', 'container_removal': 'unknown'}
    started = time.monotonic()
    try:
        env = shared.build_environment('preflight-' + stamp, trial, config)
        await asyncio.wait_for(env.start(force_build=False), timeout=timeout_s)
        containers = shared.compose_containers(project)
        if len(containers) != 1 or not containers[0][1].startswith(project):
            raise BatchError(f'preflight container ownership ambiguous for {key}')
        cid, cname = containers[0]
        runtime = shared.build_runtime(config)
        handle = ContainerHandle(container_id=cid, spec=ContainerSpec(
            run_id='preflight-' + stamp, scope='agent_container',
            image=config['image_ref'], network='none'))
        runtime._resolve_cgroup(handle)
        agent = shared.build_agent(trial.agent_dir, config)
        await asyncio.wait_for(agent.setup(env), timeout=60.0)
        input_path = f'/root/{config["input_asset"]}'
        module = 'docx,openpyxl,pptx,pypdf,pdfplumber + uploaded runtime import'
        check_source = (
            "import importlib.util,json; from pathlib import Path; "
            "import docx,openpyxl,pptx,pypdf,pdfplumber; "
            f"asset=Path({input_path!r}); assert asset.is_file() and asset.stat().st_size>0; "
            "meta_path=Path('/root/task_metadata.json'); assert meta_path.is_file(); "
            f"meta=json.loads(meta_path.read_text()); assert Path(meta['input_path']).name=={config['input_asset']!r}; "
            "runtime=Path('/root/document_tools_runtime.py'); assert runtime.is_file(); "
            "spec=importlib.util.spec_from_file_location('docops_runtime_preflight',runtime); "
            "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
            "print('preflight_ok')")
        command = 'python3 -c ' + repr(check_source)
        check = await asyncio.wait_for(env.exec(command=command), timeout=60.0)
        rc = getattr(check, 'return_code', getattr(check, 'returncode', None))
        if rc != 0 or 'preflight_ok' not in (getattr(check, 'stdout', '') or ''):
            raise BatchError(f'preflight in-container check failed for {key}')
        result.update({'status': 'passed', 'container': {'id': cid, 'name': cname},
                       'module_imported': module,
                       'asset_readable': config['input_asset'],
                       'metadata_uploaded': True, 'runtime_uploaded': True})
    except Exception as exc:
        result.update({'status': 'failed', 'error_type': type(exc).__name__,
                       'error': str(exc)[:300]})
    finally:
        if env is not None:
            try:
                await asyncio.wait_for(env.stop(delete=True), timeout=120.0)
            except Exception as exc:
                result['stop_error'] = type(exc).__name__
        if handle is not None:
            try:
                result['container_removal'] = shared.build_runtime(config).verify_removal(
                    handle, timeout_s=30.0)
            except Exception as exc:
                result['container_removal'] = 'check_failed:' + type(exc).__name__
        else:
            try:
                remaining = shared.compose_containers(project)
                result['container_removal'] = 'removed' if not remaining else 'still_exists'
            except Exception as exc:
                result['container_removal'] = 'check_failed:' + type(exc).__name__
        result['wall_s'] = round(time.monotonic() - started, 3)
    if (result['status'] != 'passed' or result['container_removal'] != 'removed'
            or 'stop_error' in result):
        result['status'] = 'failed'
    return result


def plan_mode(root: Path = ROOT) -> dict:
    collisions = []
    for rel in (APPROVAL_REL, RAW_DIR_REL, REPORT_DIR_REL):
        path = root / rel
        if path.exists():
            collisions.append(rel.as_posix())
    env_path = root / ENV_DIR_REL
    prior_stop = resumable_preparation_namespace(env_path, root) if env_path.exists() else False
    if env_path.exists():
        if not prior_stop:
            collisions.append(ENV_DIR_REL.as_posix())
    current = subprocess.run(['git', '-C', str(ROOT / 'references/repos/DocOps'),
                              'rev-parse', 'HEAD'], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    return {'collection': COLLECTION, 'source_commit': current,
            'registered_commit': DOCOPS_COMMIT, 'commit_matches': current == DOCOPS_COMMIT,
            'order': [{'round': i, 'tasks': list(row)} for i, row in enumerate(ORDER)],
            'attempt_count': 9, 'max_steps': MAX_STEPS,
            'api_base': API_BASE, 'request_model': MODEL,
            'base_image_expected_id': BASE_ID,
            'paths_clear': not collisions, 'collisions': collisions,
            'preserved_prior_stop_record': prior_stop,
            'preparation_namespace_status': (
                'contains_preserved_pre_attempt_stop_record' if prior_stop else
                'clear' if not env_path.exists() else 'occupied'),
            'ready': current == DOCOPS_COMMIT and not collisions}


def _run_dir(root: Path, run_id: str) -> Path:
    return root / RAW_DIR_REL / run_id


def verify_run_archive(run_dir: Path) -> tuple[bool, list[str]]:
    errors = []
    try:
        manifest = json.loads((run_dir / 'manifest.json').read_text())
        for item in manifest.get('outputs', []):
            path = run_dir / item['path']
            if not path.is_file() or path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
                errors.append(item['path'])
    except Exception as exc:
        errors.append('manifest:' + type(exc).__name__)
    return not errors, errors


def project_run_evidence(run_dir: Path, summary: dict) -> dict:
    """Summarize persisted action/resource fields without exposing prompts or
    full tool arguments. Logical request logs are not transport retry counts."""
    from collections import Counter
    call_files = sorted((run_dir / 'agent').glob('llm_call_*.json'),
                        key=lambda p: int(p.stem.rsplit('_', 1)[1]))
    actions, response_models, request_models = [], Counter(), Counter()
    logs = []
    for path in call_files:
        try:
            log = json.loads(path.read_text())
            logs.append(log)
            response = json.loads(log.get('original_response') or '{}')
            response_model = response.get('model')
            if response_model:
                response_models[response_model] += 1
            request_model = log.get('model')
            provider = log.get('custom_llm_provider')
            if provider and request_model:
                request_model = f'{provider}/{request_model}'
            if request_model:
                request_models[request_model] += 1
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            continue
    event_path = run_dir / 'agent/events.jsonl'
    event_rows = [json.loads(line) for line in event_path.read_text().splitlines()]
    decisions = [e['attrs'] for e in event_rows if e['kind'] == 'agent_action']
    action_counts = Counter(a['action'] for a in decisions)
    finish_at = next((i for i,e in enumerate(event_rows)
                      if e['kind'] == 'agent_action' and e['attrs']['action'] == 'finish'), None)
    after_finish = (sum(e['kind'] == 'llm_request' and e['status'] == 'open'
                        for e in event_rows[finish_at + 1:]) if finish_at is not None else None)
    opens = {e['event_id']: e['attrs'] for e in event_rows
             if e['kind'] == 'tool_call' and e['status'] == 'open'}
    tool_counts = Counter(a['tool_name'] for a in opens.values() if a['role'] == 'agent')
    category_map = {
        'copy_file': 'file_copy', 'inspect_document': 'document_structure_inspection',
        'word_inspect_format': 'format_inspection', 'word_set_format': 'format_edit',
        'word_replace_text': 'text_edit', 'word_insert_table_column': 'table_edit',
        'xlsx_read_sheet': 'spreadsheet_inspection', 'xlsx_write_cells': 'spreadsheet_edit',
        'xlsx_set_formula': 'spreadsheet_formula_edit',
        'xlsx_highlight_cells': 'spreadsheet_format_edit',
        'xlsx_delete_sheet': 'spreadsheet_structure_edit',
        'xlsx_reorder_sheets': 'spreadsheet_structure_edit',
        'ppt_list_slides': 'presentation_inspection',
        'ppt_replace_text': 'presentation_text_edit',
        'ppt_reorder_slides': 'presentation_structure_edit',
        'ppt_delete_slides': 'presentation_structure_edit',
        'ppt_set_bullets': 'presentation_bullet_edit',
        'pdf_extract_text': 'pdf_inspection', 'pdf_reorder_pages': 'pdf_page_reorder',
        'pdf_delete_pages': 'pdf_page_edit',
    }
    categories = Counter(category_map.get(name, 'unknown_or_other')
                         for name, count in tool_counts.items() for _ in range(count))
    returns = Counter()
    for e in event_rows:
        if e['kind'] != 'tool_call' or e['status'] not in ('closed', 'error', 'unclosed'):
            continue
        if opens[e['event_id']]['role'] != 'agent':
            continue
        ok = e['attrs'].get('ok')
        label = ('ok_true' if ok is True else 'ok_false' if ok is False else 'unknown_or_censored')
        returns[label] += 1
    bootstrap = Counter(a['tool_name'] for a in opens.values() if a['role'] == 'bootstrap')
    samples = summary.get('samples', [])
    sample_times = [x.get('t_monotonic_ns') for x in samples
                    if isinstance(x.get('t_monotonic_ns'), int)]
    cpu = [x.get('container', {}).get('cpu_usage_usec') for x in samples]
    cpu_valid = [x for x in cpu if isinstance(x, int) and not isinstance(x, bool)]
    cpu_monotonic = all(a <= b for a, b in zip(cpu_valid, cpu_valid[1:]))
    current_mem = [x.get('container', {}).get('mem_current_bytes') for x in samples]
    current_mem = [x for x in current_mem if isinstance(x, int) and not isinstance(x, bool)]
    peak_mem = [x.get('container', {}).get('mem_peak_bytes') for x in samples]
    peak_mem = [x for x in peak_mem if isinstance(x, int) and not isinstance(x, bool)]
    host_rss = [x.get('host_agent', {}).get('rss_bytes') for x in samples]
    host_rss = [x for x in host_rss if isinstance(x, int) and not isinstance(x, bool)]
    intervals = [(b - a) / 1e9 for a, b in zip(sample_times, sample_times[1:]) if b >= a]
    event_map = {e.get('phase'): e.get('t_monotonic_ns') for e in summary.get('events', [])}
    phase_pairs = {'harbor_start': ('harbor_start_begin', 'harbor_start_done'),
                   'agent_setup': ('agent_setup_begin', 'agent_setup_done'),
                   'agent': ('agent_begin', 'agent_end'),
                   'verifier': ('verifier_begin', 'verifier_end'),
                   'harbor_stop': ('harbor_stop_begin', 'harbor_stop_done')}
    phase_wall = {}
    for name, (begin, end) in phase_pairs.items():
        a, b = event_map.get(begin), event_map.get(end)
        phase_wall[name] = (b - a) / 1e9 if isinstance(a, int) and isinstance(b, int) and b >= a else None
    ctrf_path = run_dir / 'verifier/ctrf.json'
    failed_tests = []
    if ctrf_path.is_file():
        try:
            ctrf = json.loads(ctrf_path.read_text())
            failed_tests = [t.get('name') for t in ctrf.get('results', {}).get('tests', [])
                            if t.get('status') in ('failed', 'failure', 'error') and t.get('name')]
        except (OSError, ValueError, TypeError):
            failed_tests = []
    cpu_delta = ((cpu_valid[-1] - cpu_valid[0]) / 1e6
                 if len(cpu_valid) >= 2 and cpu_monotonic else None)
    sample_window = ((sample_times[-1] - sample_times[0]) / 1e9
                     if len(sample_times) >= 2 and sample_times[-1] >= sample_times[0] else None)
    return {
        'model_requests_logged': summary['measurement']['expected_requests'],
        'measurement': summary['measurement'],
        'request_model_counts': dict(request_models),
        'response_model_counts': dict(response_models),
        'action_counts': dict(action_counts), 'tool_name_counts': dict(tool_counts),
        'requests_after_finish': after_finish,
        'tool_activity_category_counts': dict(categories),
        'tool_return_status_counts': dict(returns),
        'bootstrap_tool_counts_from_events': dict(bootstrap),
        'usage_from_agent_context': {k: summary.get('outcome', {}).get('phases', {}).get('agent', {}).get(k)
            for k in ('n_input_tokens', 'n_output_tokens', 'n_cache_tokens', 'cost_usd')},
        'verifier_failed_test_ids': failed_tests,
        'resources': {
            'attempt_wall_s': summary.get('wall_s'), 'sample_count': len(samples),
            'sample_window_s': sample_window,
            'sample_interval_s': {'min': min(intervals) if intervals else None,
                                  'max': max(intervals) if intervals else None},
            'container_cpu_core_s': cpu_delta,
            'container_cpu_status': 'valid_endpoint_delta' if cpu_delta is not None else
                                    'unavailable_counter_missing_or_rollback',
            'memory_current_sample_peak_bytes': max(current_mem) if current_mem else None,
            'kernel_memory_peak_bytes': max(peak_mem) if peak_mem else None,
            'host_agent_rss_sample_peak_bytes': max(host_rss) if host_rss else None,
            'phase_wall_s': phase_wall,
        },
        'request_count_semantics': 'saved logical request logs; provider/framework transport retries may not be separately represented',
    }


def run_batch(root: Path, plan: dict, identity: dict, *, start_monotonic: float,
              docker_enabled: bool = True, identity_builder=None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    collection = identity['collection']
    raw_root = root / identity['paths']['raw']
    batch_wall = identity['budget']['batch_wall_s']
    batch_reserve = identity['budget']['batch_closeout_reserve_s']
    work_deadline = start_monotonic + batch_wall - batch_reserve
    frozen_id = identity_sha(identity)
    task_id_map = {t['key']: t['image_id'] for t in identity['tasks']}
    task_refs = {t['key']: t['image_ref'] for t in identity['tasks']}
    results = []
    stopped_reason = None
    specs = attempt_order()
    for i, item in enumerate(specs):
        key, round_index = item['task_key'], item['round']
        config = run_config(key, round_index, task_refs[key], task_id_map[key],
                            collection=collection)
        try:
            live = identity_builder(root) if identity_builder else build_identity(task_id_map)
            if live != identity or identity_sha(live) != frozen_id:
                raise BatchError('live files or configuration differ from frozen batch identity')
        except Exception as exc:
            stopped_reason = f'identity_drift:{type(exc).__name__}'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i:])
            break
        remaining = work_deadline - time.monotonic()
        if remaining < TOTAL_WALL_S:
            stopped_reason = 'insufficient_remaining_budget_for_full_attempt'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i:])
            break
        image_action = {'status': 'not_checked'}
        if docker_enabled:
            try:
                observed = inspect_image(task_refs[key])
                if observed != (task_id_map[key], 'linux/arm64'):
                    raise BatchError('frozen task image missing or identity changed')
                image_action = {'status': 'verified_existing', 'id': observed[0]}
            except Exception as exc:
                stopped_reason = f'image_identity_failed:{type(exc).__name__}'
                results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                                'status': 'not_executed'} for tail in specs[i:])
                break
        if work_deadline - time.monotonic() < TOTAL_WALL_S:
            stopped_reason = 'insufficient_remaining_budget_after_image_check'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i:])
            break
        now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run_id = f'{now}-r{round_index}-{task_spec(key)["short"]}'
        run_dir = raw_root / run_id
        if run_dir.exists():
            stopped_reason = 'run_id_collision'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i:])
            break
        task_inputs = next(t['files'] for t in identity['tasks'] if t['key'] == key)
        inputs = [*identity['code_and_runtime_files'],
                  *identity.get('preparation_evidence', []), *task_inputs]
        run_plan = {'run_id': run_id, 'identity_sha256': frozen_id,
                    'identity': {'files': {'task_toml': {'sha256': next(x['sha256'] for x in inputs if x['path'].endswith('/task.toml'))},
                        'instruction': {'sha256': next(x['sha256'] for x in inputs if x['path'].endswith('/instruction.md'))},
                        'task_metadata': {'sha256': next(x['sha256'] for x in inputs if x['path'].endswith('/environment/task_metadata.json'))}}},
                    'run_config': config, 'run_inputs': inputs,
                    'batch_work_deadline_monotonic': work_deadline}
        one_start = time.monotonic()
        try:
            summary = asyncio.run(shared.run_attempt(root, run_plan))
            archive_ok, archive_errors = verify_run_archive(run_dir)
            rc = shared.exit_code_for(summary)
            image_event = next(e for e in summary['events'] if e['phase'] == 'image_tag_after_stop')
            retained = (image_event.get('query_error') is None
                        and image_event.get('id') == task_id_map[key])
            if not retained:
                rc = rc or 7
            status = 'executed' if archive_ok and rc == 0 else 'failed'
            evidence = project_run_evidence(run_dir, summary)
            live_after = identity_builder(root) if identity_builder else build_identity(task_id_map)
            identity_verified = live_after == identity and identity_sha(live_after) == frozen_id
            if not identity_verified:
                rc = rc or 7
                status = 'failed'
            results.append({'round': round_index, 'task_key': key, 'run_id': run_id,
                            'status': status, 'returncode': rc,
                            'identity_sha256': frozen_id,
                            'wall_s': summary.get('wall_s'),
                            'termination': summary.get('outcome', {}).get('phases', {}).get('agent', {}).get('status'),
                            'reward': summary.get('outcome', {}).get('phases', {}).get('verifier', {}).get('reward'),
                            'archive_verified': archive_ok, 'archive_errors': archive_errors,
                            'image_retention_verified': retained,
                            'identity_after_attempt_verified': identity_verified,
                            'image_after_cleanup': image_event,
                            'image_action': image_action, **evidence})
            if not archive_ok or rc != 0:
                stopped_reason = 'attempt_infrastructure_or_archive_failure'
                results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                                'status': 'not_executed'} for tail in specs[i + 1:])
                break
        except Exception as exc:
            results.append({'round': round_index, 'task_key': key, 'run_id': run_id,
                            'status': 'failed', 'error_type': type(exc).__name__,
                            'error': str(exc)[:300],
                            'image_action': image_action})
            stopped_reason = f'attempt_exception:{type(exc).__name__}'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i + 1:])
            break
        if time.monotonic() > work_deadline:
            stopped_reason = 'batch_work_deadline_exhausted'
            results.extend({'round': tail['round'], 'task_key': tail['task_key'],
                            'status': 'not_executed'} for tail in specs[i + 1:])
            break
    def linear_quantile(values: list[float], q: float) -> float | None:
        values = sorted(values)
        if not values:
            return None
        pos = (len(values) - 1) * q
        lo, hi = int(pos), min(int(pos) + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)

    by_task = {}
    for task in TASKS:
        key = task['key']
        rows = [r for r in results if r['task_key'] == key]
        executed = [r for r in rows if r.get('status') in ('executed', 'failed')]
        resource_stats = {}
        for label, extract in (
            ('wall_s', lambda r: r.get('resources', {}).get('attempt_wall_s')),
            ('container_cpu_core_s', lambda r: r.get('resources', {}).get('container_cpu_core_s')),
            ('memory_current_sample_peak_bytes', lambda r: r.get('resources', {}).get('memory_current_sample_peak_bytes')),
            ('kernel_memory_peak_bytes', lambda r: r.get('resources', {}).get('kernel_memory_peak_bytes')),
            ('host_agent_rss_sample_peak_bytes', lambda r: r.get('resources', {}).get('host_agent_rss_sample_peak_bytes')),
        ):
            vals = [extract(r) for r in executed]
            vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
            entry = {'n': len(vals), 'raw_points': vals}
            if len(vals) == 3:
                entry.update({'median': linear_quantile(vals, .5),
                              'q1': linear_quantile(vals, .25),
                              'q3': linear_quantile(vals, .75),
                              'iqr': linear_quantile(vals, .75) - linear_quantile(vals, .25),
                              'quantile_method': 'linear interpolation at (n-1)*p'})
            else:
                entry['summary_status'] = 'three_valid_points_not_available'
            resource_stats[label] = entry
        by_task[key] = {
            'scheduled_rounds': [i for i in range(3) if key in ORDER[i]],
            'executed': sum(r.get('status') == 'executed' for r in rows),
            'failed': sum(r.get('status') == 'failed' for r in rows),
            'not_executed': sum(r.get('status') == 'not_executed' for r in rows),
            'runs': rows, 'resource_distributions': resource_stats,
            'termination_values': [r.get('termination') for r in executed],
            'reward_values': [r.get('reward') for r in executed],
            'request_count_values': [r.get('model_requests_logged') for r in executed],
            'tool_count_values': [sum(r.get('tool_name_counts', {}).values()) for r in executed],
        }
    return {'schema': 'docops-office-repeat-batch-summary-v1',
            'collection': collection, 'identity_sha256': frozen_id,
            'results': results, 'by_task': by_task, 'stopped_reason': stopped_reason,
            'batch_wall_s': round(time.monotonic() - start_monotonic, 3),
            'batch_budget_s': batch_wall, 'closeout_reserve_s': batch_reserve}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def batch_markdown(batch: dict) -> str:
    lines = [f"# {batch['collection']} 批次结果", '',
             f"Identity SHA-256：`{batch['identity_sha256']}`", '',
             '| Round | Task | Run | 状态 | 请求 | 工具类别计数 | 终止 | Reward | Wall s | CPU core-s | memory.current 峰值 B |',
             '|---:|---|---|---|---:|---|---|---:|---:|---:|---:|']
    for item in batch['results']:
        res = item.get('resources', {})
        lines.append('| {round} | {task} | {run} | {status} | {req} | {tools} | {term} | {reward} | {wall} | {cpu} | {mem} |'.format(
            round=item.get('round'), task=item['task_key'].replace('atomic__', ''),
            run=item.get('run_id', '—'), status=item['status'],
            req=item.get('model_requests_logged', '—'),
            tools=json.dumps(item.get('tool_activity_category_counts', {}), ensure_ascii=False),
            term=item.get('termination', '—'), reward=item.get('reward', '—'),
            wall=res.get('attempt_wall_s', '—'), cpu=res.get('container_cpu_core_s', '—'),
            mem=res.get('memory_current_sample_peak_bytes', '—')))
    lines.extend(['', f"停止原因：{batch.get('stopped_reason') or '无'}。",
                  '状态 `executed` 表示 attempt 链与归档完成，不表示 reward 成功。',
                  '容器资源为共享任务容器观测，不归因到单个工具；请求数是已保存逻辑请求日志，未必覆盖底层重试。',
                  ''])
    return '\n'.join(lines)


def archive_batch(root: Path, batch: dict, identity: dict, *,
                  start_monotonic: float, build_logs: list[dict]) -> int:
    """Seal the existing batch results in the identity's explicit namespace."""
    report_dir = root / identity['paths']['reports']
    env_dir = (root / identity['paths']['plan']).parent
    summary_path = report_dir / 'batch-summary.json'
    markdown_path = report_dir / 'batch-summary.md'
    write_json(summary_path, batch)
    markdown_path.write_text(batch_markdown(batch), encoding='utf-8')
    outputs = []
    for directory in (report_dir, env_dir):
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.name != 'batch-manifest.json':
                outputs.append(file_record(path, path.relative_to(root)))
    raw_manifests = []
    for row in batch['results']:
        if row.get('run_id'):
            path = root / identity['paths']['raw'] / row['run_id'] / 'manifest.json'
            if path.is_file():
                raw_manifests.append(file_record(path, path.relative_to(root)))
    manifest = {
        'schema': 'docops-office-repeat-batch-manifest-v1',
        'identity_sha256': identity_sha(identity),
        'input_root': str(ROOT), 'output_root': str(root),
        'inputs': [*identity['code_and_runtime_files'],
                   *identity.get('preparation_evidence', []),
                   *(f for task in identity['tasks'] for f in task['files'])],
        'build_logs': build_logs, 'raw_run_manifests': raw_manifests, 'outputs': outputs,
    }
    manifest_path = report_dir / 'batch-manifest.json'
    write_json(manifest_path, manifest)
    # Include local batch sealing in the final observed wall, then refresh the
    # final summary's hash. Never recursively hash the manifest itself.
    batch['batch_wall_s'] = round(time.monotonic() - start_monotonic, 3)
    batch['within_batch_budget'] = batch['batch_wall_s'] <= batch['batch_budget_s']
    write_json(summary_path, batch)
    manifest['outputs'] = [file_record(root / r['path'], Path(r['path'])) for r in outputs]
    write_json(manifest_path, manifest)
    for record in manifest['outputs'] + manifest['raw_run_manifests']:
        if file_record(root / record['path'], Path(record['path'])) != record:
            raise BatchError(f'batch output hash mismatch: {record["path"]}')
    return 0 if batch['within_batch_budget'] and len(batch['results']) == 9 and all(
        r['status'] == 'executed' for r in batch['results']) else 7


def create_approval(path: Path, digest: str) -> dict:
    approval = {'schema': 'docops-batch-approval-v1', 'collection': COLLECTION,
                'user_approval': 'approved', 'identity_sha256': digest,
                'approval_source': 'explicit user authorization in current request',
                'approved_at_utc': datetime.now(timezone.utc).isoformat(),
                'scope': {'attempts': 9, 'attempt_retry': 0,
                          'maximum_model_steps': 360,
                          'model': MODEL, 'api_base': API_BASE,
                          'max_tokens_per_request': MAX_TOKENS,
                          'per_attempt': {'max_steps': MAX_STEPS,
                              'agent_s': AGENT_S, 'verifier_s': VERIFIER_S,
                              'wall_s': TOTAL_WALL_S, 'cleanup_reserve_s': CLEANUP_S,
                              'cpu': 1, 'memory_gib': 4, 'storage_gib': 10,
                              'network': 'none', 'sample_interval_s': SAMPLE_S},
                          'batch_wall_s': BATCH_WALL_S,
                          'batch_closeout_reserve_s': BATCH_RESERVE_S,
                          'framework_attempts_per_logical_call_max': 3,
                          'cost': 'unknown; no hard cap accepted for this batch'}}
    if path.exists():
        raise BatchError('refusing to overwrite an existing approval')
    write_json(path, approval)
    return approval


def validate_approval(path: Path, digest: str) -> bool:
    try:
        approval = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return (isinstance(approval, dict)
            and approval.get('schema') == 'docops-batch-approval-v1'
            and approval.get('collection') == COLLECTION
            and approval.get('user_approval') == 'approved'
            and approval.get('identity_sha256') == digest
            and isinstance(approval.get('approved_at_utc'), str)
            and approval.get('scope', {}).get('attempts') == 9
            and approval.get('scope', {}).get('maximum_model_steps') == 360)


def execute() -> int:
    # Pin only this process; do not inherit a named remote Docker context.
    os.environ.pop('DOCKER_CONTEXT', None)
    os.environ['DOCKER_HOST'] = ENDPOINT
    started = time.monotonic()
    root = ROOT
    report_dir, raw_dir, env_dir = root / REPORT_DIR_REL, root / RAW_DIR_REL, root / ENV_DIR_REL
    p = plan_mode(root)
    if not p['ready']:
        raise BatchError(f'preflight namespace/source conflict: {p}')
    for path in (report_dir, raw_dir):
        if path.exists():
            raise BatchError(f'namespace already exists: {path}')
    if env_dir.exists():
        stop_path = env_dir / 'execution-stop.json'
        if not p.get('preserved_prior_stop_record') or not stop_path.is_file():
            raise BatchError(f'preparation namespace already exists: {env_dir}')
    else:
        env_dir.mkdir(parents=True, exist_ok=False)
    base = verify_base()
    base_record = env_dir / 'base-image.json'
    if base_record.exists():
        if json.loads(base_record.read_text()) != base:
            raise BatchError('existing base-image record conflicts with verified identity')
    else:
        write_json(base_record, base)
    if p.get('preserved_prior_stop_record'):
        correction = {
            'collection': COLLECTION,
            'historical_erroneous_base_id': PRIOR_ERRONEOUS_BASE_ID,
            'corrected_base_id': base['id'],
            'inspect_reference': BASE_REF,
            'inspect_platform': base['platform'],
            'basis': ['env/docops-arm64-word001/plan-identity-04.json',
                      'env/docops-office-repeat-01/execution-stop.json',
                      'fixed-endpoint read-only Docker inspect in this preparation'],
            'historical_files_modified': False,
        }
        correction_path = env_dir / 'base-image-correction.json'
        if correction_path.exists():
            recorded = json.loads(correction_path.read_text())
            if any(recorded.get(key) != value for key, value in correction.items()):
                raise BatchError('existing base-image correction record conflicts')
        else:
            correction['corrected_at_utc'] = datetime.now(timezone.utc).isoformat()
            write_json(correction_path, correction)
    builds = load_initial_builds(env_dir)
    ids = {}
    work_deadline = started + BATCH_WALL_S - BATCH_RESERVE_S
    if builds is None:
        builds = []
        for task in TASKS:
            key = task['key']
            remaining = work_deadline - time.monotonic()
            if remaining <= 0:
                raise BatchError('batch preparation budget exhausted during image build')
            result = build_task_image(key, image_ref(key), env_dir,
                                      timeout=min(PER_BUILD_S, remaining), log_label='initial')
            builds.append(result)
            write_json(env_dir / 'image-builds.json', {'builds': builds})
            ids[key] = result['image']['id']
    else:
        for row in builds:
            image = row['image']
            observed = inspect_image(image['reference'])
            if observed != (image['id'], 'linux/arm64'):
                raise BatchError(f'previously built task image identity mismatch: {image["reference"]}: {observed}')
            ids[row['task_key']] = image['id']
    preflight = []
    for task in TASKS:
        key = task['key']
        remaining = work_deadline - time.monotonic()
        # A preflight may spend up to 60s each in setup and its import check,
        # then up to 150s stopping and confirming deletion. Keep that cleanup
        # inside the batch work window rather than consuming closeout reserve.
        preflight_cleanup_reserve = 270.0
        if remaining <= preflight_cleanup_reserve:
            raise BatchError('batch preparation budget exhausted before preflight cleanup reserve')
        config = run_config(key, 0, image_ref(key), ids[key])
        preflight.append(asyncio.run(preflight_one(
            key, config, env_dir,
            timeout_s=min(PREFLIGHT_S, remaining - preflight_cleanup_reserve)))
        )
        write_json(env_dir / f'preflight-{task["short"]}.json', preflight[-1])
        if preflight[-1]['status'] != 'passed':
            write_json(env_dir / 'preflight-summary.json', {'checks': preflight})
            raise BatchError(f'no-model environment preflight failed for {key}')
    if work_deadline - time.monotonic() < TOTAL_WALL_S:
        raise BatchError('insufficient batch work budget for one complete attempt')
    identity = build_identity(ids)
    digest = identity_sha(identity)
    plan = {'schema': 'docops-office-repeat-plan-v1',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'identity_sha256': digest, 'identity': identity,
            'builds': builds, 'environment_checks': preflight}
    write_json(env_dir / 'plan-identity.json', plan)
    write_json(env_dir / 'frozen-identity.json',
               {'schema': 'docops-office-repeat-frozen-v1',
                'identity_sha256': digest, 'identity': identity})
    load_model_credential()
    report_dir.mkdir(parents=True, exist_ok=False)
    approval_path = report_dir / 'APPROVAL.json'
    approval = create_approval(approval_path, digest)
    if not validate_approval(approval_path, digest):
        raise BatchError('new batch approval failed identity/scope validation')
    # Batch gate is checked once before the first run. Later attempts are allowed
    # to create entries in this same collection namespace.
    batch = run_batch(root, plan, identity, start_monotonic=started)
    return archive_batch(root, batch, identity, start_monotonic=started,
                         build_logs=[b['log'] for b in builds])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', action='store_true', help='read-only plan (default)')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--i-approve-the-docops-office-repeat-01', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(plan_mode(), indent=2, ensure_ascii=False))
        return 0
    if not args.i_approve_the_docops_office_repeat_01:
        print('REFUSED: dedicated batch approval flag required', file=sys.stderr)
        return 2
    try:
        return execute()
    except Exception as exc:
        evidence_dir = ROOT / ENV_DIR_REL
        if evidence_dir.is_dir():
            stop_path = evidence_dir / 'execution-stop.json'
            if stop_path.exists():
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                stop_path = evidence_dir / f'execution-stop-{stamp}.json'
            write_json(stop_path, {
                'schema': 'docops-office-repeat-stop-v1', 'status': 'stopped',
                'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                'error_type': type(exc).__name__, 'detail': str(exc)[:500],
                'secrets_or_environment_values_recorded': False})
        print(f'BATCH_STOPPED: {type(exc).__name__}: {str(exc)[:500]}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
