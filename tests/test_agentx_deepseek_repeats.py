import unittest

from scripts.agentx_deepseek_repeat_analysis import paired_changes, run_ranges, METRICS


def observations():
    return [{'case':case,'node_id':f'n{i}','index':i,'replicate':r,'body_sha256':f'{case}{i}',
             'source_pointer':f'/{case}/{i}','source_request_sha256':f'source-{case}-{i}',
             'first_content_s':float(i+r),'remote_completion_tokens':i+r,'cache_hit_tokens':10*r}
            for case in ['baseline','multiple_subagents'] for i in range(2) for r in [1,2,3]]


class RepeatAnalysisTests(unittest.TestCase):
    def test_pairing_uses_identity_not_completion_order(self):
        rows=observations(); expected=paired_changes(rows)
        self.assertEqual(paired_changes(list(reversed(rows))),expected)
        self.assertEqual(len(expected),8)
        self.assertTrue(all(q['first_content_change_s']==q['replicate']-1 for q in expected))

    def test_same_node_names_in_different_cases_stay_separate(self):
        rows=observations()
        for q in rows:
            if q['case']=='multiple_subagents':q['first_content_s']+=q['replicate']*10
        pairs=paired_changes(rows)
        self.assertEqual({q['first_content_change_s'] for q in pairs if q['case']=='baseline'},{1.,2.})
        self.assertEqual({q['first_content_change_s'] for q in pairs if q['case']=='multiple_subagents'},{11.,22.})

    def test_missing_and_duplicate_observations_are_not_silent(self):
        rows=observations()
        for changed in [rows[:-1],rows+[rows[0]]]:
            with self.assertRaises(ValueError):paired_changes(changed)

    def test_pairing_rejects_changed_body_source_or_pointer(self):
        for field in ['body_sha256','source_pointer','source_request_sha256']:
            rows=observations(); rows[1][field]='changed'
            with self.assertRaises(ValueError):paired_changes(rows)

    def test_ranges_are_run_level_and_case_specific(self):
        metrics=[{'case':case,'replicate':r,**{k:offset+v for k in METRICS}}
                 for case,offset in [('baseline',0),('multiple_subagents',100)] for r,v in [(1,9),(2,2),(3,4)]]
        output=run_ranges(list(reversed(metrics)))
        base=next(q for q in output if q['case']=='baseline' and q['metric']=='wall_s')
        self.assertEqual((base['n_runs'],base['min'],base['max'],base['median']),(3,2,9,4))
        other=next(q for q in output if q['case']=='multiple_subagents' and q['metric']=='wall_s')
        self.assertEqual(other['min'],102)
        self.assertEqual(other['max'],109)
        self.assertNotIn('confidence_interval',base)
        for changed in [metrics[:-1],metrics+[metrics[0]]]:
            with self.assertRaises(ValueError):run_ranges(changed)


if __name__=='__main__':unittest.main()
