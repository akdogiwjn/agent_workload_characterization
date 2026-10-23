"""Add auditable adjacent-prefix time locality without changing frozen base outputs."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import numpy as np

from scripts.agentx_deep_analysis import dump, table, file_record
from scripts.agentx_full_macro import distribution
from scripts.agentx_deep_presentation import BLUE, ORANGE, GREY, TEAL, ecdf, figure, save, style, write_pptx


def classify_pair(e):
    if 'adjacent_prefix_tokens' not in e:
        return 'first_in_native_stream'
    if not e['adjacent_model_same']:
        return 'adjacent_model_changed'
    if e['adjacent_interval_gap_s'] < 0:
        return 'adjacent_predecessor_not_completed'
    if not e['adjacent_prefix_tokens']:
        return 'no_nonempty_shared_prefix'
    return 'eligible_completed_adjacent_prefix_pair'


def run(out):
    out=Path(out)
    target=out/'locality_summary.json'
    if target.exists():raise FileExistsError(target)
    base_manifest=out/'manifest.json'
    base=json.loads(base_manifest.read_text())
    inputs=[file_record(base_manifest),file_record(out/'verification.json')]
    gaps=defaultdict(list);states={};ttl_rows=[]
    ttl=(0,1,5,10,30,60,300,3600)
    for variant in ['full','256k']:
        ledger=out/f'{variant}_request_metrics.jsonl'
        record=file_record(ledger)
        expected=next(r for r in base['outputs'] if r['path']==str(ledger))
        assert record['sha256']==expected['sha256']
        inputs.append(record)
        counts=Counter();shared=Counter();ttl_tokens=Counter()
        with ledger.open() as f:
            for line in f:
                e=json.loads(line);category=classify_pair(e)
                counts[category]+=1
                if category=='eligible_completed_adjacent_prefix_pair':
                    gaps[(variant,e['kind'])].append(e['adjacent_interval_gap_s'])
                    gaps[(variant,'all')].append(e['adjacent_interval_gap_s'])
                    shared[e['kind']]+=e['adjacent_prefix_tokens'];shared['all']+=e['adjacent_prefix_tokens']
                    for seconds in ttl:
                        if e['adjacent_interval_gap_s']<=seconds:
                            ttl_tokens[(e['kind'],seconds)]+=e['adjacent_prefix_tokens']
                            ttl_tokens[('all',seconds)]+=e['adjacent_prefix_tokens']
        states[variant]={'request_partition':dict(counts),
                         'eligible_pair_gap_s':{scope:distribution(gaps[(variant,scope)]) for scope in ['all','main','subagent']},
                         'eligible_adjacent_shared_tokens':dict(shared)}
        for scope in ['all','main','subagent']:
            for seconds in ttl:
                ttl_rows.append({'variant':variant,'scope':scope,'gap_limit_s':seconds,
                                 'eligible_adjacent_prefix_tokens_within_gap':ttl_tokens[(scope,seconds)],
                                 'all_eligible_adjacent_prefix_tokens':shared[scope],
                                 'share_of_eligible_adjacent_prefix_tokens_pct':ttl_tokens[(scope,seconds)]/shared[scope]*100 if shared[scope] else None})
    table(out/'plot_data'/'10_prefix_gap_limits.csv',ttl_rows)
    style()
    fig,ax=figure('前缀复用的时间局部性：相邻请求间隔','只看同一原生代理路径、同一保存模型、共享非空前缀且前序请求已完成的相邻对',
                 '横轴0–1秒为线性段，其余为对数段；保留真实0值，不给负间隔补零。每条线使用自身合格相邻对分母。\n间隔为前一API源区间结束到下一请求开始；不认定为工具耗时，也不是LRU栈距离或实际缓存命中。')
    rows=[]
    for variant,scope,color,ls,label in [('full','main',BLUE,'-','Full 主代理'),('full','subagent',TEAL,'--','Full 子代理'),('256k','main',ORANGE,'-','256k 主代理'),('256k','subagent',GREY,'--','256k 子代理')]:
        vals=gaps[(variant,scope)];x,y=ecdf(vals)
        ax.step(x,y,where='post',lw=2.8,color=color,ls=ls,label=f'{label} (n={len(vals):,})')
        for q in np.linspace(0,100,401):rows.append({'variant':variant,'scope':scope,'percentile':float(q),'gap_s':float(np.percentile(vals,q)),'eligible_pairs':len(vals)})
    ax.set_xscale('symlog',linthresh=1);ax.set(xlabel='已完成相邻前缀的源时间间隔（秒，0–1线性，其余对数）',ylabel='累计合格相邻对比例（%）',ylim=(0,100));ax.legend(loc='lower right')
    table(out/'plot_data'/'10_prefix_reuse_gap.csv',rows)
    save(fig,out,'10_prefix_reuse_gap')
    # Keep the original nine-slide file, and publish a distinct ten-slide final deck.
    headings=[line[3:].strip() for line in (out/'slide_notes.md').read_text().splitlines() if line.startswith('## ')]
    slides=[{'heading':heading,'image':image} for heading,image in zip(headings,sorted((out/'figures').glob('0*.png')))]
    assert len(slides)==9
    slides.append({'heading':'10. 前缀复用距离：已完成相邻请求的时间局部性','image':out/'figures'/'10_prefix_reuse_gap.png'})
    deck=out/'AgentX深入分析_汇报版_10页.pptx'
    write_pptx(deck,slides)
    report={'schema':'agentx-adjacent-prefix-locality-v1','date':'2026-10-23','variants':states,
            'pair_selection':'native same-agent adjacency; same model; nonempty shared prefix; predecessor end<=current start',
            'time_distance':'current source t minus predecessor source end; not tool time or LRU stack distance',
            'final_presentation':str(deck),'model_or_tool_calls':0}
    dump(target,report)
    s=json.loads((out/'summary.json').read_text());ft=s['full']['totals'];ct=s['capped_256k']['totals'];d=s['derived_findings']
    gap=states['full']['eligible_pair_gap_s']['all']
    text=['# AgentX 深入分析：最终发现与PPT入口','',
          '**第一步已完成：393个相同会话的Full/256k全量离线深入分析。** 本轮没有运行mock、真实模型或业务工具。','',
          '- [最终10页PPT](AgentX深入分析_汇报版_10页.pptx)：16:9，中文图表，3840×2160图片嵌入；标题可编辑。图表本体进一步编辑请使用相邻SVG与作图CSV。',
          '- [逐页讲解](presentation_notes.md) · [高清PNG与SVG](figures/) · [作图CSV](plot_data/)。',
          '- [完整方法与基础9图报告](summary.md) · [时间局部性机器结果](locality_summary.json) · [基础独立核验](verification.json)。','',
          '## 可用于汇报的结论','',
          f'1. **上下文随请求进度明显增长，同时有回退候选。** Full主代理流中有{d["sessions_with_main_context_drop_candidates"]}/393会话出现至少一次≥32,768 token相邻回退；输入回退不自动等于上下文压缩。图1按会话等权，图8是按明确规则选出的案例。',
          f'2. **前缀共享潜力高，不能当成实测命中。** Full在同会话/同保存模型/只使用已完成请求/历史不淘汰条件下，输入加权最长历史前缀潜力为{d["full_history_prefix_potential_input_weighted_pct"]:.2f}%。仅同agent路径为{d["same_agent_history_prefix_potential_input_weighted_pct"]:.2f}%；跨agent路径增加{d["cross_agent_additional_potential_input_weighted_pct"]:.2f}个百分点。图4是独立定义的最近完成前缀容量模型，不模拟真实GPU缓存。',
          f'3. **前缀复用具有可量化的时间局部性。** Full有{gap["n"]:,}对同路径、同模型、前序已完成且共享非空前缀的相邻请求，源区间间隔median={gap["median"]:.3f}秒、p95={gap["p95"]:.3f}秒。重叠、模型切换与首请求分别排除并登记。这个时间距离不是工具耗时或LRU栈距离。',
          f'4. **保存请求重叠十分常见。** Full有{s["full"]["sessions_with_request_overlap"]}/393会话出现API源区间重叠，会话峰值median={s["full"]["peak_request_overlap"]["median"]}，最大{s["full"]["peak_request_overlap"]["max"]}。主代理流也可能包含多路请求，不能直接当作串行链或硬件并发。',
          f'5. **256k筛选对主/子代理影响不同。** 主代理请求保留{ct["main:requests"]/ft["main:requests"]*100:.2f}%，子代理保留{ct["subagent:requests"]/ft["subagent:requests"]*100:.2f}%；全部重建输入累计量保留{ct["all:input"]/ft["all:input"]*100:.2f}%。影响{d["sessions_affected_by_256k"]}/393会话，主代理形成{d["cap_main_adjacencies_bridged"]}对跨被移除记录的新相邻关系。两版是重叠语料，不是独立实验组。',
          f'6. **少数会话贡献大部分累计输入。** 输入量最大的{d["top_10pct_sessions_count"]}个会话贡献{d["top_10pct_sessions_input_share_pct"]:.2f}%。这里重复前缀重复计入，不等于唯一语料、实际计算量或费用。','',
          '全量明细保存源行与JSON pointer，基础匹配算法经独立穷举核对6个真实会话、216个请求，并全量核对两版167,093个请求的边界、分母与见证。Full有9个原生group的子请求结束晚于保存group区间；差异已列入group_clock_audit.csv，不改写时间或强制构造JOIN。','',
          '源数据缺少原始业务内容、工具操作、任务结果和本地资源。本轮全部结论局限于请求结构与声明过的模型假设。下一步才是小样本地回放接线验证。']
    (out/'findings.md').write_text('\n'.join(text)+'\n')
    notes=(out/'slide_notes.md').read_text().replace('PPT逐页讲解','PPT逐页讲解（最终10页）')
    notes+='\n## 10. 前缀复用距离：时间局部性\n\n'+f'Full共有{gap["n"]:,}对合格相邻请求，间隔中位数{gap["median"]:.3f}秒。这里仅统计已完成的前序API区间，不能解释成工具耗时；跨模型和重叠记录均排除。完整排除数量和各子集分母见locality_summary.json。\n\n[PNG](figures/10_prefix_reuse_gap.png) · [SVG](figures/10_prefix_reuse_gap.svg)\n'
    (out/'presentation_notes.md').write_text(notes)
    output_paths=[target,deck,out/'findings.md',out/'presentation_notes.md',
                  out/'figures'/'10_prefix_reuse_gap.png',out/'figures'/'10_prefix_reuse_gap.svg',
                  out/'plot_data'/'10_prefix_reuse_gap.csv',out/'plot_data'/'10_prefix_gap_limits.csv']
    dump(out/'locality-manifest.json',{'schema':'agentx-deep-locality-manifest-v1','inputs':inputs,
          'code_and_tests':[file_record(Path(__file__)),file_record('tests/test_agentx_deep_locality.py')],
          'outputs':[file_record(p) for p in output_paths],
          'base_outputs_unchanged':True,'pair_partition_preserved':True})
    print(json.dumps({'status':'PASS','eligible_full_pairs':gap,'deck':str(deck)},ensure_ascii=False))


if __name__=='__main__':run(Path(sys.argv[1]) if len(sys.argv)>1 else Path('reports/analysis/AGENTX-DEEP-ANALYSIS-v1'))
