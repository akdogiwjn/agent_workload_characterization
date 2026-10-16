import hashlib, json, tempfile, unittest
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('osworld_task_behavior',ROOT/'scripts/osworld_task_behavior.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class OSWorldTaskBehaviorTests(unittest.TestCase):
    def base(self, models=('MiniMax-M3',)):
        td=tempfile.TemporaryDirectory(); b=Path(td.name); traj=b/'traj'; meta=b/'meta'; tasks=b/'tasks'; tasks.mkdir()
        for model in models:
            d=traj/'website_demo'/model/'tasks'/'001'; d.mkdir(parents=True)
            rows=[{'step_num':1,'action':'pyautogui.click(1,2)','response':'x','reward':0,'done':False,'info':{}}, {'step_num':2,'action':'pyautogui.press("a")','response':'x','reward':1,'done':True,'info':{}}]
            if model=='Claude':
                rows=[{'step_num':1,'action':{'name':'computer','action_type':'tool_use','command':'pyautogui.sleep(0.1)','input':{'action':'screenshot'},'id':'x'},'done':False,'reward':0}, {'step_num':2,'action':{'name':'computer','action_type':'tool_use','command':'pyautogui.click(1,2)','input':{'action':'left_click','coordinate':[1,2]},'id':'y'},'done':True,'reward':1}]
            (d/'traj.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows)); (d/'result.txt').write_text('0\n')
            (meta/'website_demo'/model/'tasks'/'001').mkdir(parents=True); (meta/'website_demo'/model/'tasks'/'001'/'api_usage.json').write_text(json.dumps({'task_id':'001','call_count':1,'missing_usage_count':1,'numeric_totals':{},'calls':[{'call_number':1,'request_time':None,'response_time':None,'usage':None}]}))
        (tasks/'task_001.py').write_text('class Task001:\n id="001"\n instruction="Open browser and edit a file"\n related_apps=["chrome"]\n')
        files=[]
        for x in traj.rglob('*'):
            if x.is_file(): files.append({'path':str(x.relative_to(traj)),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()})
        inv=b/'inventory.json'; inv.write_text(json.dumps({'requested_revision':mod.REVISION,'files':files})); return td,traj,meta,tasks,inv

    def test_actual_entry_multimodel_and_manifest(self):
        td,tr,meta,tasks,inv=self.base(('MiniMax-M3','Claude'))
        try:
            out=Path(td.name)/'out'; s=mod.run(tr,meta,tasks,inv,out)
            self.assertEqual(s['inputs']['trajectory_count'],2)
            rows=[json.loads(x) for x in (out/'per_trajectory.jsonl').read_text().splitlines()]
            claude=next(x for x in rows if x['model']=='Claude')
            self.assertEqual(claude['native_action_category_counts']['screenshot'],1)
            self.assertEqual(claude['native_action_category_counts']['click'],1)
            self.assertEqual(claude['static_category_counts']['wait'],1)
            self.assertEqual(claude['native_source_conflicts']['native_screenshot_command_placeholder_wait'],1)
            self.assertTrue((out/'manifest.json').exists())
        finally: td.cleanup()

    def test_native_and_command_are_separate_and_unknown_is_boundary(self):
        self.assertEqual(mod.action_sources({'input':{'action':'screenshot'},'command':'pyautogui.sleep(1)'})['source_conflict'],'native_screenshot_command_placeholder_wait')
        x=mod.action_sources({'input':{'action':'left_click'},'command':'unknown_call()'})
        self.assertEqual(x['native_category'],'click'); self.assertEqual(x['command'],'unknown_call()')

    def test_task_class_selection_and_label_false_positives(self):
        root=ROOT/'data/raw/public/osworld2_tasks/v2026.06.24'
        row=mod.task_semantics(root/'task_080.py'); self.assertEqual(row['task_class'],'Task080'); self.assertEqual(row['task_id'],'080'); self.assertIsInstance(row['instruction'],str) if 'instruction' in row else None
        for key in ('092','096'):
            row=mod.task_semantics(root/f'task_{key}.py'); self.assertNotIn('development_terminal',row['labels'])

    def test_usage_validation_and_none_times(self):
        td=tempfile.TemporaryDirectory(); p=Path(td.name)/'meta/website_demo/MiniMax-M3/tasks/001'; p.mkdir(parents=True)
        data={'task_id':'001','call_count':2,'missing_usage_count':1,'numeric_totals':{},'calls':[{'call_number':1,'request_time':None,'response_time':None,'usage':None},{'call_number':1,'request_time':1,'response_time':1,'usage':{'input_tokens':2,'output_tokens':3,'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}]}
        (p/'api_usage.json').write_text(json.dumps(data)); rows,s=mod.api_summary(Path(td.name)/'meta',['001'])
        self.assertEqual(s['request_equal_count_valid'],1); self.assertEqual(s['validation_counts'].get('call_count_mismatch',0),0); self.assertEqual(s['validation_counts']['duplicate_call_number'],1); self.assertEqual(s['calls_usage_missing_count_sum'],1)
        td.cleanup()

    def test_inventory_missing_registered_file_rejected(self):
        td,tr,meta,tasks,inv=self.base()
        try:
            x=json.loads(inv.read_text()); target=tr/'website_demo/MiniMax-M3/tasks/001/traj.jsonl'; target.unlink()
            with self.assertRaises(Exception): mod.run(tr,meta,tasks,inv,Path(td.name)/'out')
        finally: td.cleanup()

    def test_native_unknown_is_a_boundary_in_actual_analyze_task(self):
        td,tr,meta,tasks,inv=self.base(("Claude",))
        try:
            d=tr/'website_demo/Claude/tasks/001'
            rows=[{'step_num':1,'action':{'action_type':'tool_use','input':{'action':'left_click'},'command':'pyautogui.click(1,2)'},'done':False}, {'step_num':2,'action':{'action_type':'tool_use','input':{'action':'mystery'},'command':'unknown()'},'done':False}, {'step_num':3,'action':{'action_type':'tool_use','input':{'action':'left_click'},'command':'pyautogui.click(2,2)'},'done':True}]
            (d/'traj.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
            row=mod.analyze_task(d,tr)
            self.assertEqual(row['native_sequence']['transition_counts'],{})
            self.assertEqual(row['native_sequence']['segment_counts'],{'click':2})
            self.assertEqual(row['native_action_category_counts']['unknown'],1)
        finally: td.cleanup()

    def test_input_cache_formula_and_missing_denominators(self):
        td=tempfile.TemporaryDirectory(); p=Path(td.name)/'meta/website_demo/MiniMax-M3/tasks/001'; p.mkdir(parents=True)
        data={'task_id':'001','call_count':3,'missing_usage_count':1,'numeric_totals':{'input_tokens':7,'output_tokens':1000,'cache_read_input_tokens':3,'cache_creation_input_tokens':5,'input_tokens_including_cache':15},'calls':[{'call_number':1,'request_time':1,'response_time':2,'usage':{'input_tokens':2,'output_tokens':100,'cache_read_input_tokens':3,'cache_creation_input_tokens':5}},{'call_number':2,'request_time':1,'response_time':2,'usage':{'input_tokens':5,'output_tokens':900,'cache_read_input_tokens':None,'cache_creation_input_tokens':0}},{'call_number':3,'request_time':1,'response_time':2,'usage':{'input_tokens':0,'output_tokens':None,'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}]}
        (p/'api_usage.json').write_text(json.dumps(data))
        try:
            rows,summary=mod.api_summary(Path(td.name)/'meta',['001']); u=summary['request_level_field_stats']
            self.assertEqual(u['input_tokens']['n'],3); self.assertEqual(u['input_tokens']['missing'],0)
            self.assertEqual(u['input_tokens_including_cache_derived']['n'],2); self.assertEqual(u['input_tokens_including_cache_derived']['missing'],1)
            self.assertIsNone(rows[0]['numeric_total_comparison']['input_tokens_including_cache']['recomputed'])
            self.assertEqual(rows[0]['numeric_total_comparison']['input_tokens_including_cache']['status'],'partial_or_mismatch')
        finally: td.cleanup()

    def test_version_evidence_is_consumed_by_complete_entry(self):
        td,tr,meta,tasks,inv=self.base()
        try:
            out=Path(td.name)/'out'; s=mod.run(tr,meta,tasks,inv,out)
            self.assertEqual(s['inputs']['task_version_evidence']['status'],'unknown')
            self.assertIn('scripts/osworld_minimax_behavior.py', [x['path'] for x in json.loads((out/'manifest.json').read_text())['analysis_code']])
        finally: td.cleanup()

    def test_task_unknown_constant_is_partial_not_executed(self):
        td=tempfile.TemporaryDirectory(); p=Path(td.name)/'task_999.py'; p.write_text('class Task999:\n id="999"\n instruction=unknown_call()\n')
        row=mod.task_semantics(p); self.assertEqual(row['parse_status'],'partial'); self.assertEqual(row['task_id'],'999'); td.cleanup()

if __name__=='__main__': unittest.main()
