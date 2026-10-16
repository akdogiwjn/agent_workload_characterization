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
    MeasuredLLM, environment_snapshot, measurement_report, sample_quality, span_coverage)
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


if __name__ == '__main__':
    unittest.main()
