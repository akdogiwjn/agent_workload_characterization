"""Counterexamples for identity joins and native replay preparation."""
import copy
import unittest

import numpy as np

from scripts.agentx_replay_smoke_audit import longest_prefix,validate_joins
from scripts.agentx_replay_smoke_prepare import leaves,select


class ReplayTests(unittest.TestCase):
    def sample(self):
        source=[{'trace_id':'a','outer_idx':0,'inner_idx':None}]
        exported=[{'metadata':{'source_trace_id':'a','source_outer_idx':0,'x_request_id':'r'}}]
        wire=[{'request_id':'r'}]
        return source,exported,wire

    def test_join_normalizes_omitted_inner_index(self):
        s,e,w=validate_joins(*self.sample());self.assertEqual(set(s),set(e));self.assertEqual(set(w),{'r'})

    def test_equal_counts_do_not_hide_wrong_source(self):
        s,e,w=self.sample();e[0]['metadata']['source_trace_id']='other'
        with self.assertRaisesRegex(ValueError,'source/export'):validate_joins(s,e,w)

    def test_equal_counts_do_not_hide_wrong_http_request(self):
        s,e,w=self.sample();w[0]['request_id']='other'
        with self.assertRaisesRegex(ValueError,'export/wire'):validate_joins(s,e,w)

    def test_duplicate_source_and_export_identities_rejected(self):
        for index in range(3):
            values=list(self.sample());values[index].append(copy.deepcopy(values[index][0]))
            with self.assertRaisesRegex(ValueError,'duplicate'):validate_joins(*values)

    def test_one_http_request_cannot_satisfy_two_sources(self):
        s,e,w=self.sample();s.append({'trace_id':'a','outer_idx':1,'inner_idx':None})
        e.append({'metadata':{'source_trace_id':'a','source_outer_idx':1,'x_request_id':'r'}})
        with self.assertRaisesRegex(ValueError,'export/wire'):validate_joins(s,e,w)

    def test_prefix_stops_at_first_different_token(self):
        for a,b,want in [([1,2,3],[1,9,3],1),([],[],0),([1],[1,2],1),([1],[2],0)]:
            self.assertEqual(longest_prefix(np.array(a),np.array(b)),want)

    def test_native_source_indices_and_absolute_child_clock(self):
        q={'type':'s','t':12,'api_time':1,'model':'m','in':64,'out':1,'hash_ids':[7]}
        rows=leaves({'id':'x','requests':[q,{'type':'subagent','agent_id':'c','t':10,'requests':[q]}]})
        self.assertEqual(rows[1]['source_t'],12)
        self.assertEqual((rows[1]['outer_idx'],rows[1]['inner_idx']),(1,0))
        self.assertEqual(rows[1]['pointer'],'/requests/1/requests/0')
        self.assertEqual(rows[0]['source_request_sha256'],rows[1]['source_request_sha256'])

    def test_selection_is_minimum_complete_session_and_deduplicated(self):
        def row(i,n,g,p=1,size=64,variant='full'):
            return {'trace_id':i,'requests':str(n),'groups':str(g),'peak':str(p),'max_input':str(size),'variant':variant}
        rows=[row('s',2,0),row('o',3,0,2),row('c',4,1),row('m',5,3),row('l',6,0,size=500000),row('256',1,0,variant='256k'),row('z',20,0)]
        result=select(rows)
        self.assertEqual([q['trace_id'] for q in result],['s','o','c','m','l'])
        self.assertEqual(select(list(reversed(rows))),result)


if __name__=='__main__':unittest.main()
