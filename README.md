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
当前状态由 [2026-10-20 状态真源](project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 公开操作和软件汇总v3已完成限定分析：SWE-rebench 9,435轨迹，SWE-bench 19,876对象/41组；OSWorld 755模型×任务/108任务，H-EPM 414轨迹，AgentX/Applied为宏观证据。部分语义和软件运行身份未知，来源不混算分母。
- 本地三个既有批次的27个显式run已完成字段与manifest盘点；历史区间覆盖v3按CPU、cgroup I/O及可用/proc I/O分列候选/有效/gap，网络字节和任务目录边界占用没有观测，未回填。
- 新口径三链各一次已完成：Office目录扫描cwd修正后0→6629B；Coding Agent/verifier目录分别增长4874269/4614250B；Assistant场景内存状态N/A。主项采集和归档通过，cache仍unsupported导致supplement aggregate partial；共享netns不是任务/API专属字节。
- 火山三链各n=1限定离线分析完成：3张独立四面板资源SVG、作图CSV和目录占用表已生成。请求Office8、Coding20、Assistant Agent/User6/1；原生工具、Submitted控制流与业务错误分别统计。Coding宿主末次process_exited保留gap；共享netns不代表API字节，不合并旧27次。报告：reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/summary.md。
- LOCAL-THREE-CLASS-COMPLETE-02已顺序执行12/12次，identity 8a17109cf441e3ae68e3f9820babe5685467657cbcafb56d765dd1158dc4942d；合并原有效样本后27个固定task×round槽位各n=3，累计35次启动含8个永久排除的旧Office错路由attempt。v3独立复核及资源图已生成；7/7固定镜像批后身份匹配，raw归档哈希回读通过。n=3不代表类别总体，HTTP次数/费用unknown。报告：reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
<!-- PROJECT_STATE:END -->

## 主要成果

- [LOCAL-THREE-CLASS-REPEAT-01限定收尾](reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-characterization-v1/summary.md)：原定27次仅启动1次Excel，批验收接线错误后停止，26未执行；不冒称重复批次完成。
- 公开操作：[操作v3](reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)。
- 具体软件：[工具栈v3](reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md)。
- 本地资源：[Coding](reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md)、[Office](reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md)、[Assistant](reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md)。
- [历史测量字段覆盖与新采集接线v3](reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)：仅核验三个登记批次各9个历史run；初始化异常收尾与按指标区间口径已离线验证，任务目录、共享netns修复未做真实运行。
- [HTML v5](reports/html/PROJECT-RESULTS-v5/index.html)：旧时点展示，最新Assistant及软件成果待最后统一更新。

## 开发与保护

代码在`src/agent_workload_characterization/`，要求Python >=3.11。按改动选择定向测试，不默认执行全历史测试或任何`--execute`入口。文档状态检查：`python3 -B scripts/check_project_state.py`。

当前事实在`project_state.json`，三个当前页面的状态块由既有render规则统一生成。原始trace、正式raw、批准/attempt、manifest、冻结身份、源码快照与环境不随文档整理删除或搬迁。未跟踪文件可能是正式成果，禁止用`git clean`代替清理审查。

本机旧交接文档、导航备份和缓存归入`local_archive/`，不提交GitHub。镜像导出、原始数据、虚拟环境、第三方源码副本和指定大型派生明细也被忽略，但保留本机原件。GitHub代码副本不含完整实验数据；运行/核验全部历史证据需另行提供这些本地资产。未执行提交或推送。
