"""Offline Git publication boundaries and repaired historical navigation."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_data_payloads_and_archive_are_ignored(self):
        paths = ['data/raw/public/example.json', 'data/normalized/example.jsonl',
                 'data/future_dataset/payload.json', 'local_archive/example.md',
                 'data/catalog/public_trace_acquisition/example/source_metadata/body.json',
                 'data/catalog/public_trace_acquisition/example/raw/trace.json',
                 'data/catalog/public_trace_acquisition/example/http/response.headers',
                 'data/catalog/p1_12_closure_evidence/registry_token_response.json']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(subprocess.run(['git', 'check-ignore', '--no-index', '-q', path],
                                                cwd=ROOT).returncode, 0)

    def test_catalog_configuration_and_acquisition_ledgers_are_visible(self):
        paths = ['data/catalog/README.md', 'data/catalog/sources.yaml',
                 'data/catalog/pilot_run_config.yaml', 'data/catalog/pilot_task_record.yaml',
                 'data/catalog/public_trace_acquisition/example/manifest.json',
                 'data/catalog/public_trace_acquisition/example/sources.json',
                 'data/catalog/public_trace_acquisition/example/summary.md',
                 'data/catalog/p1_12_closure_evidence/manifest.json',
                 'data/catalog/p1_12_closure_evidence/license_astropy.rst']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(subprocess.run(['git', 'check-ignore', '--no-index', '-q', path],
                                                cwd=ROOT).returncode, 1)

    def test_g0_migrated_links_use_existing_index_anchors(self):
        text = (ROOT / 'reports/quality/g0_review.md').read_text()
        index = (ROOT / 'docs/history_index.md').read_text()
        links = re.findall(r'\]\((\.\./\.\./docs/history_index\.md#([^)]+))\)', text)
        self.assertEqual(len(links), 5)
        for _, anchor in links:
            self.assertIn('id="' + anchor + '"', index)
        for old in ['coding_pilot_handoff.md', 'p0_07_08_09_delivery.md',
                    'coding_pilot_delivery.md', 'model_smoke_delivery.md']:
            self.assertNotIn('](../../docs/' + old, text)


if __name__ == '__main__':
    unittest.main()
