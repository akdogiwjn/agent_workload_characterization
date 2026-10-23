import unittest
from scripts.agentx_deep_locality import classify_pair


class LocalityTests(unittest.TestCase):
    def pair(self,**updates):
        return {'adjacent_prefix_tokens':128,'adjacent_model_same':True,'adjacent_interval_gap_s':0,**updates}

    def test_true_zero_gap_remains_eligible(self):
        self.assertEqual(classify_pair(self.pair()),'eligible_completed_adjacent_prefix_pair')

    def test_overlapping_request_never_promoted_by_clipping(self):
        self.assertEqual(classify_pair(self.pair(adjacent_interval_gap_s=-0.000001)),
                         'adjacent_predecessor_not_completed')

    def test_disjoint_partition_for_first_model_change_and_empty_prefix(self):
        self.assertEqual(classify_pair({}),'first_in_native_stream')
        self.assertEqual(classify_pair(self.pair(adjacent_model_same=False)),'adjacent_model_changed')
        self.assertEqual(classify_pair(self.pair(adjacent_prefix_tokens=0)),'no_nonempty_shared_prefix')


if __name__=='__main__':unittest.main()
