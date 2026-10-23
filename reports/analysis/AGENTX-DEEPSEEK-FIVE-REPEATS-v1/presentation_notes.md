# 汇报讲解：12 页

图表为嵌入图片；标题可编辑，配套 SVG / CSV 可用于改图。第 2–3 页只引用已有全量报告，第 4–11 页为所选五个会话的远程实测。

## 1. 汇报口径：原数据与新实验分开

351 次是 117 个源请求各执行 3 次；不是新增 351 个独立样本。

[PNG](figures/01-scope.png) · [SVG](figures/01-scope.svg)

## 2. 原数据：筛选改变请求构成

Full 98,827 条，256k 68,266 条；主代理与子代理的保留比例不同。

[PNG](figures/02-source-composition.png) · [SVG](figures/02-source-composition.svg)

## 3. 原数据：前缀潜力与实测缓存分别解释

全量结构潜力约 98.27%；当前远程缓存比例使用另一组固定合成输入，不直接作因果对照。

[PNG](figures/03-source-prefix.png) · [SVG](figures/03-source-prefix.svg)

## 4. 远程实测：五类三次观察总览

表中范围为三次最小值—最大值，不是置信区间；不同案例的任务和负载不同。

[PNG](figures/04-five-ranges.png) · [SVG](figures/04-five-ranges.svg)

## 5. 远程实测：耗时与输出量一起解读

多子代理 R2 的耗时和实际输出量同时增大，不能只按会话耗时判断性能。

[PNG](figures/05-wall.png) · [SVG](figures/05-wall.svg)

## 6. 远程实测：首内容延迟的重复观察

首内容延迟与整段会话耗时是不同指标；后者还受到输出长度及依赖等待影响。

[PNG](figures/06-first-content.png) · [SVG](figures/06-first-content.svg)

## 7. 远程实测：客户端资源，不含服务器

CPU 使用首末采样累计差；峰值 RSS 为采样峰值。只反映本客户端实现与证据保存开销。

[PNG](figures/07-client-resources.png) · [SVG](figures/07-client-resources.svg)

## 8. 远程实测：输出上限不保证实际长度

单次达到上限不表示接口能保证最小生成长度；不追加提示或续写来填平差异。

[PNG](figures/08-output.png) · [SVG](figures/08-output.svg)

## 9. 远程实测：记录缓存状态，不作单因素归因

输入、服务缓存及模型别名条件应同时披露；缓存命中变化不能独立解释全部延迟差异。

[PNG](figures/09-cache.png) · [SVG](figures/09-cache.svg)

## 10. 远程实测：依赖约束下的实际在途请求

全部 345 条依赖边通过核验；子代理的存在不保证实际 API 请求同时执行。

[PNG](figures/10-inflight.png) · [SVG](figures/10-inflight.svg)

## 11. 远程实测：自然结束差异的具体证据

该请求三次分别生成 1,246、59,903、3,934 token。耗时变化不等于固定输出工作负载下的性能变化。

[PNG](figures/11-natural-stop.png) · [SVG](figures/11-natural-stop.svg)

## 12. 结论：证据完整，范围明确

原始长输出负载仍未完整复现。汇报保留源结构、合成回放和当前客户端测量的证据边界。

[PNG](figures/12-boundaries.png) · [SVG](figures/12-boundaries.svg)
