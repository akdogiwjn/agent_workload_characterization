# 不同场景常用哪些工具

工具名来自保存调用/动作，不把任务中提到的软件名当作已调用API。调用次数和轨迹覆盖分开；以下不是性能或能力排名。

## Coding：工具接口与命令程序两层

| 场景 | 可观察工具/命令 | 分类边界 |
| --- | --- | --- |
| 文件定位 | Glob/glob、find_file、find/ls、rg --files | 定位路径，不与内容检索合并 |
| 内容/符号检索 | Grep/grep、search_file/search_dir、rg、find_symbols、SearchCode | 结构化搜索节点与shell调用分母不同 |
| 文件查看 | Read/read、open、编辑器view、cat/head/sed -n | head也可作为检索命令的输出过滤，组合单列 |
| 修改内容 | Edit/edit、Write、str_replace_based_edit_tool、apply_patch | 文件管理cp/mv等另列 |
| 构建/编译 | make、cmake、编译器、python setup.py build等明确命令头/参数 | 不从thought中出现build一词推断 |
| 测试 | pytest、python -m pytest/unittest、npm test、cargo/go test等 | grep/echo提及pytest不是测试 |
| 环境准备 | pip、uv、conda、npm install等 | 与构建、测试分开 |

上表是有限分类规则对应的工具族，不声称每个来源都调用了全部工具；下表给实际出现的原生接口。

| 来源/组 | 保存记录数 | 保存单位数 | 实际高频接口（次数；出现记录数） |
| --- | ---: | ---: | --- |
| SWE-bench / 20240402_sweagent_claude3opus | 443 | 8343 | `edit` 2,622；432条；`python` 1,263；354条；`open` 927；412条；`search_file` 527；231条；`goto` 504；240条；`create` 490；357条；`search_dir` 313；184条；`exit_cost` 249；249条 |
| SWE-bench / 20240402_sweagent_gpt4 | 496 | 10330 | `edit` 3,664；489条；`python` 1,259；399条；`open` 963；468条；`scroll_down` 743；185条；`goto` 682；274条；`create` 585；421条；`search_file` 582；241条；`find_file` 453；288条 |
| SWE-bench / 20240612_MASAI_gpt4o | 500 | 23013 | `READ` 6,681；500条；`COMMAND` 5,984；500条；`WRITE` 3,413；500条；`LIST` 2,882；500条；`DONE` 2,021；499条；`EDIT` 1,878；475条；`ADD` 154；46条 |
| SWE-bench / 20240620_sweagent_claude3.5sonnet | 500 | 16815 | `edit` 4,868；495条；`python` 2,681；401条；`open` 2,049；476条；`search_file` 1,415；307条；`goto` 1,379；341条；`find_file` 672；324条；`create` 662；368条；`ls` 460；226条 |
| SWE-bench / 20240728_sweagent_gpt4o | 465 | 18075 | `edit` 8,043；458条；`python` 2,852；415条；`open` 1,380；433条；`create` 784；438条；`search_file` 725；254条；`search_dir` 684；245条；`goto` 613；241条；`cd` 347；70条 |
| SWE-bench / 20240920_solver | 500 | 5037 | `edit` 2,241；499条；`execution` 1,991；434条；`submit` 485；477条；`create` 233；206条；`revert` 87；72条 |
| SWE-bench / 20240920_solver | 500 | 543 | `retrieval` 543；500条 |
| SWE-bench / 20240924_solver | 500 | 5246 | `edit` 2,459；499条；`execution` 2,007；424条；`submit` 482；476条；`create` 233；207条；`revert` 65；61条 |
| SWE-bench / 20240924_solver | 500 | 549 | `retrieval` 549；500条 |
| SWE-bench / 20241007_nfactorial | 478 | 5304 | `logged_shell_script` 5,304；478条 |
| SWE-bench / 20241028_solver | 500 | 6037 | `open` 2,287；500条；`edit` 1,571；495条；`execution` 1,152；382条；`submit` 499；493条；`create` 358；294条；`revert` 170；162条 |
| SWE-bench / 20241028_solver | 500 | 602 | `retrieval` 602；500条 |
| SWE-bench / 20241125_enginelabs | 499 | 8960 | `stringReplaceEditor` 4,245；499条；`sendShellInput` 2,737；495条；`searchFile` 719；317条；`searchDirectory` 612；383条；`finish` 499；499条；`findFile` 148；125条 |
| SWE-bench / 20241125_marscode-agent-dev | 500 | 14308 | `shell_action` 11,170；500条；`patch_action` 3,138；498条 |
| SWE-bench / 20241212_epam-ai-run-claude-3-5-sonnet | 500 | 10333 | `str_replace_editor` 6,062；500条；`run_command_line_tool` 4,271；500条 |
| SWE-bench / 20250110_learn_by_interact_claude3.5 | 500 | 12410 | `execute_bash` 5,056；500条；`file_edit` 4,135；500条；`execute_ipython` 3,219；500条 |
| SWE-bench / 20250118_codeshellagent_gemini_2.0_flash_experimental | 497 | 5766 | `execute_ipython` 4,090；497条；`execute_bash` 1,676；425条 |
| SWE-bench / 20250203_openhands_4x_scaled | 389 | 7482 | `str_replace_editor` 3,920；384条；`execute_bash` 3,562；387条 |
| SWE-bench / 20250522_tools_claude-4-opus | 500 | 23628 | `bash` 13,209；500条；`str_replace_based_edit_tool` 10,419；500条 |
| SWE-bench / 20250616_Skywork-SWE-32B | 499 | 7226 | `str_replace_editor` 3,709；495条；`execute_bash` 3,309；489条；`think` 208；178条 |
| SWE-bench / 20250623_warp | 497 | 10144 | `RequestCommandOutput` 10,144；497条 |
| SWE-bench / 20250806_SWE-Exp_DeepSeek-V3 | 500 | 0 |  |
| SWE-bench / 20251014_Lingxi_kimi_k2 | 500 | 60524 | `view_file_content` 17,520；499条；`search_files_by_keywords` 15,204；500条；`str_replace_editor` 12,491；490条；`bash` 9,299；484条；`view_directory` 2,901；499条；`think` 2,819；499条；`smart_str_replace_editor` 157；8条；`ask_repository_agent` 74；35条 |
| SWE-bench / 20251103_SalesforceAIResearch_SAGE_OpenHands | 499 | 15141 | `bash` 15,141；499条 |
| SWE-bench / lite/20240617_moatless_gpt4o | 300 | 2933 | `PlanToCode` 767；292条；`SearchCode` 632；300条；`IdentifyCode` 629；298条；`EditCode` 478；292条；`Finished` 274；274条；`ClarifyCodeChange` 142；113条；`Rejected` 11；11条 |
| SWE-bench / lite/20241127_globant_codefixer_agent | 300 | 3009 | `apply_diff_change` 1,022；299条；`read_file` 555；263条；`search_file` 494；239条；`search_codebase` 421；225条；`detect_language_and_get_dependencies` 300；299条；`search_methods_in_file` 91；57条；`get_related_files` 84；82条；`search_code_in_file` 42；33条 |
| SWE-bench / test/20251219_sonar-foundation-agent_claude-opus-4-5 | 2147 | 140245 | `bash` 101,141；2147条；`str_replace_based_edit_tool` 38,151；2147条；`find_symbols` 953；477条 |
| SWE-rebench / claude-code | 555 | 31200 | `Bash` 15,209；555条；`Read` 5,575；553条；`Grep` 5,197；540条；`Edit` 4,267；552条；`Write` 504；226条；`Monitor` 275；94条；`Glob` 172；135条；`PushNotification` 1；1条 |
| SWE-rebench / codex | 555 | 11262 | `shell` 11,262；555条 |
| SWE-rebench / cursor | 555 | 36436 | `grep` 11,850；555条；`read` 11,569；555条；`edit` 6,259；555条；`shell` 4,768；555条；`glob` 1,287；478条；`readLints` 358；356条；`await` 133；59条；`webFetch` 111；42条 |
| SWE-rebench / deepseek-v4-pro | 555 | 39977 | `bash_terminal` 38,362；555条；`edit` 826；334条；`open` 566；403条；`replace` 150；90条；`goto` 52；46条；`create` 8；8条；`search_file` 3；3条；`submit` 3；3条 |
| SWE-rebench / fable-5 | 555 | 28628 | `bash_terminal` 28,625；555条；`replace` 3；1条 |
| SWE-rebench / glm-5.2 | 555 | 52863 | `bash_terminal` 52,750；555条；`unparsed_tool_identity` 84；7条；`edit` 14；6条；`open` 14；11条；`replace` 1；1条 |
| SWE-rebench / gpt-5.6-luna | 555 | 9279 | `bash_terminal` 9,279；555条 |
| SWE-rebench / gpt-5.6-sol | 555 | 10214 | `bash_terminal` 10,214；555条 |
| SWE-rebench / grok-4.5 | 555 | 26293 | `bash_terminal` 26,293；555条 |
| SWE-rebench / junie | 555 | 0 |  |
| SWE-rebench / mimo-v2.5-pro | 555 | 44236 | `bash_terminal` 43,483；555条；`edit` 578；156条；`b_terminal` 76；6条；`replace` 17；10条；`open` 16；14条；`name` 13；3条；`unparsed_tool_identity` 8；7条；`scroll_down` 7；3条 |
| SWE-rebench / minimax-m3 | 555 | 100235 | `bash_terminal` 99,265；555条；`edit` 730；201条；`open` 104；65条；`create` 51；33条；`replace` 43；29条；`submit` 32；31条；`goto` 4；2条；`search_file` 2；2条 |
| SWE-rebench / opus-5 | 555 | 35919 | `bash_terminal` 35,808；555条；`create` 53；36条；`edit` 33；15条；`edit_file` 8；2条；`replace` 6；2条；`submit` 4；1条；`replace_in_file` 3；1条；`open` 2；2条 |
| SWE-rebench / qwen3.5-35b-a3b | 555 | 49191 | `bash_terminal` 48,605；555条；`submit` 369；338条；`open` 96；84条；`edit` 94；60条；`unparsed_tool_identity` 7；3条；`scroll_down` 6；5条；`search_file` 6；6条；`create` 4；4条 |
| SWE-rebench / qwen3.6-27b | 555 | 41055 | `bash_terminal` 39,607；555条；`open` 694；500条；`edit` 562；219条；`submit` 130；129条；`replace` 37；23条；`create` 13；12条；`scroll_down` 5；4条；`bash` 2；1条 |
| SWE-rebench / qwen3.6-35b-a3b | 555 | 40432 | `bash_terminal` 38,171；555条；`edit` 988；420条；`submit` 848；480条；`open` 248；185条；`replace` 89；57条；`unparsed_tool_identity` 45；19条；`create` 26；22条；`scroll_down` 9；3条 |
| SWE-rebench / sonnet-5 | 555 | 40928 | `bash_terminal` 40,642；555条；`edit` 103；74条；`open` 79；75条；`bash_terminter` 62；62条；`replace` 39；38条；`bash_terminate` 1；1条；`scroll_down` 1；1条；`submit` 1；1条 |

### Coding各来源组的互斥操作构成与命令程序

主标签每个保存单位恰好一个；命令程序为静态拆分的程序名，另用组件分母，不能解释为运行次数。没有命令参数的结构化接口不会被强行映射成shell程序。

| 来源/组 | 单位/分母 | 常见主操作（次数；占本组单位） | 常见原生接口 | 常见命令程序（静态组件次数） | 参数可用性（结构化/命令） |
| --- | --- | --- | --- | --- | --- |
| SWE-bench / 20240402_sweagent_claude3opus / saved_action_or_tool_call | 443 / 8,343 | 内容修改/写入 3,121（37.4%）；文本查看/输出截取 1,469（17.6%）；通用脚本执行（用途未细分） 1,224（14.7%）；内容/符号检索 859（10.3%） | `edit` 2,622；`python` 1,263；`open` 927；`search_file` 527；`goto` 504 | `python` 1,333；`exit_cost` 249；`cd` 228；`find` 207；`rm` 120 | 0/8,343；命令 8,343/8,343 |
| SWE-bench / 20240402_sweagent_gpt4 / saved_action_or_tool_call | 496 / 10,330 | 内容修改/写入 4,250（41.1%）；文本查看/输出截取 2,509（24.3%）；通用脚本执行（用途未细分） 1,252（12.1%）；内容/符号检索 969（9.4%） | `edit` 3,664；`python` 1,259；`open` 963；`scroll_down` 743；`goto` 682 | `python` 1,260；`rm` 178；`exit_cost` 156；`echo` 40；`ls` 39 | 0/10,330；命令 10,330/10,330 |
| SWE-bench / 20240612_MASAI_gpt4o / saved_action_or_tool_call | 500 / 23,013 | 文本查看/输出截取 6,702（29.1%）；内容修改/写入 5,461（23.7%）；测试/验证命令 3,833（16.7%）；文件/目录定位 2,897（12.6%） | `READ` 6,681；`COMMAND` 5,984；`WRITE` 3,413；`LIST` 2,882；`DONE` 2,021 | `python` 3,176；`pytest` 1,332；`cd` 418；`grep` 321；`runtests.py` 295 | 23,013/23,013；命令 0/23,013 |
| SWE-bench / 20240620_sweagent_claude3.5sonnet / saved_action_or_tool_call | 500 / 16,815 | 内容修改/写入 5,773（34.3%）；文本查看/输出截取 3,717（22.1%）；通用脚本执行（用途未细分） 1,996（11.9%）；内容/符号检索 1,599（9.5%） | `edit` 4,868；`python` 2,681；`open` 2,049；`search_file` 1,415；`goto` 1,379 | `python` 2,757；`ls` 506；`find` 448；`cat` 365；`grep` 305 | 0/16,815；命令 16,815/16,815 |
| SWE-bench / 20240728_sweagent_gpt4o / saved_action_or_tool_call | 465 / 18,075 | 内容修改/写入 8,833（48.9%）；通用脚本执行（用途未细分） 2,652（14.7%）；文本查看/输出截取 2,220（12.3%）；内容/符号检索 1,583（8.8%） | `edit` 8,043；`python` 2,852；`open` 1,380；`create` 784；`search_file` 725 | `python` 3,125；`ls` 422；`cd` 367；`rm` 242；`exit_cost` 226 | 0/18,075；命令 18,075/18,075 |
| SWE-bench / 20240920_solver / saved_operation_event | 500 / 5,037 | 内容修改/写入 2,474（49.1%）；测试/验证命令 1,179（23.4%）；通用脚本执行（用途未细分） 769（15.3%）；提交/结束 485（9.6%） | `edit` 2,241；`execution` 1,991；`submit` 485；`create` 233；`revert` 87 | `python` 1,948 | 2,476/5,037；命令 0/5,037 |
| SWE-bench / 20240920_solver / saved_retrieval_event | 500 / 543 | 内容/符号检索 543（100.0%） | `retrieval` 543 | 无命令组件 | 543/543；命令 0/543 |
| SWE-bench / 20240924_solver / saved_operation_event | 500 / 5,246 | 内容修改/写入 2,692（51.3%）；测试/验证命令 1,159（22.1%）；通用脚本执行（用途未细分） 791（15.1%）；提交/结束 482（9.2%） | `edit` 2,459；`execution` 2,007；`submit` 482；`create` 233；`revert` 65 | `python` 1,950 | 2,489/5,246；命令 0/5,246 |
| SWE-bench / 20240924_solver / saved_retrieval_event | 500 / 549 | 内容/符号检索 549（100.0%） | `retrieval` 549 | 无命令组件 | 549/549；命令 0/549 |
| SWE-bench / 20241007_nfactorial / saved_shell_invocation | 478 / 5,304 | 多类操作组合 4,332（81.7%）；环境/依赖准备 504（9.5%）；部分可识别组合 433（8.2%）；无法识别 35（0.7%） | `logged_shell_script` 5,304 | `conda` 5,269；`source` 5,269；`bash` 2,396；`python` 1,845；`cd` 470 | 5,304/5,304；命令 5,304/5,304 |
| SWE-bench / 20241028_solver / saved_operation_event | 500 / 6,037 | 文本查看/输出截取 2,287（37.9%）；内容修改/写入 1,929（32.0%）；通用脚本执行（用途未细分） 567（9.4%）；提交/结束 499（8.3%） | `open` 2,287；`edit` 1,571；`execution` 1,152；`submit` 499；`create` 358 | `python` 1,017；`-m` 34；`test_colormap.py` 2；`test_expr.py` 2；`test_method_dim.py` 2 | 3,938/6,037；命令 0/6,037 |
| SWE-bench / 20241028_solver / saved_retrieval_event | 500 / 602 | 内容/符号检索 602（100.0%） | `retrieval` 602 | 无命令组件 | 602/602；命令 0/602 |
| SWE-bench / 20241125_enginelabs / saved_action_or_tool_call | 499 / 8,960 | 内容修改/写入 2,711（30.3%）；通用脚本执行（用途未细分） 1,909（21.3%）；文本查看/输出截取 1,550（17.3%）；内容/符号检索 1,454（16.2%） | `stringReplaceEditor` 4,245；`sendShellInput` 2,737；`searchFile` 719；`searchDirectory` 612；`finish` 499 | `python` 1,927；`cd` 713；`pip` 290；`python3` 138；`grep` 129 | 8,960/8,960；命令 2,737/8,960 |
| SWE-bench / 20241125_marscode-agent-dev / saved_action_or_tool_call | 500 / 14,308 | 无法识别 8,665（60.6%）；内容修改/写入 3,138（21.9%）；通用脚本执行（用途未细分） 2,118（14.8%）；文件/目录定位 245（1.7%） | `shell_action` 11,170；`patch_action` 3,138 | `review_file` 3,104；`python3` 2,141；`search_class_in_project` 1,606；`search_function_in_project` 1,522；`search_file_in_project` 1,039 | 14,308/14,308；命令 11,170/14,308 |
| SWE-bench / 20241212_epam-ai-run-claude-3-5-sonnet / saved_action_or_tool_call | 500 / 10,333 | 无法识别 4,271（41.3%）；内容修改/写入 3,507（33.9%）；文本查看/输出截取 2,555（24.7%） | `str_replace_editor` 6,062；`run_command_line_tool` 4,271 | 无命令组件 | 10,333/10,333；命令 0/10,333 |
| SWE-bench / 20250110_learn_by_interact_claude3.5 / saved_action_or_tool_call | 500 / 12,410 | 通用脚本执行（用途未细分） 6,496（52.3%）；内容修改/写入 4,142（33.4%）；文件/目录定位 660（5.3%）；多类操作组合 565（4.6%） | `execute_bash` 5,056；`file_edit` 4,135；`execute_ipython` 3,219 | `cd` 4,312；`python3` 3,070；`python` 776；`ls` 720；`pip` 442 | 12,410/12,410；命令 8,275/12,410 |
| SWE-bench / 20250118_codeshellagent_gemini_2.0_flash_experimental / saved_action_or_tool_call | 497 / 5,766 | 通用脚本执行（用途未细分） 4,942（85.7%）；文件/目录定位 452（7.8%）；内容/符号检索 228（4.0%）；文件管理 36（0.6%） | `execute_ipython` 4,090；`execute_bash` 1,676 | `python` 855；`ls` 427；`grep` 242；`find` 49；`python3` 33 | 5,766/5,766；命令 5,766/5,766 |
| SWE-bench / 20250203_openhands_4x_scaled / saved_action_or_tool_call | 389 / 7,482 | 内容修改/写入 2,559（34.2%）；通用脚本执行（用途未细分） 1,519（20.3%）；文本查看/输出截取 1,445（19.3%）；内容/符号检索 647（8.6%） | `str_replace_editor` 3,920；`execute_bash` 3,562 | `cd` 2,086；`python` 1,146；`grep` 757；`python3` 644；`find` 368 | 7,482/7,482；命令 3,561/7,482 |
| SWE-bench / 20250522_tools_claude-4-opus / saved_action_or_tool_call | 500 / 23,628 | 内容修改/写入 6,324（26.8%）；通用脚本执行（用途未细分） 5,053（21.4%）；文本查看/输出截取 4,147（17.6%）；内容/符号检索 2,150（9.1%） | `bash` 13,209；`str_replace_based_edit_tool` 10,419 | `cd` 11,129；`python` 7,028；`grep` 5,552；`head` 1,986；`find` 1,161 | 23,628/23,628；命令 23,596/23,628 |
| SWE-bench / 20250616_Skywork-SWE-32B / saved_action_or_tool_call | 499 / 7,226 | 内容修改/写入 1,909（26.4%）；文本查看/输出截取 1,868（25.9%）；内容/符号检索 863（11.9%）；通用脚本执行（用途未细分） 827（11.4%） | `str_replace_editor` 3,709；`execute_bash` 3,309；`think` 208 | `cd` 1,176；`grep` 1,156；`python` 986；`find` 408；`ls` 290 | 7,226/7,226；命令 7,018/7,226 |
| SWE-bench / 20250623_warp / saved_shell_invocation | 497 / 10,144 | 测试/验证命令 3,450（34.0%）；通用脚本执行（用途未细分） 2,901（28.6%）；文件/目录定位 1,324（13.1%）；无法识别 1,017（10.0%） | `RequestCommandOutput` 10,144 | `cd` 6,870；`python` 6,316；`ls` 1,086；`find` 1,011；`head` 734 | 10,144/10,144；命令 10,144/10,144 |
| SWE-bench / 20250806_SWE-Exp_DeepSeek-V3 / saved_process_node | 500 / 0 | 保存过程节点 3,065（非工具调用） | 非工具单位 | 无命令组件 | 0/0；命令 0/0 |
| SWE-bench / 20251014_Lingxi_kimi_k2 / saved_action_or_tool_call | 500 / 60,524 | 文本查看/输出截取 17,606（29.1%）；内容/符号检索 15,708（26.0%）；内容修改/写入 12,515（20.7%）；通用脚本执行（用途未细分） 6,224（10.3%） | `view_file_content` 17,520；`search_files_by_keywords` 15,204；`str_replace_editor` 12,491；`bash` 9,299；`view_directory` 2,901 | `python` 7,733；`cd` 5,651；`grep` 678；`find` 366；`head` 241 | 57,092/60,524；命令 9,263/60,524 |
| SWE-bench / 20251103_SalesforceAIResearch_SAGE_OpenHands / saved_tool_call | 499 / 15,141 | 多类操作组合 4,899（32.4%）；文本查看/输出截取 4,405（29.1%）；通用脚本执行（用途未细分） 1,826（12.1%）；测试/验证命令 1,761（11.6%） | `bash` 15,141 | `sed` 7,879；`grep` 4,754；`git` 3,002；`python` 2,835；`ls` 1,174 | 15,141/15,141；命令 15,141/15,141 |
| SWE-bench / lite/20240617_moatless_gpt4o / saved_transition | 300 / 2,933 | 规划 909（31.0%）；内容/符号检索 632（21.5%）；文本查看/输出截取 629（21.4%）；内容修改/写入 478（16.3%） | `PlanToCode` 767；`SearchCode` 632；`IdentifyCode` 629；`EditCode` 478；`Finished` 274 | 无命令组件 | 0/2,933；命令 0/2,933 |
| SWE-bench / lite/20241127_globant_codefixer_agent / saved_tool_call | 300 / 3,009 | 内容修改/写入 1,022（34.0%）；无法识别 627（20.8%）；文本查看/输出截取 555（18.4%）；内容/符号检索 421（14.0%） | `apply_diff_change` 1,022；`read_file` 555；`search_file` 494；`search_codebase` 421；`detect_language_and_get_dependencies` 300 | 无命令组件 | 1,987/3,009；命令 0/3,009 |
| SWE-bench / test/20251219_sonar-foundation-agent_claude-opus-4-5 / saved_action_or_tool_call | 2147 / 140,245 | 多类操作组合 36,568（26.1%）；文本查看/输出截取 35,145（25.1%）；通用脚本执行（用途未细分） 27,510（19.6%）；内容/符号检索 12,993（9.3%） | `bash` 101,141；`str_replace_based_edit_tool` 38,151；`find_symbols` 953 | `cd` 83,525；`python` 53,803；`grep` 25,705；`git` 21,777；`head` 15,167 | 140,238/140,245；命令 101,046/140,245 |
| SWE-rebench / claude-code / saved_tool_call | 555 / 31,200 | 多类操作组合 6,762（21.7%）；文本查看/输出截取 6,728（21.6%）；内容/符号检索 5,554（17.8%）；内容修改/写入 4,805（15.4%） | `Bash` 15,209；`Read` 5,575；`Grep` 5,197；`Edit` 4,267；`Write` 504 | `grep` 5,669；`head` 5,210；`tail` 4,944；`git` 2,353；`ls` 2,337 | 31,200/31,200；命令 15,209/31,200 |
| SWE-rebench / codex / saved_tool_call | 555 / 11,262 | 多类操作组合 5,067（45.0%）；部分可识别组合 1,981（17.6%）；文本查看/输出截取 1,179（10.5%）；无法识别 1,087（9.7%） | `shell` 11,262 | `sed` 10,834；`grep` 5,724；`git` 5,243；`head` 4,997；`find` 1,968 | 11,262/11,262；命令 11,262/11,262 |
| SWE-rebench / cursor / saved_tool_call | 555 / 36,436 | 内容/符号检索 11,854（32.5%）；文本查看/输出截取 11,575（31.8%）；内容修改/写入 6,313（17.3%）；多类操作组合 1,963（5.4%） | `grep` 11,850；`read` 11,569；`edit` 6,259；`shell` 4,768；`glob` 1,287 | `cd` 4,292；`tail` 1,813；`cargo` 1,181；`git` 1,008；`go` 610 | 36,436/36,436；命令 4,768/36,436 |
| SWE-rebench / deepseek-v4-pro / saved_tool_call | 555 / 39,977 | 文本查看/输出截取 14,314（35.8%）；多类操作组合 8,386（21.0%）；内容/符号检索 5,287（13.2%）；内容修改/写入 3,803（9.5%） | `bash_terminal` 38,362；`edit` 826；`open` 566；`replace` 150；`goto` 52 | `cd` 11,264；`grep` 9,508；`sed` 6,880；`cat` 5,601；`head` 4,534 | 39,977/39,977；命令 38,359/39,977 |
| SWE-rebench / fable-5 / saved_tool_call | 555 / 28,628 | 多类操作组合 12,450（43.5%）；文本查看/输出截取 5,669（19.8%）；部分可识别组合 4,007（14.0%）；内容修改/写入 2,422（8.5%） | `bash_terminal` 28,625；`replace` 3 | `grep` 14,209；`head` 10,472；`sed` 6,991；`tail` 5,244；`cd` 5,107 | 28,628/28,628；命令 28,625/28,628 |
| SWE-rebench / glm-5.2 / saved_tool_call | 555 / 52,863 | 多类操作组合 22,417（42.4%）；文本查看/输出截取 14,834（28.1%）；部分可识别组合 5,490（10.4%）；内容/符号检索 3,245（6.1%） | `bash_terminal` 52,750；`unparsed_tool_identity` 84；`edit` 14；`open` 14；`replace` 1 | `cd` 34,776；`grep` 19,968；`head` 16,080；`sed` 12,837；`echo` 9,538 | 52,863/52,863；命令 52,718/52,863 |
| SWE-rebench / gpt-5.6-luna / saved_tool_call | 555 / 9,279 | 多类操作组合 6,003（64.7%）；部分可识别组合 1,719（18.5%）；文本查看/输出截取 630（6.8%）；无法识别 429（4.6%） | `bash_terminal` 9,279 | `sed` 7,363；`git` 5,908；`grep` 5,803；`head` 5,168；`tail` 1,219 | 9,279/9,279；命令 9,279/9,279 |
| SWE-rebench / gpt-5.6-sol / saved_tool_call | 555 / 10,214 | 多类操作组合 4,809（47.1%）；部分可识别组合 2,790（27.3%）；无法识别 1,399（13.7%）；提交/结束 460（4.5%） | `bash_terminal` 10,214 | `sed` 8,167；`git` 5,978；`grep` 5,565；`head` 4,740；`printf` 2,037 | 10,214/10,214；命令 10,214/10,214 |
| SWE-rebench / grok-4.5 / saved_tool_call | 555 / 26,293 | 多类操作组合 12,694（48.3%）；文本查看/输出截取 4,656（17.7%）；内容修改/写入 3,652（13.9%）；部分可识别组合 2,436（9.3%） | `bash_terminal` 26,293 | `head` 17,000；`grep` 12,261；`open` 5,355；`ls` 5,186；`echo` 5,170 | 26,293/26,293；命令 26,293/26,293 |
| SWE-rebench / junie / saved_tool_call | 555 / 0 | 无可分类保存单位 | 无接口名 | 无命令组件 | 0/0；命令 0/0 |
| SWE-rebench / mimo-v2.5-pro / saved_tool_call | 555 / 44,236 | 文本查看/输出截取 14,321（32.4%）；多类操作组合 12,569（28.4%）；内容/符号检索 5,187（11.7%）；内容修改/写入 3,586（8.1%） | `bash_terminal` 43,483；`edit` 578；`b_terminal` 76；`replace` 17；`open` 16 | `cd` 12,230；`grep` 11,968；`head` 8,251；`sed` 6,794；`cat` 6,607 | 44,236/44,236；命令 43,472/44,236 |
| SWE-rebench / minimax-m3 / saved_tool_call | 555 / 100,235 | 多类操作组合 40,604（40.5%）；文本查看/输出截取 27,630（27.6%）；部分可识别组合 10,493（10.5%）；内容/符号检索 5,364（5.4%） | `bash_terminal` 99,265；`edit` 730；`open` 104；`create` 51；`replace` 43 | `cd` 31,240；`head` 31,020；`grep` 27,470；`sed` 19,467；`cat` 19,042 | 100,235/100,235；命令 99,265/100,235 |
| SWE-rebench / opus-5 / saved_tool_call | 555 / 35,919 | 多类操作组合 16,452（45.8%）；文本查看/输出截取 7,149（19.9%）；部分可识别组合 5,509（15.3%）；无法识别 2,010（5.6%） | `bash_terminal` 35,808；`create` 53；`edit` 33；`edit_file` 8；`replace` 6 | `cd` 24,992；`grep` 14,705；`head` 12,806；`sed` 9,849；`tail` 6,241 | 35,919/35,919；命令 35,808/35,919 |
| SWE-rebench / qwen3.5-35b-a3b / saved_tool_call | 555 / 49,191 | 文本查看/输出截取 16,896（34.3%）；多类操作组合 12,349（25.1%）；内容/符号检索 5,389（11.0%）；内容修改/写入 3,751（7.6%） | `bash_terminal` 48,605；`submit` 369；`open` 96；`edit` 94；`unparsed_tool_identity` 7 | `sed` 13,390；`grep` 10,904；`cd` 9,522；`head` 8,371；`cat` 7,006 | 49,191/49,191；命令 48,605/49,191 |
| SWE-rebench / qwen3.6-27b / saved_tool_call | 555 / 41,055 | 文本查看/输出截取 13,241（32.3%）；多类操作组合 11,424（27.8%）；内容/符号检索 4,232（10.3%）；内容修改/写入 3,078（7.5%） | `bash_terminal` 39,607；`open` 694；`edit` 562；`submit` 130；`replace` 37 | `cd` 12,788；`grep` 9,356；`sed` 8,970；`cat` 8,371；`head` 7,140 | 41,055/41,055；命令 39,608/41,055 |
| SWE-rebench / qwen3.6-35b-a3b / saved_tool_call | 555 / 40,432 | 文本查看/输出截取 13,282（32.9%）；多类操作组合 10,895（26.9%）；内容/符号检索 3,760（9.3%）；内容修改/写入 3,053（7.6%） | `bash_terminal` 38,171；`edit` 988；`submit` 848；`open` 248；`replace` 89 | `cd` 11,975；`sed` 9,690；`grep` 8,486；`cat` 7,314；`head` 7,002 | 40,432/40,432；命令 38,171/40,432 |
| SWE-rebench / sonnet-5 / saved_tool_call | 555 / 40,928 | 多类操作组合 15,259（37.3%）；文本查看/输出截取 8,800（21.5%）；内容/符号检索 5,310（13.0%）；部分可识别组合 4,814（11.8%） | `bash_terminal` 40,642；`edit` 103；`open` 79；`bash_terminter` 62；`replace` 39 | `cd` 19,335；`grep` 15,214；`sed` 8,504；`head` 7,715；`tail` 7,481 | 40,928/40,928；命令 40,642/40,928 |

### MASAI 子Agent动作（明确 Model response 段）

submission 合计 23,013 个动作单位；返回块 19,569 个，无原生ID，未按顺序配对。

| 子Agent | 动作数 | 主操作构成 | 原生动作标签 |
| --- | ---: | --- | --- |
| Search Agent | 7,381 | 文本查看/输出截取 2,969 (40.2%)；内容修改/写入 2,057 (27.9%)；提交/结束 1,232 (16.7%)；文件/目录定位 576 (7.8%)；内容/符号检索 263 (3.6%)；测试/验证命令 150 (2.0%)；多类操作组合 52 (0.7%)；通用脚本执行（用途未细分） 29 (0.4%)；其他明确操作 22 (0.3%)；无法识别 15 (0.2%)；版本控制/差异检查 7 (0.1%)；环境/依赖准备 6 (0.1%)；部分可识别组合 3 (0.0%) | `READ`=2,960；`EDIT`=1,878；`DONE`=1,232；`COMMAND`=575；`LIST`=573；`ADD`=154；`WRITE`=9 |
| Template Generation Agent | 7,409 | 文本查看/输出截取 2,041 (27.5%)；测试/验证命令 1,769 (23.9%)；文件/目录定位 1,455 (19.6%)；内容修改/写入 922 (12.4%)；提交/结束 491 (6.6%)；无法识别 321 (4.3%)；通用脚本执行（用途未细分） 248 (3.3%)；部分可识别组合 56 (0.8%)；环境/依赖准备 45 (0.6%)；文件管理 28 (0.4%)；构建/编译 17 (0.2%)；多类操作组合 10 (0.1%)；内容/符号检索 5 (0.1%)；其他明确操作 1 (0.0%) | `COMMAND`=2,506；`READ`=2,039；`LIST`=1,451；`WRITE`=922；`DONE`=491 |
| Test Case Reproducer Agent | 8,223 | 内容修改/写入 2,482 (30.2%)；测试/验证命令 1,914 (23.3%)；文本查看/输出截取 1,692 (20.6%)；文件/目录定位 866 (10.5%)；无法识别 387 (4.7%)；通用脚本执行（用途未细分） 361 (4.4%)；提交/结束 298 (3.6%)；环境/依赖准备 90 (1.1%)；多类操作组合 48 (0.6%)；内容/符号检索 45 (0.5%)；文件管理 24 (0.3%)；版本控制/差异检查 6 (0.1%)；部分可识别组合 4 (0.0%)；构建/编译 4 (0.0%)；其他明确操作 1 (0.0%)；目录切换/定位 1 (0.0%) | `COMMAND`=2,903；`WRITE`=2,482；`READ`=1,682；`LIST`=858；`DONE`=298 |

MASAI 输入prompt和响应段外的标签不计作调用；动作返回独立保存，未按相邻顺序强配。
各代码仓库切片的同类统计在toolkits.json的coding.repository_scenarios；这是仓库来源切片，不是独立随机任务类别。

## Computer/Office：桌面操作，不是文档API日志

OSWorld保存接口以computer/computer_call/tool_use原生动作、以及pyautogui命令源码呈现。两者不能相加。

| 保存接口层 | 常见动作 | 能说明什么 |
| --- | --- | --- |
| 原生桌面动作 | left_click/double_click、key/type/hotkey、scroll、mouse_move/drag、screenshot、wait | 已保存的动作接口分布 |
| command静态源码 | pyautogui点击、按键、输入、滚动、移动；sleep等等待源码 | 静态可识别调用，不是实际GUI执行次数 |

### 按任务声明应用分组

同一任务可以涉及多个应用，因此以下场景重叠；应用来自当前下载的任务定义，与历史轨迹版本对应仍unknown。动作不自动归因给该应用。

| 任务声明应用 | 涉及模型×任务记录 | 原生动作中高频保存名 |
| --- | ---: | --- |
| 3d-slicer | 14 | `unknown`=687；`type`=323；`left_click`=168；`key`=162；`wait`=135 |
| blender | 7 | `unknown`=399；`left_click`=386；`type`=196；`key`=192；`wait`=107 |
| browser | 7 | `unknown`=1,062；`left_click`=665；`scroll`=292；`wait`=131；`type`=75 |
| calc | 7 | `unknown`=413；`left_click`=165；`type`=152；`key`=84；`scroll`=71 |
| calendar | 28 | `unknown`=1,873；`left_click`=1,490；`type`=454；`key`=260；`scroll`=203 |
| careerlink | 7 | `unknown`=917；`left_click`=576；`type`=340；`wait`=163；`scroll`=161 |
| chrome | 343 | `unknown`=23,914；`left_click`=16,161；`type`=9,711；`key`=7,163；`scroll`=4,108 |
| cloudcrm | 7 | `left_click`=943；`unknown`=754；`scroll`=201；`key`=132；`wait`=66 |
| evince | 7 | `left_click`=513；`unknown`=283；`type`=145；`scroll`=137；`key`=83 |
| excel | 21 | `unknown`=613；`left_click`=546；`type`=352；`key`=276；`wait`=131 |
| file-manager | 14 | `unknown`=687；`type`=323；`left_click`=168；`key`=162；`wait`=135 |
| file_manager | 28 | `unknown`=1,861；`left_click`=1,750；`type`=513；`key`=472；`scroll`=395 |
| firefox | 7 | `unknown`=1,049；`key`=506；`type`=302；`left_click`=282；`wait`=72 |
| freecad | 14 | `unknown`=530；`left_click`=339；`type`=226；`key`=209；`scroll`=119 |
| geogebra | 7 | `unknown`=321；`type`=141；`left_click`=123；`key`=89；`scroll`=37 |
| gimp | 35 | `left_click`=1,340；`unknown`=1,116；`type`=624；`key`=528；`wait`=341 |
| google-chrome | 7 | `unknown`=470；`left_click`=391；`type`=225；`key`=152；`scroll`=139 |
| image_viewer | 14 | `unknown`=878；`left_click`=620；`key`=214；`type`=201；`scroll`=142 |
| kicad | 14 | `unknown`=1,035；`type`=697；`key`=468；`left_click`=441；`scroll`=150 |
| labplot | 7 | `unknown`=683；`left_click`=322；`type`=254；`key`=232；`wait`=118 |
| libero | 7 | `unknown`=675；`type`=462；`scroll`=331；`wait`=274；`key`=250 |
| libreoffice | 7 | `unknown`=936；`left_click`=426；`type`=264；`key`=237；`wait`=51 |
| libreoffice_calc | 14 | `unknown`=1,391；`left_click`=508；`type`=491；`key`=284；`wait`=248 |
| libreoffice_impress | 28 | `unknown`=1,952；`left_click`=1,300；`key`=769；`type`=692；`wait`=256 |
| libreoffice_writer | 35 | `unknown`=2,586；`left_click`=1,236；`type`=714；`key`=511；`scroll`=277 |
| logisim | 7 | `unknown`=333；`type`=328；`left_click`=195；`key`=163；`wait`=72 |
| mailhub | 42 | `unknown`=2,690；`left_click`=1,590；`type`=791；`wait`=396；`scroll`=378 |
| mpv | 7 | `unknown`=1,029；`left_click`=475；`key`=360；`type`=299；`wait`=175 |
| musescore | 14 | `unknown`=1,879；`type`=470；`key`=249；`left_click`=196；`wait`=148 |
| nautilus | 7 | `left_click`=513；`unknown`=283；`type`=145；`scroll`=137；`key`=83 |
| obsidian | 7 | `unknown`=610；`left_click`=335；`type`=254；`key`=188；`wait`=101 |
| openboard | 7 | `unknown`=549；`left_click`=248；`key`=166；`type`=129；`wait`=29 |
| pdf_viewer | 21 | `unknown`=1,213；`left_click`=661；`type`=480；`key`=441；`scroll`=236 |
| pdfviewer | 7 | `unknown`=413；`left_click`=165；`type`=152；`key`=84；`scroll`=71 |
| reaper | 21 | `unknown`=1,610；`type`=797；`left_click`=687；`wait`=378；`key`=329 |
| shotcut | 42 | `unknown`=2,111；`left_click`=1,987；`type`=1,485；`key`=1,201；`wait`=660 |
| solvespace | 7 | `unknown`=1,029；`left_click`=475；`key`=360；`type`=299；`wait`=175 |
| studio.streamview | 7 | `unknown`=321；`type`=239；`key`=211；`left_click`=178；`wait`=162 |
| teamchat | 21 | `left_click`=1,558；`unknown`=1,496；`type`=415；`scroll`=372；`wait`=271 |
| terminal | 21 | `unknown`=1,188；`type`=806；`key`=690；`left_click`=683；`wait`=307 |
| thunderbird | 21 | `unknown`=1,629；`left_click`=822；`type`=543；`key`=407；`scroll`=135 |
| unknown | 76 | `unknown`=6,455；`left_click`=3,582；`type`=3,122；`key`=1,776；`wait`=1,154 |
| vaultbank | 7 | `unknown`=492；`left_click`=440；`type`=185；`wait`=161；`scroll`=83 |
| vs_code | 28 | `unknown`=1,349；`type`=733；`key`=597；`left_click`=472；`scroll`=210 |
| vscode | 56 | `unknown`=4,336；`type`=2,578；`left_click`=2,354；`key`=1,829；`scroll`=1,091 |
| wps | 91 | `unknown`=6,382；`type`=3,176；`left_click`=2,906；`key`=2,771；`wait`=1,017 |
| writer | 7 | `unknown`=413；`left_click`=165；`type`=152；`key`=84；`scroll`=71 |
| zotero | 35 | `unknown`=3,018；`left_click`=1,582；`type`=1,563；`key`=1,089；`wait`=616 |

具体模型下的应用切片、动作比例在toolkits.json；MiniMax-M3/Qwen的原生字段不适用，不填成0。
未找到公开DocOps执行轨迹，不能据此列出openpyxl/python-docx等库的公开调用占比；本地DocOps测量在另一个证据集合，不混入本轮。

## Assistant：状态化个人助理工具

| 来源组 | 活动 | 保存调用数（全部调用占比） | 已还原原生身份中实际调用的工具 |
| --- | --- | ---: | --- |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | datetime | 238（23.13%） | `get_current_timestamp`=86；`timestamp_to_datetime_info`=56；`datetime_info_to_timestamp`=53；`shift_timestamp`=24；`timestamp_diff`=18；`seconds_to_hours_minutes_seconds`=1 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | settings | 233（22.64%） | `set_wifi_status`=44；`get_wifi_status`=40；`set_location_service_status`=33；`set_low_battery_mode_status`=30；`get_location_service_status`=28；`get_low_battery_mode_status`=26；`get_cellular_service_status`=17；`set_cellular_service_status`=15 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | harness_summary | 207（20.12%） | `summarize_the_task`=207 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | contact | 95（9.23%） | `search_contacts`=38；`modify_contact`=37；`remove_contact`=15；`add_contact`=4 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | reminder | 86（8.36%） | `search_reminder`=50；`add_reminder`=27；`modify_reminder`=6；`remove_reminder`=3 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | messaging | 55（5.34%） | `search_messages`=44；`send_message_with_phone_number`=11 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | location | 52（5.05%） | `search_location_around_lat_lon`=34；`get_current_location`=11；`search_lat_lon`=4；`calculate_lat_lon_distance`=3 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | web_api_search | 37（3.60%） | `search_holiday`=25；`search_stock`=7；`convert_currency`=5 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | weather | 15（1.46%） | `search_weather_around_lat_lon`=15 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7 | unknown | 11（1.07%） | 身份未完全还原，保留Unknown/活动级证据 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | settings | 224（22.58%） | `set_wifi_status`=41；`get_wifi_status`=33；`set_location_service_status`=32；`get_low_battery_mode_status`=30；`get_location_service_status`=27；`set_low_battery_mode_status`=27；`set_cellular_service_status`=18；`get_cellular_service_status`=16 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | datetime | 220（22.18%） | `get_current_timestamp`=86；`datetime_info_to_timestamp`=42；`timestamp_to_datetime_info`=39；`shift_timestamp`=30；`timestamp_diff`=23 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | harness_summary | 206（20.77%） | `summarize_the_task`=206 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | contact | 93（9.38%） | `modify_contact`=38；`search_contacts`=35；`remove_contact`=16；`add_contact`=3 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | reminder | 84（8.47%） | `search_reminder`=47；`add_reminder`=28；`modify_reminder`=7；`remove_reminder`=2 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | messaging | 50（5.04%） | `search_messages`=40；`send_message_with_phone_number`=10 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | location | 44（4.44%） | `search_location_around_lat_lon`=24；`get_current_location`=11；`search_lat_lon`=6；`calculate_lat_lon_distance`=3 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | web_api_search | 39（3.93%） | `search_holiday`=26；`search_stock`=8；`convert_currency`=5 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | weather | 19（1.92%） | `search_weather_around_lat_lon`=19 |
| H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36 | unknown | 13（1.31%） | 身份未完全还原，保留Unknown/活动级证据 |

联系人、提醒、消息、设备状态、日期时间、位置/天气与网络查询分开。summarize_the_task属于H-EPM框架辅助，不与业务工具混称；allow-list中可用不代表实际调用。

## 宏观模板与视频

- AgentX：可分析请求与subagent结构，缺具体业务工具名，工具集无法从该语料恢复。
- Applied Compute：agentic_coding/code_qa/office_work是派生模板类别，不是工具名或真实Office执行日志。
- Video：当前VideoWeaver旧样本为宏观/部分解析；不在这里用推测的FFmpeg或生成工具名填补公开视频工具集。

[操作占比与限制](summary.md) · [完整机器可读工具集](toolkits.json) · [覆盖清单](coverage.json)
