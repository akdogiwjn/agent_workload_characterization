# 项目总览：证据、缺口与下一步

事实源为 [project_state.json](../project_state.json)。本页提供解释与定位，不重复审批、不提供执行命令。研究目标见[当前范围](current_scope.md)，当前工作见[短任务入口](current_task.md#current-task)；旧方法与任务库只按需查阅。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-23 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 公开trace已完成限定操作/软件汇总v3：SWE-rebench 9,435轨迹、SWE-bench现登记20,023对象/41组（原v3为19,876，后补147）、OSWorld 755模型×任务记录/108任务（命令解析扩展至v4，原生/源码分层）、H-EPM 414轨迹；AgentX Full/256k及Applied提供宏观证据：AgentX两版同393会话，98,827/68,266请求，仍无业务工具明细或本地资源。未穷尽语义解析，不混合来源分母或把软件声明当实际启动。
- SWE-bench逐任务评价补全：轨迹登记仍20,023对象/41组，另下载20,098份评价/配套文件，40/41组有公开评价产物。原8,730个未列项补出8,476未解决、140已解决、9未生成、1超时，余74空报告/30缺报告；MAYA补出222项，Mindlink同名公开来源仍缺366项评价。5个结果冲突单列；KGCompass更正300个任务身份，跨组去重实际2,294任务。仍无资源证据。
- H-EPM/ToolSandbox复核v3完成：414轨迹、2,021次调用/返回，按保存请求静态核实全部原生工具身份，原24次未知及2次仅有活动分类的调用均补出确切名称。406条有用户侧结束请求，402条有返回，4条仅保存请求、8条无请求；Agent终止原因及资源等未记录。两组不同源码且均有local changes，只作描述比较。
- SWE-rebench复核v3完成：85分片、9,435轨迹/111任务/17 participant完整核验；598,148请求/616,980结果的差额按589,061唯一ID配对、27,059未调用报告、860提取错误及其1,875候选、7,201提交分支请求与11复杂提交末尾请求核清。Junie 555轨迹的31,449步骤摘要另列，不当作零工具行为；任务失败不等于分析未完成，仍无本地资源证据。
- 本地三个既有批次的27个显式run已完成字段与manifest盘点；历史区间覆盖v3按CPU、cgroup I/O及可用/proc I/O分列候选/有效/gap，网络字节和任务目录边界占用没有观测，未回填。
- 新口径三链各一次已完成：Office目录扫描cwd修正后0→6629B；Coding Agent/verifier目录分别增长4874269/4614250B；Assistant场景内存状态N/A。主项采集和归档通过，cache仍unsupported导致supplement aggregate partial；共享netns不是任务/API专属字节。
- 火山三链各n=1限定离线分析完成：3张独立四面板资源SVG、作图CSV和目录占用表已生成。请求Office8、Coding20、Assistant Agent/User6/1；原生工具、Submitted控制流与业务错误分别统计。Coding宿主末次process_exited保留gap；共享netns不代表API字节，不合并旧27次。报告：reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/summary.md。
- LOCAL-THREE-CLASS-COMPLETE-02已顺序执行12/12次，identity 8a17109cf441e3ae68e3f9820babe5685467657cbcafb56d765dd1158dc4942d；合并原有效样本后27个固定task×round槽位各n=3，累计35次启动含8个永久排除的旧Office错路由attempt。v3独立复核及资源图已生成；7/7固定镜像批后身份匹配，raw归档哈希回读通过。n=3不代表类别总体，HTTP次数/费用unknown。报告：reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
- AgentX深入分析第1步完成：Full/256k同393会话、98,827/68,266请求；上下文演化、已完成历史前缀潜力、容量简化模型、请求重叠、筛选影响及时间局部性已分析，生成10张4K PNG/SVG、作图CSV和10页PPT。20项测试与216次真实请求穷举核对通过；模拟潜力不当作缓存命中/硬件并发，本地回放尚未开始。
- 状态防丢失保护完成：独立worktree规则、自动快照、协作锁和读取时SHA256校验已接入，33项状态/AgentX测试通过。本次远程检查点继续排除视频修改；完整恢复状态保留本机，Git HEAD不能代替完整本地状态。
<!-- PROJECT_STATE:END -->

公开数据集最新进展、来源边界及保存核查见[收尾总表](../reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)。已核验64,062项文件哈希并通过79项测试；历史HTML与综合报告未统一重制。

## 证据应如何使用

| 已有证据 | 可以支持 | 不能支持 | 入口 |
| --- | --- | --- | --- |
| LOCAL-THREE-CLASS-REPEAT-01：原批+续批累计35次启动，27个预定task×round槽位现均有3点 | 原有效Excel1、Coding5、Assistant9加Complete-02的Coding4/Office8；新批12/12执行、清理/归档/适用测量验收通过，7个固定镜像批后只读身份匹配 | 旧Office错路由8次永久保留并排除预期路由任务结果；n=3仅是固定任务重复，不代表类别总体；共享netns不是任务/API专属，HTTP次数与费用unknown | [v3合并分析](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)、[历史v2](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/summary.md) |
| 公开Coding | SWE-rebench、SWE-bench操作/工具统计；SWE-bench另补147个Sonar对象和20,098份评价/配套文件，40/41组有公开评价产物，原8,730个未列项逐项核查 | 74个空报告、30个缺报告及两组剩余来源缺口均列证据；5个结果冲突不擅自判定。KGCompass身份更正，仍不等同完整语义/资源覆盖。 | [逐任务评价](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)、[软件v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| SWE-rebench复核 | 85分片/9,435轨迹完整核验；589,061对唯一ID结果，候选提取错误、未调用报告、提交请求分列；Junie 31,449步骤摘要另列 | 调用/返回数量差额已解释，不当作缺下载；步骤与请求不冒充实际执行次数，无资源采样证据。 | [复核v3](../reports/analysis/SWE-REBENCH-behavior-v3/findings.md) |
| 公开Computer/Office | OSWorld命令解析扩展至v4，全755条、201,050条command重算；原生动作、结果及usage保留v3证据 | 原生与源码分层；剩余控制流未知与保存标记分列；无实际GUI执行/应用/资源证明。 | [行为v4](../reports/analysis/OSWORLD-task-behavior-v4/findings.md)、[原生/任务v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| 公开Assistant | H-EPM两组414轨迹、2,021次调用/返回；v3静态核实全部原生身份，24未知及2活动分类调用补出确切工具名 | 用户侧406个结束请求中402个有返回，Agent终止原因仍未记录；不同源码版本仅描述比较，无资源证据。 | [H-EPM v3](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)、[历史v2](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v2/summary.md) |
| 宏观请求/模板 | AgentX Full/256k同393会话，98,827/68,266请求；Applied Compute工作负载模板 | Full与256k重叠，不能合并分母；不足以统计真实业务软件或本地资源。 | [Full对照](../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)、[既有宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| AgentX深入分析第1步 | 同393会话Full/256k全量分析；上下文、已完成历史前缀、时间局部性、容量模型及API区间重叠；10张4K图与10页PPT | 仅源记录与声明模型；不是缓存命中、硬件并发、业务工具或资源复现。 | [报告与PPT](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/findings.md) |
| RUN-01/RUN-02、G1 机制补证 | 登记 scope 的资源与生命周期可观测性 | 独占 Tool CPU、完整应用 I/O | [G1 裁定](history_index.md#docs-g1_consolidated_review-md) |
| P1-12 三任务各三次，6 true / 2 false / 1 未评估 | 缺陷版本、固定预算下的结果与资源描述；9/9 LimitsExceeded | 正常完成成本、修复后性能基线 | [分析](../reports/analysis/P1-12-review-v1/summary.md)、[结束缺陷](../reports/analysis/P1-12-finish-protocol-review-v1/summary.md) |
| CODING-REPEAT-01 九次封存重复 | Agent/verifier分离scope的资源、区间与重复描述 | 因果解释、Tool独占CPU、思考时间、账单或Coding类别代表性 | [特征化 v3](../reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md) |
| DOCOPS-OFFICE-REPEAT-01 历史三任务重复 | 九次finish/reward=1、49逻辑请求、37派生工具调用、旧共享容器观察 | 不与新采集口径批次自动合并 | [历史特征化](../reports/analysis/DOCOPS-OFFICE-REPEAT-01-characterization-v1/summary.md) |
| DOCOPS-OFFICE-REPEAT-02 当前三任务重复 | 46请求、37自主工具、18 bootstrap；真实调用/阶段时间、共享容器CPU/内存/有限blkio；三次PPT bootstrap错误保留 | Office总体、GUI/VM资源、单工具独占或完整I/O | [新口径特征化](../reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) |
| TOOLSANDBOX-ASSISTANT-REPEAT-01 三任务各三次 | 65请求、48 Agent工具/9 User结束；共享worker阶段与proc资源、任务内变异及错误恢复路径 | 类别总体、单工具独占、函数热点、graph效果、实际HTTP或账单 | [Assistant特征化](../reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md) |
| VideoWeaver旧宏观小样与部分解析 | 请求/工具形态和指标可用性；不是零trace | 未提供有效本地视频处理CPU/RSS/I/O批次；远端生成CPU不可归本机 | [macro-v6](../reports/macro/macro-pilot-v6/summary.md)、[小样验证](../reports/quality/videoweaver_sample_validation.json) |
| DOCOPS-WORD-RESOURCE-03/04 | 单任务两种配置下未解决路径的行为与有效资源观察 | 成功完成成本、同配置重复、预算因果 | [有限分析](../reports/analysis/DOCOPS-WORD-RESOURCE-03-04-review-v1/summary.md) |
| FINISH-01 | 提交识别有效；评估启动失败，历史清理未完整确认 | 完整链路成功或 resolved=false | [报告](../reports/resource/P1-12/revalidations/FINISH-01/) |
| FINISH-02 | 21 次请求后正常提交、正确性评估与清理归档的单次闭环 | 修复后多任务变异、与旧网关同模型对照 | [报告](../reports/resource/P1-12/revalidations/FINISH-02/SUMMARY.json) |
| CPU-01 / CPU-02 | 合成 perf 可测性 / 已发生权限失败 | 真实 Agent 容器函数热点，G2 通过 | [CPU-01](history_index.md#docs-cpu_01_delivery-md)、[CPU-02](history_index.md#docs-cpu_02_delivery-md) |
| P3-01 v3 | 28 条调用恢复、关联与现有信息缺口 | 安全执行、正确性或资源等价 Replay | [审计](../reports/replay/P3-01-audit-v3/summary.md) |

“任务解决”“正常结束”“评估完成”“采集完整”“清理确认”分别判定，不能用 returncode=0 相互替代。token usage 不是账单；费用未知继续标 unknown。

## 当前目标与采样能力（2026-10-16）

用户已将目标收窄到**单任务过程中的 CPU、内存、磁盘 I/O 与占用、网络通信、时长、工具/软件统计及图表**。热点、PMU、微架构分类、优化不再是必交；传统 LLM 对照、并发和 Replay 仅为可选扩展。当前目标以[current_scope.md](current_scope.md)为准；原综合报告保留其撰写时点，不再以旧热点缺口阻塞新范围，也不自动重裁 Gate。

| 指标/展示 | 当前已经实现 | 当前缺口 |
| --- | --- | --- |
| 连续采样 | Coding 的 `ResourceSampler`、DocOps `Sampler`、ToolSandbox worker 监测均已有生产接线；三类主要 run 目标间隔 0.5s，保留真实 monotonic 时间戳 | 容器/指定进程，不是整机统一监测；单次过程中的多次采样不等于重复执行很多次任务 |
| CPU | cgroup 累计 CPU、worker `/proc` ticks；差分可得到区间平均核心数。现有 HTML 可展示 Coding/DocOps CPU 曲线 | Assistant 最新九次尚未进入 HTML；不是每个工具独占 CPU，不要求热点 |
| 内存 | cgroup current/内核 peak、宿主/worker RSS；样本中有随时间变化的读数 | RSS/current/peak 不能相加；现有 HTML 已展示 Coding/DocOps，Assistant 待统一接入 |
| 磁盘 I/O | Coding/Office cgroup累计值、Assistant `/proc/io`字段；新代码投影CPU及I/O有效相邻区间速率 | 新测量报告含差分与gap；cgroup block-service、proc read/write_bytes及rchar/wchar语义不同，不等于完整文件系统流量；HTML速率面板仍未更新 |
| 磁盘占用（必统计） | 旧批无历史起止边界，见[历史覆盖表v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)；Complete-02真实测得Coding `/testbed`、Office `/root/submission` 的前后 apparent bytes/增长，Assistant任务状态为not_applicable | 宿主run输出目录单列；共享cache仍unsupported；边界扫描不是最终归档大小，历史缺失不回填 |
| 网络通信 | Complete-02 12次真实运行均保存共享netns逐接口累计tx/rx及区间速率；固定研究槽位曲线和完整机器可读记录见[v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md) | 不是PID、任务或API专属；不跨接口求和；HTTP正文/TLS/链路字节、实际HTTP次数与账单仍unknown |
| 时长与工具统计 | 27个固定task×round槽位各有3点；attempt wall、请求/工具、任务结果、终止与清理分列，原始点及median/IQR见[v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md) | 固定任务小样本，不是类别总体；请求区间不是思考时间，缺失阶段边界不补造 |
| 汇总图表 | [HTML v5](../reports/html/PROJECT-RESULTS-v5/index.html)有单 run CPU/内存图、调用时间线及部分三次重复原始点/median/IQR | 未形成 CPU/内存/I/O/网络四面板完整总览，未纳入最新 Assistant；按用户约定最后统一更新，本轮未生成 HTML |

采样源：[cgroup reader/sampler](../src/agent_workload_characterization/collectors/resource_sampler.py)、[进程 reader](../src/agent_workload_characterization/collectors/host_process.py)、[DocOps 生产采样](../scripts/docops_word_resource_01_entry.py)、[ToolSandbox 生产采样](../scripts/toolsandbox_resource_pilot_01_entry.py)、[图表生成器](../scripts/generate_project_results_html.py)。本轮静态读取实现并抽查既有产物字段，不运行 Docker、模型、采样器或重做历史测量。

补充记录也已纳入当前目标：模型请求/客户端耗时/输入输出cache token及有证据的重试；生命周期阶段；评分、终止、工具错误、超时与可观测OOM；进程线程、user/system CPU、切换与缺页等可得字段；环境/软件/资源限制；采样覆盖、缺读与实际可得开销。磁盘占用为必统计项，GPU暂不统计。详见[采样契约§11](trace_contract.md#11-当前目标的连续采样与图表要求2026-10-16)。Complete-02 已按新冻结身份完成 Coding4、Office8，并与既有15个有效观察形成27个固定任务槽位；旧8次Office错路由仍作为失败路径保留、不计入预期路由的任务样本。共享cache仍unsupported；HTTP次数及任务/API专属网络字节仍unknown。

### 历史字段与新采集接线

[历史覆盖报告v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)分析先前三个批次显式引用的27个run并回读raw manifest；这些旧run的网络和任务目录边界缺失不回填。后续 Complete-02 的12个新run完成后，按固定任务与配置比较并独立复核，生成[三类合并v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)。v2的Office路由错配及Coding no_candidate验收错误继续保留原历史语义；8个错路由attempt排除于预期路由的27个任务观察之外。

### AgentCgroup 方法实际采用到哪里

| 参考实现/方法 | 本项目实际采用 | 未采用或不能据此声称 |
| --- | --- | --- |
| [run_swebench.py ResourceMonitor](../references/repos/agentcgroup/scripts/run_swebench.py)：后台定时调用 `podman stats`，默认 1s，取 CPU/Mem | 本项目有同类连续采样方法，但监测代码是项目自有实现：cgroup v1/v2 与 `/proc`，三类主链目标 0.5s，额外保留读状态、counter 回退与边界 | 未直接调用该 ResourceMonitor；所核查函数仅取 CPU/Mem，不能据此认定 I/O/网络采集齐全 |
| [tool_timing.py](../references/repos/agentcgroup/analysis/tool_timing.py)：merge_intervals / union_duration_seconds | [Coding 特征分析](../scripts/p1_12_coding_repeat_characterization_v2.py)改造为整数 ns 的区间合并/并集，并采用部分工具分类方法；既有报告有 method_mapping | 未采用其重叠时间均摊；uncovered 不称 thinking/waiting |
| [plot_resources.py](../references/repos/agentcgroup/scripts/plot_resources.py)：资源曲线及工具标记 | 已有相同展示方向；本项目 HTML 从自身已核验样本生成 SVG，并非直接调用该脚本 | 不继承缺失补零，不能声称它已在本项目自动提供磁盘/网络折线 |
| [逐调用 cgroup 设计](../references/repos/agentcgroup/docs/PLAN_per_tool_call_cgroup.md) | 当前用任务容器/共享 worker 的 scope 和工具/阶段事件对齐 | 没有逐工具独立 cgroup，也未接入其调度、eBPF 或 Replay；本次收窄目标不要求补这条路线 |

### 当前需要补齐的项目

1. 本轮新口径正式样本及v3合并复核已完成；不自动延伸实验授权，也不将固定任务n=3解释为类别代表性。
2. 尚未实现的是任务/API专属网络字节与共享cache归属。若以后需要，应另行评估透明的客户端正文计量接口；正文bytes也不等于TLS/链路字节。
3. HTML四指标总览仍未更新；本轮只生成独立分析包，历史raw不改写。共享netns不替代API流量，CPU不作单工具独占归因。

[总体覆盖v3](../reports/analysis/PROJECT-characterization-synthesis-v3/summary.md)及[类别/RQ/指标表](../reports/analysis/PROJECT-characterization-synthesis-v3/evidence_matrix.json)保留2026-10-12旧目标时点；公开操作/软件统计v3已完成限定分析。下一步优先服务当前采样/展示缺口，不再把热点、PMU或并发缺失列作必补。本轮只更新目标和能力核查，不实现网络采集、不新增实验、不重冻结旧身份；CPU-02/Replay继续暂停。

## 历史资料

旧方法、逐轮任务与Gate原评审已迁入本机归档，见[历史索引](history_index.md)；本页原有历史展开段完整保存在local_archive/20261016-full-docs/before-edit/docs/project_status.md。当前只维护顶部事实与指标缺口，不追加逐轮日志。
