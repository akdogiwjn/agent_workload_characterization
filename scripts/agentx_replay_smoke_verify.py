"""Offline integrity and response-body checks, independent of mock usage values."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from transformers import AutoTokenizer

from scripts.agentx_deep_analysis import dump
from scripts.agentx_replay_smoke_audit import ROOT, RAW, OUT, read_lines, source_key
from scripts.agentx_replay_smoke_prepare import record


def verify():
    summary=json.loads((OUT/'summary.json').read_text());attempt=RAW/'attempts'/summary['successful_attempt']
    manifest=json.loads((ROOT/'data/catalog/agentx-replay-smoke-01/sample-manifest.json').read_text())
    checked=[]
    for q in [manifest['source_requests'],*manifest['complete_selected_sessions'],*manifest['tokenizer_files']]:
        actual=record(q['path']);assert actual['sha256']==q['sha256'] and actual['bytes']==q['bytes'],q['path']
        checked.append(actual)
    native={}
    for q in manifest['complete_selected_sessions']:
        raw=json.loads(Path(q['path']).read_text())
        for saved in read_lines(RAW/'source_requests.jsonl'):
            if saved['trace_id']!=raw['id']:continue
            value=raw
            for part in saved['pointer'].strip('/').split('/'):
                value=value[int(part)] if isinstance(value,list) else value[part]
            digest=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            assert digest==saved['source_request_sha256']
            native[source_key(saved)]=saved
    tokenizer=AutoTokenizer.from_pretrained(RAW/'tokenizer',local_files_only=True,trust_remote_code=False)
    wire={q['request_id']:q for q in read_lines(attempt/'mock/server_requests.jsonl')}
    response_counts=[]
    for raw in read_lines(attempt/'harness/profile_export_raw.jsonl'):
        rid=raw['metadata']['x_request_id'];http=wire[rid];source=native[source_key(raw['metadata'],True)]
        assert raw['status']==200
        path=attempt/'mock/requests'/f"{http['file_id']}.json.gz"
        body=gzip.decompress(path.read_bytes());assert hashlib.sha256(body).hexdigest()==http['body_sha256']
        assert json.loads(body)==raw['payload']
        vectors_path=path.with_name(http['file_id']+'.npz')
        with np.load(vectors_path,allow_pickle=False) as vectors:
            assert len(vectors['prompt_ids'])==http['rendered_input_tokens']
            assert len(vectors['content_ids'])==http['content_input_tokens']
            assert hashlib.sha256(vectors['prompt_ids'].astype(np.int32).tobytes()).hexdigest()==http['prompt_ids_sha256']
        text=[];done=False
        for chunk in raw['responses']:
            for packet in chunk['packets']:
                if packet['value']=='[DONE]':done=True;continue
                obj=json.loads(packet['value'])
                for choice in obj.get('choices',[]):text.append(choice.get('delta',{}).get('content',''))
        count=len(tokenizer.encode(''.join(text),add_special_tokens=False))
        assert count==max(1,source['output_tokens']) and done
        response_counts.append(count)
        checked.extend([record(path),record(vectors_path)])
    assert len(response_counts)==len(native)==117
    for name in ['attempt.json','environment.json','harness/profile_export_raw.jsonl','harness/profile_export.jsonl',
                 'harness/profile_export_aiperf.json','mock/server_requests.jsonl','client.stdout','client.stderr','server.stdout','server.stderr']:
        checked.append(record(attempt/name))
    package=ROOT/'.venv/lib/python3.11/site-packages/aiperf'
    for name in ['dataset/loader/weka_trace.py','common/tokenizer.py','dataset/generator/prompt.py','timing/branch_orchestrator.py']:
        checked.append(record(package/name))
    deck=OUT/'AgentX本地回放验证_汇报版_4页.pptx'
    with zipfile.ZipFile(deck) as z:
        assert z.testzip() is None
        slides=[p for p in z.namelist() if p.startswith('ppt/slides/slide') and p.endswith('.xml')]
        assert len(slides)==4
        for p in z.namelist():
            if p.endswith('.xml') or p.endswith('.rels'):ET.fromstring(z.read(p))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    from scripts.check_project_state import check
    state_errors=check(ROOT)
    missing_state_evidence=[line for line in state_errors if line.endswith(': evidence mismatch')
                            and not (ROOT/line.removesuffix(': evidence mismatch')).is_file()]
    # Isolated Git worktrees intentionally lack ignored historical experiment
    # evidence. Record that limitation without changing or refreshing state.
    verification={'schema':'agentx-replay-final-verification-v1','status':'PASS',
        'native_request_fingerprints_verified':len(native),'http_payloads_verified':len(response_counts),
        'received_response_text_retokenized':len(response_counts),'actual_response_tokens':sum(response_counts),
        'local_evidence_files_hashed':len(checked),'pptx_slides':4,'figure_size':[3840,2160],
        'mapping_passed':summary['mapping_passed'],'owned_process_cleanup_confirmed':summary['attempt']['owned_process_cleanup_confirmed'],
        'global_project_state_check':{'status':'FAIL' if state_errors else 'PASS','errors':state_errors,
            'missing_local_evidence_files':len(missing_state_evidence),
            'disposition':'shared status files untouched; isolated worktree has no ignored historical evidence; task patch supplied separately'},
        'scope':'mechanical mapping passed; input/prefix token drift measured, not exact-token or timing reproduction'}
    assert summary['mapping_passed'] and verification['owned_process_cleanup_confirmed']
    dump(OUT/'local-evidence-manifest.json',{'files':checked,'git_policy':'manifest only; referenced captures and installed packages remain local and ignored'})
    dump(OUT/'final-verification.json',verification)
    # Refresh only this report's own manifest after verification/report updates.
    old=json.loads((OUT/'manifest.json').read_text())
    old['task_code_and_configuration']=[record(p) for p in [
        *sorted((ROOT/'scripts').glob('agentx_replay_smoke_*.py')),
        ROOT/'scripts/agentx_loopback_mock.py',ROOT/'tests/test_agentx_replay_smoke.py',
        *sorted((ROOT/'env/agentx-replay-smoke-01').glob('*')),
        *sorted((ROOT/'data/catalog/agentx-replay-smoke-01').glob('*.json'))] if p.is_file()]
    old['outputs']=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json']
    dump(OUT/'manifest.json',old)
    print(json.dumps({k:v for k,v in verification.items() if k!='global_project_state_check'},ensure_ascii=False,indent=2))
    print('global historical-state evidence issues:',len(state_errors))


if __name__=='__main__':verify()
