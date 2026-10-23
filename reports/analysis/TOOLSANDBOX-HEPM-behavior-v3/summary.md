# H-EPM / ToolSandbox：原生工具身份与终止证据复核 v3

当前两组414条轨迹的离线行为复核完成。无须以任务成功为前提，也不将源材料未记录的字段当作尚未执行的分析任务。仅读取冻结JSON并静态解析保存的请求，不执行任何来源代码、Agent、工具或模型。

## 本轮补齐

- 全部2,021次Agent调用与2,021次返回继续按调用ID关联，错误304次，数量不变。
- SANDBOX请求行保存了原生函数名。严格核对发送方/接收方、call ID、扰动名称、allow list和三条语句的AST结构，2,021次调用全部可绑定到原生工具身份。没有运行保存的Python。
- 与无异常返回中的有效tool_trace交叉核对1717次，名称一致；异常行的陈旧tool_trace继续排除。
- 原24次未知调用的原生身份全部补齐；另外2次原来只有数据库活动分类的调用也取得确切工具名。剩余未知原生身份0。

[26条身份补全证据](recovered_tool_identities.csv) · [逐调用记录](call_records.jsonl) · [活动统计](activity_counts.csv)

## 两组统计（描述性）

| 组 | 轨迹 | Agent调用 | 工具错误 | 活动序列未知边界 |
|---|---:|---:|---:|---:|
| graph_False | 207 | 1029 | 157 | 0 |
| graph_True | 207 | 992 | 147 | 0 |

调用数量、调用返回配对和来源similarity字段不变；活动与原生工具分布按补全身份重算。每轨迹分布以各组全部207条为分母，含该活动的零值；与调用条目总量分母分开。

## 终止记录：哪些是事实，哪些没有记录

- 406条保存了用户模拟器向执行环境发出的end_conversation请求，其中402条还保存了相应tool_trace返回，且末态conversation_active=false。用户侧请求及返回不算Agent业务调用。
- 另外12条末态conversation_active=true：4条已保存用户end请求但没有保存对应执行返回，8条没有保存用户end请求。它只说明记录中的请求/返回及末态，不能自动称为任务失败或异常终止。
- Agent侧end_conversation调用为0。源材料未记录完整Agent终止原因，因此不推断正常结束、轮数上限或超时。上述12条也不被当作尚未分析。

[逐轨迹终止证据](termination_records.jsonl)。milestone_similarity、minefield_similarity、similarity继续按来源值保存；不把分数阈值擅自转换成任务成功。

## 两组运行来源与剩余材料边界

共享207个场景键、各109个基础场景。来源result_summary保存的split=test、seed=42、ratio=0.8；两组git_sha分别为`4f7fffb17fe1fdfd969350b5ab081fcfec130585 + local changes`和`75cf0c9bb12a87f60c95fb1407e1ab431869a42f + local changes`。完整字段见summary.json的source_run_metadata。

graph开关来自目录名和README，源码版本不同且都有未冻结的本地修改，不能把组间差异归因为单一graph开关。无法从这些材料恢复受控实验或完整的历史源码/环境身份。

没有完整时间戳、usage/token、CPU、内存、I/O、工具耗时和费用数据；本轮不伪造或通过重跑回填这些字段。当前已选公开材料的工具行为与证据复核可收尾，未来扩充其他轨迹或开展本地测量属于另一个任务。

## 校验与复现

先复核v2 manifest的全部输入/输出/分析代码及本轮代码/测试，再静态分析；末尾再次核验输入。旧raw、v1/v2及其manifest保持不变。

```bash
python3 -B -m unittest tests.test_toolsandbox_hepm_review_v3 -v
python3 -B scripts/toolsandbox_hepm_review_v3.py
```

入口拒绝覆盖已存在的v3目录。复现需要完整本机raw与冻结v2产物，请在独立副本中使用新输出目录。

[summary.json](summary.json) · [manifest](manifest.json) · [v2历史报告](../TOOLSANDBOX-HEPM-behavior-v2/summary.md)
