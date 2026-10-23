import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
roots = ['reports/analysis/AGENTX-FULL-MACRO-v1', 'reports/analysis/OSWORLD-task-behavior-v4', 'reports/analysis/SWE-REBENCH-behavior-v3', 'reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1', 'reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1', 'reports/analysis/TOOLSANDBOX-HEPM-behavior-v3', 'data/catalog/public_trace_acquisition/AGENTX-FULL-20261022', 'data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023', 'data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023']
records = {}
counts = {}
errors = []

def walk(x):
    if isinstance(x, dict):
        if isinstance(x.get('sha256'), str) and len(x['sha256']) == 64 and 'path' in x:
            yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)

for root in roots:
    for manifest in sorted((ROOT / root).glob('*manifest*.json')):
        rows = list(walk(json.loads(manifest.read_text())))
        counts[str(manifest.relative_to(ROOT))] = len(rows)
        for row in rows:
            p = Path(row['path'])
            if not p.is_absolute():
                p = ROOT / p
            if not p.is_file() and (manifest.parent / row['path']).is_file():
                p = manifest.parent / row['path']
            key = (str(p), row['sha256'])
            records[key] = row

total = 0
for (name, expected), row in records.items():
    p = Path(name)
    if not p.is_file():
        errors.append({'path': name, 'problem': 'missing'})
        continue
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    total += p.stat().st_size
    if h.hexdigest() != expected:
        errors.append({'path': name, 'problem': 'sha256', 'expected': expected, 'actual': h.hexdigest()})
    if isinstance(row.get('bytes'), int) and row['bytes'] != p.stat().st_size:
        errors.append({'path': name, 'problem': 'size'})

raw_roots = [
    'data/raw/public/agentx_full/23f152f6f0f9399a85901b89a6458def0ef16729',
    'data/raw/public/swebench_gap/40f164d5b8f1d249bf95a6df8b74b577fd8e519d/SWEBENCH-GAP-20261023',
    'data/raw/public/swebench_instance_results/SWEBENCH-INSTANCE-RESULTS-20261023',
]
parts = [str(p.relative_to(ROOT)) for r in roots + raw_roots
         for p in (ROOT / r).rglob('*') if p.is_file() and
         (p.name.endswith(('.part', '.tmp', '.temp')) or p.name.endswith('~'))]
result = {'schema': 'public-analysis-closeout-verification-v1', 'date': '2026-10-23',
          'status': 'FAIL' if errors else 'PASS',
          'manifest_record_counts': counts, 'manifest_record_checks': sum(counts.values()),
          'unique_path_hash_checks': len(records), 'bytes_hashed': total,
          'errors': errors, 'download_or_report_partial_files': parts,
          'video_files_in_audit_scope': False}
print(json.dumps(result, ensure_ascii=False, indent=2))
