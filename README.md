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
当前状态由 [2026-10-23 状态真源](project_state.json)统一登记；这是进度记录，不是执行授权。

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

## 主要成果

- AgentX深入分析：[第一步发现与10页PPT](reports/analysis/AGENTX-DEEP-ANALYSIS-v1/findings.md)，全393会话的上下文、前缀复用、子代理时序和256k影响；提供10张4K PNG/SVG及作图CSV。

- [公开数据集收尾总表](reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)：最新分析、来源缺口、文件保存与非视频清理核查；64,062项哈希核对及79项测试通过。
- SWE-bench：[逐任务评价补全与复核](reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)，另补20,098份评价/预测等文件；原8,730个未列项逐项核查，KGCompass任务身份更正。[此前下载与覆盖复核](reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/findings.md)保留。
- OSWorld：[命令解析与行为发现v4](reports/analysis/OSWORLD-task-behavior-v4/findings.md)，全755条记录重算；[剩余未知项审查](reports/analysis/OSWORLD-task-behavior-v4/remaining_unknown_review.md)。
- H-EPM / ToolSandbox：[工具身份与终止证据复核v3](reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)，414条轨迹、2,021次调用全部核实原生工具身份，24次未知调用补齐；终止记录按请求/返回分别报告。
- SWE-rebench：[调用协议与行为复核v3](reports/analysis/SWE-REBENCH-behavior-v3/findings.md)，9,435轨迹、85分片核验；调用/返回差额逐类解释，Junie步骤摘要独立统计，原任务失败与分析进展分开。
- AgentX Full：[完整公开请求语料宏观分析及256k对照](reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)，393会话、98,827请求；不含业务工具明细或本地资源。

- [LOCAL-THREE-CLASS-REPEAT-01限定收尾](reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-characterization-v1/summary.md)：原定27次仅启动1次Excel，批验收接线错误后停止，26未执行；不冒称重复批次完成。
- 公开操作：[操作v3](reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)。
- 具体软件：[工具栈v3](reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md)。
- 本地资源：[Coding](reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md)、[Office](reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md)、[Assistant](reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md)。
- [历史测量字段覆盖与新采集接线v3](reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)：仅核验三个登记批次各9个历史run；初始化异常收尾与按指标区间口径已离线验证，任务目录、共享netns修复未做真实运行。
- [HTML v5](reports/html/PROJECT-RESULTS-v5/index.html)：旧时点展示，最新Assistant及软件成果待最后统一更新。

## 开发与保护

并发工作请遵守[状态防丢失流程](docs/project_state_protection.md)；状态更新工具自动快照并拒绝旧版本覆盖，完整本地状态与远程提交范围分开记录。

代码在`src/agent_workload_characterization/`，要求Python >=3.11。按改动选择定向测试，不默认执行全历史测试或任何`--execute`入口。文档状态检查：`python3 -B scripts/check_project_state.py`。

当前事实在`project_state.json`，三个当前页面的状态块由既有render规则统一生成。原始trace、正式raw、批准/attempt、manifest、冻结身份、源码快照与环境不随文档整理删除或搬迁。未跟踪文件可能是正式成果，禁止用`git clean`代替清理审查。

本机旧交接文档、导航备份和缓存归入`local_archive/`，不提交GitHub。镜像导出、原始数据、虚拟环境、第三方源码副本和指定大型派生明细也被忽略，但保留本机原件。GitHub代码副本不含完整实验数据；运行/核验全部历史证据需另行提供这些本地资产。未执行提交或推送。
