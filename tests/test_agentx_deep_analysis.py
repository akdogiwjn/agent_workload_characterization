"""Completion, namespace, radix, timing and presentation-contract regressions."""
import json
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from scripts.agentx_deep_analysis import (
    BUDGETS, PrefixHistory, group_audit, lcp, native_records, overlap_profile,
    progress_rows, reuse_metrics, run, scan,
)
from scripts.agentx_deep_presentation import write_pptx


def event(blocks, start=0, duration=1, scope='', model='m', pointer=None, order=0):
    return {'blocks': np.array(blocks,dtype=np.int64), 't':start,'end':start+duration,
            'scope':scope,'model':model,'pointer':pointer or f'/requests/{order}',
            'input':len(blocks)*64,'output':1,'api_time':duration,'order':order,
            'kind':'subagent' if scope else 'main','source_line':1,'keep_256k':True}


class DeepTests(unittest.TestCase):
    def test_radix_handles_splits_shorter_prefixes_and_exact_matches(self):
        history=PrefixHistory()
        for i, row in enumerate([[1,2,3,4],[1,2,8],[1],[9,4],[1,2,3,4,5]]):
            history.add(np.array(row),i)
        for row,want in [([1,2,3,9],3),([1,2],2),([1,8],1),([9,4,5],2),([8],0),([],0),([1,2,3,4,5],5)]:
            got,witness=history.query(np.array(row));self.assertEqual(got,want)
            self.assertEqual(witness is None,want==0)

    def test_radix_against_exhaustive_random_prefix_search_with_witness(self):
        rng=random.Random(712);history=PrefixHistory();saved=[]
        for i in range(300):
            q=np.array([rng.randrange(4) for _ in range(rng.randrange(1,15))])
            got,witness=history.query(q)
            expected=max((lcp(q,a) for a in saved),default=0)
            self.assertEqual(got,expected)
            if got:self.assertGreaterEqual(lcp(q,saved[witness]),got)
            history.add(q,i);saved.append(q)

    def test_inflight_future_and_current_request_are_not_reuse_candidates(self):
        rows=[event([1,2,3],0,10,order=0),event([1,2,4],1,1,order=1),
              event([1,2,3],3,1,order=2)]
        reuse_metrics(rows)
        self.assertEqual([r['history_tokens'] for r in rows],[0,0,128])
        self.assertEqual(rows[2]['reuse_witness_pointer'],'/requests/1')

    def test_completed_at_exact_start_is_eligible_and_model_isolation_holds(self):
        rows=[event([1,2],0,1,order=0),event([1,2],1,1,model='other',order=1),
              event([1,2],1,2,order=2)]
        reuse_metrics(rows)
        self.assertEqual([r['history_tokens'] for r in rows],[0,0,128])

    def test_cross_agent_extra_requires_finished_same_model_history(self):
        rows=[event([1,2,3],0,1,scope='a',order=0),event([1,2,3],2,1,scope='b',order=1)]
        reuse_metrics(rows)
        self.assertEqual(rows[1]['same_agent_history_tokens'],0)
        self.assertEqual(rows[1]['cross_agent_extra_tokens'],192)

    def test_latest_completed_is_not_latest_started(self):
        rows=[event([1,2,3],0,10,order=0),event([8,9],1,1,order=1),event([1,2,4],11,1,order=2)]
        reuse_metrics(rows)
        self.assertEqual(rows[-1]['latest_completed_prefix_tokens'],128)

    def test_sessions_have_independent_histories(self):
        a=[event([1,2],0,1)];b=[event([1,2],5,1)]
        reuse_metrics(a);reuse_metrics(b)
        self.assertEqual(b[0]['history_tokens'],0)

    def test_completion_history_matches_independent_exhaustive_oracle(self):
        rng=random.Random(907)
        rows=[event([1,2]+[rng.randrange(6) for _ in range(rng.randrange(1,9))],
                    start=rng.randrange(30),duration=rng.randrange(1,8),
                    model=rng.choice(['a','b']),scope=rng.choice(['','s1','s2']),order=i)
              for i in range(180)]
        reuse_metrics(rows)
        for row in rows:
            previous=[e for e in rows if e is not row and e['end']<=row['t'] and e['model']==row['model']]
            best=max((lcp(e['blocks'],row['blocks']) for e in previous),default=0)
            same=max((lcp(e['blocks'],row['blocks']) for e in previous if e['scope']==row['scope']),default=0)
            self.assertEqual(row['history_tokens'],best*64)
            self.assertEqual(row['same_agent_history_tokens'],same*64)

    def test_half_open_tie_and_overlap_area(self):
        rows=[event([1],0,2),event([2],2,2,scope='a'),event([3],1,2,scope='b')]
        result,_=overlap_profile(rows)
        self.assertEqual(result['peak'],2)
        self.assertEqual(result['busy_s'],4)
        self.assertEqual(result['multi_request_s'],2)
        self.assertEqual(result['api_interval_sum_s'],6)

    def test_zero_duration_adds_no_busy_time_or_concurrency(self):
        result,_=overlap_profile([event([1],0,0)])
        self.assertEqual(result['peak'],0)
        self.assertIsNone(result['overlap_fraction_of_busy'])

    def test_progress_includes_last_request_in_last_bin_and_no_interpolation(self):
        rows=[event([1],order=0),event([1,2],order=1),event([1],order=2)]
        bins=progress_rows(rows,'x','full')
        self.assertEqual([r['bin'] for r in bins],[0,10,19])
        self.assertEqual(rows[-1]['adjacent_input_delta'],-64)

    def test_native_nested_timestamps_not_offset_and_hash_metadata_checked(self):
        q={'type':'s','t':12,'api_time':1,'in':64,'out':1,'model':'m','hash_ids':[1]}
        raw={'id':'x','block_size':64,'hash_id_scope':'local','requests':[
            {'type':'subagent','agent_id':'a','t':10,'duration_ms':4000,'requests':[q]}]}
        events,groups=native_records(raw,1)
        self.assertEqual(events[0]['t'],12)
        self.assertEqual(events[0]['pointer'],'/requests/0/requests/0')
        self.assertFalse(group_audit(events,groups,'x','full')[0]['child_start_before_marker'])
        raw['block_size']=32
        with self.assertRaises(ValueError):native_records(raw,1)

    def test_unknown_missing_nonfinite_or_bad_hash_input_is_rejected(self):
        q={'type':'s','t':0,'api_time':1,'in':64,'out':1,'model':'m','hash_ids':[1]}
        for patch in [{'type':'tool'}, {'t':float('nan')},{'api_time':-1},{'in':128},{'hash_ids':[True]}]:
            raw={'id':'x','block_size':64,'hash_id_scope':'local','requests':[{**q,**patch}]}
            with self.assertRaises(ValueError):native_records(raw,1)

    def test_small_scan_totals_budget_cold_start_and_trace_ledgers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            requests=[{'type':'s','t':t,'api_time':1,'in':64*len(h),'out':1,'model':'m','hash_ids':h}
                      for t,h in [(0,[1,2]),(2,[1,2,3]),(4,[1,2,4])]]
            source=p/'source.jsonl';source.write_text(json.dumps({'id':'x','block_size':64,'hash_id_scope':'local','requests':requests})+'\n')
            summary,rows,_,_,_,_=scan(source,'fixture',p)
            self.assertEqual(summary['totals']['all:input'],512)
            self.assertEqual(summary['totals']['all:history_tokens'],256)
            self.assertEqual(summary['totals'][f'all:budget_{BUDGETS[0]}_tokens'],256)
            ledger=[json.loads(l) for l in (p/'fixture_request_metrics.jsonl').read_text().splitlines()]
            self.assertEqual(len(ledger),3)
            self.assertNotIn('blocks',ledger[0])
            self.assertEqual(rows[0]['above_256k_requests'],0)

    def test_capacity_model_clips_prefix_and_keeps_cold_request_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);blocks=list(range(2048))
            requests=[{'type':'s','t':t,'api_time':1,'in':131072,'out':1,'model':'m','hash_ids':blocks}
                      for t in [0,2]]
            source=p/'source.jsonl';source.write_text(json.dumps({'id':'x','block_size':64,'hash_id_scope':'local','requests':requests})+'\n')
            summary,*_=scan(source,'fixture',p)
            self.assertEqual(summary['totals']['all:input'],262144)
            self.assertEqual(summary['totals']['all:budget_32768_tokens'],32768)
            self.assertEqual(summary['totals']['all:budget_131072_tokens'],131072)

    def test_existing_output_is_rejected_before_input_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):run(Path(tmp))

    def test_powerpoint_zip_xml_relationships_and_widescreen_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); image=p/'image.png'; image.write_bytes(b'test-png-placeholder')
            target=p/'slides.pptx';write_pptx(target,[{'heading':'中文 & test','image':image}])
            with zipfile.ZipFile(target) as z:
                for name in z.namelist():
                    if name.endswith(('.xml','.rels')):ET.fromstring(z.read(name))
                root=ET.fromstring(z.read('ppt/presentation.xml'))
                ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
                size=root.find('p:sldSz',ns)
                self.assertAlmostEqual(int(size.attrib['cx'])/int(size.attrib['cy']),16/9)
                self.assertEqual(len(root.findall('p:sldIdLst/p:sldId',ns)),1)
                self.assertIn('中文 &amp; test',z.read('ppt/slides/slide1.xml').decode())


if __name__=='__main__':unittest.main()
