# AI Agent Workload Characterization

研究Agent执行单个任务时的CPU、内存、磁盘I/O与占用、网络、时长、工具和具体软件使用。公开trace补充行为分布，本地执行提供资源采样；不做能力排行榜。

## 日常阅读入口

| 内容 | 入口 |
| --- | --- |
| 当前目标、必采指标与排除项 | [当前范围](docs/current_scope.md) |
| 已完成什么、实现和证据限制 | [项目总览](docs/project_status.md) |
| 当前工作、下一项建议和停止点 | [当前任务](docs/current_task.md#current-task) |
| 成果、规范与历史导航 | [文档索引](docs/README.md) |

GPU、热点/PMU、微架构和优化不是当前必交。旧方法文档与任务库已移入本机归档，见[历史索引](docs/history_index.md)，不默认全文读取，不从旧命令恢复授权。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-16 状态真源](project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 公开操作和软件汇总v3已完成限定分析：SWE-rebench 9,435轨迹，SWE-bench 19,876对象/41组；OSWorld 755模型×任务/108任务，H-EPM 414轨迹，AgentX/Applied为宏观证据。部分语义和软件运行身份未知，来源不混算分母。
- 本地主设计：Coding、Office、Assistant各3任务×3重复，共27run/9任务设计。已有CPU/内存0.5s目标采样、有限I/O、阶段与调用统计；任务容器/共享进程不等于整机或工具独占测量。
- 待补：scope明确的网络收发、任务目录/输出/缓存占用、I/O速率图及完整四面板；最新Assistant与软件成果待最后统一更新HTML。旧run不倒填缺项，Video/GUI覆盖限制保留。
- 当前入口：docs/current_scope.md（目标）、docs/project_status.md（证据）、docs/current_task.md（工作）。77份历史文档已本机归档，5处旧报告链接已修复；HTML临时生成通过但来源版本标为PARTIAL。data保留配置/清单，原始大数据留本机；未授权实验或提交。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
<!-- PROJECT_STATE:END -->

## 主要成果

- 公开操作：[操作v3](reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)。
- 具体软件：[工具栈v3](reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md)。
- 本地资源：[Coding](reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md)、[Office](reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md)、[Assistant](reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md)。
- [HTML v5](reports/html/PROJECT-RESULTS-v5/index.html)：旧时点展示，最新Assistant及软件成果待最后统一更新。

## 开发与保护

代码在`src/agent_workload_characterization/`，要求Python >=3.11。按改动选择定向测试，不默认执行全历史测试或任何`--execute`入口。文档状态检查：`python3 -B scripts/check_project_state.py`。

当前事实在`project_state.json`，三个当前页面的状态块由既有render规则统一生成。原始trace、正式raw、批准/attempt、manifest、冻结身份、源码快照与环境不随文档整理删除或搬迁。未跟踪文件可能是正式成果，禁止用`git clean`代替清理审查。

本机旧交接文档、导航备份和缓存归入`local_archive/`，不提交GitHub。镜像导出、原始数据、虚拟环境、第三方源码副本和指定大型派生明细也被忽略，但保留本机原件。GitHub代码副本不含完整实验数据；运行/核验全部历史证据需另行提供这些本地资产。未执行提交或推送。
