# DOCOPS-OFFICE-REPEAT-01 离线行为—资源特征化

## 范围与核验

显式分析 9 个 run，identity `25da9eeab2600401630ca54aa11f739dbfe08be3a57d6d4808fbc8956d65712a`。计划与冻结文件的完整 identity 对象相等，规范化 SHA-256 与批准、批摘要、批 manifest 及 raw 记录一致；批 manifest 的 161 项输入、25 项输出及九份 raw manifest 的 139 项输出均逐项哈希核验；分析共登记 335 个实际输入/归档文件。清理仅依据归档事件 `removal_verified=removed`，未查询当前 Docker。

这九次是 Excel/PPT/PDF 三项固定本地 DocOps 原子任务各三次，不是 Office 总体样本。执行环境为 ARM64 适配镜像，不能声称与官方 amd64 环境等价。

## 行为与终止

共保存逻辑请求 **49** 次、Agent 自主工具调用 **37** 次；bootstrap 每 run 的 `get_task_metadata`、`inspect_document` 分开计数，不纳入 Agent 工具数。

| Task | Round | Run | 逻辑请求 | Agent 工具序列 | invalid/unknown | termination | reward |
|---|---:|---|---:|---|---:|---|---:|
| Excel | 0 | `20261010T154928Z-r0-excel001` | 7 | xlsx_read_sheet → xlsx_read_sheet → copy_file → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet | 0 | finish | 1.0 |
| PPT | 0 | `20261010T155019Z-r0-ppt008` | 5 | ppt_list_slides → copy_file → ppt_replace_text → ppt_list_slides | 0 | finish | 1.0 |
| PDF | 0 | `20261010T155045Z-r0-pdf004` | 4 | copy_file → pdf_reorder_pages → inspect_document | 0 | finish | 1.0 |
| PPT | 1 | `20261010T155107Z-r1-ppt008` | 6 | copy_file → ppt_list_slides → ppt_replace_text → ppt_list_slides | 1 | finish | 1.0 |
| PDF | 1 | `20261010T155132Z-r1-pdf004` | 4 | copy_file → pdf_reorder_pages → inspect_document | 0 | finish | 1.0 |
| Excel | 1 | `20261010T155154Z-r1-excel001` | 6 | xlsx_read_sheet → copy_file → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet | 0 | finish | 1.0 |
| PDF | 2 | `20261010T155227Z-r2-pdf004` | 4 | copy_file → pdf_reorder_pages → inspect_document | 0 | finish | 1.0 |
| Excel | 2 | `20261010T155248Z-r2-excel001` | 8 | copy_file → xlsx_read_sheet → xlsx_set_formula → xlsx_set_formula → xlsx_read_sheet | 2 | finish | 1.0 |
| PPT | 2 | `20261010T155323Z-r2-ppt008` | 5 | ppt_list_slides → copy_file → ppt_replace_text → ppt_list_slides | 0 | finish | 1.0 |

请求模型为 `{'openai/deepseek-v4-flash': 49}`，响应记录 model 为 `{'deepseek-flash': 49}`；它们是请求别名与服务端返回标识，不证明不可变模型版本。批摘要登记 Agent 工具调用 **34** 次；从响应与 transcript 的运行时提取语义重算为 **37** 次，差异run `['20261010T154928Z-r0-excel001']`。批摘要把 **6** 条计为 invalid/unknown；复核后 3 条非裸 JSON 被接受为有效动作，3 条实际无效/未知（原因 `{'no_json_object_decoded': 1, 'unsupported_action_value': 2}`），且与 transcript 无效标记相符。这属于响应格式/动作协议，不等同 API 或工具执行失败。工具返回状态分布为 `{'saved_ok_true': 37}`；按日志内相邻 assistant action / `Tool result for <tool>` 消息及参数核对关联，无独立 call ID。

请求响应中可读取的数值 token 字段（有效/49逻辑请求）为 `{'completion_tokens': '49/49，缺失 0', 'completion_tokens_details.reasoning_tokens': '49/49，缺失 0', 'prompt_cache_hit_tokens': '49/49，缺失 0', 'prompt_cache_miss_tokens': '49/49，缺失 0', 'prompt_tokens': '49/49，缺失 0', 'prompt_tokens_details.cached_tokens': '49/49，缺失 0', 'total_tokens': '49/49，缺失 0'}`；Agent 汇总 usage 另见 `summary.json` 与逐 run 数据。usage 不等于账单，保存的 cost=0 不是免费证据；费用 unknown。

活动解释按结构化工具名保守分类：copy_file、文档/内容检查、Excel 公式编辑、PPT 文本编辑、PDF 页面编辑；不同工具接口不合并成 shell/Coding 活动类别。完整安全参数摘要与逐请求状态见 `per_run.jsonl`。

## 时间与资源

| Task | Run | Attempt wall s | 采样点/窗口 s | Agent wall s | Verifier wall s | 容器 CPU core-s | Agent 阶段 CPU core-s | Verifier 阶段 CPU core-s | memory.current 峰值 B | kernel peak B | 宿主 RSS 峰值 B |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Excel | `20261010T154928Z-r0-excel001` | 50.3 | 78/38.543623213 | 37.318566975 | 1.284901093 | 7.069852 | 6.34218 | 0.609442 | 67645440 | 75599872 | 168558592 |
| PPT | `20261010T155019Z-r0-ppt008` | 25.43 | 29/14.016835525 | 12.279795697 | 1.363368894 | 5.366808 | 4.300341 | 0.97307 | 85241856 | 85241856 | 168558592 |
| PDF | `20261010T155045Z-r0-pdf004` | 21.55 | 21/10.011705613 | 8.639832774 | 1.277428841 | 4.014582 | 3.224803 | 0.488748 | 62980096 | 72388608 | 168558592 |
| PPT | `20261010T155107Z-r1-ppt008` | 25.2 | 28/13.517154433 | 12.276783977 | 1.288787086 | 5.209944 | 4.438534 | 0.593044 | 63598592 | 78237696 | 168558592 |
| PDF | `20261010T155132Z-r1-pdf004` | 21.73 | 21/10.011217086 | 8.831449116 | 1.2259288 | 4.31821 | 3.623545 | 0.589584 | 58531840 | 73515008 | 168558592 |
| Excel | `20261010T155154Z-r1-excel001` | 32.34 | 43/21.02070479 | 19.284257841 | 1.372260355 | 6.006818 | 4.996102 | 0.92862 | 78770176 | 78770176 | 168558592 |
| PDF | `20261010T155227Z-r2-pdf004` | 20.81 | 19/9.014114076 | 7.769768375 | 1.316975101 | 4.279262 | 3.523441 | 0.599853 | 66600960 | 73711616 | 168558592 |
| Excel | `20261010T155248Z-r2-excel001` | 34.47 | 47/23.024895857 | 21.402470483 | 1.346184799 | 5.969424 | 5.040865 | 0.890143 | 76169216 | 76169216 | 168558592 |
| PPT | `20261010T155323Z-r2-ppt008` | 24.74 | 27/13.012056278 | 11.73047264 | 1.218371807 | 4.932665 | 4.100144 | 0.510067 | 71151616 | 74493952 | 168558592 |

其他已记录阶段 wall（单调事件边界差，秒；archive 为事件标记跨度而非完整归档耗时）：

| Run | Harbor start | Agent setup | Agent | Verifier | Harbor stop | Archive event span |
|---|---:|---:|---:|---:|---:|---:|
| `20261010T154928Z-r0-excel001` | 0.921817335 | 0.431087436 | 37.318566975 | 1.284901093 | 10.273144417 | 0.005665677 |
| `20261010T155019Z-r0-ppt008` | 0.917687189 | 0.425905546 | 12.279795697 | 1.363368894 | 10.376057419 | 0.003567448 |
| `20261010T155045Z-r0-pdf004` | 0.909998743 | 0.396325992 | 8.639832774 | 1.277428841 | 10.259850026 | 0.002627325 |
| `20261010T155107Z-r1-ppt008` | 0.888143116 | 0.396767488 | 12.276783977 | 1.288787086 | 10.285252982 | 0.004189827 |
| `20261010T155132Z-r1-pdf004` | 0.937079353 | 0.410668217 | 8.831449116 | 1.2259288 | 10.256912175 | 0.002890049 |
| `20261010T155154Z-r1-excel001` | 0.916588934 | 0.412960779 | 19.284257841 | 1.372260355 | 10.288586567 | 0.004570352 |
| `20261010T155227Z-r2-pdf004` | 0.911372203 | 0.391121101 | 7.769768375 | 1.316975101 | 10.356671925 | 0.002865889 |
| `20261010T155248Z-r2-excel001` | 0.931205982 | 0.422099654 | 21.402470483 | 1.346184799 | 10.29618025 | 0.006754112 |
| `20261010T155323Z-r2-ppt008` | 1.023711783 | 0.360037588 | 11.73047264 | 1.218371807 | 10.345075657 | 0.003482637 |

容器 blkio service-byte 观测 delta（读/写 bytes；不是完整文件系统 I/O）：

| Run | 状态 | Read bytes | Write bytes |
|---|---|---:|---:|
| `20261010T154928Z-r0-excel001` | valid_observed_blkio_service_counter_delta | 20480 | 40960 |
| `20261010T155019Z-r0-ppt008` | valid_observed_blkio_service_counter_delta | 32768 | 28672 |
| `20261010T155045Z-r0-pdf004` | valid_observed_blkio_service_counter_delta | 8192 | 4096 |
| `20261010T155107Z-r1-ppt008` | valid_observed_blkio_service_counter_delta | 0 | 28672 |
| `20261010T155132Z-r1-pdf004` | valid_observed_blkio_service_counter_delta | 0 | 4096 |
| `20261010T155154Z-r1-excel001` | valid_observed_blkio_service_counter_delta | 0 | 40960 |
| `20261010T155227Z-r2-pdf004` | valid_observed_blkio_service_counter_delta | 0 | 4096 |
| `20261010T155248Z-r2-excel001` | valid_observed_blkio_service_counter_delta | 0 | 40960 |
| `20261010T155323Z-r2-ppt008` | valid_observed_blkio_service_counter_delta | 0 | 28672 |

采样窗口短于 attempt wall；阶段 wall 按单调事件记录计算。阶段 CPU 仅累加采样区间两端都位于阶段内的累计计数差；跨阶段边界不分摊。请求日志时间字段未被当作已验证的请求区间，工具仅报告顺序。`memory.current` 是采样最大值，kernel peak 与宿主 RSS 分列。采集器使用 cgroup v1 blkio service-bytes 设备计数，状态可区分实际无记录的零与不可用；这些是容器块设备服务计数，不是完整文档/文件系统 I/O。逐 run delta 见 `per_run.jsonl`。

## 同任务三次重复

每任务单独列三个原始点及 n、median、IQR（线性插值位置 `(n−1)p`，IQR=Q3−Q1）；有效 n 按指标计算：

### Excel (`atomic__excel_001_budget_bucket_totals_seed`)

- logical_requests: 原始点 `[7, 6, 8]`；n=3，median=7.0，IQR=1.0。
- agent_tool_calls: 原始点 `[6, 5, 5]`；n=3，median=5.0，IQR=0.5。
- phase_input_tokens: 原始点 `[23937, 19362, 27939]`；n=3，median=23937.0，IQR=4288.5。
- phase_output_tokens: 原始点 `[7245, 2835, 3273]`；n=3，median=3273.0，IQR=2205.0。
- phase_cache_tokens: 原始点 `[19456, 17152, 24704]`；n=3，median=19456.0，IQR=3776.0。
- attempt_wall_s: 原始点 `[50.3, 32.34, 34.47]`；n=3，median=34.47，IQR=8.979999999999997。
- container_cpu_core_s: 原始点 `[7.069852, 6.006818, 5.969424]`；n=3，median=6.006818，IQR=0.5502140000000004。
- memory_current_sampled_peak_bytes: 原始点 `[67645440, 78770176, 76169216]`；n=3，median=76169216.0，IQR=5562368.0。
- kernel_memory_peak_bytes: 原始点 `[75599872, 78770176, 76169216]`；n=3，median=76169216.0，IQR=1585152.0。

### PPT (`atomic__ppt_008_bullet_editing_seed`)

- logical_requests: 原始点 `[5, 6, 5]`；n=3，median=5.0，IQR=0.5。
- agent_tool_calls: 原始点 `[4, 4, 4]`；n=3，median=4.0，IQR=0.0。
- phase_input_tokens: 原始点 `[11367, 13477, 11164]`；n=3，median=11367.0，IQR=1156.5。
- phase_output_tokens: 原始点 `[1074, 1182, 1094]`；n=3，median=1094.0，IQR=54.0。
- phase_cache_tokens: 原始点 `[9088, 11648, 9472]`；n=3，median=9472.0，IQR=1280.0。
- attempt_wall_s: 原始点 `[25.43, 25.2, 24.74]`；n=3，median=25.2，IQR=0.34499999999999886。
- container_cpu_core_s: 原始点 `[5.366808, 5.209944, 4.932665]`；n=3，median=5.209944，IQR=0.21707149999999942。
- memory_current_sampled_peak_bytes: 原始点 `[85241856, 63598592, 71151616]`；n=3，median=71151616.0，IQR=10821632.0。
- kernel_memory_peak_bytes: 原始点 `[85241856, 78237696, 74493952]`；n=3，median=78237696.0，IQR=5373952.0。

### PDF (`atomic__pdf_004_audit_pages_reorder_seed`)

- logical_requests: 原始点 `[4, 4, 4]`；n=3，median=4.0，IQR=0.0。
- agent_tool_calls: 原始点 `[3, 3, 3]`；n=3，median=3.0，IQR=0.0。
- phase_input_tokens: 原始点 `[9415, 9350, 9323]`；n=3，median=9350.0，IQR=46.0。
- phase_output_tokens: 原始点 `[679, 525, 503]`；n=3，median=525.0，IQR=88.0。
- phase_cache_tokens: 原始点 `[7168, 8192, 8192]`；n=3，median=8192.0，IQR=512.0。
- attempt_wall_s: 原始点 `[21.55, 21.73, 20.81]`；n=3，median=21.55，IQR=0.46000000000000085。
- container_cpu_core_s: 原始点 `[4.014582, 4.31821, 4.279262]`；n=3，median=4.279262，IQR=0.1518139999999999。
- memory_current_sampled_peak_bytes: 原始点 `[62980096, 58531840, 66600960]`；n=3，median=62980096.0，IQR=4034560.0。
- kernel_memory_peak_bytes: 原始点 `[72388608, 73515008, 73711616]`；n=3，median=73515008.0，IQR=661504.0。

## 结论边界与下一步

数据支持：在本批登记条件下，三个任务分别呈现上述结构化操作序列、逻辑请求数和共享容器/宿主观测；同任务三次原始值存在可量化差异。reward=1 与 finish 是本批保存的任务/终止事实，资源仍可描述其执行过程。

不能据此推断 Office 类别总体、工具数导致 CPU 差异、单工具独占资源、模型/框架排名、推理时间、真实账单或 ARM64 与 amd64 等价性。三次重复不足以证明稳定趋势；容器资源不区分工具和 verifier 之外的容器活动。

唯一最小下一步建议：若要将结论从三个固定任务扩展为 Office workload 特征，先按同样固定配置为不同 Office 任务类型登记少量重复样本；本轮不启动。
