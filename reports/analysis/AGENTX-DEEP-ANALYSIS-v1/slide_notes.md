# AgentX深入分析：PPT逐页讲解

图表为16:9白底，PNG 3840×2160、SVG保留文本，作图CSV位于plot_data/。PPT标题可编辑，图表为嵌入PNG；进一步编辑使用SVG/CSV。

## 1. 上下文演化：会话等权的进度曲线

按保存请求序号统计；不是时间进度或真实业务阶段。

图：[PNG](figures/01_context_progress.png) · [SVG](figures/01_context_progress.svg)

## 2. 长上下文：区分主代理与子代理

四条线分别使用各自请求数；长上下文尾部不能由均值代表。

图：[PNG](figures/02_input_ecdf.png) · [SVG](figures/02_input_ecdf.svg)

## 3. 前缀复用：区分结构潜力与实际命中

Full输入加权历史前缀潜力为98.27%；实际缓存效果仍需回放测量。

图：[PNG](figures/03_prefix_potential.png) · [SVG](figures/03_prefix_potential.svg)

## 4. 容量敏感性：只报告明确假设下的模型结果

预算曲线用于提出实验假设，不代表GPU缓存命中率或硬件性能。

图：[PNG](figures/04_prefix_budget_model.png) · [SVG](figures/04_prefix_budget_model.svg)

## 5. 子代理与时序：请求重叠不等于计算资源并发

Full有373/393会话出现API区间重叠。

图：[PNG](figures/05_request_overlap.png) · [SVG](figures/05_request_overlap.svg)

## 6. 256k影响：请求数与重建输入量的保留比例不同

筛选影响176/393会话；不改变两版会话集合。

图：[PNG](figures/06_cap_retention.png) · [SVG](figures/06_cap_retention.svg)

## 7. 负载集中度：解释为何均值不足以描述AgentX

输入量最高的40个会话贡献63.5%的重建输入累计量。

图：[PNG](figures/07_session_concentration.png) · [SVG](figures/07_session_concentration.svg)

## 8. 案例：长上下文不是单调增长的一条线

按公开规则选择的案例，记录流中有34次≥32,768 token的相邻回退。

图：[PNG](figures/08_case_context.png) · [SVG](figures/08_case_context.svg)

## 9. 案例：主代理与子代理的源请求重叠

该案例源API区间的会话峰值重叠为23；不解释为硬件并发。

图：[PNG](figures/09_case_overlap.png) · [SVG](figures/09_case_overlap.svg)

