#!/usr/bin/env python3
"""CODING-RESOURCE-LINK-feasibility-v1: pure-interval CPU decomposition.

For each of the nine CODING-REPEAT-01 runs, classify every agent-container
CPU sampling interval (adjacent-point counter difference) by event coverage:
  only_req  - interval fully covered by LLM request intervals, no tool interval
  only_tool - interval fully covered by tool intervals, no request interval
  uncovered - interval with no request and no tool coverage
  mixed     - anything else (partial overlaps) - reported separately, never split
CPU is the cgroup cpuacct counter difference between adjacent sample points
(same basis as characterization-v3 cpu_intervals). No per-call attribution,
no linear time-proration, no wall-CPU subtraction.
"""
import json, os, sys, hashlib

BASE_DIR = '/home/lcq/agent_workload_characterization/data/raw/generated/P1-12-CODING-REPEAT-01'
OUT_DIR = '/home/lcq/agent_workload_characterization/reports/analysis/CODING-RESOURCE-LINK-feasibility-v1'
TOL = 1e-9


def cover_fraction(ivs_sorted, a, b):
    """Fraction of [a,b) covered by union of intervals."""
    tot = 0
    cur = a
    for s, e in ivs_sorted:
        if e <= cur:
            continue
        if s > b:
            break
        tot += min(e, b) - max(s, cur)
        cur = max(cur, e)
    return tot / (b - a) if b > a else 0.0


def load_run(run_dir):
    samples = json.load(open(os.path.join(run_dir, 'samples.json')))
    events = [json.loads(l) for l in open(os.path.join(run_dir, 'mini_tool_events.jsonl'))]
    status = [json.loads(l) for l in open(os.path.join(run_dir, 'mini_status.jsonl'))]
    meta = json.load(open(os.path.join(run_dir, 'metadata.json')))
    return samples, events, status, meta


def analyze_run(run_dir):
    samples, events, status, meta = load_run(run_dir)
    ag = [k for k in samples['evidence'] if 'agent' in k]
    if len(ag) != 1:
        raise ValueError('expected exactly one agent scope, got %d' % len(ag))
    ev = samples['evidence'][ag[0]]
    pts = ev['samples']

    # tool intervals: pair open/closed by tool_call_id (identity-gated)
    opens = {}
    tool_iv = []
    for e in events:
        if e['event'] == 'open':
            if e['tool_call_id'] in opens:
                raise ValueError('duplicate open for %s' % e['tool_call_id'])
            opens[e['tool_call_id']] = e['t_start_ns']
        else:
            s = opens.pop(e['tool_call_id'], None)
            if s is None or e['t_start_ns'] != s:
                raise ValueError('unpaired terminal for %s' % e['tool_call_id'])
            if e['t_end_ns'] < e['t_start_ns']:
                raise ValueError('end before start for %s' % e['tool_call_id'])
            tool_iv.append((e['t_start_ns'], e['t_end_ns']))
    if opens:
        raise ValueError('unclosed tool calls: %d' % len(opens))
    req_iv = [(e['t_start_ns'], e['t_end_ns']) for e in status]
    for s, e in req_iv:
        if e < s:
            raise ValueError('request end before start')

    tool_iv.sort()
    req_iv.sort()

    # CPU intervals from boundary_start + sample points + boundary_end
    # (counter differences; same 224-pair basis as characterization-v3)
    t0 = ev['boundary_start']['t_monotonic_ns']
    c0 = ev['boundary_start']['cpu_usage_usec']
    ts = [t0] + [p['t_monotonic_ns'] for p in pts] + [ev['boundary_end']['t_monotonic_ns']]
    cs = [c0] + [p['cpu_usage_usec'] for p in pts] + [ev['boundary_end']['cpu_usage_usec']]
    cats = {'only_req': 0.0, 'only_tool': 0.0, 'uncovered': 0.0, 'mixed': 0.0}
    n = {'only_req': 0, 'only_tool': 0, 'uncovered': 0, 'mixed': 0}
    neg_diff = 0
    invalid_time = 0
    for i in range(len(ts) - 1):
        a, b = ts[i], ts[i + 1]
        if b < a:
            invalid_time += 1
            continue
        d_cpu = (cs[i + 1] - cs[i]) / 1e6  # usec -> core-s
        if d_cpu < 0:
            neg_diff += 1
            continue
        if b - a > 10 * 2 * samples['interval_s'] * 1e9:
            # sample gap far beyond twice the target interval: still counted,
            # but classified by coverage only (gaps are recorded in raw evidence)
            pass
        fr = cover_fraction(req_iv, a, b)
        ft = cover_fraction(tool_iv, a, b)
        if fr >= 1.0 - TOL and ft <= TOL:
            k = 'only_req'
        elif ft >= 1.0 - TOL and fr <= TOL:
            k = 'only_tool'
        elif fr <= TOL and ft <= TOL:
            k = 'uncovered'
        else:
            k = 'mixed'
        cats[k] += d_cpu
        n[k] += 1
    total_cpu = sum(cats.values())
    pure_cpu = total_cpu - cats['mixed']
    tool_durs = sorted((e - s) / 1e9 for s, e in tool_iv)
    return {
        'run_id': meta['run_id'],
        'task': meta['task_id'],
        'termination': meta.get('execution_status'),
        'n_tool_calls': len(tool_iv),
        'n_requests': len(req_iv),
        'tool_duration_s': {
            'median': tool_durs[len(tool_durs) // 2] if tool_durs else None,
            'n_below_sampling_interval': sum(1 for d in tool_durs if d < samples['interval_s']),
            'sampling_interval_s': samples['interval_s'],
        },
        'cpu_intervals': {
            'neg_diff': neg_diff, 'invalid_time': invalid_time,
            'n': sum(n.values()),
            'n_by_category': n,
        },
        'cpu_core_s_by_category': {k: round(v, 6) for k, v in cats.items()},
        'cpu_total_core_s': round(total_cpu, 6),
        'pure_share_of_cpu': round(pure_cpu / total_cpu, 4) if total_cpu > 0 else None,
    }


def main():
    runs = sorted(os.listdir(BASE_DIR))
    if len(runs) != 9:
        raise ValueError('expected 9 runs, got %d' % len(runs))
    results = []
    for run in runs:
        results.append(analyze_run(os.path.join(BASE_DIR, run)))
    out = {
        'schema': 'coding-resource-link-feasibility-v1',
        'method': {
            'cpu_basis': 'cgroup cpuacct adjacent-point counter difference (same as characterization-v3 cpu_intervals)',
            'classification': 'pure-interval: interval 100% inside request-union and 0% tool -> only_req; 100% tool and 0% request -> only_tool; 0%/0% -> uncovered; anything else -> mixed (never prorated)',
            'tolerance': TOL,
            'no_per_call_attribution': True,
            'no_time_proration': True,
        },
        'runs': results,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, 'per_run_decomposition.json'), 'w') as f:
        json.dump(out, f, indent=1)
    # compact table
    print('%-8s %-24s %8s %8s %8s %8s %8s %6s' % (
        'run', 'task', 'req', 'tool', 'uncov', 'mixed', 'total', 'pure%'))
    for r in results:
        c = r['cpu_core_s_by_category']
        print('%-8s %-24s %8.2f %8.2f %8.2f %8.2f %8.2f %6.1f' % (
            r['run_id'][-6:], r['task'][:24], c['only_req'], c['only_tool'],
            c['uncovered'], c['mixed'], r['cpu_total_core_s'],
            100 * (r['pure_share_of_cpu'] or 0)))
    # per-task aggregate (median over runs)
    tasks = {}
    for r in results:
        tasks.setdefault(r['task'], []).append(r)
    print()
    for t, rs in sorted(tasks.items()):
        for k in ('only_req', 'only_tool', 'uncovered', 'mixed'):
            vals = sorted(x['cpu_core_s_by_category'][k] for x in rs)
            print('task %-24s %-10s median=%.2f (raw %s)' % (t[:24], k, vals[len(vals)//2],
                  ['%.2f' % v for v in vals]))


if __name__ == '__main__':
    main()
