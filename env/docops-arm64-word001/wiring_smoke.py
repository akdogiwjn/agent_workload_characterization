#!/usr/bin/env python3
"""C+D2: minimal collection wiring smoke over the REAL vendored Harbor lifecycle.

No model calls. Uses the registered task image (docops-word001-task:arm64-adapted-v1)
via Harbor DockerEnvironment (compose up/exec/down), registers the Harbor-owned
container as a FOREIGN container in the existing DockerCliRuntime, samples cgroup
counters through the existing read_counters chain, runs deterministic synthetic
execs only (NOT the official task instruction, NOT the verifier), then lets
Harbor stop+delete and verifies removal.

Budget: total wall <= 120s including cleanup. 1 CPU / 4 GiB / network none.
Run with: .venvs/docops-pilot-01/bin/python env/docops-arm64-word001/wiring_smoke.py
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/home/lcq/agent_workload_characterization')
sys.path.insert(0, str(ROOT / '.venvs' / 'docops-pilot-01' / 'lib' / 'python3.12' / 'site-packages'))
sys.path.insert(0, str(ROOT / 'src'))

from harbor.environments.docker.docker import (  # noqa: E402
    DockerEnvironment, _sanitize_docker_compose_project_name)
from harbor.models.task.config import EnvironmentConfig  # noqa: E402
from harbor.models.trial.paths import TrialPaths  # noqa: E402

from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    DockerCliRuntime, ContainerHandle, ContainerSpec)

TASK_ENV_DIR = ROOT / 'references/repos/DocOps/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed/environment'
IMAGE = 'docops-word001-task:arm64-adapted-v1'
SESSION = 'docops-wiring-smoke-20261008-r3'
WALL_BUDGET_S = 120.0


def docker_ps_by_project(project):
    r = subprocess.run(['docker', 'ps', '--no-trunc', '--filter',
                        'label=com.docker.compose.project=' + project,
                        '--format', '{{.ID}} {{.Names}}'],
                       capture_output=True, text=True, timeout=20)
    rows = [l.split() for l in r.stdout.strip().splitlines() if l.strip()]
    return rows


async def main():
    t_start = time.monotonic()
    events = [{'phase': 'script_start', 't_monotonic_ns': time.monotonic_ns()}]
    trial_dir = Path('/tmp/opencode2/docops-wiring-trial')
    subprocess.run(['rm', '-rf', str(trial_dir)], check=False)
    trial = TrialPaths(trial_dir=trial_dir)
    trial.mkdir()

    cfg = EnvironmentConfig(
        docker_image=IMAGE, cpus=1, memory_mb=4096, storage_mb=10240,
        allow_internet=False, workdir='/root')
    env = DockerEnvironment(
        environment_dir=TASK_ENV_DIR,
        environment_name='docops-word001-wiring-smoke',
        session_id=SESSION,
        trial_paths=trial,
        task_env_config=cfg,
    )

    project = _sanitize_docker_compose_project_name(SESSION)
    events.append({'phase': 'harbor_start_begin', 't_monotonic_ns': time.monotonic_ns()})
    await env.start(force_build=False)
    events.append({'phase': 'harbor_start_done', 't_monotonic_ns': time.monotonic_ns()})

    rows = docker_ps_by_project(project)
    assert rows, 'no container found for compose project %s' % project
    cid, cname = rows[0]
    events.append({'phase': 'container_identified',
                   'container_id': cid, 'container_name': cname,
                   'compose_project': project,
                   't_monotonic_ns': time.monotonic_ns()})

    # --- collection wiring: Harbor-owned container observed via the EXISTING runtime chain ---
    # Ownership check: DockerCliRuntime.cleanup_run only removes containers whose
    # names match its own prefix pattern (awc-<collection>-<run_id>-). The Harbor
    # compose container name cannot match; the script also never calls
    # runtime.stop/cleanup_run. Lifecycle and deletion belong to Harbor alone.
    runtime = DockerCliRuntime(authorized=True, collection='DOCOPS-WIRING-SMOKE')
    runtime_cleanup_prefix = runtime._name_prefix + '-' + SESSION + '-'
    assert not cname.startswith(runtime._name_prefix), \
        'container name unexpectedly inside runtime cleanup namespace'
    events.append({'phase': 'ownership_registered', 'owner': 'harbor',
                   'container_name': cname,
                   'runtime_cleanup_prefix_not_matching': runtime_cleanup_prefix,
                   't_monotonic_ns': time.monotonic_ns()})
    handle = ContainerHandle(
        container_id=cid,
        spec=ContainerSpec(run_id=SESSION, scope='agent_container', image=IMAGE,
                           network='none'))
    runtime._resolve_cgroup(handle)
    events.append({'phase': 'cgroup_resolved',
                   'cgroup_version': handle.cgroup_version,
                   'cgroup_dir': str(handle.cgroup_dir),
                   't_monotonic_ns': time.monotonic_ns()})

    samples = []

    def sample(tag):
        s = runtime.read_counters(handle, time.monotonic_ns())
        row = s.to_dict()
        row['tag'] = tag
        samples.append(row)
        return row

    sample('baseline')
    # sampling during a deterministic synthetic workload (NOT the task instruction)
    events.append({'phase': 'synthetic_exec_begin', 't_monotonic_ns': time.monotonic_ns()})
    r = await env.exec(command="python3 -c \"import docx, openpyxl, pptx, pypdf, pdfplumber; "
                               "d=docx.Document(); d.add_paragraph('wiring smoke'); "
                               "d.save('/root/smoke_out.docx'); print('SYNTH_OK')\"",
                       timeout_sec=30)
    events.append({'phase': 'synthetic_exec_done', 'return_code': r.return_code,
                   'stdout_tail': (r.stdout or '')[-60:],
                   't_monotonic_ns': time.monotonic_ns()})
    sample('after_exec1')

    # verify the written artifact exists inside the container (read-only check)
    r2 = await env.exec(command="ls -la /root/smoke_out.docx && python3 -c \""
                                "import docx; print('REOPEN_OK', docx.Document('/root/smoke_out.docx').paragraphs[-1].text)\"",
                        timeout_sec=20)
    events.append({'phase': 'artifact_check', 'return_code': r2.return_code,
                   'stdout_tail': (r2.stdout or '')[-80:],
                   't_monotonic_ns': time.monotonic_ns()})

    # second sampling window (idle) to show counter deltas
    for i in range(4):
        await asyncio.sleep(0.5)
        sample('window2_%d' % i)

    events.append({'phase': 'harbor_stop_begin', 'delete': True,
                   't_monotonic_ns': time.monotonic_ns()})
    await env.stop(delete=True)
    events.append({'phase': 'harbor_stop_done', 't_monotonic_ns': time.monotonic_ns()})

    removal = runtime.verify_removal(handle)
    still = docker_ps_by_project(project)
    events.append({'phase': 'removal_verified', 'result': removal,
                   'containers_left_for_project': len(still),
                   't_monotonic_ns': time.monotonic_ns()})

    wall = time.monotonic() - t_start
    out = {
        'schema': 'docops-wiring-smoke-v1',
        'session': SESSION, 'compose_project': project,
        'image': IMAGE, 'container_id': cid, 'container_name': cname,
        'cgroup_version': handle.cgroup_version,
        'cgroup_dir': str(handle.cgroup_dir),
        'events': events, 'samples': samples,
        'wall_seconds': round(wall, 2),
        'within_budget': wall <= WALL_BUDGET_S,
    }
    out_path = ROOT / 'env/docops-arm64-word001/wiring-smoke-result.json'
    out_path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ('events', 'samples')}, indent=1))
    print('samples:', len(samples), '| events:', len(events))
    assert removal == 'removed' and not still, 'container cleanup not verified'
    assert wall <= WALL_BUDGET_S, 'wall budget exceeded'
    print('WIRING SMOKE PASS')


if __name__ == '__main__':
    asyncio.run(main())
