#!/usr/bin/env python3
"""Read-only acceptance, task statistics and charts for the fixed local batch."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import html
import json
import math
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'src')]
import local_three_class_repeat_01_entry as batch
import volcano_three_chain_characterization as base
from public_trace_software_toolkits import validate_docops_runtime, DOCOPS_LIBS

OUTPUT = Path('reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-characterization-v1')


def distribution(values):
    points=[v for v in values if type(v) in (int,float) and math.isfinite(v)]
    ordered=sorted(points)
    def q(p):
        if not ordered:return None
        x=(len(ordered)-1)*p; i=int(x); j=min(i+1,len(ordered)-1)
        return ordered[i]+(ordered[j]-ordered[i])*(x-i)
    return {'n':len(points),'raw_points':points,'median':q(.5),'q1':q(.25),'q3':q(.75),
            'iqr':q(.75)-q(.25) if points else None,
            'quantile_method':'linear interpolation at (n-1)*p; missing excluded per metric'}


def verify(root, inp):
    frozen=inp.json(batch.ENV/'frozen-identity.json'); plan=inp.json(batch.ENV/'plan-identity.json')
    base.require(plan==frozen and batch.digest(plan['identity'])==plan['identity_sha256'], 'full identity mismatch')
    digest=plan['identity_sha256']
    drift=[]
    for row in batch.files_in_identity(plan['identity']):
        inp.data(Path(row['path']))
        now=inp.records[str(root/row['path'])]
        if now!=row:
            candidate=batch.ENV/'source-before/local_three_class_repeat_01_entry.frozen.py'
            base.require(row['path']==str(batch.ENTRY),'unexplained execution code/input drift')
            snapshot=inp.data(candidate)
            base.require(len(snapshot)==row['bytes'] and batch.hashlib.sha256(snapshot).hexdigest()==row['sha256'],
                         'execution snapshot mismatch')
            if not drift:drift.append({'path':row['path'],'execution':row,'current':now,'snapshot':str(candidate),
                                      'reason':'offline acceptance-key fix after batch stopped; no resume/refreeze'})
    approval=inp.json(batch.REPORT/'APPROVAL.json')
    base.require(approval['identity_sha256']==digest and approval['scope']==batch.schedule(), 'approval binding mismatch')
    m=inp.json(batch.REPORT/'manifest.json')
    for row in [*m['inputs'],*m['raw_manifests'],*m['outputs']]:
        inp.check(Path(row['path']),row)
    summary=inp.json(batch.REPORT/'batch-summary.json')
    base.require(summary['identity_sha256']==digest,'batch identity mismatch')
    base.require([{k:r[k] for k in ('sequence','chain','task','round')} for r in summary['runs']]==batch.schedule(),'slot/order mismatch')
    ids=[r['run_id'] for r in summary['runs'] if r.get('run_id')]
    base.require(len(ids)==len(set(ids)),'duplicate run ID')
    actual={p.name for p in (root/batch.RAW).iterdir() if p.is_dir()} if (root/batch.RAW).exists() else set()
    base.require(actual==set(ids),'unregistered raw run directory')
    sets={}
    for row in summary['runs']:
        if not row.get('run_id'):continue
        raw=Path(row['raw_path']); doc=inp.json(raw/'manifest.json')
        if row['chain']=='Coding':
            base.require(inp.json(raw/'metadata.json')['identity_sha256']==digest,'raw Coding identity mismatch')
            entries=[{'path':p,'sha256':h} for p,h in doc['files'].items()]
        else:
            base.require(doc['identity_sha256']==digest,'raw identity mismatch')
            entries=doc['outputs'] if row['chain']=='Office' else doc['files']
        expected={e['path'] for e in entries}
        names={str(p.relative_to(root/raw)) for p in (root/raw).rglob('*') if p.is_file() and p.name!='manifest.json'}
        base.require(names==expected,'raw file set mismatch')
        sets[str(raw)]=sorted(names|{'manifest.json'})
        for e in entries:inp.check(raw/e['path'],e)
        report=inp.json(Path(row['report_path']))
        base.require(report['identity_sha256']==digest and report['run_id']==row['run_id'],'run report binding mismatch')
        marker=inp.json(Path(row['report_path']).parent/'ATTEMPT_STARTED.json' if row['chain']=='Coding' else raw/'ATTEMPT_STARTED.json')
        base.require(marker['identity_sha256']==digest,'attempt binding mismatch')
    return plan,summary,sets,drift


def primary_metrics(run):
    main=next((s for s in run['scopes'] if s['scope_kind'] in
               ('shared_task_container','agent_container','shared_Agent_User_tools_evaluator_worker')),None)
    values={'attempt_wall_s':run['attempt_wall_s'],
        'logical_requests':run['behavior']['logical_requests'],
        'agent_requests':run['behavior']['requests_by_role'].get('agent',0),
        'user_requests':run['behavior']['requests_by_role'].get('user',0),
        'agent_tools':run['behavior']['tools_by_role'].get('agent',0),
        'bootstrap_tools':run['behavior']['tools_by_role'].get('bootstrap',0),
        'user_tools':run['behavior']['tools_by_role'].get('user',0),
        'tool_errors':run['behavior']['ordinary_tool_errors'],
        'request_union_s':run['behavior']['request_union_s'],
        'tool_union_s':run['behavior']['tool_window_union_s']}
    if main:
        values.update(main_scope_cpu_s=main['metric_quality']['cpu']['observed_valid_delta_sum'],
            main_scope_sample_window_s=main['sample_window_s'],
            memory_sampled_peak_bytes=main['memory_sampled_peak_bytes'],
            kernel_memory_peak_bytes=main['kernel_memory_peak_bytes'])
        for metric,data in main['metric_quality'].items():
            if metric!='cpu':values[metric+'_bytes']=data['observed_valid_delta_sum']
    for p in run['phases']:
        values[p['name']+'_wall_s']=p.get('wall_s')
        values[p['name']+'_cpu_s']=p.get('shared_cpu_s')
    return values


def summarize_tasks(slots,runs):
    out=[]
    for chain,tasks in batch.TASKS.items():
        for task in tasks:
            points=[r for r in runs if r['chain']==chain and r['task']==task]
            keys=sorted({k for r in points for k in r['metrics']})
            planned=[s for s in slots if s['chain']==chain and s['task']==task]
            out.append({'chain':chain,'task':task,'planned':3,'actual_n':len(points),
                'executed':sum(s['status']=='executed' for s in planned),
                'failed':sum(s['status']=='failed' for s in planned),
                'not_executed':sum(s['status']=='not_executed' for s in planned),
                'run_ids':[r['run_id'] for r in points],
                'results':[r['task_result'] for r in points],
                'metrics':{k:distribution([r['metrics'].get(k) for r in points]) for k in keys}})
    return out


def csv_file(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def point_plot(task):
    """Three quantities on independent panels, never a common unit axis."""
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="460" viewBox="0 0 1200 460">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<style>text{font:12px sans-serif;fill:#243447}</style>',
         f'<text x="20" y="25">{html.escape(task["task"])}: original points, median and IQR; no category ranking</text>']
    for i,(key,label,scale) in enumerate((('attempt_wall_s','attempt wall (s)',1),
           ('main_scope_cpu_s','main-scope sampled CPU (CPU-s)',1),
           ('memory_sampled_peak_bytes','sampled memory (MiB)',1048576))):
        s=task['metrics'].get(key,distribution([]));x=55+i*395;y0=350
        values=[v/scale for v in s['raw_points']];high=max(values,default=1)*1.15 or 1
        yy=lambda v:y0-v/high*240
        out.extend([f'<text x="{x}" y="70">{label}; valid n={s["n"]}</text>',
                    f'<path d="M{x} 100V{y0}H{x+300}" fill="none" stroke="#999"/>'])
        if values:
            q1,q3,med=[s[k]/scale for k in ('q1','q3','median')]
            out.append(f'<path d="M{x+240} {yy(q1)}V{yy(q3)}M{x+220} {yy(med)}H{x+260}" stroke="#b45309" stroke-width="5"/>')
            for j,v in enumerate(values):
                out.append(f'<circle cx="{x+45+j*65}" cy="{yy(v)}" r="5" fill="#165dbe"/><text x="{x+30+j*65}" y="{yy(v)-12}">{v:.4g}</text>')
            out.append(f'<text x="{x}" y="390">median={med:.5g}; IQR={q3-q1:.5g}</text>')
        else:out.append(f'<text x="{x}" y="210">not executed; no zero-filled points</text>')
    return '\n'.join(out+['</svg>'])


def small_multiples(task,runs,series_by_id):
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1510" viewBox="0 0 4500 1510">']
    for i,run_id in enumerate(task['run_ids']):
        run=next(r for r in runs if r['run_id']==run_id)
        svg=ET.fromstring(base.render_svg(run,series_by_id[run_id]))
        parts.append(f'<g transform="translate({1500*i},0)">')
        parts.extend(ET.tostring(child,encoding='unicode') for child in svg)
        parts.append('</g>')
    return '\n'.join(parts+['</svg>'])


def markdown(summary):
    out=['# LOCAL-THREE-CLASS-REPEAT-01：限定执行与特征化','',
        f"计划27槽位；实际启动 {len(summary['runs'])}。原批次状态 {summary['counts']}。批wall {summary['batch_wall_s']:.3f}s。",'',
        'Coding两个固定Astropy镜像缺失，无登记本地禁网恢复上下文；全类9槽位未执行。未拉取、未换任务或用旧样本充数。首个Office Excel完成后，新增批次验收错误读取host_agent（实际为host_agent_process），触发KeyError并全批停止。其余Office8与Assistant9未启动，不补跑。',
        '原批次archive_verified=false是该验收异常路径写出的状态，不是已证明raw损坏。独立只读验收重新核对文件集合与哈希、容器删除和镜像保留；不改写原batch-summary/VALIDATION。停止后仅修正验收键并离线回归，执行时源码已保存精确快照，不重冻结、不续跑。',
        '', '## 逐run四维结果','',
        '|链路/round|run_id|请求/自主工具/bootstrap/User工具|测量主项|官方结果|终止|infra/归档|wall s|主scope CPU-s|内存峰值MiB|曲线|',
        '|---|---|---|---|---|---|---|---:|---:|---:|---|']
    for r in summary['runs']:
        m=r['metrics'];v=lambda k:'unknown' if m.get(k) is None else f'{m[k]:.4f}'
        peak=m.get('memory_sampled_peak_bytes')
        out.append(f"|{r['chain']}/r{r['round']}|{r['run_id']}|{m['logical_requests']}/{m['agent_tools']}/{m['bootstrap_tools']}/{m['user_tools']}|{r['four_dimensions']['measurement']}|{json.dumps(r['task_result'],ensure_ascii=False)}|{json.dumps(r['termination'],ensure_ascii=False)}|{r['four_dimensions']['infrastructure_archive']}|{v('attempt_wall_s')}|{v('main_scope_cpu_s')}|{peak/1048576:.3f}|[SVG]({r['figure']})|" if peak is not None else f"|{r['chain']}|{r['run_id']}|见JSON|partial|unknown|unknown|见JSON|{v('attempt_wall_s')}|unknown|unknown|[SVG]({r['figure']})|")
    out += ['', '## 固定任务内重复（不跨task混合）','',
        '|链路|任务|实际n|wall median / IQR s|主scope CPU median / IQR CPU-s|内存median / IQR MiB|图|',
        '|---|---|---:|---|---|---|---|']
    for t in summary['tasks']:
        def text(key,scale=1):
            m=t['metrics'].get(key)
            if m and m['n']<3:
                return f"原始点 {[v/scale for v in m['raw_points']]} (n={m['n']}；不足3次)"
            return 'not_executed' if not m else f"{m['median']/scale:.4f} / {m['iqr']/scale:.4f} (n={m['n']})" if m['n'] else 'unknown'
        out.append(f"|{t['chain']}|{t['task']}|{t['actual_n']}|{text('attempt_wall_s')}|{text('main_scope_cpu_s')}|{text('memory_sampled_peak_bytes',1048576)}|[原始点/median/IQR]({t['distribution_figure']})" + (f"；[已有run四面板：n={t['actual_n']}]({t['small_multiples_figure']})|" if t.get('small_multiples_figure') else '|'))
    out += ['', '## 范围与限制','',
        '- 三次重复不是三个独立任务；分位数采用(n−1)×p线性插值，缺测按指标实际n，不补零。原始点与阶段CPU/wall详见per_run.jsonl及task_statistics.csv。',
        '- CPU为有效相邻区间累计差分/同窗口wall的平均core，不是瞬时值；共享容器/共享worker、宿主RSS分列，不是单工具独占资源。内核peak不是独立阶段peak，内存指标不相加。',
        '- 请求时长不是思考时间；业务工具错误、bootstrap失败、官方评分和infra分列。没有HTTP hook和账单证据，HTTP次数及费用unknown。别名与响应model不保证后端不可变。',
        '- 网络为共享netns逐接口观测，最多展示3个完整窗口有效非lo接口，按rx+tx变化量及名称确定性选择；不是API出口，虚拟接口不得相加。完整接口统计保留在JSON。',
        '- I/O是cgroup block service或/proc原口径；rchar/wchar和read/write_bytes分列，不是完整文件系统流量。目录采用apparent size；扫描活动未从资源中剔除，宿主目录结束扫描早于最终归档，不称最终归档总大小。cache仍unsupported。',
        '- 采样窗不是attempt wall；gap断线，不插值，实际阶段边界见每run SVG。小多图每run保持真实时长和轴标签，不绘制平均轨迹。',
        '- ARM64适配DocOps不声称与官方amd64字节等价；Assistant为模拟业务工具，不映射真实外部品牌。无跨类别因果、排名、Office/Assistant总体结论。',
        '- Coding历史RC7保留。本轮只修wrapper按runner的ok/failed状态契约映射，不更改旧运行或历史身份。',
        '- 仅完成SVG XML/数值/链接核验，未完成浏览器实际渲染；未安装新平台。G2/G3-R不变，CPU-02/Replay暂停。',
        '', '## 原始行为路径','']
    for r in summary['runs']:
        seq=' → '.join(f"{x['role']}:{x['name']}"+(' [error]' if x.get('ok') is False or x['status']=='error' else '') for x in r['behavior']['tools'])
        out += [f"- {r['run_id']}: {seq}。"]
    return '\n'.join(out)+'\n'


def build(root=ROOT,output=None):
    root=Path(root).resolve();out=Path(output) if output else root/OUTPUT
    base.require(not out.exists(),'refuse existing analysis output')
    inp=base.Inputs(root); frozen,b,sets,drift=verify(root,inp)
    runs=[];series_by_id={}
    for slot in b['runs']:
        if not slot.get('run_id'):continue
        spec=(slot['chain'],batch.COLLECTION,slot['run_id'],str(batch.ENV))
        r,data=base.analyze_run(inp,spec,frozen,slot['returncode'],report_path=Path(slot['report_path']))
        r.update(task=slot['task'],round=slot['round'],sequence=slot['sequence'])
        r['figure']=f"figures/{slot['run_id']}.svg";r['series_csv']=f"series/{slot['run_id']}.csv"
        r['four_dimensions']={'measurement':'partial' if slot.get('measurement_gaps') or any(r['behavior']['pairing_quality'].values()) else 'complete_in_observed_main_windows',
            'official_result':r['task_result'],'termination':r['termination'],
            'infrastructure_archive':'independent raw file set and SHA verified; original batch acceptance '+slot['status']}
        r['original_batch_acceptance']=slot
        r['metrics']=primary_metrics(r)
        runs.append(r);series_by_id[r['run_id']]=data
    tasks=summarize_tasks(b['runs'],runs)
    out.mkdir(parents=True);(out/'figures').mkdir();(out/'series').mkdir()
    for r in runs:
        svg=base.render_svg(r,series_by_id[r['run_id']]);ET.fromstring(svg)
        (out/r['figure']).write_text(svg)
        rows=[dict(x,run_id=r['run_id'],start_s=(x['t0']-r['origin_monotonic_ns'])/1e9 if type(x['t0']) is int else None,
                  end_s=(x['t1']-r['origin_monotonic_ns'])/1e9 if type(x['t1']) is int else None) for x in series_by_id[r['run_id']]]
        csv_file(out/r['series_csv'],rows,['run_id','scope','scope_kind','metric','t0','t1','start_s','end_s','value','unit','status','reason','delta','source','locator'])
    statrows=[]
    for i,t in enumerate(tasks):
        t['distribution_figure']=f'figures/task-{i}-points.svg'
        svg=point_plot(t);ET.fromstring(svg);(out/t['distribution_figure']).write_text(svg)
        if t['run_ids']:
            t['small_multiples_figure']=f'figures/task-{i}-small-multiples.svg'
            svg=small_multiples(t,runs,series_by_id);ET.fromstring(svg);(out/t['small_multiples_figure']).write_text(svg)
        for key,s in t['metrics'].items():
            statrows.append({'chain':t['chain'],'task':t['task'],'metric':key,**{k:s[k] for k in ('n','median','q1','q3','iqr')},'raw_points':json.dumps(s['raw_points'])})
    csv_file(out/'task_statistics.csv',statrows,['chain','task','metric','n','raw_points','median','q1','q3','iqr'])
    disks=[];tools=[]
    runtime=Path('references/repos/DocOps/harnesses/document_tools_runtime.py')
    bound_runtime=next((x for x in batch.files_in_identity(frozen['identity']) if x['path']==str(runtime)),None)
    mapping={}
    if bound_runtime:
        inp.check(runtime,bound_runtime)
        mapping=validate_docops_runtime(inp.data(runtime).decode())
    for r in runs:
        for scope,p in base.disk_rows(r):
            disks.append({'chain':r['chain'],'task':r['task'],'run_id':r['run_id'],'scope':scope,
                'path':(p.get('before') or p.get('after') or {}).get('path'),
                'before_bytes':(p.get('before') or {}).get('bytes'),'after_bytes':(p.get('after') or {}).get('bytes'),
                'delta_bytes':p.get('delta_bytes'),'status':p.get('delta_status'),'basis':'apparent_file_size_bytes'})
        counts=Counter((x['role'],x['name']) for x in r['behavior']['tools'])
        for (role,name),count in counts.items():
            library=DOCOPS_LIBS[name][0] if r['chain']=='Office' and name in mapping and name in DOCOPS_LIBS else None
            purpose=DOCOPS_LIBS[name][1] if library else '原生接口记录；通用检查分支未在此表重建' if r['chain']=='Office' else '模拟业务工具'
            tools.append({'chain':r['chain'],'task':r['task'],'run_id':r['run_id'],'role':role,'native_interface':name,
                'recorded_calls':count,'scope':'saved ID-paired calls, not exclusive resource attribution',
                'purpose':purpose,'implementation_library':library or 'unknown/not_applicable',
                'implementation_evidence':str(runtime)+':'+str(mapping[name]['function_line']) if library else 'no product inference',
                'implementation_limit':'bound handler library involvement; not internal function count; inspect_document branch unknown; no GUI product claim'})
    csv_file(out/'directory_footprint.csv',disks,['chain','task','run_id','scope','path','before_bytes','after_bytes','delta_bytes','status','basis'])
    csv_file(out/'operation_toolkits.csv',tools,['chain','task','run_id','role','native_interface','recorded_calls','scope','purpose','implementation_library','implementation_evidence','implementation_limit'])
    history=inp.json(batch.ENV/'history-before.json')
    for directory,rows in history.items():
        names={str(p.relative_to(root)) for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        base.require(names=={r['path'] for r in rows},'historical file set changed: '+directory)
        for row in rows:
            inp.check(Path(row['path']),row)
    summary={'collection':batch.COLLECTION,'identity_sha256':frozen['identity_sha256'],'counts':b['counts'],
             'batch_wall_s':b['wall_s'],'class_stops':b['class_stops'],'global_stop':b['global_stop'],
             'runs':runs,'slots':b['runs'],'tasks':tasks,
             'execution_code_drift':drift,
             'history_protection':{'directories':len(history),'files':sum(map(len,history.values())),'result':'unchanged'},
             'source_path_drift':'Coding wrapper and analysis projection changed; exact pre-edit sources preserved in env/local-three-class-repeat-01/source-before; old manifests untouched',
             'browser_rendering':'not performed; XML and local-link checks only'}
    (out/'summary.md').write_text(markdown(summary))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (out/'per_run.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in runs))
    for p in (Path(__file__),ROOT/'scripts/volcano_three_chain_characterization.py',
              ROOT/'scripts/toolsandbox_resource_pilot_02_review.py',
              ROOT/'scripts/public_trace_software_toolkits.py',
              ROOT/'src/agent_workload_characterization/collectors/execution_measurement.py',
              ROOT/'src/agent_workload_characterization/analyzers/public_operations.py'):
        inp.data(p.resolve())
    for key,row in list(inp.records.items()):
        base.require(base.file_record(Path(key),root)==row,'input changed during analysis')
    for directory,names in sets.items():
        base.require(sorted(str(p.relative_to(root/directory)) for p in (root/directory).rglob('*') if p.is_file())==names,'run file set changed during analysis')
    manifest={'input_root':str(root),'output_root':str(out),'inputs':sorted(inp.records.values(),key=lambda x:x['path']),
              'outputs':[base.file_record(p,out) for p in sorted(out.rglob('*')) if p.is_file()],
              'historical_file_sets':sets,'history_protection':summary['history_protection']}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for row in manifest['outputs']:
        base.require(base.file_record(out/row['path'],out)==row,'output readback mismatch')
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);a=ap.parse_args()
    s=build(a.root);print(json.dumps({'counts':s['counts'],'identity':s['identity_sha256'],'output':str(OUTPUT)}))
