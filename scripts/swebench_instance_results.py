"""Acquire and analyze public SWE-bench per-instance evaluation artifacts.

Only public HTTP downloads and static reads. Never execute recorded commands,
agents, patches, tests, benchmarks, or evaluation harnesses.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from swebench_coverage_results import INDEX, INSTANCE, file_record, split_group, verified_read, result_link, strata_for_instances

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1')
CAT = Path('data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023')
RAW = Path('data/raw/public/swebench_instance_results/SWEBENCH-INSTANCE-RESULTS-20261023')
OUT = Path('reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1')
S3 = 'https://swe-bench-submissions.s3.amazonaws.com/'
NS = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def get(url, dest):
    """Download once; safe resume validates HTTP headers on every reuse."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = dest.with_suffix(dest.suffix + '.headers')
    if not dest.exists():
        partial = Path(str(dest) + '.part')
        result = subprocess.run(['curl', '-fL', '--silent', '--show-error', '--retry', '2',
                                 '--connect-timeout', '15', '--max-time', '120',
                                 '--dump-header', str(headers), '--output', str(partial), url],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'curl failed {url}: {result.stderr[:400]}')
        partial.rename(dest)
    statuses = re.findall(r'^HTTP/\S+\s+(\d+)', headers.read_text(), re.M)
    if not statuses or statuses[-1] != '200':
        raise ValueError('no HTTP 200: ' + str(dest))
    return dest.read_bytes(), headers


def list_prefix(prefix, folder):
    records, pages, token = [], [], None
    while True:
        params = {'list-type': '2', 'prefix': prefix, 'max-keys': '1000'}
        if token:
            params['continuation-token'] = token
        url = S3 + '?' + urlencode(params)
        path = folder / f'page-{len(pages):03}.xml'
        data, headers = get(url, path)
        doc = ET.fromstring(data)
        if doc.findtext('s:Prefix', namespaces=NS) != prefix:
            raise ValueError('listing prefix mismatch')
        for item in doc.findall('s:Contents', NS):
            key = item.findtext('s:Key', namespaces=NS)
            if not key.startswith(prefix) or '..' in Path(key).parts or key.startswith('/'):
                raise ValueError('unsafe/unexpected S3 key')
            records.append({'key': key, 'bytes': int(item.findtext('s:Size', namespaces=NS)),
                            'etag': item.findtext('s:ETag', namespaces=NS).strip('"'),
                            'last_modified': item.findtext('s:LastModified', namespaces=NS)})
        pages.append({'url': url, **file_record(path), 'headers': file_record(headers)})
        if doc.findtext('s:IsTruncated', namespaces=NS) != 'true':
            break
        new_token = doc.findtext('s:NextContinuationToken', namespaces=NS)
        if not new_token or new_token == token:
            raise ValueError('broken S3 pagination')
        token = new_token
    if len({r['key'] for r in records}) != len(records):
        raise ValueError('duplicate S3 keys across pages')
    return {'prefix': prefix, 'objects': records, 'pages': pages, 'pagination_complete': True}


def discover():
    target = CAT / 'discovery.json'
    if target.exists():
        raise FileExistsError(target)
    manifest = json.loads((BASE / 'manifest.json').read_text())
    bound = {e['path']: e for e in manifest['outputs']}
    groups = sorted(json.loads(verified_read(bound[str(BASE / 'summary.json')]))['groups_summary'])
    rows = [json.loads(line) for line in verified_read(bound[str(BASE / 'per_instance.jsonl')]).decode().splitlines()]
    wanted = {g: {r['task'] for r in rows if r['group'] == g} for g in groups}
    def one(group):
        split, name = split_group(group)
        prefix = split + '/' + name + '/logs/'
        listing = list_prefix(prefix, CAT / 'source_metadata/listings' / split / name)
        local = CAT / 'source_metadata/listings' / split / name / 'index.json'
        write_json(local, listing)
        reports, legacy, other = [], [], Counter()
        for obj in listing['objects']:
            rel = obj['key'][len(prefix):]
            parts = rel.split('/')
            task = parts[0] if INSTANCE.fullmatch(parts[0]) else None
            if len(parts) == 2 and task in wanted[group] and parts[-1] == 'report.json':
                reports.append({**obj, 'group': group, 'task': task, 'artifact': 'instance_report'})
            elif len(parts) == 1 and parts[0].endswith('.log') and parts[0][:-4] in wanted[group]:
                legacy.append({**obj, 'group': group, 'task': parts[0][:-4], 'artifact': 'legacy_evaluation_log'})
            else:
                other[parts[-1] if '.' in parts[-1] else '<directory>'] += 1
        result = {'group': group, 'prefix': prefix, 'listing': file_record(local),
                  'log_objects': len(listing['objects']), 'reports': reports, 'legacy_logs': legacy,
                  'other_names': dict(other), 'wanted_instances': len(wanted[group])}
        print(json.dumps({'group': group, 'logs': result['log_objects'], 'reports': len(reports), 'legacy': len(legacy)}, ensure_ascii=False), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, group) for group in groups]
        results = [f.result() for f in as_completed(futures)]
    write_json(target, {'schema': 'swebench-instance-artifact-discovery-v1',
                        'created_at_utc': datetime.now(timezone.utc).isoformat(),
                        'baseline_manifest': file_record(BASE / 'manifest.json'),
                        'baseline_instances': bound[str(BASE / 'per_instance.jsonl')],
                        'groups': sorted(results, key=lambda x: x['group']),
                        'mutable_source_boundary': 'S3 listing is current, not historical Git-commit content',
                        'agent_or_verifier_executed': False})


def plan_download():
    """Use complete saved listings, including files outside old filename IDs."""
    discovery = json.loads((CAT / 'discovery.json').read_text())
    items = []
    for group in discovery['groups']:
        listing = json.loads(verified_read(group['listing']))
        split, submission = split_group(group['group'])
        for obj in listing['objects']:
            rel = obj['key'][len(group['prefix']):]
            parts = rel.split('/')
            task, artifact = None, None
            if len(parts) == 2 and INSTANCE.fullmatch(parts[0]) and parts[-1] == 'report.json':
                task, artifact = parts[0], 'instance_report'
            elif len(parts) == 1:
                suffix = '.' + submission + '.eval.log'
                if rel.endswith(suffix) and INSTANCE.fullmatch(rel[:-len(suffix)]):
                    task, artifact = rel[:-len(suffix)], 'legacy_evaluation_log'
            if not artifact:
                continue
            dest = RAW / obj['key']
            items.append({**obj, 'group': group['group'], 'task': task, 'artifact': artifact,
                          'path': str(dest), 'url': S3 + quote(obj['key'], safe='/'),
                          'headers_path': str(CAT / 'source_metadata/http' / (obj['key'] + '.headers'))})
    # Fetch the small publication predictions when present, for coverage/empty
    # patch evidence. Do not substitute missing predictions for a failed test.
    def predictions(group):
        split, submission = split_group(group['group'])
        prefix = split + '/' + submission + '/'
        # A direct existence GET is sufficient; a 404 is retained as evidence.
        key = prefix + 'all_preds.jsonl'
        path = CAT / 'source_metadata/prediction_probes' / split / (submission + '.headers')
        path.parent.mkdir(parents=True, exist_ok=True)
        response = subprocess.run(['curl', '-fL', '--silent', '--show-error', '--head',
                                   '--connect-timeout','15','--max-time','60','--retry','2',
                                   '--output',str(path),S3 + quote(key,safe='/')], capture_output=True, text=True)
        status = re.findall(r'^HTTP/\S+\s+(\d+)', path.read_text(), re.M)
        if response.returncode and (not status or status[-1] != '404'):
            raise RuntimeError(response.stderr)
        if status and status[-1] == '200':
            sizes = re.findall(r'^content-length:\s*(\d+)', path.read_text(), re.M|re.I)
            etags = re.findall(r'^etag:\s*"([^"]+)"', path.read_text(), re.M|re.I)
            if not sizes or not etags:
                raise ValueError('prediction HEAD missing size/ETag')
            return {'key':key,'bytes':int(sizes[-1]),'etag':etags[-1], 'group':group['group'],
                    'task':None,'artifact':'predictions','path':str(RAW/key), 'url':S3+quote(key,safe='/'),
                    'headers_path':str(CAT/'source_metadata/http'/(key+'.headers'))}
        return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item in pool.map(predictions, discovery['groups']):
            if item:
                items.append(item)
    plan = {'schema':'swebench-instance-download-plan-v1','discovery':file_record(CAT/'discovery.json'),
            'items':items,'counts':dict(Counter(i['artifact'] for i in items)),
            'payload_bytes':sum(i['bytes'] for i in items), 'agent_or_verifier_executed':False}
    path = CAT/'plan.json'
    if path.exists():
        raise FileExistsError(path)
    write_json(path,plan)
    curl_config(items,CAT/'source_metadata/download.curl')
    print(json.dumps({'counts':plan['counts'],'payload_bytes':plan['payload_bytes']},ensure_ascii=False),flush=True)


def curl_config(items,path):
    config=[]
    for item in items:
        Path(item['path']).parent.mkdir(parents=True,exist_ok=True)
        Path(item['headers_path']).parent.mkdir(parents=True,exist_ok=True)
        for name,value in [('url',item['url']),('output',item['path']+'.part'),('dump-header',item['headers_path'])]:
            config.append(name+' = '+json.dumps(value))
        config += ['fail','location','silent','show-error','connect-timeout = 15','max-time = 120',
                   'retry = 2','retry-delay = 1',f'max-filesize = {item["bytes"]}',
                   'write-out = "{\\"http\\":%{response_code},\\"exit\\":%{exitcode},\\"file\\":\\"%{filename_effective}\\"}\\n"','next']
    path.write_text('\n'.join(config[:-1])+'\n')


def supplement_plan():
    discovery=json.loads((CAT/'discovery.json').read_text());items=[]
    for group in discovery['groups']:
        listing=json.loads(verified_read(group['listing']))
        with_report={x['key'].rsplit('/',1)[0] for x in listing['objects'] if x['key'].endswith('/report.json')}
        for obj in listing['objects']:
            if not obj['key'].endswith('/run_instance.log') or obj['key'].rsplit('/',1)[0] in with_report:continue
            task=obj['key'].split('/')[-2]
            if not INSTANCE.fullmatch(task):raise ValueError('unrecognized diagnostic instance ID')
            items.append({**obj,'group':group['group'],'task':task,'artifact':'evaluation_diagnostic',
                          'path':str(RAW/obj['key']),'url':S3+quote(obj['key'],safe='/'),
                          'headers_path':str(CAT/'source_metadata/http'/(obj['key']+'.headers'))})
    path=CAT/'supplement-plan.json'
    if path.exists():raise FileExistsError(path)
    write_json(path,{'discovery':file_record(CAT/'discovery.json'),'items':items,
                     'policy':'all listed run_instance.log for native instances lacking report.json'})
    curl_config(items,CAT/'source_metadata/supplement.curl')
    print(json.dumps({'diagnostics':len(items),'bytes':sum(i['bytes'] for i in items)}))


def seal():
    target = CAT/'manifest.json'
    if target.exists():
        raise FileExistsError(target)
    plan=json.loads((CAT/'plan.json').read_text())
    supplement=json.loads((CAT/'supplement-plan.json').read_text())
    verified_read(plan['discovery'])
    validated=[]
    for item in plan['items']+supplement['items']:
        final=Path(item['path']); partial=Path(str(final)+'.part')
        if not final.resolve().is_relative_to((ROOT/RAW).resolve()) or final.exists():
            raise ValueError('unsafe/existing acquisition destination')
        data=partial.read_bytes()
        header=Path(item['headers_path']).read_text()
        statuses=re.findall(r'^HTTP/\S+\s+(\d+)',header,re.M)
        etags=re.findall(r'^etag:\s*"([^"]+)"',header,re.M|re.I)
        if len(data)!=item['bytes'] or not statuses or statuses[-1]!='200' or not etags or etags[-1]!=item['etag']:
            raise ValueError('HTTP/size/ETag mismatch: '+str(final))
        if re.fullmatch(r'[0-9a-fA-F]{32}',item['etag']) and hashlib.md5(data).hexdigest()!=item['etag'].lower():
            raise ValueError('single-part MD5 mismatch')
        content_validation='utf8_text'
        if item['artifact']=='instance_report':
            try:json.loads(data);content_validation='json'
            except (ValueError,UnicodeError):content_validation='upstream_empty_or_invalid_json_preserved'
        elif item['artifact']=='predictions':
            prediction_rows(data)
        else:data.decode('utf-8')
        validated.append({**item,'content_validation':content_validation})
    files=[]
    for item in validated:
        path=Path(item['path']);Path(str(path)+'.part').rename(path)
        files.append({**item,**file_record(path),'headers':file_record(item['headers_path'])})
    discovery=json.loads((CAT/'discovery.json').read_text())
    listings=[]
    for group in discovery['groups']:
        listing=json.loads(verified_read(group['listing']))
        listings.append(group['listing'])
        for page in listing['pages']:
            verified_read(page);verified_read(page['headers'])
            listings.extend([page,page['headers']])
    probes=[file_record(p) for p in sorted((CAT/'source_metadata/prediction_probes').rglob('*.headers'))]
    write_json(target,{'schema':'swebench-instance-acquisition-manifest-v1',
                       'created_at_utc':datetime.now(timezone.utc).isoformat(),
                       'plan':file_record(CAT/'plan.json'),'supplement_plan':file_record(CAT/'supplement-plan.json'),'discovery':file_record(CAT/'discovery.json'),
                       'listings':listings,'prediction_probes':probes,'files':files,
                       'counts':dict(Counter(i['artifact'] for i in files)),
                       'bytes':sum(i['bytes'] for i in files),
                       'integrity':'all HTTP200/listing or HEAD bytes/ETag; single-part ETag MD5 where available; local SHA256; JSON parse',
                       'source_boundary':'current mutable S3; not frozen historical Git bytes',
                       'agent_or_verifier_executed':False})
    print(json.dumps({'sealed':len(files),'bytes':sum(i['bytes'] for i in files)}),flush=True)


def parse_report(data,task,allow_flat=False):
    """Read the publisher's explicit boolean; never re-grade a saved test."""
    try:obj=json.loads(data)
    except (ValueError,UnicodeError):return {'status':'invalid_report_json','resolved':None}
    if not isinstance(obj,dict):
        return {'status':'report_instance_id_mismatch','resolved':None}
    if isinstance(obj.get(task),dict):
        record=obj[task];binding='native_instance_json_key'
    elif allow_flat and type(obj.get('resolved')) is bool and type(obj.get('patch_exists')) is bool:
        record=obj;binding='exact_S3_instance_directory_flat_report'
    else:return {'status':'report_instance_id_mismatch','resolved':None}
    if type(record.get('resolved')) is not bool:
        return {'status':'report_resolved_not_boolean','resolved':None}
    return {'status':'explicit_instance_report','resolved':record['resolved'],'instance_binding':binding,
            'fields':{k:record[k] for k in ('patch_is_None','patch_exists','patch_successfully_applied','infra_failure','infra_failure_reason') if k in record},
            'test_status_counts':{k:{s:len(v) for s,v in r.items() if isinstance(v,list)}
                                  for k,r in (record.get('tests_status') or {}).items() if isinstance(r,dict)}}


def prediction_rows(data):
    if data.lstrip().startswith(b'['):
        values=json.loads(data)
        if not isinstance(values,list):raise ValueError('prediction array required')
        return values
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def parse_predictions(data):
    records=defaultdict(list)
    for obj in prediction_rows(data):
        if not isinstance(obj,dict) or not isinstance(obj.get('instance_id'),str):
            raise ValueError('invalid prediction record')
        patch=obj.get('model_patch')
        records[obj['instance_id']].append({'patch_is_string':isinstance(patch,str),'empty_patch':patch in ('',None),
                                           'patch_sha256':hashlib.sha256(patch.encode()).hexdigest() if isinstance(patch,str) else None})
    return dict(records)


def canonical_task(group,task,objects):
    """The KGCompass filename contains a model suffix; use native task metadata."""
    if 'KGCompass' not in group:return task, 'original_filename'
    ids=set()
    for obj in objects:
        text=Path(obj['path']).read_text()
        ids.update(re.findall(r'^\s*- Instance ID:\s*(\S+)\s*$',text,re.M))
    if len(ids)!=1:
        raise ValueError('KGCompass missing/ambiguous native task ID')
    value=next(iter(ids))
    if not INSTANCE.fullmatch(value) or not task.startswith(value+'.'):
        raise ValueError('KGCompass native metadata/filename mismatch')
    return value,'native_task_metadata_with_filename_prefix_check'


def legacy_evidence(data):
    text=data.decode('utf-8')
    markers=re.findall(r'^>>>>> (.+)$',text,re.M)
    return {'markers':dict(Counter(markers)),
            'test_script_completed':bool(re.search(r'^.*Test script run successful\s*$',text,re.M)) and
                                    bool({'Some Tests Failed','All Tests Passed'} & set(markers)),
            'tests_all_passed_marker':'All Tests Passed' in markers,
            'error_markers':[m for m in markers if any(s in m.lower() for s in ('failed to','timeout','timed out','reset failed','tests errored'))]}


def classify(evaluation,report=None,legacy=None,prediction=None):
    memberships=set(evaluation['memberships'])
    published=evaluation.get('reported_resolved')
    if report and report['resolved'] is not None:
        value=report['resolved']
        conflicts=[]
        if published is not None and published is not value:conflicts.append('summary_vs_instance_report')
        if value and memberships & {'no_generation','no_logs','no_apply','test_errored','test_timeout'}:
            conflicts.append('positive_report_vs_saved_failure_stage')
        if conflicts:
            return {'status':'conflicting_published_results','resolved':None,
                    'basis':'instance_report_and_public_summary_disagree','conflicts':conflicts}
        return {'status':'resolved' if value else 'unresolved','resolved':value,
                'basis':'explicit_instance_report','conflicts':conflicts}
    if published is not None:
        return {'status':'resolved' if published else 'unresolved','resolved':published,
                'basis':'explicit_public_summary','conflicts':[]}
    if 'no_generation' in memberships:
        return {'status':'no_generation','resolved':None,'basis':'explicit_public_summary_stage','conflicts':[]}
    if legacy and legacy['test_script_completed'] and not legacy['error_markers'] and {'applied','with_logs'}<=memberships:
        # Complement is confined to a positively evaluated cohort, not all IDs.
        return {'status':'legacy_completed_not_resolved','resolved':False,
                'basis':'completed_legacy_log_and_published_applied_with_logs_not_resolved','conflicts':[]}
    if memberships & {'no_apply','install_fail','reset_failed','test_errored','test_timeout'}:
        return {'status':'evaluation_stage_failure','resolved':None,'basis':'explicit_public_summary_stage','conflicts':[]}
    if prediction and len(prediction)==1 and prediction[0]['empty_patch']:
        return {'status':'empty_prediction','resolved':None,'basis':'saved_prediction_empty_patch','conflicts':[]}
    if 'no_logs' in memberships:
        return {'status':'evaluation_logs_missing','resolved':None,'basis':'explicit_public_summary_stage','conflicts':[]}
    if report:
        return {'status':'invalid_instance_report','resolved':None,'basis':report['status'],'conflicts':[]}
    return {'status':'no_public_result_artifact','resolved':None,'basis':'complete_log_prefix_listing_and_saved_summary','conflicts':[]}


def analyze():
    if OUT.exists():raise FileExistsError(OUT)
    inputs={}
    frozen_code=[file_record(Path(__file__)),file_record(ROOT/'tests/test_swebench_instance_results.py')]
    def read(entry):
        data=verified_read(entry);inputs[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    base_manifest=json.loads(read(file_record(BASE/'manifest.json')))
    baseline_inputs={e['path']:e for e in base_manifest['inputs']}
    for entry in base_manifest['outputs']:read(entry)
    acquisition=json.loads(read(file_record(CAT/'manifest.json')))
    discovery=json.loads(read(acquisition['discovery']))
    read(acquisition['plan'])
    read(acquisition['supplement_plan'])
    for entry in acquisition['listings']+acquisition['prediction_probes']:read(entry)
    reports,legacy,predictions,diagnostics={},{},{},{}
    for i,entry in enumerate(acquisition['files'],1):
        data=read(entry);read(entry['headers'])
        key=(entry['group'],entry['task'])
        if entry['artifact']=='instance_report':
            if Path(entry['key']).parts[-2:]!=(entry['task'],'report.json'):raise ValueError('report directory/task mismatch')
            reports[key]={**parse_report(data,entry['task'],allow_flat=True),'path':entry['path']}
        elif entry['artifact']=='legacy_evaluation_log':legacy[key]={**legacy_evidence(data),'path':entry['path']}
        elif entry['artifact']=='predictions':predictions[entry['group']]=parse_predictions(data)
        else:
            text=data.decode('utf-8')
            diagnostics[key]={'path':entry['path'],'explicit_error_lines':[line[:1000] for line in text.splitlines()
                              if re.search(r'(?:EvaluationError|Error evaluating|Evaluation error|Failed to apply patch|Traceback \(most recent call last\))',line)]}
        if i%5000==0:print(f'verified/parsing {i}/{len(acquisition["files"])}',flush=True)
    sources=json.loads((BASE/'evaluation_sources.json').read_text())
    # Re-read and bind the exact original public summary files.
    from swebench_coverage_results import parse_results
    memberships={}
    for group,source in sources.items():
        if source['available']:
            data=read(baseline_inputs[source['path']]); memberships[group]=parse_results(data)[0]
        else:memberships[group]={}
    instances=[];remapped=[];cross=Counter();native=Counter();patch_binding=Counter()
    old_unknown=Counter();old_missing=Counter();old_other=Counter()
    for line in (BASE/'per_instance.jsonl').open():
        old=json.loads(line);group=old['group'];oldtask=old['task']
        # Native KGCompass metadata is outside the baseline output manifest but
        # every source object is bound by its input SHA. Verify before reading.
        for obj in old['objects']:
            if 'KGCompass' in group:
                read(baseline_inputs[obj['path']])
        task,identity=canonical_task(group,oldtask,old['objects'])
        ev=result_link(task,memberships[group],sources[group]['available'])
        if task!=oldtask:remapped.append({'group':group,'old_task':oldtask,'task':task,'basis':identity})
        report=reports.get((group,task));log=legacy.get((group,task));pred=predictions.get(group,{}).get(task)
        outcome=classify(ev,report,log,pred)
        diagnostic=diagnostics.get((group,task))
        if outcome['status'] in ('no_public_result_artifact','evaluation_logs_missing') and diagnostic and diagnostic['explicit_error_lines']:
            outcome={'status':'evaluation_stage_failure','resolved':None,'basis':'explicit_evaluation_diagnostic_error','conflicts':[]}
        for n in old['native_records']:
            patch=n['submission_patch_sha256']
            if patch and pred and len(pred)==1:
                binding='exact_patch_bytes_match' if patch==pred[0]['patch_sha256'] else 'patch_bytes_differ'
            else:binding='patch_comparison_unavailable'
            patch_binding[binding]+=1
            label=n.get('last_saved_transition') if n['format']=='moatless-transitions' else n['termination']['value']
            native[(group,str(label),outcome['status'])]+=1
        row={**old,'previous_task':oldtask,'task':task,'task_identity_basis':identity,
             'previous_evaluation':old['evaluation'],'evaluation':{**outcome,'status':outcome['status']},
             'published_summary':ev,'instance_report':report,'legacy_log':log,'prediction':pred,'evaluation_diagnostic':diagnostic}
        instances.append(row);cross[(old['evaluation']['status'],outcome['status'])]+=1
        if old['evaluation']['status']=='not_listed_in_saved_fields':old_unknown[outcome['status']]+=1
        if old['evaluation']['status']=='evaluation_file_missing':old_missing[outcome['status']]+=1
        if old['evaluation']['status']=='listed_other_saved_fields':old_other[outcome['status']]+=1
    if len({(r['group'],r['task']) for r in instances})!=len(instances):raise ValueError('canonical identity duplicates')
    groups={}
    for group in sorted(sources):
        rows=[r for r in instances if r['group']==group]
        groups[group]={'trace_instance_keys':len(rows),'outcomes':dict(Counter(r['evaluation']['status'] for r in rows)),
                       'downloaded_reports':sum(g==group for g,t in reports),'downloaded_legacy_logs':sum(g==group for g,t in legacy),
                       'predictions_available':group in predictions,
                       'prediction_instances':len(predictions.get(group,{})),
                       'report_parser_statuses':dict(Counter(r['status'] for (g,t),r in reports.items() if g==group)),
                       'conflicting_instances':sum(bool(r['evaluation']['conflicts']) for r in rows)}
    strata,excluded=strata_for_instances(instances)
    selected=[json.loads(x) for x in (BASE/'subset90_links.jsonl').open()]
    lookup={(r['group'],r['previous_task']):r for r in instances}
    subset=[{'group':r['group'],'task':r['task'],'selected_path':r['selected_path'],
             'evaluation':lookup[(r['group'],r['task'])]['evaluation'],
             'instance_report':lookup[(r['group'],r['task'])]['instance_report'],
             'legacy_log':lookup[(r['group'],r['task'])]['legacy_log']} for r in selected]
    summary={'schema':'swebench-instance-results-analysis-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
             'acquisition_counts':acquisition['counts'],'acquisition_bytes':acquisition['bytes'],
             'groups':groups,'trace_group_instance_keys':len(instances),
             'distinct_canonical_task_ids':len({r['task'] for r in instances}),
             'outcomes':dict(Counter(r['evaluation']['status'] for r in instances)),
             'previous_8730_now':dict(old_unknown),'previous_666_missing_summary_now':dict(old_missing),
             'previous_1747_other_fields_now':dict(old_other),
             'native_task_id_corrections':len(remapped),'conflicting_instances':sum(bool(r['evaluation']['conflicts']) for r in instances),
             'native_patch_prediction_comparison':dict(patch_binding),
             'behavior_strata':strata,'multiple_behavior_rows_excluded':excluded,
             'source_result_boundary':'publisher reports and stages; no grading or benchmark rerun; exact attempt identity not presumed',
             'legacy_boundary':'legacy not-resolved inference requires completed test log plus explicit published applied/with_logs cohort',
             'old_raw_and_reports_preserved':True,'agent_or_verifier_executed':False}
    OUT.mkdir(parents=True)
    for name,rows in [('per_instance.jsonl',instances),('subset90_links.jsonl',subset),('task_identity_corrections.jsonl',remapped)]:
        with (OUT/name).open('w') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    write_json(OUT/'summary.json',summary)
    write_json(OUT/'report_schema_review.json',{'counts':dict(Counter(r['status'] for r in reports.values())),
                                             'problems':[{'group':g,'task':t,**r} for (g,t),r in reports.items() if r['resolved'] is None]})
    def csv_out(name,fields,rows):
        with (OUT/name).open('w',newline='') as stream:
            w=csv.DictWriter(stream,fields);w.writeheader();w.writerows(rows)
    outcomes=sorted(summary['outcomes'])
    csv_out('group_outcomes.csv',['group','trace_instance_keys','downloaded_reports','downloaded_legacy_logs']+outcomes,
            [{'group':g,**{k:s[k] for k in ('trace_instance_keys','downloaded_reports','downloaded_legacy_logs')},
              **{k:s['outcomes'].get(k,0) for k in outcomes}} for g,s in groups.items()])
    csv_out('result_recovery.csv',['previous_status','current_status','instances'],
            [{'previous_status':k[0],'current_status':k[1],'instances':v} for k,v in sorted(cross.items())])
    csv_out('native_result_cross_tabs.csv',['group','native_value','evaluation_status','instances'],
            [{'group':k[0],'native_value':k[1],'evaluation_status':k[2],'instances':v} for k,v in sorted(native.items())])
    csv_out('behavior_strata.csv',['group','unit_kind','result','n','median','q1','q3','iqr'],
            [{'group':r['group'],'unit_kind':r['unit_kind'],'result':r['saved_result_stratum'],
              **{k:r['saved_units_per_instance'][k] for k in ('n','median','q1','q3','iqr')}} for r in strata])
    # Human-readable findings are rendered in a separate offline step after
    # reviewing any unexpected schemas; preserve these machine results frozen.
    for record in list(inputs.values())+frozen_code:verified_read(record)
    write_json(OUT/'manifest.json',{'schema':'swebench-instance-analysis-manifest-v1','inputs':list(inputs.values()),
                                   'analysis_code_and_tests':frozen_code,
                                   'outputs':[file_record(p) for p in sorted(OUT.iterdir()) if p.is_file()]})
    print(json.dumps({k:summary[k] for k in ('outcomes','previous_8730_now','previous_666_missing_summary_now','native_task_id_corrections','conflicting_instances')},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--supplement-plan', action='store_true')
    args = parser.parse_args()
    if args.discover:
        discover()
    elif args.plan:
        plan_download()
    elif args.seal:
        seal()
    elif args.analyze:
        analyze()
    elif args.supplement_plan:
        supplement_plan()
