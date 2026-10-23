"""Offline AgentX workload characterization; never executes requests or tools."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import heapq
import json
import math
from pathlib import Path

import numpy as np

from scripts.agentx_full_macro import distribution, file_record

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('reports/analysis/AGENTX-DEEP-ANALYSIS-v1')
BUDGETS = (32768, 65536, 131072, 262144, 524288, 1048576)


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def table(path, rows, fields=None):
    rows = list(rows)
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def lcp(a, b):
    n = min(len(a), len(b))
    if not n:
        return 0
    different = np.flatnonzero(a[:n] != b[:n])
    return int(different[0]) if len(different) else n


class PrefixNode:
    """Compact radix tree of full hash sequences, with an audit witness."""
    __slots__ = ('edge', 'children', 'witness')

    def __init__(self, edge, witness):
        self.edge, self.witness = edge, witness
        self.children = {}


class PrefixHistory:
    def __init__(self):
        self.root = PrefixNode(np.array([], dtype=np.int64), None)

    def add(self, blocks, witness):
        parent, offset = self.root, 0
        while offset < len(blocks):
            key = int(blocks[offset])
            node = parent.children.get(key)
            if node is None:
                parent.children[key] = PrefixNode(blocks[offset:], witness)
                return
            match = lcp(node.edge, blocks[offset:])
            if match < len(node.edge):
                split = PrefixNode(node.edge[:match], node.witness)
                node.edge = node.edge[match:]
                split.children[int(node.edge[0])] = node
                parent.children[key] = split
                node = split
            offset += match
            if offset == len(blocks):
                node.witness = witness
                return
            parent = node

    def query(self, blocks):
        node, offset, witness = self.root, 0, None
        while offset < len(blocks):
            node = node.children.get(int(blocks[offset]))
            if node is None:
                break
            match = lcp(node.edge, blocks[offset:])
            offset += match
            if match:
                witness = node.witness
            if match < len(node.edge):
                break
        return offset, witness


def native_records(raw, line):
    if raw.get('hash_id_scope') != 'local' or raw.get('block_size') != 64:
        raise ValueError('unsupported hash namespace/block size')
    events, groups, identities = [], [], set()

    def walk(items, scope, pointer):
        if not isinstance(items, list):
            raise ValueError('invalid request list')
        order = 0
        for i, q in enumerate(items):
            p = f'{pointer}/{i}'
            if q.get('type') == 'subagent':
                child = scope + (q['agent_id'],)
                if child in identities:
                    raise ValueError('duplicate native group identity')
                identities.add(child)
                groups.append({'path': '/'.join(child), 'pointer': p, 't': q.get('t'),
                               'duration_ms': q.get('duration_ms'), 'status': q.get('status'),
                               'parent': '/'.join(scope), 'type': q.get('subagent_type')})
                walk(q['requests'], child, p + '/requests')
            elif q.get('type') in ('s', 'n'):
                for k in ('t', 'api_time', 'in', 'out'):
                    if type(q.get(k)) not in (int, float) or not math.isfinite(q[k]) or q[k] < 0:
                        raise ValueError(f'invalid {k}: {line}:{p}')
                hashes = q.get('hash_ids')
                if not isinstance(hashes, list) or any(type(x) is not int for x in hashes):
                    raise ValueError('invalid hash vector')
                if len(hashes) * 64 != q['in']:
                    raise ValueError('hash/input mismatch')
                # Python integers can exceed int64 in other corpora. Do not coerce silently.
                a = np.asarray(hashes, dtype=np.int64)
                events.append({'pointer': p, 'scope': '/'.join(scope), 'kind': 'subagent' if scope else 'main',
                               'order': order, 't': q['t'], 'end': q['t'] + q['api_time'],
                               'api_time': q['api_time'], 'input': q['in'], 'output': q['out'],
                               'model': q['model'], 'blocks': a, 'source_line': line,
                               'keep_256k': q['in'] + q['out'] <= 256000})
                order += 1
            else:
                raise ValueError('unknown request type')
    walk(raw['requests'], (), '/requests')
    return events, groups


def overlap_profile(events):
    """Half-open source intervals; ends processed before starts at equal time."""
    changes = defaultdict(lambda: [0, 0])
    for e in events:
        if e['end'] <= e['t']:
            continue
        k = 0 if e['kind'] == 'main' else 1
        changes[e['t']][k] += 1
        changes[e['end']][k] -= 1
    active = [0, 0]
    points, busy, area, overlap, peak, peak_t = [], 0., 0., 0., 0, None
    times = sorted(changes)
    for i, t in enumerate(times):
        active = [active[k] + changes[t][k] for k in (0, 1)]
        n = sum(active)
        if n > peak:
            peak, peak_t = n, t
        points.append({'t': t, 'main': active[0], 'subagent': active[1], 'all': n})
        if i + 1 < len(times):
            d = times[i+1] - t
            busy += d if n else 0
            overlap += d if n > 1 else 0
            area += d * n
    assert math.isclose(area, sum(e['end']-e['t'] for e in events), rel_tol=1e-8, abs_tol=1e-5)
    return {'peak': peak, 'peak_t': peak_t, 'busy_s': busy, 'multi_request_s': overlap,
            'api_interval_sum_s': area, 'overlap_fraction_of_busy': overlap / busy if busy else None}, points


def reuse_metrics(events):
    """Only completed, same-model requests in this session are reusable candidates."""
    histories, streams = {}, {}
    latest, pending = {}, []
    ordered = sorted(events, key=lambda e: (e['t'], e['pointer']))
    for sequence, e in enumerate(ordered):
        while pending and pending[0][0] <= e['t']:
            _, _, old = heapq.heappop(pending)
            histories.setdefault(old['model'], PrefixHistory()).add(old['blocks'], old)
            streams.setdefault((old['model'], old['scope']), PrefixHistory()).add(old['blocks'], old)
            latest[old['model']] = old
        best, witness = histories.get(e['model'], PrefixHistory()).query(e['blocks'])
        same, _ = streams.get((e['model'], e['scope']), PrefixHistory()).query(e['blocks'])
        prior = latest.get(e['model'])
        most_recent = lcp(prior['blocks'], e['blocks']) if prior else 0
        e.update(history_tokens=best*64, same_agent_history_tokens=same*64,
                 cross_agent_extra_tokens=(best-same)*64,
                 latest_completed_prefix_tokens=most_recent*64,
                 reuse_witness_pointer=witness['pointer'] if witness else None,
                 reuse_witness_end=witness['end'] if witness else None,
                 reuse_witness_scope=witness['scope'] if witness else None)
        assert 0 <= same <= best <= len(e['blocks'])
        assert witness is None or witness['end'] <= e['t']
        heapq.heappush(pending, (e['end'], sequence, e))


def progress_rows(events, trace_id, variant):
    scopes, rows = defaultdict(list), []
    for e in events:
        scopes[e['scope']].append(e)
    for scope, items in scopes.items():
        items.sort(key=lambda e: e['order'])
        bins = defaultdict(list)
        for i, e in enumerate(items):
            b = min(19, int(i / (len(items)-1) * 20)) if len(items) > 1 else 0
            e['progress_bin'] = b
            bins[b].append(e['input'])
            if i:
                previous = items[i-1]
                e['adjacent_input_delta'] = e['input'] - previous['input']
                e['adjacent_prefix_tokens'] = lcp(e['blocks'], previous['blocks']) * 64
                e['adjacent_model_same'] = e['model'] == previous['model']
                e['adjacent_interval_gap_s'] = e['t'] - previous['end']
        if not scope:
            for b, values in bins.items():
                rows.append({'variant': variant, 'trace_id': trace_id, 'bin': b,
                             'session_bin_median': float(np.median(values)), 'requests': len(values)})
    return rows


def compact_event(e):
    return {k: v for k, v in e.items() if k != 'blocks'}


def group_audit(events, groups, trace_id, variant):
    rows = []
    for g in groups:
        child = [e for e in events if e['scope'] == g['path'] or e['scope'].startswith(g['path']+'/')]
        t, duration = g['t'], g['duration_ms']
        valid = type(t) in (int, float) and type(duration) in (int, float) and math.isfinite(t) and math.isfinite(duration) and t >= 0 and duration >= 0
        end = t + duration/1000 if valid else None
        rows.append({'variant': variant, 'trace_id': trace_id, **g,
                     'saved_interval_valid': valid, 'saved_end': end, 'child_requests': len(child),
                     'child_start_before_marker': sum(e['t'] < t-1e-6 for e in child) if valid else None,
                     'child_end_after_saved_group': sum(e['end'] > end+1e-6 for e in child) if valid else None})
    return rows


def scan(path, variant, out):
    totals = Counter()
    session_rows, progress, group_rows = [], [], []
    values = defaultdict(list)
    cases = {}
    seen_ids = set()
    ledger = out / f'{variant}_request_metrics.jsonl'
    with Path(path).open() as stream, ledger.open('w') as dest:
        for line, source in enumerate(stream, 1):
            raw = json.loads(source)
            tid = raw['id']
            if tid in seen_ids:
                raise ValueError('duplicate session')
            seen_ids.add(tid)
            events, groups = native_records(raw, line)
            reuse_metrics(events)
            progress += progress_rows(events, tid, variant)
            ga = group_audit(events, groups, tid, variant)
            group_rows += ga
            profile, points = overlap_profile(events)
            main = [e for e in events if e['kind'] == 'main']
            child = [e for e in events if e['kind'] == 'subagent']
            removed = [e for e in events if not e['keep_256k']]
            row = {'variant': variant, 'trace_id': tid, 'source_line': line,
                   'requests': len(events), 'main_requests': len(main), 'subagent_requests': len(child),
                   'groups': len(groups), 'input_sum': sum(e['input'] for e in events),
                   'output_sum': sum(e['output'] for e in events),
                   'main_input_sum': sum(e['input'] for e in main),
                   'subagent_input_sum': sum(e['input'] for e in child),
                   'main_input_median': float(np.median([e['input'] for e in main])) if main else None,
                   'max_input': max((e['input'] for e in events), default=None),
                   'above_256k_requests': len(removed),
                   'above_256k_input_sum': sum(e['input'] for e in removed),
                   'main_context_drop_candidates': sum(e.get('adjacent_input_delta', 0) <= -32768 for e in main),
                   **profile}
            if variant == 'full':
                retained_main = [e for e in main if e['keep_256k']]
                bridged = sum(b['order']-a['order'] > 1 for a, b in zip(retained_main, retained_main[1:]))
                row['cap_bridged_main_adjacent_pairs'] = bridged
                row['cap_removed_main_prefix_requests'] = retained_main[0]['order'] if retained_main else len(main)
                row['cap_removed_main_suffix_requests'] = len(main)-1-retained_main[-1]['order'] if retained_main else 0
            session_rows.append(row)
            for e in events:
                assert 0 <= e['latest_completed_prefix_tokens'] <= e['history_tokens'] <= e['input']
                for group in ('all', e['kind']):
                    prefix = group + ':'
                    totals[prefix+'requests'] += 1
                    for name in ('input', 'output', 'history_tokens', 'same_agent_history_tokens', 'cross_agent_extra_tokens'):
                        totals[prefix+name] += e[name]
                    totals[prefix+'positive_history_requests'] += e['history_tokens'] > 0
                    totals[prefix+'cross_agent_extra_requests'] += e['cross_agent_extra_tokens'] > 0
                    totals[prefix+'no_completed_prefix_requests'] += e['history_tokens'] == 0
                    for budget in BUDGETS:
                        totals[prefix+f'budget_{budget}_tokens'] += min(budget, e['latest_completed_prefix_tokens'])
                    values[prefix+'input'].append(e['input'])
                    values[prefix+'prefix_fraction'].append(e['history_tokens']/e['input'] if e['input'] else 0)
                dest.write(json.dumps({'variant': variant, 'trace_id': tid, **compact_event(e)}, separators=(',', ':'))+'\n')
            if variant == 'full':
                # Keep only small case ledgers, not the raw hash arrays.
                keys = [('most_subagents', row['groups']), ('peak_request_overlap', row['peak']),
                        ('most_context_drops', row['main_context_drop_candidates'])]
                for name, score in keys:
                    if name not in cases or (score, tid) > (cases[name]['score'], cases[name]['trace_id']):
                        cases[name] = {'trace_id': tid, 'score': score, 'summary': row,
                                       'requests': [compact_event(e) for e in events], 'points': points}
            if line % 50 == 0:
                print(f'{variant}: {line} sessions / {totals["all:requests"]:,} requests', flush=True)
    return {'variant': variant, 'sessions': len(session_rows), 'totals': dict(totals),
            'group_count': len(group_rows), 'group_clock_audit': {
                'invalid_saved_intervals': sum(not g['saved_interval_valid'] for g in group_rows),
                'groups_with_child_before_marker': sum(bool(g['child_start_before_marker']) for g in group_rows),
                'groups_with_child_end_after_saved_group': sum(bool(g['child_end_after_saved_group']) for g in group_rows)},
            'peak_request_overlap': distribution([r['peak'] for r in session_rows]),
            'sessions_with_request_overlap': sum(r['peak'] > 1 for r in session_rows)}, session_rows, progress, group_rows, values, cases


def verify_sources():
    manifest = Path('reports/analysis/AGENTX-FULL-MACRO-v1/manifest.json')
    base = json.loads(manifest.read_text())
    summary_path = Path('reports/analysis/AGENTX-FULL-MACRO-v1/summary.json')
    expected_summary = next(r for r in base['outputs'] if r['path'] == str(summary_path))
    if file_record(summary_path)['sha256'] != expected_summary['sha256']:
        raise ValueError('baseline summary identity mismatch')
    expected_paths = {}
    verified = [file_record(manifest), file_record(summary_path)]
    for name, prefix in [('full', 'data/raw/public/agentx_full/'), ('256k', 'data/raw/public/agentx/')]:
        record = next(r for r in base['inputs'] if r['path'].startswith(prefix) and r['path'].endswith('/traces.jsonl'))
        actual = file_record(record['path'])
        if actual['sha256'] != record['sha256'] or actual['bytes'] != record['bytes']:
            raise ValueError('frozen input mismatch: '+record['path'])
        expected_paths[name] = Path(record['path'])
        verified.append(actual)
    return expected_paths, verified, json.loads(summary_path.read_text())


def run(out):
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    paths, verified, baseline = verify_sources()
    if any(out.resolve().is_relative_to(p.parent.resolve()) or p.resolve().is_relative_to(out.resolve()) for p in paths.values()):
        raise ValueError('source/output overlap')
    out.mkdir(parents=True)
    (out/'figures').mkdir()
    (out/'plot_data').mkdir()
    results = {}
    all_sessions, all_progress, all_groups = [], [], []
    for variant in ('full', '256k'):
        print('Scanning '+variant, flush=True)
        results[variant] = scan(paths[variant], variant, out)
        result, sessions, progress, groups, _, _ = results[variant]
        expected = baseline['full' if variant == 'full' else 'capped_256k']
        assert result['sessions'] == expected['trace_count']
        assert result['totals']['all:requests'] == expected['total_model_request_count']
        assert result['totals']['all:input'] == expected['total_input_tokens_reconstructed']
        assert result['totals']['all:output'] == expected['total_output_tokens']
        assert result['group_count'] == expected['subagent_group_count']
        all_sessions += sessions
        all_progress += progress
        all_groups += groups
    assert {r['trace_id'] for r in results['full'][1]} == {r['trace_id'] for r in results['256k'][1]}
    f, c = results['full'][0], results['256k'][0]
    assert f['totals']['all:requests'] - sum(r['above_256k_requests'] for r in results['full'][1]) == c['totals']['all:requests']
    table(out/'per_session.csv', all_sessions, list(dict.fromkeys(k for r in all_sessions for k in r)))
    table(out/'group_clock_audit.csv', all_groups)
    table(out/'plot_data'/'context_progress_per_session.csv', all_progress)
    summary = {'schema': 'agentx-deep-analysis-v1', 'date': '2026-10-23',
               'status': 'PASS_WITH_EXPLICIT_SOURCE_AND_MODEL_LIMITS',
               'full': f, 'capped_256k': c,
               'inputs_verified': verified,
               'steps_executed': ['offline_full_corpus_analysis', 'presentation_chart_generation'],
               'model_calls': 0, 'tool_or_agent_replay': False,
               'prefix_model': 'same session and saved model; only requests completed by current source t; unlimited-history potential is not a cache hit rate',
               'budget_model': 'per-session/model latest-completed-request prefix snapshot, retain first B tokens, replace at every completion; no output KV, no LRU/shared-cache/HBM simulation',
               'timeline': 'source-relative coordinates, main and child t treated as root-absolute per existing adapter; no parent offset added; recorded API overlap is not CPU/GPU concurrency',
               'cap': 'same sessions, overlapping variants, cap condition input+output<=256000; no causal inference from version differences'}
    dump(out/'summary.json', summary)
    dump(out/'case_selection.json', {k: {x: v for x, v in case.items() if x not in ('requests','points')} for k, case in results['full'][5].items()})
    from scripts.agentx_deep_presentation import render
    render(out, summary, results)
    outputs = [file_record(p) for p in sorted(out.rglob('*')) if p.is_file()]
    code = [file_record(Path(__file__)), file_record(Path('scripts/agentx_deep_presentation.py')),
            file_record(Path('tests/test_agentx_deep_analysis.py'))]
    dump(out/'manifest.json', {'schema': 'agentx-deep-analysis-manifest-v1', 'inputs': verified,
                              'analysis_code_and_tests': code, 'outputs': outputs,
                              'input_hashes_rechecked_before_analysis': True,
                              'historical_files_modified': False, 'model_or_tool_requests_executed': False})
    print(json.dumps({'status': summary['status'], 'report': str(out/'summary.md'),
                      'full_requests': f['totals']['all:requests'], 'capped_requests': c['totals']['all:requests']}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args()
    # Script invocation and module imports use the same repository package root.
    run(args.output_dir)
