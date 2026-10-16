"""Read-only document relocation audit. Never rewrite historical manifests or approvals."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ('README.md', 'project_state.json', 'docs', 'src', 'scripts',
              'tests', 'reports', 'env', 'data/catalog', 'data/raw/generated',
              'workload_catalog', '.github')
SKIP_PARTS = {'.git', '__pycache__', '.venvs', 'node_modules', 'harbor-src', 'source'}
SKIP_FILES = {'docs/archive_index.json', 'docs/archive_reference_audit.json',
              'docs/history_index.md'}
TEXT_SUFFIXES = {'.md', '.json', '.jsonl', '.py', '.csv', '.yaml', '.yml',
                 '.txt', '.html', '.toml', '.log'}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_path(root, value):
    p = Path(value)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Unsafe document locator: ' + value)
    result = root / p
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Locator escapes project: ' + value)
    return result


def load_index(root):
    data = json.loads((root / 'docs/archive_index.json').read_text())
    result = {}
    for row in data['entries']:
        logical, physical = row['original'], row['archived']
        safe_path(root, logical)
        target = safe_path(root, physical)
        if logical in result or not physical.startswith('local_archive/'):
            raise ValueError('Duplicate or invalid archive entry: ' + logical)
        if not target.is_file() or digest(target) != row['sha256'] or target.stat().st_size != row['bytes']:
            raise ValueError('Archived document bytes/hash mismatch: ' + logical)
        result[logical] = row
    return result


def resolve_document(root, logical, expected_sha256=None):
    row = load_index(root)[logical]
    if expected_sha256 is not None and row['sha256'] != expected_sha256:
        raise ValueError('Historical hash mismatch; relocation is not a content repair: ' + logical)
    return safe_path(root, row['archived'])


def scan_files(root):
    for name in SCAN_ROOTS:
        base = root / name
        if not base.exists():
            continue
        if base.is_file():
            yield base
            continue
        for parent, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_PARTS and not (Path(parent) / d).is_symlink())
            for filename in sorted(names):
                p = Path(parent) / filename
                if not p.is_symlink() and p.suffix in TEXT_SUFFIXES and p.relative_to(root).as_posix() not in SKIP_FILES:
                    yield p


def audit(root):
    index = load_index(root)
    names = {Path(k).name.encode(): k for k in index}
    if len(names) != len(index):
        raise ValueError('Ambiguous document basenames')
    pattern = re.compile(rb'(?<![A-Za-z0-9_])(?:' + b'|'.join(re.escape(n) for n in names) + rb')(?![A-Za-z0-9_.-])')
    refs, checks, unchecked = [], [], []
    count = total = 0
    for path in scan_files(root):
        rel = path.relative_to(root).as_posix()
        count += 1
        total += path.stat().st_size
        found = {}
        with path.open('rb') as handle:
            tail, offset = b'', 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                block = tail + chunk
                # Most large trace JSON contains no document suffix at all.
                # Keep the overlap even when skipping a block so split names are found.
                hits = pattern.finditer(block) if b'.md' in block else ()
                for hit in hits:
                    if hit.end() <= len(tail):
                        continue
                    logical = names[hit.group()]
                    entry = index[logical]
                    prefix = block[max(0, hit.end() - 1024):hit.end()]
                    new = prefix.endswith(entry['archived'].encode())
                    key = (logical, new)
                    if key not in found:
                        found[key] = {'file': rel, 'original': logical, 'archived': entry['archived'],
                                      'already_new_locator': new, 'occurrences': 0,
                                      'first_byte_offset': offset - len(tail) + hit.start(),
                                      'policy': 'preserve_historical_record_use_index' if rel.startswith(('reports/', 'env/', 'data/')) else 'current_navigation_or_explicit_logical_key'}
                    found[key]['occurrences'] += 1
                offset += len(chunk)
                tail = block[-1024:]
        refs.extend(found.values())
        if not found or path.suffix != '.json':
            continue
        if path.stat().st_size > 32 * 1024 * 1024:
            unchecked.append({'file': rel, 'reason': 'lexically_scanned_but_not_loaded_for_hash_structure_due_to_size'})
            continue
        try:
            tree = json.loads(path.read_text())
        except (ValueError, UnicodeError):
            unchecked.append({'file': rel, 'reason': 'not_parseable_as_one_json_document'})
            continue
        stack = [('', tree)]
        while stack:
            pointer, node = stack.pop()
            pairs = []
            if isinstance(node, dict):
                for key, value in node.items():
                    stack.append((pointer + '/' + str(key), value))
                    if key in index and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value):
                        pairs.append((key, value, None))
                logical = node.get('path') or node.get('file') or node.get('source')
                expected = node.get('sha256')
                if isinstance(logical, str) and logical.startswith(str(root) + '/'):
                    logical = logical[len(str(root)) + 1:]
                if isinstance(logical, str) and logical in index and isinstance(expected, str):
                    pairs.append((logical, expected, node.get('bytes')))
            elif isinstance(node, list):
                stack.extend((pointer + '/' + str(i), value) for i, value in enumerate(node))
            for logical, expected, size in pairs:
                row = index[logical]
                ok = expected == row['sha256'] and (size is None or size == row['bytes'])
                checks.append({'file': rel, 'pointer': pointer, 'original': logical,
                               'archived': row['archived'], 'expected_sha256': expected,
                               'archived_sha256': row['sha256'], 'status': 'exact_relocated' if ok else 'preexisting_content_drift'})
    return {'schema': 'document-reference-audit-v1', 'historical_records_rewritten': False,
            'scanned_files': count, 'scanned_bytes': total, 'relocated_documents': len(index),
            'excluded': ['local_archive (original bytes preserved)', 'public trace payloads',
                         'virtual environments', 'external/vendor frozen source', 'non-text files'],
            'reference_files': len({r['file'] for r in refs}),
            'hash_check_counts': dict(Counter(r['status'] for r in checks)),
            'references': refs, 'hash_checks': checks, 'hash_structure_unchecked': unchecked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--resolve')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.resolve:
        result = {'path': str(resolve_document(args.root, args.resolve, args.sha256))}
    else:
        result = audit(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
