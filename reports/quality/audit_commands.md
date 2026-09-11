# P0-00 r2 只读检查记录

以下命令于本次返修实际执行；只读解析并输出到 stdout，未导入旧应用模块、运行 pipeline 或写入来源。输出经 apply_patch 保存为 audit_evidence.json。它们是审计记录，不是项目 CLI。

## 全量字段扫描与文件证据

```bash
python3 - <<'PY'
import json, hashlib, collections, zipfile, pathlib, datetime, subprocess
b=pathlib.Path('/home/lcq/agent_workload/benchmark')
p=pathlib.Path('/home/lcq/agent_workload_characterization')
out={'audited_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'roots':{'benchmark':str(b),'project':str(p),'analysis':str(b/'benchmark_analysis/src/agent_trace_analysis'),'runtime':'/home/lcq/agent_vm_bench'},'files':{},'counts':{},'samples':{},'methods':{}}
def register(path, digest=True):
 st=path.stat()
 key=str(path)
 if key not in out['files']:
  h=None
  if digest:
   hh=hashlib.sha256()
   with path.open('rb') as f:
    for chunk in iter(lambda:f.read(1024*1024), b''): hh.update(chunk)
   h=hh.hexdigest()
  out['files'][key]={'size_bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':h,'hash_status':'computed' if digest else 'not_computed_large_archive'}
def rows(rel):
 path=b/rel
 register(path)
 with path.open() as f:return [json.loads(x) for x in f if x.strip()]
# AgentX full recursive field scan, no payload text output.
path=b/'agent_benchmark_traces/agentx_256k/traces.jsonl'
tot=collections.Counter(); minimum=None; subminimum=None; missing=None
h=hashlib.sha256()
def walk(reqs,prefix='requests'):
 for i,r in enumerate(reqs):
  loc=f'{prefix}[{i}]'
  yield loc,r
  if r.get('type')=='subagent':yield from walk(r.get('requests',[]),loc+'.requests')
with path.open('rb') as f:
 for ln,raw in enumerate(f,1):
  h.update(raw)
  if not raw.strip():continue
  d=json.loads(raw); flat=list(walk(d.get('requests',[])))
  model=[(loc,r) for loc,r in flat if r.get('type')!='subagent']
  groups=[(loc,r) for loc,r in flat if r.get('type')=='subagent']
  totals={'main_requests':sum(r.get('type')!='subagent' for r in d.get('requests',[])),'model_requests':len(model),'subagent_groups':len(groups),'input_tokens':sum(r.get('in') or 0 for _,r in model),'output_tokens':sum(r.get('out') or 0 for _,r in model)}
  tot.update(totals);tot['sessions']+=1
  tot['groups_missing_tool_use_count']+=sum(r.get('tool_use_count') is None for _,r in groups)
  tot['requests_missing_api_time']+=sum(r.get('api_time') is None for _,r in model)
  sample={'path':str(path),'line_1based':ln,'session_id':d.get('id'),'expected':totals}
  if minimum is None or len(model)<minimum['expected']['model_requests']:
   minimum={**sample,'request_scalars':[{'selector':loc,**{k:r.get(k) for k in ['type','in','out','t','api_time']}} for loc,r in model]}
  if groups and (subminimum is None or len(model)<subminimum['expected']['model_requests']):
   subminimum={**sample,'groups':[{'selector':loc,'agent_id':r.get('agent_id'),'child_request_count':len(r.get('requests',[])),'tool_use_count':r.get('tool_use_count')} for loc,r in groups]}
  if missing is None:
   for loc,r in model:
    if r.get('api_time') is None:missing={**sample,'selector':loc};break
out['counts']['agentx']=dict(tot)
st=path.stat();out['files'][str(path)]={'size_bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':h.hexdigest(),'hash_status':'computed'}
out['samples']['agentx_minimum']=minimum
out['samples']['agentx_subagent']=subminimum
out['samples']['agentx_missing_api_time']=missing
out['methods']['agentx']='Parse all nonblank JSONL rows; recursively visit requests; type=subagent is group, other types counted as model requests. Tokens summed over model records; no turn inference.'
# Applied all template records
ac={}
for path in sorted((b/'agent_benchmark_traces/applied_compute').glob('*.jsonl')):
 rr=rows(str(path.relative_to(b)))
 ac[path.name]={'records':len(rr),'num_turns_distribution':dict(sorted(collections.Counter(r.get('num_turns') for r in rr).items()))}
 for ln,d in enumerate(rr,1):
  n=d.get('num_turns')
  if n in [0,2] and f'applied_n{n}' not in out['samples']:
   inputs=[d['input_prompt_length']]
   for o,t in zip(d['assistant_response_length'],d['tool_call_output_length']):inputs.append(inputs[-1]+o+t)
   out['samples'][f'applied_n{n}']={'path':str(path),'line_1based':ln,'record':d,'expected_template':{'model_requests':n+1,'input_contexts':inputs,'total_input_tokens':sum(inputs),'max_context_tokens':max(inputs),'total_output_tokens':sum(d['assistant_response_length'])+d['final_assistant_response_length']}}
out['counts']['applied_compute']=ac
# sidecar current and archived; row counts, association/state breakdown
side={}
for base in ['traces_generation/sidecar','trace_cleanup_archive/20260908T060905Z/sidecar_before']:
 for ds in ['docops','agentic_vbench','videoweaver','workarena']:
  key=base+'/'+ds; entry={}
  for table in ['run_manifest','model_calls','tool_calls']:
   path=b/key/(table+'.jsonl')
   if not path.exists():entry[table]={'status':'missing'};continue
   rr=rows(str(path.relative_to(b)))
   extra={}
   if table=='run_manifest':
    for field in ['agent','execution_status','evaluation_status','archive_status']:
     extra[field]=dict(collections.Counter(str(r.get(field)) for r in rr))
   if table=='model_calls':
    extra['association_status']=dict(collections.Counter(str(r.get('association_status')) for r in rr))
    extra['by_trace_id']=dict(collections.Counter(str(r.get('trace_id')) for r in rr))
   entry[table]={'rows':len(rr),**extra}
  side[key]=entry
out['counts']['sidecar']=side
# Raw vs selected video telemetry join on actual call ids
raw=rows('telemetry/video_weaver.jsonl'); selected=rows('traces_generation/sidecar/videoweaver/model_calls.jsonl')
rawkeys=collections.Counter((r.get('trace_id'),r.get('call_id')) for r in raw)
selkeys=collections.Counter((r.get('trace_id'),r.get('call_id')) for r in selected)
out['counts']['video_raw']={'rows':len(raw),'unique_trace_call_pairs':len(rawkeys),'duplicate_pair_rows':sum(n-1 for n in rawkeys.values()),'by_trace_id':dict(collections.Counter(str(r.get('trace_id')) for r in raw)),'selected_rows':len(selected),'selected_pairs_absent_from_raw':len(set(selkeys)-set(rawkeys)),'raw_pairs_not_selected':len(set(rawkeys)-set(selkeys))}
# Zip member inspection; no extraction.
for name,rel,suffix in [('osworld','osworld_verified/autoglm_50steps.zip','traj.jsonl'),('spreadsheet','spreadsheetbench_v2/trajectory_example.zip','.traj')]:
 path=b/'agent_benchmark_traces'/rel;register(path,False)
 with zipfile.ZipFile(path) as z:
  members=[n for n in z.namelist() if not n.endswith('/')]
  traces=[n for n in members if n.endswith(suffix)]
  entry={'member_count':len(members),'trajectory_members':len(traces),'result_members':sum(n.endswith('/result.txt') for n in members)}
  if name=='spreadsheet':
   groups=collections.defaultdict(list)
   for n in traces:groups[pathlib.PurePosixPath(n).stem].append(n)
   collisions={k:v for k,v in groups.items() if len(v)>1}
   entry.update({'unique_legacy_task_keys':len(groups),'colliding_legacy_keys':len(collisions),'members_in_collisions':sum(map(len,collisions.values())),'collision_example':next(iter(collisions.items()),None)})
  out['counts'][name]=entry
# SWE file paths, not parsed run count.
swe=b/'agent_benchmark_traces/swebench_experiments/verified'
out['counts']['swe_trajectory_files']={}
for sub in sorted(swe.iterdir()):
 if sub.is_dir():
  fs=[x for x in sub.rglob('*') if x.is_file() and (x.suffix=='.traj' or (x.suffix=='.json' and 'trajs' in x.parts))]
  out['counts']['swe_trajectory_files'][sub.name]={'files':len(fs),'example_path':str(fs[0]) if fs else None}
for manifest in ['bench_manifest.full.jsonl','bench_manifest.verified.jsonl']:
 rr=rows('agent_benchmark_traces/tracebench/'+manifest)
 out['counts'][manifest]={'rows':len(rr),'first_record_keys':list(rr[0]) if rr else []}
rr=rows('agent_benchmark_traces/mlperf_edge_agentic/agentic_coding_2.5h.jsonl')
out['counts']['mlperf']={'rows':len(rr),'conversation_ids':len({r.get('conversation_id') for r in rr}),'missing_conversation_id':sum(r.get('conversation_id') is None for r in rr)}
# archive lists are lists, not directories or deduplicated trial population.
path=b/'trace_cleanup_archive/20260908T060905Z/manifest.json';register(path);d=json.loads(path.read_text())
out['counts']['cleanup']={k:{'entries':len(d[k]),'by_dataset':dict(collections.Counter(x.get('dataset') for x in d[k]))} for k in ['keep','move']}
# local source manifest and file locator only
bundles=b/'agent_benchmark_traces/gen_videoweaver_traces/bundles'
out['counts']['video_bundles']=[]
for path in sorted(bundles.glob('*/manifest.json')):
 register(path);d=json.loads(path.read_text())
 out['counts']['video_bundles'].append({'path':str(path),'trace_id':d.get('trace_id'),'keys':list(d)})
 if 'text_long_video' in str(path):
  out['samples']['video_bundle']={'path':str(path),'trace_id':d.get('trace_id'),'trajectory':d.get('trajectory') or d.get('generation_trajectory'),'model_telemetry':d.get('model_telemetry')}
# source code hashes, not executing imports/pipeline
for path in sorted((b/'benchmark_analysis/src/agent_trace_analysis').rglob('*.py')):register(path)
for rel in ['traces_generation/sidecar/gen_sidecar.py','telemetry_proxy/proxy.py','telemetry_proxy/export_trace.py','traces_generation/TELEMETRY_SUMMARY.md','benchmark_analysis/analysis_output/ingest_summary.json','agent_benchmark_traces/agentx_256k/README.md']:
 path=b/rel
 if path.is_file():register(path)
refs={}
for path in sorted((p/'references/repos').iterdir()):
 if path.is_dir():
  r=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True)
  refs[path.name]={'path':str(path),'head':r.stdout.strip() if r.returncode==0 else None}
out['reference_heads']=refs
out['methods']['sidecar']='JSON parse every nonblank line; counts are derived rows, not independently verified original runs. archived and current paths counted separately.'
out['methods']['archives']='zip central directory only, no extraction; cleanup manifest keep/move list lengths are not unique task/run counts.'
print(json.dumps(out,ensure_ascii=False,indent=2))
PY
```

## 历史/当前范围与重复证据

```bash
python3 - <<'PY'
import pathlib,json,hashlib,collections,os,datetime
b=pathlib.Path('/home/lcq/agent_workload/benchmark')
out={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def rr(path):
 with path.open() as f:return [json.loads(x) for x in f if x.strip()]
raw=rr(b/'telemetry/video_weaver.jsonl');sc=rr(b/'traces_generation/sidecar/videoweaver/model_calls.jsonl')
ids={x['trace_id'] for x in sc}
def complete(r):
 return isinstance(r.get('input_tokens'),int) and isinstance(r.get('output_tokens'),int) and all(isinstance(r.get(k),(int,float)) for k in ['ttft','api_latency','model_latency']) and bool(r.get('model'))
chosen=[r for r in raw if r.get('trace_id') in ids];filt=[r for r in chosen if complete(r)]
out['video_filter']={'raw_rows':len(raw),'selected_trace_ids':sorted(ids),'matching_trace_ids':len(chosen),'other_trace_ids_rows':len(raw)-len(chosen),'complete_rows_in_selected':len(filt),'incomplete_rows_in_selected':len(chosen)-len(filt),'pair_set_equals_sidecar':{(r['trace_id'],r['call_id']) for r in filt}=={(r['trace_id'],r['call_id']) for r in sc},'per_trace':{}}
for tid in sorted(ids):
 selected=[r for r in sc if r['trace_id']==tid]
 out['video_filter']['per_trace'][tid]={'selected':len(selected),'tokens_input':sum(r.get('input_tokens') or 0 for r in selected),'tokens_output':sum(r.get('output_tokens') or 0 for r in selected),'max_context':max(r.get('context_tokens') or 0 for r in selected),'raw':sum(r.get('trace_id')==tid for r in raw)}
# file censuses of archived generated snapshots; parse result files, do not infer equivalence to sidecar.
out['local_result_census']={}
for rel in ['agent_benchmark_traces/gen_docops_traces','agent_benchmark_traces/gen_agentic_vbench_traces','traces_generation/DocOps/results','traces_generation/agentic-vbench']:
 root=b/rel; errors=[]; result_count=0; trials=[]; aggregate=0
 for dp,dn,fn in os.walk(root,onerror=lambda e:errors.append({'path':e.filename,'error':type(e).__name__})):
  dn[:]=[x for x in dn if x not in ['.git','.venv','node_modules','__pycache__']]
  if 'result.json' not in fn:continue
  path=pathlib.Path(dp)/'result.json';result_count+=1
  try:
   data=path.read_bytes();d=json.loads(data)
   if d.get('trial_name'):
    trials.append({'path':str(path),'trial_name':d['trial_name'],'sha256':hashlib.sha256(data).hexdigest()})
   else:aggregate+=1
  except (OSError,ValueError) as ex:errors.append({'path':str(path),'error':type(ex).__name__})
 out['local_result_census'][rel]={'result_files_seen':result_count,'trial_name_records':len(trials),'records_without_trial_name':aggregate,'scan_errors':errors,'trials':trials}
out['snapshot_overlap']={}
for a,c in [('agent_benchmark_traces/gen_docops_traces','traces_generation/DocOps/results'),('agent_benchmark_traces/gen_agentic_vbench_traces','traces_generation/agentic-vbench')]:
 aa=out['local_result_census'][a]['trials'];cc=out['local_result_census'][c]['trials']
 shared={x['sha256'] for x in aa}&{x['sha256'] for x in cc}
 out['snapshot_overlap'][a]={'compared_to':c,'shared_result_content_hashes':len(shared),'note':'Matching result bytes prove result-file duplication only; not whole-directory equivalence or unique-run identity.'}
# Workarena source count + sample ID form.
fs=sorted((b/'agent_benchmark_traces/gen_workarena_traces').glob('*.json'))
out['workarena']={'json_files':len(fs),'first_path':str(fs[0]),'first_identifiers':{k:v for k,v in json.loads(fs[0].read_text()).items() if k in ['trace_id','task_id','seed','agent','reward']}}
# video bundle native exports vs generation source exact hashes
out['video_snapshot_pairs']=[]
for path in sorted((b/'agent_benchmark_traces/gen_videoweaver_traces/bundles').glob('*/model_telemetry/model_telemetry.jsonl')):
 counterpart=b/'traces_generation/VideoWeaver'/path.parent.parent.name/'trace_bundle/model_telemetry/model_telemetry.jsonl'
 out['video_snapshot_pairs'].append({'snapshot':str(path),'generation':str(counterpart),'exists':counterpart.is_file(),'same_sha256':counterpart.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(counterpart.read_bytes()).hexdigest(),'records':len(rr(path))})
print(json.dumps(out,ensure_ascii=False,indent=2))
PY
```

另检查 locator、YAML/CSV 可解析性、source_path、样例定位及已记录源文件 hash 前后相等，结果见 validation.json。这不证明上一执行者未修改文件，也不覆盖未哈希文件。

## 后续完整性核对（补算 ZIP 内容 hash）

```bash
python3 - <<'PY'
import json,pathlib,hashlib,datetime
p=pathlib.Path('/home/lcq/agent_workload_characterization/reports/quality/audit_evidence.json')
e=json.loads(p.read_text());out={}
for name,m in e['files'].items():
 f=pathlib.Path(name);st=f.stat();r={'size_bytes':st.st_size,'mtime_ns':str(st.st_mtime_ns)}
 if m['sha256'] is None:
  h=hashlib.sha256()
  with f.open('rb') as src:
   for chunk in iter(lambda:src.read(1024*1024),b''):h.update(chunk)
  r.update(sha256=h.hexdigest(),hash_status='computed',sha256_recorded_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 out[name]=r
print(json.dumps(out))
PY
```

## 最终验证命令

```bash
python3 - <<'PY'
import pathlib,json,yaml,csv,hashlib,zipfile,datetime
p=pathlib.Path('/home/lcq/agent_workload_characterization')
errors=[]; checks={}
c=yaml.safe_load((p/'data/catalog/sources.yaml').read_text())
code=yaml.safe_load((p/'data/catalog/code_components.yaml').read_text())
samples=yaml.safe_load((p/'data/catalog/sample_candidates.yaml').read_text())
e=json.loads((p/'reports/quality/audit_evidence.json').read_text())
for f in sorted((p/'data/catalog').glob('*.yaml')):yaml.safe_load(f.read_text())
checks['yaml_files_parsed']=len(list((p/'data/catalog').glob('*.yaml')))
checks['evidence_json_parsed']=True
ids=[s['source_id'] for s in c['sources']]
if len(ids)!=len(set(ids)):errors.append('duplicate source_id')
for s in c['sources']:
 l=s['locator'];path=pathlib.Path(c['roots'][l['root']])/l['path']
 if not path.exists():errors.append('missing locator:'+str(path))
 elif (l['kind']=='file')!=path.is_file():errors.append('locator kind mismatch:'+str(path))
checks['source_locators_checked']=len(ids)
nc=0
for key,items in code.items():
 if not isinstance(items,list):continue
 for item in items:
  path=pathlib.Path(code['roots'][item['root']])/item['path'];nc+=1
  if not path.exists():errors.append('missing code path:'+str(path))
checks['code_locators_checked']=nc
with (p/'reports/quality/asset_inventory.csv').open(newline='') as f:
 table=list(csv.reader(f))
width=len(table[0])
if any(len(row)!=width for row in table):errors.append('CSV width mismatch')
checks['csv_rows']=len(table)-1;checks['csv_columns']=width
if {row[0] for row in table[1:]}!=set(ids):errors.append('CSV/YAML source set mismatch')
cmap={s['source_id']:s for s in c['sources']}
for s in samples['real_candidates']:
 l=s['locator'];path=pathlib.Path(samples['roots'][l['root']])/l['path']
 if not path.is_file():errors.append('missing sample:'+str(path));continue
 if l.get('line_1based'):
  with path.open() as f:
   d=next((json.loads(line) for i,line in enumerate(f,1) if i==l['line_1based']),None)
  if d is None:errors.append('missing line:'+s['sample_id'])
  if l.get('record_id') and d.get('id')!=l['record_id']:errors.append('ID mismatch:'+s['sample_id'])
  if s['sample_id']=='AC-N2':
   if d!=s['record']:errors.append('template record mismatch')
   contexts=[d['input_prompt_length']]
   for a,t in zip(d['assistant_response_length'],d['tool_call_output_length']):contexts.append(contexts[-1]+a+t)
   actual={'model_requests':d['num_turns']+1,'input_contexts':contexts,'total_input_tokens':sum(contexts),'max_context_tokens':max(contexts),'total_output_tokens':sum(d['assistant_response_length'])+d['final_assistant_response_length']}
   if actual!=s['expected']:errors.append('template arithmetic mismatch')
  elif s['sample_id'].startswith('AX-'):
   def walk(rs):
    for r in rs:
     if r.get('type')=='subagent':yield from walk(r.get('requests',[]))
     else:yield r
   rr=list(walk(d['requests']))
   if len(rr)!=s['expected']['model_requests'] or sum(x.get('in') or 0 for x in rr)!=s['expected']['input_tokens'] or sum(x.get('out') or 0 for x in rr)!=s['expected']['output_tokens']:errors.append('AgentX expected mismatch')
 if l.get('archive_members'):
  with zipfile.ZipFile(path) as z:
   if not set(l['archive_members'])<=set(z.namelist()):errors.append('sample archive member missing')
 if s['sample_id']=='VW-LONG':
  d=json.loads(path.read_text())
  if d['trace_id']!=l['record_id'] or d['trajectory']['wall_time_s']!=s['expected']['manifest_wall_time_s']:errors.append('video manifest mismatch')
checks['real_candidates_checked']=len(samples['real_candidates'])
checks['synthetic_designs_separate']=len(samples['synthetic_designs'])
# Compare measured sidecar table lengths to catalog and all source_path identities.
total_paths=0
for s in c['sources']:
 if s['role'] not in ['current_derived_sidecar','historical_derived_sidecar']:continue
 root=pathlib.Path(c['roots']['benchmark'])/s['locator']['path']
 for tab in ['run_manifest','model_calls','tool_calls']:
  with (root/(tab+'.jsonl')).open() as f: rr=[json.loads(x) for x in f if x.strip()]
  if len(rr)!=s['counts'][tab]['rows']:errors.append('sidecar count mismatch:'+s['source_id']+'/'+tab)
  if s['role']=='current_derived_sidecar' and tab=='run_manifest':
   for r in rr:
    source=pathlib.Path(c['roots']['benchmark'])/'traces_generation'/r['source_path']
    if not source.exists():errors.append('missing sidecar source:'+str(source))
    total_paths+=1
checks['current_sidecar_source_paths']=total_paths
# Integrity across this audit window only; no mtime-only historical guarantee.
verified=0;stat_only=0
for path,meta in e['files'].items():
 path=pathlib.Path(path)
 if not path.exists():errors.append('source disappeared:'+str(path));continue
 if meta['sha256']:
  h=hashlib.sha256()
  with path.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  if h.hexdigest()!=meta['sha256']:errors.append('source bytes changed:'+str(path))
  verified+=1
 else:
  st=path.stat()
  if st.st_size!=meta['size_bytes'] or str(st.st_mtime_ns)!=str(meta['mtime_ns']):errors.append('unhashed archive stat changed:'+str(path))
  stat_only+=1
checks['source_sha256_matches']=verified
checks['unhashed_archive_stat_only_checks']=stat_only
checks['supplement_trial_hash_matches']=0
for census in e['supplement']['local_result_census'].values():
 for r in census['trials']:
  if hashlib.sha256(pathlib.Path(r['path']).read_bytes()).hexdigest()!=r['sha256']:errors.append('trial result changed:'+r['path'])
  checks['supplement_trial_hash_matches']+=1
# Existing IDs incl relations / observed zeros are plans, not executed app tests.
checks['application_tests_executed']=False
checks['legacy_pipeline_executed']=False
print(json.dumps({'audit_revision':'P0-00-r2','validated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors,'scope_limitations':['PASS means audit artifact consistency only, not G0/schema/adapter correctness.','SHA-256 verification covers listed files during this repair only, not prior AI changes or all source tree files.','Both ZIP archives hashed and member-index inspected; payload semantics not fully parsed.','Unreadable AgenticVBench sessions, full raw-run dedup, upstream license/version gaps and runtime compatibility remain documented limitations.']},ensure_ascii=False,indent=2))
PY
```
