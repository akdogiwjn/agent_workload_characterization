"""G1-02 bounded OFFLINE tests. Real host protocol, fake Docker/counters.
No formal 20M workload, no production config, credentials, Docker or network.
"""
import copy
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import yaml
from agent_workload_characterization.runners import g1_02_entry as entry
from agent_workload_characterization.runners.container_runtime import FakeContainerRuntime
from agent_workload_characterization.collectors.resource_sampler import CounterSnapshot
from agent_workload_characterization.collectors.semantic_recorder import FakeClock


class ProtocolRuntime(FakeContainerRuntime):
    def __init__(self):
        super().__init__(FakeClock());self.children=[];self.pending=[];self.mode=None;self.envs=[]
    def start(self,spec,timeout_s=1):
        self.envs.append((os.environ.get('DOCKER_HOST'),os.environ.get('DOCKER_CONTEXT')))
        if self.mode=='lost_create':
            self.pending.append({'name':'owned-lost','removed':False});raise OSError('lost')
        return super().start(spec,timeout_s)
    def open_interactive(self,handle,command,timeout_s):
        argv=shlex.split(command)
        if self.mode=='empty':argv=['python3','-c','pass']
        if self.mode=='hang':argv=['python3','-c','import time;time.sleep(3)']
        if self.mode=='wrong_id':argv[-1]=argv[-1].replace('emit("request_finished", id=ident','emit("request_finished", id="WRONG"')
        proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        self.children.append(proc);return proc
    def read_counters(self,handle,t):
        self.read_log.append((handle.spec.scope,t))
        if self.mode=='read_error':raise OSError('fake-reader')
        n=len(self.read_log)
        cpu=None if self.mode=='missing' else (100000-n if self.mode=='reset' else n*100)
        return CounterSnapshot(handle.spec.scope,'agent_container',t,cpu_usage_usec=cpu,
                               mem_current_bytes=4096,read_status={'cpu.stat':'ok'})
    def cleanup_pending(self,timeout_s):
        result=[dict(p,removed=True) for p in self.pending];self.pending=[]
        return result


class G102Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        cfg=entry.load_config()
        cfg['workload'].update(work_iterations=150000,service_iterations=1000)
        cfg['measurement']['sampling_interval_s']=.001
        cfg['limits'].update(batch_wall_s=5,cleanup_reserve_s=1,operation_s=1,work_interval_s=.5)
        self.catalog=self.root/'catalog.yaml';self.catalog.write_text(yaml.safe_dump(cfg))
        self.namespace=self.root/'reports/resource/G1-02'
        self.patches=mock.patch.multiple(entry,PROJECT_ROOT=self.root,CATALOG=self.catalog,
                         APPROVAL=self.namespace/'APPROVAL.json',ATTEMPT=self.namespace/'ATTEMPT_STARTED.json')
        self.patches.start();self.runtime=ProtocolRuntime()
    def tearDown(self):
        for proc in self.runtime.children:
            if proc.poll() is None:proc.kill();proc.wait(timeout=1)
        self.patches.stop();self.tmp.cleanup()
    def run_batch(self,**kw):
        return entry.run_runtime_batch(self.runtime,self.namespace/'batch',**kw)
    def approve(self):
        self.namespace.mkdir(parents=True,exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(approved=True,approved_by='synthetic-test',
            approved_at_utc='fixture',checklist_identity=entry.build_plan()['identity'])))
    def run_main(self,preflight=None):
        def check(*,deadline):
            self.assertEqual(os.environ.get('DOCKER_HOST'),'unix:///var/run/docker.sock')
            self.assertNotIn('DOCKER_CONTEXT',os.environ)
            return preflight or {'status':'READY'}
        with mock.patch.object(entry,'DockerCliRuntime',return_value=self.runtime),mock.patch.object(entry,'docker_preflight',side_effect=check),context_output():
            return entry.main(['--execute','--i-approve-the-g1-02-b'])

    def test_real_entry_complete_chain_once_and_env(self):
        self.approve()
        with mock.patch.dict(os.environ,{'DOCKER_HOST':'tcp://fake','DOCKER_CONTEXT':'remote','HTTPS_PROXY':'fake'}):
            self.assertEqual(self.run_main(),0)
            self.assertEqual(os.environ['DOCKER_HOST'],'tcp://fake')
            self.assertEqual(os.environ['HTTPS_PROXY'],'fake')
        self.assertEqual(self.run_main(),3)
        self.assertEqual(len(self.runtime.started),2)
        self.assertEqual(self.runtime.active_at_start,[[],[]])
        self.assertEqual(self.runtime.containers,{})
        self.assertTrue(all(p.poll() is not None for p in self.runtime.children))
        batch=next(self.namespace.glob('G1-02-*'))
        events=[json.loads(l) for l in (batch/'service.tool_events.jsonl').read_text().splitlines()]
        self.assertEqual([(e['tool_call_id'],e['event']) for e in events],
            [('sync-1','open'),('sync-1','closed'),('sync-2','open'),('sync-2','closed')])
        summary=json.loads((batch/'summary.json').read_text())
        service=summary['cases'][0]['evidence']
        self.assertTrue(service['scopes'][0]['resource']['boundary_end'])
        intervals=summary['cases'][1]['evidence']['intervals']
        self.assertEqual(len(intervals),12)
        self.assertTrue(all(r['sample_ticks']==0 for r in intervals if r['condition']=='OFF'))
        self.assertTrue(any(r['sample_ticks']>0 for r in intervals if r['condition']=='ON'))
        self.assertTrue(all(r['host']['n_snapshots']>=2 for r in intervals))
        self.assertEqual({r['work_checksum'] for r in intervals},
            {runpy.run_path(str(entry.CONTROLLER))['expected_digest'](150000)})
        manifest=json.loads((batch/'manifest.json').read_text())
        for name,value in manifest['outputs'].items():self.assertEqual(entry.sha(batch/name),value['sha256'])

    def test_short_comparison_can_be_inconclusive_without_mechanism_failure(self):
        cfg=entry.load_config();cfg['comparison']['minimum_samples_per_interval']=999
        r=self.run_batch(config=cfg)
        self.assertEqual(r['status'],'PASS');self.assertEqual(r['comparison']['sufficiency'],'inconclusive')

    def test_empty_zero_exit_fails_actual_interactive_path(self):
        self.runtime.mode='empty';r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(len(self.runtime.started),1)
        self.assertIn('protocol_eof',str(r))

    def test_wrong_id_retains_raw_and_error_hook(self):
        self.runtime.mode='wrong_id';r=self.run_batch()
        self.assertEqual(r['status'],'FAIL')
        self.assertIn('WRONG',(self.namespace/'batch/service.events.jsonl').read_text())
        self.assertIn('"event": "error"',(self.namespace/'batch/service.tool_events.jsonl').read_text())

    def test_hang_deadline_and_cleanup(self):
        self.runtime.mode='hang';t=time.monotonic()
        r=self.run_batch(deadline=t+1.2)
        self.assertEqual(r['status'],'FAIL');self.assertLess(time.monotonic()-t,2)
        self.assertEqual(self.runtime.containers,{})

    def test_reader_exception_independent_cleanup_and_archive(self):
        self.runtime.mode='read_error';r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(self.runtime.containers,{})
        self.assertTrue((self.namespace/'batch/manifest.json').exists())

    def test_missing_cpu_service_cannot_pass(self):
        self.runtime.mode='missing';self.assertEqual(self.run_batch()['status'],'FAIL')

    def test_pending_lost_create_consumed(self):
        self.runtime.mode='lost_create';r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(self.runtime.pending,[])
        self.assertTrue(r['cleanup'][0]['removed'])

    def test_stop_then_verify_recompute(self):
        original=self.runtime.stop;seen=[]
        def stop(h,timeout_s):seen.append(timeout_s);time.sleep(.03);original(h,timeout_s)
        def verify(h,timeout_s):
            self.assertLess(timeout_s,seen[-1]);return 'removed'
        with mock.patch.object(self.runtime,'stop',side_effect=stop),mock.patch.object(self.runtime,'verify_removal',side_effect=verify):
            r=self.run_batch(deadline=time.monotonic()+1.3)
        self.assertTrue(seen)

    def test_unconfirmed_cleanup_fails_and_no_second_case(self):
        self.runtime.next_verify_result='check_failed';r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(len(self.runtime.started),1)

    def test_threshold_stops_in_protocol(self):
        cfg=entry.load_config();cfg['limits']['report_threshold_mib']=.00001
        r=self.run_batch(config=cfg)
        self.assertEqual(r['status'],'FAIL');self.assertEqual(len(self.runtime.started),1)
        self.assertEqual(self.runtime.containers,{})

    def test_approval_drift_and_old_approval_refused(self):
        self.approve();record=json.loads(entry.APPROVAL.read_text());record['checklist_identity']['collection']='RUN-02'
        entry.APPROVAL.write_text(json.dumps(record))
        self.assertEqual(self.run_main(),3);self.assertEqual(self.runtime.started,[])
        self.assertFalse(entry.ATTEMPT.exists())

    def test_single_flag_no_probe(self):
        with mock.patch.object(entry.subprocess,'run',side_effect=AssertionError('NO SUBPROCESS')):
            self.assertEqual(entry.main(['--execute']),2)

    def test_preflight_failure_marker_no_runtime(self):
        self.approve();self.assertEqual(self.run_main({'status':'NOT_READY'}),4)
        self.assertEqual(self.runtime.started,[])
        self.assertEqual(json.loads(entry.ATTEMPT.read_text())['status'],'failed')

    def test_preflight_shared_deadline_and_local_env(self):
        calls=[]
        def fake(argv,**kw):
            calls.append(kw['timeout']);time.sleep(.01)
            return subprocess.CompletedProcess(argv,0,'default' if len(calls)==1 else 'linux/arm64','')
        with entry.local_docker_environment():
            self.assertEqual(entry.docker_preflight(deadline=time.monotonic()+.2,runner=fake)['status'],'READY')
        self.assertLess(calls[1],calls[0]);self.assertLessEqual(calls[0],.2)

    def test_paths_symlink_existing_and_protected(self):
        self.namespace.mkdir(parents=True);target=self.root/'target';target.mkdir()
        (self.namespace/'redirect').symlink_to(target,target_is_directory=True)
        for path in [self.namespace/'redirect/new',self.root/'data/raw/x']:
            with self.assertRaises((entry.G102Error,ValueError)):entry.guarded(path,new=True)
        with self.assertRaises(entry.G102Error):entry.guarded(target,new=True)

    def test_config_bad_values_and_yaml_order(self):
        cfg=entry.load_config();self.assertEqual(cfg['comparison']['order'][0],'OFF')
        cfg['limits']['work_interval_s']=float('nan');self.catalog.write_text(yaml.safe_dump(cfg))
        with self.assertRaises(entry.G102Error):entry.load_config()

    def test_shared_code_in_approval_identity(self):
        code=entry.build_plan()['identity']['code_sha256']
        for name in ['container_runtime','tool_event_env','report_writer']:
            self.assertIn('src/agent_workload_characterization/runners/'+name+'.py',code)
        self.assertIn('src/agent_workload_characterization/collectors/resource_sampler.py',code)

    def test_compare_missing_reset_latency_checksum(self):
        result=self.run_batch();intervals=result['cases'][1]['evidence']['intervals']
        compare=runpy.run_path(str(entry.CONTROLLER))['compare']
        cfg=entry.load_config()
        variants=[('cpu_boundary_missing',lambda r:r['resource']['boundary_end'].update(cpu_usage_usec=None)),
                  ('cpu_reset',lambda r:r['resource']['boundary_end'].update(cpu_usage_usec=0)),
                  ('boundary_latency',lambda r:r.update(boundary_read_latency_s=float('nan'))),
                  ('checksum',lambda r:r.update(work_checksum='wrong')),
                  ('too_few_samples',lambda r:r.update(sample_ticks=0))]
        for reason,mutate in variants:
            with self.subTest(reason=reason):
                rows=copy.deepcopy(intervals);mutate(rows[1]);answer=compare(rows,cfg)
                self.assertEqual(answer['sufficiency'],'inconclusive');self.assertIn(reason,answer['reasons'])

    def test_manifest_failure_still_cleans_and_returns_failure(self):
        original=entry.write_json
        def write(path,payload):
            if Path(path).name=='manifest.json':raise OSError('fake archive failure')
            return original(path,payload)
        with mock.patch.object(entry,'write_json',side_effect=write):r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['archive_status'],'failed')
        self.assertEqual(self.runtime.containers,{})
        self.assertTrue((self.namespace/'batch/archive_failure.json').exists())

    def test_pending_unconfirmed_prevents_success(self):
        with mock.patch.object(self.runtime,'cleanup_pending',return_value=[{'removed':False}]):r=self.run_batch()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(len(self.runtime.started),1)

    def test_expired_budget_no_container_and_failed_archive(self):
        r=self.run_batch(deadline=time.monotonic()-.1)
        self.assertEqual(r['status'],'FAIL');self.assertEqual(self.runtime.started,[])
        self.assertTrue(r['budget_overrun'])

    def test_existing_batch_and_symlink_approval_rejected(self):
        self.namespace.mkdir(parents=True);(self.namespace/'batch').mkdir()
        with self.assertRaises(entry.G102Error):self.run_batch()
        target=self.root/'approval';target.write_text('{}');entry.APPROVAL.symlink_to(target)
        with self.assertRaises(entry.G102Error):entry.verify_approval(entry.APPROVAL)

    def test_default_plan_no_subprocess(self):
        with mock.patch.object(entry.subprocess,'run',side_effect=AssertionError('NO PROBE')),context_output():
            self.assertEqual(entry.main([]),0)

    def test_boundaries_archived_before_remove(self):
        stop=self.runtime.stop
        def checked(handle,timeout_s):
            path=self.namespace/'batch'/(handle.spec.scope+'.evidence.json')
            self.assertTrue(path.exists())
            evidence=json.loads(path.read_text())
            self.assertTrue(evidence['scopes'][0]['resource']['boundary_end'])
            stop(handle,timeout_s)
        with mock.patch.object(self.runtime,'stop',side_effect=checked):
            self.assertEqual(self.run_batch()['status'],'PASS')

    def test_evidence_write_failure_cannot_bypass_cleanup(self):
        original=entry.write_json
        def write(path,payload):
            if str(path).endswith('.evidence.json'):raise OSError('fake')
            original(path,payload)
        with mock.patch.object(entry,'write_json',side_effect=write):
            result=self.run_batch()
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(len(self.runtime.started),1)
        self.assertEqual(self.runtime.containers,{})


def context_output():
    return mock.patch('sys.stdout',new_callable=io.StringIO)
