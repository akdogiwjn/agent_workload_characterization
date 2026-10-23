import asyncio
import unittest

from scripts.agentx_deepseek_branch_prepare import compile_edges,validate_dag
from scripts.agentx_deepseek_branches import schedule
from scripts.agentx_deepseek_branch_analysis import audit_edges,intervals


def node(n,*deps):return {'node_id':n,'depends_on':list(deps)}


class GraphTests(unittest.TestCase):
    def test_half_open_interval_concurrency_does_not_double_count_ties(self):
        result,_=intervals([{'start_s':0,'end_s':1},{'start_s':1,'end_s':2}])
        self.assertEqual(result['peak'],1);self.assertEqual(result['interval_sum_s'],2)
        result,_=intervals([{'start_s':0,'end_s':2},{'start_s':1,'end_s':3}])
        self.assertEqual(result['peak'],2);self.assertEqual(result['multi_request_s'],1)

    def test_dependency_audit_rejects_dispatch_before_parent_completion(self):
        result={'a':{'ended_monotonic_ns':100},'b':{'started_monotonic_ns':99}}
        with self.assertRaises(ValueError):audit_edges([{'predecessor':'a','successor':'b','kind':'spawn'}],result)
        result['b']['started_monotonic_ns']=100
        self.assertTrue(audit_edges([{'predecessor':'a','successor':'b','kind':'spawn'}],result)[0]['passed'])

    def test_cycle_and_missing_predecessor_rejected(self):
        for nodes in [[node('a','b'),node('b','a')],[node('a','missing')],[node('a'),node('a')]]:
            with self.assertRaises(ValueError):validate_dag(nodes)

    def test_official_metadata_projection_preserves_spawn_and_join(self):
        def turn(branches=(),prerequisites=()):return {'branch_ids':list(branches),'prerequisites':list(prerequisites)}
        meta=[{'conversation_id':'p','branches':[{'branch_id':'b','child_conversation_ids':['c'],'mode':'spawn','dispatch_timing':'post'}],
               'turns':[turn(['b']),turn(prerequisites=[{'kind':'spawn_join','branch_id':'b'}])]},
              {'conversation_id':'c','branches':[],'turns':[turn(),turn()]}]
        deps,edges,parents=compile_edges(meta)
        self.assertEqual(deps['c#0'],{'p#0'});self.assertEqual(deps['p#1'],{'p#0','c#1'})
        self.assertEqual(deps['c#1'],{'c#0'});self.assertEqual(parents,{'c':'p'})
        self.assertEqual({q['kind'] for q in edges},{'spawn','join','serial'})


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_children_overlap_and_join_waits_for_both(self):
        nodes=[node('p0'),node('a','p0'),node('b','p0'),node('p1','p0','a','b')]
        started={'a':asyncio.Event(),'b':asyncio.Event()};finished=set()
        async def send(q):
            n=q['node_id']
            if n in started:
                self.assertIn('p0',finished);started[n].set();await started['b' if n=='a' else 'a'].wait()
            if n=='p1':self.assertTrue({'a','b'}<=finished)
            finished.add(n);return {'status':'completed'}
        result=await asyncio.wait_for(schedule(nodes,send),1)
        self.assertEqual(len(result),4);self.assertEqual(finished,{'p0','p1','a','b'})

    async def test_failure_stops_new_dispatch_but_drains_inflight(self):
        started=asyncio.Event();release=asyncio.Event();called=[]
        async def send(q):
            n=q['node_id'];called.append(n)
            if n=='a':started.set();await release.wait();return {'status':'completed'}
            if n=='b':await started.wait();release.set();return {'status':'http_error'}
            raise AssertionError('blocked descendant was sent')
        result=await asyncio.wait_for(schedule([node('a'),node('b'),node('c','b')],send),1)
        self.assertEqual(result['a']['status'],'completed');self.assertEqual(result['b']['status'],'http_error')
        self.assertEqual(result['c']['status'],'not_executed');self.assertEqual(set(called),{'a','b'})

    async def test_concurrency_limit_is_enforced(self):
        active=0;peak=0
        async def send(q):
            nonlocal active,peak
            active+=1;peak=max(peak,active);await asyncio.sleep(.001);active-=1
            return {'status':'completed'}
        await schedule([node(str(i)) for i in range(20)],send,3)
        self.assertEqual(peak,3)


if __name__=='__main__':unittest.main()
