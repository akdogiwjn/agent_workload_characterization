"""PPT-ready scientific charts and a self-contained 16:9 presentation."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
import json
import math
from pathlib import Path
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

from scripts.agentx_deep_analysis import BUDGETS, dump, table

BLUE, ORANGE, TEAL, INK, GREY = '#2563EB', '#EA580C', '#0D9488', '#152238', '#64748B'


def style():
    font = Path('/usr/share/fonts/google-droid-fonts/DroidSansFallback.ttf')
    if font.exists():
        fm.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': ['DejaVu Sans', 'Droid Sans Fallback'],
                         'font.size': 18, 'axes.titlesize': 25, 'axes.labelsize': 18,
                         'xtick.labelsize': 15, 'ytick.labelsize': 15, 'legend.fontsize': 15,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#CBD5E1', 'axes.labelcolor': INK,
                         'text.color': INK, 'xtick.color': INK, 'ytick.color': INK,
                         'figure.facecolor': 'white', 'axes.facecolor': 'white',
                         'svg.fonttype': 'none', 'axes.unicode_minus': False})


def figure(title, subtitle, footer):
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=.11, right=.96, bottom=.20, top=.78)
    fig.text(.065, .925, title, fontsize=28, weight='bold')
    fig.text(.065, .865, subtitle, fontsize=16, color=GREY)
    fig.text(.065, .065, footer, fontsize=12, color=GREY, va='bottom')
    ax.grid(axis='y', alpha=.17)
    ax.set_axisbelow(True)
    return fig, ax


def save(fig, out, name):
    fig.savefig(out/'figures'/f'{name}.png', dpi=240)
    fig.savefig(out/'figures'/f'{name}.svg')
    plt.close(fig)


def ecdf(values):
    x = np.sort(np.asarray(values))
    return x, np.arange(1, len(x)+1)/len(x)*100


def write_pptx(path, slides):
    """Minimal Office Open XML: embedded chart PNGs and editable text boxes.

    Charts are images in the deck; matching SVG/CSV files provide editable assets.
    No Python package installation, external links or macros are required.
    """
    ns = 'http://schemas.openxmlformats.org'
    a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    rel = ns+'/officeDocument/2006/relationships'
    header = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    w, h = 12192000, 6858000
    types = {'rels': 'application/vnd.openxmlformats-package.relationships+xml', 'xml': 'application/xml', 'png': 'image/png'}
    overrides = {'/ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
                 '/ppt/slideMasters/slideMaster1.xml': 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml',
                 '/ppt/slideLayouts/slideLayout1.xml': 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml',
                 '/ppt/theme/theme1.xml': 'application/vnd.openxmlformats-officedocument.theme+xml'}
    for i in range(1, len(slides)+1):
        overrides[f'/ppt/slides/slide{i}.xml'] = 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
    def rels(rows):
        return header+f'<Relationships xmlns="{ns}/package/2006/relationships">'+''.join(
            f'<Relationship Id="{i}" Type="{rel}/{t}" Target="{escape(target)}"/>' for i,t,target in rows)+'</Relationships>'
    group = '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    def textbox(ident, text, x, y, cx, cy, size, color='152238'):
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="{ident}" name="Text {ident}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
                f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
                '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r>'
                f'<a:rPr lang="zh-CN" sz="{size}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
                '<a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/></a:rPr>'
                f'<a:t>{escape(text)}</a:t></a:r><a:endParaRPr lang="zh-CN"/></a:p></p:txBody></p:sp>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', header+f'<Types xmlns="{ns}/package/2006/content-types">'+''.join(
            f'<Default Extension="{k}" ContentType="{v}"/>' for k,v in types.items())+''.join(
            f'<Override PartName="{k}" ContentType="{v}"/>' for k,v in overrides.items())+'</Types>')
        z.writestr('_rels/.rels', rels([('rId1','officeDocument','ppt/presentation.xml')]))
        z.writestr('ppt/presentation.xml', header+f'<p:presentation xmlns:p="{p}" xmlns:a="{a}" xmlns:r="{rel}">'
                   '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>'+''.join(
                       f'<p:sldId id="{255+i}" r:id="rId{i+1}"/>' for i in range(1,len(slides)+1))+
                   f'</p:sldIdLst><p:sldSz cx="{w}" cy="{h}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', rels([('rId1','slideMaster','slideMasters/slideMaster1.xml')]+[
            (f'rId{i+1}','slide',f'slides/slide{i}.xml') for i in range(1,len(slides)+1)]))
        z.writestr('ppt/slideMasters/slideMaster1.xml', header+f'<p:sldMaster xmlns:p="{p}" xmlns:a="{a}" xmlns:r="{rel}">'
                   f'<p:cSld><p:spTree>{group}</p:spTree></p:cSld>'
                   '<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>'
                   '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>')
        z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels', rels([
            ('rId1','slideLayout','../slideLayouts/slideLayout1.xml'),('rId2','theme','../theme/theme1.xml')]))
        z.writestr('ppt/slideLayouts/slideLayout1.xml', header+f'<p:sldLayout xmlns:p="{p}" xmlns:a="{a}" type="blank" preserve="1">'
                   f'<p:cSld name="Blank"><p:spTree>{group}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
        z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', rels([('rId1','slideMaster','../slideMasters/slideMaster1.xml')]))
        colors = {'dk1':'152238','lt1':'FFFFFF','dk2':'334155','lt2':'F8FAFC','accent1':'2563EB','accent2':'EA580C',
                  'accent3':'0D9488','accent4':'7C3AED','accent5':'64748B','accent6':'DB2777','hlink':'2563EB','folHlink':'7C3AED'}
        z.writestr('ppt/theme/theme1.xml', header+f'<a:theme xmlns:a="{a}" name="AgentX White"><a:themeElements><a:clrScheme name="AgentX">'+''.join(
            f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k,v in colors.items())+'</a:clrScheme>'
            '<a:fontScheme name="Aptos"><a:majorFont><a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
            '<a:fmtScheme name="AgentX"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst>'+''.join('<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>' for _ in range(3))+'</a:lnStyleLst>'
            '<a:effectStyleLst>'+''.join('<a:effectStyle><a:effectLst/></a:effectStyle>' for _ in range(3))+'</a:effectStyleLst>'
            '<a:bgFillStyleLst>'+''.join('<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' for _ in range(3))+'</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>')
        for i, slide in enumerate(slides, 1):
            pic = ('<p:pic><p:nvPicPr><p:cNvPr id="3" name="Chart"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                   '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                   '<p:spPr><a:xfrm><a:off x="609600" y="640080"/><a:ext cx="10972800" cy="6172200"/></a:xfrm>'
                   '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
            # Picture retains exact 16:9 aspect; title and page number are editable.
            content = textbox(2, slide['heading'], 609600, 91440, 10972800, 457200, 2300)
            content += pic + textbox(4, str(i), 11521440, 91440, 304800, 365760, 1200, '64748B')
            z.writestr(f'ppt/slides/slide{i}.xml', header+f'<p:sld xmlns:p="{p}" xmlns:a="{a}" xmlns:r="{rel}">'
                       f'<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree>{group}{content}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', rels([
                ('rId1','slideLayout','../slideLayouts/slideLayout1.xml'),('rId2','image',f'../media/image{i}.png')]))
            z.write(slide['image'], f'ppt/media/image{i}.png')


def render(out, summary, results):
    style()
    slides, plot_rows = [], []
    def finish(fig, name, heading, finding):
        save(fig, out, name)
        slides.append({'figure': name, 'heading': heading, 'finding': finding,
                       'image': out/'figures'/f'{name}.png'})
    full, cap = summary['full'], summary['capped_256k']
    ft, ct = full['totals'], cap['totals']
    sessions = results['full'][1]
    weighted = ft['all:history_tokens']/ft['all:input']*100
    same_weighted = ft['all:same_agent_history_tokens']/ft['all:input']*100
    extra = ft['all:cross_agent_extra_tokens']/ft['all:input']*100
    summary['derived_findings'] = {
        'full_history_prefix_potential_input_weighted_pct': weighted,
        'same_agent_history_prefix_potential_input_weighted_pct': same_weighted,
        'cross_agent_additional_potential_input_weighted_pct': extra,
        'sessions_affected_by_256k': sum(r['above_256k_requests'] > 0 for r in sessions),
        'cap_main_adjacencies_bridged': sum(r['cap_bridged_main_adjacent_pairs'] for r in sessions),
        'sessions_with_main_context_drop_candidates': sum(r['main_context_drop_candidates'] > 0 for r in sessions),
        'main_context_drop_candidates': sum(r['main_context_drop_candidates'] for r in sessions),
    }
    rank = sorted(sessions, key=lambda r:r['input_sum'], reverse=True)
    for pct in (1, 10):
        n = math.ceil(len(rank)*pct/100)
        summary['derived_findings'][f'top_{pct}pct_sessions_count'] = n
        summary['derived_findings'][f'top_{pct}pct_sessions_input_share_pct'] = sum(r['input_sum'] for r in rank[:n])/ft['all:input']*100

    # 1. Equal-session main-stream progress; no interpolation of absent observations.
    fig, ax = figure('主代理上下文随请求进度变化', '每个会话、每个5%进度箱先取中位数；再跨会话汇总，避免长会话支配曲线',
                     'AgentX v1.0 | 393个相同会话；两版各自按保留请求序号归一化，不是相同物理时间。阴影=P25–P75。\n输入长度由64-token hash块重建；曲线不表示业务阶段或实际KV显存。')
    for variant, label, color in [('full','Full',BLUE),('256k','256k',ORANGE)]:
        bins = defaultdict(list)
        for r in results[variant][2]:bins[r['bin']].append(r['session_bin_median'])
        rows=[]
        for b, values in sorted(bins.items()):
            q=np.percentile(values,[25,50,75]);r={'variant':variant,'progress_mid_pct':(b+.5)*5,'sessions':len(values),'p25':float(q[0]),'median':float(q[1]),'p75':float(q[2])};rows.append(r);plot_rows.append(r)
        x=[r['progress_mid_pct'] for r in rows]
        ax.plot(x,[r['median']/1000 for r in rows],color=color,lw=3,label=label)
        ax.fill_between(x,[r['p25']/1000 for r in rows],[r['p75']/1000 for r in rows],color=color,alpha=.14)
    ax.set(xlabel='主代理原生记录流内的请求进度（%）',ylabel='重建输入长度（千 token）',xlim=(0,100));ax.legend()
    table(out/'plot_data'/'01_context_progress.csv',plot_rows)
    finish(fig,'01_context_progress','上下文演化：会话等权的进度曲线','按保存请求序号统计；不是时间进度或真实业务阶段。')

    # 2. Request-level context ECDF, with own denominators and logarithmic x.
    fig, ax = figure('长上下文主要出现在哪一类请求？','Full与256k分别统计主代理/子代理请求，不混合两版分母',
                     '经验累计分布（ECDF）；横轴对数刻度。Full/256k是同393会话的重叠版本。\n这里的输入是重建长度，不是精确计费token或独立样本。')
    rows=[]
    for variant,color in [('full',BLUE),('256k',ORANGE)]:
        for group,ls,label in [('main','-','主代理'),('subagent','--','子代理')]:
            vals=results[variant][4][group+':input'];x,y=ecdf(vals)
            ax.step(x/1000,y,where='post',color=color,ls=ls,lw=2.4,label=f'{variant} {label} (n={len(vals):,})')
            for q in np.linspace(0,100,401):rows.append({'variant':variant,'scope':group,'percentile':float(q),'input_tokens':float(np.percentile(vals,q)),'requests':len(vals)})
    ax.set_xscale('log');ax.set(xlabel='重建输入长度（千 token，对数轴）',ylabel='累计请求比例（%）',ylim=(0,100));ax.legend(loc='upper left')
    table(out/'plot_data'/'02_input_ecdf.csv',rows)
    finish(fig,'02_input_ecdf','长上下文：区分主代理与子代理','四条线分别使用各自请求数；长上下文尾部不能由均值代表。')

    # 3. Potential overlap with completion-aware same-session/model history.
    fig,ax=figure('可复用前缀的潜力有多大？','仅匹配同一会话、同一保存模型中，在当前请求开始前已完成的输入前缀',
                  '“潜力”是假设历史前缀永不淘汰；不是实测缓存命中率、token节省率或加速比。\n不使用尚未完成请求，也不跨会话/模型共享hash；首个请求及无匹配请求按0计入分母。')
    rows=[]
    for variant,color in [('full',BLUE),('256k',ORANGE)]:
        vals=results[variant][4]['all:prefix_fraction'];x,y=ecdf(vals)
        ax.step(x*100,y,where='post',lw=3,color=color,label=f'{variant} (n={len(vals):,})')
        for q in np.linspace(0,100,401):rows.append({'variant':variant,'percentile':float(q),'prefix_fraction':float(np.percentile(vals,q)),'requests':len(vals)})
    ax.set(xlabel='当前输入中与已完成历史共享的最长前缀（%）',ylabel='累计请求比例（%）',xlim=(0,100),ylim=(0,100));ax.legend(loc='upper left')
    table(out/'plot_data'/'03_prefix_potential_ecdf.csv',rows)
    finish(fig,'03_prefix_potential','前缀复用：区分结构潜力与实际命中',f'Full输入加权历史前缀潜力为{weighted:.2f}%；实际缓存效果仍需回放测量。')

    # 4. Intentionally simple, precisely specified retention-policy model.
    fig,ax=figure('缓存预算敏感性：一个明确的简化模型','每个会话×模型仅保留“最近完成请求”的前B个输入token；每次完成即替换',
                  '预算是每个会话×模型的重建token容量，不是全机显存；不含输出KV、LRU、跨会话竞争和实际模型计算。\n采用源时间下已完成请求；纵轴是模型内共享前缀token / 全部重建输入token，不是实测命中率。')
    rows=[]
    for variant,group,color,ls,label in [('full','all',BLUE,'-','Full 全部'),('full','main',TEAL,'--','Full 主代理'),('full','subagent',ORANGE,'--','Full 子代理'),('256k','all',GREY,'-','256k 全部')]:
        totals=results[variant][0]['totals'];y=[]
        for b in BUDGETS:
            val=totals[f'{group}:budget_{b}_tokens']/totals[group+':input']*100;y.append(val)
            rows.append({'variant':variant,'scope':group,'budget_tokens_per_session_model':b,'retained_prefix_tokens':totals[f'{group}:budget_{b}_tokens'],'input_tokens_denominator':totals[group+':input'],'modeled_prefix_share_pct':val})
        ax.plot(np.asarray(BUDGETS)/1024,y,'o',ls=ls,color=color,lw=3,label=label)
    ax.set_xscale('log',base=2);ax.set_xticks(np.asarray(BUDGETS)/1024,[str(b//1024) for b in BUDGETS]);ax.set(xlabel='前缀保留预算（×1024 token / 会话×模型）',ylabel='简化模型中的前缀复用比例（%）',ylim=(0,100));ax.legend(loc='lower right')
    table(out/'plot_data'/'04_prefix_budget_model.csv',rows)
    finish(fig,'04_prefix_budget_model','容量敏感性：只报告明确假设下的模型结果','预算曲线用于提出实验假设，不代表GPU缓存命中率或硬件性能。')

    # 5. Source-request overlap, equal session ECDF.
    fig,ax=figure('一个会话内，保存的API请求会重叠多少？','对每个会话独立扫描[t, t+api_time)区间；统计峰值，再跨393会话画累计分布',
                  '主/子代理时间采用已发布语料的根会话相对坐标；不叠加父起点，不混合不同会话的时钟。\n请求区间重叠不是CPU/GPU并发、实际线程数或子代理数量，也不证明父代理在等待。')
    rows=[]
    for variant,color in [('full',BLUE),('256k',ORANGE)]:
        x,y=ecdf([r['peak'] for r in results[variant][1]]);ax.step(x,y,where='post',color=color,lw=3,label=f'{variant} (393会话)')
        for i,j in zip(x,y):rows.append({'variant':variant,'peak_recorded_request_overlap':int(i),'session_ecdf_pct':float(j)})
    ax.set(xlabel='会话内API源区间的峰值重叠数',ylabel='累计会话比例（%）',ylim=(0,100));ax.legend(loc='lower right')
    table(out/'plot_data'/'05_request_overlap_ecdf.csv',rows)
    finish(fig,'05_request_overlap','子代理与时序：请求重叠不等于计算资源并发',f'Full有{full["sessions_with_request_overlap"]}/393会话出现API区间重叠。')

    # 6. Cap changes request and reconstructed-input weights very differently.
    fig,ax=figure('256k筛选保留了多少请求与输入量？','以Full为分母，保留条件为重建输入+输出≤256,000；两版不是独立实验组',
                  '“输入量”是逐请求重建输入之和，重复前缀会重复累计；不是唯一语料量、计费量或实测计算工作量。\n筛选会改变保留请求的相邻关系；这里不将版本差异解释为性能收益。')
    labels=['全部请求','主代理请求','子代理请求'];x=np.arange(3);rows=[]
    for field,label,color,offset in [('requests','请求数保留率',BLUE,-.18),('input','重建输入累计量保留率',ORANGE,.18)]:
        y=[]
        for scope in ('all','main','subagent'):
            rate=ct[f'{scope}:{field}']/ft[f'{scope}:{field}']*100;y.append(rate)
            rows.append({'scope':scope,'measure':field,'full':ft[f'{scope}:{field}'],'capped':ct[f'{scope}:{field}'],'retained_pct':rate})
        bars=ax.bar(x+offset,y,width=.34,color=color,label=label)
        ax.bar_label(bars,labels=[f'{v:.1f}%' for v in y],padding=7,fontsize=19)
    ax.set_xticks(x,labels);ax.set(ylabel='相对于Full的保留比例（%）',ylim=(0,118));ax.legend(loc='upper left',ncols=2)
    table(out/'plot_data'/'06_cap_retention.csv',rows)
    finish(fig,'06_cap_retention','256k影响：请求数与重建输入量的保留比例不同',f'筛选影响{summary["derived_findings"]["sessions_affected_by_256k"]}/393会话；不改变两版会话集合。')

    # 7. Cumulative concentration by session; no population extrapolation.
    fig,ax=figure('少数会话是否贡献了大部分输入量？','将393个会话按逐请求重建输入累计量降序排列',
                  '这是当前筛选语料的会话集中度，不代表全部生产用户或业务类别。\n重复前缀重复计入；累计输入长度不等于真实推理工作量或API账单。')
    xx=np.arange(1,len(rank)+1)/len(rank)*100;yy=np.cumsum([r['input_sum'] for r in rank])/ft['all:input']*100
    ax.plot(xx,yy,color=BLUE,lw=3);ax.plot([0,100],[0,100],color=GREY,ls='--',lw=1.8,label='均匀贡献参考线');ax.legend(loc='lower right')
    top=summary['derived_findings']['top_10pct_sessions_input_share_pct'];n=summary['derived_findings']['top_10pct_sessions_count']
    ax.scatter([n/393*100],[top],s=90,color=ORANGE,zorder=3);ax.annotate(f'前{n}个会话：{top:.1f}%',(n/393*100,top),xytext=(22,top-8),fontsize=19)
    ax.set(xlabel='按输入量降序的累计会话比例（%）',ylabel='累计重建输入量比例（%）',xlim=(0,100),ylim=(0,100))
    table(out/'plot_data'/'07_session_concentration.csv',[{'rank':i+1,'trace_id':r['trace_id'],'session_share_pct':float(xx[i]),'input_share_cumulative_pct':float(yy[i]),'input_sum':r['input_sum']} for i,r in enumerate(rank)])
    finish(fig,'07_session_concentration','负载集中度：解释为何均值不足以描述AgentX',f'输入量最高的{n}个会话贡献{top:.1f}%的重建输入累计量。')

    # 8. Case chosen by explicit native main-stream context-drop count.
    case=results['full'][5]['most_context_drops'];events=case['requests'];main=sorted([e for e in events if e['kind']=='main'],key=lambda e:e['order'])
    fig,ax=figure('案例：主代理记录流中的上下文增长与回退',f'选择规则：相邻输入回退≥32,768 token次数最多；会话 {case["trace_id"][:12]}…',
                  '蓝线连接保存的主代理请求序号，橙点表示会被256k规则移除的请求。\n输入回退只是记录流候选现象；可能涉及多路请求/模型切换，不能据此认定执行了上下文压缩。')
    ax.plot([e['order'] for e in main],[e['input']/1000 for e in main],lw=1.7,color=BLUE)
    dropped=[e for e in main if not e['keep_256k']];ax.scatter([e['order'] for e in dropped],[e['input']/1000 for e in dropped],s=14,color=ORANGE,label='256k筛选移除',zorder=3)
    ax.set(xlabel='主代理原生记录流内请求序号（从0开始）',ylabel='重建输入长度（千 token）');ax.legend()
    table(out/'plot_data'/'08_case_context.csv',[{'trace_id':case['trace_id'],'source_line':e['source_line'],'pointer':e['pointer'],'order':e['order'],'source_t':e['t'],'model':e['model'],'input':e['input'],'keep_256k':e['keep_256k'],'adjacent_input_delta':e.get('adjacent_input_delta')} for e in main])
    finish(fig,'08_case_context','案例：长上下文不是单调增长的一条线',f'按公开规则选择的案例，记录流中有{case["score"]}次≥32,768 token的相邻回退。')

    # 9. Peak-source-overlap case, exact step trace in a predefined 10-minute window.
    case=results['full'][5]['peak_request_overlap'];center=case['summary']['peak_t'];left=max(0,center-300);right=left+600
    points=case['points'];before=[p for p in points if p['t']<=left];chosen=([dict(before[-1],t=left)] if before else [{'t':left,'main':0,'subagent':0,'all':0}])+[p for p in points if left<p['t']<right]
    chosen.append(dict(chosen[-1],t=right))
    fig,ax=figure('案例：峰值附近10分钟的API请求重叠',f'选择规则：Full会话内API源区间峰值最大；会话 {case["trace_id"][:12]}…',
                  f'窗口为根会话源坐标[{left:.3f}, {right:.3f})秒；这是局部窗口，不是完整会话时长。\n阶梯线直接来自保存的[t,t+api_time)区间；不是本地CPU/GPU资源曲线。')
    for group,label,color in [('all','全部请求',BLUE),('main','主代理请求',TEAL),('subagent','子代理请求',ORANGE)]:
        ax.step([(p['t']-left)/60 for p in chosen],[p[group] for p in chosen],where='post',color=color,lw=2.7,label=label)
    ax.set(xlabel='局部窗口内时间（分钟）',ylabel='同时处于API源区间的请求数',xlim=(0,10));ax.legend(loc='upper right')
    table(out/'plot_data'/'09_case_overlap.csv',[{'trace_id':case['trace_id'],'window_start_s':left,'window_end_s':right,'source_t':p['t'],'relative_s':p['t']-left,**{k:p[k] for k in ['all','main','subagent']}} for p in chosen])
    finish(fig,'09_case_overlap','案例：主代理与子代理的源请求重叠',f'该案例源API区间的会话峰值重叠为{case["score"]}；不解释为硬件并发。')

    summary['presentation']={'chart_count':len(slides),'png_pixels':[3840,2160],'aspect_ratio':'16:9',
                              'formats':['PNG','SVG','CSV','PPTX'], 'pptx_chart_editability':'charts embedded as PNG; titles editable; companion SVG and CSV supplied',
                              'case_selection':'maximum context-drop candidates and maximum recorded API request overlap; descriptive extremes, not representative population samples'}
    dump(out/'summary.json',summary)
    write_pptx(out/'AgentX深入分析_汇报版.pptx',slides)
    notes=['# AgentX深入分析：PPT逐页讲解','','图表为16:9白底，PNG 3840×2160、SVG保留文本，作图CSV位于plot_data/。PPT标题可编辑，图表为嵌入PNG；进一步编辑使用SVG/CSV。','']
    for i,s in enumerate(slides,1):
        notes += [f'## {i}. {s["heading"]}','',s['finding'],'',f'图：[PNG](figures/{s["figure"]}.png) · [SVG](figures/{s["figure"]}.svg)','']
    (out/'slide_notes.md').write_text('\n'.join(notes)+'\n')
    d=summary['derived_findings'];main_ret=ct['main:requests']/ft['main:requests']*100;child_ret=ct['subagent:requests']/ft['subagent:requests']*100
    md=['# AgentX 全量深入分析 v1','',
        '本轮完成第一步：固定版本Full/256k全量离线分析与PPT图表制作。未启动mock、真实模型、Agent或业务工具。',
        '',f'Full为393会话、{ft["all:requests"]:,}请求；256k为同393会话、{ct["all:requests"]:,}请求，两个版本不作为独立总体。',
        '', '## 可用于汇报的主要发现','',
        f'1. **256k筛选改变负载构成。** 主代理保留{main_ret:.2f}%请求，子代理保留{child_ret:.2f}%请求；全部重建输入累计量仅保留{ct["all:input"]/ft["all:input"]*100:.2f}%。影响{d["sessions_affected_by_256k"]}/393会话，并在主代理流中形成{d["cap_main_adjacencies_bridged"]:,}对跨被移除记录的新相邻关系。这不是性能提升或缓存命中差异。',
        f'2. **前缀结构存在较高复用潜力。** 同会话、同模型、已完成历史、无淘汰假设下，Full重建输入加权最长前缀潜力为{weighted:.2f}%；限同一原生agent路径为{same_weighted:.2f}%，跨路径增加{extra:.2f}个百分点。这里不是实测缓存命中率；具体保留策略的容量敏感性另见图4。',
        f'3. **请求流有重叠，不能按单串行链理解。** Full中{full["sessions_with_request_overlap"]}/393会话出现保存API区间重叠，峰值分布median={full["peak_request_overlap"]["median"]}、p95={full["peak_request_overlap"]["p95"]}、max={full["peak_request_overlap"]["max"]}。这不是CPU/GPU并发或实际子代理数。',
        f'4. **少数会话贡献较多累计输入。** 重建输入量最大的{n}个会话（向上取整约10%）贡献{top:.2f}%。统计针对当前筛选语料，不外推为全部生产用户分布。',
        f'5. **上下文演化不宜只报均值。** {d["sessions_with_main_context_drop_candidates"]}/393主代理记录流出现≥32,768 token相邻回退，共{d["main_context_drop_candidates"]:,}次；只能称为回退候选，不能自动解释成真实上下文压缩。图1按会话等权报告进度分布，图8提供有明确选择规则的极值案例。',
        '', '## 汇报材料','',
        '- [9页PPT](AgentX深入分析_汇报版.pptx)：16:9，中文标题、完整图注；图表嵌入高清PNG，标题可编辑。',
        '- [逐页讲解](slide_notes.md) · [全部高清PNG及SVG](figures/) · [作图CSV](plot_data/)。',
        '- [逐会话指标](per_session.csv) · [分组时钟审查](group_clock_audit.csv) · [案例选择](case_selection.json) · [机器摘要](summary.json)。',
        '- `full_request_metrics.jsonl` / `256k_request_metrics.jsonl`保存每请求源行、JSON pointer、前缀匹配证据及时间，作为本地审计明细。',
        '', '## 方法与限制','',
        '输入固定为既有AGENTX-FULL-MACRO-v1 manifest绑定的Full/256k文件，分析前重核SHA256及字节数，并逐项对账原393会话、请求数、分组数和输入/输出累计量。原始文件和旧报告不改写。',
        '',
        '**前缀匹配**使用完整有序hash向量的压缩radix tree，严格区分会话和保存模型；仅在请求结束时间≤当前请求开始时插入历史，不能使用当前请求、未来请求或仍在途的请求。分别计算同agent路径与整个会话同模型历史的最长公共前缀，保存匹配见证。无限历史结果是一个结构潜力基准，不假设实际物理缓存无限。',
        '',
        '**容量模型**每个会话×模型独立保留最近完成请求的输入前缀，预算B=32/64/128/256/512/1024×1024 token；每次完成后替换为该请求的前B个token。它不是LRU，不模拟跨会话争用、输出KV、实际字节占用或调度后的时序变化。所有预算结果包括冷启动请求，按全部重建输入加权；不标作实测命中。',
        '',
        '**上下文进度**按原生主代理请求序号划分20箱，每个会话每箱先取中位数，再跨会话取中位数/P25/P75。缺失箱不插值，逐箱有效会话数随CSV保存；Full与256k各自归一化，不能当作相同时刻的因果对照。主代理原生流可能包含多路调用与模型切换。',
        '',
        '**时序**将公开语料子请求t视为根会话相对坐标，不加父起点；在同一会话内扫描半开API区间，只计算保存区间重叠，不重建未记录的工具阶段或业务因果依赖。组duration与子请求是否一致另列审查；不同会话的时钟不拼接。',
        '',f'Full分组时钟审查：{json.dumps(full["group_clock_audit"],ensure_ascii=False)}；256k：{json.dumps(cap["group_clock_audit"],ensure_ascii=False)}。这些源字段差异保留，不移动时间或填造边界。',
        '',
        '公开数据没有原始提示词/代码/工具参数与结果、任务正确性及本地资源测量。所有曲线均为源记录分析或明确假设的前缀模型，不能解释为真实工具CPU、API账单、缓存加速比、模型能力或原业务复现。下一步本地mock回放尚未执行。',
        '',
        '复算命令：`PYTHONPATH=. python3 -B -m scripts.agentx_deep_analysis --output-dir <新的输出目录>`；渲染使用matplotlib/numpy，PPTX通过标准Office Open XML打包，不需安装Office。输出目录存在则拒绝覆盖。',
        '', '来源：[既有Full分析](../AGENTX-FULL-MACRO-v1/summary.md) · [官方方法说明](https://inferencex.semianalysis.com/agentx/methodology)。']
    (out/'summary.md').write_text('\n'.join(md)+'\n')
