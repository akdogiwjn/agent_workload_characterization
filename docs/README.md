# 文档索引

日常只读当前文档，不再默认打开旧任务书。事实源为[project_state.json](../project_state.json)。

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
<!-- PROJECT_STATE:END -->

## 当前入口

| 内容 | 入口 |
| --- | --- |
| 项目目标、必采指标和排除项 | [current_scope](current_scope.md) |
| 已有证据、实现能力和缺口 | [project_status](project_status.md) |
| 当前工作、下一建议和授权边界 | [current_task](current_task.md) |
| 采样字段与统计语义 | [trace_contract](trace_contract.md#11-当前目标的连续采样与图表要求2026-10-16) |
| 环境、身份和状态维护 | [reproducibility](reproducibility.md) |
| 数据与原始证据保护 | [data_management](data_management.md) |

## 成果入口

| 内容 | 报告 |
| --- | --- |
| 公开操作构成/工具接口 | [操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md) |
| 公开数据集收尾 | [最新分析与保存核查](../reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)，各数据集限定范围完成；HTML及旧综合报告保留历史时点 |
| SWE-bench补充分析 | [逐任务评价补全](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[剩余来源问题](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/remaining_source_gaps.csv)；新增20,098份评价/配套文件，KGCompass身份更正；[原下载/覆盖复核](../reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/findings.md)及90条选择保留 |
| SWE-rebench复核 | [调用协议与行为v3](../reports/analysis/SWE-REBENCH-behavior-v3/findings.md)、[逐participant协议](../reports/analysis/SWE-REBENCH-behavior-v3/participant_protocol_details.csv)；598,148调用/616,980结果差额按harness错误与提交请求解释，Junie步骤摘要另列 |
| H-EPM / ToolSandbox | [工具身份与终止复核v3](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)、[26次身份补全](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/recovered_tool_identities.csv)；[原行为v2](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v2/summary.md)保留 |
| 具体软件与程序库 | [软件工具集v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| 三类本地最新分析 | [合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)，9个固定任务各3次，旧错路由样本单列排除 |
| 本地Coding | [特征化v3](../reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md) |
| 本地Office | [REPEAT-02](../reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) |
| 本地Assistant | [REPEAT-01](../reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md) |
| 本地历史测量字段与新采集接线 | [覆盖盘点v2](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v2/summary.md)（v1保留） |
| OSWorld | [命令解析与行为v4](../reports/analysis/OSWORLD-task-behavior-v4/findings.md)、[未知项审查](../reports/analysis/OSWORLD-task-behavior-v4/remaining_unknown_review.md)；[任务与原生层v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| AgentX/Applied | [AgentX Full与256k对照](../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)；[既有256k/Applied宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| 离线HTML | [v5](../reports/html/PROJECT-RESULTS-v5/index.html)，最新成果最后统一更新 |

## 历史只按需查询

旧方法、逐轮任务、交接、批准说明、CPU/G1/IR/适配器设计等77份历史文档已移入本机Git忽略的local_archive。见[历史索引](history_index.md)、[迁移登记](archive_index.json)、[引用审计](archive_reference_audit.json)。本轮编辑前快照位于local_archive/20261016-full-docs/before-edit。

报告历史原文及其manifest不改写。需要历史证据时按原逻辑路径查索引，再核对原登记SHA；不能把当前新目标当作旧批准或旧运行的证据。迁移后代码库仍不包含全部本地数据/归档，不承诺GitHub克隆后可核验全部历史证据。
