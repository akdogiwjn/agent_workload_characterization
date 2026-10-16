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
| SWE-bench / 20240620_sweagent_claude3.5sonnet | 500 | 16815 | `edit` 4,868；495条；`python` 2,681；401条；`open` 2,049；476条；`search_file` 1,415；307条；`goto` 1,379；341条；`find_file` 672；324条；`create` 662；368条；`ls` 460；226条 |
| SWE-bench / 20240728_sweagent_gpt4o | 465 | 18075 | `edit` 8,043；458条；`python` 2,852；415条；`open` 1,380；433条；`create` 784；438条；`search_file` 725；254条；`search_dir` 684；245条；`goto` 613；241条；`cd` 347；70条 |
| SWE-bench / 20241125_enginelabs | 499 | 8960 | `stringReplaceEditor` 4,245；499条；`sendShellInput` 2,737；495条；`searchFile` 719；317条；`searchDirectory` 612；383条；`finish` 499；499条；`findFile` 148；125条 |
| SWE-bench / 20250203_openhands_4x_scaled | 389 | 7482 | `str_replace_editor` 3,920；384条；`execute_bash` 3,562；387条 |
| SWE-bench / lite/20240617_moatless_gpt4o | 300 | 2933 | `PlanToCode` 767；292条；`SearchCode` 632；300条；`IdentifyCode` 629；298条；`EditCode` 478；292条；`Finished` 274；274条；`ClarifyCodeChange` 142；113条；`Rejected` 11；11条 |
| SWE-bench / test/20251219_sonar-foundation-agent_claude-opus-4-5 | 2147 | 140245 | `bash` 101,141；2147条；`str_replace_based_edit_tool` 38,151；2147条；`find_symbols` 953；477条 |
| SWE-rebench / claude-code | 555 | 31200 | `Bash` 15,209；555条；`Read` 5,575；553条；`Grep` 5,197；540条；`Edit` 4,267；552条；`Write` 504；226条；`Monitor` 275；94条；`Glob` 172；135条；`PushNotification` 1；1条 |
| SWE-rebench / codex | 555 | 11262 | `shell` 11,262；555条 |
| SWE-rebench / cursor | 555 | 36436 | `grep` 11,850；555条；`read` 11,569；555条；`edit` 6,259；555条；`shell` 4,768；555条；`glob` 1,287；478条；`readLints` 358；356条；`await` 133；59条；`webFetch` 111；42条 |
| SWE-rebench / deepseek-v4-pro | 555 | 39977 | `bash_terminal` 38,362；555条；`edit` 826；334条；`open` 566；403条；`replace` 150；90条；`goto` 52；46条；`create` 8；8条；`search_file` 3；3条；`submit` 3；3条 |
| SWE-rebench / fable-5 | 555 | 28628 | `bash_terminal` 28,625；555条；`replace` 3；1条 |
| SWE-rebench / glm-5.2 | 555 | 52863 | `bash_terminal` 52,750；555条；`edit` 14；6条；`open` 14；11条；``/`` 3；2条；`<function=get_weather><parameter=city>Paris</parameter></function>` 2；1条；`>\n<function=get_weather>\n<parameter=city>Paris</parameter>\n</function>\n<` 2；1条；`\n"
    "<function=read_file>\n"
    "<parameter=path>/src/main.py</parameter>\n"
    "</function>\n"
    "` 2；1条；`\n",
    "<function=get_weather>\n",
    "<parameter=city>Paris</parameter>\n",
    "<parameter=units>celsius</parameter>\n",
    "</function>\n",
    "` 2；1条 |
| SWE-rebench / gpt-5.6-luna | 555 | 9279 | `bash_terminal` 9,279；555条 |
| SWE-rebench / gpt-5.6-sol | 555 | 10214 | `bash_terminal` 10,214；555条 |
| SWE-rebench / grok-4.5 | 555 | 26293 | `bash_terminal` 26,293；555条 |
| SWE-rebench / junie | 555 | 0 |  |
| SWE-rebench / mimo-v2.5-pro | 555 | 44236 | `bash_terminal` 43,483；555条；`edit` 578；156条；`b_terminal` 76；6条；`replace` 17；10条；`open` 16；14条；`name` 13；3条；`scroll_down` 7；3条；`get_weather` 6；1条 |
| SWE-rebench / minimax-m3 | 555 | 100235 | `bash_terminal` 99,265；555条；`edit` 730；201条；`open` 104；65条；`create` 51；33条；`replace` 43；29条；`submit` 32；31条；`goto` 4；2条；`search_file` 2；2条 |
| SWE-rebench / opus-5 | 555 | 35919 | `bash_terminal` 35,808；555条；`create` 53；36条；`edit` 33；15条；`edit_file` 8；2条；`replace` 6；2条；`submit` 4；1条；`replace_in_file` 3；1条；`open` 2；2条 |
| SWE-rebench / qwen3.5-35b-a3b | 555 | 49191 | `bash_terminal` 48,605；555条；`submit` 369；338条；`open` 96；84条；`edit` 94；60条；`scroll_down` 6；5条；`search_file` 6；6条；`create` 4；4条；`edit 27:27 << 'EOF'

def _contains_merge_conflict_markers(content: str) -` 2；1条 |
| SWE-rebench / qwen3.6-27b | 555 | 41055 | `bash_terminal` 39,607；555条；`open` 694；500条；`edit` 562；219条；`submit` 130；129条；`replace` 37；23条；`create` 13；12条；`scroll_down` 5；4条；`bash` 2；1条 |
| SWE-rebench / qwen3.6-35b-a3b | 555 | 40432 | `bash_terminal` 38,171；555条；`edit` 988；420条；`submit` 848；480条；`open` 248；185条；`replace` 89；57条；`create` 26；22条；`scroll_down` 9；3条；`goto` 7；7条 |
| SWE-rebench / sonnet-5 | 555 | 40928 | `bash_terminal` 40,642；555条；`edit` 103；74条；`open` 79；75条；`bash_terminter` 62；62条；`replace` 39；38条；`bash_terminate` 1；1条；`scroll_down` 1；1条；`submit` 1；1条 |

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
