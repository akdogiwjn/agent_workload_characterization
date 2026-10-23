import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import swebench_coverage_results as mod


class ResultSemanticsTests(unittest.TestCase):
    def test_nonmembership_does_not_mean_failure(self):
        members,_,issues=mod.parse_results(json.dumps({'resolved':['r__r-1'],'no_logs':['r__r-2']}).encode())
        self.assertEqual(issues,[])
        self.assertTrue(mod.result_link('r__r-1',members,True)['reported_resolved'])
        absent=mod.result_link('r__r-3',members,True)
        self.assertEqual(absent['status'],'not_listed_in_saved_fields')
        self.assertIsNone(absent['reported_resolved'])
        self.assertEqual(mod.result_link('r__r-2',members,True)['status'],'listed_other_saved_fields')
        self.assertIsNone(mod.result_link('r__r-2',members,True)['reported_resolved'])

    def test_conflicts_duplicates_and_explicit_unresolved_are_distinct(self):
        members,fields,_=mod.parse_results(json.dumps({'resolved':['r__r-1']*2,'no_generation':['r__r-1'],'unresolved':['r__r-2']}).encode())
        self.assertEqual(fields['resolved']['duplicate_entries'],1)
        self.assertEqual(mod.result_link('r__r-1',members,True)['status'],'conflicting_saved_memberships')
        self.assertIsNone(mod.result_link('r__r-1',members,True)['reported_resolved'])
        self.assertIs(mod.result_link('r__r-2',members,True)['reported_resolved'],False)

    def test_bad_result_types_are_not_coerced_into_ids(self):
        members,_,problems=mod.parse_results(json.dumps({'resolved':{'r__r-1':True},'no_logs':['not-an-instance'],'other':['r__r-2']}).encode())
        self.assertEqual(members,{})
        self.assertEqual(len(problems),3)
        self.assertEqual(mod.result_link('metadata',members,True)['status'],'not_an_instance_identifier')
        self.assertEqual(mod.result_link('r__r-1',members,False)['status'],'evaluation_file_missing')

    def test_finished_and_submit_do_not_substitute_for_evaluation(self):
        note=mod.native_summary(json.dumps({'transitions':[{'name':'Finished'}],'info':{'submission':'patch'}}).encode(),'lite/20240617_moatless_gpt4o')
        self.assertEqual(note['last_saved_transition'],'Finished')
        self.assertIsNone(note['termination']['value'])
        note=mod.native_summary(json.dumps({'trajectory':[{'action':'submit'}],'info':{'exit_status':'submitted (exit_cost)'}}).encode(),'20240620_sweagent_claude3.5sonnet')
        self.assertEqual(note['explicit_submit_markers'],1)
        self.assertEqual(note['termination']['value'],'submitted (exit_cost)')

    def test_multiple_views_are_not_summed_as_one_attempt(self):
        rows=[{'group':'g','evaluation':{'status':'listed_resolved'},'behavior_rows':[{'unit_kind':'tool','unit_count':2},{'unit_kind':'tool','unit_count':3}]},
              {'group':'g','evaluation':{'status':'not_listed_in_saved_fields'},'behavior_rows':[{'unit_kind':'flow','unit_count':0}]}]
        strata,excluded=mod.strata_for_instances(rows)
        self.assertEqual(len(strata),1)
        self.assertEqual(strata[0]['saved_units_per_instance']['median'],0)
        self.assertEqual(excluded[0]['instances'],1)


class GapFinalizeTests(unittest.TestCase):
    def make_plan(self,root,bad_second=False):
        raw=root/'new_raw';raw.mkdir()
        old=root/'oldplan.json';old.write_text('{}')
        items=[]
        for i in range(2):
            path=raw/f'r__r-{i}.json';data=b'[]'
            Path(str(path)+'.part').write_bytes(data)
            header=root/f'{i}.headers'
            md5='0'*32 if bad_second and i==1 else hashlib.md5(data).hexdigest()
            header.write_text('HTTP/1.1 200 OK\nETag: "'+md5+'"\n')
            items.append({'path':str(path),'partial_path':str(path)+'.part','headers_path':str(header),
                          'bytes':2,'key':f'test/g/trajs/r__r-{i}.json','url':'https://example.invalid/public'})
        p=root/'plan.json';p.write_text(json.dumps({'old_plan':mod.file_record(old),'index_commit':mod.INDEX,'items':items}))
        return p,raw

    def test_live_etag_and_bytes_verified_before_sealing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,raw=self.make_plan(Path(tmp));m=mod.finalize_gap(p,raw)
            self.assertEqual(m['count'],2)
            self.assertTrue(all(Path(e['path']).exists() for e in m['files']))
            self.assertEqual(list(raw.glob('*.part')),[])

    def test_corruption_does_not_partially_seal_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,raw=self.make_plan(Path(tmp),bad_second=True)
            with self.assertRaisesRegex(ValueError,'ETag'):mod.finalize_gap(p,raw)
            self.assertEqual(len(list(raw.glob('*.part'))),2)
            self.assertFalse((p.parent/'manifest.json').exists())

    def test_destination_cannot_write_old_raw_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,raw=self.make_plan(Path(tmp))
            with self.assertRaisesRegex(ValueError,'outside new raw scope'):mod.finalize_gap(p,Path(tmp)/'other')


class EntryTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous=Path.cwd();os.chdir(tmp)
            try:
                base=Path('baseline');base.mkdir()
                original=[];behavior=[];registrations=[]
                groups=['20240620_sweagent_claude3.5sonnet','lite/20240617_moatless_gpt4o',mod.SONAR]
                selected=[]
                index=Path('data/raw/public/swebench_public_traces')/mod.INDEX/'experiments'
                for group in groups:
                    split,sub=mod.split_group(group)
                    path=index/group/'trajs/r__r-1.json';path.parent.mkdir(parents=True)
                    value=([{'role':'assistant','additional_kwargs':{'tool_calls':[{'id':'c','function':{'name':'bash','arguments':'{"command":"ls"}'}}]}}] if group==mod.SONAR else
                           {'transitions':[{'name':'Finished','actions':[]}],'info':{}} if split=='lite' else
                           {'trajectory':[{'action':'submit','observation':'saved'}],'info':{'exit_status':'submitted'}})
                    path.write_text(json.dumps(value));entry={**mod.file_record(path),'role':'trajectory'};registrations.append(entry)
                    parsed=mod.operations._analyze_swebench_bytes(str(path),group,path.read_bytes())
                    original.append({**entry,'group':group,'task':'r__r-1','status':parsed['status'],'reason_code':parsed['reason_code'],'unit_count':parsed['unit_count']})
                    for kind,units in parsed['units_by_kind']:
                        behavior.append(mod.operations.summarize_units('SWE-bench',group,'r__r-1',{'path':str(path)},kind,units,parsed.get('returns',[])))
                    selected.append({'split':split,'submission':sub,'items':[{'task_id':'r__r-1','file':str(path)}]})
                    ev=index/'evaluation'/split/sub/'results/results.json';ev.parent.mkdir(parents=True)
                    ev.write_text(json.dumps({'resolved':['r__r-1'] if split=='verified' else [],'no_logs':['r__r-1'] if split=='lite' else []}))
                    registrations.append({**mod.file_record(ev),'role':'experiments_index'})
                for name,value in [('coverage.json',{'objects':original}),('summary.json',{})]: (base/name).write_text(json.dumps(value))
                (base/'per_trajectory.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in behavior))
                codes=[]
                for name in ['scripts/public_trace_operations.py','src/agent_workload_characterization/analyzers/public_operations.py']:
                    p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((mod.ROOT/name).read_bytes());codes.append(mod.file_record(p))
                (base/'manifest.json').write_text(json.dumps({'inputs':codes,'outputs':[mod.file_record(base/n) for n in ['coverage.json','summary.json','per_trajectory.jsonl']]}))
                for i,name in enumerate(mod.ACQUISITIONS):
                    p=Path('data/catalog/public_trace_acquisition')/name/'manifest.json';p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_text(json.dumps({'inputs':registrations if i==0 else []}))
                sel=Path('reports/analysis/SWEBENCH-subset-behavior-v1/selection.json');sel.parent.mkdir(parents=True)
                sel.write_text(json.dumps({'groups':selected}))
                (sel.parent/'manifest.json').write_text(json.dumps({'outputs':[mod.file_record(sel)]}))
                added=Path('data/raw/public/swebench_gap/test/g/trajs/r__r-2.json');added.parent.mkdir(parents=True)
                added.write_text(json.dumps([{'role':'assistant','additional_kwargs':{'tool_calls':[{'id':'c2','function':{'name':'bash','arguments':'{"command":"ls"}'}}]}}]))
                acq=Path('gap-manifest.json');acq.write_text(json.dumps({'index_commit':mod.INDEX,'files':[{**mod.file_record(added),'group':mod.SONAR,'task':'r__r-2'}]}))
                for name in ['scripts/swebench_coverage_results.py','tests/test_swebench_coverage_results.py']:
                    p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((mod.ROOT/name).read_bytes())
                yield base,acq,Path('new-report')
            finally:os.chdir(previous)

    def test_complete_entry_exact_group_link_and_unchanged_frozen_inputs(self):
        with self.fixture() as (base,acq,out):
            original=(base/'coverage.json').read_bytes()
            s=mod.run(base,acq,out)
            self.assertEqual(s['objects'],4)
            self.assertEqual(s['evaluation_groups_available'],3)
            self.assertEqual(s['groups_summary']['20240620_sweagent_claude3.5sonnet']['evaluation_status_instances'],{'listed_resolved':1})
            self.assertEqual(s['groups_summary']['lite/20240617_moatless_gpt4o']['evaluation_status_instances'],{'listed_other_saved_fields':1})
            self.assertEqual(s['groups_summary'][mod.SONAR]['evaluation_status_instances'],{'not_listed_in_saved_fields':2})
            self.assertEqual((base/'coverage.json').read_bytes(),original)
            self.assertEqual(s['independent_task_keys'],2)
            self.assertTrue((out/'manifest.json').exists())
            with self.assertRaises(FileExistsError):mod.run(base,acq,out)

    def test_changed_frozen_object_fails_before_output(self):
        with self.fixture() as (base,acq,out):
            d=json.loads((base/'coverage.json').read_text());Path(d['objects'][0]['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'frozen file mismatch'):mod.run(base,acq,out)
            self.assertFalse(out.exists())

    def test_cross_revision_gap_is_rejected(self):
        with self.fixture() as (base,acq,out):
            data=json.loads(acq.read_text());data['index_commit']='different';acq.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'index revision differs'):mod.run(base,acq,out)
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
