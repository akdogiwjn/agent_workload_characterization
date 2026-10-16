# v2 → v3 集中更正

| 问题 | v2错误 | 修复依据与v3结果 | 仍未知/限制 |
| --- | --- | --- | --- |
| SAGE OpenHands 命令协议 | 499个文件被留在过程/歧义类 | 检出 15,155 个 `Running command:` 候选，提取 15,141 条非空命令；14 个空命令标记拒绝；另存 17,338 个 return_code 结果记录 | 0 个ID配对；消息相邻只单列 15,138 条结果线索，不宣称一一关联；未把提示/叙述作为命令 |
| SWE-Exp | 500个文件因首项problem_statement被判配套产物 | 按完整列表读取 3,065 个带assistant/observation的保存过程节点，并按instructor类型汇总 | 节点不是工具调用或真实执行时间线；未推断工具名 |
| MASAI | 只读Template Generation Agent，v2计 7,409 个动作 | 按三类明确Model response段读取，v3共 23,013 个动作；分Agent计数见summary.json/toolkits.json | Test Case Reproducer Agent重算 8,223，前置扫描线索 8,212，差 +11；无稳定ID或无效标签证据支持去重，差异原因未确认。 另有 19,569 个无ID返回块不与动作配对，响应段外 21,848 个同形标签被排除 |
| Learn-by-Interact file_edit | v2提取 729 个file_edit | v3候选 4,177、闭合 4,135、提取 4,135、拒绝/歧义 42；该submission总动作 9,022 → 12,410 | 仍无调用ID；不执行编辑正文。CodeShell同形候选 0，未发现同类实际遗漏 |
| SWE-rebench关联 | v2调用 598,148、返回0、调用缺ID 598,148 | v3从原生tool_call_id/tool_result重算：调用 598,148、返回 616,980、唯一1:1 589,061、仅调用侧ID 9,087 | 重复、孤立、缺ID及非1:1仍分列，不按位置补配；147个不可识别tool字段仍未知身份 |
| Solver返回归属 | v2将 5,150 个操作返回重复挂到检索行 | v3按事件类型归属：操作事件 5,150 个，检索事件 0 个，总计 5,150 | 返回只表示保存的execution事件结果字段，不代表成功执行；retrieval仍用独立单位 |

v2与历史原始文件保持原字节。v2绑定源码在修改前的精确快照位于 `env/public-trace-operations-v3/source-before-edit/`；v3 manifest同时登记快照、当前代码及输入输出哈希。
