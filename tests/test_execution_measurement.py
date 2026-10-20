"""Offline regression of saved measurement evidence; never call external APIs."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_workload_characterization.collectors.execution_measurement import (
    MeasuredLLM, RunSupplement, counter_rate_intervals, directory_footprint_snapshot,
    disk_footprint_report, environment_snapshot, measurement_report,
    network_rate_intervals, read_network_namespace, sample_quality, span_coverage,
    office_resource_rate_intervals, container_directory_footprint_snapshot)
from agent_workload_characterization.collectors.semantic_recorder import SemanticRecorder, SystemClock
from agent_workload_characterization.collectors.resource_sampler import ResourceSampler, CounterSnapshot
from agent_workload_characterization.collectors.host_process import HostProcessReader


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recorder = SemanticRecorder(self.root, SystemClock(), run_id='r',
            attempt_id='a', task_id='t', source_type='synthetic')
        self.recorder.begin_run()

    def test_request_zero_usage_and_response_identity_no_secret(self):
        class Transport:
            async def call(self, **kwargs):
                return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=0,
                    completion_tokens=0, cache_tokens=0), model_name='response-model', response_id='id')
        agent = SimpleNamespace(model_name='planned-model')
        llm = MeasuredLLM(Transport(), self.recorder, agent)
        asyncio.run(llm.call(prompt='private prompt', message_history=[{'content': 'private history'}]))
        self.recorder.seal()
        raw = (self.root / 'events.jsonl').read_text()
        self.assertNotIn('private prompt', raw)
        self.assertNotIn('private history', raw)
        end = next(e for e in map(json.loads, raw.splitlines()) if e['kind'] == 'llm_request' and e['status'] == 'closed')
        self.assertEqual(end['attrs']['usage']['prompt_tokens'], 0)
        self.assertEqual(end['attrs']['response_model'], 'response-model')
        report = measurement_report(self.root / 'events.jsonl', expected_requests=1, expected_tools=0)
        self.assertEqual(report['call_timing_status'], 'complete')
        self.assertEqual(report['request_usage_missing_or_unreturned'], 0)
        self.assertIsNone(report['transport_attempts']['value'])

    def test_normal_seal_closes_run_root_with_its_open_event_id(self):
        self.recorder.seal()
        rows = [json.loads(line) for line in (self.root / 'events.jsonl').read_text().splitlines()]
        opened = next(row for row in rows if row['kind'] == 'run' and row['status'] == 'open')
        terminal = [row for row in rows if row['kind'] == 'run' and row['status'] == 'closed']
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0]['event_id'], opened['event_id'])

    def test_transport_error_and_cancellation_are_closed_without_exception_text(self):
        for exc in (RuntimeError('private key material'), asyncio.CancelledError()):
            class Transport:
                async def call(self, **kwargs):
                    raise exc
            agent = SimpleNamespace(model_name='fake')
            llm = MeasuredLLM(Transport(), self.recorder, agent)
            with self.assertRaises(type(exc)):
                asyncio.run(llm.call(prompt='', message_history=[]))
        self.recorder.seal()
        raw = (self.root / 'events.jsonl').read_text()
        self.assertNotIn('private key', raw)
        report = span_coverage(self.root / 'events.jsonl')
        self.assertEqual(report['spans']['llm_request']['error_terminal'], 2)
        self.assertEqual(report['status'], 'verified')

    def test_unclosed_is_censored_not_zero(self):
        self.recorder.begin('tool_call', {'tool_name': 'fake'})
        self.recorder.seal()
        report = measurement_report(self.root / 'events.jsonl', expected_requests=0, expected_tools=1)
        self.assertEqual(report['call_timing_status'], 'partial')
        self.assertEqual(report['tool_spans']['spans']['tool_call']['censored'], 1)

    def test_duplicate_pair_bool_time_and_unknown_time_rejected(self):
        event = self.recorder.begin('llm_request', {})
        self.recorder.end(event)
        self.recorder.seal()
        path = self.root / 'events.jsonl'
        original = path.read_text()
        rows = [json.loads(l) for l in original.splitlines()]
        end = next(e for e in rows if e['kind'] == 'llm_request' and e['status'] == 'closed')
        for mutation in ('duplicate', 'bool', 'unknown'):
            copy = json.loads(json.dumps(rows))
            target = next(e for e in copy if e['kind'] == 'llm_request' and e['status'] == 'closed')
            if mutation == 'duplicate':
                copy.append(end)
            elif mutation == 'bool':
                target['t_monotonic_ns'] = True
            else:
                target['attrs']['timing_source'] = 'unknown'
            path.write_text('\n'.join(json.dumps(e) for e in copy))
            self.assertEqual(span_coverage(path)['status'], 'partial', mutation)

    def test_missing_events_cannot_pass_with_zero_expected_counts(self):
        report = measurement_report(self.root / 'absent', expected_requests=0, expected_tools=0)
        self.assertEqual(report['call_timing_status'], 'partial')

    def test_native_child_times_not_parent_receipt_times(self):
        event = self.recorder.begin('llm_request', {})
        self.recorder.end(event, attrs={'timing_source': 'child_status', 't_start_ns': 9, 't_end_ns': 8})
        self.recorder.seal()
        self.assertIn('invalid_or_missing_time', span_coverage(self.root / 'events.jsonl')['errors'])

    def test_sampling_zero_missing_reset_and_boundary_quality(self):
        def row(t, role, cpu):
            return {'t_monotonic_ns': t, 'role': role, 'container': {
                'cpu_usage_usec': cpu, 'mem_current_bytes': 0, 'io_read_bytes': 0,
                'io_write_bytes': 0, 'read_status': {'cpu.stat': 'ok'}}}
        rows = [row(1, 'boundary_start', 0), row(2, 'sample', 0), row(3, 'boundary_end', 0)]
        self.assertEqual(sample_quality(rows, .5)['status'], 'complete')
        rows[1]['container']['cpu_usage_usec'] = None
        self.assertEqual(sample_quality(rows, .5)['missing']['cpu_usage_usec'], 1)
        rows[1]['container']['cpu_usage_usec'] = 10
        self.assertEqual(sample_quality(rows, .5)['counter_regressions']['cpu_usage_usec'], 1)

    def test_sampler_cost_includes_boundaries(self):
        class Reader:
            def read(self, t):
                return CounterSnapshot(scope='s', scope_kind='agent_container', t_monotonic_ns=t,
                    cpu_usage_usec=0, read_status={'cpu.stat': 'ok'})
        sampler = ResourceSampler()
        sampler.register('s', 'agent_container', Reader())
        sampler.start('s')
        sampler.sample_once()
        sampler.stop('s')
        result = sampler.collector_self_observation()
        self.assertEqual(result['total_reads'], 3)
        self.assertGreaterEqual(result['read_wall_ns'], 0)

    def test_host_identity_counters_and_no_unrelated_process_reads(self):
        fields = ['0'] * 22
        fields[0] = 'R'
        for i, value in ((7, 3), (9, 2), (11, 7), (12, 5), (17, 4), (19, 123), (21, 10)):
            fields[i] = str(value)
        proc = self.root / '42'
        proc.mkdir()
        (proc / 'stat').write_text('42 (owned) ' + ' '.join(fields))
        (proc / 'io').write_text('rchar: 1\nwchar: 2\nread_bytes: 0\nwrite_bytes: 0\n')
        (proc / 'status').write_text('voluntary_ctxt_switches: 3\nnonvoluntary_ctxt_switches: 4\n')
        reader = HostProcessReader(42, proc_root=self.root, expected_starttime=123)
        snap = reader.read()
        self.assertEqual((snap.user_ticks, snap.system_ticks, snap.minor_faults, snap.major_faults, snap.threads), (7, 5, 3, 2, 4))
        self.assertEqual(snap.process_io['read_bytes'], 0)
        reader.expected_starttime = 124
        self.assertIsNone(reader.read().cpu_ticks)

    def test_environment_does_not_persist_credentials_or_whole_environment(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'secret-test-value'}):
            result = environment_snapshot()
        self.assertNotIn('secret-test-value', json.dumps(result))
        self.assertNotIn('DEEPSEEK_API_KEY', json.dumps(result))
        self.assertIn('python', result)
        self.assertEqual(result['cache_initial_state']['reason'], 'not_controlled')

    def test_counter_intervals_compute_core_and_io_rates_and_preserve_gaps(self):
        rows = [
            {'t_monotonic_ns': 1_000_000_000, 'scope': 's', 'cpu': 0, 'read': 0, 'read_status': 'ok'},
            {'t_monotonic_ns': 1_500_000_000, 'scope': 's', 'cpu': 500_000, 'read': 100, 'read_status': 'ok'},
            {'t_monotonic_ns': 1_500_000_000, 'scope': 's', 'cpu': 600_000, 'read': 200, 'read_status': 'ok'},
            {'t_monotonic_ns': 2_000_000_000, 'scope': 's', 'cpu': 100, 'read': 10, 'read_status': 'ok'},
            {'t_monotonic_ns': 2_500_000_000, 'scope': 's', 'cpu': None, 'read': 20, 'read_status': 'ok'},
        ]
        intervals = counter_rate_intervals(rows, {
            'cpu': {'path': 'cpu', 'divisor': 1_000_000, 'unit': 'cpu_seconds',
                    'identity_paths': ['scope'], 'status_path': 'read_status'},
            'read': {'path': 'read', 'unit': 'bytes', 'identity_paths': ['scope'],
                     'status_path': 'read_status'}})
        self.assertEqual(intervals[0]['metrics']['cpu']['rate_per_s'], 1.0)
        self.assertEqual(intervals[0]['metrics']['read']['rate_per_s'], 200.0)
        self.assertEqual(intervals[1]['metrics']['cpu']['reason'], 'nonpositive_or_invalid_time_delta')
        self.assertEqual(intervals[2]['metrics']['cpu']['reason'], 'counter_decreased')
        self.assertEqual(intervals[3]['metrics']['cpu']['reason'], 'counter_missing_or_invalid')

    def test_counter_interval_nested_reader_status_accepts_real_cgroup_status(self):
        rows = [
            {'t_monotonic_ns': 1_000_000_000, 'cpu_usage_usec': 0,
             'scope': 's', 'read_status': {'cpuacct.usage': 'ok_ns_converted_to_usec'}},
            {'t_monotonic_ns': 2_000_000_000, 'cpu_usage_usec': 250_000,
             'scope': 's', 'read_status': {'cpuacct.usage': 'ok_ns_converted_to_usec'}},
        ]
        interval = counter_rate_intervals(rows, {
            'cpu': {'path': 'cpu_usage_usec', 'divisor': 1_000_000,
                    'unit': 'cpu_seconds', 'rate_unit': 'average_core',
                    'identity_paths': ['scope'],
                    'status_paths': [('read_status', 'cpu.stat'),
                                     ('read_status', 'cpuacct.usage')]}})[0]
        self.assertEqual(interval['metrics']['cpu']['status'], 'valid')
        self.assertEqual(interval['metrics']['cpu']['rate_per_s'], 0.25)

    def test_counter_interval_does_not_join_different_resource_scopes(self):
        rows = [
            {'t_monotonic_ns': 1_000_000_000, 'scope': 'agent', 'cpu': 10},
            {'t_monotonic_ns': 2_000_000_000, 'scope': 'verifier', 'cpu': 20},
        ]
        interval = counter_rate_intervals(rows, {
            'cpu': {'path': 'cpu', 'unit': 'cpu_seconds', 'scope_path': 'scope'}})[0]
        self.assertEqual(interval['metrics']['cpu']['status'], 'gap')
        self.assertEqual(interval['metrics']['cpu']['reason'], 'scope_identity_changed')

    def test_counter_interval_checks_both_endpoint_status_and_identity(self):
        def row(t, status, *, pid=7, start=100, cpu=0, io=0):
            return {'t_monotonic_ns': t, 'pid': pid, 'start': start,
                    'cpu': cpu, 'io': io, 'read_status': status}
        spec = {'cpu': {'path': 'cpu', 'unit': 'ticks',
                        'identity_paths': ['pid', 'start'],
                        'status_path': 'read_status'},
                'io': {'path': 'io', 'unit': 'bytes',
                       'identity_paths': ['pid', 'start'],
                       'status_path': 'read_status'}}
        for left_status, right_status in (('permission_denied', 'ok'),
                                           ('ok', 'permission_denied'),
                                           ('permission_denied', 'permission_denied')):
            got = counter_rate_intervals([row(1, left_status), row(2, right_status)], spec)[0]
            self.assertEqual(got['metrics']['cpu']['status'], 'gap')
        valid = counter_rate_intervals([row(1, 'ok', cpu=1), row(2, 'ok', cpu=2)], spec)[0]
        self.assertEqual(valid['metrics']['cpu']['delta'], 1)
        self.assertEqual(valid['metrics']['io']['delta'], 0)
        changed = counter_rate_intervals([row(1, 'ok'), row(2, 'ok', start=101)], spec)[0]
        self.assertEqual(changed['metrics']['cpu']['reason'], 'scope_identity_changed')
        missing = counter_rate_intervals([row(1, 'ok'),
            {'t_monotonic_ns': 2, 'read_status': 'ok', 'cpu': 1, 'io': 1}], spec)[0]
        self.assertEqual(missing['metrics']['cpu']['reason'], 'scope_identity_missing')

    def test_counter_interval_keeps_metric_gaps_independent_and_does_not_bridge_missing_reads(self):
        rows = [
            {'t_monotonic_ns': 1_000_000_000, 'pid': 9, 'start': 30,
             'cpu': 0, 'io': 0, 'status': {'cpu': 'ok', 'io': 'permission_denied'}},
            {'t_monotonic_ns': 2_000_000_000, 'pid': 9, 'start': 30,
             'cpu': 1_000_000, 'io': 10, 'status': {'cpu': 'ok', 'io': 'ok'}},
            {'t_monotonic_ns': 3_000_000_000, 'pid': 9, 'start': 30,
             'cpu': 2_000_000, 'io': 20, 'status': {'cpu': 'permission_denied', 'io': 'ok'}},
            {'t_monotonic_ns': 4_000_000_000, 'pid': 9, 'start': 30,
             'cpu': 3_000_000, 'io': 30, 'status': {'cpu': 'ok', 'io': 'ok'}},
        ]
        intervals = counter_rate_intervals(rows, {
            'cpu': {'path': 'cpu', 'divisor': 1_000_000, 'unit': 'cpu_seconds',
                    'rate_unit': 'average_core', 'identity_paths': ['pid', 'start'],
                    'status_path': ('status', 'cpu')},
            'io': {'path': 'io', 'unit': 'bytes', 'identity_paths': ['pid', 'start'],
                   'status_path': ('status', 'io')}})
        self.assertEqual(intervals[0]['metrics']['cpu']['status'], 'valid')
        self.assertEqual(intervals[0]['metrics']['io']['reason'], 'reader_status_left:permission_denied')
        self.assertEqual(intervals[1]['metrics']['cpu']['reason'], 'reader_status_right:permission_denied')
        self.assertEqual(intervals[1]['metrics']['io']['status'], 'valid')
        self.assertEqual(intervals[2]['metrics']['cpu']['status'], 'gap')
        self.assertEqual(intervals[2]['metrics']['io']['status'], 'valid')

    def test_counter_interval_rejects_bool_negative_counter_and_negative_timestamp(self):
        spec = {'cpu': {'path': 'cpu', 'divisor': 100, 'unit': 'cpu_seconds',
                        'identity_paths': ['scope'], 'status_path': 'status'}}
        def pair(left, right):
            return counter_rate_intervals([left, right], spec)[0]['metrics']['cpu']
        base = {'t_monotonic_ns': 1, 'scope': 's', 'cpu': 0, 'status': 'ok'}
        self.assertEqual(pair(base, {**base, 't_monotonic_ns': 2, 'cpu': True})['reason'],
                         'counter_missing_or_invalid')
        self.assertEqual(pair({**base, 'cpu': -1}, {**base, 't_monotonic_ns': 2})['reason'],
                         'negative_counter')
        self.assertEqual(pair({**base, 't_monotonic_ns': -1},
                              {**base, 't_monotonic_ns': 2})['reason'],
                         'nonpositive_or_invalid_time_delta')

    def test_office_nested_sample_projection_uses_nested_status_identity_and_clk_tck(self):
        def sample(t, cpu_usec, io_read, ticks, rchar, *, cstatus='ok_summed_devices',
                   hstatus='ok', container='cid', pid=17, start=123, clk=100):
            return {'t_monotonic_ns': t,
                'container': {'scope_kind': 'agent_container', 'container_id': container,
                    'cpu_usage_usec': cpu_usec, 'io_read_bytes': io_read,
                    'io_write_bytes': io_read * 2,
                    'read_status': {'cpu.stat': 'ok', 'io.stat': cstatus}},
                'host_agent': {'pid': pid, 'starttime_ticks': start, 'clk_tck': clk,
                    'cpu_ticks': ticks, 'process_io': {'rchar': rchar, 'wchar': rchar * 2,
                        'read_bytes': rchar * 3, 'write_bytes': rchar * 4},
                    'read_status': {'stat': hstatus, 'io': hstatus}}}
        rows = [sample(1_000_000_000, 100, 50, 100, 100),
                sample(2_000_000_000, 1_000_100, 550, 125, 400)]
        projected = office_resource_rate_intervals(rows, container_id='cid')
        c = projected['container'][0]['metrics']
        h = projected['host_agent_process'][0]['metrics']
        self.assertEqual(c['cpu']['rate_per_s'], 1.0)
        self.assertEqual(c['io_read']['rate_per_s'], 500.0)
        self.assertEqual(c['io_write']['rate_per_s'], 1000.0)
        self.assertEqual(h['cpu']['rate_per_s'], .25)
        self.assertEqual(h['proc_rchar']['rate_per_s'], 300.0)
        bad = [rows[0], sample(2_000_000_000, 1_000_100, 550, 125, 400,
                               cstatus='not_found', hstatus='permission_denied')]
        broken = office_resource_rate_intervals(bad, container_id='cid')
        self.assertEqual(broken['container'][0]['metrics']['io_read']['status'], 'gap')
        self.assertEqual(broken['container'][0]['metrics']['cpu']['status'], 'valid')
        self.assertEqual(broken['host_agent_process'][0]['metrics']['cpu']['status'], 'gap')

    def test_office_projection_breaks_on_container_identity_and_unknown_clk_tck(self):
        base = {'t_monotonic_ns': 1_000_000_000,
            'container': {'cpu_usage_usec': 0, 'io_read_bytes': 0, 'io_write_bytes': 0,
                          'read_status': {'cpu.stat':'ok','io.stat':'ok'}},
            'host_agent': {'pid': 1, 'starttime_ticks': 2, 'cpu_ticks': 10,
                'clk_tck': None, 'process_io': {'rchar': 0, 'wchar': 0,
                'read_bytes': 0, 'write_bytes': 0},
                'read_status': {'stat':'ok','io':'ok'}}}
        nxt = json.loads(json.dumps(base)); nxt['t_monotonic_ns'] += 1_000_000_000
        nxt['container']['cpu_usage_usec'] = 1_000_000
        result = office_resource_rate_intervals([base, nxt], container_id=None)
        self.assertEqual(result['container'][0]['metrics']['cpu']['reason'], 'scope_identity_missing')
        self.assertEqual(result['host_agent_process'][0]['metrics']['cpu']['reason'],
                         'unit_conversion_unavailable')

    def test_office_projection_detects_container_identity_change_in_nested_rows(self):
        def row(t, cid, cpu):
            return {'t_monotonic_ns': t, 'container': {'container_id': cid,
                    'cpu_usage_usec': cpu, 'read_status': {'cpu.stat': 'ok'}},
                    'host_agent': {'pid': 1, 'starttime_ticks': 5, 'clk_tck': 100,
                        'cpu_ticks': 10, 'process_io': {},
                        'read_status': {'stat': 'ok', 'io': 'ok'}}}
        result = office_resource_rate_intervals([row(1, 'container-a', 0),
                                                 row(2, 'container-b', 1_000_000)],
                                                container_id='fallback')
        self.assertEqual(result['container'][0]['metrics']['cpu']['reason'],
                         'scope_identity_changed')

    def test_container_disk_snapshot_uses_runtime_execute_and_bounded_timeout(self):
        class Runtime:
            def execute(self, handle, command, timeout_s, *, output_limit):
                self.command, self.timeout_s = command, timeout_s
                self.assert_output_limit = output_limit
                payload = {'clock_domain': 'container_kernel_monotonic',
                    't_monotonic_ns': 10, 'entries': [{'role':'task_workspace',
                     'scope':'agent:/testbed', 'path':'/testbed', 'status':'complete',
                     'bytes':12, 'observed_subtotal_bytes':12, 'scan_wall_ns':3}]}
                return {'returncode':0, 'output':json.dumps(payload)}
        runtime = Runtime()
        result = container_directory_footprint_snapshot(runtime, object(),
            [{'path':'/testbed','role':'task_workspace','scope':'agent:/testbed'}],
            timeout_s=.25)
        self.assertEqual(result['entries'][0]['bytes'], 12)
        self.assertEqual(runtime.timeout_s, .25)
        self.assertIn('/testbed', runtime.command)
        class TimedOutRuntime:
            def execute(self, handle, command, timeout_s, *, output_limit):
                return {'returncode': 124, 'timed_out': True, 'output': ''}
        failed = container_directory_footprint_snapshot(TimedOutRuntime(), object(),
            [{'path': '/testbed', 'role': 'task_workspace', 'scope': 'agent:/testbed'}],
            timeout_s=.1)
        self.assertEqual(failed['status'], 'partial')
        self.assertEqual(failed['entries'][0]['role'], 'task_workspace')
        self.assertIsNone(failed['entries'][0]['bytes'])

    def test_network_namespace_projection_and_unsupported_source_are_explicit(self):
        fixture = self.root / 'proc'
        (fixture / 'self/net').mkdir(parents=True)
        (fixture / 'self/ns').mkdir(parents=True)
        (fixture / 'self/net/dev').write_text(
            'Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n'
            ' eth0: 100 1 0 0 0 0 0 0 250 1 0 0 0 0 0 0\n')
        (fixture / 'self/ns/net').symlink_to('net:[42]')
        # readlink() is patched because a fixture symlink cannot reproduce a kernel netns link.
        with patch('os.readlink', return_value='net:[42]'):
            snap = read_network_namespace(fixture, t_monotonic_ns=10)
        self.assertEqual(snap['scope_kind'], 'network_namespace_shared')
        self.assertEqual(snap['interfaces']['eth0'], {'rx_bytes': 100, 'tx_bytes': 250})
        rate = network_rate_intervals([
            snap,
            {**snap, 't_monotonic_ns': 1_000_000_010,
             'interfaces': {'eth0': {'rx_bytes': 300, 'tx_bytes': 450}}}])[0]
        self.assertEqual(rate['metrics']['rx_bytes']['bytes_per_s'], 200.0)
        self.assertEqual(rate['metrics']['tx_bytes']['bytes_per_s'], 200.0)
        gap = network_rate_intervals([snap, {**snap, 't_monotonic_ns': 20,
             'interfaces': {'eth0': {'rx_bytes': 1, 'tx_bytes': 450}}}])[0]
        self.assertEqual(gap['metrics']['rx_bytes']['reason'], 'counter_decreased')
        namespace_gap = network_rate_intervals([snap, {**snap, 't_monotonic_ns': 20,
             'namespace_id': 'net:[43]'}])[0]
        self.assertEqual(namespace_gap['metrics']['rx_bytes']['reason'],
                         'network_namespace_identity_missing_or_changed')
        missing_namespace = network_rate_intervals([
            {**snap, 'namespace_id': None}, {**snap, 't_monotonic_ns': 20,
             'namespace_id': None}])[0]
        self.assertIsNone(missing_namespace['metrics']['rx_bytes']['bytes_per_s'])
        changed_interface = network_rate_intervals([
            snap, {**snap, 't_monotonic_ns': 1_000_000_010,
                   'interfaces': {'veth0': {'rx_bytes': 200, 'tx_bytes': 300}}}])[0]
        self.assertEqual(changed_interface['metrics']['rx_bytes']['reason'],
                         'interface_or_counter_missing')
        failed_read = network_rate_intervals([
            snap, {**snap, 't_monotonic_ns': 1_000_000_010,
                   'read_status': 'PermissionError'}])[0]
        self.assertEqual(failed_read['metrics']['rx_bytes']['reason'],
                         'network_counter_read_unavailable')

    def test_disk_footprint_overlap_symlink_disappearance_and_growth(self):
        root = self.root / 'out'
        nested = root / 'nested'
        nested.mkdir(parents=True)
        (root / 'a.bin').write_bytes(b'abc')
        (nested / 'b.bin').write_bytes(b'12345')
        link = self.root / 'out-link'
        link.symlink_to(root, target_is_directory=True)
        specs = [
            {'path': str(root), 'role': 'output', 'scope': 'run', 'ownership': 'run_scoped'},
            {'path': str(nested), 'role': 'nested', 'scope': 'run'},
            {'path': str(link), 'role': 'link', 'scope': 'run'},
            {'path': None, 'role': 'workspace', 'scope': 'container',
             'unavailable_status': 'unsupported', 'reason': 'not_host_visible'},
        ]
        before = directory_footprint_snapshot(specs)
        self.assertEqual(next(x for x in before['entries'] if x['role'] == 'output')['bytes'], 8)
        self.assertEqual(next(x for x in before['entries'] if x['role'] == 'nested')['status'],
                         'overlapping_path_excluded')
        self.assertEqual(next(x for x in before['entries'] if x['role'] == 'link')['status'],
                         'symlink_not_followed')
        self.assertEqual(next(x for x in before['entries'] if x['role'] == 'workspace')['status'],
                         'unsupported')
        (root / 'a.bin').write_bytes(b'abcdefgh')
        after = directory_footprint_snapshot(specs)
        report = disk_footprint_report(before, after)
        self.assertEqual(next(x for x in report['paths'] if x['role'] == 'output')['delta_bytes'], 5)

    def test_disk_scan_disappearance_is_partial_not_zero(self):
        root = self.root / 'changing'
        root.mkdir()
        gone = root / 'gone.bin'
        gone.write_bytes(b'disappears')
        real_scandir = os.scandir
        def disappearing_scandir(path):
            rows = list(real_scandir(path))
            if Path(path) == root:
                gone.unlink()
            return rows
        with patch('agent_workload_characterization.collectors.execution_measurement.os.scandir',
                   side_effect=disappearing_scandir):
            row = directory_footprint_snapshot([{'path': str(root), 'role': 'out', 'scope': 'run'}])['entries'][0]
        self.assertEqual(row['status'], 'partial')
        self.assertIsNone(row['bytes'])
        self.assertIn('file_disappeared_during_scan', row['errors'])

    def test_disk_scan_permission_and_deadline_are_partial_not_zero(self):
        root = self.root / 'restricted'
        root.mkdir()
        with patch('agent_workload_characterization.collectors.execution_measurement.os.scandir',
                   side_effect=PermissionError()):
            denied = directory_footprint_snapshot([{'path': str(root), 'role': 'workspace',
                                                       'scope': 'container'}])['entries'][0]
        self.assertEqual(denied['status'], 'partial')
        self.assertIsNone(denied['bytes'])
        expired = directory_footprint_snapshot([{'path': str(root), 'role': 'workspace',
                                                   'scope': 'container'}], timeout_s=0)['entries'][0]
        self.assertEqual(expired['status'], 'partial')
        self.assertIn('scan_timeout', expired['errors'])

    def test_run_supplement_stops_and_returns_raw_and_derived_network_data(self):
        root = self.root / 'run'
        root.mkdir()
        value = {'rx': 0, 'tx': 0}
        def fake_reader(*, t_monotonic_ns):
            value['rx'] += 10
            value['tx'] += 20
            return {'scope': 'current_process_network_namespace',
                    'scope_kind': 'network_namespace_shared', 'namespace_id': 'net:[test]',
                    't_monotonic_ns': t_monotonic_ns,
                    'interfaces': {'eth-test': {'rx_bytes': value['rx'], 'tx_bytes': value['tx']}},
                    'read_status': 'observed'}
        supplement = RunSupplement(root, interval_s=10, network_reader=fake_reader)
        supplement.start()
        (root / 'output.bin').write_bytes(b'x')
        result = supplement.stop()
        self.assertEqual(result['disk_footprint']['paths'][0]['delta_bytes'], 1)
        self.assertGreaterEqual(result['network']['sample_count'], 2)
        self.assertEqual(result['network']['scope_kind'], 'network_namespace_shared')
        self.assertTrue(result['network']['intervals'])
        self.assertEqual(result['api_transport_bytes']['status'], 'unsupported')
        self.assertEqual(result['measurement_contract_version'], 'real-run-measurement-v3')


if __name__ == '__main__':
    unittest.main()
