"""One bounded, model-free check of the fixed Excel image and scan wrapper."""
import json
import os
from pathlib import Path
import subprocess
import time

from agent_workload_characterization.collectors.execution_measurement import container_directory_footprint_snapshot
from agent_workload_characterization.runners.container_runtime import DockerCliRuntime, ContainerSpec

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).with_name('no-model-check.json')
assert not DEST.exists(), 'check already consumed; do not overwrite'
frozen = json.loads((ROOT / 'env/docops-measurement-volcano-01/frozen-identity.json').read_text())['identity']
task = frozen['task']
os.environ['DOCKER_HOST'] = frozen['docker_endpoint']
os.environ.pop('DOCKER_CONTEXT', None)
start = time.monotonic()
deadline = start + 120
work = start + 85
runtime = DockerCliRuntime(authorized=True, collection='office-scan-check-02')
handle = None
record = {'kind': 'model_free_container_check', 'model_calls': 0, 'status': 'failed',
          'started_monotonic_ns': time.monotonic_ns(), 'image_expected': task['image_id']}

def inspect():
    p = subprocess.run(['docker', '--host', frozen['docker_endpoint'], 'image', 'inspect',
                        task['image_ref'], '--format', '{{.Id}} {{.Os}}/{{.Architecture}}'],
                       capture_output=True, text=True, check=True, timeout=min(5, deadline-time.monotonic()))
    image, platform = p.stdout.strip().split()
    assert (image, platform) == (task['image_id'], 'linux/arm64'), 'image identity mismatch'
    return {'id': image, 'platform': platform, 'returncode': p.returncode}

def remaining():
    value = min(10, work - time.monotonic())
    if value <= 0: raise TimeoutError('check work deadline')
    return value

try:
    record['image_before'] = inspect()
    spec = ContainerSpec('no-model-scan-02', 'scan', task['image_ref'], cwd='/',
                         cpu_limit='1', mem_limit='4g', network='none', pull='never')
    handle = runtime.start(spec, deadline=min(work, time.monotonic()+20))
    record['container_id'] = handle.container_id
    setup = runtime.execute(handle, 'python3 --version && mkdir -p /root/submission', timeout_s=remaining())
    record['python_check'] = {'returncode': setup['returncode'], 'output': setup['output'][:80]}
    assert setup['returncode'] == 0
    paths = [{'path': '/root/submission', 'role': 'task_workspace_and_submission',
              'scope': 'agent_container:/root/submission', 'ownership': 'check_private'}]
    record['before'] = container_directory_footprint_snapshot(runtime, handle, paths, timeout_s=remaining())
    write = runtime.execute(handle, "python3 -c \"from pathlib import Path; Path('/root/submission/awc_scan_fixture.bin').write_bytes(b'x'*32768)\"", timeout_s=remaining())
    assert write['returncode'] == 0
    record['after'] = container_directory_footprint_snapshot(runtime, handle, paths, timeout_s=remaining())
    assert record['before']['status'] == record['after']['status'] == 'complete'
    record['growth_bytes'] = record['after']['entries'][0]['bytes'] - record['before']['entries'][0]['bytes']
    assert record['growth_bytes'] == 32768
    record['status'] = 'passed'
except Exception as exc:
    record['error_type'] = type(exc).__name__
finally:
    try:
        if handle is not None:
            runtime.stop(handle, timeout_s=min(15, max(.1, deadline-time.monotonic())))
            record['container_removal'] = runtime.verify_removal(handle, timeout_s=min(10, max(.1, deadline-time.monotonic())))
        else:
            cleanup = runtime.cleanup_pending(timeout_s=min(15, max(.1, deadline-time.monotonic())))
            record['pending_cleanup_status'] = getattr(cleanup, 'status', None)
        record['image_after'] = inspect()
        if record.get('container_removal') != 'removed': record['status'] = 'failed'
    except Exception as exc:
        record['cleanup_error_type'] = type(exc).__name__
        record['status'] = 'failed'
    record['wall_s'] = time.monotonic()-start
    record['within_120s'] = record['wall_s'] <= 120
    with DEST.open('x') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k:v for k,v in record.items() if k not in ('before','after')}, ensure_ascii=False))
raise SystemExit(0 if record['status']=='passed' and record['within_120s'] else 1)
