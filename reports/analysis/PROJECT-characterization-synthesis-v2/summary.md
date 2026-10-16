# 项目特征化综合报告 v2

更新日期：2026-10-11。范围：汇编八个既有分析包，不新增实验、不重跑源分析器。旧 synthesis-v1 与 HTML v1/v2/v3 保留。

## 1. 当前阶段与目标

研究 Agent 行为与 CPU/OS 资源特征；benchmark 为负载来源，不是能力排行榜。

公开行为侧多来源证据 + Coding/Office 小规模 scope 级资源描述；工具级特性、热点及受控并发尚未闭合。

已经形成两条互补证据线：公开 trace/模板描述行为广度，本地受控运行描述真实资源。**现在不能再说“Office 没有资源数据”或“资源侧完全空白”。** 但有限 scope 级测量也不等于工具 CPU 特性、函数热点或类别级规律均已回答。

## 2. 当前核心发现

### 1. 公开数据补充行为广度，不能替代本地资源观测

SWE-rebench 9,435 条 trajectory、SWE-bench 三格式 90 条子集、OSWorld 755 条 model×task 记录分别支持保存行为描述。OSWorld 的 21 valid / 734 partial 是分析覆盖状态，不是任务成败；静态 pyautogui 调用也不等于实际 GUI 执行次数。

依据：[来源报告](../SWE-REBENCH-behavior-v2/summary.md)、[来源报告](../SWEBENCH-subset-behavior-v1/summary.md)、[来源报告](../OSWORLD-task-behavior-v3/summary.md)。

### 2. 请求形态呈现多轮、大上下文与 subagent

AgentX 登记 393 traces / 68,266 模型请求，其中 39,822 为 subagent 内部请求；Applied 三类各 8,192 条 production-derived 模板。token、模板 latency 和 source-relative 区间不是 CPU、真实工具耗时或账单。

依据：[来源报告](../AGENTX-APPLIED-MACRO-v1/summary.md)。

### 3. Coding 同任务重复已有真实资源变异证据

修复后 Coding 九次运行有 226 次请求、348 次工具调用，5 次 Submitted、4 次 LimitsExceeded。Astropy-13398 三次均预算终止，但评估有 1 次 resolved=true、2 次 false；其 Agent CPU IQR 为 37.89 core-s。调用数不能单独解释 CPU 差异。

依据：[来源报告](../P1-12-CODING-REPEAT-01-characterization-v3/summary.md)。

### 4. Office 九次重复已形成成功路径的资源证据

Excel/PPT/PDF 三个固定 DocOps 任务各三次，全部 finish / reward=1；49 次逻辑请求、37 次重建 Agent 工具动作，bootstrap 另计。原批摘要的 34 次工具数保留为历史，派生分析以运行时解析语义复核为 37；不是 Office 类别总体成功率。

依据：[来源报告](../DOCOPS-OFFICE-REPEAT-01-characterization-v1/summary.md)。

### 5. 未解决路径同样可作为有限资源样本

Word-03/04 均 reward=0，但分别为 steps_exhausted 与 finish，测量与清理有效。首个 verifier 失败均为顶级标题样式一致性；后续检查未知。不同步数配置的两次运行不是受控重复，不能解释为预算因果。

依据：[来源报告](../DOCOPS-WORD-RESOURCE-03-04-review-v1/summary.md)。

### 6. 区间关联与容器曲线不等于单工具 CPU 归因

Coding 纯请求采样区间的容器 CPU 差分为 0 usec，只约束被观测容器及计数器精度，不证明宿主 Agent 阻塞或整个系统没有 CPU 工作。Office 的 blkio service-byte 差分也不是完整文件系统 I/O；两个类别尚无统一测量边界与受控条件，不能直接作性能排名。

依据：[来源报告](../CODING-RESOURCE-LINK-feasibility-v1/summary.md)、[来源报告](../DOCOPS-OFFICE-REPEAT-01-characterization-v1/summary.md)。


## 3. 本地资源数据：两套设计分别展示

所有表格均为每个固定 task 的 n=3；IQR 使用分位位置 (n−1)p 的线性插值。数值直接读取已登记分析 JSON，不重新估计。CPU 单位 core-s；MiB=1,048,576 bytes。

### Coding：修复后 CODING-REPEAT-01

Agent/verifier 是不同容器 scope；下表仅为 Agent，不加上 verifier。

| Task | n | attempt wall 中位数 / IQR (s) | Agent CPU 中位数 / IQR (core-s) | Agent 内核 peak 中位数 (MiB) | Agent 终止 |
| --- | ---: | ---: | ---: | ---: | --- |
| astropy__astropy-13236 | 3 | 128.12 / 8.20 | 25.10 / 10.44 | 113.30 | LimitsExceeded=1, Submitted=2 |
| astropy__astropy-13398 | 3 | 149.73 / 41.28 | 34.50 / 37.89 | 140.83 | LimitsExceeded=3 |
| django__django-16485 | 3 | 99.82 / 11.79 | 39.42 / 9.89 | 1341.02 | Submitted=3 |

Astropy-13398 的正确 attempt wall 中位数为 **149.73s**，Agent 内核峰值内存 IQR 为 **129.83 MiB**。不沿用旧快照误记的 162.69s / 136.1 MiB。162.69s 在源数据中是另一观测范围的最大值，不是 attempt wall 中位数。

### Office：DOCOPS-OFFICE-REPEAT-01

Agent 工具与 verifier 共用任务容器；下表 CPU 为已登记共享容器范围，不是 Agent 工具独占 CPU。

| 固定 Task | n | attempt wall 中位数 / IQR (s) | 容器 CPU 中位数 / IQR (core-s) | memory.current 采样峰值中位数 (MiB) | 内核 peak 中位数 (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Excel (atomic__excel_001_budget_bucket_totals_seed) | 3 | 34.47 / 8.980 | 6.006818 / 0.550214 | 72.64 | 72.64 |
| PPT (atomic__ppt_008_bullet_editing_seed) | 3 | 25.20 / 0.345 | 5.209944 / 0.217071 | 67.86 | 74.61 |
| PDF (atomic__pdf_004_audit_pages_reorder_seed) | 3 | 21.55 / 0.460 | 4.279262 / 0.151814 | 60.06 | 70.11 |

三项任务全部 finish / reward=1，49 次逻辑请求、37 次重建的 Agent 工具调用、9 次 finish、3 次 invalid/unknown。每 run 两项 bootstrap 另计。37 与原批摘要 34 的差异已经由源分析说明，不改写批摘要。宿主 RSS 是共享批进程观察，不是九个独立 Agent 的内存。

Word-03/04 另属单任务两种配置：reward=0 的有效测量描述未解决路径成本，不能称为成功完成成本，也不与本表混合估算同配置重复。

### 比较边界

- Coding Agent/verifier 为独立容器；Office 两阶段共用容器。CPU 数值不合并为类别排名。
- memory.current 采样峰值、内核 peak 与宿主 RSS 分列；Office 宿主 RSS 为共享批进程观察。
- 任务、预算、harness、API 路由/响应模型、环境与 CPU 限制未统一；模型别名不是冻结后端版本。
- 每 task n=3；报告原始点/median/IQR，不强调 P95/P99；重复不是独立 task。
- Word 两次不同配置不并入 Office 三任务重复；历史旧 Coding 结束协议缺陷批次不并入修复后基线。
- 本次未纳入已验收的 Assistant/Video 可比资源数据，不等于所有历史小样均不存在。

不能根据这两表直接宣布“Office 比 Coding 更省 CPU”。任务规模、预算、harness、工具栈、模型路由与资源限制均未统一，而且两类容器范围不同。

## 4. Evidence → Allowed Claim：原六个 RQ 的覆盖

| RQ | 当前覆盖 | 允许的结论 | 尚缺 |
| --- | --- | --- | --- |
| RQ1：Agent workload 与传统 LLM workload 有什么不同？ | 形态描述初步覆盖；受控传统 LLM 对照缺失 | 描述各来源中的多轮、上下文、工具交错与状态形态，分别注明原始 trace、模板和静态源码层。 | 没有统一传统 LLM 对照；来源、任务与 harness 差异不能解释为架构因果效应。 |
| RQ2：Agent 时间到底花在哪里？ | Coding 区间与 DocOps 阶段级部分覆盖 | 限定观测范围内的区间/阶段描述与同任务重复变异；mixed 保留，不按比例分摊。 | DocOps 缺可靠逐请求/逐工具起止时间；LLM、Agent、Tool、Environment、Sandbox 尚未全部闭合为时间分解；不推算思考或等待时间。 |
| RQ3：真正造成 CPU / Memory / IO 压力的是什么？ | Coding 与 Office 的 scope 级资源描述已覆盖一部分 | 固定任务配置的容器级资源分布及活动共现；未解决但测量有效的运行也可分析其路径开销。 | 未控制跨类别任务/模型/harness/资源限制混杂；blkio 不是完整文件系统 I/O；共享容器观察不证明单工具独占资源或压力原因。 |
| RQ4：不同 Tool 的 CPU workload 特征是什么？ | 工具结构与 scope 共现已有；工具级特性未闭合 | 描述接口与活动组成、筛选测量候选；不能仅由调用数判定 CPU 特性。 | 缺逐工具/进程级资源边界与线程、调度和基础 CPU 统计；不能认定 compute/memory/IO/latency-bound 或单/多线程。 |
| RQ5：主要热点和软件优化机会在哪里？ | 未闭合；没有有效真实 Agent 函数热点样本 | 指出需要进一步观测的区间，不声称已找到函数热点或优化收益。 | CPU-02 普通用户检查被拒；特权方案未安装、未批准且安全闭环未完成，路线暂停；不能据此断言特权 perf 必然不可用。 |
| RQ6：多个 Agent 并发时系统会发生什么？ | 受控并发实验缺失 | 描述保存的 subagent/request 形态；不把它当真实调度并发或本机争用测量。 | 缺受控 Agent 并发度对照、资源争用、尾延迟与 sandbox 可扩展性证据。 |

不把“任务解决率”“获得 reward=1”当作所有研究问题通过。结果、Agent 终止、基础设施状态、测量完整性保持独立。公开数据与本地数据不跨来源合并为总体样本量。

## 5. 已完成的旧建议与下一步

旧报告建议的 Coding 区间 CPU 关联、SWE-bench 原生格式子集和 Office 试点/重复均已推进，不再列为待启动任务。大量已下载 SWE-bench 对象并未全量分析；本报告只声明已分析的 90 条子集和独立 SWE-rebench 语料，不重新盘点整个下载目录。

优先建议：**TOOL-OBSERVABILITY-01 — 优先补齐既有 DocOps 的请求/工具时间边界（先做有限离线准备）**。

目标：针对 RQ2 的实际缺口，在现有 Agent 调用位置记录宿主 monotonic begin/end、调用身份、返回/异常状态；同时记录 bootstrap 与 verifier 边界。不再扩通用框架。

为什么先做它：当前 DocOps 报告已明确缺少可靠请求/工具起止时间，这是 RQ2 的实际观测缺口。再次增加相同粒度样本不会补齐这项信息。最小事件边界接线比立刻恢复特权 perf 路线更直接，但它仍不解决单工具独占 CPU 或函数热点。

边界：只准备必要的最小接线与离线验证，随后另行批准一个独立单次实测。时间边界首先闭合耗时与事件关联，不自动给出独占 CPU、函数热点或完整 I/O。

停止条件：最小方案与实际路径离线验证完成即停；不复用旧批准，不自动新建 attempt 或执行。

备选：若优先扩大类别覆盖，可转向既定 Assistant/Video benchmark 的单任务可行性盘点；它与测量粒度是两类不同缺口，不自动下载或运行。

本段是研究顺序建议，**未实施、未授权、未启动**。CPU-02 / Replay 继续暂停；G2 / G3-R 未通过，本报告不重新裁定 Gate。

## 6. 验证范围与历史保护

- 八个分析包登记的 30 个输出均已在本轮回读 bytes/SHA-256，匹配后才汇编。
- 本轮未重新核验每份报告全部原始输入；原始级身份与采样核验引用各来源报告，不扩大为本轮独立重验。
- 数值表与机器可读 [evidence_matrix.json](evidence_matrix.json) 共用已登记统计；[manifest.json](manifest.json) 登记本轮输入与两个输出，不自哈希。
- 旧 synthesis-v1、历史 HTML、raw、批准、attempt、catalog 与参考仓库不修改。状态/方法历史快照漂移与实验输出损坏不是同一概念。
- HTML 新版总览读取本矩阵与发现，不再另维护一套硬编码结论。未做浏览器实际渲染检查，不宣称页面视觉验收已完成。
