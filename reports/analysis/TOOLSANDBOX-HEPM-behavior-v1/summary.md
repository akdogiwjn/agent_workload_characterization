# H-EPM ToolSandbox 公开轨迹行为分析 v1

第三方 H-EPM（commit `4ad8ad335fe63d365f4baf97df77e19055c79f1c`）发布的 ToolSandbox 扩展实验离线分析；仅读取已保存 JSON，不执行来源框架或数据中的代码，不运行 benchmark/轨迹/模型。

## 规模与身份
- 两组各 207 条轨迹、207 个 dataset-local 场景标识；共享场景键 207 个；payload 832 文件 / 23,150,323 bytes 逐项 bytes/SHA-256 核验通过。
- 运行配置（summary_on/split_test/graph）仅见于目录名与来源 README，轨迹文件内无逐运行配置字段；两组不作为受控因果实验。
- 变体合并仅剥离 H-EPM 后缀（scramble/distraction/all_tools；与 tool_augmentation_list、result_summary 类别逐场景一致），得 109 个基础场景；alt/implicit/low_battery_mode/wifi_off 等官方场景命名 token 不合并。

## 调用与返回关联
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：工具调用条目 1029、tool 结果消息 1029；带 ID 调用 1029、配对 1029、缺返回 0、孤立返回 0、重复调用 ID 条目 0、名称不匹配 0；协议问题 无。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：工具调用条目 992、tool 结果消息 992；带 ID 调用 992、配对 992、缺返回 0、孤立返回 0、重复调用 ID 条目 0、名称不匹配 0；协议问题 无。

## 工具接口与活动
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：原生身份调用 top：summarize_the_task=207, get_current_timestamp=82, datetime_info_to_timestamp=46, timestamp_to_datetime_info=46, search_messages=44, search_reminder=43, set_wifi_status=42, search_contacts=38；scrambled 名调用 120 条（解析：{'content_prefix_summary_tool': 28, 'database_namespace_activity': 22, 'milestone_tool_trace': 15, 'native_name': 909, 'unresolved_scrambled': 55}）。
  活动构成（pooled，分母=调用条目）：{'contact': 92, 'datetime': 215, 'harness_summary': 207, 'location': 52, 'messaging': 55, 'reminder': 79, 'settings': 224, 'weather': 15, 'web_api_search': 35}。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：原生身份调用 top：summarize_the_task=206, get_current_timestamp=82, search_reminder=45, search_messages=40, set_wifi_status=39, datetime_info_to_timestamp=38, search_contacts=35, timestamp_to_datetime_info=32；scrambled 名调用 108 条（解析：{'content_prefix_summary_tool': 24, 'database_namespace_activity': 19, 'milestone_tool_trace': 15, 'native_name': 884, 'unresolved_scrambled': 50}）。
  活动构成（pooled，分母=调用条目）：{'contact': 90, 'datetime': 201, 'harness_summary': 206, 'location': 44, 'messaging': 50, 'reminder': 82, 'settings': 213, 'weather': 19, 'web_api_search': 37}。
- 原生工具共 35 个（allow list 并集）；harness 辅助 summarize_the_task 单列，end_conversation 声明可用但从未被调用。

## 行为序列
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：每轨迹调用数 median 5.0 / IQR 4.0（n=207）；活动序列同类转换 328、异类转换 421、Unknown 边界相邻对 74；活动转换最高：settings->settings=161, datetime->datetime=92, harness_summary->datetime=52, datetime->reminder=42, contact->contact=40。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：每轨迹调用数 median 5.0 / IQR 3.0（n=207）；活动序列同类转换 288、异类转换 437、Unknown 边界相邻对 64；活动转换最高：settings->settings=144, datetime->datetime=78, harness_summary->datetime=47, datetime->reminder=45, contact->contact=39。
- 序列仅按保存记录顺序，不代表真实执行顺序或并发关系；未解析活动记为 None 边界，转换不跨越边界。

## 具体行为观察
- 零工具调用轨迹 5 条（类别组合：[('CANONICALIZATION', 'SINGLE_TOOL_CALL', 'SINGLE_USER_TURN', 'THREE_DISTRACTION_TOOLS', 'TOOL_DESCRIPTION_SCRAMBLED'), ('INSUFFICIENT_INFORMATION', 'NO_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'TEN_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'TEN_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'THREE_DISTRACTION_TOOLS', 'TOOL_NAME_SCRAMBLED')]），多为 INSUFFICIENT_INFORMATION 场景中模型直接向用户澄清。
- summarize_the_task 每轨迹调用分布 {'0': 19, '1': 378, '2': 16, '3': 1}；system prompt 声明必须至少调用一次，但存在 0 次调用的轨迹，未按成功/失败解释。
- 含未解析 scrambled 调用的轨迹 34 条；minefield_similarity>0 的轨迹 35 条；milestone_similarity=1 的轨迹 128 条（仅原始字段计数，不转换为成功）。
- 工具执行错误（结果内容以异常头开始）合计 304 条，两组各类计数见 summary.json；与任务评估字段、harness 异常（exception_type 非空 0 条）分开统计。

## 终止与任务结果
- end_conversation 调用：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': 0, 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': 0}；结果摘要 exception_type/traceback 非空计数：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': [0, 0], 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': [0, 0]}。
  - H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：milestone_similarity median 0.933729570102293（IQR 0.3205184857266423，n=207）；minefield_similarity median 0.0；similarity median 0.89990306819505；turn_count median 13.0。
  - H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：milestone_similarity median 0.9200093052786817（IQR 0.33333333333333337，n=207）；minefield_similarity median 0.0；similarity median 0.8781023829191136；turn_count median 11.0。
- 终止状态 unknown：会话内无终止字段；end_conversation 在 allow list 中声明但从未被调用；末条消息角色分布见 summary.json，不据此猜测正常结束。
- 来源声明规则仅一条（build_graph 的 milestone_similarity > 0.55 过滤），适用边界为工具图构建，不是任务成功定义；本分析未使用该阈值。

## 两组同场景保存指标差异（描述性）
- milestone_similarity：n=207，持平 98，diff（True−False）median 0.0 / IQR 0.003112737388714315。
- minefield_similarity：n=207，持平 200，diff（True−False）median 0.0 / IQR 0.0。
- similarity：n=207，持平 91，diff（True−False）median 0.0 / IQR 0.008170370980035369。
- turn_count：n=207，持平 84，diff（True−False）median 0.0 / IQR 2.0。
- 以上仅为共享场景键上保存字段的描述性差异；两组非受控因果实验、非独立随机样本，不推断 graph 配置导致成功率、效率或资源变化。

## 相对既有公开行为证据的新增点
- 相比 Coding 的 shell/编辑工具与 OSWorld 的 GUI 动作，本数据提供有证据的 Assistant/工具协作形态：状态化 PIM 工具（reminder/contact/messaging/setting 四个数据库命名空间，写入与声明一致）、时间戳换算工具链（datetime 类调用为最大业务活动之一）、设备设置前置条件（网络关闭时 web 类工具返回 ConnectionError，PermissionError 为最常见工具执行错误）、以及 harness 在 system prompt 中强制要求的状态摘要调用 summarize_the_task。
- 工具名/描述/参数扰动的行为证据：TOOL_NAME_SCRAMBLED 场景中模型实际调用扰动后名称；其中一部分可经里程碑 tool_trace、[SummaryTool] 内容前缀或 database_update 命名空间还原原生身份或活动，其余 105 条调用保持 Unknown。
- 一条 assistant 消息可含多个工具调用（两组共 123 条多调用消息）；消息数不等于调用数。
- 尚缺字段或来源语义：真实执行顺序/并发、任何时间戳、usage/token、终止机制、逐运行配置（graph 开关仅目录名）、资源与费用。
- 值得后续本地测量的候选线索（仅为研究线索，不构成执行授权）：多调用消息的并行工具执行形态、summarize_the_task 摘要调用的上下文增长、设备设置前置失败后的重试行为。

## 限制
- 保存顺序不等于真实执行顺序；无并发证据
- 调用数量不是调用速率、工具耗时或资源消耗
- 不存在 usage/token 字段；不涉及费用或账单
- similarity 字段按原样报告，绝不转换为成功
- 无里程碑/内容/数据库证据的 scrambled 调用保持 Unknown
- 两组仅作描述性对照；不对 graph 配置作任何因果结论
- 无任何 CPU/内存/I/O 字段；资源测量不支持

[summary.json](summary.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)
