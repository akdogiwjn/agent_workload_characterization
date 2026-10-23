import unittest

from scripts.agentx_deepseek_five_repeat_analysis import verify_source_repetitions


class FiveRepeatCoverageTests(unittest.TestCase):
    def setUp(self):
        self.expected=[{'trace_id':'trace','source_outer_idx':4,'source_inner_idx':i,'source_request_sha256':f'hash-{i}'} for i in [None,0,1]]
        self.rows=[{**q,'replicate':r} for q in self.expected for r in [1,2,3]]

    def test_outer_and_inner_requests_are_distinct_sources(self):
        result=verify_source_repetitions(list(reversed(self.rows)),self.expected)
        self.assertEqual(result,{'unique_sources':3,'executions':9,'replicates_per_source':3,'unique_sessions':1})

    def test_correct_total_cannot_hide_three_copies_of_same_replicate(self):
        rows=[{**q,'replicate':1} for q in self.rows]
        with self.assertRaises(ValueError):verify_source_repetitions(rows,self.expected)

    def test_missing_changed_or_unexpected_source_fails(self):
        for changed in [self.rows[:-1],self.rows+[{**self.rows[0],'trace_id':'other'}],
                        [{**q,'source_request_sha256':'wrong'} if i==0 else q for i,q in enumerate(self.rows)]]:
            with self.assertRaises(ValueError):verify_source_repetitions(changed,self.expected)

    def test_duplicate_expected_source_is_not_collapsed(self):
        with self.assertRaises(ValueError):verify_source_repetitions(self.rows,self.expected+[self.expected[0]])


if __name__=='__main__':unittest.main()
