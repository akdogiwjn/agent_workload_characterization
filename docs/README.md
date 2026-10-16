# 文档索引

日常只读当前文档，不再默认打开旧任务书。事实源为[project_state.json](../project_state.json)。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-16 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 公开操作和软件汇总v3已完成限定分析：SWE-rebench 9,435轨迹，SWE-bench 19,876对象/41组；OSWorld 755模型×任务/108任务，H-EPM 414轨迹，AgentX/Applied为宏观证据。部分语义和软件运行身份未知，来源不混算分母。
- 本地主设计：Coding、Office、Assistant各3任务×3重复，共27run/9任务设计。已有CPU/内存0.5s目标采样、有限I/O、阶段与调用统计；任务容器/共享进程不等于整机或工具独占测量。
- 待补：scope明确的网络收发、任务目录/输出/缓存占用、I/O速率图及完整四面板；最新Assistant与软件成果待最后统一更新HTML。旧run不倒填缺项，Video/GUI覆盖限制保留。
- 当前入口：docs/current_scope.md（目标）、docs/project_status.md（证据）、docs/current_task.md（工作）。77份历史文档已本机归档，5处旧报告链接已修复；HTML临时生成通过但来源版本标为PARTIAL。data保留配置/清单，原始大数据留本机；未授权实验或提交。
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
| 具体软件与程序库 | [软件工具集v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| 本地Coding | [特征化v3](../reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md) |
| 本地Office | [REPEAT-02](../reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) |
| 本地Assistant | [REPEAT-01](../reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md) |
| OSWorld | [任务与行为v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| AgentX/Applied | [宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| 离线HTML | [v5](../reports/html/PROJECT-RESULTS-v5/index.html)，最新成果最后统一更新 |

## 历史只按需查询

旧方法、逐轮任务、交接、批准说明、CPU/G1/IR/适配器设计等77份历史文档已移入本机Git忽略的local_archive。见[历史索引](history_index.md)、[迁移登记](archive_index.json)、[引用审计](archive_reference_audit.json)。本轮编辑前快照位于local_archive/20261016-full-docs/before-edit。

报告历史原文及其manifest不改写。需要历史证据时按原逻辑路径查索引，再核对原登记SHA；不能把当前新目标当作旧批准或旧运行的证据。迁移后代码库仍不包含全部本地数据/归档，不承诺GitHub克隆后可核验全部历史证据。
