# DOCOPS Word 03/04 有限行为—资源联合分析

## 证据范围与核验

仅分析显式登记的 DOCOPS-03 与 DOCOPS-04 两个归档 run。两份 raw manifest 的输出 bytes/SHA、归档 identity、对应计划/冻结值/批准 identity 均由分析入口核验；提交 DOCX 与官方输入按保存哈希定位。历史身份按归档链判断，不要求当前源码回到历史字节。

该分析描述一个 DocOps Word 任务的两次不同步数配置运行，不是受控重复，也不估计步数预算的因果效应。

## 行为、终止与资源

| Run | 步数上限 | 请求 | 工具动作/类别 | 终止 | Reward | Wall s | 容器 CPU core-s | memory.current 采样峰值 B | 内核 memory peak B | 宿主 Agent RSS 采样峰值 B | 采样点/窗口 s |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| DOCOPS-WORD-RESOURCE-03 | 12 | 12 | 12 (file_copy:1, document_structure_inspection:1, format_inspection:3, text_edit:2, format_edit:5) | steps_exhausted | 0.0 | 85.38 | 6.680099 | 75710464 | 77762560 | 163729408 | 149 / 74.096074883 |
| DOCOPS-WORD-RESOURCE-04 | 40 | 6 | 5 (file_copy:1, document_structure_inspection:2, format_inspection:1, text_edit:1) | finish | 0.0 | 58.98 | 5.704128 | 82542592 | 82542592 | 162017280 | 96 / 47.575497794 |

### 每次运行的行为与提交文档证据

- DOCOPS-WORD-RESOURCE-03：请求模型 `openai/deepseek-v4-flash`；响应模型计数 `{'deepseek-flash': 12}`。bootstrap/setup 单列为 `{'get_task_metadata': 1, 'inspect_document': 1}`，不计入模型自主工具动作。工具返回状态 `{'ok_true': 11, 'unknown_not_persisted_or_not_linkable': 1}`；verifier 首个失败为 `Top-level headings are not styled consistently.`；此前顺序断言状态：passed by sequential verifier control flow。阶段 wall 为 `{'harbor_start': 0.924594822, 'agent_setup': 0.438315786, 'agent': 70.35322446, 'verifier': 1.410398703, 'harbor_stop': 10.264617131, 'archive': 1.26e-05}` 秒；阶段内样本 CPU 差分为 `{'agent_setup': None, 'agent': 5.318106, 'verifier': 1.006266}` core-s；当前源码回读与历史 identity 文件哈希不一致项 `['entry']`（不改变已核验归档身份）。可用独立 run-report 与 raw 的交叉核验 `None`；无独立报告时为 null。
  提交 DOCX 与输入按段落位置比较：文本改变段落索引 `[18, 40, 45]`；正文新标签/TOC新标签/旧标签计数为 `{'new_body_label_exact_paragraphs': 1, 'new_toc_label_exact_paragraphs': 1, 'old_label_occurrences': 0}`。格式编辑动作数 `5`，其参数中的直接格式字段数 `0`；动作参数为 `[{'paragraph_index': 25, 'style_name': 'Heading 1', 'direct_format_fields_supplied': []}, {'paragraph_index': 45, 'style_name': 'Heading 1', 'direct_format_fields_supplied': []}, {'paragraph_index': 28, 'style_name': 'Heading 2', 'direct_format_fields_supplied': []}, {'paragraph_index': 48, 'style_name': 'Heading 2', 'direct_format_fields_supplied': []}, {'paragraph_index': 50, 'style_name': 'Heading 2', 'direct_format_fields_supplied': []}]`。保存文档 Heading 1 样式段落数 `2`（索引 `[25, 45]`）；静态定位到的 verifier 顶级标题中 `3` 个匹配、直接 XML 签名有 `3` 种。具体段落直接属性与签名见 per_run.json。该 XML 盘点不重跑 verifier，也不替代其实际结果。
- DOCOPS-WORD-RESOURCE-04：请求模型 `openai/deepseek-v4-flash`；响应模型计数 `{'deepseek-flash': 6}`。bootstrap/setup 单列为 `{'get_task_metadata': 1, 'inspect_document': 1}`，不计入模型自主工具动作。工具返回状态 `{'ok_true': 5}`；verifier 首个失败为 `Top-level headings are not styled consistently.`；此前顺序断言状态：passed by sequential verifier control flow。阶段 wall 为 `{'harbor_start': 0.914662919, 'agent_setup': 0.392767052, 'agent': 44.026393993, 'verifier': 1.38564357, 'harbor_stop': 10.269852107, 'archive': 1.168e-05}` 秒；阶段内样本 CPU 差分为 `{'agent_setup': None, 'agent': 4.571002, 'verifier': 0.981776}` core-s；当前源码回读与历史 identity 文件哈希不一致项 `[]`（不改变已核验归档身份）。可用独立 run-report 与 raw 的交叉核验 `{'run_id_matches': True, 'identity_matches': True, 'request_count_matches': True, 'termination_matches': True, 'reward_matches': True, 'wall_matches': True, 'tool_name_counts_match': True}`；无独立报告时为 null。
  提交 DOCX 与输入按段落位置比较：文本改变段落索引 `[18, 40]`；正文新标签/TOC新标签/旧标签计数为 `{'new_body_label_exact_paragraphs': 1, 'new_toc_label_exact_paragraphs': 1, 'old_label_occurrences': 0}`。格式编辑动作数 `0`，其参数中的直接格式字段数 `0`；动作参数为 `[]`。保存文档 Heading 1 样式段落数 `0`（索引 `[]`）；静态定位到的 verifier 顶级标题中 `3` 个匹配、直接 XML 签名有 `3` 种。具体段落直接属性与签名见 per_run.json。该 XML 盘点不重跑 verifier，也不替代其实际结果。

终止与任务结果（独立维度）：DOCOPS-WORD-RESOURCE-03：steps_exhausted，reward=0.0；DOCOPS-WORD-RESOURCE-04：finish，reward=0.0。保存的 pytest 输出首个失败为：DOCOPS-WORD-RESOURCE-03：Top-level headings are not styled consistently.；DOCOPS-WORD-RESOURCE-04：Top-level headings are not styled consistently.。失败前的顺序断言已执行且未触发失败；后续断言未执行或 unknown。reward=0 不抹去实际采样的描述价值，但这些开销不是成功完成成本。

模型请求与 bootstrap/setup 分开计数。工具类别依据结构化 action 的 tool_name；返回只在保存的对话历史中出现紧随其后的 `Tool result for <tool>` 消息时关联。若终止前没有下一请求持久化该消息，返回状态保持 unknown。工具参数摘要和提交 DOCX 的段落/样式状态见 per_run.json；工具成功不等于 verifier 正确。

资源按原采样字段重算：CPU 为首末有效 cgroup 累计计数差，memory.current 为采样最大值，kernel memory peak 单列，宿主 RSS 为采样最大值。采样窗口短于 attempt wall；阶段 CPU 仅累计阶段内两端样本均在边界内的相邻采样差，边界混合未均摊。容器资源不能归因到单个工具，宿主 RSS 不是模型推理 CPU。I/O 只盘点字段与读取状态，不解释为完整文件系统 I/O。

## 有限结论与缺口

两条记录共同出现的结构化工具类别为 `['document_structure_inspection', 'file_copy', 'format_inspection', 'text_edit']`；调用证明动作被发出，不代表结果正确。格式参数、工具返回和保存 DOCX 状态需交叉解读。出现 finish 也不等于任务通过；两点间 wall/CPU/内存差异不能单因归结为 max_steps。

reward=0 仍可用于分析实际调用序列、终止路径和已观测资源；但不应称为成功完成成本、Office 类别规律或模型能力结论。当前没有逐工具资源时间戳，也不能把请求时间解释为服务端推理时间。

下一步唯一建议：若研究问题要区分任务特异性与稳定行为，先评估是否在另一项固定 Office 任务上做固定配置重复；不要为了 reward=1 自动重跑本任务。

G2/G3-R 裁定不变；CPU-02 与 Replay 继续暂停。
