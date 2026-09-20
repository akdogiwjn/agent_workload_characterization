import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_project_state import PAGES, check, render


class ProjectStateTests(unittest.TestCase):
    def fixture(self, root):
        state = {'updated_at': 'fixture', 'public_summary': ['offline only'],
                 'execution_authorization': 'none_this_state_is_not_an_approval',
                 'evidence': [{'path': 'evidence.txt', 'sha256': hashlib.sha256(b'fixture').hexdigest()}]}
        (root / 'project_state.json').write_text(json.dumps(state))
        (root / 'evidence.txt').write_bytes(b'fixture')
        for page in PAGES:
            target = root / page
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(state, page))

    def test_clean_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            self.assertEqual(check(root), [])

    def test_drift_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            p = root / 'README.md'
            p.write_text(p.read_text().replace('offline only', 'run now'))
            self.assertTrue(check(root))
            self.fixture(root)
            p.write_text(p.read_text() * 2)
            self.assertTrue(check(root))

    def test_evidence_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            (root / 'evidence.txt').write_bytes(b'changed')
            self.assertTrue(any('evidence mismatch' in x for x in check(root)))

    def test_cannot_grant_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            p = root / 'project_state.json'; s = json.loads(p.read_text())
            s['execution_authorization'] = 'approved'; p.write_text(json.dumps(s))
            self.assertIn('state must not authorize execution', check(root))
