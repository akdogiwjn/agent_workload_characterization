"""Select complete, small AgentX sessions and pin source/tokenizer identities."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/agentx-replay-smoke-01'
CAT=ROOT/'data/catalog/agentx-replay-smoke-01'


def record(path):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}


def select(rows):
    rows=[r for r in rows if r['variant']=='full']
    rules=[('serial',lambda r:int(r['groups'])==0 and int(r['peak'])==1),
           ('root_overlap',lambda r:int(r['groups'])==0 and int(r['peak'])>1),
           ('explicit_subagent',lambda r:int(r['groups'])>0),
           ('multiple_subagents',lambda r:int(r['groups'])>=3),
           ('long_context',lambda r:int(r['max_input'])>=500000)]
    chosen=[];seen=set()
    for label,predicate in rules:
        candidates=sorted((r for r in rows if predicate(r) and r['trace_id'] not in seen),
                          key=lambda r:(int(r['requests']),r['trace_id']))
        if not candidates:raise ValueError('no sample for '+label)
        row=candidates[0];seen.add(row['trace_id']);chosen.append({'stratum':label,**row})
    return chosen


def leaves(raw):
    rows=[]
    def walk(items,scope,pointer,outer=None):
        for i,q in enumerate(items):
            p=f'{pointer}/{i}'
            if q['type']=='subagent':walk(q['requests'],scope+[q['agent_id']],p+'/requests',i if outer is None else outer)
            else:
                if q['type'] not in ['s','n']:raise ValueError('unsupported entry')
                rows.append({'trace_id':raw['id'],'pointer':p,'scope':scope,'outer_idx':i if outer is None else outer,
                             'inner_idx':None if outer is None else i,'source_t':q['t'],'source_api_time':q['api_time'],
                             'model':q['model'],'input_tokens':q['in'],'output_tokens':q['out'],
                             'hash_ids':q['hash_ids'],'source_request_sha256':hashlib.sha256(json.dumps(q,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    walk(raw['requests'],[],'/requests')
    return rows


def prepare(source_root):
    source_root=Path(source_root)
    selected=select(list(csv.DictReader((ROOT/'reports/analysis/AGENTX-DEEP-ANALYSIS-v1/per_session.csv').open())))
    baseline=json.loads((ROOT/'reports/analysis/AGENTX-FULL-MACRO-v1/manifest.json').read_text())
    entry=next(r for r in baseline['inputs'] if r['path'].startswith('data/raw/public/agentx_full/') and r['path'].endswith('traces.jsonl'))
    source=source_root/entry['path']
    actual=record(source)
    if actual['sha256']!=entry['sha256'] or actual['bytes']!=entry['bytes']:raise ValueError('source identity mismatch')
    target=RAW/'sessions'
    if target.exists():raise FileExistsError(target)
    target.mkdir(parents=True)
    wanted={int(r['source_line']):r for r in selected};outputs=[];requests=[]
    with source.open() as stream:
        for line,text in enumerate(stream,1):
            if line not in wanted:continue
            raw=json.loads(text);chosen=wanted[line]
            if raw['id']!=chosen['trace_id']:raise ValueError('sample locator mismatch')
            leaf=leaves(raw)
            if len(leaf)!=int(chosen['requests']):raise ValueError('sample request count mismatch')
            p=target/(raw['id']+'.json');p.write_text(json.dumps(raw,separators=(',',':'))+'\n')
            outputs.append({'stratum':chosen['stratum'],'source_line':line,'trace_id':raw['id'],
                            'requests':len(leaf),'groups':int(chosen['groups']),
                            'max_input_tokens':int(chosen['max_input']),**record(p)})
            requests.extend({'source_line':line,**r} for r in leaf)
    (RAW/'source_requests.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in requests))
    metadata=json.loads((RAW/'tokenizer/hf-api.json').read_text())
    tokens=[record(p) for p in sorted((RAW/'tokenizer').glob('*')) if p.is_file()]
    result={'schema':'agentx-replay-smoke-sample-v1','date':'2026-10-23',
            'selection_rule':'minimum total saved requests then lexicographic trace ID within each explicit stratum; deduplicate sessions',
            'source':actual,'source_revision':'23f152f6f0f9399a85901b89a6458def0ef16729',
            'complete_selected_sessions':outputs,'selected_sessions':len(outputs),'selected_requests':len(requests),
            'selected_groups':sum(r['groups'] for r in outputs),
            'tokenizer_model':'Qwen/Qwen3-0.6B','tokenizer_revision':metadata['sha'],'tokenizer_files':tokens,
            'model_weights_downloaded':False,'business_content_recovered':False,
            'source_requests':record(RAW/'source_requests.jsonl')}
    CAT.mkdir(parents=True,exist_ok=True)
    (CAT/'sample-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['selected_sessions','selected_requests','selected_groups','tokenizer_revision']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root',type=Path,required=True)
    prepare(parser.parse_args().source_root)
