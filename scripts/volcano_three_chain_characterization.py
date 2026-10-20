#!/usr/bin/env python3
"""Offline review and four-panel SVGs for exactly three saved Volcano runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import statistics
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from agent_workload_characterization.collectors.execution_measurement import counter_rate_intervals, network_rate_intervals
from agent_workload_characterization.analyzers.public_operations import classify_call
from toolsandbox_resource_pilot_02_review import _pair_spans, _merge, _duration

RUNS = (
    ('Office', 'DOCOPS-MEASUREMENT-VOLCANO-02', '20261016T143948Z-excel001', 'docops-measurement-volcano-02'),
    ('Coding', 'CODING-MEASUREMENT-VOLCANO-01', '20261016T144518Z-django16485-91776c', 'coding-measurement-volcano-01'),
    ('Assistant', 'TOOLSANDBOX-MEASUREMENT-VOLCANO-01', '20261016T145056Z-tsbvolcano01', 'toolsandbox-measurement-volcano-01'),
)
CENTRAL = Path('env/docops-measurement-volcano-02')
OUTPUT = Path('reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def file_record(path, base):
    data = path.read_bytes()
    return {'path': str(path.relative_to(base)) if path.is_relative_to(base) else str(path),
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class Inputs:
    def __init__(self, root):
        self.root = root.resolve()
        self.records = {}
        self.drift = []

    def data(self, path):
        path = path if path.is_absolute() else self.root / path
        data = path.read_bytes()
        self.records[str(path)] = {'path': str(path.relative_to(self.root)) if path.is_relative_to(self.root) else str(path),
                                  'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        return data

    def json(self, path):
        return json.loads(self.data(path))

    def lines(self, path):
        return [json.loads(line) for line in self.data(path).decode().splitlines() if line.strip()]

    def check(self, path, expected, *, historical_code=False):
        data = self.data(path)
        ok = hashlib.sha256(data).hexdigest() == expected['sha256']
        ok = ok and ('bytes' not in expected or len(data) == expected['bytes'])
        if not ok and historical_code:
            self.drift.append({'path': str(path), 'historical': expected,
                               'current': self.records[str((self.root / path).resolve())]})
        else:
            require(ok, 'input bytes/SHA mismatch: ' + str(path))


def verify_inputs(inp):
    """Explicit manifest conventions; never invokes a production plan builder."""
    root = inp.root
    close = inp.json(CENTRAL / 'validation-closeout.json')
    central_md = inp.data(CENTRAL / 'validation-summary.md').decode()
    code_paths = set()
    saved = {}
    for chain, col, run, env in RUNS:
        plan = inp.json(Path('env') / env / 'plan-identity.json')
        frozen = inp.json(Path('env') / env / 'frozen-identity.json')
        identity = plan['identity']
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=chain == 'Office',
                                            separators=(',', ':')).encode()).hexdigest()
        require(identity == frozen['identity'] and digest == plan['identity_sha256'] == frozen['identity_sha256'],
                'full plan/frozen identity mismatch: ' + chain)
        require(identity['collection'] == col, 'identity collection mismatch')
        saved[chain] = plan
        code_paths.update(x['path'] for x in identity.get('code_and_runtime_files', identity.get('code_and_inputs', [])))
    central = inp.json(CENTRAL / 'validation-manifest.json')
    for row in central['inputs'] + central['outputs']:
        inp.check(Path(row['path']), row, historical_code=row['path'] in code_paths)
    require(len(close['runs']) == len(RUNS), 'central run census mismatch')
    archives = []
    sets = {}
    for chain, col, run, env in RUNS:
        raw = Path('data/raw/generated') / col / run
        reportdir = Path('reports/resource') / col
        report = inp.json(reportdir / 'run-report.json')
        approval = inp.json(reportdir / 'APPROVAL.json')
        digest = saved[chain]['identity_sha256']
        require(report['run_id'] == run and report['identity_sha256'] == approval['identity_sha256'] == digest,
                'approval/report identity mismatch: ' + chain)
        rows = [x for x in close['runs'] if x['chain'] == chain]
        require(len(rows) == 1 and rows[0]['run_id'] == run and rows[0]['identity_sha256'] == digest and run in central_md,
                'central table/closeout association mismatch')
        outer = inp.json(reportdir / 'manifest.json')
        require(outer['identity_sha256'] == digest, 'outer identity mismatch')
        for row in outer['inputs'] + outer['outputs']:
            inp.check(Path(row['path']), row)
        manifest = inp.json(raw / 'manifest.json')
        if chain == 'Coding':
            entries = [{'path': name, 'sha256': sha} for name, sha in manifest['files'].items()]
            meta = inp.json(raw / 'metadata.json')
            marker = inp.json(reportdir / 'ATTEMPT_STARTED.json')
            require(meta['identity_sha256'] == marker['identity_sha256'] == digest and marker['run_id'] == run,
                    'Coding raw metadata/marker identity mismatch')
        else:
            require(manifest['identity_sha256'] == digest and manifest['run_id'] == run, 'raw identity mismatch')
            entries = manifest['outputs'] if chain == 'Office' else manifest['files']
            start = inp.json(raw / 'ATTEMPT_STARTED.json')
            end = inp.json(raw / 'ATTEMPT_COMPLETED.json')
            require(start['identity_sha256'] == digest and start['run_id'] == end['run_id'] == run,
                    'attempt marker mismatch')
            require(end.get('identity_sha256', digest) == digest, 'terminal marker identity mismatch')
        names = [x['path'] for x in entries]
        actual = {str(p.relative_to(root / raw)) for p in (root / raw).rglob('*')
                  if p.is_file() and p.name != 'manifest.json'}
        require(len(names) == len(set(names)) and set(names) == actual, 'raw file set mismatch: ' + chain)
        for row in entries:
            inp.check(raw / row['path'], row)
        for row in manifest.get('inputs', []):
            inp.check(Path(row['path']), row, historical_code=row['path'] in code_paths)
        archives.append({'chain': chain, 'raw_files': len(entries), 'raw_set_and_hashes': 'pass',
                         'outer_records': len(outer['inputs']) + len(outer['outputs']),
                         'identity': 'full saved plan/frozen structures, digest, approval, report and raw association',
                         'coding_raw_manifest_bytes': 'not registered; measured now, original SHA verified' if chain == 'Coding' else 'registered'})
        for directory in (raw, reportdir):
            sets[str(directory)] = sorted(str(p.relative_to(root / directory)) for p in (root / directory).rglob('*') if p.is_file())
    return saved, close, archives, sets


def pairs(events):
    bad = [x.get('kind') for x in events if not x.get('event_id')]
    spans, issues = _pair_spans([x for x in events if x.get('event_id')])
    issues['missing_id'] = bad
    return spans, issues


def metric_specs(process=False):
    ident = ['pid', 'starttime_ticks'] if process else ['container_id']
    cpu = {'path': 'cpu_ticks' if process else 'cpu_usage_usec', 'unit': 'cpu_seconds',
           'rate_unit': 'average_core', 'identity_paths': ident}
    if process:
        cpu.update(divisor_path='clk_tck', status_paths=[('read_status', 'stat')])
    else:
        cpu.update(divisor=1e6, status_paths=[('read_status', 'cpu.stat'), ('read_status', 'cpuacct.usage')])
    out = {'cpu': cpu}
    for name in (('read_bytes', 'write_bytes', 'rchar', 'wchar') if process else ('io_read_bytes', 'io_write_bytes')):
        out[name] = {'path': ('process_io', name) if process else name, 'unit': 'bytes',
                     'rate_unit': 'bytes_per_second', 'identity_paths': ident,
                     'status_paths': [('read_status', 'io')] if process else [('read_status', 'io.stat'), ('read_status', 'io')]}
    return out


def valid_memory(row, process=False, peak=False):
    key = 'rss_bytes' if process else ('mem_peak_bytes' if peak else 'mem_current_bytes')
    status = row.get('read_status', {})
    names = ['stat'] if process else (['memory.peak', 'memory.max_usage_in_bytes'] if peak else ['memory.current', 'memory.usage_in_bytes'])
    ok = any(str(status.get(k, '')).startswith('ok') for k in names)
    return type(row.get(key)) is int and row[key] >= 0 and ok


def scope_projection(rows, *, scope, kind, source, locations, process=False, bounds=None, target=.5):
    """Only consecutive endpoints; retain gaps and the original sample ordering."""
    projected = counter_rate_intervals(rows, metric_specs(process))
    series = []
    for i, item in enumerate(projected):
        outside = bounds is not None and (item['t_start_ns'] is None or item['t_end_ns'] is None or
                                          item['t_start_ns'] < bounds[0] or item['t_end_ns'] > bounds[1])
        for metric, value in item['metrics'].items():
            if outside:
                value.update(status='gap', reason='outside_scope_observation_boundary', delta=None, rate_per_s=None)
            series.append({'scope': scope, 'scope_kind': kind, 'metric': metric,
                't0': item['t_start_ns'], 't1': item['t_end_ns'], 'value': value['rate_per_s'],
                'unit': 'core' if metric == 'cpu' else 'B/s', 'status': value['status'], 'reason': value['reason'],
                'delta': value['delta'], 'source': source, 'locator': locations[i] + ' -> ' + locations[i+1]})
    memory = []
    for i, row in enumerate(rows):
        t = row.get('t_monotonic_ns')
        good = type(t) is int and (i == 0 or type(rows[i-1].get('t_monotonic_ns')) is int and t > rows[i-1]['t_monotonic_ns'])
        good = good and (not bounds or bounds[0] <= t <= bounds[1])
        good = good and valid_memory(row, process)
        identity = [row.get('pid'), row.get('starttime_ticks')] if process else [row.get('container_id')]
        good = good and all(x is not None and not isinstance(x, bool) for x in identity)
        if i:
            previous = rows[i-1]
            previous_identity = [previous.get('pid'), previous.get('starttime_ticks')] if process else [previous.get('container_id')]
            good = good and identity == previous_identity
        value = row.get('rss_bytes' if process else 'mem_current_bytes')
        memory.append(value if good else None)
        series.append({'scope': scope, 'scope_kind': kind, 'metric': 'RSS' if process else 'memory.current',
            't0': t, 't1': t, 'value': value / 1048576 if good else None, 'unit': 'MiB',
            'status': 'valid' if good else 'gap', 'reason': None if good else 'memory_read_identity_time_or_boundary_invalid',
            'delta': None, 'source': source, 'locator': locations[i]})
    intervals = [(b['t_monotonic_ns']-a['t_monotonic_ns'])/1e9 for a,b in zip(rows,rows[1:])
                 if type(a.get('t_monotonic_ns')) is int and type(b.get('t_monotonic_ns')) is int]
    quality = {}
    for metric in metric_specs(process):
        selected = [x for x in series if x['metric'] == metric]
        valid = [x for x in selected if x['status'] == 'valid']
        quality[metric] = {'candidate': len(selected), 'valid': len(valid), 'gap': len(selected)-len(valid),
            'gap_reasons': dict(Counter(x['reason'] for x in selected if x['status'] != 'valid')),
            'observed_valid_delta_sum': math.fsum(x['delta'] for x in valid) if valid else None,
            'full_window_delta': math.fsum(x['delta'] for x in valid) if valid and len(valid)==len(selected) else None,
            'unit': 'CPU-s' if metric == 'cpu' else 'bytes'}
    peak = [r['mem_peak_bytes'] for r in rows if not process and valid_memory(r, peak=True)
            and (not bounds or bounds[0] <= r['t_monotonic_ns'] <= bounds[1])]
    times = [r['t_monotonic_ns'] for r in rows if type(r.get('t_monotonic_ns')) is int]
    summary = {'scope': scope, 'scope_kind': kind, 'source': source, 'saved_points_including_boundaries': len(rows),
        'sample_window_ns': [times[0], times[-1]] if times else None,
        'sample_window_s': (times[-1]-times[0])/1e9 if len(times)>1 else None,
        'registered_boundaries_ns': bounds, 'target_interval_s': target,
        'actual_interval_min_s': min(intervals) if intervals else None,
        'actual_interval_median_s': statistics.median(intervals) if intervals else None,
        'actual_interval_max_s': max(intervals) if intervals else None,
        'nonincreasing_times': sum(x<=0 for x in intervals), 'metric_quality': quality,
        'memory_valid_points': sum(v is not None for v in memory),
        'memory_gap_points': sum(v is None for v in memory),
        'memory_sampled_peak_bytes': max((v for v in memory if v is not None), default=None),
        'memory_measure': 'RSS' if process else 'memory.current',
        'kernel_memory_peak_bytes': max(peak, default=None),
        'kernel_peak_note': 'unknown at process scope; container cumulative high-water, not per-stage independent peak' if process else 'cumulative container high-water; not summed across scopes',
        'read_status_counts': {k:dict(Counter(str(r.get('read_status',{}).get(k)) for r in rows))
                               for k in sorted({k for r in rows for k in r.get('read_status',{})})}}
    summary['cpu_counter_unit'] = 'ticks' if process else 'usec'
    summary['clk_tck_values'] = sorted({r['clk_tck'] for r in rows if type(r.get('clk_tck')) is int}) if process else None
    return summary, series


def project_network(samples, source):
    intervals = network_rate_intervals(samples)
    by_interface = defaultdict(list)
    for x in intervals:
        by_interface[x['interface']].append(x)
    stats = {}
    for name, rows in sorted(by_interface.items()):
        metrics = {}
        for key in ('rx_bytes','tx_bytes'):
            valid = [x['metrics'][key] for x in rows if x['metrics'][key]['status']=='valid']
            gaps = Counter(x['metrics'][key]['reason'] for x in rows if x['metrics'][key]['status']!='valid')
            metrics[key] = {'candidate':len(rows),'valid':len(valid),'gap':len(rows)-len(valid),'gap_reasons':dict(gaps),
                'valid_delta_bytes':sum(x['delta_bytes'] for x in valid) if valid else None,
                'full_window_delta_bytes':sum(x['delta_bytes'] for x in valid) if len(valid)==len(rows)==len(samples)-1 and valid else None}
        stats[name] = metrics
    candidates = [name for name,m in stats.items() if name!='lo' and
                  all(m[k]['full_window_delta_bytes'] is not None for k in ('rx_bytes','tx_bytes'))]
    selected = sorted(candidates,key=lambda n:(-sum(stats[n][k]['full_window_delta_bytes'] for k in ('rx_bytes','tx_bytes')),n))[:3]
    series=[]
    for name in selected:
        for i,x in enumerate(by_interface[name]):
            for key,y in x['metrics'].items():
                series.append({'scope':name,'scope_kind':'shared_netns_interface','metric':key,
                    't0':x['t_start_ns'],'t1':x['t_end_ns'],'value':y['bytes_per_s'],'unit':'B/s',
                    'status':y['status'],'reason':y['reason'],'delta':y['delta_bytes'],'source':source,
                    'locator':f'network.samples[{i}:{i+2}].interfaces.{name}'})
    d=[(b['t_monotonic_ns']-a['t_monotonic_ns'])/1e9 for a,b in zip(samples,samples[1:])]
    return {'scope':'shared network namespace per interface; not PID/task/API-exclusive',
        'source':source,'locator':'network.samples[*].interfaces.<interface>.{rx_bytes,tx_bytes}',
        'saved_points':len(samples),'sample_window_ns':[samples[0]['t_monotonic_ns'],samples[-1]['t_monotonic_ns']] if samples else None,
        'actual_interval_median_s':statistics.median(d) if d else None,'actual_interval_max_s':max(d,default=None),
        'nonincreasing_times':sum(x<=0 for x in d),'namespace_ids':sorted({str(x.get('namespace_id')) for x in samples}),
        'selected_interfaces':selected,'interface_count':len(stats),'interfaces':stats,
        'selection_rule':'max 3 non-lo interfaces, both counters valid across the complete saved window; descending (rx_delta+tx_delta), then interface name. Display ranking only, not API egress identification; never sum interfaces.'},series


def phase(name, start, end, *, cpu_start=None, cpu_end=None, divisor=1, note=''):
    return {'name':name,'start_ns':start,'end_ns':end,
            'wall_s':(end-start)/1e9 if type(start) is int and type(end) is int and end>=start else None,
            'shared_cpu_s':(cpu_end-cpu_start)/divisor if type(cpu_start) is int and type(cpu_end) is int and cpu_end>=cpu_start and divisor else None,
            'note':note}


def behavior(events, chain, inp, raw):
    spans,quality=pairs(events)
    requests=[x for x in spans if x['kind']=='llm_request']
    tools=[x for x in spans if x['kind']=='tool_call']
    out={'pairing_quality':quality,'logical_requests':len(requests),'requests_by_role':dict(Counter(x['attrs'].get('role','agent') for x in requests)),
         'response_models':dict(Counter(str(x['terminal_attrs'].get('response_model')) for x in requests)),
         'request_union_s':_duration([(x['start_ns'],x['end_ns']) for x in requests]),'actual_http_attempts':None,'actual_bill':None,
         'unknown_reason':'No HTTP transport hook or billing evidence; project-layer attempts are not HTTP counts'}
    out['requests']=[{'event_id':x['event_id'],'start_ns':x['start_ns'],'end_ns':x['end_ns'],
                     'role':x['attrs'].get('role','agent'),'status':x['status']} for x in requests]
    if chain=='Coding':
        native=inp.lines(raw/'mini_tool_events.jsonl')
        converted=[{'event_id':x.get('event_id'),'kind':'tool_call','status':x['event'],
            't_monotonic_ns':x.get('t_start_ns') if x['event']=='open' else x.get('t_end_ns'),
            'attrs':{k:v for k,v in x.items() if k not in ('command_view','event')}} for x in native]
        tools,tq=pairs(converted);out['native_tool_pairing_quality']=tq
        trajectory=inp.json(raw/'mini_trajectory.json')
        assistant=[x for x in trajectory['messages'] if x.get('role')=='assistant']
        out['response_models']=dict(Counter(str(x.get('extra',{}).get('response',{}).get('model')) for x in assistant))
        out['response_model_source']='mini_trajectory.json messages[role=assistant].extra.response.model'
        byid=defaultdict(list)
        for m in assistant:
            for call in m.get('tool_calls') or []:
                byid[call.get('id')].append(call)
        steps=[]
        for t in tools:
            calls=byid.get(t['attrs'].get('tool_call_id'),[])
            call=calls[0] if len(calls)==1 else None
            f=call.get('function',{}) if call else {}
            try:args=json.loads(f.get('arguments','{}'))
            except (ValueError,TypeError):args={}
            label=classify_call(f.get('name'),args)
            steps.append({'event_id':t['event_id'],'tool_call_id':t['attrs'].get('tool_call_id'),
                'name':f.get('name'),'role':'agent','start_ns':t['start_ns'],'end_ns':t['end_ns'],
                'status':t['status'],'exception_type':t['terminal_attrs'].get('exception_type'),
                'returncode':t['terminal_attrs'].get('returncode'),
                'native_id_trajectory_matches':len(calls),'static_operation':label['operation'],
                'static_programs':label['executables'],'static_limit':label['reason']})
        out['termination']=trajectory['info']['exit_status']
        out['operation_counts']=dict(Counter(x['static_operation'] for x in steps))
        out['tool_pair_source']='mini_tool_events.jsonl event_id; tool_call_id links unique saved trajectory call only'
        out['ordinary_tool_errors']=sum(t['status']=='error' and t['exception_type']!='Submitted' for t in steps)
        out['control_flow_terminals']=sum(t['exception_type']=='Submitted' for t in steps)
        out['shell_returncode_counts']=dict(Counter(str(t['returncode']) for t in steps if t['status']=='closed'))
        out['shell_nonzero_returns']=sum(type(t['returncode']) is int and t['returncode']!=0 for t in steps if t['status']=='closed')
    else:
        steps=[{'event_id':t['event_id'],'name':t['attrs'].get('tool_name'),'role':t['attrs'].get('role'),
            'start_ns':t['start_ns'],'end_ns':t['end_ns'],'status':t['status'],
            'ok':t['terminal_attrs'].get('ok'),'error':t['terminal_attrs'].get('error'),
            'return_saved':'result_sha256' in t['terminal_attrs']} for t in tools]
        out['ordinary_tool_errors']=sum(x['status']=='error' or x.get('ok') is False for x in steps)
        out['control_flow_terminals']=0
        out['saved_ok_by_role']={role:dict(Counter(str(x.get('ok')) for x in steps if x['role']==role)) for role in {x['role'] for x in steps}}
    out['tools']=steps
    out['tools_by_role']=dict(Counter(x['role'] for x in steps))
    out['tool_terminal_counts']=dict(Counter(x['status'] for x in steps))
    out['tool_window_union_s']=_duration([(x['start_ns'],x['end_ns']) for x in steps])
    if chain=='Office':
        finish=[x['t_monotonic_ns'] for x in events if x['kind']=='agent_action' and x['attrs'].get('action')=='finish']
        terminal=max(finish,default=None)
    elif chain=='Coding':
        terminal=max((x['end_ns'] for x in steps if x['exception_type']=='Submitted'),default=None)
    else:
        terminal=max((x['end_ns'] for x in steps if x['name']=='end_conversation'),default=None)
    out['requests_after_termination']=sum(x['start_ns']>terminal for x in requests) if terminal else None
    out['last_tool_terminal']=steps[-1] if steps else None
    return out


def analyze_run(inp, spec, saved, archived_returncode, *, report_path):
    chain,col,run,env=spec;raw=Path('data/raw/generated')/col/run
    report=inp.json(report_path)
    supplemental=inp.json(raw/'supplemental_measurements.json')
    events=inp.lines(raw/('agent/events.jsonl' if chain=='Office' else 'events.jsonl'))
    root_span=[x for x in pairs(events)[0] if x['kind']=='run']
    result={'chain':chain,'collection':col,'run_id':run,'n':1,'identity_sha256':saved['identity_sha256'],
        'raw':str(raw),'behavior':behavior(events,chain,inp,raw),'scopes':[],'phases':[],
        'api_bytes':'unknown/unsupported','supplement_aggregate_status':supplemental['status']}
    series=[]
    def scope(rows,scope,kind,source,locs,**kw):
        stats,data=scope_projection(rows,scope=scope,kind=kind,source=str(source),locations=locs,**kw)
        result['scopes'].append(stats);series.extend(data)
    if chain=='Office':
        summary=inp.json(raw/'summary.json');samples=summary['samples'];life={x['phase']:x for x in summary['events']}
        origin=inp.json(raw/'ATTEMPT_STARTED.json')['started_at_monotonic_ns']
        cid=summary['container']['id']
        for key,kind,process in [('container','shared_task_container',False),('host_agent','shared_host_agent_and_collector',True)]:
            rows=[dict(x[key],t_monotonic_ns=x['t_monotonic_ns']) for x in samples]
            if not process:
                for row in rows:row['container_id']=cid
            scope(rows,key,kind,raw/'summary.json',[f'samples[{i}].{key}' for i in range(len(rows))],process=process)
        for name,a,b in [('setup','agent_setup_begin','agent_setup_done'),('Agent','agent_begin','agent_end'),('verifier','verifier_begin','verifier_end'),('cleanup','harbor_stop_begin','harbor_stop_done'),('archive markers only','archive_begin','archive_done')]:
            l,h=life.get(a,{}),life.get(b,{})
            result['phases'].append(phase(name,l.get('t_monotonic_ns'),h.get('t_monotonic_ns'),
                cpu_start=l.get('shared_resource_boundary',{}).get('cpu_usage_usec'),
                cpu_end=h.get('shared_resource_boundary',{}).get('cpu_usage_usec'),divisor=1e6,
                note='counter read timestamps differ slightly from lifecycle event; shared container; archive markers are not full archive cost'))
        result.update(attempt_wall_s=summary['wall_s'],attempt_wall_source='summary.wall_s',
            task_result=summary['outcome']['phases']['verifier'],termination=summary['outcome']['phases']['agent']['status'],
            infra=summary['outcome']['infra_failures'],cleanup=[life[k] for k in ('harbor_stop_done','removal_verified','image_tag_after_stop')],
            entry_returncode=report['exit_code'],collector_read_wall_ns=summary['measurement']['collector']['read_wall_ns'],
            origin_source='ATTEMPT_STARTED.started_at_monotonic_ns',environment=str(raw/'environment.json'))
    elif chain=='Coding':
        origin=root_span[0]['start_ns'];samples=inp.json(raw/'samples.json');meta=inp.json(raw/'metadata.json')
        for name,v in samples['evidence'].items():
            kind=v['scope_kind'];tag='agent' if kind=='agent_container' else 'verifier'
            ids=[x['attrs']['container_id'] for x in events if x['kind']=='container' and x['attrs'].get('scope')==tag and x['attrs'].get('action')=='start']
            require(len(ids)==1,'container identity association ambiguous')
            rows=[v['boundary_start'],*v['samples'],v['boundary_end']]
            locs=[f'evidence.{name}.boundary_start',*[f'evidence.{name}.samples[{i}]' for i in range(len(v['samples']))],f'evidence.{name}.boundary_end']
            rows=[dict(x,container_id=ids[0]) for x in rows]
            bounds=[v['boundary_start']['t_monotonic_ns'],v['boundary_end']['t_monotonic_ns']]
            scope(rows,name,kind,raw/'samples.json',locs,bounds=bounds,target=v['interval_target_s'])
            result['scopes'][-1]['periodic_saved_points']=len(v['samples'])
            result['phases'].append(phase(tag+' container observation',*bounds,
                cpu_start=rows[0]['cpu_usage_usec'],cpu_end=rows[-1]['cpu_usage_usec'],divisor=1e6,
                note='resource boundary window, not exact Agent function duration'))
        host=inp.json(raw/'host_process.jsonl')  # This filename holds one JSON document.
        rows=[dict(x,clk_tck=host['summary']['clk_tck']) for x in host['records']]
        scope(rows,host['summary']['scope'],'shared_host_mini_child',raw/'host_process.jsonl',
              [f'records[{i}]' for i in range(len(rows))],process=True,target=None)
        result['phases'] += [phase('setup',None,None,note='no precise standalone saved setup interval'),phase('cleanup',None,None,note='container stop/removal markers are points, not start/end spans')]
        verifier=[x for x in pairs(events)[0] if x['kind']=='verifier' and x['attrs'].get('status')=='running']
        for x in verifier:result['phases'].append(phase('verifier running call',x['start_ns'],x['end_ns']))
        result.update(attempt_wall_s=report['budget_usage']['elapsed_total_s'],attempt_wall_source='run-report.budget_usage.elapsed_total_s',
            run_root_span_s=root_span[0]['duration_s'],task_result={'resolved':report['resolved'],'evaluation_status':report['evaluation_status']},
            termination=result['behavior']['termination'],infra=report['cleanup_errors'],cleanup_status=report['cleanup_status'],
            entry_returncode=archived_returncode,returncode_source='central validation-closeout.runs.entry_returncode; raw report does not duplicate shell returncode',
            returncode_reason='entry expects archive_status==complete while runner success is ok; verified archives intact; no code/return value changed',
            raw_runner_statuses={k:report[k] for k in ('execution_status','evaluation_status','archive_status','cleanup_status')},
            collector_read_wall_ns=samples['collector']['read_wall_ns'],origin_source='events run.open.t_monotonic_ns',
            host_collector_read_wall_ns=host['summary']['collector']['read_wall_ns_total'])
    else:
        origin=report['parent_start_ns'];envdoc=inp.json(raw/'environment.json');hz=envdoc['sc_clk_tck'];rows=inp.lines(raw/'samples.jsonl')
        for row in rows:row['clk_tck']=hz
        scope(rows,'worker','shared_Agent_User_tools_evaluator_worker',raw/'samples.jsonl',[f'line {i+1}' for i in range(len(rows))],process=True)
        bounds=inp.lines(raw/'boundaries.jsonl');byname={x['phase']:x for x in bounds}
        for name,a,b in [('initialization','worker_start','play_begin'),('imports','imports_begin','imports_end'),('play','play_begin','play_end'),('evaluator','evaluate_begin','evaluate_end')]:
            l,h=byname.get(a,{}),byname.get(b,{})
            result['phases'].append(phase(name,l.get('t_monotonic_ns'),h.get('t_monotonic_ns'),cpu_start=l.get('cpu_ticks'),cpu_end=h.get('cpu_ticks'),divisor=hz,
                note='imports is nested within initialization; do not sum both; shared worker counters'))
        result['phases'].append(phase('worker end to reap check',byname.get('worker_end',{}).get('t_monotonic_ns'),report['cleanup']['checked_monotonic_ns'],note='observed tail span, not an exclusive full cleanup cost'))
        result.update(attempt_wall_s=report['wall_s'],attempt_wall_source='run-report.wall_s; final outer report writes follow',worker_window_wall_s=report['worker_window_wall_s'],
            task_result=report['evaluation'],termination=report['worker_result']['stop'],infra=report['worker_result']['failure'],cleanup=report['cleanup'],
            entry_returncode=report['exit_code'],clk_tck=hz,origin_source='run-report.parent_start_ns',collector_read_wall_ns=None,
            project_layer_attempts=sum(x['terminal_attrs'].get('transport_attempt_count',0) for x in pairs(events)[0] if x['kind']=='llm_request'),
            system_setup_boundaries=sum(x['phase']=='system_setup_exec' for x in bounds),
            batch_spans=sum(x['kind']=='tool_batch' for x in pairs(events)[0]))
    result['origin_monotonic_ns']=origin
    net,data=project_network(supplemental['network']['samples'],str(raw/'supplemental_measurements.json'))
    series.extend(data);result['network']=net
    result['network']['read_wall_ns']=supplemental['network'].get('read_wall_ns')
    result['network']['target_interval_s']=supplemental['network']['interval_target_s']
    result['disk']={'task_workspace':supplemental['task_workspace']['status'],
                    'container':supplemental['container_disk_footprints'],'host':supplemental['disk_footprint'],
                    'basis':'apparent file size; no allocated size; host output end scan precedes final archive writes'}
    observed=[(s['sample_window_ns'][0],s['sample_window_ns'][1]) for s in result['scopes'] if s['sample_window_ns']]
    result['resource_observed_union_s']=_duration(observed)
    merged = _merge(observed)
    lo, hi = origin, origin + round(result['attempt_wall_s']*1e9)
    cursor = lo
    uncovered = []
    for a,b in merged:
        a,b=max(a,lo),min(b,hi)
        if b<a:continue
        if a>cursor:uncovered.append([cursor,a])
        cursor=max(cursor,b)
    if cursor<hi:uncovered.append([cursor,hi])
    result['resource_windows_union_ns']=merged
    result['attempt_regions_without_any_listed_resource_scope_ns']=uncovered
    for scope_stats in result['scopes']:
        candidates=[x for x in series if x['scope']==scope_stats['scope'] and x['status']=='valid' and x['metric']=='cpu']
        peak=max(candidates,key=lambda x:x['value'],default=None)
        if peak:
            scope_stats['cpu_rate_peak']={k:peak[k] for k in ('value','t0','t1','source','locator')}
            scope_stats['cpu_rate_peak']['overlapping_saved_phases']=[p['name'] for p in result['phases']
                if p['start_ns'] is not None and p['end_ns'] is not None and peak['t0']<p['end_ns'] and peak['t1']>p['start_ns']]
            scope_stats['cpu_rate_peak']['overlapping_requests']=[x['event_id'] for x in result['behavior']['requests']
                if peak['t0']<x['end_ns'] and peak['t1']>x['start_ns']]
            scope_stats['cpu_rate_peak']['overlapping_tools']=[{'event_id':x['event_id'],'name':x['name']} for x in result['behavior']['tools']
                if peak['t0']<x['end_ns'] and peak['t1']>x['start_ns']]
            scope_stats['cpu_rate_peak']['note']='interval/phase co-occurrence only, not exclusive or causal attribution'
    result['measurement_status']={
        'semantic_pairing':'verified' if not any(result['behavior']['pairing_quality'].values()) else 'partial',
        'resource_gaps':{s['scope']:{k:v['gap'] for k,v in s['metric_quality'].items() if v['gap']} for s in result['scopes']},
        'coverage':'only the saved scope windows; not the whole attempt',
        'supplement_aggregate':supplemental['status'],'cache_and_api_bytes':'unsupported/unknown'}
    result['scan_window_cooccurrence']=[]
    for scope_name,footprint in supplemental['container_disk_footprints'].items():
        for boundary,scan in footprint.items():
            if boundary not in ('before_agent','after_agent','before_verifier','after_verifier'):continue
            for entry in scan.get('entries',[]):
                start=entry.get('scan_started_monotonic_ns');duration=entry.get('scan_wall_ns')
                if type(start) is int and type(duration) is int:
                    result['scan_window_cooccurrence'].append({'scope':scope_name,'boundary':boundary,
                        'path':entry.get('path'),'start_ns':start,'scan_wall_ns':duration,
                        'coincident_resource_scopes':[s['scope'] for s in result['scopes'] if s['sample_window_ns'] and
                            s['sample_window_ns'][0]<=start<=start+duration<=s['sample_window_ns'][1]],
                        'clock':'saved container_kernel_monotonic scan timestamps versus same-host resource timestamps; includes read-boundary error',
                        'note':'co-occurrence only; scanner activity not subtracted from resource counts'})
    result['timeline_scope_note']='resource windows differ from attempt wall; no full-lifecycle coverage claim'
    result['figure']=f'figures/{chain.lower()}.svg';result['series_csv']=f'series/{chain.lower()}.csv'
    return result,series


COLORS=['#165dbe','#b45309','#16826c','#9e3e8c','#5650a3','#975b33','#476774','#d43c46']


def render_svg(run, series):
    """No chart library; interval rates are horizontal segments, gaps never joined."""
    width,height=1500,1510;left,right=85,1120;origin=run['origin_monotonic_ns']
    time_end=max([run['attempt_wall_s']]+[(x['t1']-origin)/1e9 for x in series if type(x['t1']) is int])
    def xpos(t):return left+(t-origin)/1e9/max(time_end,.001)*(right-left)
    chunks=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{html.escape(run["chain"])} saved resource observations</title>',
        '<style>text{font-family:sans-serif;fill:#243447;font-size:12px}.small{font-size:10px}.phase{stroke:#7e8793;stroke-dasharray:3 4;opacity:.6}</style>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="40" y="30" font-size="19">{html.escape(run["chain"])} | {html.escape(run["run_id"])}</text>',
        f'<text x="40" y="53">t=0: {html.escape(run["origin_source"])} = {origin} ns (same-host monotonic); one saved run</text>',
        '<text x="40" y="75">Gaps stay gaps. CPU is interval-average core (1 core = 100%); not remote model CPU or exclusive tool cost.</text>',
        '<text x="40" y="96">Network: up to 3 complete-window non-lo interfaces ranked by rx+tx; display rule, NOT identified API egress. Never sum interfaces.</text>']
    panels=[('CPU interval average (core)','cpu','core'),('Observed memory (MiB; current and RSS distinct)','memory','MiB'),
            ('Disk counters: cgroup / proc, separate series (MiB/s)','disk','MiB/s'),('Shared netns per-interface rx/tx (MiB/s)','network','MiB/s')]
    for panel,(title,kind,unit) in enumerate(panels):
        y=135+panel*325;plot_top=y+90;bottom=y+260
        relevant=[x for x in series if (x['metric']=='cpu' if kind=='cpu' else x['metric'] in ('RSS','memory.current') if kind=='memory' else x['scope_kind']=='shared_netns_interface' if kind=='network' else x['unit']=='B/s' and x['scope_kind']!='shared_netns_interface')]
        groups=defaultdict(list)
        for row in relevant:groups[(row['scope'],row['metric'])].append(row)
        divisor=1048576 if kind in ('disk','network') else 1
        maximum=max((x['value']/divisor for x in relevant if x['value'] is not None and math.isfinite(x['value'])),default=0)
        maximum=maximum*1.08 if maximum>0 else 1
        chunks.append(f'<text x="40" y="{y+8}" font-size="16">{title}</text>')
        chunks.append(f'<path d="M{left} {plot_top}V{bottom}H{right}" stroke="#8b97a5" fill="none"/>')
        for j in range(5):
            yy=bottom-(bottom-plot_top)*j/4
            chunks.append(f'<path d="M{left} {yy}H{right}" stroke="#e3e7ec"/><text x="{left-10}" y="{yy+4}" text-anchor="end">{maximum*j/4:.3g}</text>')
        for j in range(6):
            t=time_end*j/5;xx=left+(right-left)*j/5
            chunks.append(f'<text x="{xx}" y="{bottom+20}" text-anchor="middle">{t:.2f}s</text>')
        for j,(key,rows) in enumerate(groups.items()):
            color=COLORS[j%len(COLORS)];label=html.escape(key[0]+' / '+key[1])
            # Scope IDs may be long: legends wrap into the wide right margin.
            chunks.append(f'<text class="small" x="{left+(j%2)*520}" y="{y+29+(j//2)*15}" style="fill:{color}">{label}</text>')
            previous=None
            for row in rows:
                if row['value'] is None or row['status']!='valid' or type(row['t0']) is not int or type(row['t1']) is not int:
                    previous=None;continue
                yy=bottom-row['value']/divisor/maximum*(bottom-plot_top)
                x0,x1=xpos(row['t0']),xpos(row['t1'])
                if kind=='memory':
                    if previous is not None:
                        chunks.append(f'<path class="data" d="M{previous[0]:.3f} {previous[1]:.3f}L{x1:.3f} {yy:.3f}" stroke="{color}" fill="none"/>')
                    else:chunks.append(f'<circle class="data" cx="{x1:.3f}" cy="{yy:.3f}" r="1.4" fill="{color}"/>')
                    previous=(x1,yy)
                else:
                    chunks.append(f'<path class="data" d="M{x0:.3f} {yy:.3f}H{x1:.3f}" stroke="{color}" stroke-width="1.4" fill="none"/>')
        for j,p in enumerate(run['phases']):
            for endpoint in ('start_ns','end_ns'):
                if type(p[endpoint]) is not int:continue
                xx=xpos(p[endpoint]);chunks.append(f'<path class="phase" d="M{xx:.3f} {plot_top}V{bottom}"/>')
            if type(p['start_ns']) is int:
                chunks.append(f'<text class="small" x="1140" y="{plot_top+j*17}">{html.escape(p["name"])}: {(p["start_ns"]-origin)/1e9:.3f} - {"?" if p["end_ns"] is None else format((p["end_ns"]-origin)/1e9,".3f")}s</text>')
        chunks.append(f'<text class="small" x="40" y="{bottom+43}">Source: series/{run["chain"].lower()}.csv (source file + locator + raw monotonic endpoints); unit={unit}; no smoothing/interpolated missing points.</text>')
    chunks.append('<text x="40" y="1465">Disk/proc counters are not complete filesystem I/O. Shared netns includes background traffic and virtual-interface duplicate observations.</text>')
    chunks.append('<text x="40" y="1486">Directory scans may contribute CPU/I/O inside these windows. Kernel memory peak is not a current/RSS curve; scope peaks are never added.</text></svg>')
    return '\n'.join(chunks)


def disk_rows(run):
    out=[]
    for name,value in run['disk']['container'].items():
        for p in value['footprint']['paths']:out.append((name,p))
    out += [('host log/output/cache',p) for p in run['disk']['host']['paths']]
    return out


def markdown(summary):
    out=['# 火山网关三链单次行为—资源分析','',
         '三次独立验证的主要计数、资源曲线与目录边界可核验；不是类别对照实验，每类n=1，不合并旧27次重复。', '',
         '|链路|请求/角色|工具/角色|任务结果|终止|attempt wall s|清理/归档|',
         '|---|---|---|---|---|---|---|']
    for r in summary['runs']:
        result=r['task_result'];score=result.get('reward',result.get('resolved',result.get('similarity')))
        out.append(f'|{r["chain"]}|{r["behavior"]["logical_requests"]} / {r["behavior"]["requests_by_role"]}|{r["behavior"]["tools_by_role"]}|{score}|{r["termination"]}|{r["attempt_wall_s"]:.6f}|归档哈希/文件集通过；RC={r["entry_returncode"]}|')
    out += ['', '## 有限观察（均为本次固定任务n=1）','']
    for r in summary['runs']:
        observed=[p for p in r['phases'] if p['shared_cpu_s'] is not None and p['name']!='imports']
        out.append('- '+r['chain']+'：'+ '；'.join(f'{p["name"]}窗口 {p["wall_s"]:.3f}s / 共享CPU {p["shared_cpu_s"]:.6f}s' for p in observed)+'。阶段/边界口径独立，不解释为工具独占或因果。')
    out += ['- 任务目录前后扫描与共享netns逐接口观测均有可回读证据；Assistant场景状态在内存，目录not_applicable。日志/输出目录、缓存与任务目录分列，缓存仍unsupported。',
            '- CPU区间峰与阶段只作共现：逐scope的峰值区间、源位置和相交阶段在JSON中；不能证明是某个工具、线程池或函数造成。', '']
    for r in summary['runs']:
        out += ['',f'## {r["chain"]}：{r["run_id"]}','',f'![{r["chain"]}资源曲线]({r["figure"]})','',
                f'[独立SVG]({r["figure"]}) · [作图CSV]({r["series_csv"]})。t=0来自 `{r["origin_source"]}`，原始值 `{r["origin_monotonic_ns"]}` ns。',
                f'实际响应model分别为 `{r["behavior"]["response_models"]}`。两种标识不能据名称判为两个不同后端或保证同一后端。', '',
                '|scope|保存点数（含边界）|采样窗 s|有效CPU区间/候选|有效差分CPU-s|内存采样峰 bytes|内核peak bytes|实际间隔median/max s|',
                '|---|---|---|---|---|---|---|---|']
        for s in r['scopes']:
            cpu=s['metric_quality']['cpu']
            out.append(f'|{s["scope"]}|{s["saved_points_including_boundaries"]}|{s["sample_window_s"]}|{cpu["valid"]}/{cpu["candidate"]}|{cpu["observed_valid_delta_sum"]}|{s["memory_measure"]}: {s["memory_sampled_peak_bytes"]}|{s["kernel_memory_peak_bytes"]}|{s["actual_interval_median_s"]}/{s["actual_interval_max_s"]}|')
        out += ['', '|scope|I/O计数器|有效区间/候选|有效观测差分 bytes|gap原因|','|---|---|---|---|---|']
        for s in r['scopes']:
            for name,value in s['metric_quality'].items():
                if name!='cpu':out.append(f'|{s["scope"]}|{name}|{value["valid"]}/{value["candidate"]}|{value["observed_valid_delta_sum"]}|{value["gap_reasons"]}|')
        out += ['', '|实际阶段/观测跨度|wall s|共享scope CPU-s|说明|','|---|---|---|---|']
        for p in r['phases']:out.append(f'|{p["name"]}|{p["wall_s"]}|{p["shared_cpu_s"]}|{p["note"]}|')
        out += ['', '工具顺序（不映射成工具独占资源）：', '',
                ' → '.join((t.get('name') or 'unknown') + (' [Submitted控制流]' if t.get('exception_type')=='Submitted' else ' [已记录错误]' if t['status']=='error' else '') for t in r['behavior']['tools']),
                '',f'角色计数：{r["behavior"]["tools_by_role"]}；普通工具错误 {r["behavior"]["ordinary_tool_errors"]}，控制流终态 {r["behavior"]["control_flow_terminals"]}；终止后请求 {r["behavior"]["requests_after_termination"]}。',
                f'网络保存 {r["network"]["saved_points"]} 点、{r["network"]["interface_count"]} 接口；展示 {r["network"]["selected_interfaces"]}。按全窗口有效同接口rx+tx排序只为展示，不是API出口识别，跨接口不求和。完整逐接口统计在per_run.jsonl。',
                '', '|展示接口|完整有效窗rx变化 B|完整有效窗tx变化 B|rx/tx有效区间|','|---|---|---|---|']
        for name in r['network']['selected_interfaces']:
            metrics=r['network']['interfaces'][name]
            out.append(f'|{name}|{metrics["rx_bytes"]["full_window_delta_bytes"]}|{metrics["tx_bytes"]["full_window_delta_bytes"]}|{metrics["rx_bytes"]["valid"]}/{metrics["tx_bytes"]["valid"]}|')
        out += ['', '|目录角色/scope|路径|before B|after B|增长 B|状态|扫描wall ns（前/后）|','|---|---|---|---|---|---|---|']
        if r['disk']['task_workspace']=='not_applicable':out.append('|任务状态|内存场景|N/A|N/A|N/A|not_applicable|N/A|')
        for name,p in disk_rows(r):
            a,b=p.get('before') or {},p.get('after') or {}
            out.append(f'|{name} / {p.get("scope")}|{a.get("path")}|{a.get("bytes")}|{b.get("bytes")}|{p.get("delta_bytes")}|{p.get("delta_status")}|{a.get("scan_wall_ns")}/{b.get("scan_wall_ns")}|')
        out += ['',f'已保存资源读取wall成本：{r.get("collector_read_wall_ns")} ns；独立宿主monitor读取：{r.get("host_collector_read_wall_ns")} ns；共享网络读取：{r["network"]["read_wall_ns"]} ns。None表示未保存；读取wall成本不是完整采集器CPU。',
                f'观测覆盖状态：`{r["measurement_status"]}`。无任何已列资源scope覆盖的attempt区间（monotonic ns）为 `{r["attempt_regions_without_any_listed_resource_scope_ns"]}`；这不是“等待/思考时间”。',
                '目录扫描位于相应资源观测窗口内时，CPU/I/O包括这一观测活动；没有剔除成“纯任务成本”。宿主日志结束占用测量早于最终归档完成，不是最终归档总大小。',
                'null/None表示未知或不可用，不是0。RSS/current/内核peak分列，不相加。网络与资源采样窗口均不等于attempt完整生命周期。']
        if r['chain']=='Coding':out += ['', 'RC7保持原值：入口要求archive_status==complete，而共享runner成功值为ok；本次execution/evaluation/archive/cleanup均ok，归档文件集和哈希通过，是入口退出码误判，不是已证实归档损坏；未修改入口、旧返回码或重跑。',
            f'保存命令的静态用途分类：{r["behavior"]["operation_counts"]}，分母为保存工具调用，不是CPU或时长比例。shell普通返回码分布：{r["behavior"]["shell_returncode_counts"]}，非零返回不与Submitted控制流终态混淆。',
            '容器目标采样0.5s；host_mini_child实际约0.2s，未保存独立目标间隔，target保持unknown。末次宿主读取process_exited造成一个有效性gap，未补成0，也不据此把容器有效区间丢弃。']
        if r['chain']=='Assistant':out += ['', 'ConnectionError是保存的业务工具返回（并非自动归为网关/infra失败）；结束由User end_conversation。官方similarity保留原值，不自设成功阈值。初始化、play、evaluator的CPU窗口各自独立，不能把整个worker CPU统称Agent工具成本。']
    out += ['', '## 核验与边界','',f'三份raw文件集及哈希、外层归档和完整保存身份关联通过。当前源码漂移记录：{summary["verification"]["current_code_drift"]}。只核验实际读取的输入，不声称重审全仓库。',
            '每类只有一次固定任务，不能推断类别规律、稳定性、因果、效率或排名；不与旧批混算。请求时长不是思考时间，wall−CPU没有等待时间含义。无HTTP传输hook和账单，实际HTTP数/费用unknown；token与项目尝试不代替它们。',
            '采样细目（逐指标valid/gap/reason、读取状态、时间异常、窗口）保存在summary.json/per_run.jsonl；未插值、未补零。CSV仅保存图中资源scope与最多3个选中接口的实际点/区间，其余接口保留机器可读统计。',
            '资源峰值与阶段/请求/工具只能称同窗共现，不是独占资源或因果；短调用可能处于同一0.5s采样区间。不同CPU端点窗口不强行守恒。',
            '本轮仅离线分析；未运行任务或evaluator、未调用API/Docker、未更新HTML、未提交Git。CPU-02/Replay暂停，Gate裁定不变。']
    return '\n'.join(out)+'\n'


def build(root=ROOT, output=None):
    root=Path(root).resolve();out=(Path(output) if output else root/OUTPUT).resolve()
    require(not out.exists(),'output exists; never overwrite a published analysis')
    inp=Inputs(root);saved,close,archives,sets=verify_inputs(inp)
    runs=[];data=[]
    for spec in RUNS:
        old=next(x for x in close['runs'] if x['chain']==spec[0])
        run,series=analyze_run(inp,spec,saved[spec[0]],old['entry_returncode'],
                               report_path=Path('reports/resource')/spec[1]/'run-report.json')
        require(old['logical_requests']==run['behavior']['logical_requests'],'central request count differs from raw')
        require(old['response_models']==run['behavior']['response_models'],'central response models differ from raw')
        require(old['tool_pairs']==len(run['behavior']['tools']),'central tool count differs from raw')
        require(old['entry_returncode']==run['entry_returncode'],'central returncode mismatch')
        require(not any(run['behavior']['pairing_quality'].values()),'semantic event pairing error')
        if 'native_tool_pairing_quality' in run['behavior']:
            require(not any(run['behavior']['native_tool_pairing_quality'].values()),'native event pairing error')
        runs.append(run);data.append(series)
    summary={'schema':'volcano-three-chain-characterization-v1','scope':'exactly 3 fixed independent single runs, each n=1; no cross-class denominator',
             'runs':runs,'verification':{'archives':archives,'current_code_drift':inp.drift,'saved_identity_structures':'verified'}}
    out.mkdir(parents=True);(out/'figures').mkdir();(out/'series').mkdir()
    for run,series in zip(runs,data):
        svg=render_svg(run,series);ElementTree.fromstring(svg)
        (out/run['figure']).write_text(svg)
        with (out/run['series_csv']).open('w',newline='') as stream:
            fields=['run_id','scope','scope_kind','metric','t0','t1','start_s','end_s','value','unit','status','reason','delta','source','locator']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for x in series:
                writer.writerow(dict(x,run_id=run['run_id'],start_s=(x['t0']-run['origin_monotonic_ns'])/1e9 if type(x['t0']) is int else None,
                    end_s=(x['t1']-run['origin_monotonic_ns'])/1e9 if type(x['t1']) is int else None))
    (out/'summary.md').write_text(markdown(summary))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (out/'per_run.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in runs))
    # Read cost and footprint tables use the same per-run structure as the report.
    with (out/'directory_footprint.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['chain','scope','path','before_bytes','after_bytes','delta_bytes','status','basis'])
        for run in runs:
            for name,p in disk_rows(run):writer.writerow([run['chain'],p.get('scope'),(p.get('before') or {}).get('path'),(p.get('before') or {}).get('bytes'),(p.get('after') or {}).get('bytes'),p.get('delta_bytes'),p.get('delta_status'),'apparent_file_size'])
    for path in (__file__,ROOT/'tests/test_volcano_three_chain_characterization.py',ROOT/'scripts/toolsandbox_resource_pilot_02_review.py',ROOT/'src/agent_workload_characterization/collectors/execution_measurement.py',ROOT/'src/agent_workload_characterization/analyzers/public_operations.py'):
        inp.data(Path(path).resolve())
    for key,before in list(inp.records.items()):require(file_record(Path(key),root)==before,'input changed during analysis: '+key)
    for directory,names in sets.items():require(sorted(str(p.relative_to(root/directory)) for p in (root/directory).rglob('*') if p.is_file())==names,'protected input file set changed')
    manifest={'input_root':str(root),'output_root':str(out),'inputs':sorted(inp.records.values(),key=lambda x:x['path']),
              'analysis_code':str(Path(__file__).resolve()),'historical_file_sets_unchanged':sets,
              'outputs':[file_record(p,out) for p in sorted(out.rglob('*')) if p.is_file()]}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for record in manifest['outputs']:require(file_record(out/record['path'],out)==record,'output hash readback failed')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=build(args.root,args.output)
    print(json.dumps({'runs':len(result['runs']),'output':str(args.output or args.root/OUTPUT),'status':'complete_limited_offline_analysis'},ensure_ascii=False))


if __name__=='__main__':main()
