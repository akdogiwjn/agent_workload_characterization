"""Concurrent-write rejection, exact snapshots and unrelated-entry preservation."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_project_state import PAGES, check, render
from scripts.update_project_state import apply, digest, merge_dict, snapshot


class StateUpdateTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'docs').mkdir()
            state={'schema':'fixture','updated_at':'2026-10-23',
                   'execution_authorization':'none_this_state_is_not_an_approval',
                   'completed_limited_deliverables':{'other_task':{'keep':True}},
                   'public_summary':['existing task summary'],'evidence':[]}
            for page in PAGES:
                content=('before\n'+render(state,page)+'\nafter\n').encode()
                (root/page).write_bytes(content)
                state['evidence'].append({'path':page,'sha256':digest(content)})
            (root/'project_state.json').write_text(json.dumps(state)+'\n')
            yield root

    def test_snapshot_saves_exact_state_and_three_pages(self):
        with self.fixture() as root:
            result=snapshot(root);saved=Path(result['snapshot'])
            for p in ['project_state.json',*PAGES]:
                self.assertEqual((saved/p).read_bytes(),(root/p).read_bytes())
            self.assertFalse(result['execution_authorized'])

    def test_apply_preserves_other_tasks_and_takes_before_snapshot(self):
        with self.fixture() as root:
            before=(root/'project_state.json').read_bytes()
            result=apply(root,{'completed_limited_deliverables':{'this_task':{'status':'done'}}},digest(before),['new task summary'])
            state=json.loads((root/'project_state.json').read_text())
            self.assertEqual(state['completed_limited_deliverables']['other_task'],{'keep':True})
            self.assertEqual(state['completed_limited_deliverables']['this_task'],{'status':'done'})
            self.assertEqual(state['public_summary'],['existing task summary','new task summary'])
            self.assertEqual((Path(result['snapshot'])/'project_state.json').read_bytes(),before)
            self.assertEqual(check(root),[])

    def test_stale_writer_cannot_overwrite_any_current_file(self):
        with self.fixture() as root:
            before={p:(root/p).read_bytes() for p in ['project_state.json',*PAGES]}
            with self.assertRaisesRegex(ValueError,'stale'):
                apply(root,{'anything':'value'},'0'*64)
            for p,value in before.items():self.assertEqual((root/p).read_bytes(),value)

    def test_dictionary_to_scalar_replacement_is_rejected(self):
        with self.assertRaises(ValueError):merge_dict({'tasks':{'other':1}},{'tasks':None})

    def test_authorization_evidence_and_summary_cannot_be_blanket_replaced(self):
        with self.fixture() as root:
            current=digest((root/'project_state.json').read_bytes())
            for forbidden in ['execution_authorization','evidence','public_summary']:
                with self.assertRaises(ValueError):apply(root,{forbidden:[]},current)

    def test_hash_drift_is_not_silently_refreshed(self):
        with self.fixture() as root:
            p=root/'evidence.txt';p.write_text('original')
            s=json.loads((root/'project_state.json').read_text())
            s['evidence'].append({'path':'evidence.txt','sha256':digest(p.read_bytes())})
            (root/'project_state.json').write_text(json.dumps(s));p.write_text('changed')
            before=(root/'project_state.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'evidence mismatch'):
                apply(root,{},digest(before))
            self.assertEqual((root/'project_state.json').read_bytes(),before)

    def test_named_current_evidence_can_be_refreshed(self):
        with self.fixture() as root:
            (root/'current-note.md').write_text('new note')
            apply(root,{},digest((root/'project_state.json').read_bytes()),refresh_evidence=['current-note.md'])
            self.assertEqual(check(root),[])

    def test_intervening_external_writer_is_detected_after_snapshot(self):
        with self.fixture() as root:
            from scripts import update_project_state as module
            real=module.save_snapshot;before=(root/'project_state.json').read_bytes()
            def external_write(*args):
                saved=real(*args)
                (root/'project_state.json').write_text('{"external_task":"preserve me"}')
                return saved
            with patch.object(module,'save_snapshot',side_effect=external_write):
                with self.assertRaisesRegex(ValueError,'concurrent writer'):
                    apply(root,{'new_entry':'value'},digest(before))
            self.assertEqual(json.loads((root/'project_state.json').read_text()),{'external_task':'preserve me'})
            backups=list((root/'local_archive/project-state-snapshots').glob('*/project_state.json'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)

    def test_evidence_path_cannot_escape_repository(self):
        with self.fixture() as root:
            with self.assertRaises(ValueError):
                apply(root,{},digest((root/'project_state.json').read_bytes()),refresh_evidence=['../outside'])


if __name__=='__main__':unittest.main()
