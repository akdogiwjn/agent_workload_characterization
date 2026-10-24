"""Concurrent-write rejection, exact snapshots and unrelated-entry preservation."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_project_state import END, PAGES, START, check, render
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

    def add_evidence_record(self, root, name, sha256):
        state=json.loads((root/'project_state.json').read_text())
        state['evidence'].append({'path':name,'sha256':sha256})
        (root/'project_state.json').write_text(json.dumps(state)+'\n')

    def set_public_summary(self, root, lines):
        state=json.loads((root/'project_state.json').read_text())
        state['public_summary']=lines
        for page in PAGES:
            path=root/page;text=path.read_text()
            start=text.index(START);end=text.index(END)+len(END)
            updated=text[:start]+render(state,page)+text[end:]
            path.write_text(updated)
            row=next(item for item in state['evidence'] if item['path']==page)
            row.update(bytes=len(updated.encode()),sha256=digest(updated.encode()))
        (root/'project_state.json').write_text(json.dumps(state)+'\n')

    def state_and_pages(self, root):
        return {name:(root/name).read_bytes() for name in ['project_state.json',*PAGES]}

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

    def test_missing_historical_evidence_is_rejected_by_default_without_changes(self):
        with self.fixture() as root:
            missing='historical/missing.json'
            self.add_evidence_record(root,missing,digest(b'historical bytes'))
            before=self.state_and_pages(root)
            with self.assertRaises(FileNotFoundError):
                apply(root,{'new_task':{'status':'done'}},digest(before['project_state.json']))
            self.assertEqual(self.state_and_pages(root),before)

    def test_allow_missing_evidence_preserves_registration_and_reports_check_failure(self):
        with self.fixture() as root:
            missing='historical/missing.json';original_sha=digest(b'historical bytes')
            self.add_evidence_record(root,missing,original_sha)
            before=json.loads((root/'project_state.json').read_text())
            result=apply(root,{'new_task':{'status':'done'}},
                         digest((root/'project_state.json').read_bytes()),
                         allow_missing_evidence=True)
            self.assertEqual(result['status'],'UPDATED_WITH_MISSING_EVIDENCE')
            after=json.loads((root/'project_state.json').read_text())
            self.assertEqual(next(row for row in after['evidence'] if row['path']==missing),
                             {'path':missing,'sha256':original_sha})
            self.assertEqual(result['missing_evidence_preserved'],[missing])
            self.assertEqual(after['completed_limited_deliverables']['other_task'],
                             before['completed_limited_deliverables']['other_task'])
            self.assertTrue(any(missing in error for error in check(root)))

    def test_allow_missing_evidence_does_not_allow_existing_hash_mismatch(self):
        with self.fixture() as root:
            evidence=root/'historical/evidence.json';evidence.parent.mkdir()
            evidence.write_bytes(b'original bytes')
            self.add_evidence_record(root,'historical/evidence.json',digest(b'original bytes'))
            evidence.write_bytes(b'changed bytes')
            before=self.state_and_pages(root)
            with self.assertRaisesRegex(ValueError,'evidence mismatch'):
                apply(root,{'new_task':{'status':'done'}},digest(before['project_state.json']),
                      allow_missing_evidence=True)
            self.assertEqual(self.state_and_pages(root),before)
            self.assertEqual(evidence.read_bytes(),b'changed bytes')

    def test_replace_summary_replaces_only_exact_target_and_keeps_other_content(self):
        with self.fixture() as root:
            self.set_public_summary(root,['before target','target summary','after target'])
            before=json.loads((root/'project_state.json').read_text())
            apply(root,{},digest((root/'project_state.json').read_bytes()),
                  replace_summary=[('target summary','replacement summary')])
            after=json.loads((root/'project_state.json').read_text())
            self.assertEqual(after['public_summary'],
                             ['before target','replacement summary','after target'])
            self.assertEqual(after['completed_limited_deliverables'],
                             before['completed_limited_deliverables'])
            self.assertEqual(check(root),[])

    def test_unmatched_summary_replacement_is_rejected_without_changes(self):
        with self.fixture() as root:
            before=self.state_and_pages(root)
            with self.assertRaisesRegex(ValueError,'exactly one'):
                apply(root,{},digest(before['project_state.json']),
                      replace_summary=[('not present','replacement')])
            self.assertEqual(self.state_and_pages(root),before)


if __name__=='__main__':unittest.main()
