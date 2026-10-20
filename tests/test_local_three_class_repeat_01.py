"""Focused offline regressions; no fake output enters the real namespace."""
import json
import os
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
import local_three_class_repeat_01_entry as entry
import coding_measurement_volcano_01_entry as coding


class BatchTests(unittest.TestCase):
    def test_runner_status_contract_not_docops_archive_vocabulary(self):
        ok = dict(execution_status='ok', evaluation_status='ok', archive_status='ok', cleanup_status='ok')
        self.assertEqual(coding.exit_code_for(ok), 0)
        for field, value in [('archive_status','failed'), ('archive_status','complete'),
                             ('execution_status','infra_failure'), ('evaluation_status','infra_failure'),
                             ('cleanup_status','unconfirmed'), ('execution_status','unknown')]:
            self.assertNotEqual(coding.exit_code_for({**ok,field:value}), 0)
        self.assertNotEqual(coding.exit_code_for({}), 0)

    def test_exact_order_task_round_identity_and_full_budget(self):
        rows = entry.schedule()
        self.assertEqual(len(rows), 27)
        self.assertEqual([r['sequence'] for r in rows], list(range(27)))
        self.assertEqual(len({(r['chain'],r['task'],r['round']) for r in rows}), 27)
        for chain in entry.TASKS:
            tasks = entry.TASKS[chain]
            self.assertEqual([r['task'] for r in rows if r['chain']==chain],
                             [tasks[i] for i in (0,1,2,1,2,0,2,0,1)])
        self.assertEqual(entry.TOTAL, 14*3600)
        self.assertEqual(entry.CAPS, {'Coding':1800,'Office':2700,'Assistant':480})

    def test_plan_is_read_only_and_approval_is_not_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = {'entry': {'path':'test.py','bytes':1,'sha256':entry.hashlib.sha256(b'x').hexdigest()}}
            (root/'test.py').write_bytes(b'x')
            frozen = {'identity':identity,'identity_sha256':entry.digest(identity)}
            for name in ('plan-identity.json','frozen-identity.json'):
                entry.write(entry.ENV/name, frozen, root)
            entry.write(entry.REPORT/'APPROVAL.json', {'synthetic':True}, root)
            before = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(entry,'inspect',side_effect=AssertionError('Docker forbidden')), \
                 patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
                self.assertTrue(entry.plan(root)['namespace_clean'])
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            entry.write(entry.REPORT/'ATTEMPT_STARTED.json', {}, root)
            self.assertFalse(entry.plan(root)['namespace_clean'])
            (root/'test.py').write_bytes(b'y')
            with self.assertRaisesRegex(ValueError,'drift'):
                entry.plan(root)

    def test_raw_manifest_file_set_and_hash_refuse_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a.json').write_text('{}')
            entry.write(Path('manifest.json'), {'outputs':[entry.record('a.json',root)]},root)
            self.assertEqual(entry.verify_raw(root,'Office'),1)
            (root/'a.json').write_text('null')
            with self.assertRaisesRegex(ValueError,'hash'):
                entry.verify_raw(root,'Office')

    def test_class_failure_and_global_cleanup_stop_are_distinct(self):
        report={'summary':{'outcome':{'infra_failures':[]}},'exit_code':0,
                'removal_verified':'removed','image_retention_verified':True}
        self.assertEqual(entry.adjudicate('Office',report,True),(False,False,None))
        self.assertEqual(entry.adjudicate('Office',{**report,'image_retention_verified':False},True)[:2],(True,False))
        self.assertEqual(entry.adjudicate('Office',{**report,'removal_verified':'unknown'},True)[:2],(True,True))
        self.assertEqual(entry.adjudicate('Office',report,False)[:2],(True,False))

    def test_measurement_gate_uses_production_interval_scope_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            entry.write(Path('supplemental_measurements.json'),{
                'network':{'samples':[{},{}]},
                'container_disk_footprints':{'submission':{'footprint':{'status':'complete'}}}},root)
            valid=[{'metrics':{'cpu':{'status':'valid'}}}]
            report={'summary':{'measurement':{'call_timing_status':'complete',
                    'resource_intervals':{'container':valid,'host_agent_process':valid}}}}
            self.assertEqual(entry.key_measurements(root,'Office',report),[])
            report['summary']['measurement']['resource_intervals']['host_agent_process']=[]
            self.assertEqual(entry.key_measurements(root,'Office',report),['host_agent_process_cpu_intervals_missing'])

    def test_new_office_projection_reaches_real_lifecycle_and_final_manifest(self):
        import docops_office_repeat_01_entry as office
        from tests.test_docops_measurement_validate_01_entry import external_boundaries
        old=json.loads((ROOT/'env/docops-office-repeat-01/frozen-identity.json').read_text())['identity']
        task=next(t for t in old['tasks'] if t['key']==entry.TASKS['Office'][0])
        cfg=office.run_config(task['key'],0,task['image_ref'],task['image_id'],collection=entry.COLLECTION)
        comp={'tasks':[task],'code_and_runtime_files':[], 'run_configs':{task['key']:cfg}}
        frozen={'identity':{'components':{'Office':comp}},'identity_sha256':'a'*64}
        slot=entry.schedule()[9]
        with tempfile.TemporaryDirectory() as tmp, external_boundaries(self) as (transport, runtime, calls, saved, _), \
             patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
            root=Path(tmp);(root/entry.ENTRY).parent.mkdir(parents=True)
            (root/entry.ENTRY).write_bytes((ROOT/entry.ENTRY).read_bytes())
            with patch.object(entry,'ROOT',root):
                report=entry.office_run(slot,frozen,'fixture-office',time.monotonic()+1000)
            self.assertEqual(report['exit_code'],0,report['summary']['outcome'])
            self.assertEqual(report['removal_verified'],'removed')
            self.assertTrue(report['image_retention_verified'])
            self.assertEqual(len(calls),2)
            self.assertTrue(saved)
            self.assertIn('verify_removal',transport.order)
            self.assertFalse(any('--rmi' in str(x) for x in transport.order))
            self.assertGreater(entry.verify_raw(root/entry.RAW/'fixture-office','Office'),5)


if __name__=='__main__':
    unittest.main()
