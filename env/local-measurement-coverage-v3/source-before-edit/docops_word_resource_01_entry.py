#!/usr/bin/env python3
"""DOCOPS-WORD-RESOURCE-04: single-attempt project-adapted DocOps word_001
resource pilot. (v3: adds task metadata upload and explicit DOCX format tools.)

Earlier v2 fixes identity gating, lifecycle/budget coverage, result
adjudication and archive completeness per offline review.

Thin entry chaining the REAL vendored Harbor 0.4.0 lifecycle, the official
DocumentToolsAgent, the official task verifier, and the project's existing
resource collectors.

Modes:
  --plan (default)   read-only identity + plan printout (no credentials/docker/model).
  --execute          requires --i-approve-the-docops-word-resource-04; refuses when
                     an attempt already exists, when the recomputed identity does
                     not match the frozen identity below, or when the actual task
                     image ID on this host differs from the registered one.

v2 fixes over v1:
  - identity recomputed at execute time MUST equal FROZEN_IDENTITY_SHA256 and now
    binds the actual Harbor implementation files, collection code and dependency
    freeze; actual image ID verified via docker image inspect before start.
  - Harbor start, container identification and sampler init moved INSIDE the
    try/finally: any startup exception still runs cleanup, archive and manifests.
    start/stop are also deadline-bounded; every phase timeout is capped by the
    total deadline minus the 300s cleanup/archive reserve (hard guarantee).
  - verifier reads VerifierResult.rewards (dict, real Harbor interface); agent
    termination is classified finish / steps_exhausted / agent_timeout /
    agent_error from the official transcript tail; CLI returns non-zero when
    infra failures exist.
  - archive order: ATTEMPT_COMPLETED written BEFORE manifest scan; llm_call_*
    model evidence included in manifest hashes; archive_done event persisted in
    the on-disk summary; manifest records summary.json hash (manifest excludes
    only itself).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path('/home/lcq/agent_workload_characterization')
COLLECTION = 'DOCOPS-WORD-RESOURCE-04'
APPROVAL_PATH = PROJECT_ROOT / 'reports/resource/DOCOPS-WORD-RESOURCE-04/APPROVAL.json'
PREFLIGHT_PATH = PROJECT_ROOT / 'reports/resource/DOCOPS-WORD-RESOURCE-04/PREFLIGHT.json'
REPORT_PATH = PROJECT_ROOT / 'reports/resource/DOCOPS-WORD-RESOURCE-04/run-report.json'

TASK_DIR = (PROJECT_ROOT / 'references/repos/DocOps/tasks/'
            'atomic__word_001_engineering_report_toc_hierarchy_seed')
TASK_IMAGE = 'docops-word001-task:arm64-adapted-v1'
TASK_IMAGE_ID_EXPECTED = ('sha256:869486d7bdb34f8da3a1affabaeb085413c850630e'
                          'f01e0ed1f8a01d64db779f')
BASE_IMAGE_ID_EXPECTED = ('sha256:062bf50871c0e9d7d4a175643343746f27c7857325'
                          '962525d7ebe9ae0c08fe9b1')
MODEL_REQUEST_ID = 'openai/deepseek-v4-flash'
API_BASE = 'https://api.deepseek.com/v1'

AGENT_BUDGET_S = 1200.0
VERIFIER_BUDGET_S = 600.0
START_BUDGET_S = 300.0
SETUP_BUDGET_S = 60.0
STOP_BUDGET_S = 300.0
TOTAL_WALL_S = 2700.0
CLEANUP_RESERVE_S = 300.0
SAMPLE_INTERVAL_S = 0.5
MAX_STEPS = 40
MAX_TOKENS = 32768

# Frozen identity of the approved plan lives in an external file (the identity
# itself binds this entry's hash, so the frozen value cannot live inside it).
FROZEN_IDENTITY_PATH = PROJECT_ROOT / 'env/docops-arm64-word001/frozen-identity-04.json'


def run_config(plan: dict) -> dict:
    """Return the explicit per-attempt configuration; default preserves the
    historical single Word entry, while the Office repeat entry supplies a
    complete task-specific configuration without mutating module globals."""
    config = plan.get('run_config')
    if config is not None:
        required = {'collection', 'task_dir', 'task_key', 'round', 'image_ref',
                    'image_id', 'input_asset', 'max_steps', 'max_tokens',
                    'agent_budget_s', 'verifier_budget_s', 'start_budget_s',
                    'setup_budget_s', 'stop_budget_s', 'total_wall_s',
                    'cleanup_reserve_s', 'sample_interval_s', 'cpu_limit',
                    'memory_mb', 'storage_mb', 'network'}
        if not required.issubset(config):
            raise ValueError('run_config missing required fields')
        return config
    return {
        'collection': COLLECTION, 'task_dir': str(TASK_DIR),
        'task_key': 'atomic__word_001_engineering_report_toc_hierarchy_seed',
        'round': None, 'image_ref': TASK_IMAGE,
        'image_id': TASK_IMAGE_ID_EXPECTED,
        'input_asset': 'word_001_engineering_report_toc_hierarchy_seed.docx',
        'max_steps': MAX_STEPS, 'max_tokens': MAX_TOKENS,
        'agent_budget_s': AGENT_BUDGET_S, 'verifier_budget_s': VERIFIER_BUDGET_S,
        'start_budget_s': START_BUDGET_S, 'setup_budget_s': SETUP_BUDGET_S,
        'stop_budget_s': STOP_BUDGET_S, 'total_wall_s': TOTAL_WALL_S,
        'cleanup_reserve_s': CLEANUP_RESERVE_S,
        'sample_interval_s': SAMPLE_INTERVAL_S, 'cpu_limit': 1,
        'memory_mb': 4096, 'storage_mb': 10240, 'network': 'none',
    }


def frozen_identity_sha() -> str | None:
    try:
        return json.loads(FROZEN_IDENTITY_PATH.read_text())['identity_sha256']
    except (OSError, KeyError, ValueError):
        return None

sys.path.insert(0, str(PROJECT_ROOT / '.venvs/docops-pilot-01/lib/python3.12/site-packages'))
sys.path.insert(0, str(PROJECT_ROOT / 'references/repos/DocOps/harnesses'))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            c = f.read(1 << 20)
            if not c:
                break
            h.update(c)
    return h.hexdigest()


def remove_credential_fingerprints(run_dir: Path) -> int:
    """Remove only LiteLLM's known credential fingerprint fields from newly
    written call logs before archive; retain request/response/usage evidence."""
    sensitive_names = {'api_key_sha256', 'x-api-key_sha256'}
    removed = 0

    def clean(value):
        nonlocal removed
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if str(key).lower() in sensitive_names:
                    removed += 1
                    continue
                result[key] = clean(item)
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    for path in sorted((run_dir / 'agent').glob('llm_call_*.json')):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        cleaned = clean(payload)
        if cleaned != payload:
            path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + '\n')
    return removed


def identity_files() -> dict:
    return {
        'task_toml': TASK_DIR / 'task.toml',
        'instruction': TASK_DIR / 'instruction.md',
        'input_docx': (TASK_DIR / 'environment/'
                       'word_001_engineering_report_toc_hierarchy_seed.docx'),
        'test_sh': TASK_DIR / 'tests/test.sh',
        'test_outputs': TASK_DIR / 'tests/test_outputs.py',
        'verifier_utils': TASK_DIR / 'tests/verifier_utils.py',
        'agent_harness': PROJECT_ROOT / 'references/repos/DocOps/harnesses/document_tools_agent.py',
        'runtime_tools': PROJECT_ROOT / 'references/repos/DocOps/harnesses/document_tools_runtime.py',
        'task_metadata': TASK_DIR / 'environment/task_metadata.json',
        'project_agent_adapter': PROJECT_ROOT / 'src/agent_workload_characterization/runners/docops_word_agent.py',
        'project_runtime_adapter': PROJECT_ROOT / 'src/agent_workload_characterization/runners/docops_word_runtime.py',
        'project_environment_adapter': PROJECT_ROOT / 'src/agent_workload_characterization/runners/docops_environment.py',
        # actual Harbor implementation used at runtime (installed from this copy)
        'harbor_pyproject': PROJECT_ROOT / 'env/docops-arm64-word001/harbor-src/pyproject.toml',
        'harbor_docker_env': (PROJECT_ROOT / 'env/docops-arm64-word001/harbor-src/src/'
                              'harbor/environments/docker/docker.py'),
        'harbor_installed_docker_env': (PROJECT_ROOT / '.venvs/docops-pilot-01/lib/'
                                       'python3.12/site-packages/harbor/environments/docker/docker.py'),
        'harbor_lite_llm': (PROJECT_ROOT / 'env/docops-arm64-word001/harbor-src/src/'
                            'harbor/llms/lite_llm.py'),
        'harbor_verifier': (PROJECT_ROOT / 'env/docops-arm64-word001/harbor-src/src/'
                            'harbor/verifier/verifier.py'),
        # project collection code used at runtime
        'collector_container_runtime': PROJECT_ROOT / 'src/agent_workload_characterization/runners/container_runtime.py',
        'collector_host_process': PROJECT_ROOT / 'src/agent_workload_characterization/collectors/host_process.py',
        'collector_resource_sampler': PROJECT_ROOT / 'src/agent_workload_characterization/collectors/resource_sampler.py',
        'collector_semantic_recorder': PROJECT_ROOT / 'src/agent_workload_characterization/collectors/semantic_recorder.py',
        'collector_execution_measurement': PROJECT_ROOT / 'src/agent_workload_characterization/collectors/execution_measurement.py',
        # dependency freeze of the pilot venv
        'dependency_freeze': PROJECT_ROOT / 'env/docops-arm64-word001/harbor-venv-freeze.txt',
        'entry': Path(__file__).resolve(),
    }


def build_identity() -> dict:
    from agent_workload_characterization.collectors.execution_measurement import CONTRACT
    files = identity_files()
    return {
        'measurement_contract': CONTRACT,
        'collection': COLLECTION,
        'task_dir': str(TASK_DIR),
        'execution_interface': {
            'approval_flag': '--i-approve-the-docops-word-resource-04',
            'command': 'PYTHONPATH=src LITELLM_LOCAL_MODEL_COST_MAP=True .venvs/docops-pilot-01/bin/python -B scripts/docops_word_resource_01_entry.py --execute --i-approve-the-docops-word-resource-04',
        },
        'state_paths': {
            'approval': str(APPROVAL_PATH.relative_to(PROJECT_ROOT)),
            'preflight': str(PREFLIGHT_PATH.relative_to(PROJECT_ROOT)),
            'attempt_root': f'data/raw/generated/{COLLECTION}/<run_id>/',
            'attempt_started': f'data/raw/generated/{COLLECTION}/<run_id>/ATTEMPT_STARTED.json',
            'attempt_completed': f'data/raw/generated/{COLLECTION}/<run_id>/ATTEMPT_COMPLETED.json',
            'report': str(REPORT_PATH.relative_to(PROJECT_ROOT)),
        },
        'files': {k: {'path': str(v), 'bytes': v.stat().st_size,
                      'sha256': sha256_file(v)} for k, v in files.items()},
        'task_image': {'reference': TASK_IMAGE, 'expected_id': TASK_IMAGE_ID_EXPECTED},
        'base_image': {'label': 'harbor-claude-code-base:2.1.114',
                       'expected_id': BASE_IMAGE_ID_EXPECTED,
                       'note': 'ARM64 adapted environment (provenance unknown, '
                               'registered); NOT claimed equivalent to the official '
                               'amd64 archive'},
        'cleanup': {'compose_delete_args': ['down', '--volumes', '--remove-orphans'],
                    'retain_images': True, 'errors': 'propagate_to_entry_and_verify_removal'},
        'model_route': {'request_id': MODEL_REQUEST_ID, 'api_base': API_BASE,
                        'credential': 'DEEPSEEK_API_KEY mapped to OPENAI_API_KEY '
                                      'in-process only; fixed, no auto-switching',
                        'documented_backend': 'DeepSeek-V4.1-Flash',
                        'model_version_note': 'User-selected legacy request alias; '
                            'official docs route it to V4.1-Flash. Not an immutable '
                            'version pin; actual response model not yet observed.',
                        'documentation': 'https://api-docs.deepseek.com/'},
        'agent_api_configuration': {
            'stop_policy': 'omitted by JsonActionLLM; project-side JSON action '
                           'configuration, not a verified official-provider fix',
            'extra_body': None,
            'extra_body_note': 'Do not send the former gateway thinking_mode '
                               'parameter; official provider defaults apply.',
            'validation_scope': 'API smoke is recorded separately; configuration '
                                'identity does not prove full-task success'},
        'budget': {'total_wall_s': TOTAL_WALL_S, 'agent_s': AGENT_BUDGET_S,
                   'verifier_s': VERIFIER_BUDGET_S, 'start_s': START_BUDGET_S,
                   'setup_s': SETUP_BUDGET_S, 'stop_s': STOP_BUDGET_S,
                   'cleanup_reserve_s': CLEANUP_RESERVE_S,
                   'container': {'cpus': 1, 'memory_mb': 4096, 'network': 'none'},
                   'max_steps': MAX_STEPS, 'max_tokens_per_request': MAX_TOKENS,
                   'max_tokens_note': 'output cap; reasoning-token accounting is '
                                      'provider-side semantics',
                   'attempt_retries': 0,
                   'framework_retry': 'Harbor LiteLLM call has tenacity retry: up to '
                                      '3 attempts per logical call, auth errors not '
                                      'retried; registered approval item, not disabled'},
        'sampling': {'interval_s': SAMPLE_INTERVAL_S,
                     'container_counters': 'cgroup v1 cpuacct/memory(+throttle blkio '
                                           'variant; io recorded as read, semantics '
                                           'ok_no_records_real_zero)',
                     'host_agent_process': 'proc cpu_ticks/rss via HostProcessReader',
                     'clock': 'host monotonic for sampling and events'},
    }


def identity_digest(identity: dict) -> str:
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def docker_image_id(reference: str, timeout_s: float = 30.0) -> str | None:
    r = subprocess.run(['docker', 'image', 'inspect', reference, '--format', '{{.Id}}'],
                       capture_output=True, text=True,
                       timeout=max(0.001, timeout_s))
    return r.stdout.strip() if r.returncode == 0 else None


def compose_containers(project: str) -> list[tuple[str, str]]:
    r = subprocess.run(['docker', 'ps', '--no-trunc', '--filter',
                        'label=com.docker.compose.project=' + project,
                        '--format', '{{.ID}} {{.Names}}'],
                       capture_output=True, text=True, timeout=30)
    return [tuple(l.split()) for l in r.stdout.strip().splitlines() if l.strip()]


# ---- overridable builders (tests substitute fakes via these names) ----

def build_environment(session_id: str, trial_paths, config: dict | None = None):
    from agent_workload_characterization.runners.docops_environment import DocOpsDockerEnvironment
    from harbor.models.task.config import EnvironmentConfig
    config = config or run_config({})
    task_dir = Path(config['task_dir'])
    cfg = EnvironmentConfig(docker_image=config['image_ref'],
                            cpus=config['cpu_limit'],
                            memory_mb=config['memory_mb'],
                            storage_mb=config['storage_mb'],
                            allow_internet=config['network'] != 'none',
                            workdir='/root')
    return DocOpsDockerEnvironment(
        environment_dir=task_dir / 'environment',
        environment_name='docops-' + str(config['task_key']).split('__')[-1][:24],
        session_id=session_id,
        trial_paths=trial_paths,
        task_env_config=cfg,
    )


class JsonActionLLM:
    """Omit textual stop sequences for project-side JSON action responses.

    The former gateway probe is historical evidence, not a compatibility test
    of the current official route. Official-provider behavior remains untested.
    """

    def __init__(self, inner):
        self._inner = inner

    async def call(self, *, prompt, message_history, **kw):
        kw.pop('stop', None)
        if kw.get('extra_body') is None:
            kw.pop('extra_body', None)
        return await self._inner.call(prompt=prompt,
                                      message_history=message_history, **kw)


def build_agent(logs_dir: Path, config: dict | None = None):
    from agent_workload_characterization.runners.docops_word_agent import DocOpsWordAgent
    config = config or run_config({})
    agent = DocOpsWordAgent(
        logs_dir=logs_dir,
        model_name=MODEL_REQUEST_ID,
        api_base=API_BASE,
        max_steps=config['max_steps'],
        max_tokens=config['max_tokens'],
        thinking_mode=None,
        metadata_path=Path(config['task_dir']) / 'environment/task_metadata.json',
    )
    agent.llm = JsonActionLLM(agent.llm)
    return agent


def build_verifier(task, trial_paths, environment):
    from harbor.verifier.verifier import Verifier
    return Verifier(task=task, trial_paths=trial_paths, environment=environment)


def build_runtime(config: dict | None = None):
    from agent_workload_characterization.runners.container_runtime import DockerCliRuntime
    config = config or run_config({})
    return DockerCliRuntime(authorized=True, collection=config['collection'])


class Sampler(threading.Thread):
    def __init__(self, handle, runtime, interval_s: float = SAMPLE_INTERVAL_S):
        super().__init__(daemon=True)
        self.handle = handle
        self.runtime = runtime
        self.interval_s = interval_s
        self.host_reader = None
        self.stop_event = threading.Event()
        self.rows = []
        self.lock = threading.Lock()
        self.read_gate = threading.Lock()
        self.read_wall_ns = 0

    def run(self):
        from agent_workload_characterization.collectors.host_process import HostProcessReader
        self.host_reader = HostProcessReader(os.getpid())
        self.read_once('boundary_start')
        while not self.stop_event.is_set():
            self.read_once('sample')
            self.stop_event.wait(self.interval_s)
        self.read_once('boundary_end')

    def read_once(self, role):
        from dataclasses import asdict
        with self.read_gate:
            t = time.monotonic_ns()
            row = {'t_monotonic_ns': t, 'clock_domain': 'system_monotonic', 'role': role}
            try:
                row['container'] = self.runtime.read_counters(self.handle, t).to_dict()
                row['container'].update(container_id=self.handle.container_id,
                                        cgroup_version=self.handle.cgroup_version)
            except Exception as e:
                row['container_error'] = type(e).__name__
            try:
                h = self.host_reader.read(t)
                if h.read_status.get('stat') == 'ok' and self.host_reader.expected_starttime is None:
                    self.host_reader.expected_starttime = h.starttime_ticks
                row['host_agent'] = asdict(h)
                row['host_agent'].update(clk_tck=self.host_reader.clk_tck,
                                         page_size=self.host_reader.page_size,
                                         scope='shared_host_agent_and_collector_process')
            except Exception as e:
                row['host_agent_error'] = type(e).__name__
            with self.lock:
                row['read_wall_ns'] = time.monotonic_ns() - t
                self.read_wall_ns += row['read_wall_ns']
                self.rows.append(row)

    def shared_counter_boundary(self):
        # Synchronous proc/cgroup reads only, never docker exec. This is a
        # shared scope window; it includes concurrent work and read overhead.
        with self.read_gate:
            t = time.monotonic_ns()
            try:
                return {**self.runtime.read_counters(self.handle, t).to_dict(),
                        'container_id': self.handle.container_id}
            except Exception as exc:
                return {'t_monotonic_ns': t, 'read_status': {'boundary': type(exc).__name__}}
            finally:
                with self.lock:
                    self.read_wall_ns += time.monotonic_ns() - t


def classify_agent_termination(trial, agent_status: str) -> str:
    """finish vs steps_exhausted from the official transcript tail."""
    if agent_status != 'completed':
        return agent_status
    try:
        tail = (trial.agent_dir / 'document-tools-agent.txt').read_text()
        if tail.rstrip().endswith('Task ended without an explicit finish.'):
            return 'steps_exhausted'
        return 'finish'
    except OSError:
        return 'completed_transcript_unreadable'


async def run_attempt(collection_root: Path, plan: dict) -> dict:
    from harbor.models.task.task import Task
    from harbor.models.trial.paths import TrialPaths
    from harbor.models.agent.context import AgentContext
    from agent_workload_characterization.runners.container_runtime import (
        ContainerHandle, ContainerSpec)
    from harbor.environments.docker.docker import _sanitize_docker_compose_project_name

    config = run_config(plan)
    task_dir = Path(config['task_dir'])
    collection = config['collection']
    t0 = time.monotonic()
    events = []

    def ev(phase, **kw):
        if phase in ('agent_setup_begin', 'agent_setup_done', 'agent_begin',
                     'agent_end', 'verifier_begin', 'verifier_end') and sampler is not None:
            kw['shared_resource_boundary'] = sampler.shared_counter_boundary()
        events.append({'phase': phase, 't_monotonic_ns': time.monotonic_ns(), **kw})

    def remaining_to(phase_budget: float) -> float:
        """WORK-phase deadline: total wall minus the cleanup/archive reserve."""
        total_deadline = min(t0 + config['total_wall_s'],
                             plan.get('batch_work_deadline_monotonic', float('inf')))
        hard = total_deadline - config['cleanup_reserve_s']
        return max(0.0, min(phase_budget, hard - time.monotonic()))

    def cleanup_remaining_to(phase_budget: float) -> float:
        """CLEANUP-phase deadline: bounded by the TOTAL wall (the reserve is
        available to cleanup; archive runs after, locally, and is recorded
        even if it exceeds the wall)."""
        total_deadline = min(t0 + config['total_wall_s'],
                             plan.get('batch_work_deadline_monotonic', float('inf')))
        return max(0.0, min(phase_budget, total_deadline - time.monotonic()))

    run_dir = collection_root / 'data/raw/generated' / collection / plan['run_id']
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / 'ATTEMPT_STARTED.json').write_text(json.dumps(
        {'run_id': plan['run_id'], 'collection': collection,
         'identity_sha256': plan['identity_sha256'],
         'task_key': config['task_key'], 'round': config['round'],
         'started_at_monotonic_ns': time.monotonic_ns()}, indent=1))
    from agent_workload_characterization.collectors.execution_measurement import (
        CONTRACT_VERSION, RunSupplement, container_directory_footprint_snapshot,
        office_resource_rate_intervals)
    supplement = RunSupplement(run_dir, interval_s=config['sample_interval_s'],
        disk_specs=[
            {'path': str(run_dir), 'role': 'attempt_output',
             'scope': 'host_visible_trial_and_archive', 'ownership': 'run_scoped'},
            {'path': None, 'role': 'shared_task_cache', 'scope': 'host_and_container',
             'ownership': 'shared_unassigned', 'unavailable_status': 'unsupported',
             'reason': 'no_task_exclusive_cache_path_registered'}])
    supplement_start_error = None
    try:
        supplement.start()
    except Exception as exc:  # observation failure must not prevent execution cleanup
        supplement_start_error = type(exc).__name__
    ev('attempt_started', run_id=plan['run_id'])

    task = Task(task_dir)
    trial = TrialPaths(trial_dir=run_dir)
    trial.mkdir()
    env = build_environment(plan['run_id'], trial, config)

    outcome = {'phases': {}, 'infra_failures': []}
    measured_agent = None
    sampler = None
    handle = None
    runtime = build_runtime(config)
    cid = cname = None

    def finish_phase(name, **kw):
        outcome['phases'][name] = kw
        ev('phase_' + name, **kw)

    # EVERYTHING from Harbor start onward is inside try/finally so that startup
    # exceptions still run cleanup and produce summary/manifest.
    try:
        ev('harbor_start_begin')
        try:
            await asyncio.wait_for(env.start(force_build=False),
                                   timeout=remaining_to(config['start_budget_s']))
        except asyncio.TimeoutError:
            raise RuntimeError('harbor_start timeout within total budget')
        ev('harbor_start_done')

        project = _sanitize_docker_compose_project_name(plan['run_id'])
        rows = compose_containers(project)
        if len(rows) != 1:
            raise RuntimeError('expected exactly 1 compose container, found %d' % len(rows))
        cid, cname = rows[0]
        if not cname.startswith(project):
            raise RuntimeError('container %s not owned by project %s' % (cname, project))
        ev('container_identified', container_id=cid, container_name=cname,
           compose_project=project)

        assert not cname.startswith(runtime._name_prefix)
        handle = ContainerHandle(container_id=cid,
                                 spec=ContainerSpec(run_id=plan['run_id'],
                                                    scope='agent_container',
                                                    image=config['image_ref'], network='none'))
        runtime._resolve_cgroup(handle)
        ev('cgroup_resolved', version=handle.cgroup_version, dir=str(handle.cgroup_dir))

        sampler = Sampler(handle, runtime, config['sample_interval_s'])
        sampler.start()

        agent = build_agent(trial.agent_dir, config)
        measured_agent = agent
        agent.resource_read = sampler.shared_counter_boundary
        ctx = AgentContext()
        # official setup: uploads the document-tools runtime and creates the
        # submission dir; budgeted like any other work phase
        ev('agent_setup_begin')
        task_disk_spec = [{'path': '/root/submission',
            'role': 'task_workspace_and_submission',
            'scope': 'agent_container:/root/submission',
            'ownership': 'task_run_private'}]
        task_disk_baseline = None
        task_disk_final = None
        try:
            await asyncio.wait_for(agent.setup(env), timeout=remaining_to(config['setup_budget_s']))
            ev('agent_setup_done')
            # setup creates the fixed submission directory; this is the
            # baseline immediately before the Agent can write task output.
            task_disk_baseline = container_directory_footprint_snapshot(
                runtime, handle, task_disk_spec,
                timeout_s=min(3.0, remaining_to(3.0)))
            supplement.record_container_disk_boundary(
                'task_workspace_submission', 'before_agent', task_disk_baseline)
        except Exception as e:
            outcome['infra_failures'].append('agent_setup:' + type(e).__name__)
            finish_phase('agent', status='agent_setup_error',
                         error_type=type(e).__name__, detail=str(e)[:200])
            agent = None
        if agent is not None:
            ev('agent_begin', model=MODEL_REQUEST_ID)
            agent_t = remaining_to(config['agent_budget_s'])
            try:
                await asyncio.wait_for(agent.run(task.instruction, env, ctx),
                                       timeout=agent_t)
                term = classify_agent_termination(trial, 'completed')
                finish_phase('agent', status=term,
                             n_input_tokens=ctx.n_input_tokens,
                             n_output_tokens=ctx.n_output_tokens,
                             n_cache_tokens=ctx.n_cache_tokens,
                             cost_usd=ctx.cost_usd,
                             agent_budget_s=round(agent_t, 1))
            except asyncio.TimeoutError:
                finish_phase('agent', status='agent_timeout',
                             agent_budget_s=round(agent_t, 1))
            except Exception as e:
                finish_phase('agent', status='agent_error',
                             error_type=type(e).__name__, detail=str(e)[:200])
            task_disk_final = container_directory_footprint_snapshot(
                runtime, handle, task_disk_spec,
                timeout_s=min(3.0, remaining_to(3.0)))
            supplement.record_container_disk_boundary(
                'task_workspace_submission', 'after_agent', task_disk_final)
            ev('agent_end')

            ev('verifier_begin')
            verifier = build_verifier(task, trial, env)
            ver_t = remaining_to(config['verifier_budget_s'])
            try:
                vr = await asyncio.wait_for(verifier.verify(), timeout=ver_t)
                rewards = getattr(vr, 'rewards', None)  # real Harbor interface: dict
                finish_phase('verifier', status='completed',
                             rewards=rewards,
                             reward=(rewards or {}).get('reward'),
                             verifier_budget_s=round(ver_t, 1))
            except asyncio.TimeoutError:
                finish_phase('verifier', status='verifier_timeout',
                             verifier_budget_s=round(ver_t, 1))
            except Exception as e:
                finish_phase('verifier', status='verifier_infra_error',
                             error_type=type(e).__name__, detail=str(e)[:200])
                outcome['infra_failures'].append('verifier:' + type(e).__name__)
            ev('verifier_end')
    except Exception as e:
        outcome['infra_failures'].append('startup_or_run:' + type(e).__name__)
        finish_phase('run', status='startup_or_run_error',
                     error_type=type(e).__name__, detail=str(e)[:200])
    finally:
        # cleanup ALWAYS runs, deadline-bounded, and archive happens regardless
        if sampler is not None:
            sampler.stop_event.set()
            sampler.join(timeout=10)
        ev('sampling_stopped', rows=len(sampler.rows) if sampler else 0)
        if sampler is not None and sampler.is_alive():
            outcome['infra_failures'].append('sampler_stop_unconfirmed')
        if env is not None:
            ev('harbor_stop_begin', delete=True)
            stop_err = None
            try:
                await asyncio.wait_for(env.stop(delete=True),
                                       timeout=cleanup_remaining_to(config['stop_budget_s']))
            except Exception as e:
                stop_err = type(e).__name__
                outcome['infra_failures'].append('harbor_stop:' + stop_err)
            ev('harbor_stop_done', stop_error=stop_err)
        if handle is not None:
            removal = runtime.verify_removal(
                handle, timeout_s=cleanup_remaining_to(30.0))
            ev('removal_verified', result=removal)
            if removal != 'removed':
                outcome['infra_failures'].append('removal:' + removal)
        # Project stop(delete=True) retains images while deleting compose
        # containers/volumes/orphans. Observe the tag afterward; absence alone
        # does not establish who deleted it. NEVER rebuild/re-pull here.
        # A query failure must NEVER abort archiving; with no remaining budget the
        # query is not attempted at all (recorded unknown).
        image_query_budget = cleanup_remaining_to(30.0)
        tag_after = None
        tag_query_error = None
        if image_query_budget <= 0:
            tag_query_error = 'skipped_no_remaining_budget'
        else:
            try:
                tag_after = docker_image_id(config['image_ref'], timeout_s=image_query_budget)
            except Exception as e:
                tag_query_error = type(e).__name__
        ev('image_tag_after_stop', present=tag_after is not None, id=tag_after,
           query_error=tag_query_error)
        if tag_query_error is not None:
            outcome['image_tag_after_stop'] = 'unknown:' + tag_query_error
        elif tag_after is None:
            outcome['image_tag_after_stop'] = 'not_present'

        try:
            supplemental_measurements = supplement.stop()
            if supplement_start_error:
                supplemental_measurements['status'] = 'partial'
                supplemental_measurements['start_error'] = supplement_start_error
        except Exception as e:
            supplemental_measurements = {'schema': 'run-supplement-v1', 'status': 'partial',
                                         'measurement_contract_version': CONTRACT_VERSION,
                                         'failure': type(e).__name__,
                                         'start_error': supplement_start_error}
        (run_dir / 'supplemental_measurements.json').write_text(
            json.dumps(supplemental_measurements, ensure_ascii=False, indent=1) + '\n')

        # ---- archive: final wall adjudicated AFTER all archiving work ----
        ev('archive_begin')
        credential_fingerprint_fields_removed = remove_credential_fingerprints(run_dir)
        ev('call_log_credential_fingerprints_removed',
           count=credential_fingerprint_fields_removed)
        run_inputs = plan.get('run_inputs')
        if run_inputs is None:
            run_inputs = [
                {'path': 'task.toml', 'sha256': plan['identity']['files']['task_toml']['sha256']},
                {'path': 'instruction.md', 'sha256': plan['identity']['files']['instruction']['sha256']},
                {'path': 'environment/task_metadata.json', 'sha256': plan['identity']['files']['task_metadata']['sha256']},
                {'path': 'input_asset', 'sha256': plan['identity']['files']['input_docx']['sha256']}]
        manifest = {
            'schema': ('docops-resource-run-manifest-v2' if 'run_config' in plan
                       else 'docops-word-resource-01-run-manifest-v2'),
            'run_id': plan['run_id'],
            'identity_sha256': plan['identity_sha256'], 'task_key': config['task_key'],
            'round': config['round'],
            'inputs': [{'path': item['path'], 'sha256': item['sha256']}
                       for item in run_inputs],
            'outputs': [],
        }
        with (sampler.lock if sampler else threading.Lock()):
            samples = list(sampler.rows) if sampler else []
        from agent_workload_characterization.collectors.execution_measurement import (
            environment_snapshot, measurement_report, office_resource_rate_intervals,
            sample_quality)
        measurement = measurement_report(
            trial.agent_dir / 'events.jsonl',
            expected_requests=getattr(measured_agent, 'request_count', None),
            expected_tools=getattr(measured_agent, 'tool_count', None))
        measurement['resource_sampling'] = sample_quality(samples, config['sample_interval_s'])
        measurement['resource_intervals'] = office_resource_rate_intervals(
            samples, container_id=cid)
        measurement['supplemental_measurements'] = 'supplemental_measurements.json'
        measurement['collector'] = {
            'read_wall_ns': sampler.read_wall_ns if sampler else None,
            'scope': 'shared_host_process',
            'note': 'read wall cost only; not CPU or full instrumentation overhead'}
        (run_dir / 'measurement.json').write_text(json.dumps(measurement, indent=1))
        (run_dir / 'environment.json').write_text(json.dumps(environment_snapshot(), indent=1))
        ev('archive_done')
        # FINAL wall: measured after the archive events are collected and before
        # the summary/attempt/manifest writes, so archiving time is included in
        # the adjudication (the writes themselves are the last thing measured
        # into the recorded wall via a re-check below).
        final_wall = time.monotonic() - t0
        summary = {
            'schema': 'docops-word-resource-01-run-v2',
            'run_id': plan['run_id'],
            'collection': collection, 'task_key': config['task_key'],
            'round': config['round'], 'max_steps': config['max_steps'],
            'identity_sha256': plan['identity_sha256'],
            'task_image': {'reference': config['image_ref'],
                           'expected_id': config['image_id']},
            'outcome': outcome,
            'wall_s': round(final_wall, 2),
            'within_total_budget': final_wall <= config['total_wall_s'],
            'container': ({'id': cid, 'name': cname, 'compose_project':
                           _sanitize_docker_compose_project_name(plan['run_id']),
                           'cgroup_version': handle.cgroup_version}
                          if (cid and handle is not None) else None),
            'events': events,
            'call_log_credential_fingerprint_fields_removed': credential_fingerprint_fields_removed,
            'samples': samples,
            'measurement': measurement,
        }
        sp = run_dir / 'summary.json'
        ap = run_dir / 'ATTEMPT_COMPLETED.json'

        def write_summary_and_attempt(wall: float):
            summary['wall_s'] = round(wall, 2)
            summary['within_total_budget'] = wall <= config['total_wall_s']
            sp.write_text(json.dumps(summary, indent=1, ensure_ascii=False))
            ap.write_text(json.dumps(
                {'run_id': plan['run_id'], 'wall_s': round(wall, 2),
                 'within_total_budget': wall <= config['total_wall_s'],
                 'infra_failures': outcome['infra_failures'],
                 'phases': {k: v.get('status') for k, v in outcome['phases'].items()}},
                indent=1))

        write_summary_and_attempt(final_wall)  # provisional write for the scan
        for f in sorted(run_dir.rglob('*')):
            if f.is_file() and f.name != 'manifest.json':
                manifest['outputs'].append({'path': str(f.relative_to(run_dir)),
                                            'bytes': f.stat().st_size,
                                            'sha256': sha256_file(f)})
        (run_dir / 'manifest.json').write_text(json.dumps(manifest, indent=1))
        # FINAL observed wall AFTER all archiving work (scan, hashing, manifest
        # write): persisted on the NORMAL path too (not only on overrun), then
        # summary/ATTEMPT_COMPLETED are rewritten and their manifest entries
        # refreshed in both cases.
        final_wall = time.monotonic() - t0
        write_summary_and_attempt(final_wall)
        for e_ in manifest['outputs']:
            if e_['path'] in ('summary.json', 'ATTEMPT_COMPLETED.json'):
                f_ = run_dir / e_['path']
                e_['bytes'] = f_.stat().st_size
                e_['sha256'] = sha256_file(f_)
        (run_dir / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    return summary


def plan_mode(collection_root: Path) -> dict:
    identity = build_identity()
    digest = identity_digest(identity)
    raw_namespace = collection_root / 'data/raw/generated' / COLLECTION
    existing = list(raw_namespace.iterdir()) if raw_namespace.exists() else []
    report_namespace = collection_root / 'reports/resource' / COLLECTION
    existing_records = ([p.name for p in report_namespace.iterdir()
                         if p.name != 'APPROVAL.json']
                        if report_namespace.is_dir() else
                        ([report_namespace.name] if report_namespace.exists() else []))
    approval_path = report_namespace / 'APPROVAL.json'
    approval_status = 'missing'
    if approval_path.exists():
        try:
            approval = json.loads(approval_path.read_text())
            approval_status = ('valid' if isinstance(approval, dict)
                and approval.get('schema') == 'docops-single-run-approval-v1'
                and approval.get('collection') == COLLECTION
                and approval.get('user_approval') == 'approved'
                and approval.get('identity_sha256') == digest
                and 'entry_invocation' not in approval else 'invalid_or_stale')
        except (OSError, ValueError):
            approval_status = 'invalid_or_stale'
    frozen = frozen_identity_sha()
    return {'collection': COLLECTION, 'identity': identity,
            'identity_sha256': digest,
            'frozen_identity_sha256': frozen,
            'identity_matches_frozen': digest == frozen,
            'existing_attempts': [p.name for p in existing],
            'existing_namespace_records': existing_records,
            'approval_status': approval_status,
            'ready_for_approval': (not existing and not existing_records
                                   and digest == frozen),
            'ready_for_execution': (not existing and not existing_records
                                    and digest == frozen
                                    and approval_status == 'valid')}


def exit_code_for(summary: dict) -> int:
    """Pure adjudication: 0 normal (agent budget termination included);
    7 infra failure; 8 agent error / setup error / verifier timeout;
    9 total-wall overrun (including time spent archiving)."""
    if summary['outcome']['infra_failures']:
        return 7
    if not summary.get('within_total_budget', True):
        return 9
    phases = summary['outcome']['phases']
    if (phases.get('agent', {}).get('status') in ('agent_error', 'agent_setup_error')
            or phases.get('verifier', {}).get('status') == 'verifier_timeout'):
        return 8
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', action='store_true', default=True)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--i-approve-the-docops-word-resource-04', action='store_true')
    ap.add_argument('--collection-root', default=str(PROJECT_ROOT))
    args = ap.parse_args()
    root = Path(args.collection_root).resolve()

    if not args.execute:
        print(json.dumps(plan_mode(root), indent=1, ensure_ascii=False))
        return 0

    if not args.i_approve_the_docops_word_resource_04:
        print('REFUSED: --execute requires --i-approve-the-docops-word-resource-04',
              file=sys.stderr)
        return 2
    p = plan_mode(root)
    if p['existing_attempts'] or p['existing_namespace_records']:
        print('REFUSED: existing attempt(s) under %s: %s (no overwrite, no renumbering)'
              % (COLLECTION, p['existing_attempts'] + p['existing_namespace_records']),
              file=sys.stderr)
        return 3
    if not p['identity_matches_frozen']:
        print('REFUSED: recomputed identity %s != frozen %s (code or inputs changed; '
              're-freeze deliberately)' % (p['identity_sha256'], p['frozen_identity_sha256']),
              file=sys.stderr)
        return 4
    if p['approval_status'] != 'valid':
        print('REFUSED: APPROVAL.json must be a fresh approval for this collection '
              'and the current complete identity (%s)' % p['approval_status'],
              file=sys.stderr)
        return 10
    actual_id = docker_image_id(TASK_IMAGE)
    if actual_id != TASK_IMAGE_ID_EXPECTED:
        print('REFUSED: actual task image id %s != registered %s (no rebuild here)'
              % (actual_id, TASK_IMAGE_ID_EXPECTED), file=sys.stderr)
        return 5
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print('REFUSED: DEEPSEEK_API_KEY not present in environment', file=sys.stderr)
        return 6
    os.environ['OPENAI_API_KEY'] = api_key
    p['run_id'] = time.strftime('%Y%m%dT%H%M%SZ') + '-word001'
    summary = asyncio.run(run_attempt(root, p))
    print(json.dumps({'run_id': summary['run_id'],
                      'phases': {k: v.get('status') for k, v in summary['outcome']['phases'].items()},
                      'infra_failures': summary['outcome']['infra_failures'],
                      'wall_s': summary['wall_s']}, indent=1))
    return exit_code_for(summary)


if __name__ == '__main__':
    sys.exit(main())
