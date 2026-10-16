#!/usr/bin/env python3
"""Directed counter-example tests for coding_resource_link_feasibility helpers.

Synthetic samples/events only; no real run data, no network, no execution.
"""
import json, os, sys, tempfile, importlib.util

spec = importlib.util.spec_from_file_location(
    'crif', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'coding_resource_link_feasibility.py'))
crif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crif)


def test_cover_fraction_full_partial_none():
    ivs = [(10, 20), (30, 40)]
    assert abs(crif.cover_fraction(ivs, 10, 20) - 1.0) < 1e-9
    assert abs(crif.cover_fraction(ivs, 5, 15) - 0.5) < 1e-9
    assert abs(crif.cover_fraction(ivs, 20, 30) - 0.0) < 1e-9
    # adjacent intervals merge in union
    assert abs(crif.cover_fraction([(0, 10), (10, 20)], 0, 20) - 1.0) < 1e-9


def test_pure_classification_boundaries():
    # interval fully inside a request, no tools -> only_req
    # interval straddling request edge -> mixed
    # interval with no events -> uncovered
    with tempfile.TemporaryDirectory() as d:
        # t0 = 0; points at 0.5s steps; cpu counter +1e6 usec per interval (1 core-s each)
        pts = []
        t = 500_000_000
        for i in range(4):
            pts.append({'t_monotonic_ns': t * (i + 1), 'cpu_usage_usec': 1_000_000 * (i + 1),
                        'mem_current_bytes': 1, 'mem_peak_bytes': 1,
                        'io_read_bytes': 0, 'io_write_bytes': 0, 'read_status': {}})
        samples = {
            'interval_s': 0.5,
            'evidence': {'sc-agent': {
                'boundary_start': {'t_monotonic_ns': 0, 'cpu_usage_usec': 0},
                'boundary_end': {'t_monotonic_ns': 2_000_000_000, 'cpu_usage_usec': 4_000_000},
                'samples': pts, 'sample_gaps_ns': []}},
        }
        json.dump(samples, open(os.path.join(d, 'samples.json'), 'w'))
        # requests cover [0.2s, 0.7s) -> interval2 [0.5,1.0) partially covered
        status = [{'t_start_ns': 200_000_000, 't_end_ns': 700_000_000, 'n_calls': 1}]
        with open(os.path.join(d, 'mini_status.jsonl'), 'w') as f:
            f.write(json.dumps(status[0]) + '\n')
        # tool covers [1.0s, 2.0s) fully -> intervals 3,4 are only_tool... but interval
        # boundaries: intervals are [0,0.5),[0.5,1.0),[1.0,1.5),[1.5,2.0)
        ev = [
            {'event': 'open', 'tool_call_id': 'c1', 't_start_ns': 1_000_000_000, 'event_id': 'e1', 'seq': 1},
            {'event': 'closed', 'tool_call_id': 'c1', 't_start_ns': 1_000_000_000,
             't_end_ns': 2_000_000_000, 'event_id': 'e1', 'seq': 1, 'returncode': 0},
        ]
        with open(os.path.join(d, 'mini_tool_events.jsonl'), 'w') as f:
            for e in ev:
                f.write(json.dumps(e) + '\n')
        json.dump({'run_id': 'test', 'task_id': 't__t-1', 'execution_status': 'ok'},
                  open(os.path.join(d, 'metadata.json'), 'w'))
        r = crif.analyze_run(d)
        c = r['cpu_core_s_by_category']
        # interval1 [0,0.5): request covers 0.2-0.5 -> partial -> mixed
        # interval2 [0.5,1.0): request covers 0.5-0.7 -> partial -> mixed
        # interval3 [1.0,1.5): fully tool -> only_tool
        # interval4 [1.5,2.0): fully tool -> only_tool
        assert abs(c['mixed'] - 2.0) < 1e-6, c
        assert abs(c['only_tool'] - 2.0) < 1e-6, c
        assert c['only_req'] == 0.0 and c['uncovered'] == 0.0
        assert r['cpu_intervals']['neg_diff'] == 0


def test_unpaired_tool_raises():
    with tempfile.TemporaryDirectory() as d:
        samples = {'interval_s': 0.5, 'evidence': {'sc-agent': {
            'boundary_start': {'t_monotonic_ns': 0, 'cpu_usage_usec': 0},
            'boundary_end': {'t_monotonic_ns': 1, 'cpu_usage_usec': 1},
            'samples': [], 'sample_gaps_ns': []}}}
        json.dump(samples, open(os.path.join(d, 'samples.json'), 'w'))
        with open(os.path.join(d, 'mini_status.jsonl'), 'w') as f:
            pass
        with open(os.path.join(d, 'mini_tool_events.jsonl'), 'w') as f:
            f.write(json.dumps({'event': 'open', 'tool_call_id': 'c1',
                                't_start_ns': 1, 'event_id': 'e1', 'seq': 1}) + '\n')
        json.dump({'run_id': 't', 'task_id': 't', 'execution_status': 'ok'},
                  open(os.path.join(d, 'metadata.json'), 'w'))
        try:
            crif.analyze_run(d)
            raise AssertionError('expected ValueError for unclosed tool call')
        except ValueError as e:
            assert 'unclosed' in str(e)


def test_negative_cpu_diff_counted_not_attributed():
    with tempfile.TemporaryDirectory() as d:
        pts = [{'t_monotonic_ns': 500_000_000, 'cpu_usage_usec': 500_000,
                'mem_current_bytes': 1, 'mem_peak_bytes': 1,
                'io_read_bytes': 0, 'io_write_bytes': 0, 'read_status': {}}]
        samples = {'interval_s': 0.5, 'evidence': {'sc-agent': {
            'boundary_start': {'t_monotonic_ns': 0, 'cpu_usage_usec': 1_000_000},
            'boundary_end': {'t_monotonic_ns': 500_000_000, 'cpu_usage_usec': 500_000},
            'samples': pts, 'sample_gaps_ns': []}}}
        json.dump(samples, open(os.path.join(d, 'samples.json'), 'w'))
        open(os.path.join(d, 'mini_status.jsonl'), 'w').close()
        open(os.path.join(d, 'mini_tool_events.jsonl'), 'w').close()
        json.dump({'run_id': 't', 'task_id': 't', 'execution_status': 'ok'},
                  open(os.path.join(d, 'metadata.json'), 'w'))
        r = crif.analyze_run(d)
        assert r['cpu_intervals']['neg_diff'] == 1
        assert r['cpu_total_core_s'] == 0.0


if __name__ == '__main__':
    test_cover_fraction_full_partial_none()
    test_pure_classification_boundaries()
    test_unpaired_tool_raises()
    test_negative_cpu_diff_counted_not_attributed()
    print('all 4 directed tests passed')
