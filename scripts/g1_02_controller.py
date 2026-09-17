"""Host-only controller. ON periodic reads run in the selector loop; OFF has
only boundaries. Uses existing ResourceSampler/HostProcessMonitor and hook.
No container PID is read from the host, and no sampler thread can leak.
"""
import dataclasses
import hashlib
import json
import math
import os
import selectors
import time

from agent_workload_characterization.collectors.host_process import HostProcessMonitor, read_starttime
from agent_workload_characterization.runners.tool_event_env import wrap_environment


class ControllerError(RuntimeError):
    pass


def expected_digest(n):
    # Independent closed-form oracle for worker's iterative recurrence.
    return hashlib.sha256(str((3*n*(n-1)//2) & 0xFFFFFFFF).encode()).hexdigest()


def finite(v):
    return type(v) in (int,float) and math.isfinite(v) and v >= 0


class Transport:
    def __init__(self, proc, deadline, emit, check):
        self.proc,self.deadline,self.emit,self.check=proc,deadline,emit,check
        self.buffer=b''; self.tick=None; self.period=.2; self.next_tick=0
        self.local_deadline=None
        os.set_blocking(proc.stdout.fileno(),False)
        os.set_blocking(proc.stdin.fileno(),False)
        self.selector=selectors.DefaultSelector()
        self.selector.register(proc.stdout,selectors.EVENT_READ)

    def remaining(self, deadline):
        self.check()
        rem=min(deadline,self.deadline,self.local_deadline if self.local_deadline is not None else self.deadline)-time.monotonic()
        if rem<=0:raise ControllerError('protocol_deadline')
        return rem

    def send(self, op, ident=None, **fields):
        data=json.dumps(dict(op=op,id=ident,**fields)).encode()+b'\n'
        deadline=min(self.deadline,time.monotonic()+15)
        with selectors.DefaultSelector() as sel:
            sel.register(self.proc.stdin,selectors.EVENT_WRITE)
            while data:
                rem=self.remaining(deadline)
                if not sel.select(min(rem,.05)):continue
                try:n=os.write(self.proc.stdin.fileno(),data)
                except BlockingIOError:continue
                data=data[n:]

    def recv(self, deadline=None):
        deadline=min(deadline or self.deadline,time.monotonic()+15)
        while True:
            rem=self.remaining(deadline)
            if self.tick and time.monotonic()>=self.next_tick:
                self.tick();self.next_tick=time.monotonic()+self.period
                rem=self.remaining(deadline)
            if b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                event=json.loads(line)
                if not isinstance(event,dict):raise ControllerError('non_object_event')
                self.emit(event)
                return event
            if not self.selector.select(min(rem,.05)):continue
            chunk=os.read(self.proc.stdout.fileno(),4096)
            if not chunk:raise ControllerError('protocol_eof')
            self.buffer+=chunk
            if len(self.buffer)>65536:raise ControllerError('protocol_line_limit')

    def close(self):
        self.selector.close()


def compare(intervals, config):
    reasons=[];cmp=config['comparison'];deltas=[]
    if len(intervals)!=12 or [r['condition'] for r in intervals]!=cmp['order']:
        reasons.append('interval_order_or_count')
    for r in intervals:
        bs=[r['resource'].get(k) for k in ('boundary_start','boundary_end')]
        valid=all(isinstance(b,dict) and finite(b.get('cpu_usage_usec')) for b in bs)
        if not valid:reasons.append('cpu_boundary_missing')
        elif bs[1]['cpu_usage_usec']<bs[0]['cpu_usage_usec']:reasons.append('cpu_reset')
        if r['work_checksum']!=expected_digest(config['workload']['work_iterations']):reasons.append('checksum')
        if not finite(r['worker_cpu_s']) or r['worker_cpu_s']<cmp['minimum_worker_cpu_s']:reasons.append('short_worker_cpu')
        lat=r.get('boundary_read_latency_s')
        if not finite(lat) or lat>cmp['boundary_read_max_s']:reasons.append('boundary_latency')
        if r['condition']=='ON' and r['sample_ticks']<cmp['minimum_samples_per_interval']:reasons.append('too_few_samples')
        if r['condition']=='OFF' and r['sample_ticks']!=0:reasons.append('off_periodic_reads')
        samples=r['resource'].get('samples',[])
        if valid:
            sequence=[bs[0],*samples,bs[1]]
            if any(not finite(s.get('cpu_usage_usec')) for s in sequence):
                reasons.append('sample_cpu_missing')
            elif any(b['cpu_usage_usec']<a['cpu_usage_usec'] for a,b in zip(sequence,sequence[1:])):
                reasons.append('sample_cpu_reset')
            if any(not bs[0]['t_monotonic_ns']<=s['t_monotonic_ns']<=bs[1]['t_monotonic_ns'] for s in samples):
                reasons.append('sample_outside_boundaries')
        host=r['host']
        if host['n_readable']!=host['n_snapshots'] or host['n_readable']<2:reasons.append('host_boundary_missing')
        if valid and finite(r['worker_cpu_s']):
            cpu=(bs[1]['cpu_usage_usec']-bs[0]['cpu_usage_usec'])/1e6
            ww=(r['done']['t_monotonic_ns']-r['started']['t_monotonic_ns'])/1e9
            bw=(bs[1]['t_monotonic_ns']-bs[0]['t_monotonic_ns'])/1e9
            allowance=2/host['clk_tck']+config['limits']['per_container_cpu']*max(0,bw-ww)
            r['cpu_diagnostic']=dict(container_cpu_s=cpu,worker_cpu_s=r['worker_cpu_s'],
                difference_s=cpu-r['worker_cpu_s'],allowance_s=allowance,
                semantics='different_windows_diagnostic_not_error_bound')
            if abs(cpu-r['worker_cpu_s'])>allowance:reasons.append('cpu_diagnostic_outside_allowance')
    for pair in range(6):
        records={r['condition']:r for r in intervals if r['pair']==pair}
        if set(records)=={'ON','OFF'}:deltas.append(records['ON']['bracket_wall_ns']-records['OFF']['bracket_wall_ns'])
    ordered=sorted(deltas)
    return dict(sufficiency='inconclusive' if reasons or len(deltas)!=6 else 'sufficient',
        reasons=sorted(set(reasons)),pair_count=len(deltas),deltas_ns=deltas,
        median_delta_ns=(ordered[2]+ordered[3])/2 if len(ordered)==6 else None,
        range_ns=[min(ordered),max(ordered)] if ordered else None,
        definition='host bracket wall including boundary/collector/control work; startup/archive excluded')


def run_controller(*, proc, case, config, deadline, sampler_factory, events_path,
                   hook_path, check, run_id):
    events=[];intervals=[];scopes=[]
    result=dict(status='FAIL',events=events,intervals=intervals,scopes=scopes,case=case,
                errors=[],comparison={'sufficiency':'not_applicable'})
    event_file=events_path.open('x',encoding='utf-8')
    def emit(event):
        row=dict(event,received_monotonic_ns=time.monotonic_ns())
        events.append(row);event_file.write(json.dumps(row)+'\n');event_file.flush();check()
    transport=Transport(proc,deadline,emit,check)
    identity=None;seen=set();last_time=-1;active=None
    def receive(name, ident=None, until=None, state=None):
        nonlocal identity,last_time
        row=transport.recv(until)
        current=tuple(row.get(k) for k in ('run_id','service_id','pid','starttime_ticks'))
        if identity is None:
            if (row.get('event')!='ready' or current[0]!=run_id or current[1]!=run_id+':service'
                or type(current[2]) is not int or current[2]<=0
                or type(current[3]) is not int or current[3]<0):raise ControllerError('worker_identity')
            identity=current
        stamp=row.get('t_monotonic_ns');token=(name,ident)
        if (current!=identity or row.get('event')!=name or row.get('id')!=ident or
            type(stamp) is not int or stamp<last_time or token in seen or
            (state is not None and row.get('state')!=state)):
            raise ControllerError('event_identity_order_or_state')
        seen.add(token);last_time=stamp
        return row

    def begin(scope,condition):
        nonlocal active
        host=HostProcessMonitor(os.getpid(),expected_starttime=read_starttime(os.getpid()),
                               interval_s=config['measurement']['sampling_interval_s'])
        sampler=sampler_factory(scope)
        active=(scope,sampler,host,condition,time.monotonic_ns(),time.process_time_ns())
        host.poll_once();sampler.start(scope)
        if condition=='ON':
            def tick():sampler.sample_once();host.poll_once()
            transport.tick=tick;transport.period=host.interval_s
            transport.next_tick=time.monotonic()+host.interval_s

    def end():
        nonlocal active
        if active is None:return None
        scope,sampler,host,condition,t0,cpu0=active;transport.tick=None;errors=[]
        try:sampler.stop(scope)
        except Exception as exc:errors.append(type(exc).__name__)
        try:host.poll_once()
        except Exception as exc:errors.append(type(exc).__name__)
        hs=host.summary();hs['scope']='host_orchestrator_process'
        hs['records']=[dataclasses.asdict(s) for s in host.snapshots]
        hs['process_time_ns_delta']=time.process_time_ns()-cpu0
        ev=sampler.all_scope_evidence()[scope]
        ev['formal_io']=None;ev['io_reason']='degraded_host_v1_blkio'
        row=dict(scope=scope,condition=condition,resource=ev,host=hs,
                 bracket_wall_ns=time.monotonic_ns()-t0,errors=errors)
        scopes.append(row);active=None
        if errors:raise ControllerError('collector_stop_failed')
        return row

    try:
        transport.send('hello');receive('ready')
        if case=='service':
            begin('service','ON')
            class SyncEnvironment:
                def execute(self,action,cwd='',*,timeout=None):
                    ident=action['tool_call_id'];until=min(deadline,time.monotonic()+config['limits']['work_interval_s'])
                    transport.local_deadline=until
                    transport.send('sync',ident,iterations=config['workload']['service_iterations'])
                    receive('request_started',ident,until);done=receive('request_finished',ident,until)
                    if done.get('digest')!=expected_digest(config['workload']['service_iterations']):raise ControllerError('sync_checksum')
                    transport.local_deadline=None
                    return {'returncode':0,'output':''}
            env=wrap_environment(SyncEnvironment(),hook_path)
            try:
                for ident in ('sync-1','sync-2'):env.execute({'command':'sync','tool_call_id':ident})
            finally:env.close()
            for ident,cancel in [('job-1',False),('job-2',True)]:
                until=min(deadline,time.monotonic()+config['limits']['work_interval_s'])
                transport.local_deadline=until
                transport.send('submit',ident,cancelable=cancel);receive('job_submitted',ident,until)
                transport.send('release',ident);receive('job_started',ident,until)
                if cancel:
                    transport.send('cancel',ident);receive('job_finished',ident,until,state='cancelled')
                else:
                    transport.send('poll',ident);receive('poll_result',ident,until,state='started')
                    transport.send('proceed',ident,iterations=config['workload']['service_iterations'])
                    receive('proceed_ack',ident,until);done=receive('job_finished',ident,until,state='completed')
                    if done.get('digest')!=expected_digest(config['workload']['service_iterations']):raise ControllerError('job_checksum')
                transport.send('wait',ident);receive('wait_result',ident,until,state='cancelled' if cancel else 'completed')
                transport.local_deadline=None
            row=end()
            if not all(finite((row['resource'].get(k) or {}).get('cpu_usage_usec')) for k in ('boundary_start','boundary_end')):
                raise ControllerError('service_cpu_boundary_missing')
            if row['resource']['boundary_end']['cpu_usage_usec']<row['resource']['boundary_start']['cpu_usage_usec']:
                raise ControllerError('service_cpu_reset')
        else:
            for i,condition in enumerate(config['comparison']['order']):
                ident=f'window-{i}'
                transport.local_deadline=min(deadline,time.monotonic()+config['limits']['work_interval_s'])
                transport.send('window_start',ident);baseline=receive('baseline_ready',ident)
                begin(ident,condition)
                until=min(deadline,time.monotonic()+config['limits']['work_interval_s'])
                transport.send('window_release',ident,iterations=config['workload']['work_iterations'])
                started=receive('work_started',ident,until);done=receive('work_done',ident,until);row=end()
                transport.send('window_ack',ident);ack=receive('window_acknowledged',ident)
                transport.local_deadline=None
                ls=[(row['resource'].get(k) or {}).get('read_status',{}).get('read_latency_s') for k in ('boundary_start','boundary_end')]
                latency=max(map(float,ls)) if all(v is not None for v in ls) else None
                row.update(pair=i//2,baseline=baseline,started=started,done=done,ack=ack,
                    worker_cpu_s=done.get('cpu_seconds'),work_checksum=done.get('digest'),
                    boundary_read_latency_s=latency,sample_ticks=len(row['resource']['samples']))
                intervals.append(row)
                if row['work_checksum']!=expected_digest(config['workload']['work_iterations']):raise ControllerError('work_checksum')
            result['comparison']=compare(intervals,config)
        transport.send('shutdown');receive('closed')
        proc.wait(timeout=transport.remaining(deadline))
        if proc.returncode!=0:raise ControllerError('worker_exit_nonzero')
        result['status']='PASS'
    except Exception as exc:
        result['errors'].append(type(exc).__name__+(':'+str(exc) if isinstance(exc,ControllerError) else ''))
    finally:
        try:end()
        except Exception as exc:result['errors'].append(type(exc).__name__);result['status']='FAIL'
        if proc.poll() is None:
            proc.kill()
            try:proc.wait(timeout=max(.01,min(1,deadline-time.monotonic())))
            except Exception:result['errors'].append('worker_reap_unconfirmed');result['status']='FAIL'
        transport.close();event_file.close();proc.stdin.close();proc.stdout.close()
    result['returncode']=proc.returncode
    return result
