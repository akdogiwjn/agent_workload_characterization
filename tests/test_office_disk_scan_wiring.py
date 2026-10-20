"""Real Office handle/exec/scanner/archive path; only external transports fake."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
from tests.test_docops_measurement_validate_01_entry import external_boundaries
import docops_measurement_validate_01_entry as entry
from tests.test_docops_cleanup import assert_archive
from agent_workload_characterization.runners.container_runtime import (
    DockerCliRuntime, ContainerHandle, ContainerSpec)
from agent_workload_characterization.collectors.execution_measurement import (
    container_directory_footprint_snapshot)


class OfficeScanTests(unittest.TestCase):
    def run_profile(self, failed):
        profile = entry.VOLCANO_02_PROFILE
        argv_seen = []
        scan_runtime = DockerCliRuntime(authorized=True)

        def popen(argv, **kwargs):
            argv_seen.append(argv)
            self.assertEqual(argv[1:4], ['exec', '-w', '/'])
            self.assertIn('/root/submission', argv[-1])
            data = {'entries': [{'role': 'task_workspace_and_submission',
                    'scope': 'agent_container:/root/submission', 'path': '/root/submission',
                    'status': 'complete', 'bytes': len(argv_seen) * 10}]}

            class Process:
                returncode = 7 if failed else 0
                stdout = io.BytesIO((('synthetic failure Authorization: Bearer synthetic-secret ' + 'x' * 700)
                                     if failed else json.dumps(data)).encode())
                def poll(self): return self.returncode
                def wait(self): return self.returncode
            return Process()

        with tempfile.TemporaryDirectory(prefix='office-scan-wiring-') as tmp, \
                patch.dict(os.environ, {}, clear=False), external_boundaries(self) as (transport, runtime, *_):
            root = Path(tmp)
            runtime.execute = scan_runtime.execute
            entry.freeze(root, profile=profile)
            entry.record_explicit_approval(root, profile=profile)
            plan = entry.plan_mode(root, profile=profile)
            from agent_workload_characterization.runners import smoke_launcher
            route = entry.configured_route(profile)
            with patch.object(smoke_launcher, 'load_credentials', return_value=(route['api_base'], 'synthetic')), \
                    patch('subprocess.Popen', side_effect=popen):
                self.assertEqual(entry.execute(root, plan, profile=profile), 0)
            report = json.loads((root / profile.report_rel / 'run-report.json').read_text())
            summary = report['summary']
            assert_archive(self, root, summary)
            self.assertEqual(transport.order[-2:], ['cleanup', 'verify_removal'])
            self.assertEqual(runtime.removal_calls, 1)
            self.assertEqual(len(argv_seen), 2)
            raw = root / profile.raw_rel / summary['run_id']
            disk = json.loads((raw / 'supplemental_measurements.json').read_text())
            scope = disk['container_disk_footprints']['task_workspace_submission']
            if failed:
                for boundary in ('before_agent', 'after_agent'):
                    row = scope[boundary]
                    self.assertIsNone(row['entries'][0]['bytes'])
                    self.assertEqual(row['diagnostics']['returncode'], 7)
                    self.assertIs(row['diagnostics']['timed_out'], False)
                    self.assertEqual(row['diagnostics']['cwd'], '/')
                    self.assertNotIn('synthetic-secret', row['diagnostics']['error_summary'])
                    self.assertLessEqual(len(row['diagnostics']['error_summary']), 512)
            else:
                self.assertEqual(scope['footprint']['paths'][0]['delta_bytes'], 10)

    def test_real_office_handle_exec_scanner_and_archive(self):
        self.run_profile(False)

    def test_failed_scan_keeps_null_diagnostics_and_cleanup(self):
        self.run_profile(True)

    def test_coding_default_cwd_unchanged_and_scan_timeout(self):
        handle = ContainerHandle('f' * 64, ContainerSpec('fixture', 'agent', 'synthetic'))
        argv = DockerCliRuntime().build_exec_argv(handle, 'true')
        self.assertEqual(argv[1:4], ['exec', '-w', '/testbed'])
        class Runtime:
            def execute(self, *a, **kw):
                return {'returncode': 124, 'timed_out': True, 'output': 'synthetic scan timeout'}
        row = container_directory_footprint_snapshot(Runtime(), handle,
            [{'path': '/testbed', 'role': 'task_workspace', 'scope': 'agent'}], timeout_s=1)
        self.assertIsNone(row['entries'][0]['bytes'])
        self.assertEqual(row['diagnostics'], {'returncode': 124, 'timed_out': True,
            'cwd': '/testbed', 'error_summary': 'synthetic scan timeout'})

    def test_new_collection_guard_and_identity_contains_actual_scanner(self):
        profile = entry.VOLCANO_02_PROFILE
        with tempfile.TemporaryDirectory(prefix='office-plan-guard-') as tmp:
            root = Path(tmp)
            with patch.object(entry.office, 'inspect_image', side_effect=AssertionError('Docker')):
                plan = entry.plan_mode(root, profile=profile)
            self.assertEqual(list(root.iterdir()), [])
            entry.freeze(root, profile=profile)
            entry.record_explicit_approval(root, profile=profile)
            self.assertTrue(entry.plan_mode(root, profile=profile)['ready_for_execution'])
            paths = {r['path'] for r in plan['identity']['code_and_runtime_files']}
            self.assertIn('src/agent_workload_characterization/collectors/execution_measurement.py', paths)
            self.assertIn(profile.entry_script, paths)
            (root / profile.raw_rel / 'previous').mkdir(parents=True)
            self.assertFalse(entry.plan_mode(root, profile=profile)['ready_for_execution'])
            with self.assertRaises(SystemExit) as rejected:
                entry.main(['--execute', entry.VOLCANO_PROFILE.flag], root=root, profile=profile)
            self.assertEqual(rejected.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
