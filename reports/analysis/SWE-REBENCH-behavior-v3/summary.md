# SWE-rebench：调用协议、行为覆盖与结果复核 v3

本项目当前选定的第三方normalized语料复核完成：85个分片、9,435条轨迹、111个任务、17个participant、每组5轮。分片压缩字节与解压内容SHA256均核验。没有执行保存命令、Agent、模型或评测。

## 调用与返回差额：明确解释来源

来源保存598,148个tool_call事件、616,980个tool_result事件。589,061对可按唯一ID关联，未出现重复ID或孤立返回ID；其余记录不能直接视为丢失了工具执行日志。

| 记录类型 | 数量 | 含义 |
|---|---:|---|
| 没有ID的明确未调用报告 | 27,059 | tool_call_not_invoked，包括error_to_regenerate的嵌套context |
| 没有ID的多调用提取错误 | 860 | multiple_tool_calls_extracted，保存候选ID清单 |
| 无ID且类型仍不明确 | 0 | 保留来源未知，不按位置配对 |
| 无独立返回、ID见于提取错误的候选 | 1,875 | 是候选与harness错误的ID关系，不是执行返回 |
| 无返回、源码含提交操作的请求 | 7,201 | 包含独立submit和组合命令中的submit分支 |
| 其余没有返回的请求 | 11 | 逐事件保留证据 |

上表前3行合计27,919个无ID记录，后3行合计9,087个无返回请求。两者差为18,832，恰好解释返回数多于调用数的差额。并非漏下载了18,832次调用，也不能把harness解析错误里的候选当作已经执行的工具。

[逐participant协议统计](participant_protocol_details.csv) · [逐事件证据](protocol_detail_evidence.jsonl)

提取错误以JSON对象或Python字面量形式保存在error字段。本轮只用AST读取字面量中的type/context/candidate ID，不执行表达式；拒绝通过相邻位置给候选补出工具返回。submit只表示保存请求含提交意图，不证明条件分支执行、正常退出或题目成功。

## 通用shell行为：沿用已验收的命令语义

原行为v2只支持简单命令，476,590个Unknown不应被当作当前全部分析的语义覆盖结论。本轮沿用冻结的PUBLIC-TRACE-OPERATIONS-v3静态命令分析，并按轨迹ID、participant、任务、行号逐项与原始记录对齐，没有把bash一律归为执行活动。

按全部598,148个保存请求：完全Unknown 17,999、部分识别55,074、多类组合200,103。含测试操作的请求53,790，含编辑/写入78,567；类别存在重叠，不相加成100%，也不表示所有分支实际运行。

[全部请求与有ID结果请求的操作对照](operations_by_evidence_scope.csv)单列589,061个可关联结果的请求，避免把候选提取错误、提交分支和真正有返回的请求混作执行次数。行为×来源评测结果的逐participant分层见[operation_result_strata.csv](operation_result_strata.csv)，不进行模型排名。

## Junie：没有标准tool_call不代表零工具行为

Junie的555条轨迹保存31,449个agent_step摘要，标准tool_call/tool_result事件均为0。每条记录的agent_step数与来源usage.tool_calls一致，555/555条相符。它是另一种保存格式，不能把31,449条摘要塞入598,148次标准调用分母。

摘要标题包括Opened 10,275次、Found 5,528次、Edited 4,044次，以及命令式标题。保留标题和elapsed_ms字段的存在性，不从标题恢复不存在的原生call ID、参数或调用返回协议；也不把elapsed_ms当作已验证的CPU或工具独占耗时。

## 任务结果、退出状态与保存质量

来源评测状态：resolved=4,751、failed=4,683、skipped=1。evaluation_matches_selected均为true，status与resolved布尔值无内部冲突；这是来源自报的一致性检查，不是本项目重新评分。来源agent_exit_status为submit=7,212、submitted=2,220、agent/agent_proxy/inference_server/prompt_too_long=3。

失败任务仍可完成行为分析，submit/submitted也不等于修复成功。见[退出状态×评测结果](evaluation_exit_cross_tab.csv)。

源发布策略明确不含patch；4,092条工具结果被截断、32条缓存内容被省略，均与源manifest总计相符。它们是已保存语料的内容策略，不是本轮尚未下载的文件。提示词有暴露/不可见边界，provider/agent上报的token、wall_time_seconds和cost_usd均不当作本项目资源采样或账单。

## 本轮结论与边界

已选语料的完整性、调用协议、保存行为、任务结果和来源质量均已复核；无需先让原Agent把失败任务修成成功才能收尾。无CPU、内存、I/O、可靠工具时长和完整原始provider日志，不能靠重新解释现有字段补出。未来新增其他语料、原始日志或本地资源测量是独立任务。

本轮保存v1/v2及PUBLIC-TRACE-OPERATIONS-v3原件；最新机器汇总为[reviewed_summary.json](reviewed_summary.json)。

```bash
python3 -B -m unittest tests.test_swe_rebench_review_v3 tests.test_swe_rebench_protocol_details -v
python3 -B scripts/swe_rebench_review_v3.py
python3 -B scripts/swe_rebench_protocol_details.py
```

入口拒绝覆盖既有输出；复现需完整本地raw与冻结历史报告，在独立副本中新建输出。

[初步复核manifest](manifest.json) · [明细复核manifest](review-manifest.json) · [校验](verification.json)
