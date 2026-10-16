#!/usr/bin/env python3
"""Offline analysis of the explicitly sealed REPEAT-02 nine-run collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docops_office_repeat_characterization as old
from docops_word_resource_analysis import file_record
from p1_12_coding_repeat_characterization_v2 import merge_intervals_ns, union_ns

COLLECTION = 'DOCOPS-OFFICE-REPEAT-02'
REPORT = 'reports/resource/' + COLLECTION
RAW = 'data/raw/generated/' + COLLECTION
ENV = 'env/docops-office-repeat-02'
OUT = 'reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1'
TASKS, SCHEDULE = old.TASKS, old.SCHEDULE
NS = 1_000_000_000


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def stamp(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def distribution(values, ids=None):
    result = old._describe(values, [{'id': k, 'value': v} for k, v in zip(ids or range(len(values)), values)])
    return {**result, 'objects': len(values), 'missing_or_invalid': len(values) - result['n']}


def partition(window, groups):
    """Exact mutually exclusive integer-ns occupancy; saved intervals, not inference."""
    start, end = window
    clipped = {k: merge_intervals_ns([(max(start, a), min(end, b)) for a, b in rows
                                     if b > start and a < end]) for k, rows in groups.items()}
    edges = sorted({start, end, *(t for rows in clipped.values() for pair in rows for t in pair)})
    segments, totals = [], Counter()
    for a, b in zip(edges, edges[1:]):
        active = [k for k, rows in clipped.items() if any(s <= a and b <= e for s, e in rows)]
        label = '+'.join(active) or 'uncovered'
        segments.append((a, b, label))
        totals[label] += b - a
    return {'window_ns': [start, end], 'segments': segments,
            'exclusive_ns': dict(totals), 'residual_ns': end - start - sum(totals.values()),
            'union_s': {k: union_ns(v) / NS for k, v in clipped.items()},
            'overlap_s': sum(v for k, v in totals.items() if '+' in k) / NS,
            'exclusive_s': {k: v / NS for k, v in totals.items()}}


def pair_events(events):
    buckets = defaultdict(list)
    issues, result = [], []
    for line, event in enumerate(events, 1):
        if event.get('kind') in {'llm_request', 'tool_call'}:
            buckets[(event['kind'], event.get('event_id'))].append((line, event))
    for (kind, eid), rows in buckets.items():
        opens = [r for r in rows if r[1].get('status') == 'open']
        ends = [r for r in rows if r[1].get('status') != 'open']
        faults = []
        if not eid: faults.append('missing_id')
        if not opens: faults.append('orphan_terminal')
        if not ends: faults.append('missing_terminal')
        if len(opens) > 1: faults.append('duplicate_open')
        if len(ends) > 1: faults.append('duplicate_terminal')
        if not faults:
            (line0, a), (line1, b) = opens[0], ends[0]
            t0, t1 = a.get('t_monotonic_ns'), b.get('t_monotonic_ns')
            if not stamp(t0) or not stamp(t1) or t1 < t0: faults.append('invalid_time')
            if a.get('clock_domain') != 'system_monotonic' or b.get('clock_domain') != 'system_monotonic': faults.append('clock_unknown')
            if line1 <= line0: faults.append('terminal_before_open_in_saved_order')
        if faults:
            issues.append({'kind': kind, 'event_id': eid, 'reasons': faults, 'lines': [n for n, _ in rows]})
            continue
        result.append({'kind': kind, 'event_id': eid, 'open_line': line0, 'terminal_line': line1,
                       'start_ns': t0, 'end_ns': t1, 'wall_s': (t1-t0)/NS,
                       'start_attrs': a.get('attrs', {}), 'end_attrs': b.get('attrs', {}),
                       'terminal_status': b.get('status')})
    return result, {'event_counts': dict(Counter((e['kind'] + ':' + e['status']) for e in events
                                               if e.get('kind') in {'llm_request', 'tool_call'})),
                    'paired': len(result), 'issues': issues}


def valid_read(c, field):
    if not number(c.get(field)) or c[field] < 0: return False
    status = c.get('read_status', {})
    key = {'cpu_usage_usec': 'cpuacct.usage', 'mem_current_bytes': 'memory.usage_in_bytes',
           'mem_peak_bytes': 'memory.max_usage_in_bytes'}.get(field, 'io')
    return str(status.get(key, '')).startswith('ok')


def counter_change(a, b):
    if not a or not b:
        return {'status': 'unavailable_missing_boundary', 'cpu_core_s': None,
                'io_read_bytes': None, 'io_write_bytes': None, 'memory_current_change_bytes': None}
    ok_clock = stamp(a.get('t_monotonic_ns')) and stamp(b.get('t_monotonic_ns')) and b['t_monotonic_ns'] >= a['t_monotonic_ns']
    ok_scope = (a.get('scope') == b.get('scope') and a.get('scope_kind') == b.get('scope_kind')
                and a.get('container_id') == b.get('container_id'))
    result = {'status': 'observed_shared_counter_window' if ok_clock and ok_scope else 'invalid_clock_or_scope',
              'read_window_ns': [a.get('t_monotonic_ns'), b.get('t_monotonic_ns')], 'field_status': {}}
    for field, name, scale in [('cpu_usage_usec', 'cpu_core_s', 1e6), ('io_read_bytes', 'io_read_bytes', 1),
                               ('io_write_bytes', 'io_write_bytes', 1)]:
        state = 'valid' if ok_clock and ok_scope and valid_read(a, field) and valid_read(b, field) else 'missing_invalid_read_or_scope'
        if state == 'valid' and b[field] < a[field]: state = 'counter_decreased'
        result[name] = (b[field]-a[field])/scale if state == 'valid' else None
        result['field_status'][name] = state
    result['memory_current_change_bytes'] = b['mem_current_bytes']-a['mem_current_bytes'] if ok_clock and ok_scope and valid_read(a, 'mem_current_bytes') and valid_read(b, 'mem_current_bytes') else None
    result['kernel_peak_at_start_bytes'] = a['mem_peak_bytes'] if valid_read(a, 'mem_peak_bytes') else None
    result['kernel_peak_at_end_bytes'] = b['mem_peak_bytes'] if valid_read(b, 'mem_peak_bytes') else None
    return result


def sample_resources(samples, phase_windows, call_windows):
    if not samples:
        return {'sample_count': 0, 'window_s': None, 'cpu_core_s': None, 'memory_current_peak_bytes': None,
                'kernel_peak_bytes': None, 'host_rss_peak_bytes': None, 'issues': ['no_samples'],
                'io_block_service_bytes': {'io_read_bytes': None, 'io_write_bytes': None}}
    ts = [x.get('t_monotonic_ns') for x in samples]
    good_time = all(stamp(t) for t in ts) and all(b > a for a, b in zip(ts, ts[1:]))
    issues = [] if good_time else ['sample_time_missing_or_nonincreasing']
    cpu = [x.get('container', {}).get('cpu_usage_usec') for x in samples]
    missing = Counter(); regressions = Counter()
    for x in samples:
        for f in ['cpu_usage_usec', 'mem_current_bytes', 'mem_peak_bytes', 'io_read_bytes', 'io_write_bytes']:
            if not valid_read(x.get('container', {}), f): missing[f] += 1
        if x.get('clock_domain') != 'system_monotonic' or x.get('container', {}).get('t_monotonic_ns') != x.get('t_monotonic_ns'):
            issues.append('sample_clock_domain_or_read_timestamp_mismatch')
    for a, b in zip(samples, samples[1:]):
        for f in ['cpu_usage_usec', 'io_read_bytes', 'io_write_bytes']:
            if number(a['container'].get(f)) and number(b['container'].get(f)) and b['container'][f] < a['container'][f]: regressions[f] += 1
    phase_parts = partition((ts[0], ts[-1]), phase_windows) if good_time else None
    call_parts = partition((ts[0], ts[-1]), call_windows) if good_time else None
    phase_bins, call_bins, invalid, intervals = Counter(), Counter(), [], []
    for i, (a, b) in enumerate(zip(samples, samples[1:])):
        change = counter_change(a['container'], b['container'])
        if not stamp(ts[i]) or not stamp(ts[i+1]) or ts[i+1] <= ts[i] or change['cpu_core_s'] is None or not good_time or issues:
            invalid.append(i);continue
        def label(parts):
            covered = {k for left, right, k in parts['segments'] if left < ts[i+1] and right > ts[i]}
            return next(iter(covered)) if len(covered) == 1 else 'mixed_boundary'
        stage, activity = label(phase_parts), label(call_parts)
        phase_bins[stage] += change['cpu_core_s'];call_bins[activity] += change['cpu_core_s']
        intervals.append({'index': i, 'start_ns': ts[i], 'end_ns': ts[i+1], 'cpu_core_s': change['cpu_core_s'],
                          'phase_class': stage, 'call_class': activity})
    total = (cpu[-1]-cpu[0])/1e6 if good_time and not missing['cpu_usage_usec'] and not regressions['cpu_usage_usec'] and not issues else None
    def peak(field):
        values = [x['container'][field] for x in samples if valid_read(x['container'], field)]
        return max(values) if values else None
    rss = [x.get('host_agent', {}).get('rss_bytes') for x in samples]
    rss_values = [v for v in rss if number(v) and v >= 0]
    host = [x.get('host_agent', {}) for x in samples]
    ticks = [x.get('cpu_ticks') for x in host]
    host_valid = (good_time and all(number(t) and t >= 0 for t in ticks)
                  and all(x.get('read_status', {}).get('stat') == 'ok' for x in host)
                  and number(host[0].get('clk_tck')) and host[0]['clk_tck'] > 0
                  and all((x.get('pid'), x.get('starttime_ticks'), x.get('clk_tck')) ==
                          (host[0].get('pid'), host[0].get('starttime_ticks'), host[0].get('clk_tck')) for x in host)
                  and all(b >= a for a,b in zip(ticks,ticks[1:])))
    end = counter_change(samples[0]['container'], samples[-1]['container'])
    for field in ['io_read_bytes', 'io_write_bytes']:
        if missing[field] or regressions[field] or not good_time: end[field] = None
    gaps = [(b-a)/NS for a, b in zip(ts, ts[1:]) if stamp(a) and stamp(b)]
    subtotal = sum(x['cpu_core_s'] for x in intervals)
    read_cost = [x['read_wall_ns'] for x in samples if number(x.get('read_wall_ns')) and x['read_wall_ns'] >= 0]
    return {'sample_count': len(samples), 'window_ns': [ts[0], ts[-1]], 'window_s': (ts[-1]-ts[0])/NS if good_time else None,
            'cpu_core_s': total, 'memory_current_peak_bytes': peak('mem_current_bytes'), 'kernel_peak_bytes': peak('mem_peak_bytes'),
            'host_rss_peak_bytes': max(rss_values) if rss_values else None, 'host_rss_missing': len(rss)-len(rss_values),
            'shared_host_cpu_core_s': (ticks[-1]-ticks[0])/host[0]['clk_tck'] if host_valid else None,
            'shared_host_cpu_status': 'valid_same_pid_starttime_tick_delta' if host_valid else 'unavailable_missing_invalid_or_changed_process',
            'shared_host_identity': {k: host[0].get(k) for k in ['pid','starttime_ticks','clk_tck','scope']},
            'sample_gap_s': distribution(gaps), 'missing_reads': dict(missing), 'counter_regressions': dict(regressions), 'issues': sorted(set(issues)),
            'io_block_service_bytes': {f: end[f] for f in ['io_read_bytes', 'io_write_bytes']},
            'cpu_partition': {'phase_core_s': dict(phase_bins), 'call_core_s': dict(call_bins), 'intervals': intervals,
                              'invalid_interval_indices': invalid, 'valid_interval_subtotal_core_s': subtotal,
                              'full_window_residual_core_s': total-subtotal if total is not None else None},
            'collector_read_wall_s': sum(read_cost) / NS if read_cost else None,
            'collector_read_wall_missing': len(samples)-len(read_cost),
            'collector_read_wall_status': 'complete_observed_subtotal' if len(read_cost)==len(samples) else 'partial_observed_subtotal' if read_cost else 'unavailable',
            'memory_current_points': [{'t_ns': x.get('t_monotonic_ns'), 'bytes': x['container'].get('mem_current_bytes') if valid_read(x['container'], 'mem_current_bytes') else None} for x in samples]}


def verify_inputs(root):
    used = {}; drift = []; counts = Counter()
    def read(path):
        used[str(path.relative_to(root))] = file_record(root, path)
        return old.load_json(path)
    plan = read(root/ENV/'plan-identity.json'); frozen = read(root/ENV/'frozen-identity.json')
    identity = plan['identity']; digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if identity != frozen['identity'] or digest != plan['identity_sha256'] or digest != frozen['identity_sha256']:
        raise ValueError('full historical plan/frozen identity mismatch')
    code = {x['path'] for x in identity['code_and_runtime_files']}
    def check(base, row):
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('unsafe manifest path')
        p = base/rel; actual = file_record(root, p) if p.is_file() else None
        match = actual and actual['sha256'] == row['sha256'] and ('bytes' not in row or actual['bytes'] == row['bytes'])
        if not match:
            if str(p.relative_to(root)) in code:
                drift.append({'path': str(p.relative_to(root)), 'historical': row, 'current': actual});return
            raise ValueError('archive/input hash mismatch or missing: '+str(p.relative_to(root)))
        used[actual['path']] = actual;counts['hash_records_verified'] += 1
    batch = read(root/REPORT/'batch-summary.json'); bm = read(root/REPORT/'batch-manifest.json')
    approval = read(root/REPORT/'APPROVAL.json'); attempt = read(root/REPORT/'ATTEMPT_STARTED.json')
    validation = read(root/REPORT/'VALIDATION.json'); vm = read(root/REPORT/'VALIDATION-MANIFEST.json')
    for obj in [batch, bm, approval, attempt, validation, vm]:
        if obj.get('identity_sha256') != digest: raise ValueError('archived identity digest conflict')
    if batch['collection'] != COLLECTION or approval['collection'] != COLLECTION or approval['user_approval'] != 'approved': raise ValueError('collection/approval conflict')
    for m in [bm, vm]:
        if Path(m['input_root']) != root or Path(m['output_root']) != root: raise ValueError('manifest root conflict')
        for name in ['inputs', 'outputs']:
            for item in m[name]:check(root, item)
    expected = [(r, task) for r, tasks in enumerate(SCHEDULE) for task in tasks]
    rows = batch['results']
    if [(x['round'], x['task_key']) for x in rows] != expected or len({x['run_id'] for x in rows}) != len(expected): raise ValueError('explicit 3x3 schedule/run identity mismatch')
    refs = {Path(x['path']).parent.name: x for x in bm['raw_run_manifests']}
    if set(refs) != {x['run_id'] for x in rows} or len(bm['raw_run_manifests']) != len(rows): raise ValueError('raw manifest reference set conflict')
    for row in rows:
        p = root/RAW/row['run_id'];check(root, refs[row['run_id']]);m = read(p/'manifest.json')
        if any(m.get(k) != row.get(k) for k in ['run_id', 'round', 'task_key', 'identity_sha256']): raise ValueError('raw identity mismatch')
        for item in m['inputs']:check(root, item)
        for item in m['outputs']:check(p, item)
        actual = {str(q.relative_to(p)) for q in p.rglob('*') if q.is_file()}
        if actual != {x['path'] for x in m['outputs']} | {'manifest.json'}: raise ValueError('formal run file set differs from archive')
        counts['raw_outputs'] += len(m['outputs'])
    return batch, identity, used, {'historical_full_structure_equal': True, 'identity_sha256': digest,
                                  'current_code_readback_drift': drift, 'counts': dict(counts),
                                  'approval_structure_note': 'approval/attempt/archive bind digest; full structure exists in matching plan/frozen, not assumed duplicated in every record'}


def analyze_run(root, row):
    p = root/RAW/row['run_id'];s = old.load_json(p/'summary.json');m = old.load_json(p/'measurement.json');env = old.load_json(p/'environment.json')
    if any(s.get(k) != row.get(k) for k in ['run_id', 'round', 'task_key', 'identity_sha256']): raise ValueError('summary identity conflict')
    phases = s['outcome']['phases']
    if row['termination'] != phases['agent']['status'] or row['reward'] != phases['verifier'].get('reward'): raise ValueError('outcome conflict')
    started=old.load_json(p/'ATTEMPT_STARTED.json');completed=old.load_json(p/'ATTEMPT_COMPLETED.json')
    if any(started.get(k) != row.get(k) for k in ['run_id','task_key','round','identity_sha256']) or started.get('collection') != COLLECTION:
        raise ValueError('raw attempt identity conflict')
    if completed.get('run_id') != row['run_id'] or completed.get('wall_s') != s['wall_s']:
        raise ValueError('raw final wall/run conflict')
    evpath = p/'agent/events.jsonl';events = [json.loads(l) for l in evpath.read_text().splitlines() if l.strip()]
    pairs, pairing = pair_events(events)
    requests = [x for x in pairs if x['kind'] == 'llm_request'];tools = [x for x in pairs if x['kind'] == 'tool_call']
    request_ids = {x['event_id'] for x in requests}
    for x in tools:
        if x['start_attrs'].get('role') == 'agent' and x['start_attrs'].get('request_event_id') not in request_ids:
            pairing['issues'].append({'kind': 'tool_call', 'event_id': x['event_id'], 'reasons': ['unlinked_request_id']})
    life = s['events'];phase = old._event_phase(life)
    phase_windows = {k: [(v['start_monotonic_ns'], v['end_monotonic_ns'])] for k, v in phase.items()
                     if k in ['agent_setup', 'agent', 'verifier'] and v['status'] != 'unavailable'}
    call_windows = {'request': [(x['start_ns'], x['end_ns']) for x in requests],
                    'bootstrap': [(x['start_ns'], x['end_ns']) for x in tools if x['start_attrs'].get('role') == 'bootstrap'],
                    'agent_tool': [(x['start_ns'], x['end_ns']) for x in tools if x['start_attrs'].get('role') == 'agent']}
    agent_time = partition(phase_windows['agent'][0], call_windows) if 'agent' in phase_windows else None
    if pairing['issues'] and agent_time: agent_time['status'] = 'partial_due_to_event_pairing_issues'
    elif agent_time: agent_time['status'] = 'complete_saved_interval_partition'
    times = [e.get('t_monotonic_ns') for e in life]
    if not all(stamp(t) for t in times) or any(b < a for a,b in zip(times,times[1:])): raise ValueError('lifecycle clock invalid')
    all_life_windows = {k: [(v['start_monotonic_ns'], v['end_monotonic_ns'])] for k,v in phase.items() if v['status'] != 'unavailable'}
    lifecycle_time = partition((times[0], times[-1]), all_life_windows)
    lifecycle_time['archive_note'] = 'archive marker span, not complete archival duration; attempt wall is separately saved'
    byname = {e['phase']: e for e in life};bounds = {}
    for name, (a,b) in {'agent_setup': ('agent_setup_begin','agent_setup_done'), 'agent': ('agent_begin','agent_end'), 'verifier': ('verifier_begin','verifier_end')}.items():
        ea, eb = byname.get(a,{}), byname.get(b,{})
        change = counter_change(ea.get('shared_resource_boundary'), eb.get('shared_resource_boundary'))
        change['event_window_ns'] = [ea.get('t_monotonic_ns'),eb.get('t_monotonic_ns')]
        change['read_minus_event_ns'] = [e.get('shared_resource_boundary',{}).get('t_monotonic_ns')-e['t_monotonic_ns'] if e.get('shared_resource_boundary') else None for e in [ea,eb]]
        selected = [x['container'] for x in s['samples'] if name in phase_windows and phase_windows[name][0][0] <= x['t_monotonic_ns'] <= phase_windows[name][0][1]]
        vals = [x['mem_current_bytes'] for x in selected if valid_read(x,'mem_current_bytes')]
        change['within_event_window_memory_current_sample_peak_bytes'] = max(vals) if vals else None
        change['within_event_window_sample_count'] = len(selected)
        cpu_sequence = [ea.get('shared_resource_boundary',{}), *selected, eb.get('shared_resource_boundary',{})]
        cpus = [c.get('cpu_usage_usec') for c in cpu_sequence]
        change['periodic_cpu_missing_inside_phase'] = sum(not valid_read(c,'cpu_usage_usec') for c in selected)
        if any(number(a) and number(b) and b<a for a,b in zip(cpus,cpus[1:])):
            change['cpu_core_s']=None
            change.setdefault('field_status',{})['cpu_core_s']='counter_decreased_inside_phase'
        bounds[name] = change
    resources = sample_resources(s['samples'], phase_windows, call_windows)
    tool_rows = []
    for x in tools:
        a,b=x['start_attrs'],x['end_attrs'];change=counter_change(a.get('resource_before'), b.get('resource_after'))
        change['read_minus_event_ns'] = [c.get('t_monotonic_ns')-t if c else None for c,t in [(a.get('resource_before'),x['start_ns']),(b.get('resource_after'),x['end_ns'])]]
        tool_rows.append({'event_id':x['event_id'], 'request_event_id':a.get('request_event_id'), 'open_line':x['open_line'], 'terminal_line':x['terminal_line'],
                          'name':a.get('tool_name'),'role':a.get('role'),'activity':old._activity(a.get('tool_name')),
                          'start_ns':x['start_ns'],'end_ns':x['end_ns'],'wall_s':x['wall_s'],'ok':b.get('ok'),
                          'result_sha256':b.get('result_sha256'),'shared_container_change':change})
    action_points = [e for e in events if e.get('kind')=='agent_action'];action_counts=Counter(e['attrs'].get('action','unknown') for e in action_points)
    finishes = [e for e in action_points if e['attrs'].get('action')=='finish' and stamp(e.get('t_monotonic_ns'))]
    after_finish=sum(x['start_ns']>finishes[0]['t_monotonic_ns'] for x in requests) if len(finishes)==1 else None
    logs = [x for x in old.load_json(p/'manifest.json')['outputs'] if old.RUN_RE.search(x['path'])]
    bootstrap_errors=[];continued=[]
    for item in logs:
        log=old.load_json(p/item['path'])
        for msg in log.get('messages',[]):
            c=msg.get('content')
            if isinstance(c,str) and c.startswith('Bootstrap tool result (inspect_document'):
                payload=json.loads(c.split('\n',1)[1])
                if payload.get('ok') is False:
                    bootstrap_errors.append({'call_log':item['path'],'ok':False,'error_category':payload.get('error'),
                                             'result_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()})
        action, diagnostic=old._decode_action(log)
        continued.append({'call_log':item['path'],'action':action.get('action') if action else 'invalid',
                          'tool_name':action.get('tool_name') if action else None,'parameter_fields':sorted(action.get('arguments',{})) if action and isinstance(action.get('arguments'),dict) else [],
                          'parse_status':diagnostic['status']})
    false_inspect=[x for x in tool_rows if x['role']=='bootstrap' and x['name']=='inspect_document' and x['ok'] is False]
    for x in false_inspect:
        if not any(e['result_sha256']==x['result_sha256'] for e in bootstrap_errors): raise ValueError('bootstrap return/hash cannot be linked to context')
    ids=[x['event_id'] for x in requests];req_rows=[]
    for x in requests:
        a,b=x['start_attrs'],x['end_attrs']
        req_rows.append({'event_id':x['event_id'],'step_index':a.get('step_index'),'start_ns':x['start_ns'],'end_ns':x['end_ns'],
                         'wall_s':x['wall_s'],'ok':b.get('ok'),'request_model':a.get('model'),'response_model':b.get('response_model'),
                         'usage':b.get('usage'),'context_message_count':a.get('context_message_count'),'context_characters':a.get('context_characters')})
    usage_fields=sorted({k for x in req_rows if isinstance(x['usage'],dict) for k in x['usage']})
    usage={k:distribution([x['usage'].get(k) if isinstance(x['usage'],dict) else None for x in req_rows],ids) for k in usage_fields}
    agent_tools=[x for x in tool_rows if x['role']=='agent'];last=agent_tools[-1] if agent_tools else None
    cleanup=[e.get('result') for e in life if e['phase']=='removal_verified'];retained=[e for e in life if e['phase']=='image_tag_after_stop']
    ctrf=old.load_json(p/'verifier/ctrf.json')['results']['summary']
    issues=pairing['issues']
    if len(requests)!=row['model_requests_logged']:issues.append({'reasons':['paired_requests_vs_saved_batch_count_difference']})
    return {'run_id':row['run_id'],'task_key':row['task_key'],'round':row['round'],'identity_sha256':row['identity_sha256'],
            'source':str((p/'summary.json').relative_to(root)),'attempt_wall_s':s['wall_s'],'within_budget':s['within_total_budget'],
            'termination':phases['agent']['status'],'reward':phases['verifier'].get('reward'),'infra':s['outcome']['infra_failures'],
            'verifier_status':phases['verifier']['status'],'verifier_summary':ctrf,'cleanup':cleanup,'image_after_stop':retained,
            'measurement_saved_status':m['call_timing_status'],'environment_unavailable':{k:env.get(k) for k in ['filesystem','cache_initial_state','cpu_field_status']},
            'pairing':pairing,'request_count':len(requests),'agent_tool_count':len(agent_tools),'bootstrap_tool_count':len(tool_rows)-len(agent_tools),
            'action_counts':dict(action_counts),'requests_after_finish':after_finish,'last_agent_tool_terminal':{k:last[k] for k in ['event_id','terminal_line','ok','end_ns']} if last else None,
            'requests':req_rows,'tools':tool_rows,'usage_request_distributions':usage,'saved_call_log_count':len(logs),
            'sequence':[x['name'] for x in agent_tools]+(['finish'] if len(finishes)==1 else []),
            'bootstrap_error_tool_count':len(false_inspect),'bootstrap_error_context_occurrences':bootstrap_errors,'saved_response_actions':continued,
            'time':{'phase':phase,'agent_partition':agent_time,'lifecycle_partition':lifecycle_time,
                    'stop_to_removal_check_marker_s':(byname['removal_verified']['t_monotonic_ns']-byname['harbor_stop_done']['t_monotonic_ns'])/NS if 'removal_verified' in byname and 'harbor_stop_done' in byname else None,
                    'request_duration':distribution([x['wall_s'] for x in requests],ids),
                    'agent_tool_duration':distribution([x['wall_s'] for x in agent_tools],[x['event_id'] for x in agent_tools])},
            'resources':resources,'phase_boundary_changes':bounds}


def summarize(batch, identity_check, runs):
    by_task={}
    for task in TASKS:
        rows=sorted([r for r in runs if r['task_key']==task],key=lambda r:r['round']);ids=[r['run_id'] for r in rows]
        metrics={k:distribution([r[k] for r in rows],ids) for k in ['attempt_wall_s','request_count','agent_tool_count','bootstrap_tool_count']}
        for k in ['window_s','cpu_core_s','memory_current_peak_bytes','kernel_peak_bytes','host_rss_peak_bytes','shared_host_cpu_core_s','collector_read_wall_s']:
            metrics[k]=distribution([r['resources'].get(k) for r in rows],ids)
        for phase in ['agent_setup','agent','verifier','harbor_start','harbor_stop']:
            metrics[phase+'_wall_s']=distribution([r['time']['phase'][phase].get('wall_s') for r in rows],ids)
        for phase in ['agent_setup','agent','verifier']:
            metrics[phase+'_boundary_cpu_core_s']=distribution([r['phase_boundary_changes'][phase]['cpu_core_s'] for r in rows],ids)
        for k in ['request','bootstrap','agent_tool']:
            metrics[k+'_union_s']=distribution([r['time']['agent_partition']['union_s'][k] if r['time']['agent_partition'] else None for r in rows],ids)
        metrics['agent_uncovered_s']=distribution([r['time']['agent_partition']['exclusive_s'].get('uncovered',0) if r['time']['agent_partition'] else None for r in rows],ids)
        for k in ['io_read_bytes','io_write_bytes']:
            metrics[k]=distribution([r['resources']['io_block_service_bytes'].get(k) for r in rows],ids)
        by_task[task]={'n_runs':len(rows),'metrics':metrics,'sequences':[{'run_id':r['run_id'],'sequence':r['sequence']} for r in rows],
                       'outcomes':[{'run_id':r['run_id'],'reward':r['reward'],'termination':r['termination'],'infra':r['infra'],'bootstrap_errors':r['bootstrap_error_tool_count']} for r in rows]}
    return {'collection':COLLECTION,'identity_check':identity_check,'explicit_run_ids':[r['run_id'] for r in runs],
            'totals':{'runs':len(runs),'independent_tasks':len(by_task),'logical_requests':sum(r['request_count'] for r in runs),
                      'agent_tools':sum(r['agent_tool_count'] for r in runs),'bootstrap_tools':sum(r['bootstrap_tool_count'] for r in runs),
                      'finish':sum(r['termination']=='finish' for r in runs),'reward_1':sum(r['reward']==1 for r in runs),
                      'bootstrap_ok_false':sum(r['bootstrap_error_tool_count'] for r in runs),'samples':sum(r['resources']['sample_count'] for r in runs),
                      'pairing_issue_count':sum(len(r['pairing']['issues']) for r in runs)},
            'by_task':by_task,'batch_wall_s':batch['batch_wall_s'],'quantile_method':'linear interpolation at (n-1)*p; metrics use finite non-bool values',
            'definitions':{'time':'same-host system_monotonic ns; request wall is client logical-call boundary, including possible internal retries',
                           'partition':'exclusive occupancy from clipped interval unions; overlap explicitly retained; uncovered has no causal interpretation',
                           'cpu':'shared container core-s; phase boundary counter reads preferred; sample bins only wholly contained intervals, mixed never prorated',
                           'memory':'memory.current sampled maximum; kernel peak cumulative high-water mark, never a phase-independent peak; shared host RSS separate',
                           'io':'observed cgroup block-service bytes, not complete filesystem/application I/O',
                           'archive':'saved marker span only; cannot reconstruct full archive duration from these markers'},
            'ppt_diagnosis':{'saved_exception':'AttributeError','path':'Agent bootstrap -> project runtime dispatch -> official tool_inspect_document .pptx branch -> runtime catches exception class -> Agent saves false payload and continues',
                             'static_candidate_site':'prs.slides[:max_items] in document_tools_runtime.py; local container python-pptx implementation/traceback not archived; exact inner raising attribute unconfirmed',
                             'direct_effect':'initial PPT document inspection yielded no successful inspection payload; failure was supplied to subsequent requests; later ppt_list_slides/text edit/finish observed',
                             'unknown_effect':'counterfactual path, extra requests/cost/quality impact and deeper dependency stack are unknown; reward=1 does not establish no impact'},
            'limitations':['No transport hook: actual HTTP tries unknown; usage and cost=0 are not bills.',
                           'Resource read timestamps precede event timestamps; offsets saved; tool windows are shared-scope changes, not exclusive cost.',
                           '0.5s periodic sampling undercovers short calls; boundary/mixed bins retained, no interpolation.',
                           'Three repetitions per fixed task, not nine independent tasks or representative Office population.',
                           'ARM64 adaptation not byte-equivalent official amd64 environment; alias not immutable model pin.',
                           'No CPU hotspots, remote inference cost, thinking time, causal effects or rankings; old batch/Excel smoke excluded.']}


def markdown(summary, runs):
    t=summary['totals'];rows=['# DOCOPS-OFFICE-REPEAT-02 限定行为—资源分析','',
        f"显式{t['runs']}次、{t['independent_tasks']}个固定任务；{t['logical_requests']}逻辑请求、{t['agent_tools']}自主工具、{t['bootstrap_tools']} bootstrap。finish={t['finish']}、reward=1={t['reward_1']}；配对问题{t['pairing_issue_count']}。旧批和单次Excel不纳入。",'',
        '## 原始点：阶段与调用窗口','',
        '| run | 请求/工具 | attempt s | Agent s | 请求并集 s | bootstrap并集 s | 自主工具并集 s | uncovered s | verifier s | stop s |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    def fmt(v):return 'null' if v is None else f'{v:.6f}'
    for r in runs:
        p=r['time']['agent_partition'];f=r['time']['phase'];u=p['union_s'] if p else {};ex=p['exclusive_s'] if p else {}
        rows.append('| '+ ' | '.join([r['run_id'],f"{r['request_count']}/{r['agent_tool_count']}",fmt(r['attempt_wall_s']),fmt(f['agent'].get('wall_s')),*(fmt(u.get(k)) for k in ['request','bootstrap','agent_tool']),fmt(ex.get('uncovered',0) if p else None),fmt(f['verifier'].get('wall_s')),fmt(f['harbor_stop'].get('wall_s'))])+' |')
    rows+=['','请求、工具、bootstrap列为并集，不能在重叠时直接相加；互斥mask分解、overlap及整数ns守恒残差见per_run。uncovered不称思考/等待/框架独占开销。归档只保存marker span，不当成完整归档耗时。','',
           '## 共享容器资源原始点','', '| run | 观测窗 s | 总CPU core-s | setup / Agent / verifier 边界CPU core-s | current / 内核peak / 宿主RSS MiB |', '| --- | --- | --- | --- | --- |']
    for r in runs:
        a=r['resources'];b=r['phase_boundary_changes'];rows.append('| '+ ' | '.join([r['run_id'],fmt(a['window_s']),fmt(a['cpu_core_s']),' / '.join(fmt(b[k]['cpu_core_s']) for k in ['agent_setup','agent','verifier']), ' / '.join(fmt(a[k]/1048576 if a[k] is not None else None) for k in ['memory_current_peak_bytes','kernel_peak_bytes','host_rss_peak_bytes'])])+' |')
    rows+=['','完整memory.current点、I/O读写计数器、采样质量、CPU sample partition与工具前后共享变化均在per_run。阶段边界CPU和纯采样CPU分箱使用不同读窗口，不互相替代；跨边界mixed不分摊。内核peak为累计高水位，不是阶段独立峰值，三个内存口径不相加。','', '## 任务内重复统计','', '| task | 指标 | 原始三个点 | 有效n | median | IQR |', '| --- | --- | --- | --- | --- | --- |']
    for task,group in summary['by_task'].items():
        for key in ['request_count','agent_tool_count','attempt_wall_s','agent_wall_s','request_union_s','agent_tool_union_s','cpu_core_s','agent_boundary_cpu_core_s','verifier_boundary_cpu_core_s','memory_current_peak_bytes']:
            d=group['metrics'][key];rows.append(f"| {old.SHORT[task]} | {key} | "+', '.join(fmt(x['value']) for x in d['points'])+f" | {d['n']} | {fmt(d['median'])} | {fmt(d['iqr'])} |")
    rows+=['','分位数为(n−1)×p线性插值，missing不填零，n由每个指标独立确定；三个repeat不是三个task。','', '## 有限观察与证据','']
    for task,group in summary['by_task'].items():
        m=group['metrics'];points=m['attempt_wall_s']['points'];lo=min(points,key=lambda x:x['value']);hi=max(points,key=lambda x:x['value']);low=next(r for r in runs if r['run_id']==lo['id']);high=next(r for r in runs if r['run_id']==hi['id'])
        rows.append(f"- {old.SHORT[task]} attempt wall原始范围{lo['value']:.3f}–{hi['value']:.3f}s；最大与最小run的Agent阶段差{high['time']['phase']['agent']['wall_s']-low['time']['phase']['agent']['wall_s']:.6f}s，请求并集差{high['time']['agent_partition']['union_s']['request']-low['time']['agent_partition']['union_s']['request']:.6f}s，自主工具并集差{high['time']['agent_partition']['union_s']['agent_tool']-low['time']['agent_partition']['union_s']['agent_tool']:.6f}s。这里只定位观测差异，不解释模型慢、缓存或因果。")
        rows.append(f"  保存的自主工具序列："+'；'.join(f"r{r['round']}: "+' → '.join(r['sequence']) for r in runs if r['task_key']==task))
        selected=[r for r in runs if r['task_key']==task]
        ratios=distribution([r['time']['agent_partition']['union_s']['request']/r['time']['phase']['agent']['wall_s'] for r in selected])
        cpu=group['metrics']['agent_boundary_cpu_core_s'];vcpu=group['metrics']['verifier_boundary_cpu_core_s']
        rows.append(f"  请求并集/Agent观测窗口逐run比例median={ratios['median']*100:.3f}%（n={ratios['n']}），不是推理时间占比。Agent共享边界CPU median={cpu['median']:.6f}、verifier={vcpu['median']:.6f}core-s；这些窗口共现不说明单工具独占成本。")
    residuals=[r['time']['agent_partition']['residual_ns'] for r in runs if r['time']['agent_partition']]
    rows.append(f"- Agent区间互斥时间分解残差范围{min(residuals)}–{max(residuals)}ns；保存请求与工具重叠并集范围"+f"{min(r['time']['agent_partition']['overlap_s'] for r in runs):.6f}–{max(r['time']['agent_partition']['overlap_s'] for r in runs):.6f}s；不是通过假定无重叠得到。")
    mixed=[r['resources']['cpu_partition']['call_core_s'].get('mixed_boundary',0)/r['resources']['cpu_core_s'] for r in runs if r['resources'].get('cpu_core_s') and 'cpu_partition' in r['resources']]
    if mixed:
        rows.append(f"- 调用边界mixed采样区间包含各run观测CPU的{min(mixed)*100:.3f}%–{max(mixed)*100:.3f}%；不将这部分均匀摊给请求或工具。调用分箱使用整个资源采样窗口，uncovered还可能包含setup/verifier，不能与Agent时间分解的uncovered混用。")
    failed=[x for r in runs for x in r['tools'] if x['role']=='bootstrap' and x['ok'] is False]
    if failed:
        rows.append(f"- bootstrap失败窗口原始wall点："+', '.join(f"{x['wall_s']:.6f}s" for x in failed)+"；窗口内共享容器CPU变化："+', '.join(fmt(x['shared_container_change']['cpu_core_s'])+'core-s' for x in failed)+"。失败已被计时和记录，不代表没有资源变化。")
    rows+=['', '## PPT bootstrap异常','',f"独立工具终态确认{t['bootstrap_ok_false']}次ok=false。第一及后续保存请求包含AttributeError返回；按返回SHA与工具终态关联，而非位置强配。后续自主ppt_list_slides / ppt_replace_text及finish均有保存事件，verifier均完成。setup完成≠bootstrap全部成功。",'',
           summary['ppt_diagnosis']['path'], summary['ppt_diagnosis']['static_candidate_site'], summary['ppt_diagnosis']['direct_effect'], summary['ppt_diagnosis']['unknown_effect'],'',
           '没有保存内部traceback或容器内python-pptx源文件，不能把可疑切片表达式升级为已证实的具体抛错行。本轮不执行工具或依赖重现，也不修复运行时。','', '## 边界与下一步','',
           *['- '+x for x in summary['limitations']], '',
           '本批限定分析完成；下一步唯一建议：对PPT inspection切片路径及固定依赖接口进行独立离线诊断/修复评审，保留这批历史错误，不以reward=1抹去。无需为了分析自动扩样或恢复CPU-02/Replay。','',
           '机器可读结果：[summary.json](summary.json)、[per_run.jsonl](per_run.jsonl)、[manifest.json](manifest.json)。']
    return '\n'.join(rows)+'\n'


def analyze(root, output=None):
    root=Path(root).resolve();output=Path(output or root/OUT)
    if output.exists():raise FileExistsError('sealed output directory already exists')
    batch,identity,used,checks=verify_inputs(root)
    runs=[analyze_run(root,row) for row in batch['results']]
    summary=summarize(batch,checks,runs)
    span_ids=Counter(x['event_id'] for r in runs for x in r['requests']+r['tools'])
    summary['cross_run_duplicate_span_ids']={k:v for k,v in span_ids.items() if v>1}
    for source in ['scripts/docops_office_repeat_02_characterization.py','scripts/docops_office_repeat_characterization.py',
                   'scripts/docops_word_resource_analysis.py','scripts/p1_12_coding_repeat_characterization_v2.py']:
        path=Path(__file__) if source.endswith('repeat_02_characterization.py') else Path(__file__).parent/Path(source).name
        # Code identities are rooted in the repository, not synthetic input roots.
        summary.setdefault('analysis_code',[]).append({'path':source,'bytes':path.stat().st_size,'sha256':old.sha256(path)})
    # These code files are read for the exception/timestamp mechanism, never imported.
    sources=['references/repos/DocOps/harnesses/document_tools_runtime.py','references/repos/DocOps/harnesses/document_tools_agent.py',
             'src/agent_workload_characterization/runners/docops_word_runtime.py','src/agent_workload_characterization/runners/docops_word_agent.py',
             'scripts/docops_word_resource_01_entry.py']
    for rel in sources:
        path=root/rel
        if path.is_file():
            text=path.read_text();used[rel]=file_record(root,path)
            if rel=='references/repos/DocOps/harnesses/document_tools_runtime.py':
                summary['ppt_diagnosis']['static_source_positions']=[{'path':rel,'line':i,'expression':'prs.slides[:max_items]'} for i,line in enumerate(text.splitlines(),1) if 'prs.slides[:max_items]' in line]
    summary['diagnostic_source_files_available']=[x for x in sources if x in used]
    output.mkdir(parents=True)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (output/'per_run.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in runs))
    (output/'summary.md').write_text(markdown(summary,runs))
    outputs=[file_record(output,output/name) for name in ['summary.json','per_run.jsonl','summary.md']]
    manifest={'schema':'docops-repeat02-characterization-manifest-v1','input_root':str(root),'output_root':str(output),
              'inputs':sorted(used.values(),key=lambda r:r['path']),'analysis_code_root':str(Path(__file__).resolve().parents[1]),
              'analysis_code':summary['analysis_code'],'outputs':outputs,'manifest_self_hash':False}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    for r in outputs:
        if file_record(output,output/r['path'])!=r:raise ValueError('final output hash mismatch')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path)
    args=p.parse_args(argv);s=analyze(args.root,args.output);print(json.dumps(s['totals'],ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
