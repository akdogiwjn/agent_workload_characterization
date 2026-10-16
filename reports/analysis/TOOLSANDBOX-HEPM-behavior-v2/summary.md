# H-EPM ToolSandbox 公开轨迹行为分析 v2

第三方 H-EPM（commit `4ad8ad335fe63d365f4baf97df77e19055c79f1c`）发布的 ToolSandbox 扩展实验离线分析；仅读取已保存 JSON，不执行来源框架或数据中的代码，不运行 benchmark/轨迹/模型。v1 产物保留不改。

## 规模与身份
- 两组各 207 条轨迹、207 个 dataset-local 场景标识；共享场景键 207 个；payload 832 文件 / 23,150,323 bytes 逐项 bytes/SHA-256 核验通过。
- 运行来源（各组 result_summary.json 保存）：split=test、split_seed=42、split_ratio=0.8；git_sha 分别为 `4f7fffb17fe1fdfd969350b5ab081fcfec130585 + local changes` 与 `75cf0c9bb12a87f60c95fb1407e1ab431869a42f + local changes`——两组运行于不同源码版本且均带 local changes，这是组间比较的额外混杂因素；summary_on 与 graph 开关仍仅见于目录名与来源 README。两组不作为受控因果实验。
- 变体合并仅剥离 H-EPM 后缀（scramble/distraction/all_tools；与 tool_augmentation_list、result_summary 类别逐场景一致），得 109 个基础场景；alt/implicit/low_battery_mode/wifi_off 等官方场景命名 token 不合并。

## 调用与返回关联
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：工具调用条目 1029、tool 结果消息 1029；带 ID 调用 1029、配对 1029、缺返回 0、孤立返回 0、重复调用 ID 条目 0、名称不匹配 0；协议问题 无。
  SANDBOX 交叉核验（execution_context._dbs.SANDBOX 按 openai_tool_call_id）：唯一调用 ID 1029、行数 2058、会话调用全部命中 1029/1029、未命中 0。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：工具调用条目 992、tool 结果消息 992；带 ID 调用 992、配对 992、缺返回 0、孤立返回 0、重复调用 ID 条目 0、名称不匹配 0；协议问题 无。
  SANDBOX 交叉核验（execution_context._dbs.SANDBOX 按 openai_tool_call_id）：唯一调用 ID 992、行数 1984、会话调用全部命中 992/992、未命中 0。

## 工具接口与活动
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：原生身份调用 top：summarize_the_task=207, get_current_timestamp=86, timestamp_to_datetime_info=56, datetime_info_to_timestamp=53, search_reminder=50, search_messages=44, set_wifi_status=44, get_wifi_status=40；scrambled 名调用 120 条（解析：{'database_namespace_activity': 1, 'native_name': 909, 'sandbox_tool_trace': 108, 'unresolved_scrambled': 11}）。
  活动构成（pooled，分母=调用条目）：{'contact': 95, 'datetime': 238, 'harness_summary': 207, 'location': 52, 'messaging': 55, 'reminder': 86, 'settings': 233, 'weather': 15, 'web_api_search': 37}。每轨迹分布区分双分母：条件分布仅覆盖出现该活动的轨迹（如 contact n=49），全体分布含零值（n=207），两组数值见 summary.json。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：原生身份调用 top：summarize_the_task=206, get_current_timestamp=86, search_reminder=47, datetime_info_to_timestamp=42, set_wifi_status=41, search_messages=40, timestamp_to_datetime_info=39, modify_contact=38；scrambled 名调用 108 条（解析：{'database_namespace_activity': 1, 'native_name': 884, 'sandbox_tool_trace': 94, 'unresolved_scrambled': 13}）。
  活动构成（pooled，分母=调用条目）：{'contact': 93, 'datetime': 220, 'harness_summary': 206, 'location': 44, 'messaging': 50, 'reminder': 84, 'settings': 224, 'weather': 19, 'web_api_search': 39}。每轨迹分布区分双分母：条件分布仅覆盖出现该活动的轨迹（如 contact n=48），全体分布含零值（n=207），两组数值见 summary.json。
- 原生工具共 35 个（allow list 并集）；harness 辅助 summarize_the_task 单列，end_conversation 声明可用但从未被 agent 调用。
- 扰动名调用解析：202 条经 SANDBOX 实际 tool_trace（按调用 ID、排除异常行）还原原生身份，其余经 [SummaryTool] 前缀/database_update 命名空间回退或保持 Unknown（24 条）；异常行携带的 69 条陈旧 summarize_the_task 痕迹不作为依据。

## 行为序列
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：每轨迹调用数 median 5.0 / IQR 4.0（n=207）；活动序列异类转换 451 多于同类转换 355，Unknown 边界相邻对 17；单条转换最高：settings->settings=169, datetime->datetime=105, harness_summary->datetime=58, datetime->reminder=54, contact->contact=44。
- H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：每轨迹调用数 median 5.0 / IQR 3.0（n=207）；活动序列异类转换 454 多于同类转换 316，Unknown 边界相邻对 19；单条转换最高：settings->settings=154, datetime->datetime=92, datetime->reminder=50, harness_summary->datetime=49, contact->contact=43。
- 序列仅按保存记录顺序，不代表真实执行顺序或并发关系；未解析活动记为 None 边界，转换不跨越边界。

## 具体行为观察
- 零工具调用轨迹 5 条（类别组合：[('CANONICALIZATION', 'SINGLE_TOOL_CALL', 'SINGLE_USER_TURN', 'THREE_DISTRACTION_TOOLS', 'TOOL_DESCRIPTION_SCRAMBLED'), ('INSUFFICIENT_INFORMATION', 'NO_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'TEN_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'TEN_DISTRACTION_TOOLS'), ('INSUFFICIENT_INFORMATION', 'THREE_DISTRACTION_TOOLS', 'TOOL_NAME_SCRAMBLED')]），多为 INSUFFICIENT_INFORMATION 场景中模型直接向用户澄清。
- summarize_the_task 每轨迹调用分布 {'0': 19, '1': 378, '2': 16, '3': 1}；system prompt 声明必须至少调用一次，但存在 0 次调用的轨迹，未按成功/失败解释。
- 含未解析 scrambled 调用的轨迹 17 条；minefield_similarity>0 的轨迹 35 条；milestone_similarity=1 的轨迹 128 条（仅原始字段计数，不转换为成功）。
- 工具执行错误（结果内容以异常头开始）合计 304 条，与 SANDBOX tool_call_exception 按调用 ID 计数一致；与任务评估字段、harness 异常（exception_type 非空 0 条）分开统计。

## 终止与任务结果
- agent 侧 end_conversation 调用：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': 0, 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': 0}；结果摘要 exception_type/traceback 非空计数：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': [0, 0], 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': [0, 0]}。
- 末态 conversation_active（SANDBOX 最后保存值）：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': {'False': 201, 'True': 6}, 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': {'False': 201, 'True': 6}}；SANDBOX tool_trace 含 end_conversation 执行的轨迹：{'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7': 201, 'H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36': 201}（全部为非 agent 行，即用户模拟器侧）。二者仅按保存值报告，不据此推断正常结束或终止原因。
  - H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7：milestone_similarity median 0.933729570102293（IQR 0.3205184857266423，n=207）；minefield_similarity median 0.0；similarity median 0.89990306819505；turn_count median 13.0。
  - H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36：milestone_similarity median 0.9200093052786817（IQR 0.33333333333333337，n=207）；minefield_similarity median 0.0；similarity median 0.8781023829191136；turn_count median 11.0。
- agent 侧终止状态 unknown：会话内无终止字段；end_conversation 在 allow list 中声明但从未被 agent 调用；末条消息角色分布见 summary.json，不据此猜测正常结束。
- 来源声明规则仅一条（build_graph 的 milestone_similarity > 0.55 过滤），适用边界为工具图构建，不是任务成功定义；本分析未使用该阈值。

## 两组同场景保存指标差异（描述性）
- milestone_similarity：n=207，持平 98，diff（True−False）median 0.0 / IQR 0.003112737388714315。
- minefield_similarity：n=207，持平 200，diff（True−False）median 0.0 / IQR 0.0。
- similarity：n=207，持平 91，diff（True−False）median 0.0 / IQR 0.008170370980035369。
- turn_count：n=207，持平 84，diff（True−False）median 0.0 / IQR 2.0。
- 以上仅为共享场景键上保存字段的描述性差异；两组运行于不同源码版本（git_sha 不同、均带 local changes）、graph 开关仅目录名证据、非独立随机样本，不推断 graph 配置导致成功率、效率或资源变化。

## 相对既有公开行为证据的新增点
- 相比 Coding 的 shell/编辑工具与 OSWorld 的 GUI 动作，本数据提供有证据的 Assistant/工具协作形态：状态化 PIM 工具（reminder/contact/messaging/setting 四个数据库命名空间，写入与声明一致）、时间戳换算工具链（datetime 类调用为最大业务活动之一）、设备设置前置条件（网络关闭时 web 类工具返回 ConnectionError，PermissionError 为最常见工具执行错误）、以及 harness 在 system prompt 中强制要求的状态摘要调用 summarize_the_task。
- 工具名/描述/参数扰动的行为证据：TOOL_NAME_SCRAMBLED 场景中模型实际调用扰动后名称；202 条可经 SANDBOX 保存的实际 tool_trace 按调用 ID 还原原生身份（异常行陈旧痕迹已排除），其余经内容前缀/命名空间回退或保持 Unknown（24 条）。
- 一条 assistant 消息可含多个工具调用（两组共 123 条多调用消息）；消息数不等于调用数。
- 尚缺字段或来源语义：真实执行顺序/并发、任何时间戳、usage/token、agent 侧终止机制、资源与费用；graph 开关仅有目录名证据，且两组源码版本不同。
- 值得后续本地测量的候选线索（仅为研究线索，不构成执行授权）：多调用消息的并行工具执行形态、summarize_the_task 摘要调用的上下文增长、设备设置前置失败后的重试行为。

## v1→v2 修正
- scrambled_resolution: v1 resolved scrambled calls via milestone_matches expected tool_trace names (including 2 matches with milestone_similarity 0); v2 uses the actual tool_trace saved in execution_context._dbs.SANDBOX keyed by call id, excluding rows with tool_call_exception (69 stale summarize_the_task traces on exception rows are not trusted)
- run_provenance: v1 stated run configuration appears only in directory names; v2 records split/split_seed/split_ratio and the per-group result_summary git_sha (different between groups, both with local changes) and marks the source-version difference as a group-comparison confounder
- activity_stats_denominators: v1 activity_calls_per_trajectory_stats covered only trajectories where the activity occurs without saying so; v2 renames it to conditional stats and adds all-trajectories stats including zeros
- delivery_wording: v1 delivery summary said same-tool transitions dominate; cross-activity transitions (858) actually outnumber same-activity transitions (616)

## 限制
- 保存顺序不等于真实执行顺序；无并发证据
- 调用数量不是调用速率、工具耗时或资源消耗
- 不存在 usage/token 字段；不涉及费用或账单
- similarity 字段按原样报告，绝不转换为成功
- 无 SANDBOX tool_trace/内容前缀/数据库证据的 scrambled 调用保持 Unknown
- 末态 conversation_active 与用户侧 end_conversation 仅按保存值报告，不推断正常结束或终止原因
- 两组仅作描述性对照；源码版本不同且 graph 开关仅目录名证据，不作任何因果结论
- 无任何 CPU/内存/I/O 字段；资源测量不支持

[summary.json](summary.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)
