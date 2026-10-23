"""Compile the pinned official harness branch DAG before remote execution."""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import json
import os
from pathlib import Path

from scripts.agentx_deepseek_pilot import ROOT,canonical,sha,dump,lines,file_record,stamp,adapt_payload

RAW=ROOT/'data/raw/agentx-deepseek-branches-01'
ENV=ROOT/'env/agentx-deepseek-branches-01'
CASES=[('single_subagent','bbdcb12440a7ab3496b9fac8b5f9824b1672',21),
       ('multiple_subagents','2a2da059b7425d9dc1f999fca1177bc1cdb9',30)]


def key(cid,turn):return f'{cid}#{turn}'


def validate_dag(nodes):
    by_id={q['node_id']:q for q in nodes}
    if len(by_id)!=len(nodes):raise ValueError('duplicate node')
    done=set();layers=[]
    while len(done)<len(nodes):
        ready=[k for k,q in by_id.items() if k not in done and set(q['depends_on'])<=done]
        if not ready:raise ValueError('cycle or missing predecessor')
        done.update(ready);layers.append(sorted(ready))
    return layers


def compile_edges(metadata):
    """Translate official post-SPAWN, per-chain ordering and SPAWN_JOIN.

    Selected sessions are one level deep; refuse unreviewed nested semantics.
    Ignore recorded waits exactly as in the validated step-2 configuration.
    """
    convs={q['conversation_id']:q for q in metadata};deps=defaultdict(set);edges=[];spawn_parent={}
    branches={b['branch_id']:b for q in metadata for b in q['branches']}
    def edge(a,b,kind):deps[b].add(a);edges.append({'predecessor':a,'successor':b,'kind':kind})
    for conv in metadata:
        cid=conv['conversation_id']
        for i,turn in enumerate(conv['turns']):
            node=key(cid,i)
            if i:edge(key(cid,i-1),node,'serial')
            for ref in turn.get('replay_predecessors',[]):edge(key(ref['conversation_id'],ref['turn_index']),node,'replay_frontier')
            for bid in turn['branch_ids']:
                b=branches[bid]
                if b['mode']!='spawn' or b['dispatch_timing']!='post':raise ValueError('unreviewed branch mode')
                for child in b['child_conversation_ids']:
                    if child in spawn_parent:raise ValueError('multiple spawn parents')
                    spawn_parent[child]=cid
                    edge(node,key(child,0),'spawn')
            for prereq in turn['prerequisites']:
                if prereq['kind']!='spawn_join':raise ValueError('unreviewed prerequisite')
                for child in branches[prereq['branch_id']]['child_conversation_ids']:
                    edge(key(child,len(convs[child]['turns'])-1),node,'join')
    if any(parent in spawn_parent for parent in spawn_parent.values()):raise ValueError('nested branches require separate review')
    return deps,edges,spawn_parent


def reconstruct(source_root):
    """Call installed official loader offline; do not run any benchmark service."""
    source_root=Path(source_root)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
        HF_HUB_CACHE=str(source_root/'data/raw/agentx-replay-smoke-01/hf-cache'),TOKENIZERS_PARALLELISM='false',
        AIPERF_DATASET_WEKA_PARALLEL_WORKERS='1')
    from aiperf.config import BenchmarkConfig,BenchmarkRun
    from aiperf.common import random_generator as rng
    from aiperf.common.tokenizer import Tokenizer
    from aiperf.dataset.generator.prompt import PromptGenerator
    from aiperf.dataset.loader.weka_trace import WekaTraceLoader
    exported=source_root/'data/raw/agentx-replay-smoke-01/attempts/03-full-sample/harness/profile_export_aiperf.json'
    config=BenchmarkConfig.model_validate(json.loads(exported.read_text())['input_config'])
    assert config.get_default_dataset().ignore_trace_delays
    run=BenchmarkRun(benchmark_id='offline-branch-identity',cfg=config,artifact_dir=RAW/'offline-loader',random_seed=42,cli_command=None)
    rng.init(42)
    tokenizer=Tokenizer.from_pretrained('Qwen/Qwen3-0.6B',revision='c1899de289a04d12100db370d81485cdf75e47ca')
    generator=PromptGenerator(prompts=None,prefix_prompts=None,tokenizer=tokenizer)
    loader=WekaTraceLoader(filename=str(source_root/'data/raw/agentx-replay-smoke-01/sessions'),run=run,prompt_generator=generator)
    data=loader.load_dataset();selected={trace:data[trace] for _,trace,_ in CASES}
    conversations=loader.convert_to_conversations(selected)
    return [c.to_metadata().model_dump(mode='json') for c in conversations]


def prepare(source_root):
    source_root=Path(source_root);RAW.mkdir(parents=True,exist_ok=False);ENV.mkdir(parents=True,exist_ok=True)
    metadata=reconstruct(source_root);dump(RAW/'official-metadata.json',metadata)
    export=source_root/'data/raw/agentx-replay-smoke-01/attempts/03-full-sample/harness/profile_export_raw.jsonl'
    pinned=json.loads((source_root/'reports/analysis/AGENTX-REPLAY-SMOKE-v1/local-evidence-manifest.json').read_text())
    assert file_record(export)['sha256']==next(q['sha256'] for q in pinned['files'] if q['path']==str(export))
    captures=lines(export);source={}
    for q in lines(source_root/'data/raw/agentx-replay-smoke-01/source_requests.jsonl'):
        source[(q['trace_id'],q['outer_idx'],q['inner_idx'])]=q
    cases=[]
    for label,trace,count in CASES:
        current=[q for q in metadata if q['conversation_id']==trace or q['conversation_id'].startswith(trace+'::')]
        deps,edges,parents=compile_edges(current)
        records=[q for q in captures if q['metadata']['source_trace_id']==trace]
        records_by_node={key(q['metadata']['conversation_id'],q['metadata']['turn_index']):q for q in records}
        nodes=[]
        for conv in current:
            for i,turn in enumerate(conv['turns']):
                node_id=key(conv['conversation_id'],i);q=records_by_node[node_id];m=q['metadata']
                assert (turn['source_trace_id'],turn['source_outer_idx'],turn['source_inner_idx'])==(m['source_trace_id'],m['source_outer_idx'],m.get('source_inner_idx'))
                native=source[(trace,m['source_outer_idx'],m.get('source_inner_idx'))]
                payload=adapt_payload(q['payload']);assert payload['max_tokens']==native['output_tokens']
                body=canonical(payload);path=RAW/'frozen-requests'/label/f'{len(nodes):03d}.json.gz';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(body,mtime=0))
                nodes.append({'node_id':node_id,'index':len(nodes),'conversation_id':conv['conversation_id'],'turn_index':i,
                    'parent_conversation_id':parents.get(conv['conversation_id']),'depends_on':sorted(deps[node_id]),
                    'trace_id':trace,'source_outer_idx':native['outer_idx'],'source_inner_idx':native['inner_idx'],
                    'source_pointer':native['pointer'],'source_request_sha256':native['source_request_sha256'],
                    'source_input_tokens':native['input_tokens'],'source_output_tokens':native['output_tokens'],
                    'body_sha256':sha(body),'messages_sha256':sha(canonical(payload['messages'])),'body_bytes':len(body),'payload':str(path)})
        assert len(nodes)==len(records)==count and len(records_by_node)==count
        layers=validate_dag(nodes)
        cases.append({'label':label,'trace_id':trace,'requests':count,'execution_chains':len(current),
            'native_subagent_groups':len({q['source_outer_idx'] for q in nodes if q['source_inner_idx'] is not None}),
            'output_token_limit_sum':sum(q['source_output_tokens'] for q in nodes),'largest_output_limit':max(q['source_output_tokens'] for q in nodes),
            'source_input_token_sum':sum(q['source_input_tokens'] for q in nodes),'edges':edges,'topological_layers':layers,'nodes':nodes})
    plan={'schema':'agentx-deepseek-branch-plan-v1','created_at_shanghai':stamp(),'endpoint':'https://api.deepseek.com/v1/chat/completions',
        'model':'deepseek-flash','thinking':'disabled','temperature':0,'probe_requests':1,'profile_requests':51,
        'maximum_inflight_requests':8,'request_total_timeout_s':900,'read_timeout_s':90,'wall_limit_s':1800,
        'automatic_retries':0,'failure_policy':'stop dispatch on first failed response, drain in-flight requests, mark blocked nodes not_executed; no automatic retry',
        'source_timing_reproduced':False,'model_outputs_fed_back':False,'server_resources_collected':False,
        'scheduler':'dependency DAG compiled offline from official harness 1.0.7 metadata; post-SPAWN/chain serial/SPAWN_JOIN; drop source waits as in step 2',
        'cases_run':'single_subagent first, then multiple_subagents; no overlap between cases',
        'source_export':file_record(export),'official_metadata':file_record(RAW/'official-metadata.json'),
        'code':[file_record(ROOT/'scripts/agentx_deepseek_branches.py'),file_record(Path(__file__)),file_record(ROOT/'scripts/agentx_deepseek_pilot.py')],
        'cases':cases}
    dump(ENV/'plan.json',plan)
    print(json.dumps([{k:c[k] for k in ['label','requests','execution_chains','native_subagent_groups','output_token_limit_sum','largest_output_limit']} for c in cases],ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);prepare(p.parse_args().source_root)
