"""CPU-02 single production entry: one real Verifier segment + one perf record.

Default plan is side-effect free. Execution requires BOTH flags AND a real
approval whose checklist_identity equals the live build_plan identity; the
attempt marker is exclusive and never reused. One fresh container (network
none, pull never, fixed arm64 digest) runs the official SWE-bench prepare
chain, then a container-side supervisor reports its identity and blocks on
the control protocol; only after the host has (a) mapped the container PID to the
host PID (innermost NSpid + pid-namespace inode + starttime, anchored on
the container init PID) and (b) confirmed the attached perf is actually
producing samples (perf.data growth while the marker loop runs) does it
exec the official eval script under the same PID. perf stays on the host;
no docker client is ever the sampling target. Tests inject fake
runtime/perf/grader/proc-roots through the real entry path.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid

from ..collectors import perf_adapter
from ..collectors.host_process import read_starttime
from ..collectors.resource_sampler import ResourceSampler, ScopeReader
from .coding_pilot import SwebenchVerifierRunner
from .container_runtime import ContainerSpec, ContainerHandle
from .cpu_01_entry import (_drain, _group_alive, remaining as _remaining,
                           stop_process_group as _stop_group)
from .report_writer import guard_cpu_report, guard_cpu_root, _catalog_protected_roots

PROJECT_ROOT=Path(__file__).resolve().parents[3]
CODE_ROOT=PROJECT_ROOT
CATALOG=PROJECT_ROOT/'workload_catalog/cpu_02.yaml'
RECORD=PROJECT_ROOT/'data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3/django__django-16485/record.json'
CANDIDATE=PROJECT_ROOT/'data/raw/generated/RUN-02/20260915T012427Z-2d75aa/candidate.patch'
SUPERVISOR=PROJECT_ROOT/'scripts/cpu_02_supervisor.py'
PERF_SUPERVISOR=PROJECT_ROOT/'scripts/cpu_02_perf_supervisor.py'
VENV_PYTHON=PROJECT_ROOT/'.venvs/swebench-eval-02e7a74/bin/python'
APPROVAL=PROJECT_ROOT/'reports/cpu/CPU-02/APPROVAL.json'
ATTEMPT=PROJECT_ROOT/'reports/cpu/CPU-02/ATTEMPT_STARTED.json'
PARANOID_PATH='/proc/sys/kernel/perf_event_paranoid'
SCOPE='cpu02-verifier'
EVAL_SCRIPT_ORIGINAL_SHA256='17f89072e31422786c1f91ffc6b6a0ba0d5741511439209f119ed3eaaf55bca1'
EVAL_SCRIPT_GENERATED_SHA256='c44c7b80f030a1352063585330d30f75c9252169e8668a14b6f0d0a812ce0a1b'
EVAL_SCRIPT_DIFFERENCE_ID='record_eval_script_plus_exit_code_v1'


class CPU02Error(RuntimeError):
    pass


class UnavailableSignal(Exception):
    """perf refused/unready before eval: honest 'unavailable', not infra FAIL."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config():
    import yaml
    cfg=yaml.safe_load(CATALOG.read_text())
    if not isinstance(cfg,dict) or cfg.get('execution_authorized') is not False:
        raise CPU02Error('catalog_not_offline_registered')
    w=cfg['workload']
    if w['record_sha256']!=sha(RECORD):raise CPU02Error('record_hash_drift')
    if w['candidate_sha256']!=sha(CANDIDATE):raise CPU02Error('candidate_hash_drift')
    lim=cfg['limits']
    for key,maximum in {'batch_wall_s':300,'cleanup_reserve_s':30,'prepare_wall_s':60,
                        'eval_wall_s':120,'operation_s':15,'perf_ready_window_s':10,
                        'report_threshold_mib':100}.items():
        v=lim[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=maximum:
            raise CPU02Error('invalid_budget')
    if lim['retries']!=0 or lim['network']!='none' or lim['pull']!='never':
        raise CPU02Error('invalid_isolation')
    if lim['batch_wall_s']<=lim['cleanup_reserve_s']:raise CPU02Error('invalid_reserve')
    perf=cfg['perf']
    freq=perf['record']['frequency_hz']
    if type(freq) is not int or not 1<=freq<=lim['record_frequency_hz_max']:
        raise CPU02Error('invalid_record_frequency')
    if perf['record']['event']!='cycles':raise CPU02Error('invalid_record_event')
    rd=perf['readiness']
    if rd.get('protocol')!='perf_record_control_fifo_ack':
        raise CPU02Error('invalid_readiness_protocol')
    if type(rd.get('ack_timeout_s')) not in (int,float) or not 0<rd['ack_timeout_s']<=15:
        raise CPU02Error('invalid_readiness')
    if cfg['sampling']['interval_s']<=0:raise CPU02Error('invalid_sampling_interval')
    return cfg


def _registered_eval_script_identity(record):
    """Return the fixed evaluator/script identity without side effects.

    The default plan must remain subprocess-free.  The execute path performs
    the authoritative make_test_spec call in the pinned evaluator venv and
    compares its bytes with these registered values before starting Docker.
    """
    original=record.get('eval_script')
    if not isinstance(original,str) or not original.strip():
        raise CPU02Error('eval_script_missing')
    if hashlib.sha256(original.encode()).hexdigest()!=EVAL_SCRIPT_ORIGINAL_SHA256:
        raise CPU02Error('eval_script_original_hash_drift')
    return dict(original_sha256=EVAL_SCRIPT_ORIGINAL_SHA256,
                original_bytes=len(original.encode()),
                generated_sha256=EVAL_SCRIPT_GENERATED_SHA256,
                generated_bytes=1453,
                evaluator={'venv_python':str(VENV_PYTHON),
                           'pinned_harness':'02e7a74',
                           'call':'swebench.harness.utils.make_test_spec(record).eval_script'},
                difference_id=EVAL_SCRIPT_DIFFERENCE_ID,
                difference=("insert SWEBENCH_TEST_EXIT_CODE=$? immediately after "
                            "the test command, then echo its value after the end marker"))


def _load_generated_eval_script(record, *, deadline=None):
    """Generate the official script in the pinned venv and enforce the one
    registered two-line difference from record.eval_script."""
    registered=_registered_eval_script_identity(record)
    if not VENV_PYTHON.is_file():
        raise CPU02Error('evaluator_unavailable')
    code=('import hashlib,json,sys;'
          'from swebench.harness.utils import make_test_spec;'
          'r=json.load(open(sys.argv[1]));s=make_test_spec(r).eval_script;'
          'print(json.dumps({"script":s,"sha256":hashlib.sha256(s.encode()).hexdigest()},'
          'separators=(",",":")))')
    try:
        timeout=15.0
        if deadline is not None:
            timeout=min(timeout,max(0.001,deadline-time.monotonic()))
        proc=subprocess.run([str(VENV_PYTHON),'-B','-c',code,str(RECORD)],
                            capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise CPU02Error('evaluator_unavailable') from exc
    if proc.returncode!=0:
        raise CPU02Error('evaluator_unavailable')
    try:
        result=json.loads(proc.stdout)
        generated=result['script']
        if result['sha256']!=EVAL_SCRIPT_GENERATED_SHA256:
            raise ValueError
    except (ValueError,KeyError,json.JSONDecodeError):
        raise CPU02Error('eval_script_generated_hash_drift')
    original=record['eval_script']
    marker=": '>>>>> End Test Output'\n"
    expected=(original.replace(marker,
        "SWEBENCH_TEST_EXIT_CODE=$?\n"+marker+
        'echo ">>>>> Test Exit Code: $SWEBENCH_TEST_EXIT_CODE"\n',1)
        if original.count(marker)==1 else None)
    # The expected transformation is deliberately exact; accepting arbitrary
    # generated scripts would silently change the evaluated workload.
    if expected is None or generated!=expected:
        raise CPU02Error('eval_script_unregistered_diff')
    metadata=dict(registered)
    metadata.update(generated_sha256=result['sha256'],
                    generated_bytes=len(generated.encode()),
                    verified_by='make_test_spec(record) in pinned evaluator')
    return generated,metadata


def build_plan():
    cfg=load_config()
    record=json.loads(RECORD.read_text())
    eval_identity=_registered_eval_script_identity(record)
    paths=sorted((CODE_ROOT/'src/agent_workload_characterization').rglob('*.py'))+[SUPERVISOR]
    identity=dict(catalog_sha256=sha(CATALOG),config=cfg,
        code_sha256={str(p.relative_to(CODE_ROOT)):sha(p) for p in paths},
        interpreter={'path':str(Path(sys.executable).resolve()),'version':sys.version.split()[0]},
        collection='CPU-02',approval='reports/cpu/CPU-02/APPROVAL.json',
        record={'path':str(RECORD.relative_to(CODE_ROOT)),'sha256':cfg['workload']['record_sha256']},
        candidate={'path':str(CANDIDATE.relative_to(CODE_ROOT)),'sha256':cfg['workload']['candidate_sha256']},
        image=cfg['workload']['image'],
        supervisor={'script':str(SUPERVISOR.relative_to(CODE_ROOT)),
                    'protocol':'ready_json_then_control_fifo_ack_release_then_exec'},
        evaluator={'venv_python':str(VENV_PYTHON),
                   'parser':'official make_test_spec + get_eval_report (02e7a74)',
                   'eval_script':eval_identity},
        perf={'binary':cfg['perf']['binary'],'record_event':cfg['perf']['record']['event'],
              'record_frequency_hz':cfg['perf']['record']['frequency_hz'],
              'attach':'-p host_pid_of_container_target',
              'readiness':cfg['perf']['readiness']})
    return dict(task='CPU-02',mode='plan_only',identity=identity,
        b_command=(f'PYTHONPATH=src {shlex.quote(str(VENV_PYTHON))} -B '
                   '-m agent_workload_characterization.runners.cpu_02_entry '
                   '--execute --i-approve-the-cpu-02-b'),
        authorization={'user_approval':'pending','tool_execution_permission':'pending'},
        limits=cfg['limits'])


def guarded(path, *, new=False):
    root=guard_cpu_root(PROJECT_ROOT,'CPU-02')
    path=Path(path)
    if not path.is_absolute():path=PROJECT_ROOT/path
    if '..' in path.parts or not path.is_relative_to(root):raise CPU02Error('output_outside_namespace')
    current=PROJECT_ROOT.resolve()
    for part in path.relative_to(current).parts:
        current=current/part
        if current.is_symlink():raise CPU02Error('output_symlink')
    real=path.resolve()
    for p in [PROJECT_ROOT/'references',PROJECT_ROOT/'data/raw',*_catalog_protected_roots(PROJECT_ROOT)]:
        p=p.resolve()
        if real==p or real.is_relative_to(p) or p.is_relative_to(real):raise CPU02Error('protected_output')
    if new and path.exists():raise CPU02Error('output_exists')
    return path


def write_json(path,payload):
    guarded(path,new=True)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x',encoding='utf-8') as fh:
        json.dump(payload,fh,indent=2,allow_nan=False);fh.write('\n')


def rewrite_json(path, payload):
    """Replace an already guarded report file without changing its path."""
    guarded(path)
    tmp=Path(path).with_name('.'+Path(path).name+'.tmp-'+uuid.uuid4().hex)
    with tmp.open('x',encoding='utf-8') as fh:
        json.dump(payload,fh,indent=2,allow_nan=False);fh.write('\n')
    os.replace(tmp,path)


def verify_approval(path,identity=None):
    path=guarded(path)
    if path!=APPROVAL:raise CPU02Error('approval_wrong_namespace')
    record=json.loads(path.read_text())
    if (record.get('checklist_identity')!=(identity or build_plan()['identity']) or
        record.get('approved') is not True or not record.get('approved_by') or not record.get('approved_at_utc')):
        raise CPU02Error('approval_identity_or_user_record')
    return record


def register_attempt(identity):
    guarded(ATTEMPT,new=True).parent.mkdir(parents=True,exist_ok=True)
    write_json(ATTEMPT,dict(status='started',identity=identity,
        started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))


def finish_marker(status,detail):
    path=guarded(ATTEMPT);record=json.loads(path.read_text())
    record.update(status=status,detail=detail)
    tmp=path.with_name('ATTEMPT_FINISH-'+uuid.uuid4().hex+'.json')
    write_json(tmp,record);os.replace(tmp,path)


def remaining(deadline, ceiling):
    rem=min(ceiling,deadline-time.monotonic())
    if rem<=0:raise CPU02Error('budget_exhausted')
    return rem


def cleanup_timeout(deadline, *, limit_s, on_exhausted):
    rem=deadline-time.monotonic()
    if rem<=0:
        on_exhausted();return .1
    return min(limit_s,rem)


# ---------------------------------------------------------------------------
# A1 pieces: supervisor protocol, PID mapping, perf attach readiness
# ---------------------------------------------------------------------------

def supervisor_command(verifier):
    source=SUPERVISOR.read_text()
    program=('ns={"__name__":"owned_cpu02_supervisor"};exec('+repr(source)+',ns);'
             'ns["main"]('+repr(verifier.EVAL_FILE)+')')
    return 'python3 -u -c '+shlex.quote(program)


def read_supervisor_ready(proc, timeout_s):
    """Read the supervisor's ready line with a real deadline, skipping (and
    keeping) non-JSON noise lines a login shell may print before it — a
    ready line alone still proves nothing until the PID mapping and the perf
    control ACK on the host side both succeed."""
    box={'lines':[], 'done': threading.Event()}
    def reader():
        try:
            while not box['done'].is_set():
                line=proc.stdout.readline()
                if not line:
                    box['eof']=True;break
                stripped=line.strip()
                if not stripped:continue
                try:
                    obj=json.loads(stripped)
                except ValueError:
                    box['lines'].append(('noise',stripped[:100]));continue
                box['lines'].append(('json',obj))
                if obj.get('event')=='supervisor_ready':
                    box['ready']=obj;break
        except (OSError,ValueError):
            box['eof']=True
    t=threading.Thread(target=reader,daemon=True);t.start();t.join(timeout_s)
    if t.is_alive():
        box['done'].set()
        return {'status':'timeout'}
    ready=box.get('ready')
    if ready is None:
        return {'status':'eof' if box.get('eof') else 'no_ready_line',
                'observed_noise':[l[1] for l in box['lines'] if l[0]=='noise'][:5]}
    if not ready.get('pid') or not ready.get('starttime_ticks'):
        return {'status':'identity_incomplete','raw':ready}
    return {'status':'ok','container_pid':int(ready['pid']),
            'starttime_ticks':int(ready['starttime_ticks']),'raw':ready}


def classify_proc_read_error(operation, target_pid, exc):
    """Project proc read failures to a non-sensitive diagnostic record."""
    code=getattr(exc,'errno',None)
    if code in (errno.EACCES,errno.EPERM): category='permission_denied'
    elif code in (errno.ENOENT,errno.ESRCH): category='process_missing_or_not_visible'
    else: category='unknown'
    return {'operation':operation,'target_pid':target_pid,
            'exception_type':type(exc).__name__,'errno':code,
            'category':category}


def map_container_pid(container_pid, starttime, init_host_pid, *, proc_root=None,
                      init_namespace=None, candidate_namespace_reader=None):
    """Container PID -> host PID, unambiguous or refused.

    The candidate must (1) show the container PID as the INNERMOST NSpid
    entry, (2) live in the same pid namespace as the container's init
    process (ns/pid inode compared against /proc/<init>/ns/pid), and
    (3) carry the supervisor-reported starttime (the kernel value is the
    same read from either namespace). A docker CLI client on the host is
    in the host namespace, so the inode check excludes it. Zero or
    multiple matches refuse the mapping; PID is never guessed."""
    root=Path(proc_root) if proc_root is not None else Path('/proc')
    if init_namespace is None:
        try:
            ns_ref=os.readlink(str(root/f'{init_host_pid}/ns/pid'))
        except OSError as exc:
            return {'status':'map_failed','reason':'init_ns_unreadable',
                    'read_error':classify_proc_read_error('init_ns',init_host_pid,exc)}
    else:
        ns_ref=init_namespace
    matches=[];read_errors=[]
    try:
        entries=[e for e in os.listdir(root) if e.isdigit()]
    except OSError as exc:
        return {'status':'map_failed','reason':'proc_unreadable',
                'read_error':classify_proc_read_error('proc_list',None,exc)}
    for entry in entries:
        try:
            status=(root/entry/'status').read_text(encoding='ascii',errors='replace')
            nsline=next((l for l in status.splitlines() if l.startswith('NSpid:')),None)
            if nsline is None:continue
            fields=nsline.split()[1:]
            if not fields or fields[-1]!=str(container_pid):continue
            stat=(root/entry/'stat').read_text(encoding='ascii',errors='replace')
            st_value=int(stat.rsplit(')',1)[1].split()[19])
            if st_value!=starttime:continue
            try:
                candidate_ns=os.readlink(str(root/entry/'ns/pid'))
            except OSError as exc:
                if (candidate_namespace_reader is None or
                        getattr(exc,'errno',None) not in (errno.EACCES,errno.EPERM)):
                    raise
                candidate_ns=candidate_namespace_reader(int(entry), container_pid, starttime)
            if candidate_ns!=ns_ref:continue
            matches.append(int(entry))
        except OSError as exc:
            # Keep only a safe category; never include paths, cmdline or
            # exception text in a diagnostic artifact.
            read_errors.append(classify_proc_read_error('candidate_proc',int(entry),exc))
            continue
        except (ValueError,IndexError,StopIteration):
            continue
    if len(matches)==1:
        return {'status':'ok','host_pid':matches[0],'namespace':ns_ref,
                'container_pid':container_pid,'starttime_ticks':starttime,
                'checks':'innermost_nspid+pidns_inode+starttime'}
    if not matches:
        result={'status':'map_failed','reason':'no_unique_match'}
        if read_errors:result['read_errors']=read_errors
        return result
    return {'status':'map_failed','reason':'ambiguous_matches','candidates':sorted(matches)}


def build_perf_supervisor_argv(supervisor_path, *, host_pid, starttime_ticks,
                               pgid, data_path, ctl_path, ack_path, deadline,
                               owner_uid=None):
    """Build the fixed, non-shell argv for the separately installed supervisor."""
    if not isinstance(host_pid, int) or host_pid <= 0:
        raise CPU02Error('invalid_perf_target_pid')
    if not isinstance(starttime_ticks, int) or starttime_ticks <= 0:
        raise CPU02Error('invalid_perf_target_starttime')
    if not isinstance(pgid, int) or pgid <= 0:
        raise CPU02Error('invalid_perf_target_pgid')
    if not isinstance(owner_uid, int) or owner_uid < 0:
        raise CPU02Error('invalid_perf_output_owner')
    return ['sudo','--non-interactive','--',str(supervisor_path),
            '--target-pid',str(host_pid),'--target-starttime',str(starttime_ticks),
            '--target-pgid',str(pgid),'--event','cycles','--frequency','99',
            '--output',str(data_path),'--owner-uid',str(owner_uid),
            '--control',str(ctl_path),'--ack',str(ack_path),
            '--deadline-monotonic',str(deadline)]


def start_perf_controlled(perf_bin, host_pid, data_path, *, cfg, output_dir,
                          sudo=False, supervisor_path=None, target_starttime=None,
                          target_pgid=None, deadline=None):
    """Launch host perf in attach mode under the DOCUMENTED control protocol.

    perf-record(1): ``--control=fifo:ctl-fifo[,ack-fifo]`` — listen on the
    ctl fifo for enable/disable/stop commands; each command's completion is
    sent as ``ack\\n`` on the ack fifo. ``-D -1`` starts the measurement
    with events DISABLED, so nothing is sampled while the barrier runs.
    The readiness barrier is a real protocol ACK ('enable' -> 'ack'), not
    Popen success, a sleep, or perf.data growth (which may be metadata)."""
    rd=cfg['perf']['readiness']
    ctl_path=output_dir/'perf_ctl.fifo';ack_path=output_dir/'perf_ack.fifo'
    data_created=False
    if sudo and (data_path.exists() or data_path.is_symlink()):
        raise CPU02Error('perf_data_path_not_exclusive')
    for p in (ctl_path,ack_path):
        if p.exists():raise CPU02Error('control_fifo_exists')
        os.mkfifo(p)
    # O_RDWR open on both sides so neither perf nor this process blocks
    ctl_fd=os.open(ctl_path,os.O_RDWR|os.O_NONBLOCK)
    ack_fd=os.open(ack_path,os.O_RDWR|os.O_NONBLOCK)
    argv=[perf_bin,'record','-D','-1','-F',str(cfg['perf']['record']['frequency_hz']),
          '-e',cfg['perf']['record']['event'],'-p',str(host_pid),'-o',str(data_path),
          '--control',f'fifo:{ctl_path},{ack_path}']
    launch_argv=(build_perf_supervisor_argv(supervisor_path,host_pid=host_pid,
                 starttime_ticks=target_starttime,pgid=target_pgid,data_path=data_path,
                 ctl_path=ctl_path,ack_path=ack_path,deadline=deadline,
                 owner_uid=os.getuid())
                 if supervisor_path is not None else
                 (['sudo','--non-interactive','--']+argv) if sudo else argv)
    if sudo:
        # Root perf must write a file that remains owned/readable by the
        # ordinary orchestrator.  Never relax permissions or follow a link.
        if data_path.exists() or data_path.is_symlink():
            raise CPU02Error('perf_data_path_not_exclusive')
        fd=os.open(data_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
        data_created=True
    try:
        proc=subprocess.Popen(launch_argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            start_new_session=True,text=True)
    except OSError as exc:
        os.close(ctl_fd);os.close(ack_fd)
        for p in (ctl_path,ack_path):
            try:p.unlink()
            except FileNotFoundError:pass
        if data_created:
            try:data_path.unlink()
            except FileNotFoundError:pass
        return {'status':'launch_failed','error':type(exc).__name__,'argv':launch_argv,
                'sudo_record':bool(sudo)}
    outputs={}
    drains=[threading.Thread(target=_drain,args=(proc.stdout,'stdout',1<<18,outputs)),
            threading.Thread(target=_drain,args=(proc.stderr,'stderr',1<<18,outputs))]
    for t in drains:t.start()
    # Capture the identity used for any later ordinary-user process-group
    # signal.  A bare PID/PGID is not sufficient: if the child has exited and
    # the identifier has been reused, cleanup must refuse to signal it.
    perf_starttime_ticks=None
    perf_pgid=None
    try:
        perf_starttime_ticks=read_starttime(proc.pid)
        perf_pgid=os.getpgid(proc.pid)
    except (OSError,ProcessLookupError):
        pass
    return {'status':'started','argv':launch_argv,'record_argv':argv,
            'perf_pid':proc.pid,'proc':proc,'sudo_record':bool(sudo),
            'perf_starttime_ticks':perf_starttime_ticks,'perf_pgid':perf_pgid,
            'drains':drains,'ctl_fd':ctl_fd,'ack_fd':ack_fd,
            'output_evidence':outputs,
            'ctl_path':str(ctl_path),'ack_path':str(ack_path),
            'ack_timeout_s':rd['ack_timeout_s']}


def control_cmd(perf, cmd, *, deadline=None, on_exhausted=None):
    """Send one control command and wait for the documented ACK. Returns the
    acknowledgement evidence; no ACK means the barrier is NOT confirmed."""
    import select
    timeout=perf['ack_timeout_s']
    if deadline is not None:
        timeout=min(timeout, max(0.0, deadline-time.monotonic()))
        if timeout<=0:
            if on_exhausted: on_exhausted()
            return {'cmd':cmd,'ack':False,'error':'budget_exhausted'}
    try:
        os.write(perf['ctl_fd'],f'{cmd}\n'.encode())
    except OSError as exc:
        return {'cmd':cmd,'ack':False,'error':type(exc).__name__}
    end=time.monotonic()+timeout
    while True:
        process=perf.get('proc')
        if process is not None:
            try:
                exit_code=process.poll()
            except (OSError,AttributeError):
                exit_code=None
            if exit_code is not None:
                return {'cmd':cmd,'ack':False,'error':'perf_exited_before_ack',
                        'process_exit_code':exit_code}
        remaining=end-time.monotonic()
        if remaining<=0:
            return {'cmd':cmd,'ack':False,'error':'ack_timeout'}
        r,_,_=select.select([perf['ack_fd']],[],[],min(0.05,remaining))
        if r:break
    try:
        data=os.read(perf['ack_fd'],64)
    except OSError as exc:
        return {'cmd':cmd,'ack':False,'error':type(exc).__name__}
    text=data.decode('ascii','replace').strip()
    return {'cmd':cmd,'ack':text=='ack','raw':text[:32]}


def stop_perf(perf, *, deadline, limit_s, on_exhausted):
    """Stop perf via the documented 'stop' command first, then escalate
    SIGINT/SIGKILL on the whole perf group; waits until the group is
    confirmed gone."""
    events=[]
    result=control_cmd(perf,'stop',deadline=deadline,on_exhausted=on_exhausted)
    events.append('stop_cmd_ack='+str(result['ack']))
    proc=perf['proc']
    wait_end=time.monotonic()+cleanup_timeout(deadline,limit_s=limit_s,
                                              on_exhausted=on_exhausted)
    while time.monotonic()<wait_end:
        if proc.poll() is not None and not _group_alive(proc.pid):
            events.append('stop_cmd:group_stopped');return events
        time.sleep(.05)
    def identity_matches():
        pid=perf.get('perf_pid')
        expected_start=perf.get('perf_starttime_ticks')
        expected_pgid=perf.get('perf_pgid')
        if not isinstance(pid,int) or pid<=0 or expected_start is None or expected_pgid is None:
            return False
        try:
            return (read_starttime(pid)==expected_start and os.getpgid(pid)==expected_pgid)
        except (OSError,ProcessLookupError):
            return False
    for sig in (signal.SIGINT,signal.SIGKILL):
        if not identity_matches():
            events.append('identity_changed_no_signal')
            return events
        try:os.killpg(proc.pid,sig)
        except (ProcessLookupError,PermissionError) as exc:
            events.append(f'{sig.name}:{type(exc).__name__}')
        wait_end=time.monotonic()+cleanup_timeout(deadline,limit_s=limit_s,
                                                  on_exhausted=on_exhausted)
        while time.monotonic()<wait_end:
            if proc.poll() is not None and not _group_alive(proc.pid):
                events.append(f'{sig.name}:group_stopped');return events
            time.sleep(.05)
        events.append(f'{sig.name}:group_alive_after_wait')
    return events


class ContainerReader(ScopeReader):
    def __init__(self,runtime,handle,scope):
        self.runtime,self.handle,self.scope=runtime,handle,scope
    def read(self,t):
        start=time.monotonic_ns()
        snap=self.runtime.read_counters(self.handle,t)
        snap.scope=self.scope;snap.scope_kind='agent_container'
        snap.read_status['read_latency_s']=str((time.monotonic_ns()-start)/1e9)
        return snap


def grade_eval(log_text, record, candidate, *, model_name):
    """Official grading semantics (make_test_spec + get_eval_report, the
    same chain SwebenchVerifierRunner uses). swebench imports are lazy so
    the offline suite never needs the venv."""
    if (not log_text.strip()
            or '>>>>> Start Test Output' not in log_text
            or '>>>>> End Test Output' not in log_text):
        return {'status':'tests_not_run','resolved':None,'infra_failure':None}
    from swebench.harness.utils import make_test_spec
    from swebench.harness.grading import get_eval_report
    import tempfile
    test_spec=make_test_spec(record)
    with tempfile.TemporaryDirectory() as tmp:
        log_path=Path(tmp)/'test_output.txt'
        log_path.write_text(log_text,encoding='utf-8')
        prediction={'instance_id':record['instance_id'],
                    'model_name_or_path':model_name,
                    'model_patch':candidate}
        report=get_eval_report(test_spec=test_spec,prediction=prediction,
                               test_log_path=str(log_path),include_tests_status=True)
        entry=report[record['instance_id']]
        return {'status':'ok','resolved':bool(entry.get('resolved')),
                'infra_failure':entry.get('infra_failure'),
                'test_status':{k:entry.get(k) for k in ('resolved','infra_failure')}}


def run_report_phase(perf_bin, data_path, *, symfs=None, runner=None, timeout_s=30):
    argv=[perf_bin,'report','--stdio','--no-children']
    if symfs is not None:argv+=['--symfs',str(symfs)]
    argv+=['-i',str(data_path)]
    run=runner or subprocess.run
    try:
        proc=run(argv,capture_output=True,text=True,timeout=timeout_s)
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'status':'failed','error':type(exc).__name__,'argv':argv}
    if proc.returncode!=0:
        return {'status':'nonzero_rc','returncode':proc.returncode,
                'stderr_tail':(proc.stderr or '')[-300:],'argv':argv}
    parsed=perf_adapter.parse_report(proc.stdout or '')
    if parsed['evidence_status']=='empty_output':
        # rc=0 with empty output is NOT a parsable profile
        return {'status':'empty_output','argv':argv,
                'stderr_tail':(proc.stderr or '')[-300:]}
    return {'status':'parsed','argv':argv,'stdout':proc.stdout or '',
            'parsed':parsed}


# ---------------------------------------------------------------------------
# A2 single production chain
# ---------------------------------------------------------------------------

def run_batch(runtime, output_dir, *, config=None, deadline=None, run_id=None,
              identity=None, preflight=None, perf_bin=None, proc_root=None,
              grader=None, report_runner=None, paranoid_check=True):
    config=json.loads(json.dumps(config or load_config()))
    lim=config['limits']
    deadline=deadline if deadline is not None else time.monotonic()+lim['batch_wall_s']
    perf_bin=perf_bin if perf_bin is not None else config['perf']['binary']
    output_dir=guarded(output_dir,new=True)
    guard_cpu_report(PROJECT_ROOT,output_dir,'CPU-02');output_dir.mkdir(parents=True)
    run_id=run_id or 'CPU-02-'+uuid.uuid4().hex
    payload=dict(run_id=run_id,status='pending',phases={},cleanup={},preflight=preflight,
        errors=[],budget_overrun=False,archive_status='pending')
    payload['clock_anchor']={'monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns(),
        'domain':'same_host_CLOCK_MONOTONIC',
        'assumption':'native docker and perf share host clocks'}
    payload['config_limits']=dict(lim)
    payload['scope_semantics']=('container CPU boundary is shared cgroup evidence, '
        'not per-function CPU seconds; function weights are period-weighted Self '
        'overhead; CPU-01 IPC/overhead numbers are NOT transferable')
    candidate=CANDIDATE.read_text()
    verifier=SwebenchVerifierRunner()
    overrun=lambda: payload.__setitem__('budget_overrun',True)
    work_deadline=deadline-lim['cleanup_reserve_s']
    def bytes_now():return sum(p.stat().st_size for p in output_dir.rglob('*') if p.is_file())
    def check():
        if bytes_now()>lim['report_threshold_mib']*2**20:
            raise CPU02Error('report_threshold_exceeded')
        remaining(work_deadline,lim['operation_s'])
    def threshold_breach():
        try:return bytes_now()>lim['report_threshold_mib']*2**20
        except OSError:return False
    handle=None;supervisor=None;perf=None;sampler=None
    data_path=output_dir/'perf.data'
    payload['perf_binary_sha256']=_file_sha_if_exists(perf_bin)
    record=json.loads(RECORD.read_text())
    prepare=dict(status='pending')
    payload['phases']['prepare']=prepare
    eval_script=None
    try:
        # This is intentionally before runtime.start(): evaluator drift or an
        # unavailable pinned venv must not create a container.
        eval_script,eval_identity=_load_generated_eval_script(record,
                                                               deadline=work_deadline)
        prepare['eval_script']=eval_identity
        # ---- container + official prepare (NOT part of the eval window) --
        remaining(work_deadline,lim['operation_s'])
        spec=ContainerSpec(run_id,SCOPE,config['workload']['image'],
            cpu_limit=str(lim['container_cpu']),mem_limit='8g',network='none',
            pull='never',platform='linux/arm64')
        handle=runtime.start(spec,timeout_s=remaining(work_deadline,lim['operation_s']))
        prepare.update(status='FAIL',container_id=handle.container_id)
        prepare_deadline=min(work_deadline,time.monotonic()+lim['prepare_wall_s'])
        def exec_cmd(cmd):
            return runtime.execute(handle,cmd,remaining(prepare_deadline,lim['operation_s']))
        w=exec_cmd(verifier.build_patch_heredoc(candidate))
        if w.get('returncode')!=0:
            prepare.update(status='infra_failure',detail='patch upload failed');raise CPU02Error('prepare_failed')
        applied=False;apply_results=[]
        for reset,apply_cmd in verifier.build_apply_chain():
            if reset:
                exec_cmd(reset)
            r=exec_cmd(apply_cmd)
            apply_results.append({'cmd':apply_cmd,'returncode':r.get('returncode')})
            if r.get('returncode')==0:applied=True;break
        if not applied:
            rev=exec_cmd(f'git apply --check --reverse {verifier.PATCH_FILE}')
            if rev.get('returncode')!=0:
                prepare.update(status='patch_apply_failed',detail='all official apply strategies failed',
                               apply_results=apply_results);raise CPU02Error('prepare_failed')
            applied=True
        e=exec_cmd(verifier.build_eval_heredoc(eval_script))
        if e.get('returncode')!=0:
            prepare.update(status='infra_failure',detail='eval script upload failed');raise CPU02Error('prepare_failed')
        prepare.update(status='ok',patch_applied=applied,apply_results=apply_results)
        check()
        # ---- supervisor + identity + mapping --------------------------------
        sup=dict(status='FAIL')
        payload['phases']['supervisor']=sup
        remaining(work_deadline,lim['operation_s'])
        supervisor=runtime.open_interactive(handle,supervisor_command(verifier),
            remaining(work_deadline,lim['operation_s']))
        ready=read_supervisor_ready(supervisor,remaining(work_deadline,lim['operation_s']))
        if ready['status']!='ok':
            sup.update(status='no_ready',detail=ready['status'],raw=ready.get('raw_line'))
            raise CPU02Error('supervisor_not_ready')
        sup.update(status='ready',container_pid=ready['container_pid'],
                   starttime_ticks=ready['starttime_ticks'],identity=ready['raw'])
        init_pid=runtime.container_init_pid(handle,timeout_s=remaining(work_deadline,lim['operation_s']))
        if not init_pid:
            sup.update(status='init_pid_unavailable');raise CPU02Error('mapping_failed')
        mapping=map_container_pid(ready['container_pid'],ready['starttime_ticks'],init_pid,proc_root=proc_root)
        sup['mapping']=mapping
        if mapping['status']!='ok':
            raise CPU02Error('mapping_failed')
        host_pid=mapping['host_pid']
        # host-side identity cross-check of the mapped PID
        host_start=read_starttime(host_pid)
        if host_start is not None and host_start!=ready['starttime_ticks']:
            sup.update(status='host_starttime_mismatch');raise CPU02Error('mapping_failed')
        check()
        # ---- perf attach + control-ACK barrier --------------------------------
        perf_phase=dict(status='FAIL',host_pid=host_pid)
        payload['phases']['perf']=perf_phase
        attach=start_perf_controlled(perf_bin,host_pid,data_path,cfg=config,
            output_dir=output_dir)
        perf_phase.update({k:v for k,v in attach.items()
                           if k not in ('proc','drains','ctl_fd','ack_fd')})
        if attach['status']=='launch_failed':
            raise CPU02Error('perf_launch_failed')
        perf=attach
        time.sleep(.2)  # let perf fail fast or reach its control loop
        if perf['proc'].poll() is not None:
            perf_phase['status']='unavailable'
            perf_phase['detail']='perf_exited_before_control'
            raise UnavailableSignal('perf_exited_early')
        enable_result=control_cmd(perf,'enable',deadline=deadline,on_exhausted=overrun)
        perf_phase['enable_ack']=enable_result
        if perf['proc'].poll() is not None or not enable_result['ack']:
            perf_phase['status']='unavailable'
            perf_phase['detail']='no_enable_ack'
            raise UnavailableSignal('perf_control_no_ack')
        perf_phase['status']='ready'
        perf_phase['window_open_monotonic_ns']=time.monotonic_ns()
        perf_phase['window_semantics']=('sampling window = [enable ack, '
            'disable ack] via perf-record(1) --control; eval window = '
            '[release, exec exit]; the sampling window encloses the eval '
            'window and waiting time is excluded by -D -1')
        check()
        # ---- resource baseline, release, eval window ------------------------
        sampler=ResourceSampler(interval_s=config['sampling']['interval_s'])
        sampler.register(SCOPE,'agent_container',ContainerReader(runtime,handle,SCOPE))
        sampler.start(SCOPE)
        payload['phases']['eval']=eval_phase=dict(status='FAIL')
        release_t=time.monotonic_ns()
        supervisor.stdin.write('{"cmd":"release"}\n');supervisor.stdin.flush()
        out_box={'chunks':[],'total':0}
        def drain_eval():
            try:
                while True:
                    line=supervisor.stdout.readline()
                    if not line:break
                    out_box['total']+=len(line)
                    if out_box['total']<=(4<<20):out_box['chunks'].append(line)
            except (OSError,ValueError):pass
            finally:
                # the reader thread owns the stdout pipe: closing here (EOF
                # or error) never deadlocks against a lingering writer
                try:supervisor.stdout.close()
                except (OSError,ValueError):pass
        reader=threading.Thread(target=drain_eval,daemon=True);reader.start()
        eval_deadline=min(deadline-lim['cleanup_reserve_s'],
                          time.monotonic()+lim['eval_wall_s'])
        timed_out=False
        next_sample=time.monotonic()+config['sampling']['interval_s']
        while supervisor.poll() is None:
            now=time.monotonic()
            if now>=eval_deadline:
                timed_out=True;break
            if now>=next_sample:
                sampler.sample_once()
                next_sample=now+config['sampling']['interval_s']
            if threshold_breach():
                payload['report_threshold_exceeded']=True
                raise CPU02Error('report_threshold_exceeded')
            time.sleep(.05)
        eval_end_t=time.monotonic_ns()
        try:sampler.stop(SCOPE)
        except Exception as exc:eval_phase['sampler_stop_error']=type(exc).__name__
        # close the sampling window with a documented disable ACK
        disable_result=control_cmd(perf,'disable',deadline=deadline,on_exhausted=overrun)
        perf_phase['disable_ack']=disable_result
        perf_phase['window_close_monotonic_ns']=time.monotonic_ns()
        if perf['proc'].poll() is not None:
            # sampling died while the eval was still running: keep evidence,
            # never claim a complete sampling window
            perf_phase['exited_before_stop']=True
        stop_events=stop_perf(perf,deadline=deadline,limit_s=lim['operation_s'],
                              on_exhausted=overrun)
        perf_phase['stop_events']=stop_events
        if stop_events and not any(ev.endswith(':group_stopped') for ev in stop_events):
            perf_phase['status']='stop_unconfirmed'
        # bounded drain FIRST, then assemble and persist the log — writing
        # before the reader joins would lose tail lines
        reader.join(timeout=cleanup_timeout(deadline,limit_s=lim['operation_s'],
                                            on_exhausted=overrun))
        eval_phase['reader_alive']=reader.is_alive()
        eval_output=''.join(out_box['chunks'])
        (output_dir/'eval_output.txt').write_text(eval_output,encoding='utf-8')
        eval_phase.update(eval_rc=supervisor.poll(),
            timed_out=timed_out,wall_s=(eval_end_t-release_t)/1e9,
            output_bytes_total=out_box['total'],
            release_monotonic_ns=release_t,eval_end_monotonic_ns=eval_end_t)
        if timed_out:
            eval_phase['status']='timeout'
            raise CPU02Error('eval_timeout')
        res=sampler.all_scope_evidence().get(SCOPE)
        payload['phases']['resource']=res
        bs=(res or {}).get('boundary_start') or {}
        be=(res or {}).get('boundary_end') or {}
        if bs.get('cpu_usage_usec') is None or be.get('cpu_usage_usec') is None:
            eval_phase['status']='cgroup_boundary_missing'
            raise CPU02Error('cgroup_boundary_missing')
        if be['cpu_usage_usec']<bs['cpu_usage_usec']:
            eval_phase['status']='cgroup_counter_reset'
            raise CPU02Error('cgroup_counter_reset')
        eval_phase['status']='executed'
        check()
        # ---- official grading ------------------------------------------------
        grade_fn=grader or grade_eval
        try:
            grade=grade_fn(eval_output,record,candidate,model_name='cpu-02-offline-a')
        except Exception as exc:
            payload['phases']['grade']=dict(status='infra_failure',error=type(exc).__name__)
            raise CPU02Error('grade_failed')
        payload['phases']['grade']=grade
        if grade.get('infra_failure'):
            raise CPU02Error('grade_infra_failure')
        check()
        # ---- symbols + report ------------------------------------------------
        symbols=dict(status='pending',files={},unresolved_dsos=[])
        payload['phases']['symbols']=symbols
        # first (bare) pass is ISOLATED from host symbols via an empty symfs
        empty_symfs=output_dir/'empty_symfs';empty_symfs.mkdir()
        report1=run_report_phase(perf_bin,data_path,symfs=empty_symfs,
            runner=report_runner,timeout_s=remaining(work_deadline,lim['operation_s']))
        if report1['status']!='parsed':
            symbols.update(status='report1_failed',report_status=report1['status'])
            payload['phases']['report']=dict(status=report1['status'],argv=report1.get('argv'))
            raise CPU02Error('report_failed')
        (output_dir/'report_raw_bare.txt').write_text(report1['stdout'],encoding='utf-8')
        payload['phases']['report']=dict(status='parsed_bare',parsed=report1['parsed'],
            argv=report1['argv'],
            bare_pass_note='host symbols isolated with an empty --symfs root')
        symbols_dir=output_dir/'symbols'
        dsos=sorted({r['dso'] for r in report1['parsed']['rows']
                     if r['dso'] and r['dso']!='[unknown]'})
        import base64 as _b64
        for dso in dsos:
            if not dso.startswith('/'):
                # short DSO names are NOT resolved by guessing paths
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'not_absolute_path'})
                continue
            verify_cmd=('python3 -c "import os,sys;'
                        'print(\'ok\' if os.path.isfile(sys.argv[1]) else \'no\')" '
                        +shlex.quote(dso))
            verify=runtime.execute(handle,verify_cmd,
                remaining(work_deadline,lim['operation_s']))
            if verify.get('returncode')!=0 or (verify.get('output') or '').strip()!='ok':
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'not_verified_in_container'})
                continue
            source_cmd=('python3 -c "import hashlib,os,sys;d=open(sys.argv[1],\'rb\').read();'
                        'print(str(len(d))+\' \'+hashlib.sha256(d).hexdigest())" '
                        +shlex.quote(dso))
            source=runtime.execute(handle,source_cmd,remaining(work_deadline,lim['operation_s']))
            try:
                source_parts=(source.get('output') or '').strip().split()
                source_bytes=int(source_parts[0]); source_sha=source_parts[1]
                if source.get('returncode')!=0 or len(source_parts)!=2 or len(source_sha)!=64:
                    raise ValueError
            except (ValueError,IndexError,TypeError):
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'source_integrity_unavailable'})
                continue
            # binary-safe copy: the container's python3 emits base64 (ASCII
            # through the text channel); the host decodes back to raw bytes
            fetch_cmd=('python3 -c "import base64,sys;'
                       'sys.stdout.write(base64.b64encode(open(sys.argv[1],\'rb\').read()).decode())" '
                       +shlex.quote(dso))
            fetch=runtime.execute(handle,fetch_cmd,
                remaining(work_deadline,lim['operation_s']),
                output_limit=lim['report_threshold_mib']*2**20)
            if (fetch.get('returncode')!=0 or fetch.get('output_truncated')
                    or not (fetch.get('output') or '').strip()):
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'container_read_failed'})
                continue
            try:
                data=_b64.b64decode(fetch['output'].strip(),validate=True)
            except (ValueError,TypeError):
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'base64_invalid'})
                continue
            decoded_sha=hashlib.sha256(data).hexdigest()
            if len(data)!=source_bytes or decoded_sha!=source_sha:
                symbols['unresolved_dsos'].append({'dso':dso,'reason':'source_integrity_mismatch',
                                                   'source_bytes':source_bytes,
                                                   'decoded_bytes':len(data)})
                continue
            target=symbols_dir/dso.lstrip('/')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
            symbols['files'][dso]={'bytes':len(data),'sha256':decoded_sha,
                                   'source_bytes':source_bytes,'source_sha256':source_sha}
            if threshold_breach():
                payload['report_threshold_exceeded']=True
                raise CPU02Error('report_threshold_exceeded')
        symbols['status']=('collected' if symbols['files']
                           else 'no_container_dsos')
        symbols['source_guarantee']=('a DSO is claimed container-sourced only '
            'when it is an absolute path, verified to exist inside THIS '
            'container, and copied binary-safe via container python3 base64; '
            'everything else stays unresolved with its reason')
        report2=run_report_phase(perf_bin,data_path,symfs=symbols_dir,
            runner=report_runner,timeout_s=remaining(work_deadline,lim['operation_s']))
        if report2['status']=='parsed':
            (output_dir/'report_raw_symfs.txt').write_text(report2['stdout'],encoding='utf-8')
            payload['phases']['report'].update(status='parsed_with_symfs',
                symfs_parsed=report2['parsed'],
                symfs_note=('symbols come from THIS batch container only; bare '
                            'addresses and [unknown] are kept, never faked by '
                            'host libraries with the same name'))
        else:
            payload['phases']['report'].update(symfs_status=report2['status'])
        check()
    except UnavailableSignal:
        pass
    except Exception as exc:
        payload['errors'].append(type(exc).__name__)
        payload['status']='FAIL'
    finally:
        # independent cleanup: in-container workload first (killing the perf
        # client or the docker exec client is NOT stopping the container
        # work), then the perf group, then the supervisor client, then the
        # container itself
        if handle is not None and hasattr(runtime,'terminate_workload'):
            try:
                payload['cleanup']['workload_termination']=runtime.terminate_workload(
                    handle,timeout_s=cleanup_timeout(deadline,limit_s=lim['operation_s'],
                                                     on_exhausted=overrun))
            except Exception as exc:
                payload['cleanup']['workload_termination']='error:'+type(exc).__name__
        if perf is not None and isinstance(perf,dict) and perf.get('proc') is not None:
            if perf['proc'].poll() is None:
                events=stop_perf(perf,deadline=deadline,limit_s=lim['operation_s'],
                                 on_exhausted=overrun)
                payload['cleanup']['perf_stop_events']=events
            for t in perf.get('drains') or []:
                t.join(timeout=1)
            for stream in (getattr(perf.get('proc'),'stdout',None),
                           getattr(perf.get('proc'),'stderr',None)):
                if stream is not None:
                    try: stream.close()
                    except (OSError,ValueError): pass
            for fd_key in ('ctl_fd','ack_fd'):
                fd=perf.get(fd_key)
                if fd is not None:
                    try:os.close(fd)
                    except OSError:pass
        if supervisor is not None:
            try:
                if supervisor.poll() is None:
                    supervisor.kill()
                supervisor.wait(timeout=cleanup_timeout(deadline,limit_s=lim['operation_s'],
                                                         on_exhausted=overrun))
                supervisor.stdin.close()
                for stream in (supervisor.stdout, supervisor.stderr):
                    if stream is not None:
                        try: stream.close()
                        except (OSError,ValueError): pass
                payload['cleanup']['supervisor']='reaped'
            except Exception as exc:
                payload['cleanup']['supervisor']='cleanup_error:'+type(exc).__name__
        if handle is not None:
            try:runtime.stop(handle,timeout_s=cleanup_timeout(deadline,limit_s=lim['operation_s'],on_exhausted=overrun))
            except Exception as exc:payload['cleanup']['stop_error']=type(exc).__name__
            try:payload['cleanup']['container']=runtime.verify_removal(handle,timeout_s=cleanup_timeout(deadline,limit_s=lim['operation_s'],on_exhausted=overrun))
            except Exception:payload['cleanup']['container']='check_failed'
            try:
                pending=runtime.cleanup_pending(timeout_s=cleanup_timeout(deadline,limit_s=lim['operation_s'],on_exhausted=overrun)) if hasattr(runtime,'cleanup_pending') else []
                payload['cleanup']['pending']=pending
            except Exception as exc:payload['cleanup']['pending_error']=type(exc).__name__
    if payload['status']=='pending':
        grade=payload['phases'].get('grade') or {}
        perf_phase=payload['phases'].get('perf') or {}
        eval_status=(payload['phases'].get('eval') or {}).get('status')
        report_status=(payload['phases'].get('report') or {}).get('status')
        cleanup=payload['cleanup']
        # the final state CONSUMES the cleanup results: an unconfirmed
        # container removal / supervisor reap / pending cleanup can never
        # yield complete (or unavailable-as-honest-result)
        cleanup_ok=(cleanup.get('container')=='removed'
                    and cleanup.get('supervisor')=='reaped'
                    and all(p.get('removed') is True
                            for p in (cleanup.get('pending') or [])))
        sampling_ok=(perf_phase.get('status')=='ready'
                     and not perf_phase.get('exited_before_stop')
                     and perf_phase.get('status')!='stop_unconfirmed'
                     and (perf_phase.get('enable_ack') or {}).get('ack')
                     and (perf_phase.get('disable_ack') or {}).get('ack'))
        if not cleanup_ok:
            payload['status']='FAIL'
        elif perf_phase.get('status')=='unavailable':
            payload['status']='unavailable'
        elif (eval_status=='executed' and grade.get('status')=='ok'
              and not grade.get('infra_failure')
              and report_status in ('parsed_bare','parsed_with_symfs')
              and sampling_ok):
            payload['status']='complete'
        else:
            # tests_not_run and infra_failure are recorded distinctly in
            # phases.grade but are NOT validation successes
            payload['status']='FAIL'
    try:
        payload['archive_status']='complete'
        payload['wall_s']=lim['batch_wall_s']-(deadline-time.monotonic())
        payload['budget_overrun'] |= time.monotonic()>deadline
        if payload['budget_overrun']: payload['status']='FAIL'
        if bytes_now()+len(json.dumps(payload,indent=2).encode()) > lim['report_threshold_mib']*2**20:
            payload['status']='FAIL';payload['report_threshold_exceeded']=True
        write_json(output_dir/'summary.json',payload)
        created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        for _ in range(2):
            outputs={str(p.relative_to(output_dir)):{'bytes':p.stat().st_size,'sha256':sha(p)}
                     for p in output_dir.rglob('*') if p.is_file() and p.name!='manifest.json'}
            manifest=dict(identity=identity or build_plan()['identity'],outputs=outputs,
                inputs=dict(catalog={'bytes':CATALOG.stat().st_size,'sha256':sha(CATALOG)},
                            record={'bytes':RECORD.stat().st_size,'sha256':sha(RECORD)},
                            candidate={'bytes':CANDIDATE.stat().st_size,'sha256':sha(CANDIDATE)},
                            supervisor={'bytes':SUPERVISOR.stat().st_size,'sha256':sha(SUPERVISOR)},
                            perf_binary=payload.get('perf_binary_sha256')),
                created_at_utc=created_at,status=payload['status'])
            if (output_dir/'manifest.json').exists(): rewrite_json(output_dir/'manifest.json',manifest)
            else: write_json(output_dir/'manifest.json',manifest)
            if time.monotonic()>deadline and not payload['budget_overrun']:
                payload['budget_overrun']=True;payload['status']='FAIL'
                rewrite_json(output_dir/'summary.json',payload)
                continue
            break
        actual=json.loads((output_dir/'manifest.json').read_text())['outputs']
        if actual!=outputs or any(sha(output_dir/p)!=v['sha256'] or
                (output_dir/p).stat().st_size!=v['bytes'] for p,v in actual.items()):
            raise CPU02Error('archive_hash_mismatch')
    except Exception as exc:
        payload.update(status='FAIL',archive_status='failed')
        payload['errors'].append(type(exc).__name__)
        try:
            if (output_dir/'summary.json').exists():
                rewrite_json(output_dir/'summary.json',payload)
        except Exception:
            payload['summary_rewrite_failed']=True
        try:write_json(output_dir/'archive_failure.json',{'status':'FAIL','category':type(exc).__name__})
        except Exception:pass
    # final budget verdict AFTER cleanup and archiving: wall spent in the
    # closing steps is part of the batch
    return payload


def _eval_script_from_catalog(record):
    """Offline-safe eval script source: the fixed record carries the exact
    official eval_script string; make_test_spec merely regenerates it. When
    the evaluator venv is importable the batch REFUSES on drift between the
    two; otherwise (offline suite) the record text is used and the check is
    recorded as not performed."""
    return record.get('eval_script')


def _file_sha_if_exists(path):
    try:return sha(path)
    except OSError:return None


def preflight_checks(*, deadline, runtime=None, perf_bin=None,
                     paranoid_path=None):
    perf_bin=perf_bin if perf_bin is not None else load_config()['perf']['binary']
    paranoid_path=paranoid_path if paranoid_path is not None else PARANOID_PATH
    checks={'perf_binary':Path(perf_bin).is_file() and os.access(perf_bin,os.X_OK),
            'venv_python':VENV_PYTHON.is_file(),
            'record':RECORD.is_file(),'candidate':CANDIDATE.is_file()}
    paranoid_value=None;paranoid_status='unreadable'
    try:
        paranoid_value=int(Path(paranoid_path).read_text().strip())
        paranoid_status='ok'
    except (OSError,ValueError):pass
    docker=None
    if runtime is not None:
        try:
            docker=runtime.preflight(deadline=deadline) if hasattr(runtime,'preflight') else None
        except Exception:
            docker=None
    return dict(status='READY' if all(checks.values()) else 'NOT_READY',
        checks=checks,perf_binary=perf_bin,
        perf_event_paranoid={'value':paranoid_value,'read_status':paranoid_status,
            'note':'recorded only; actual permission is a runtime result'},
        docker=docker)


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--i-approve-the-cpu-02-b',action='store_true')
    args=parser.parse_args(argv)
    if not args.execute and not args.i_approve_the_cpu_02_b:
        print(json.dumps(build_plan(),indent=2));return 0
    if not (args.execute and args.i_approve_the_cpu_02_b):return 2
    try:
        plan=build_plan();identity=plan['identity']
        verify_approval(APPROVAL,identity);register_attempt(identity)
    except Exception as exc:
        print('REFUSED:'+type(exc).__name__);return 3
    deadline=time.monotonic()+plan['limits']['batch_wall_s']
    rc=5;detail='execution_failed'
    from .g1_02_entry import local_docker_environment
    from .container_runtime import DockerCliRuntime
    try:
        with local_docker_environment():
            # the SAME fixed local endpoint now covers preflight AND every
            # runtime call in this process — no remote context or env
            # override can silently move the batch elsewhere
            preflight=preflight_checks(deadline=deadline)
            preflight['docker']=docker_preflight(deadline=deadline)
            write_json(guarded(APPROVAL.parent/'PREFLIGHT.json',new=True),preflight)
            if preflight['status']!='READY' or preflight['docker']['status']!='READY':
                rc=4;detail='preflight_failed'
            else:
                batch='CPU-02-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
                result=run_batch(DockerCliRuntime(authorized=True,collection='CPU-02'),
                    APPROVAL.parent/batch,config=identity['config'],deadline=deadline,
                    run_id=batch,identity=identity,preflight=preflight)
                rc=0 if result['status'] in ('complete','unavailable') and result['archive_status']=='complete' else 5
                detail=(f"eval_{(result['phases'].get('eval') or {}).get('status','absent')}"
                        f"_grade_{(result['phases'].get('grade') or {}).get('status','absent')}"
                        f"_sampling_{(result['phases'].get('perf') or {}).get('status','absent')}")
    except Exception as exc:detail=type(exc).__name__
    try:finish_marker('completed' if rc==0 else 'failed',detail)
    except Exception:rc=5
    print(json.dumps({'returncode':rc,'detail':detail}))
    return rc


def docker_preflight(*, deadline, runner=None, image=None):
    """Same fixed local-endpoint/digest preflight G1-02 uses."""
    runner=runner or subprocess.run
    image=image or load_config()['workload']['image']
    checks={}
    for name,args in [('context',['context','show']),('image',['image','inspect',image,'--format','{{.Os}}/{{.Architecture}}'])]:
        try:
            proc=runner(['docker',*args],capture_output=True,text=True,timeout=remaining(deadline,15))
            checks[name]=proc.returncode==0 and proc.stdout.strip()==('default' if name=='context' else 'linux/arm64')
        except Exception as exc:
            return dict(status='NOT_READY',checks=checks,category=type(exc).__name__)
        if not checks[name]:return dict(status='NOT_READY',checks=checks,category=name+'_unverified')
    return dict(status='READY',checks=checks,endpoint='unix:///var/run/docker.sock',image=image)


if __name__=='__main__':
    raise SystemExit(main())
