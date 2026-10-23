"""Stream and audit normalized SWE-rebench evidence; execute no saved commands."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import re
import shlex
from collections import Counter, defaultdict
from pathlib import Path

import swe_rebench_behavior as behavior

ROOT=Path(__file__).resolve().parents[1]
RAW=Path(behavior.PREFIX)
BASE=Path('reports/analysis/SWE-REBENCH-behavior-v2')
OPERATIONS=Path('reports/analysis/PUBLIC-TRACE-OPERATIONS-v3')
OUT=Path('reports/analysis/SWE-REBENCH-behavior-v3')
SAFE_TOOL=re.compile(r'^[A-Za-z_][A-Za-z0-9_.:-]{0,99}$')


def record(path):
    path=Path(path);data=path.read_bytes()
    try:name=str(path.relative_to(ROOT))
    except ValueError:name=str(path)
    return {'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def noninvocation_error(error):
    if isinstance(error,dict):return error.get('type')=='tool_call_not_invoked'
    if not isinstance(error,str):return False
    try:value=json.loads(error)
    except ValueError:value=None
    if isinstance(value,dict):return value.get('type')=='tool_call_not_invoked'
    return re.fullmatch(r"\{\s*(['\"])type\1\s*:\s*(['\"])tool_call_not_invoked\2\s*\}",error) is not None


def submit_intent(event):
    name=event.get('tool')
    if name=='submit':return True
    if name not in ('bash_terminal','Bash','bash','shell','terminal'):return False
    value=event.get('input')
    if isinstance(value,dict):value=value.get('command')
    if isinstance(value,list) and all(isinstance(x,str) for x in value):args=value
    elif isinstance(value,str):
        try:args=shlex.split(value)
        except ValueError:return False
    else:return False
    return args==['submit']


def protocol_review(events):
    calls=defaultdict(list);returns=defaultdict(list);missing=[]
    for i,event in enumerate(events):
        if event.get('type')=='tool_call':calls[event.get('tool_call_id')].append((i,event))
        elif event.get('type')=='tool_result':
            if event.get('tool_call_id') is None:missing.append((i,event))
            else:returns[event['tool_call_id']].append((i,event))
    counts=Counter();unpaired=[];nonids=[]
    for cid,entries in calls.items():
        if cid is not None and len(entries)==1 and len(returns.get(cid,[]))==1:counts['unique_id_pairs']+=1
        elif cid is not None and not returns.get(cid):
            for i,event in entries:
                kind='submit_request_without_saved_return' if submit_intent(event) else 'other_request_without_saved_return'
                counts[kind]+=1;unpaired.append((i,event,kind))
        else:counts['ambiguous_call_entries']+=len(entries)
    for i,event in missing:
        kind='explicit_tool_not_invoked' if noninvocation_error(event.get('error')) else 'unidentified_result_without_id'
        counts[kind]+=1;nonids.append((i,event,kind))
    counts['orphan_return_ids']=sum(cid not in calls for cid in returns)
    counts['call_entries']=sum(len(v) for v in calls.values());counts['return_entries']=sum(len(v) for v in returns.values())+len(missing)
    return dict(counts),unpaired,nonids


def availability(value):
    if value is None:return 'null_or_absent'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,(int,float)) and math.isfinite(value):return 'finite_nonnegative' if value>=0 else 'negative'
    return 'unsupported_or_nonfinite'


def run():
    if OUT.exists():raise FileExistsError(OUT)
    inputs={}
    def read(entry):
        path=Path(entry['path']);data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if len(data)!=entry['bytes'] or digest!=entry['sha256']:raise ValueError('frozen file mismatch: '+str(path))
        inputs[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    code=[record(Path(__file__)),record(ROOT/'tests/test_swe_rebench_review_v3.py')]
    previous=json.loads(read(record(BASE/'manifest.json')))
    for entry in previous['inputs']+previous['outputs']:read(entry)
    analyzer=previous['analyzer'];assert behavior.sha256(Path(analyzer['path']))==analyzer['sha256']
    read(record(analyzer['path']))
    oldrows={r['trajectory_id']:r for r in map(json.loads,(BASE/'per_trajectory.jsonl').open())}
    oldsummary=json.loads((BASE/'summary.json').read_text())
    operation_manifest=json.loads(read(record(OPERATIONS/'manifest.json')))
    bound={e['path']:e for e in operation_manifest['outputs']}
    operation_path=OPERATIONS/'per_trajectory.jsonl'
    read(bound[str(operation_path)])
    for entry in operation_manifest['inputs']:
        if entry['path'] in ('scripts/public_trace_operations.py','src/agent_workload_characterization/analyzers/public_operations.py'):read(entry)
    operations={r['location']['trajectory_id']:r for r in map(json.loads,operation_path.open()) if r['source']=='SWE-rebench'}
    if len(operations)!=9435 or len(oldrows)!=9435:raise ValueError('baseline scope mismatch')
    for name in ('manifest.json','index.jsonl','README.md','schema.json'):read(record(RAW/name))
    source_manifest=json.loads((RAW/'manifest.json').read_text())
    index=[json.loads(line) for line in (RAW/'index.jsonl').open()]
    shards={s['path']:s for s in previous['shards']}
    identities=set();trajectories=[];anomalies=[];step_rows=[];issues=[]
    by_participant=defaultdict(Counter);event_fields=defaultdict(Counter);step_prefixes=defaultdict(Counter)
    duration_fields=defaultdict(Counter);usage_fields=defaultdict(Counter)
    totals=Counter();evaluation_cross=Counter();normalization=Counter();operation_totals=Counter();operation_presence=Counter()
    for shard_idx,item in enumerate(index,1):
        path=RAW/item['path'];frozen=shards[item['path']]
        read({**frozen,'path':str(path)})
        content_hash=hashlib.sha256();rows=0;shard_events=0
        with gzip.open(path,'rb') as stream:
            for line_no,line in enumerate(stream,1):
                content_hash.update(line);rows+=1
                rec=json.loads(line);tid=rec['trajectory_id'];old=oldrows[tid];operation=operations[tid]
                participant=rec['participant']['key'];task=rec['instance_id'];run_index=rec['run']['index']
                identity=(participant,task,run_index)
                if identity in identities:raise ValueError('duplicate native identity')
                identities.add(identity)
                if (old['participant'],old['task_id'],old['run_index'])!=identity:raise ValueError('baseline identity mismatch')
                if operation['location']['path']!=str(path) or operation['location']['line']!=line_no or operation['task']!=task:raise ValueError('operation row identity mismatch')
                events=rec['events'];types=Counter(e['type'] for e in events);shard_events+=len(events)
                protocol,unpaired,nonids=protocol_review(events)
                if protocol.get('ambiguous_call_entries',0) or protocol['orphan_return_ids']:raise ValueError('unexpected duplicate/orphan protocol')
                assert protocol['call_entries']==old['tool_call_count']==operation['unit_count']
                assert protocol['return_entries']==old['tool_result_count']
                totals.update(protocol);by_participant[participant].update(protocol)
                totals['events']+=len(events);totals['trajectories']+=1;totals['agent_step_events']+=types['agent_step']
                by_participant[participant]['trajectories']+=1;by_participant[participant]['agent_step_events']+=types['agent_step']
                by_participant[participant]['trajectories_with_standard_calls']+=bool(types['tool_call'])
                by_participant[participant]['trajectories_with_agent_steps']+=bool(types['agent_step'])
                if rec['evaluation'].get('evaluation_matches_selected') is not True:issues.append({'trajectory_id':tid,'reason':'evaluation_not_confirmed_selected'})
                ev=rec['evaluation'];evaluation_cross[(participant,ev['agent_exit_status'],ev['status'],ev['resolved'])]+=1
                expected={'resolved':True,'failed':False,'skipped':False}
                if ev['status'] in expected and type(ev['resolved']) is bool and expected[ev['status']] is not ev['resolved']:
                    issues.append({'trajectory_id':tid,'reason':'status_and_resolved_conflict'})
                norm=rec['normalization']
                for key in ('truncated_tool_results','cache_tool_results_omitted'):normalization[key]+=norm.get(key,0)
                usage=rec['usage']
                for key in ('model_calls','steps','tool_calls','wall_time_seconds','cost_usd'):
                    usage_fields[participant][key+':'+availability(usage.get(key))]+=1
                for event in events:
                    kind=event['type'];event_fields[kind].update(event.keys())
                    for field in ('duration_ms','elapsed_ms'):
                        if field in event:duration_fields[participant][kind+':'+field+':'+availability(event[field])]+=1
                    if kind=='agent_step':
                        name=event.get('name') or '';prefix=name.split(maxsplit=1)[0] if isinstance(name,str) and name.strip() else '<missing>'
                        step_prefixes[participant][prefix]+=1
                for event_idx,event,kind in unpaired:
                    name=event.get('tool');safe=name if isinstance(name,str) and SAFE_TOOL.fullmatch(name) else '<unparsed_tool_identity>'
                    anomalies.append({'trajectory_id':tid,'participant':participant,'task_id':task,'run':run_index,
                                      'event_index':event_idx,'seq':event.get('seq'),'call_id':event.get('tool_call_id'),
                                      'kind':kind,'tool':safe,'input_sha256':hashlib.sha256(json.dumps(event.get('input'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
                for event_idx,event,kind in nonids:
                    anomalies.append({'trajectory_id':tid,'participant':participant,'task_id':task,'run':run_index,
                                      'event_index':event_idx,'seq':event.get('seq'),'call_id':None,'kind':kind,'status':event.get('status')})
                operation_totals.update(operation['operation_counts']);operation_presence.update(operation['operation_call_presence_counts'])
                trajectories.append({'trajectory_id':tid,'participant':participant,'task_id':task,'run_index':run_index,
                                     'source':{'path':str(path),'line':line_no},'event_types':dict(types),'protocol_review':protocol,
                                     'operation_counts':operation['operation_counts'],
                                     'operation_call_presence_counts':operation['operation_call_presence_counts'],
                                     'native_tool_counts':operation['native_tool_counts'],
                                     'normalization':norm,'evaluation':ev,'reported_usage':usage,
                                     'event_duration_fields_not_reinterpreted':old['duration_ms']})
        if content_hash.hexdigest()!=item['content_sha256'] or content_hash.hexdigest()!=frozen['content_sha256']:
            raise ValueError('uncompressed content hash mismatch')
        if rows!=111 or rows!=item['rows'] or shard_events!=item['events']:raise ValueError('index rows/events mismatch')
        if shard_idx%10==0:print(f'verified and reviewed {shard_idx}/85 shards',flush=True)
    assert len(identities)==9435 and totals['call_entries']==598148 and totals['return_entries']==616980
    assert totals['unique_id_pairs']==589061
    assert totals['submit_request_without_saved_return']+totals['other_request_without_saved_return']==9087
    assert totals['explicit_tool_not_invoked']+totals['unidentified_result_without_id']==27919
    assert totals['events']==source_manifest['events']
    assert normalization['truncated_tool_results']==source_manifest['truncated_tool_results']
    assert normalization['cache_tool_results_omitted']==source_manifest['cache_tool_results_omitted']
    assert sum(operation_totals.values())==598148
    OUT.mkdir(parents=True)
    for name,rows in [('per_trajectory.jsonl',trajectories),('protocol_evidence.jsonl',anomalies)]:
        with (OUT/name).open('w') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    def csv_out(name,fields,rows):
        with (OUT/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fields);writer.writeheader();writer.writerows(rows)
    columns=sorted(set(k for p in by_participant.values() for k in p))
    csv_out('participant_protocol.csv',['participant']+columns,
            [{'participant':p,**{k:c.get(k,0) for k in columns}} for p,c in sorted(by_participant.items())])
    csv_out('evaluation_exit_cross_tab.csv',['participant','agent_exit_status','evaluation_status','resolved','trajectories'],
            [{'participant':k[0],'agent_exit_status':k[1],'evaluation_status':k[2],'resolved':k[3],'trajectories':v} for k,v in sorted(evaluation_cross.items(),key=lambda x:str(x[0]))])
    strata=defaultdict(list)
    for row in trajectories:
        for operation in sorted(operation_presence):
            strata[(row['participant'],row['evaluation']['status'],operation)].append(row['operation_call_presence_counts'].get(operation,0))
    strata_rows=[]
    for (p,status,op),values in sorted(strata.items()):
        strata_rows.append({'participant':p,'evaluation_status':status,'operation':op,'n':len(values),
                            'median':behavior.percentile(values,.5),'iqr':behavior.iqr(values),'total_call_presence':sum(values)})
    csv_out('operation_result_strata.csv',['participant','evaluation_status','operation','n','median','iqr','total_call_presence'],strata_rows)
    summary={'schema':'swe-rebench-protocol-and-operation-review-v3','source':'third_party_normalized_corpus_without_patches',
             'scope':{'shards':85,'trajectories':9435,'tasks':111,'participants':17,'runs_per_participant':5},
             'protocol_totals':dict(totals),'participant_protocol':{p:dict(c) for p,c in sorted(by_participant.items())},
             'operation_counts_reused_from_frozen_v3':dict(operation_totals),'operation_presence_counts':dict(operation_presence),
             'source_normalization_totals':dict(normalization),'event_field_inventory':{k:dict(v) for k,v in event_fields.items()},
             'event_duration_field_inventory':{k:dict(v) for k,v in duration_fields.items()},
             'source_usage_field_inventory':{k:dict(v) for k,v in usage_fields.items()},
             'agent_step_caption_prefixes':{k:dict(v) for k,v in step_prefixes.items()},
             'evaluation_status_counts':dict(Counter(row['evaluation']['status'] for row in trajectories)),
             'agent_exit_status_counts':dict(Counter(row['evaluation']['agent_exit_status'] for row in trajectories)),
             'evaluation_identity_or_consistency_issues':issues,
             'rules':{'association':'unique ID only; no positional reconstruction; non-invocation reports kept separate',
                      'submit':'explicit submission request is intent, not proof of normal exit or successful task',
                      'junie':'agent_step captions are preserved process evidence, not reconstructed native tool invocations',
                      'semantics':'reuse frozen PUBLIC-TRACE-OPERATIONS-v3, no fresh reinterpretation of shell text',
                      'timing':'duration_ms/elapsed_ms and source usage are metadata, not resources or measured tool wall time'},
             'old_raw_and_reports_preserved':True,'agent_model_command_or_benchmark_executed':False}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    # Produce final wording after reviewing the actual complete-file counters.
    for entry in list(inputs.values())+code:read(entry)
    (OUT/'manifest.json').write_text(json.dumps({'schema':'swe-rebench-review-v3-manifest','inputs':list(inputs.values()),
                                              'analysis_code_and_tests':code,'outputs':[record(p) for p in sorted(OUT.iterdir()) if p.is_file()]},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'scope':summary['scope'],'protocol_totals':summary['protocol_totals'],
                      'evaluation_issues':len(issues),'normalization':dict(normalization)},ensure_ascii=False),flush=True)


if __name__=='__main__':run()
