"""Twelve slides separating full-source structure from remote client experiments."""
from __future__ import annotations

import numpy as np

from scripts.agentx_deep_analysis import table
from scripts.agentx_deepseek_pilot import dump
from scripts.agentx_deep_presentation import style,figure,save,write_pptx,BLUE,ORANGE,TEAL

LABELS={'baseline':'单链基线','single_subagent':'单子代理','multiple_subagents':'多子代理',
        'serial_intervals':'原始区间串行','long_context':'长上下文'}
COLORS=[BLUE,TEAL,ORANGE,'#7C3AED','#DB2777']


def render(out,summary,offline,rows,profiles):
    style();slides=[];notes=[];metrics=summary['cases'];ranges=summary['ranges']
    footer='所选 5 个固定会话，每类 n=3；远程缓存/负载未控制，不作总体、因果或显著性判断。'
    def finish(fig,name,title,note):
        save(fig,out,name);svg=out/'figures'/f'{name}.svg'
        svg.write_text('\n'.join(q.rstrip() for q in svg.read_text().splitlines())+'\n')
        slides.append({'heading':title,'image':out/'figures'/f'{name}.png'});notes.append((title,note,name))
    def table_style(ax,cols,values,fontsize=16,scale=2.7):
        ax.axis('off');t=ax.table(cellText=values,colLabels=cols,loc='center',cellLoc='center')
        t.auto_set_font_size(False);t.set_fontsize(fontsize);t.scale(1,scale)
        for (r,c),cell in t.get_celld().items():
            cell.set_edgecolor('#CBD5E1')
            if r==0:cell.set_facecolor('#DBEAFE');cell.set_text_props(weight='bold')
    def series(axis,field):
        for label,color in zip(LABELS,COLORS):
            current=[q for q in metrics if q['case']==label]
            axis.plot([1,2,3],[q[field] for q in current],'-o',color=color,label=LABELS[label],lw=2.4)
        axis.set_xticks([1,2,3],['R1（历史）','R2','R3']);axis.grid(alpha=.17)
    def split(fig,ax):
        ax.remove();axes=fig.subplots(1,2);fig.subplots_adjust(left=.09,right=.96,bottom=.20,top=.73,wspace=.28)
        return axes
    fig,ax=figure('AgentX：全量结构分析与五类重复实测','两类证据独立呈现；模型服务端与原始业务工具未纳入资源测量','Full 与 256k 为同一会话集合的不同版本；实测案例为固定选样，不代表全量总体。')
    scope=[{'evidence':'Full 源记录','sessions':393,'unique_requests':98827,'executions':'未执行','meaning':'上下文、前缀、时序结构'},
        {'evidence':'256k 源记录','sessions':393,'unique_requests':68266,'executions':'未执行','meaning':'同会话筛选版本'},
        {'evidence':'远程 DeepSeek 回放','sessions':5,'unique_requests':117,'executions':351,'meaning':'客户端延迟、缓存与资源'}]
    table_style(ax,['证据范围','唯一会话','唯一请求','正式执行','可解释内容'],
        [[q['evidence'],str(q['sessions']),f"{q['unique_requests']:,}",str(q['executions']),q['meaning']] for q in scope],15,3.3)
    finish(fig,'01-scope','汇报口径：原数据与新实验分开','351 次是 117 个源请求各执行 3 次；不是新增 351 个独立样本。')
    table(out/'plot_data/evidence_scope.csv',scope)
    fig,ax=figure('原数据统计｜Full 与 256k 的请求构成','均为 393 个会话；分别统计原生主代理和显式子代理记录','引用既有全量分析；未重新执行原始任务。两个版本不能相加为独立总体。')
    source_rows=[];x=np.arange(2)
    for shift,key,label,color in [(-.18,'full','Full',BLUE),(.18,'capped_256k','256k',TEAL)]:
        values=[offline[key]['totals'][role+':requests'] for role in ['main','subagent']]
        ax.bar(x+shift,values,width=.34,label=label,color=color)
        for p,v in zip(x+shift,values):ax.text(p,v+1100,f'{v:,}',ha='center',fontsize=16)
        source_rows += [{'variant':label,'role':role,'requests':v} for role,v in zip(['main','subagent'],values)]
    ax.set_xticks(x,['主代理记录','显式子代理记录']);ax.set_ylabel('源请求数量');ax.set_ylim(0,65000);ax.legend()
    finish(fig,'02-source-composition','原数据：筛选改变请求构成','Full 98,827 条，256k 68,266 条；主代理与子代理的保留比例不同。')
    table(out/'plot_data/source_request_composition.csv',source_rows)
    fig,ax=figure('原数据统计｜历史前缀复用的结构潜力','Full，输入 token 加权；同会话、同保存模型、只使用已完成历史、无淘汰','这是 hash 前缀结构模型；不等于服务缓存命中率、GPU KV 占用或缓存加速比。')
    d=offline['derived_findings'];same=d['same_agent_history_prefix_potential_input_weighted_pct']
    cross=d['cross_agent_additional_potential_input_weighted_pct'];none=100-same-cross;left=0
    prefix_rows=[]
    for label,value,color in [('同路径潜力',same,BLUE),('跨路径额外潜力',cross,ORANGE),('无已完成历史匹配',none,'#CBD5E1')]:
        ax.barh([0],[value],left=left,height=.4,color=color,label=f'{label}  {value:.2f}%');left+=value
        prefix_rows.append({'component':label,'input_weighted_pct':value})
    ax.set_xlim(0,100);ax.set_ylim(-.8,.8);ax.set_yticks([0],['Full']);ax.set_xlabel('占重建输入 token 合计 / %');ax.legend(loc='lower center',bbox_to_anchor=(.5,.04),ncol=3,fontsize=13)
    ax.text(49,0,f'历史前缀总潜力 {same+cross:.2f}%',color='white',ha='center',va='center',fontsize=25,weight='bold')
    finish(fig,'03-source-prefix','原数据：前缀潜力与实测缓存分别解释','全量结构潜力约 98.27%；当前远程缓存比例使用另一组固定合成输入，不直接作因果对照。')
    table(out/'plot_data/source_prefix_potential.csv',prefix_rows)
    fig,ax=figure('远程实测｜五类案例均已各完成三次','本轮新增 134 条正式执行；累计 351 条正式执行 + 15 次探针',footer)
    values=[];case_ranges=[]
    for label in LABELS:
        r={q['metric']:q for q in ranges if q['case']==label};m=next(q for q in metrics if q['case']==label)
        w=r['wall_s'];p=r['first_content_p50_s'];rss=r['client_sampled_peak_rss_mib'];o=r['output_to_target_pct']
        values.append([LABELS[label],str(m['requests']),f"{w['min']:.2f}–{w['max']:.2f}",f"{p['min']:.3f}–{p['max']:.3f}",
            f"{rss['min']:.2f}–{rss['max']:.2f}",f"{o['min']:.2f}–{o['max']:.2f}"])
        case_ranges.append({'case':label,'requests_per_run':m['requests'],'wall_min_s':w['min'],'wall_max_s':w['max'],
            'first_content_p50_min_s':p['min'],'first_content_p50_max_s':p['max'],'rss_min_mib':rss['min'],'rss_max_mib':rss['max'],
            'output_coverage_min_pct':o['min'],'output_coverage_max_pct':o['max']})
    table_style(ax,['案例','每轮请求','耗时范围 s','首内容 P50 范围 s','RSS 范围 MiB','输出覆盖范围 %'],values,14,3)
    finish(fig,'04-five-ranges','远程实测：五类三次观察总览','表中范围为三次最小值—最大值，不是置信区间；不同案例的任务和负载不同。')
    table(out/'plot_data/case_ranges.csv',case_ranges)
    fig,ax=figure('远程实测｜会话耗时的逐次变化','首个正式请求开始至最后一个正式请求结束，不含探针；连线仅表示观察顺序',footer)
    series(ax,'wall_s');ax.set_ylabel('正式会话耗时 / 秒');ax.set_ylim(bottom=0);ax.legend(ncol=2,fontsize=13)
    finish(fig,'05-wall','远程实测：耗时与输出量一起解读','多子代理 R2 的耗时和实际输出量同时增大，不能只按会话耗时判断性能。')
    fig,ax=figure('远程实测｜首内容延迟 P50 / P95','每个分位数在本轮的 20–30 个请求内计算；不合并重复请求推断总体',footer)
    axes=split(fig,ax)
    for axis,field,title in zip(axes,['first_content_p50_s','first_content_p95_s'],['每轮 P50','每轮 P95']):
        series(axis,field);axis.set_title(title);axis.set_ylabel('首内容延迟 / 秒');axis.set_ylim(bottom=0)
    handles,names=axes[0].get_legend_handles_labels()
    fig.legend(handles,names,ncol=5,fontsize=12,loc='lower center',bbox_to_anchor=(.5,.10))
    finish(fig,'06-first-content','远程实测：首内容延迟的重复观察','首内容延迟与整段会话耗时是不同指标；后者还受到输出长度及依赖等待影响。')
    fig,ax=figure('远程实测｜客户端 RSS 与 CPU','仅 HTTP 工作进程；包括序列化与证据保存，排除采样父进程及其他会话',footer+'\n历史 R1 多子代理、长上下文接续其他案例；新轮次每次独立进程，资源前置条件不同。')
    axes=split(fig,ax)
    for axis,field,ylabel in zip(axes,['client_sampled_peak_rss_mib','mean_cpu_percent_one_core_from_sample_delta'],['采样峰值 RSS / MiB','采样窗口平均 CPU / 单核 %']):
        series(axis,field);axis.set_ylabel(ylabel);axis.set_ylim(0,max(q[field] for q in metrics)*1.3);axis.legend(ncol=2,fontsize=11,loc='lower left')
    finish(fig,'07-client-resources','远程实测：客户端资源，不含服务器','CPU 使用首末采样累计差；峰值 RSS 为采样峰值。只反映本客户端实现与证据保存开销。')
    fig,ax=figure('远程实测｜实际输出对原始长度的覆盖','原始输出长度仅作为 max_tokens 上限，允许模型自然 stop；输入为固定合成文本',footer+'\n输出覆盖是长度指标，不是任务成功率；原始长输出负载仍未完整复现。')
    series(ax,'output_to_target_pct');ax.axhline(100,color='#64748B',ls=':');ax.set_ylim(0,112)
    ax.set_ylabel('实际输出 / 原始输出长度合计 %');ax.legend(ncol=2,fontsize=12,loc='center right')
    finish(fig,'08-output','远程实测：输出上限不保证实际长度','单次达到上限不表示接口能保证最小生成长度；不追加提示或续写来填平差异。')
    fig,ax=figure('远程实测｜输入 token 加权缓存命中比例','使用 provider usage 返回的缓存计数；没有清缓存或更改正文来规避缓存',footer+'\n与第 3 页全量前缀潜力的样本和定义不同，不直接比较为缓存效率损失。')
    series(ax,'input_weighted_cache_hit_pct_reported');ax.set_ylim(0,110);ax.set_ylabel('输入缓存命中 token 比例 %');ax.legend(ncol=2,fontsize=12,loc='lower left')
    finish(fig,'09-cache','远程实测：记录缓存状态，不作单因素归因','输入、服务缓存及模型别名条件应同时披露；缓存命中变化不能独立解释全部延迟差异。')
    fig,ax=figure('远程实测｜请求在途峰值与原生分组不同','按半开请求区间计算；保留依赖图，未复现源记录的原始时间间隔',footer+'\n在途请求不是 GPU 并发数，也不是原生子代理数。')
    x=np.arange(5)
    for r,offset,color in [(1,-.24,BLUE),(2,0,TEAL),(3,.24,ORANGE)]:
        values=[next(q['peak_inflight'] for q in metrics if q['case']==label and q['replicate']==r) for label in LABELS]
        ax.bar(x+offset,values,width=.22,color=color,label=f'R{r}')
    ax.set_xticks(x,list(LABELS.values()));ax.set_ylabel('同时在途请求数 / 个');ax.set_ylim(0,8);ax.legend(ncol=3)
    finish(fig,'10-inflight','远程实测：依赖约束下的实际在途请求','全部 345 条依赖边通过核验；子代理的存在不保证实际 API 请求同时执行。')
    fig,ax=figure('远程实测｜同一请求的输出与耗时可大幅变化','多子代理固定索引 9：正文、模型设置和 59,903 token 上限保持一致',footer)
    axes=split(fig,ax);long=sorted([q for q in rows if q['case']=='multiple_subagents' and q['index']==9],key=lambda q:q['replicate'])
    for axis,field,ylabel in zip(axes,['remote_completion_tokens','duration_s'],['实际输出 / token','单请求耗时 / 秒']):
        vals=[q[field] for q in long];axis.bar([1,2,3],vals,color=[BLUE,TEAL,ORANGE],width=.55)
        axis.set_xticks([1,2,3],[f"R{q['replicate']}\n{q['finish_reason']}" for q in long]);axis.set_ylabel(ylabel);axis.set_ylim(0,max(vals)*1.3);axis.grid(axis='y',alpha=.17)
        for i,v in enumerate(vals,1):axis.text(i,v+max(vals)*.035,f'{v:,.0f}' if field=='remote_completion_tokens' else f'{v:.2f}',ha='center',fontsize=16)
    finish(fig,'11-natural-stop','远程实测：自然结束差异的具体证据','该请求三次分别生成 1,246、59,903、3,934 token。耗时变化不等于固定输出工作负载下的性能变化。')
    table(out/'plot_data/long_request_example.csv',long)
    fig,ax=figure('结论边界与已保存证据','全量分析、回放验证和远程实测分别回答不同问题','本轮 134 正式请求 + 6 探针全部完成，零自动重试；原始证据保留本地，派生结果与清单提交 Git。')
    table_style(ax,['证据','本次可支持的结论','解释边界'],[
        ['Full / 256k 全量结构','上下文、前缀潜力、源区间重叠','无原始业务工具日志'],
        ['5 会话 × 3 次远程执行','所测条件下延迟与客户端资源','固定案例，n=3，不推广总体'],
        ['117 源请求 / 351 次执行','正文、源指纹、SSE、依赖均可核验','合成输入；新输出不反馈后续'],
        ['实际输出 / 缓存逐次保存','可解释输出负载与缓存状态变化','远程负载与版本未控制'],
        ['原始工具与服务器资源','未执行原始业务工具、未测服务器','不推断任务成功率或 GPU 资源']
    ],14,3)
    finish(fig,'12-boundaries','结论：证据完整，范围明确','原始长输出负载仍未完整复现。汇报保留源结构、合成回放和当前客户端测量的证据边界。')
    write_pptx(out/'AgentX全量分析与五类重复实测_汇报版_12页.pptx',slides)
    dump(out/'slides.json',[{'heading':q['heading'],'image':str(q['image'].relative_to(out))} for q in slides])
    md=['# 汇报讲解：12 页','', '图表为嵌入图片；标题可编辑，配套 SVG / CSV 可用于改图。第 2–3 页只引用已有全量报告，第 4–11 页为所选五个会话的远程实测。','']
    for i,(title,note,name) in enumerate(notes,1):md += [f'## {i}. {title}','',note,'',f'[PNG](figures/{name}.png) · [SVG](figures/{name}.svg)','']
    (out/'presentation_notes.md').write_text('\n'.join(md).rstrip()+'\n')
    table(out/'plot_data/run_metrics.csv',metrics);table(out/'plot_data/run_ranges.csv',ranges)
