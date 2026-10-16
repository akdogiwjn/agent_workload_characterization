# 项目总览：证据、缺口与下一步

事实源为 [project_state.json](../project_state.json)。本页提供解释与定位，不重复审批、不提供执行命令。研究目标见[当前范围](current_scope.md)，当前工作见[短任务入口](current_task.md#current-task)；旧方法与任务库只按需查阅。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-16 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 公开操作和软件汇总v3已完成限定分析：SWE-rebench 9,435轨迹，SWE-bench 19,876对象/41组；OSWorld 755模型×任务/108任务，H-EPM 414轨迹，AgentX/Applied为宏观证据。部分语义和软件运行身份未知，来源不混算分母。
- 本地主设计：Coding、Office、Assistant各3任务×3重复，共27run/9任务设计。已有CPU/内存0.5s目标采样、有限I/O、阶段与调用统计；任务容器/共享进程不等于整机或工具独占测量。
- 待补：scope明确的网络收发、任务目录/输出/缓存占用、I/O速率图及完整四面板；最新Assistant与软件成果待最后统一更新HTML。旧run不倒填缺项，Video/GUI覆盖限制保留。
- 当前入口：docs/current_scope.md（目标）、docs/project_status.md（证据）、docs/current_task.md（工作）。77份历史文档已本机归档，5处旧报告链接已修复；HTML临时生成通过但来源版本标为PARTIAL。data保留配置/清单，原始大数据留本机；未授权实验或提交。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
<!-- PROJECT_STATE:END -->

## 证据应如何使用

| 已有证据 | 可以支持 | 不能支持 | 入口 |
| --- | --- | --- | --- |
| 公开操作与工具集：SWE-rebench全9,435条、SWE-bench登记19,876对象逐文件分流、OSWorld、H-EPM | 文件定位/检索/查看/修改/构建/测试等来源内比例、工具频次与出现轨迹数、声明应用与业务场景切片 | 部分/歧义记录、明确执行次数、耗时/资源或生产总体分布 | [操作总结](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)、[场景工具表](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/toolkits.md) |
| AgentX与Applied宏观请求/派生模板 | 来源内请求、多轮与subagent形态 | 具体工具集、真实Office API或CPU开销 | [宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
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
| 磁盘 I/O | DocOps 保存 cgroup blkio 读写累计值，Assistant 保存 `/proc/io` 的 read_bytes/write_bytes 与 rchar/wchar | 新图表还没有 I/O 速率面板；Coding 旧批按实际字段与缺读状态判断。块设备服务字节不是完整文件系统流量，rchar/wchar 不是磁盘实际字节 |
| 磁盘占用（必统计） | 历史镜像、归档文件大小等局部记录各保留原语义 | 尚无统一的逐任务工作目录/输出/缓存起止占用与增长汇总；整机空闲或镜像大小不能替代。占用与I/O分开，目录扫描不强制按0.5s执行 |
| 网络通信 | 有逻辑请求/工具事件、客户端请求窗口及 usage；它们能描述请求行为 | **没有统一的 rx/tx 字节连续采样与速率图**；请求次数、token、客户端耗时不能替代网络字节或 RTT。LLM API 在宿主发出时，禁网任务容器不能覆盖该通信 |
| 时长与工具统计 | 已有 attempt wall、阶段边界、调用计数、软件工具集、任务结果/终止/错误分列及任务内重复统计 | 客户端延迟不是纯推理或网络时间；可靠边界缺失的旧数据不补造 |
| 汇总图表 | [HTML v5](../reports/html/PROJECT-RESULTS-v5/index.html)有单 run CPU/内存图、调用时间线及部分三次重复原始点/median/IQR | 未形成 CPU/内存/I/O/网络四面板完整总览，未纳入最新 Assistant；按用户约定最后统一更新，本轮未生成 HTML |

采样源：[cgroup reader/sampler](../src/agent_workload_characterization/collectors/resource_sampler.py)、[进程 reader](../src/agent_workload_characterization/collectors/host_process.py)、[DocOps 生产采样](../scripts/docops_word_resource_01_entry.py)、[ToolSandbox 生产采样](../scripts/toolsandbox_resource_pilot_01_entry.py)、[图表生成器](../scripts/generate_project_results_html.py)。本轮静态读取实现并抽查既有产物字段，不运行 Docker、模型、采样器或重做历史测量。

补充记录也已纳入当前目标：模型请求/客户端耗时/输入输出cache token及有证据的重试；生命周期阶段；评分、终止、工具错误、超时与可观测OOM；进程线程、user/system CPU、切换与缺页等可得字段；环境/软件/资源限制；采样覆盖、缺读与实际可得开销。磁盘占用为必统计项，GPU暂不统计。详见[采样契约§11](trace_contract.md#11-当前目标的连续采样与图表要求2026-10-16)。这些多已有部分实现，但不能笼统标全部complete；真实HTTP次数、TTFT、OOM和完整进程树等未观测项仍保持unknown。本次只补文档要求，没有新增采集实现。

### AgentCgroup 方法实际采用到哪里

| 参考实现/方法 | 本项目实际采用 | 未采用或不能据此声称 |
| --- | --- | --- |
| [run_swebench.py ResourceMonitor](../references/repos/agentcgroup/scripts/run_swebench.py)：后台定时调用 `podman stats`，默认 1s，取 CPU/Mem | 本项目有同类连续采样方法，但监测代码是项目自有实现：cgroup v1/v2 与 `/proc`，三类主链目标 0.5s，额外保留读状态、counter 回退与边界 | 未直接调用该 ResourceMonitor；所核查函数仅取 CPU/Mem，不能据此认定 I/O/网络采集齐全 |
| [tool_timing.py](../references/repos/agentcgroup/analysis/tool_timing.py)：merge_intervals / union_duration_seconds | [Coding 特征分析](../scripts/p1_12_coding_repeat_characterization_v2.py)改造为整数 ns 的区间合并/并集，并采用部分工具分类方法；既有报告有 method_mapping | 未采用其重叠时间均摊；uncovered 不称 thinking/waiting |
| [plot_resources.py](../references/repos/agentcgroup/scripts/plot_resources.py)：资源曲线及工具标记 | 已有相同展示方向；本项目 HTML 从自身已核验样本生成 SVG，并非直接调用该脚本 | 不继承缺失补零，不能声称它已在本项目自动提供磁盘/网络折线 |
| [逐调用 cgroup 设计](../references/repos/agentcgroup/docs/PLAN_per_tool_call_cgroup.md) | 当前用任务容器/共享 worker 的 scope 和工具/阶段事件对齐 | 没有逐工具独立 cgroup，也未接入其调度、eBPF 或 Replay；本次收窄目标不要求补这条路线 |

### 当前需要补齐的项目

1. 明确任务 scope 与宿主 API 所在位置，补网络观测；整机网卡流量若使用，只能作带干扰说明的宿主背景，不冒充任务专属。
2. 复用已有有效 I/O 和 CPU/内存序列，补齐四面板时间对齐总览与 Assistant 数据接入；历史网络没有采集就显示 unavailable，不能靠公开 trace 或 token 倒填。
3. 保留类别范围与质量限制：Video 本地资源、GUI/VM 子域尚未实测；已有 27 run 是九个固定任务设计，不是总体代表性。是否扩类别另行决定，不借本次目标调整自动运行。

[总体覆盖v3](../reports/analysis/PROJECT-characterization-synthesis-v3/summary.md)及[类别/RQ/指标表](../reports/analysis/PROJECT-characterization-synthesis-v3/evidence_matrix.json)保留2026-10-12旧目标时点；公开操作/软件统计v3已完成限定分析。下一步优先服务当前采样/展示缺口，不再把热点、PMU或并发缺失列作必补。本轮只更新目标和能力核查，不实现网络采集、不新增实验、不重冻结旧身份；CPU-02/Replay继续暂停。

## 历史资料

旧方法、逐轮任务与Gate原评审已迁入本机归档，见[历史索引](history_index.md)；本页原有历史展开段完整保存在local_archive/20261016-full-docs/before-edit/docs/project_status.md。当前只维护顶部事实与指标缺口，不追加逐轮日志。
