# 项目总体证据覆盖与下一步 v3

更新：2026-10-12。只汇编已交付证据，不新增实验、不重跑源分析器。v1/v2保留各自时点，当前判断以本报告和状态真源为准。

## 当前阶段

公开行为侧已有多来源证据；本地资源侧已有 **Coding、Office、Assistant三个固定设计，各3任务×3重复**。当前主设计合计27个run、9个任务设计，不包含旧缺陷批次、PILOT或不同配置样本；这不是跨类别统一实验，也不代表类别总体。

重点已从“证明能测”推进到“扩类别覆盖并区分阶段/工具开销”。不需要为了满分补跑，也不因某阶段CPU高就认定函数热点。

## 四大类覆盖表

| 类别与既定benchmark | 已分析的公开/历史行为 | 当前本地资源主设计 | 尚缺 |
| --- | --- | --- | --- |
| Coding：SWE-bench / SWE-rebench | SWE-rebench 9,435 trajectory；SWE-bench三格式90条子集 | CODING-REPEAT-01：3×3，226请求、348工具；Agent/verifier分离容器 | 独立任务代表性、单工具归因、PMU/热点与受控条件 |
| Computer / Office：OSWorld / DocOps | OSWorld 755 model×task、108任务、7模型；Applied Office只是派生模板 | DocOps REPEAT-02：Excel/PPT/PDF 3×3，46请求、37自主工具、18 bootstrap；真实调用和阶段边界 | **GUI/VM子域未实测**；不能用文档任务替代GUI结论；三次PPT bootstrap失败保留 |
| Assistant / Tool：ToolSandbox | H-EPM第三方两组共414条；官方实测与其扩展配置不同 | ASSISTANT-REPEAT-01：3×3，65请求、48 Agent工具、9 User结束；共享worker阶段与proc资源 | 单工具独占资源、函数原因与类别代表性；真实HTTP次数/账单unknown |
| Video：VideoWeaver / AgenticVBench | 已有VideoWeaver宏观小样、adapter及macro-pilot-v6；验证记录full_ingest=false、parsed_records=2 | **无已验收本地视频处理资源批次**，不是CPU/RSS为0 | 完整任务/媒体/evaluator身份与本地剪辑/编码/渲染测量；远端生成CPU不可由本机取得 |

Computer/Office按方法论为同一大类；GUI是其中尚未测量的子域，不另外把项目改成五大类。Video也不能写成“完全没有trace”：现有旧小样是宏观/部分解析证据，不是完整视频任务资源特征化。

## 已有证据真正新增了什么

- **Office时间边界已闭合到限定范围。** REPEAT-02有请求/自主工具/bootstrap配对及真实阶段读数；“DocOps缺可靠调用边界、下一步先开发观测链”不再是当前待办。[来源](../DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md)
- **Assistant资源不再空白。** Task C波动主要落在evaluator：其共享CPU原始点1536.27/845.15/2765.90 process CPU-s，IQR960.375。与更多调用或错误共现，不证明因果、工具独占或具体函数热点。[来源](../TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md)
- **I/O不再全部null，但仍有限。** DocOps是cgroup blkio service-byte；Assistant是proc rchar/wchar/read_bytes/write_bytes。两者都不是完整文件系统或网络流量，不直接合并。[Office来源](../DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) · [Assistant来源](../TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md)
- **Coding容器等待窗口不能外推宿主。** 纯请求采样区间的容器CPU差为0仅约束该scope和计数器精度，不证明宿主阻塞或系统CPU为0。[来源](../CODING-RESOURCE-LINK-feasibility-v1/summary.md)

## 原六个RQ：Evidence → Allowed Claim

| RQ | 当前覆盖 | 可以说什么 | 仍不能说什么 |
| --- | --- | --- | --- |
| RQ1 Agent与传统LLM workload区别 | 形态描述部分覆盖 | 多轮、上下文、工具交错、状态与用户模拟器的来源内描述 | 没有受控传统LLM对照，不能把来源差异当架构因果 |
| RQ2 时间花在哪里 | Coding区间＋新Office/Assistant边界与阶段部分覆盖 | 明确窗口内并集/互斥分解、mixed、重复差异 | 客户端时间不是思考时间；uncovered不是等待；工具batch不是逐工具独占耗时 |
| RQ3 CPU/Memory/I/O压力来源 | 三类scope资源与活动共现部分覆盖 | 固定配置原始点/median/IQR、初始化/play/evaluator分列 | 跨类别任务、harness、模型、限制未统一，不能排名或证明压力原因 |
| RQ4 Tool CPU特性 | 接口、共享窗口和线程等前置证据 | 描述工具结构、提出可测候选 | 缺独占/进程树归因、cycles/instructions/IPC/cache/TLB/PMU；不能判定compute/memory/IO/latency-bound |
| RQ5 热点与优化机会 | 无有效真实Agent函数热点 | 定位值得进一步观测的阶段；静态代码仅列候选 | 不能由高CPU认定某库/函数为热点，也没有优化收益证据 |
| RQ6 多Agent并发 | 有宏观subagent形态，无受控争用实验 | 描述保存的请求结构 | 顺序重复、工具排列检查都不是Agent并发或sandbox扩展性实验 |

机器可读的类别、六RQ和指标覆盖见 [evidence_matrix.json](evidence_matrix.json)。不提供没有明确分母的“项目完成百分比”。

## 尚缺的类别与指标

1. **类别优先缺口：Video本地资源。** 四大类中唯一尚无已验收本地资源批次；现有生成型小样不能测远端CPU。Computer/Office内部的GUI/VM也是独立未测子域。
2. **粒度缺口：工具资源与基础CPU统计。** 当前是容器或共享进程，不是单工具独占；需要可靠边界及对应统计，更多相同scope样本不会自动补齐。
3. **解释力缺口：函数热点、PMU与架构敏感性。** 没有受控跨平台/硬件对照；CPU-02继续暂停，不自行恢复特权路线。
4. **对照与并发缺口：传统LLM基线、受控并发争用。** 请求结构、线程数、工具排列不是这些实验的替代。
5. **跨切面限制：环境与传输。** 已有实验身份/依赖/运行时快照，但全项目来源版本、许可证和环境重建并非全部闭合；模型别名不是不可变后端版本。正式批次实际HTTP与账单unknown，不因单次smoke有hook而补填。

## 唯一推荐下一任务：VIDEO-RESOURCE-PILOT-PREP-01

**仅建议，未开始、未授权。目标是既定Video benchmark的一个本地编辑任务可行性方案，不是马上执行三任务批次。**

先只读盘点已有VideoWeaver小样，以及AgenticVBench源码、任务、媒体和verifier的本地可用性/来源身份。当前 `references/repos` 清单未见AgenticVBench目录；方法文档的引用不等于源码或媒体已经在位。

优先考察AgenticVBench的本地剪辑/编码任务，因为它服务尚缺的视频工具资源证据。核对Agent/模型输入能力、arm64依赖、执行位置和可复用测量scope；只选择有正式定义及可追溯资产的一个候选。不自行发明替代benchmark，不把远端生成服务算成本机负载。

资产不足就提出最小获取需求；不自动联网、安装、API、Docker/VM、任务执行或创建批准/attempt。方案可审即停。后续执行另行批准；不修改官方规则追求reward=1。

不再把已完成的DocOps调用边界、Assistant公开分析或3×3试点列作未启动工作。工具粒度/GUI/并发仍是真实缺口，但本轮不启动；Replay保持暂停。

## 核验范围与历史保护

本轮回读11个既有分析/宏观包的41个输出并核对登记哈希，另读取并登记VideoWeaver sample validation。未重跑源分析器、evaluator或实验；未重新核验全部raw，原始级结论引用来源报告。各报告写作时的“当前代码匹配”不扩大为本轮对全部历史实现的重新认证。

v1/v2综合报告、来源报告、raw、批准、冻结身份及HTML v5原位保留。HTML v5仍是其生成时点的展示，未更新为本矩阵，也未补入最新Assistant结果，按用户安排留到最后统一处理。

G1保持登记限定范围；G2/G3-R未通过。CPU-02与Replay暂停。本报告不构成新执行批准，也不重新裁定Gate。

[manifest.json](manifest.json) 登记实际来源与本报告两项输出，不自哈希。
