import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_document_archive import audit, load_index, resolve_document


class DocumentArchiveTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'docs').mkdir()
        archive = root / 'local_archive/docs/old.md'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'historical document\n')
        row = {'original': 'docs/old.md', 'archived': 'local_archive/docs/old.md',
               'bytes': archive.stat().st_size, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
        (root / 'docs/archive_index.json').write_text(json.dumps({'entries': [row]}))
        return row

    def test_resolve_exact_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            self.assertEqual(resolve_document(root, row['original'], row['sha256']), root / row['archived'])

    def test_wrong_historical_hash_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'Historical hash mismatch'):
                resolve_document(root, row['original'], '0' * 64)

    def test_archive_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            (root / row['archived']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                load_index(root)

    def test_duplicate_and_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            p = root / 'docs/archive_index.json'
            p.write_text(json.dumps({'entries': [row, row]}))
            with self.assertRaises(ValueError):
                load_index(root)
            row['archived'] = '../outside'
            p.write_text(json.dumps({'entries': [row]}))
            with self.assertRaises(ValueError):
                load_index(root)

    def test_report_hashes_checked_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            report = root / 'reports'; report.mkdir()
            manifest = report / 'manifest.json'
            manifest.write_text(json.dumps({'inputs': [{'path': row['original'], 'sha256': row['sha256'], 'bytes': row['bytes']},
                                                       {'path': row['original'], 'sha256': '0' * 64}]}))
            before = manifest.read_bytes()
            result = audit(root)
            self.assertEqual(result['hash_check_counts'], {'exact_relocated': 1, 'preexisting_content_drift': 1})
            self.assertEqual(manifest.read_bytes(), before)
            self.assertFalse((root / row['original']).exists())

    def test_references_across_chunk_boundary_and_new_locator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); row = self.fixture(root)
            p = root / 'README.md'
            p.write_bytes(b'x ' * (524288 - 2) + row['original'].encode() + b'\n' + row['archived'].encode())
            result = audit(root)
            refs = [r for r in result['references'] if r['file'] == 'README.md']
            self.assertEqual(sum(r['occurrences'] for r in refs), 2)
            self.assertEqual({r['already_new_locator'] for r in refs}, {True, False})


if __name__ == '__main__':
    unittest.main()
