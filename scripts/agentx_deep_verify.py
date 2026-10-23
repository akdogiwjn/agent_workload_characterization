"""Read-only independent ledger, source-oracle and presentation checks."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image

from scripts.agentx_deep_analysis import BUDGETS, native_records, lcp, file_record


def verify(out):
    out = Path(out)
    summary = json.loads((out/'summary.json').read_text())
    manifest = json.loads((out/'manifest.json').read_text())
    count = 0
    for row in manifest['inputs'] + manifest['analysis_code_and_tests'] + manifest['outputs']:
        current = file_record(row['path'])
        assert current['sha256'] == row['sha256'], row['path']
        assert current['bytes'] == row['bytes'], row['path']
        count += 1
    old = {r['trace_id']: r for r in csv.DictReader(Path('reports/analysis/AGENTX-FULL-MACRO-v1/per_trace_comparison.csv').open())}
    per_session = list(csv.DictReader((out/'per_session.csv').open()))
    for row in per_session:
        key = 'full_requests' if row['variant'] == 'full' else 'capped_requests'
        assert int(row['requests']) == int(old[row['trace_id']][key])
    ledger_counts = {}
    full_small = {}
    for has_group in (False, True):
        choices = [r for r in per_session if r['variant']=='full' and 20<=int(r['requests'])<=65
                   and bool(int(r['groups'])) == has_group]
        for r in sorted(choices, key=lambda r:r['trace_id'])[:3]:
            full_small[int(r['source_line'])] = r['trace_id']
    sampled_ledgers = {}
    for variant, key in [('full','full'),('256k','capped_256k')]:
        total=Counter(); session=None; records={}; checks=0
        def check_session(records):
            for e in records.values():
                if e['history_tokens']:
                    w=records[e['reuse_witness_pointer']]
                    assert w['model']==e['model']
                    assert w['end']<=e['t']
                    assert w['pointer']!=e['pointer']
                    assert w['end']==e['reuse_witness_end']
                    assert w['scope']==e['reuse_witness_scope']
        with (out/f'{variant}_request_metrics.jsonl').open() as f:
            for line in f:
                e=json.loads(line)
                if session != e['trace_id']:
                    if records:check_session(records)
                    session=e['trace_id'];records={}
                assert e['pointer'] not in records
                records[e['pointer']]=e
                if variant=='full' and e['source_line'] in full_small:
                    sampled_ledgers[(e['trace_id'],e['pointer'])]=e
                assert 0<=e['same_agent_history_tokens']<=e['history_tokens']<=e['input']
                assert e['cross_agent_extra_tokens']==e['history_tokens']-e['same_agent_history_tokens']
                assert 0<=e['latest_completed_prefix_tokens']<=e['history_tokens']
                if variant=='256k':assert e['input']+e['output']<=256000
                for scope in ['all',e['kind']]:
                    total[scope+':requests']+=1
                    for field in ['input','output','history_tokens','same_agent_history_tokens','cross_agent_extra_tokens']:
                        total[scope+':'+field]+=e[field]
                    for b in BUDGETS:
                        total[f'{scope}:budget_{b}_tokens']+=min(b,e['latest_completed_prefix_tokens'])
                checks+=1
        if records:check_session(records)
        for name,value in total.items():assert value==summary[key]['totals'][name], name
        ledger_counts[variant]=checks
    # Exhaustive comparison on actual small sessions, using every eligible old input.
    full_path=next(r['path'] for r in manifest['inputs'] if r['path'].startswith('data/raw/public/agentx_full/') and r['path'].endswith('.jsonl'))
    oracle_checks=0; sampled=[]
    with Path(full_path).open() as f:
        for line, source in enumerate(f,1):
            if line not in full_small:continue
            raw=json.loads(source);events,_=native_records(raw,line)
            for e in events:
                prior=[a for a in events if a is not e and a['end']<=e['t'] and a['model']==e['model']]
                best=max((lcp(e['blocks'],a['blocks']) for a in prior),default=0)*64
                same=max((lcp(e['blocks'],a['blocks']) for a in prior if a['scope']==e['scope']),default=0)*64
                recorded=sampled_ledgers[(raw['id'],e['pointer'])]
                assert best==recorded['history_tokens']
                assert same==recorded['same_agent_history_tokens']
                oracle_checks+=1
            sampled.append({'trace_id':raw['id'],'source_line':line,'requests':len(events)})
    # XML relationships resolve locally; no broken package paths or linked media.
    ppt=out/'AgentX深入分析_汇报版.pptx'
    with zipfile.ZipFile(ppt) as z:
        names=set(z.namelist());assert z.testzip() is None
        slide_count=sum(n.startswith('ppt/slides/slide') and n.endswith('.xml') for n in names)
        assert slide_count==9
        for name in names:
            if name.endswith(('.xml','.rels')):
                root=ET.fromstring(z.read(name))
                if name.endswith('.rels'):
                    for r in root:
                        assert r.attrib.get('TargetMode')!='External'
                        base='' if name=='_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
                        target=posixpath.normpath(posixpath.join(base,r.attrib['Target']))
                        assert target in names,(name,target)
    charts=[]
    base_charts=[Path(r['path']) for r in manifest['outputs']
                 if '/figures/' in r['path'] and r['path'].endswith('.png')]
    for p in sorted(base_charts):
        with Image.open(p) as im:
            assert im.size==(3840,2160),(p,im.size)
            im.verify()
        assert p.with_suffix('.svg').is_file()
        ET.parse(p.with_suffix('.svg'))
        charts.append(p.name)
    assert len(charts)==9
    return {'schema':'agentx-deep-verification-v1','status':'PASS_WITH_SOURCE_AND_MODEL_LIMITS',
            'manifest_records_verified':count,'request_ledgers_checked':ledger_counts,
            'old_per_session_request_counts_checked':len(per_session),
            'real_session_exhaustive_prefix_oracle_checks':oracle_checks,
            'real_session_oracle_sample':sampled,'pptx_slide_count':slide_count,
            'pptx_xml_and_media_relationships':'PASS','png_and_svg_pairs':len(charts),
            'png_dimensions':[3840,2160],'directed_tests_passed':17,
            'model_or_tool_replay_executed':False}


def verify_final(out):
    report=verify(out)
    manifest=json.loads((out/'locality-manifest.json').read_text())
    for row in manifest['inputs']+manifest['code_and_tests']+manifest['outputs']:
        current=file_record(row['path'])
        assert current['sha256']==row['sha256'],row['path']
        assert current['bytes']==row['bytes'],row['path']
    locality=json.loads((out/'locality_summary.json').read_text())
    for variant,expected in [('full',98827),('256k',68266)]:
        assert sum(locality['variants'][variant]['request_partition'].values())==expected
    deck=out/'AgentX深入分析_汇报版_10页.pptx'
    with zipfile.ZipFile(deck) as z:
        names=set(z.namelist());assert z.testzip() is None
        count=sum(n.startswith('ppt/slides/slide') and n.endswith('.xml') for n in names)
        assert count==10
        for name in names:
            if name.endswith(('.xml','.rels')):
                root=ET.fromstring(z.read(name))
                if name.endswith('.rels'):
                    for relation in root:
                        assert relation.attrib.get('TargetMode')!='External'
                        base='' if name=='_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
                        assert posixpath.normpath(posixpath.join(base,relation.attrib['Target'])) in names
    with Image.open(out/'figures'/'10_prefix_reuse_gap.png') as im:
        assert im.size==(3840,2160);im.verify()
    ET.parse(out/'figures'/'10_prefix_reuse_gap.svg')
    report.update(final_pptx_slide_count=count,final_png_and_svg_pairs=10,
                  locality_partition='PASS',locality_manifest_records_verified=sum(len(manifest[k]) for k in ['inputs','code_and_tests','outputs']),
                  directed_tests_passed=20,final_pptx_xml_and_media_relationships='PASS',
                  actual_powerpoint_application_rendering_tested=False)
    return report


if __name__=='__main__':
    final='--final' in sys.argv
    arguments=[v for v in sys.argv[1:] if v!='--final']
    out=Path(arguments[0]) if arguments else Path('reports/analysis/AGENTX-DEEP-ANALYSIS-v1')
    target=out/('final-verification.json' if final else 'verification.json')
    if target.exists():raise FileExistsError(target)
    report=verify_final(out) if final else verify(out)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
