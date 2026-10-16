# 公开轨迹：操作构成与常用工具集

本轮仅离线读取公开数据与已验收分析；不运行轨迹、Agent、工具或模型。比例均注明来源、分母和可识别范围。

## 先看结论

- Coding：终端/shell、文件/代码检索、文件查看、编辑接口，以及命令内的构建/测试共同构成工具集；不能把 bash 都叫作“执行”。
- Computer/Office：这里的公开证据来自 OSWorld 的桌面操作接口与 pyautogui 源码；可描述点击、输入、滚动等，不能从点击自动判断“编辑公式”。
- Assistant：联系人、消息、提醒、设备设置、日期时间、位置/天气/查询等结构化工具；H-EPM 的摘要工具单列为框架辅助。
- AgentX 与 Applied Compute 没有可用于统计具体工具名的完整工具日志；模板名 office_work 不证明使用了某个 Office API。
- VideoWeaver 既有小样没有在本轮升级成完整公开工具语料；视频工具集仍不能从现有公开证据完整汇总。

## Coding：SWE-rebench 全量已登记语料

9,435 条轨迹、598,148 个保存的 tool_call、616,980 个 tool_result；按原生ID只对唯一1:1计关联，不是平均 participant，也不是耗时/CPU占比。

| 操作 | 单一主要用途/组合标签次数 | 占全部保存调用 |
| --- | ---: | ---: |
| 多类操作组合 | 200,103 | 33.454% |
| 文本查看/输出截取 | 161,306 | 26.968% |
| 内容/符号检索 | 58,155 | 9.723% |
| 部分可识别组合 | 55,074 | 9.207% |
| 内容修改/写入 | 42,886 | 7.170% |
| 版本控制/差异检查 | 21,618 | 3.614% |
| 无法识别 | 17,999 | 3.009% |
| 文件/目录定位 | 16,318 | 2.728% |
| 提交/结束 | 8,101 | 1.354% |
| 通用脚本执行（用途未细分） | 6,237 | 1.043% |
| 测试/验证命令 | 3,762 | 0.629% |
| 其他明确操作 | 2,771 | 0.463% |
| 文件管理 | 2,155 | 0.360% |
| 构建/编译 | 793 | 0.133% |
| 环境/依赖准备 | 786 | 0.131% |
| 目录切换/定位 | 84 | 0.014% |

mixed=一个保存调用中包含多类可识别操作；partial=含未识别片段；script_execute只确认解释器执行，不能细说用途。Unknown不排除分母。

### 含某类操作的调用（允许重叠）

一次 `grep ... | head ...` 同时涉及检索和查看。下表每类在同一调用内最多记一次，分母仍为全部调用；类别间不能相加成100%，也不证明条件分支实际执行。

| 保存命令涉及的操作 | 调用数 | 全部调用占比 |
| --- | ---: | ---: |
| 文本查看/输出截取 | 372,786 | 62.323% |
| 目录切换/定位 | 178,504 | 29.843% |
| 内容/符号检索 | 167,761 | 28.047% |
| 内容修改/写入 | 78,567 | 13.135% |
| 无法识别 | 73,073 | 12.217% |
| 文件/目录定位 | 54,400 | 9.095% |
| 测试/验证命令 | 53,790 | 8.993% |
| 其他明确操作 | 50,451 | 8.435% |
| 版本控制/差异检查 | 48,827 | 8.163% |
| 通用脚本执行（用途未细分） | 21,118 | 3.531% |
| 文件管理 | 13,519 | 2.260% |
| 构建/编译 | 11,660 | 1.949% |
| 提交/结束 | 8,590 | 1.436% |
| 环境/依赖准备 | 6,158 | 1.030% |

### 常用原生工具接口

| 接口 | 调用数 | 调用占比 | 出现轨迹 / 全部轨迹 |
| --- | ---: | ---: | ---: |
| `bash_terminal` | 511,104 | 85.45% | 7215 / 9435 |
| `shell` | 16,030 | 2.68% | 1110 / 9435 |
| `Bash` | 15,209 | 2.54% | 555 / 9435 |
| `grep` | 11,850 | 1.98% | 555 / 9435 |
| `read` | 11,575 | 1.94% | 559 / 9435 |
| `edit` | 10,187 | 1.70% | 2040 / 9435 |
| `Read` | 5,575 | 0.93% | 553 / 9435 |
| `Grep` | 5,197 | 0.87% | 540 / 9435 |
| `Edit` | 4,267 | 0.71% | 552 / 9435 |
| `open` | 1,819 | 0.30% | 1339 / 9435 |
| `submit` | 1,392 | 0.23% | 988 / 9435 |
| `glob` | 1,287 | 0.22% | 478 / 9435 |
| `Write` | 504 | 0.08% | 226 / 9435 |
| `replace` | 387 | 0.06% | 253 / 9435 |
| `readLints` | 358 | 0.06% | 356 / 9435 |

其中有 147 条 tool_call 的 tool 字段不是受支持的短接口标识（如包含多行正文或超长内容）；按 `unparsed_tool_identity` 计入未知接口，逐组保留长度与SHA-256，不把该正文当接口名展示。原始事件位置仍可回查。


### 常见命令程序（源码片段口径）

以下是保存命令静态拆分后的程序名频数，不是实际执行次数；&&/||、管道等不证明所有分支都执行。

`cd`=180,025, `grep`=177,180, `head`=151,076, `sed`=134,772, `cat`=80,555, `tail`=74,395, `git`=65,928, `export`=37,108, `ls`=35,140, `echo`=32,081, `cargo`=31,304, `find`=26,605, `go`=22,504, `python`=16,724, `python3`=16,054, `open`=14,938, `npx`=14,043, `edit`=13,432, `rm`=8,940, `replace`=7,615, `submit`=7,199, `mvnw`=6,220, `mvn`=5,366, `xargs`=4,939, `wc`=4,731

### 分组与仓库场景

toolkits.json 保留每个 participant、每个原生 submission、每个代码仓库切片的完整操作/工具计数、调用占比与轨迹出现次数；不合并跨格式分母。

## SWE-bench：本地三轮登记对象

登记对象 19,876 个，覆盖 41 个 submission；互斥文件分流为动作对象 12,509、部分/歧义 6,054、有正面依据的配套产物 1,313。其中部分/歧义对象内有 500 个文件保存 3,065 个过程节点（不是工具调用，且不另加到对象数）；动作单位 422,003。缺失/身份漂移/登记冲突为 0/0/0。

不同协议按来源组保留原生工具与操作分母；SWE-Exp过程节点、Solver retrieval、Moatless transition和shell调用不混成同一种单位。对象并非都是真实执行轨迹。逐组清单见[coverage.md](coverage.md)，逐文件原因见coverage.json。

| submission | 单位类型 | 保存记录数 | 单位总数 | Unknown / Partial |
| --- | --- | ---: | ---: | ---: |
| 20240402_sweagent_claude3opus | saved_action_or_tool_call | 443 | 8343 | 163 / 52 |
| 20240402_sweagent_gpt4 | saved_action_or_tool_call | 496 | 10330 | 70 / 8 |
| 20240612_MASAI_gpt4o | saved_action_or_tool_call | 500 | 23013 | 723 / 63 |
| 20240620_sweagent_claude3.5sonnet | saved_action_or_tool_call | 500 | 16815 | 156 / 87 |
| 20240728_sweagent_gpt4o | saved_action_or_tool_call | 465 | 18075 | 247 / 9 |
| 20240920_solver | saved_operation_event | 500 | 5037 | 43 / 0 |
| 20240920_solver | saved_retrieval_event | 500 | 543 | 0 / 0 |
| 20240924_solver | saved_operation_event | 500 | 5246 | 57 / 0 |
| 20240924_solver | saved_retrieval_event | 500 | 549 | 0 / 0 |
| 20241007_nfactorial | saved_shell_invocation | 478 | 5304 | 35 / 433 |
| 20241028_solver | saved_operation_event | 500 | 6037 | 135 / 0 |
| 20241028_solver | saved_retrieval_event | 500 | 602 | 0 / 0 |
| 20241125_enginelabs | saved_action_or_tool_call | 499 | 8960 | 50 / 37 |
| 20241125_marscode-agent-dev | saved_action_or_tool_call | 500 | 14308 | 8665 / 35 |
| 20241212_epam-ai-run-claude-3-5-sonnet | saved_action_or_tool_call | 500 | 10333 | 4271 / 0 |
| 20250110_learn_by_interact_claude3.5 | saved_action_or_tool_call | 500 | 12410 | 56 / 225 |
| 20250118_codeshellagent_gemini_2.0_flash_experimental | saved_action_or_tool_call | 497 | 5766 | 9 / 24 |
| 20250203_openhands_4x_scaled | saved_action_or_tool_call | 389 | 7482 | 123 / 225 |
| 20250522_tools_claude-4-opus | saved_action_or_tool_call | 500 | 23628 | 1135 / 849 |
| 20250616_Skywork-SWE-32B | saved_action_or_tool_call | 499 | 7226 | 349 / 155 |
| 20250623_warp | saved_shell_invocation | 497 | 10144 | 1017 / 81 |
| 20250806_SWE-Exp_DeepSeek-V3 | saved_process_node | 500 | 0 | 0 / 0 |
| 20251014_Lingxi_kimi_k2 | saved_action_or_tool_call | 500 | 60524 | 336 / 134 |
| 20251103_SalesforceAIResearch_SAGE_OpenHands | saved_tool_call | 499 | 15141 | 294 / 38 |
| lite/20240617_moatless_gpt4o | saved_transition | 300 | 2933 | 0 / 0 |
| lite/20241127_globant_codefixer_agent | saved_tool_call | 300 | 3009 | 627 / 0 |
| test/20251219_sonar-foundation-agent_claude-opus-4-5 | saved_action_or_tool_call | 2147 | 140245 | 586 / 1490 |

### 集中更正与 v2 对照

SAGE的命令协议、SWE-Exp过程节点、MASAI三个子Agent阶段、Learn-by-Interact编辑块、SWE-rebench原生调用关联及Solver返回归属均已按本地记录重算；详见[逐项更正](corrections.md)。例如MASAI v2计 7,409 次，v3计 23,013 次；Learn-by-Interact file_edit由 729 增至 4,135 次。

v1标记5,239个对象已解释、213,183个保存单位；v3相对v1新增7,270个含明确动作的对象、208,820个动作单位。该差值包含读取规则改变，不代表新增下载。

v2绑定的脚本、分类器与测试原始字节及SHA已保存在env/public-trace-operations-v3/source-before-edit/；v1/v2报告和manifest保持原样。历史绑定代码与当前代码的路径/字节差异见summary.json与manifest。

不解析自由文本中的thought、prompt或示例命令作为真实工具调用。Moatless与SWE-Exp保存过程节点不当作工具执行；Solver retrieval也独立列为检索事件。B类不等于“文件没有动作”，C类须有正面配套产物依据。

## Computer/Office：OSWorld

| 模型 | 轨迹 | 原生动作记录 | 静态源码调用节点 |
| --- | ---: | ---: | ---: |
| MiniMax-M3 | 108 | 不适用 | 3241101 |
| claude-opus-4-7 | 108 | 34260 | 39053 |
| claude-sonnet-4-6-max | 108 | 27203 | 27184 |
| claude-sonnet-4-6-medium | 108 | 31190 | 31706 |
| gpt-5.5 | 108 | 16179 | 0 |
| gpt-5.6 | 107 | 34883 | 0 |
| qwen3.7 | 108 | 不适用 | 13128 |

### 各模型保存的常用桌面动作

- MiniMax-M3：原生动作字段不适用；只报告另一层静态源码类别，不填原生动作0%。
- claude-opus-4-7：`left_click` 11,193（32.7%）、`type` 7,403（21.6%）、`key` 7,383（21.5%）、`wait` 3,321（9.7%）、`scroll` 2,123（6.2%）、`triple_click` 710（2.1%）、`double_click` 666（1.9%）、`left_click_drag` 655（1.9%）
- claude-sonnet-4-6-max：`left_click` 9,175（33.7%）、`type` 6,880（25.3%）、`key` 3,864（14.2%）、`scroll` 2,549（9.4%）、`wait` 2,415（8.9%）、`screenshot` 1,090（4.0%）、`triple_click` 428（1.6%）、`double_click` 210（0.8%）
- claude-sonnet-4-6-medium：`left_click` 10,119（32.4%）、`type` 7,888（25.3%）、`key` 5,190（16.6%）、`scroll` 3,099（9.9%）、`wait` 2,697（8.6%）、`screenshot` 919（2.9%）、`triple_click` 505（1.6%）、`double_click` 218（0.7%）
- gpt-5.5：`unknown` 16,179（100.0%）
- gpt-5.6：`unknown` 34,883（100.0%）
- qwen3.7：原生动作字段不适用；只报告另一层静态源码类别，不填原生动作0%。

原生动作保存了点击、键盘输入、滚动、指针移动、截图和等待等接口；静态 command 调用单列，不能与原生动作重复相加，也不证明实际GUI执行次数。
按任务定义声明的应用（浏览器、表格、文档、邮件等）分组的动作构成见toolkits.json。一个任务可涉及多个应用，不把多应用切片强行加成100%。历史任务版本绑定仍unknown。
没有公开DocOps执行轨迹作为本轮分母；不能把本地DocOps的xlsx/ppt/pdf工具名单冒充公开Office工具统计。

## Assistant：H-EPM ToolSandbox

### H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7

207 条轨迹，1029 个Agent调用。

| 活动 | 调用数 | 全部调用占比 |
| --- | ---: | ---: |
| datetime | 238 | 23.13% |
| settings | 233 | 22.64% |
| harness_summary | 207 | 20.12% |
| contact | 95 | 9.23% |
| reminder | 86 | 8.36% |
| messaging | 55 | 5.34% |
| location | 52 | 5.05% |
| web_api_search | 37 | 3.60% |
| weather | 15 | 1.46% |
| unknown | 11 | 1.07% |

常用已解析原生工具：`summarize_the_task`=207, `get_current_timestamp`=86, `timestamp_to_datetime_info`=56, `datetime_info_to_timestamp`=53, `search_reminder`=50, `set_wifi_status`=44, `search_messages`=44, `get_wifi_status`=40, `search_contacts`=38, `modify_contact`=37, `search_location_around_lat_lon`=34, `set_location_service_status`=33

### H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36

207 条轨迹，992 个Agent调用。

| 活动 | 调用数 | 全部调用占比 |
| --- | ---: | ---: |
| settings | 224 | 22.58% |
| datetime | 220 | 22.18% |
| harness_summary | 206 | 20.77% |
| contact | 93 | 9.38% |
| reminder | 84 | 8.47% |
| messaging | 50 | 5.04% |
| location | 44 | 4.44% |
| web_api_search | 39 | 3.93% |
| weather | 19 | 1.92% |
| unknown | 13 | 1.31% |

常用已解析原生工具：`summarize_the_task`=206, `get_current_timestamp`=86, `search_reminder`=47, `datetime_info_to_timestamp`=42, `set_wifi_status`=41, `search_messages`=40, `timestamp_to_datetime_info`=39, `modify_contact`=38, `search_contacts`=35, `get_wifi_status`=33, `set_location_service_status`=32, `shift_timestamp`=30

允许工具清单不等于实际调用；扰动名的身份解析依据既有v2的SANDBOX记录，24条无法分类调用保留Unknown。User结束工具和Agent业务调用不混合。

## 不可提供具体工具集的来源

- AgentX：请求流及显式subagent结构，具体业务工具名/参数未提供。
- Applied Compute：三类派生workload模板，只有轮次、token长度与模拟延迟；没有实际Office API调用。
- VideoWeaver：现有宏观小样/部分解析不能替代完整公开视频工具语料。

## 口径与可复核性

- 主操作比例：每个保存单位一个标签，含mixed/partial/unknown，合计等于该来源分母。
- 文本查看包括cat/read以及管道中的head/tail输出截取，不都代表直接打开源码文件；内容修改/写入也包含生成脚本与其他文件，不冒称全部都是仓库源码修改。
- 组件比例：静态命令片段单独分母，只表示保存源码构成，不是实际执行频率。
- 重定向只辅助识别命令用途：测试日志保存不另算一次工具操作；单条echo/printf/cat输出写入文件另识别为写入。仅对单个闭合、字面量marker及已知消费者的heredoc做静态解析，不执行正文；其他情况Unknown。
- 常用工具同时给调用频数和轨迹出现数，避免少数长轨迹决定全部结论。
- 所有分类都不代表时间或CPU占比；没有新增性能、成功率或因果结论。
- 不执行数据中的代码、AST、shell、工具、evaluator；不读取凭据或访问网络。

## 历史更正

原90条子集中的SWE-agent组，旧summary.md写1053个action，但同包summary.json接口与活动合计均为1064。本轮从该组30份原件重新统计，见summary.json的historical_corrections；旧包不改写。

[场景工具表](toolkits.md) · [逐项更正](corrections.md) · [操作统计CSV](coding_operations.csv) · [summary.json](summary.json) · [toolkits.json](toolkits.json) · [coverage.json](coverage.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)
