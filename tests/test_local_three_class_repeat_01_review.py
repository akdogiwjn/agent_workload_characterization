"""Small saved-evidence fixtures through the complete analysis/chart entry."""
import csv
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import local_three_class_repeat_01_review as review
from tests.test_volcano_three_chain_characterization import fixture as previous_fixture,tree


def write(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj))


def fixture(root,scale=1):
    old=root/'source_fixture';previous_fixture(old,cpu_scale=scale)
    b=review.batch
    (root/'synthetic-interpreter-bytes').write_bytes(b'fixture, never executed')
    (root/'interpreter-link').symlink_to('synthetic-interpreter-bytes')
    ident={'collection':b.COLLECTION,'schedule':b.schedule(),'test':'synthetic evidence only',
           'interpreter':b.record('interpreter-link',root)}
    digest=b.digest(ident);frozen={'identity':ident,'identity_sha256':digest}
    for n in ('plan-identity.json','frozen-identity.json'):write(root/b.ENV/n,frozen)
    write(root/b.ENV/'history-before.json',{})
    write(root/b.REPORT/'APPROVAL.json',{'identity_sha256':digest,'scope':b.schedule()})
    runs=[]
    specs={x[0]:x for x in review.base.RUNS}
    for slot in b.schedule():
        chain=slot['chain'];spec=specs[chain];run_id=f'fixture-{slot["sequence"]:02d}'
        raw=root/b.RAW/run_id;shutil.copytree(old/'data/raw/generated'/spec[1]/spec[2],raw)
        def replace(obj):
            if isinstance(obj,dict):
                return {k:digest if k=='identity_sha256' else run_id if k=='run_id' else replace(v) for k,v in obj.items()}
            if isinstance(obj,list):return [replace(v) for v in obj]
            return obj
        for p in raw.rglob('*.json'):
            if p.name!='manifest.json':write(p,replace(json.loads(p.read_text())))
        marker={'run_id':run_id,'identity_sha256':digest,'started_at_monotonic_ns':1_000_000_000}
        write(raw/'ATTEMPT_STARTED.json',marker)
        entries=[b.record(p.relative_to(raw),raw) for p in sorted(raw.rglob('*')) if p.is_file() and p.name!='manifest.json']
        doc={'files':{x['path']:x['sha256'] for x in entries}} if chain=='Coding' else {'identity_sha256':digest,'outputs' if chain=='Office' else 'files':entries}
        write(raw/'manifest.json',doc)
        rp=b.REPORT/run_id/'run-report.json'
        report=replace(json.loads((old/'reports/resource'/spec[1]/'run-report.json').read_text()))
        write(root/rp,report);write(root/rp.parent/'ATTEMPT_STARTED.json',marker)
        runs.append({**slot,'run_id':run_id,'status':'executed','returncode':0,'archive_verified':True,
                     'raw_path':str(b.RAW/run_id),'report_path':str(rp),'measurement_gaps':[]})
    summary={'identity_sha256':digest,'counts':{'executed':27,'failed':0,'not_executed':0},
             'runs':runs,'wall_s':99,'class_stops':{},'global_stop':None}
    write(root/b.REPORT/'batch-summary.json',summary)
    outputs=[b.record(p.relative_to(root),root) for p in sorted((root/b.REPORT).rglob('*')) if p.is_file()]
    write(root/b.REPORT/'manifest.json',{'inputs':[],'raw_manifests':[], 'outputs':outputs})


class ReviewTests(unittest.TestCase):
    def test_complete_entry_27_slots_csv_svg_task_statistics_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';fixture(root);before=tree(root);out=Path(tmp)/'analysis'
            with patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
                s=review.build(root,out)
            self.assertEqual(len(s['runs']),27);self.assertEqual(len(s['tasks']),9)
            self.assertEqual(before,tree(root))
            for t in s['tasks']:
                self.assertEqual(t['actual_n'],3);self.assertEqual(t['metrics']['attempt_wall_s']['n'],3)
                ET.parse(out/t['small_multiples_figure']);ET.parse(out/t['distribution_figure'])
            for r in s['runs']:
                ET.parse(out/r['figure'])
                self.assertIn('class="data"',(out/r['figure']).read_text())
                with (out/r['series_csv']).open() as f:self.assertTrue(list(csv.DictReader(f)))
            m=json.loads((out/'manifest.json').read_text())
            self.assertNotIn('manifest.json',[r['path'] for r in m['outputs']])
            for r in m['outputs']:self.assertEqual(review.base.file_record(out/r['path'],out),r)

    def test_changed_input_changes_cpu_summary_and_hash_conflict_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root1=Path(tmp)/'one';root2=Path(tmp)/'two';fixture(root1,1);fixture(root2,2)
            a=review.build(root1,Path(tmp)/'a');b=review.build(root2,Path(tmp)/'b')
            self.assertEqual(b['runs'][9]['metrics']['main_scope_cpu_s'],2*a['runs'][9]['metrics']['main_scope_cpu_s'])
            p=root1/review.batch.RAW/'fixture-09'/'summary.json';p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'mismatch'):
                review.build(root1,Path(tmp)/'bad')

    def test_quantile_missing_and_scope_denominators(self):
        d=review.distribution([1,None,3,9])
        self.assertEqual((d['n'],d['median'],d['q1'],d['q3'],d['iqr']),(3,3,2,6,4))
        self.assertIsNone(review.distribution([None])['median'])


if __name__=='__main__':unittest.main()
