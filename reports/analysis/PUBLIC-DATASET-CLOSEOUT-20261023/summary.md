# 公开数据集分析收尾核查（2026-10-23）

本轮已经完成约定的公开语料下载补全、静态行为解析和结果复核。现有公开记录范围内没有必须继续补做的分析项；保留的来源缺失、语义未知和结果冲突均已单列。扩大数据集或重新运行任务属于后续工作。

| 数据集 | 最新分析入口 | 本轮进展及保留边界 |
| --- | --- | --- |
| SWE-rebench | [行为与调用协议v3](../SWE-REBENCH-behavior-v3/findings.md) | 85分片、9,435轨迹完整核验；调用/返回数量差额已核清，Junie步骤摘要另列。归一化语料不含完整原生执行及本地资源证据。 |
| SWE-bench公开submissions | [逐任务评价补全](../SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[覆盖复核](../SWEBENCH-COVERAGE-RESULTS-v1/findings.md) | 登记20,023对象/41组；补下147轨迹文件和20,098份评价等文件。剩余空文件、无公开评价、5项来源冲突等见[逐项清单](../SWEBENCH-INSTANCE-RESULTS-v1/remaining_source_gaps.csv)；“任务未解决”不表示分析没完成。并未承诺穷尽上游所有submission或完整解析所有原生格式。 |
| OSWorld | [行为解析v4](../OSWORLD-task-behavior-v4/findings.md)、[剩余未知项复核](../OSWORLD-task-behavior-v4/remaining_unknown_review.md) | 755模型×任务记录、201,050条保存命令；扩展静态解析，原生动作与源码调用分别统计。静态分支和保存片段不等于全部实际执行。 |
| H-EPM / ToolSandbox | [工具与终止证据v3](../TOOLSANDBOX-HEPM-behavior-v3/summary.md) | 414轨迹、2,021次调用全部核实原生工具身份；结束请求与返回分列。两组源码不同且含本地修改，不能作单开关因果对照。 |
| AgentX Full / 256k | [Full完整宏观分析及对照](../AGENTX-FULL-MACRO-v1/summary.md) | 两版均393会话，98,827/68,266请求；完整语料分析已超出早期AX-7/AX-SUB试点。仍不含完整业务工具日志；两版重叠，不合并为独立样本。 |
| Applied Compute | [既有宏观分析](../AGENTX-APPLIED-MACRO-v1/summary.md) | coding、code QA、office各8,192模板，既有模板分析保留；模板不是实际执行轨迹，本轮无新增执行分析。 |

当前报告、图表、CSV/JSON汇总、逐条派生结果、下载登记及SHA256清单均保存在本机。最新入口已登记到README、文档索引及project_state；各历史报告保持原时点。[HTML v5](../../html/PROJECT-RESULTS-v5/index.html)和旧综合报告仍是历史快照，尚未统一重制。

本次只读核对16份分析/采集manifest，共166,322条文件哈希登记，按路径和预期哈希去重后核验64,062项（约7.16 GB文件内容），全部匹配。79项定向及相关回归测试通过。完整核对结果见[verification.json](verification.json)。该检查核实保存文件及其登记一致性，不替代独立重跑或重新评分。

清理核查限于本轮非视频报告、采集目录及新增原始数据目录：没有发现`.part`、`.tmp`、`.temp`或编辑备份残片，没有必须删除的项目文件。`/tmp/TOOLSANDBOX-HEPM-behavior-v3-draft-20261023/`是可丢弃的初稿，保留在项目外；没有删除正式报告、历史版本、原始数据或任何视频文件。

远程发布范围为分析脚本、测试、汇总报告、图表、采集计划和manifest，以及本轮导航/状态增量。原始语料、source_metadata和被忽略的大型逐条派生文件保留本机，不随Git上传；Git远程不是完整数据备份，单独克隆不能直接完成全部历史数据校验。共享文档的非本会话改动与视频改动留在本地工作区，不纳入本轮提交。
