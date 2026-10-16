# 场景—软件与工具栈（公开轨迹及本地实验）

本报告按证据层分表，不把接口名、软件名、声明应用和实现库混合成一个排行榜。静态命令组件只证明文本记录中出现了命令头；OSWorld任务应用是任务声明；DocOps库只有在具体接口被调用且运行源码绑定后才记为本批实现使用。

## 范围与口径

- Coding公开语料：复用 PUBLIC-TRACE-OPERATIONS-v3 的 23,944 条逐轨迹分析行和 41 个来源/提交组；其中 39 组出现本轮识别名单内的程序名，其余不等于无工具。另对本地P1-12批 9 个run、3个任务重读已登记trajectory，独立分表。程序频数是静态命令头/组件出现次数，另列调用覆盖。
- Computer/Office：OSWorld 108 个任务定义投影到 755 条 model×task 记录（不是独立任务数）；声明应用不等于运行应用。
- Assistant：H-EPM 2 个来源版本组分别报告；本地 ToolSandbox Assistant Repeat-01 为 9 次固定任务运行、3个任务设计。模拟API不映射为真实产品。
- DocOps：仅使用已验收 Repeat-02 的9次运行、3个固定任务。库版本未由所选报告确认。

## Coding：保存命令组件

表中以组为单位保留原始程序名、静态组件频数和轨迹出现数。轨迹出现数按同一轨迹去重；组件频数可能在一个调用中重复。返回/成功无法从聚合命令头表逐项关联，以下不称实际成功执行。

| 来源/提交（participant） | task覆盖分母 | 轨迹分母 | 保存记录分母 | 已识别组件数 | 常见程序组件（频数；轨迹数） |
|---|---:|---:|---:|---:|---|
| SWE-bench / `20240402_sweagent_claude3opus` | 443 | 443 | 8343 | 1953 | `python` [command_head] 1,333（354/443轨迹）; `find` [command_head] 207（117/443轨迹）; `ls` [command_head] 86（65/443轨迹）; `django-admin` [command_head] 57（39/443轨迹）; `pytest` [command_head] 51（16/443轨迹）; `sphinx-build` [command_head] 39（18/443轨迹）; `make` [command_head] 28（13/443轨迹）; `unittest` [explicit_python_module] 26（10/443轨迹） |
| SWE-bench / `20240402_sweagent_gpt4` | 496 | 496 | 10330 | 1374 | `python` [command_head] 1,260（399/496轨迹）; `ls` [command_head] 39（25/496轨迹）; `pytest` [command_head] 27（8/496轨迹）; `cat` [command_head] 16（8/496轨迹）; `pytest` [explicit_python_module] 9（4/496轨迹）; `find` [command_head] 8（5/496轨迹）; `grep` [command_head] 5（4/496轨迹）; `sphinx-build` [command_head] 3（3/496轨迹） |
| SWE-bench / `20240612_MASAI_gpt4o` | 500 | 500 | 23013 | 5326 | `python` [command_head] 3,176（308/500轨迹）; `pytest` [command_head] 1,332（262/500轨迹）; `grep` [command_head] 321（155/500轨迹）; `tox` [command_head] 220（60/500轨迹）; `pip` [command_head] 102（69/500轨迹）; `django-admin` [command_head] 64（35/500轨迹）; `bash` [shell_entry] 26（7/500轨迹）; `cat` [command_head] 23（19/500轨迹） |
| SWE-bench / `20240620_sweagent_claude3.5sonnet` | 500 | 500 | 16815 | 5140 | `python` [command_head] 2,757（402/500轨迹）; `ls` [command_head] 506（228/500轨迹）; `find` [command_head] 448（211/500轨迹）; `cat` [command_head] 365（79/500轨迹）; `grep` [command_head] 305（158/500轨迹）; `pytest` [command_head] 214（41/500轨迹）; `pip` [command_head] 112（27/500轨迹）; `sed` [command_head] 92（44/500轨迹） |
| SWE-bench / `20240728_sweagent_gpt4o` | 465 | 465 | 18075 | 4578 | `python` [command_head] 3,125（416/465轨迹）; `ls` [command_head] 422（139/465轨迹）; `unittest` [explicit_python_module] 287（42/465轨迹）; `grep` [command_head] 175（25/465轨迹）; `find` [command_head] 95（47/465轨迹）; `sphinx-build` [command_head] 93（14/465轨迹）; `django-admin` [command_head] 74（17/465轨迹）; `make` [command_head] 73（16/465轨迹） |
| SWE-bench / `20240920_solver` | 500 | 500 | 543 | 1948 | `python` [command_head] 1,948（432/500轨迹） |
| SWE-bench / `20240924_solver` | 500 | 500 | 549 | 1950 | `python` [command_head] 1,950（420/500轨迹） |
| SWE-bench / `20241007_nfactorial` | 478 | 478 | 5304 | 10508 | `conda` [command_head] 5,269（478/478轨迹）; `bash` [shell_entry] 2,396（347/478轨迹）; `python` [command_head] 1,845（478/478轨迹）; `cat` [command_head] 431（355/478轨迹）; `django-admin` [command_head] 198（119/478轨迹）; `sphinx-build` [command_head] 82（23/478轨迹）; `make` [command_head] 54（21/478轨迹）; `grep` [command_head] 53（28/478轨迹） |
| SWE-bench / `20241028_solver` | 500 | 500 | 602 | 1017 | `python` [command_head] 1,017（296/500轨迹） |
| SWE-bench / `20241125_enginelabs` | 499 | 499 | 8960 | 2629 | `python` [command_head] 1,927（459/499轨迹）; `pip` [command_head] 290（110/499轨迹）; `python3` [command_head] 138（35/499轨迹）; `grep` [command_head] 129（75/499轨迹）; `pytest` [explicit_python_module] 27（11/499轨迹）; `sphinx-build` [command_head] 27（12/499轨迹）; `find` [command_head] 20（5/499轨迹）; `conda` [command_head] 14（10/499轨迹） |
| SWE-bench / `20241125_marscode-agent-dev` | 500 | 500 | 14308 | 2525 | `python3` [command_head] 2,141（371/500轨迹）; `ls` [command_head] 245（114/500轨迹）; `grep` [command_head] 45（11/500轨迹）; `pip` [command_head] 35（19/500轨迹）; `cat` [command_head] 22（8/500轨迹）; `find` [command_head] 11（6/500轨迹）; `pytest` [explicit_python_module] 7（1/500轨迹）; `head` [command_head] 6（4/500轨迹） |
| SWE-bench / `20241212_epam-ai-run-claude-3-5-sonnet` | 500 | 500 | 10333 | 0 | 无已识别软件名 |
| SWE-bench / `20250110_learn_by_interact_claude3.5` | 500 | 500 | 12410 | 6113 | `python3` [command_head] 3,070（403/500轨迹）; `python` [command_head] 776（100/500轨迹）; `ls` [command_head] 720（477/500轨迹）; `pip` [command_head] 442（210/500轨迹）; `cat` [command_head] 285（31/500轨迹）; `grep` [command_head] 239（63/500轨迹）; `sphinx-build` [command_head] 158（10/500轨迹）; `find` [command_head] 104（85/500轨迹） |
| SWE-bench / `20250118_codeshellagent_gemini_2.0_flash_experimental` | 497 | 497 | 5766 | 1685 | `python` [command_head] 855（258/497轨迹）; `ls` [command_head] 427（240/497轨迹）; `grep` [command_head] 242（101/497轨迹）; `find` [command_head] 49（32/497轨迹）; `python3` [command_head] 33（13/497轨迹）; `pytest` [explicit_python_module] 27（6/497轨迹）; `cat` [command_head] 17（8/497轨迹）; `xargs` [command_head] 10（8/497轨迹） |
| SWE-bench / `20250203_openhands_4x_scaled` | 389 | 389 | 7482 | 3786 | `python` [command_head] 1,146（232/389轨迹）; `grep` [command_head] 757（316/389轨迹）; `python3` [command_head] 644（130/389轨迹）; `find` [command_head] 368（211/389轨迹）; `ls` [command_head] 345（295/389轨迹）; `pip` [command_head] 141（89/389轨迹）; `pytest` [explicit_python_module] 135（54/389轨迹）; `xargs` [command_head] 49（33/389轨迹） |
| SWE-bench / `20250522_tools_claude-4-opus` | 500 | 500 | 23628 | 18353 | `python` [command_head] 7,028（500/500轨迹）; `grep` [command_head] 5,552（500/500轨迹）; `head` [command_head] 1,986（464/500轨迹）; `pytest` [explicit_python_module] 1,529（494/500轨迹）; `find` [command_head] 1,161（500/500轨迹）; `sort` [command_head] 251（233/500轨迹）; `tail` [command_head] 229（121/500轨迹）; `xargs` [command_head] 193（127/500轨迹） |
| SWE-bench / `20250616_Skywork-SWE-32B` | 499 | 499 | 7226 | 3818 | `grep` [command_head] 1,156（341/499轨迹）; `python` [command_head] 986（237/499轨迹）; `find` [command_head] 408（248/499轨迹）; `ls` [command_head] 290（157/499轨迹）; `python3` [command_head] 288（55/499轨迹）; `pytest` [command_head] 113（55/499轨迹）; `git` [command_head] 112（45/499轨迹）; `xargs` [command_head] 105（79/499轨迹） |
| SWE-bench / `20250623_warp` | 497 | 497 | 10144 | 11687 | `python` [command_head] 6,316（477/497轨迹）; `pytest` [explicit_python_module] 1,628（481/497轨迹）; `ls` [command_head] 1,086（419/497轨迹）; `find` [command_head] 1,011（417/497轨迹）; `head` [command_head] 734（363/497轨迹）; `grep` [command_head] 474（260/497轨迹）; `python3` [command_head] 175（32/497轨迹）; `git` [command_head] 79（25/497轨迹） |
| SWE-bench / `20250806_SWE-Exp_DeepSeek-V3` | 500 | 500 | 0 | 0 | 无已识别软件名 |
| SWE-bench / `20251014_Lingxi_kimi_k2` | 500 | 500 | 60524 | 10735 | `python` [command_head] 7,733（478/500轨迹）; `pytest` [explicit_python_module] 1,152（377/500轨迹）; `grep` [command_head] 678（205/500轨迹）; `find` [command_head] 366（165/500轨迹）; `head` [command_head] 241（121/500轨迹）; `ls` [command_head] 199（76/500轨迹）; `python3` [command_head] 109（14/500轨迹）; `sed` [command_head] 90（22/500轨迹） |
| SWE-bench / `20251103_SalesforceAIResearch_SAGE_OpenHands` | 499 | 499 | 15141 | 22219 | `sed` [command_head] 7,879（493/499轨迹）; `grep` [command_head] 4,754（494/499轨迹）; `git` [command_head] 3,002（492/499轨迹）; `python` [command_head] 2,835（470/499轨迹）; `ls` [command_head] 1,174（499/499轨迹）; `pytest` [command_head] 1,046（393/499轨迹）; `head` [command_head] 712（193/499轨迹）; `cat` [command_head] 257（87/499轨迹） |
| SWE-bench / `lite/20240617_moatless_gpt4o` | 300 | 300 | 2933 | 0 | 无已识别软件名 |
| SWE-bench / `lite/20241127_globant_codefixer_agent` | 300 | 300 | 3009 | 0 | 无已识别软件名 |
| SWE-bench / `test/20251219_sonar-foundation-agent_claude-opus-4-5` | 2147 | 2147 | 140245 | 157699 | `python` [command_head] 53,803（2085/2147轨迹）; `grep` [command_head] 25,705（2113/2147轨迹）; `git` [command_head] 21,777（2147/2147轨迹）; `head` [command_head] 15,167（2125/2147轨迹）; `pytest` [explicit_python_module] 13,471（2082/2147轨迹）; `tail` [command_head] 13,363（2030/2147轨迹）; `cat` [command_head] 6,276（1934/2147轨迹）; `python3` [command_head] 3,593（237/2147轨迹） |
| SWE-rebench / `claude-code` | 111 | 555 | 31200 | 31824 | `grep` [command_head] 5,669（507/555轨迹）; `head` [command_head] 5,210（518/555轨迹）; `tail` [command_head] 4,944（554/555轨迹）; `git` [command_head] 2,353（456/555轨迹）; `ls` [command_head] 2,337（485/555轨迹）; `cargo` [command_head] 1,741（125/555轨迹）; `sed` [command_head] 1,140（244/555轨迹）; `go` [command_head] 1,074（108/555轨迹） |
| SWE-rebench / `codex` | 111 | 555 | 11262 | 36502 | `sed` [command_head] 10,834（555/555轨迹）; `grep` [command_head] 5,724（541/555轨迹）; `git` [command_head] 5,243（555/555轨迹）; `head` [command_head] 4,997（544/555轨迹）; `find` [command_head] 1,968（523/555轨迹）; `cargo` [command_head] 1,168（125/555轨迹）; `pnpm` [command_head] 779（80/555轨迹）; `rg` [command_head] 771（553/555轨迹） |
| SWE-rebench / `cursor` | 111 | 555 | 36436 | 8542 | `tail` [command_head] 1,813（355/555轨迹）; `cargo` [command_head] 1,181（125/555轨迹）; `git` [command_head] 1,008（193/555轨迹）; `go` [command_head] 610（105/555轨迹）; `head` [command_head] 570（214/555轨迹）; `pnpm` [command_head] 551（72/555轨迹）; `grep` [command_head] 370（92/555轨迹）; `uv` [command_head] 324（56/555轨迹） |
| SWE-rebench / `deepseek-v4-pro` | 111 | 555 | 39977 | 44433 | `grep` [command_head] 9,508（551/555轨迹）; `sed` [command_head] 6,880（445/555轨迹）; `cat` [command_head] 5,601（526/555轨迹）; `head` [command_head] 4,534（538/555轨迹）; `tail` [command_head] 3,438（514/555轨迹）; `git` [command_head] 2,425（551/555轨迹）; `find` [command_head] 1,689（494/555轨迹）; `cargo` [command_head] 1,560（125/555轨迹） |
| SWE-rebench / `fable-5` | 111 | 555 | 28628 | 57189 | `grep` [command_head] 14,209（553/555轨迹）; `head` [command_head] 10,472（555/555轨迹）; `sed` [command_head] 6,991（549/555轨迹）; `tail` [command_head] 5,244（554/555轨迹）; `git` [command_head] 3,817（553/555轨迹）; `ls` [command_head] 3,033（542/555轨迹）; `cat` [command_head] 2,233（529/555轨迹）; `cargo` [command_head] 2,017（125/555轨迹） |
| SWE-rebench / `glm-5.2` | 111 | 555 | 52863 | 93563 | `grep` [command_head] 19,968（555/555轨迹）; `head` [command_head] 16,080（555/555轨迹）; `sed` [command_head] 12,837（553/555轨迹）; `tail` [command_head] 8,592（555/555轨迹）; `cat` [command_head] 8,082（555/555轨迹）; `git` [command_head] 5,054（555/555轨迹）; `ls` [command_head] 3,497（542/555轨迹）; `find` [command_head] 2,812（503/555轨迹） |
| SWE-rebench / `gpt-5.6-luna` | 111 | 555 | 9279 | 33057 | `sed` [command_head] 7,363（555/555轨迹）; `git` [command_head] 5,908（555/555轨迹）; `grep` [command_head] 5,803（555/555轨迹）; `head` [command_head] 5,168（554/555轨迹）; `tail` [command_head] 1,219（377/555轨迹）; `python3` [command_head] 805（450/555轨迹）; `cargo` [command_head] 797（123/555轨迹）; `cat` [command_head] 768（362/555轨迹） |
| SWE-rebench / `gpt-5.6-sol` | 111 | 555 | 10214 | 35815 | `sed` [command_head] 8,167（555/555轨迹）; `git` [command_head] 5,978（555/555轨迹）; `grep` [command_head] 5,565（555/555轨迹）; `head` [command_head] 4,740（550/555轨迹）; `cat` [command_head] 1,316（454/555轨迹）; `cargo` [command_head] 1,274（125/555轨迹）; `find` [command_head] 1,135（477/555轨迹）; `python3` [command_head] 774（419/555轨迹） |
| SWE-rebench / `grok-4.5` | 111 | 555 | 26293 | 59886 | `head` [command_head] 17,000（555/555轨迹）; `grep` [command_head] 12,261（555/555轨迹）; `ls` [command_head] 5,186（555/555轨迹）; `cat` [command_head] 4,505（532/555轨迹）; `git` [command_head] 4,466（552/555轨迹）; `sed` [command_head] 3,842（389/555轨迹）; `tail` [command_head] 3,592（543/555轨迹）; `find` [command_head] 1,472（504/555轨迹） |
| SWE-rebench / `junie` | 111 | 555 | 0 | 0 | 无已识别软件名 |
| SWE-rebench / `mimo-v2.5-pro` | 111 | 555 | 44236 | 56595 | `grep` [command_head] 11,968（553/555轨迹）; `head` [command_head] 8,251（555/555轨迹）; `sed` [command_head] 6,794（450/555轨迹）; `cat` [command_head] 6,607（534/555轨迹）; `tail` [command_head] 5,147（537/555轨迹）; `find` [command_head] 2,737（554/555轨迹）; `git` [command_head] 2,368（552/555轨迹）; `cargo` [command_head] 2,015（125/555轨迹） |
| SWE-rebench / `minimax-m3` | 111 | 555 | 100235 | 159110 | `head` [command_head] 31,020（555/555轨迹）; `grep` [command_head] 27,470（555/555轨迹）; `sed` [command_head] 19,467（537/555轨迹）; `cat` [command_head] 19,042（555/555轨迹）; `tail` [command_head] 14,478（552/555轨迹）; `git` [command_head] 8,906（555/555轨迹）; `ls` [command_head] 6,395（555/555轨迹）; `cargo` [command_head] 5,284（125/555轨迹） |
| SWE-rebench / `opus-5` | 111 | 555 | 35919 | 72833 | `grep` [command_head] 14,705（555/555轨迹）; `head` [command_head] 12,806（555/555轨迹）; `sed` [command_head] 9,849（554/555轨迹）; `tail` [command_head] 6,241（555/555轨迹）; `git` [command_head] 4,864（555/555轨迹）; `cat` [command_head] 4,417（545/555轨迹）; `ls` [command_head] 4,094（541/555轨迹）; `cargo` [command_head] 2,786（125/555轨迹） |
| SWE-rebench / `qwen3.5-35b-a3b` | 111 | 555 | 49191 | 62409 | `sed` [command_head] 13,390（538/555轨迹）; `grep` [command_head] 10,904（552/555轨迹）; `head` [command_head] 8,371（554/555轨迹）; `cat` [command_head] 7,006（554/555轨迹）; `tail` [command_head] 4,285（512/555轨迹）; `git` [command_head] 3,006（532/555轨迹）; `cargo` [command_head] 2,065（121/555轨迹）; `ls` [command_head] 2,025（508/555轨迹） |
| SWE-rebench / `qwen3.6-27b` | 111 | 555 | 41055 | 53497 | `grep` [command_head] 9,356（548/555轨迹）; `sed` [command_head] 8,970（521/555轨迹）; `cat` [command_head] 8,371（552/555轨迹）; `head` [command_head] 7,140（555/555轨迹）; `tail` [command_head] 3,596（518/555轨迹）; `git` [command_head] 2,312（529/555轨迹）; `find` [command_head] 2,265（555/555轨迹）; `cargo` [command_head] 1,764（124/555轨迹） |
| SWE-rebench / `qwen3.6-35b-a3b` | 111 | 555 | 40432 | 51554 | `sed` [command_head] 9,690（526/555轨迹）; `grep` [command_head] 8,486（548/555轨迹）; `cat` [command_head] 7,314（554/555轨迹）; `head` [command_head] 7,002（555/555轨迹）; `tail` [command_head] 3,442（516/555轨迹）; `git` [command_head] 2,431（539/555轨迹）; `find` [command_head] 2,146（549/555轨迹）; `cargo` [command_head] 1,620（123/555轨迹） |
| SWE-rebench / `sonnet-5` | 111 | 555 | 40928 | 66578 | `grep` [command_head] 15,214（555/555轨迹）; `sed` [command_head] 8,504（552/555轨迹）; `head` [command_head] 7,715（554/555轨迹）; `tail` [command_head] 7,481（555/555轨迹）; `git` [command_head] 5,789（555/555轨迹）; `cat` [command_head] 4,049（544/555轨迹）; `find` [command_head] 2,696（488/555轨迹）; `python3` [command_head] 2,199（444/555轨迹） |

软件组件的用途按程序身份/保存的操作分类保守解释：grep/rg为检索；find/ls/tree为定位或目录浏览；cat/head/tail等为查看/截取；Git为版本控制；pytest/Vitest等是明确测试运行器；Python/Node/Java通常仅能确认解释器入口；Maven/Gradle/Cargo/Go等聚合计数没有保留子命令时，不细分 build 与 test。`npm test`只有脚本内容被绑定时才能归到具体测试框架。本表不把Shell内建、参数碎片、`python`目标脚本名或 grep 参数中的词汇当软件。

## Local Coding：固定本地重复批次

对P1-12-CODING-REPEAT-01已验收manifest显式选择的9个run、3个任务做静态命令身份提取；按task分开，三个run是同任务重复。调用ID与tool返回仅按唯一原生ID配对。总bash逻辑调用及返回核验：{"call_ids_missing": 0, "calls": 348, "calls_with_unparsed_arguments": 0, "calls_without_unique_return": 5, "duplicate_call_ids": 0, "duplicate_return_ids": 0, "orphan_return_records": 0, "return_ids_missing": 0, "returns": 343, "returns_without_unique_call": 0, "unique_id_pairs": 343}。下表组件数是命令文本静态拆分，不等同进程启动次数；每项另列组件出现数和保存调用涉及数。

| 固定任务 | task数/3 | run数/3 | Bash调用分母 | 常见软件组件（静态出现；涉及调用/run） |
|---|---:|---:|---:|---|
| `astropy__astropy-13236` | 1 | 3 | 134 | 无已识别软件名 |
| `astropy__astropy-13398` | 1 | 3 | 133 | 无已识别软件名 |
| `django__django-16485` | 1 | 3 | 81 | 无已识别软件名 |

## Computer/Office：OSWorld任务声明应用

以下由 `related_apps` 与 `snapshot` 的原始标识按任务去重；model×task数是同一声明投影到保存轨迹记录后的覆盖，不是启动次数。原始ID未丢弃；泛化/组合/环境标记在机器表中保留为未映射或歧义，不能据此声称产品启动。

| 原始任务应用标识 | 规范显示/家族（仅可确认者） | 任务数/108 | model×task记录数/755 | 证据层 |
|---|---|---:|---:|---|
| `chrome` | Chrome / 浏览器 | 52 | 364 | task declaration (related_apps, snapshot) |
| `wps` | WPS（组件未指定） / WPS | 13 | 91 | task declaration (related_apps, snapshot) |
| `ubuntu` | unknown（保留原始标签） / unknown | 11 | 77 | task declaration (snapshot) |
| `base_setup` | unknown（保留原始标签） / unknown | 8 | 56 | task declaration (snapshot) |
| `vscode` | Visual Studio Code / Visual Studio Code | 8 | 56 | task declaration (related_apps, snapshot) |
| `mailhub` | unknown（保留原始标签） / unknown | 6 | 42 | task declaration (related_apps) |
| `shotcut` | Shotcut / 视频编辑 | 6 | 42 | task declaration (related_apps, snapshot) |
| `gimp` | GIMP / 图像编辑 | 5 | 35 | task declaration (related_apps, snapshot) |
| `libreoffice_writer` | LibreOffice Writer / LibreOffice | 5 | 35 | task declaration (related_apps) |
| `zotero` | unknown（保留原始标签） / unknown | 5 | 35 | task declaration (related_apps, snapshot) |
| `calendar` | unknown（保留原始标签） / unknown | 4 | 28 | task declaration (related_apps) |
| `excel` | unknown（保留原始标签） / unknown | 4 | 28 | task declaration (related_apps, snapshot) |
| `file_manager` | unknown（保留原始标签） / unknown | 4 | 28 | task declaration (related_apps) |
| `libreoffice_calc` | LibreOffice Calc / LibreOffice | 4 | 28 | task declaration (related_apps, snapshot) |
| `libreoffice_impress` | LibreOffice Impress / LibreOffice | 4 | 28 | task declaration (related_apps) |
| `vs_code` | Visual Studio Code / Visual Studio Code | 4 | 28 | task declaration (related_apps) |
| `chrome_thunderbird` | unknown（保留原始标签） / unknown | 3 | 21 | task declaration (snapshot) |
| `pdf_viewer` | unknown（保留原始标签） / unknown | 3 | 21 | task declaration (related_apps) |
| `reaper` | REAPER / 音频工作站 | 3 | 21 | task declaration (related_apps, snapshot) |
| `teamchat` | unknown（保留原始标签） / unknown | 3 | 21 | task declaration (related_apps) |
| `terminal` | unknown（保留原始标签） / unknown | 3 | 21 | task declaration (related_apps) |
| `thunderbird` | Thunderbird / 邮件客户端 | 3 | 21 | task declaration (related_apps, snapshot) |
| `3d-slicer` | 3D Slicer / 医学影像 | 2 | 14 | task declaration (related_apps) |
| `file-manager` | unknown（保留原始标签） / unknown | 2 | 14 | task declaration (related_apps) |
| `freecad` | FreeCAD / CAD | 2 | 14 | task declaration (related_apps) |
| `image_viewer` | unknown（保留原始标签） / unknown | 2 | 14 | task declaration (related_apps) |
| `init_state` | unknown（保留原始标签） / unknown | 2 | 14 | task declaration (snapshot) |
| `kicad` | KiCad / 电子设计 | 2 | 14 | task declaration (related_apps) |
| `musescore` | MuseScore / 乐谱编辑 | 2 | 14 | task declaration (related_apps, snapshot) |
| `blender` | Blender / 3D创作 | 1 | 7 | task declaration (related_apps) |
| `browser` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `calc` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `careerlink` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `chrome_vscode` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (snapshot) |
| `cloudcrm` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `default` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (snapshot) |
| `desktop` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (snapshot) |
| `evince` | Evince / PDF阅读器 | 1 | 7 | task declaration (related_apps) |
| `firefox` | Firefox / 浏览器 | 1 | 7 | task declaration (related_apps) |
| `geogebra` | GeoGebra / 数学软件 | 1 | 7 | task declaration (related_apps) |
| `google-chrome` | Google Chrome / 浏览器 | 1 | 7 | task declaration (related_apps) |
| `labplot` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `libero` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `libreoffice` | LibreOffice（组件未指定） / LibreOffice | 1 | 7 | task declaration (related_apps) |
| `logisim` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `mpv` | mpv / 媒体播放器 | 1 | 7 | task declaration (related_apps) |
| `nautilus` | Nautilus / 文件管理器 | 1 | 7 | task declaration (related_apps) |
| `obsidian` | Obsidian / 笔记软件 | 1 | 7 | task declaration (related_apps) |
| `office` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (snapshot) |
| `openboard` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `pdfviewer` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `solvespace` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `studio.streamview` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `vaultbank` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |
| `writer` | unknown（保留原始标签） / unknown | 1 | 7 | task declaration (related_apps) |

OSWorld行为报告检查了 755 条 model×task 记录；保存动作没有可靠的前台应用身份，因此运行时具体应用为 unknown。computer/pyautogui属于动作接口/实现代码，不等于Chrome、Writer或其他应用被实际启动。历史任务revision与轨迹绑定仍unknown。

家族覆盖按任务去重，不把同一任务里多个别名/组件重复计数：

| 应用家族 | 任务覆盖 | model×task覆盖 |
|---|---:|---:|
| 浏览器 | 53/108 | 371/755 |
| LibreOffice | 13/108 | 91/755 |
| WPS | 13/108 | 91/755 |
| Visual Studio Code | 12/108 | 84/755 |
| 视频编辑 | 6/108 | 42/755 |
| 图像编辑 | 5/108 | 35/755 |
| 邮件客户端 | 3/108 | 21/755 |
| 音频工作站 | 3/108 | 21/755 |
| CAD | 2/108 | 14/755 |
| 乐谱编辑 | 2/108 | 14/755 |
| 医学影像 | 2/108 | 14/755 |
| 电子设计 | 2/108 | 14/755 |
| 3D创作 | 1/108 | 7/755 |
| PDF阅读器 | 1/108 | 7/755 |
| 媒体播放器 | 1/108 | 7/755 |
| 数学软件 | 1/108 | 7/755 |
| 文件管理器 | 1/108 | 7/755 |
| 笔记软件 | 1/108 | 7/755 |

## Assistant：模拟工具环境，不是外部软件名

H-EPM是第三方公开的适配ToolSandbox轨迹；各保存来源版本组独立按该组trajectory/scenario记录数作分母。`summarize_the_task`是框架辅助；其余解析出的联系人、消息、提醒、设置、位置、时间、天气等名称是模拟业务/API接口，没有可确认的外部服务品牌。

| 来源/版本组 | 接口名 | 用途/命名空间 | 调用数 | 轨迹覆盖/组内分母 |
|---|---|---|---:|---:|
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `add_contact` | simulated business/API operation; external product unknown | 4 | 4/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `add_reminder` | simulated business/API operation; external product unknown | 27 | 27/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `calculate_lat_lon_distance` | simulated business/API operation; external product unknown | 3 | 3/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `convert_currency` | simulated business/API operation; external product unknown | 5 | 5/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `datetime_info_to_timestamp` | simulated business/API operation; external product unknown | 53 | 46/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_cellular_service_status` | simulated business/API operation; external product unknown | 17 | 16/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_current_location` | simulated business/API operation; external product unknown | 11 | 9/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_current_timestamp` | simulated business/API operation; external product unknown | 86 | 80/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_location_service_status` | simulated business/API operation; external product unknown | 28 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_low_battery_mode_status` | simulated business/API operation; external product unknown | 26 | 25/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `get_wifi_status` | simulated business/API operation; external product unknown | 40 | 34/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `modify_contact` | simulated business/API operation; external product unknown | 37 | 20/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `modify_reminder` | simulated business/API operation; external product unknown | 6 | 6/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `remove_contact` | simulated business/API operation; external product unknown | 15 | 15/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `remove_reminder` | simulated business/API operation; external product unknown | 3 | 3/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_contacts` | simulated business/API operation; external product unknown | 38 | 38/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_holiday` | simulated business/API operation; external product unknown | 25 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_lat_lon` | simulated business/API operation; external product unknown | 4 | 3/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_location_around_lat_lon` | simulated business/API operation; external product unknown | 34 | 22/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_messages` | simulated business/API operation; external product unknown | 44 | 26/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_reminder` | simulated business/API operation; external product unknown | 50 | 31/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_stock` | simulated business/API operation; external product unknown | 7 | 5/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `search_weather_around_lat_lon` | simulated business/API operation; external product unknown | 15 | 11/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `seconds_to_hours_minutes_seconds` | simulated business/API operation; external product unknown | 1 | 1/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `send_message_with_phone_number` | simulated business/API operation; external product unknown | 11 | 6/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `set_cellular_service_status` | simulated business/API operation; external product unknown | 15 | 11/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `set_location_service_status` | simulated business/API operation; external product unknown | 33 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `set_low_battery_mode_status` | simulated business/API operation; external product unknown | 30 | 27/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `set_wifi_status` | simulated business/API operation; external product unknown | 44 | 32/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `shift_timestamp` | simulated business/API operation; external product unknown | 24 | 24/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `summarize_the_task` | framework summary helper | 207 | 197/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `timestamp_diff` | simulated business/API operation; external product unknown | 18 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7` | `timestamp_to_datetime_info` | simulated business/API operation; external product unknown | 56 | 42/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `add_contact` | simulated business/API operation; external product unknown | 3 | 3/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `add_reminder` | simulated business/API operation; external product unknown | 28 | 28/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `calculate_lat_lon_distance` | simulated business/API operation; external product unknown | 3 | 3/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `convert_currency` | simulated business/API operation; external product unknown | 5 | 5/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `datetime_info_to_timestamp` | simulated business/API operation; external product unknown | 42 | 39/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_cellular_service_status` | simulated business/API operation; external product unknown | 16 | 15/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_current_location` | simulated business/API operation; external product unknown | 11 | 10/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_current_timestamp` | simulated business/API operation; external product unknown | 86 | 79/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_location_service_status` | simulated business/API operation; external product unknown | 27 | 19/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_low_battery_mode_status` | simulated business/API operation; external product unknown | 30 | 27/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `get_wifi_status` | simulated business/API operation; external product unknown | 33 | 28/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `modify_contact` | simulated business/API operation; external product unknown | 38 | 21/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `modify_reminder` | simulated business/API operation; external product unknown | 7 | 7/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `remove_contact` | simulated business/API operation; external product unknown | 16 | 15/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `remove_reminder` | simulated business/API operation; external product unknown | 2 | 2/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_contacts` | simulated business/API operation; external product unknown | 35 | 35/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_holiday` | simulated business/API operation; external product unknown | 26 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_lat_lon` | simulated business/API operation; external product unknown | 6 | 4/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_location_around_lat_lon` | simulated business/API operation; external product unknown | 24 | 17/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_messages` | simulated business/API operation; external product unknown | 40 | 26/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_reminder` | simulated business/API operation; external product unknown | 47 | 28/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_stock` | simulated business/API operation; external product unknown | 8 | 5/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `search_weather_around_lat_lon` | simulated business/API operation; external product unknown | 19 | 9/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `send_message_with_phone_number` | simulated business/API operation; external product unknown | 10 | 6/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `set_cellular_service_status` | simulated business/API operation; external product unknown | 18 | 12/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `set_location_service_status` | simulated business/API operation; external product unknown | 32 | 18/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `set_low_battery_mode_status` | simulated business/API operation; external product unknown | 27 | 26/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `set_wifi_status` | simulated business/API operation; external product unknown | 41 | 31/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `shift_timestamp` | simulated business/API operation; external product unknown | 30 | 27/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `summarize_the_task` | framework summary helper | 206 | 198/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `timestamp_diff` | simulated business/API operation; external product unknown | 23 | 20/207 |
| H-EPM `H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36` | `timestamp_to_datetime_info` | simulated business/API operation; external product unknown | 39 | 33/207 |

本地 ToolSandbox Assistant Repeat-01 的工具名同样是模拟业务接口。所选批次共9次运行；调用总数从已验收逐run事件汇总。按本地事件分别统计，不映射为微信、Outlook、Google Calendar等真实软件。

| 本地角色 | 模拟接口 | 任务数/3 | 运行数/9 | 保存调用数 | ok数 |
|---|---|---:|---:|---:|---:|
| agent | `add_reminder` | 1 | 3 | 3 | 3 |
| agent | `datetime_info_to_timestamp` | 1 | 3 | 3 | 3 |
| user | `end_conversation` | 3 | 9 | 9 | 9 |
| agent | `get_cellular_service_status` | 1 | 2 | 2 | 2 |
| agent | `get_current_timestamp` | 2 | 6 | 6 | 6 |
| agent | `modify_contact` | 1 | 3 | 3 | 3 |
| agent | `search_contacts` | 2 | 6 | 14 | 14 |
| agent | `search_messages` | 1 | 3 | 7 | 6 |
| agent | `send_message_with_phone_number` | 1 | 3 | 4 | 3 |
| agent | `set_cellular_service_status` | 1 | 3 | 3 | 3 |
| agent | `timestamp_to_datetime_info` | 1 | 3 | 3 | 3 |

## 本地 DocOps：接口到处理库

库映射来自被Repeat-02身份/分析manifest绑定的 `document_tools_runtime.py`，并与每次保存工具调用关联。调用数是接口调用数；ok单列。这里只把具体格式接口映射到实现函数直接使用的库。`inspect_document`按实际路径扩展名分支，分析产物没有保留可验证的每次分支，因此不把它的调用摊给库。

| 固定任务 | 调用接口 | 角色 | 实现库 | 用途 | 调用数 | ok数 | 运行数/9 |
|---|---|---|---|---|---:|---:|---:|
| `atomic__excel_001_budget_bucket_totals_seed` | `xlsx_read_sheet` | agent | openpyxl | 表格读取 | 7 | 7 | 3 |
| `atomic__excel_001_budget_bucket_totals_seed` | `xlsx_set_formula` | agent | openpyxl | 公式写入 | 6 | 6 | 3 |
| `atomic__pdf_004_audit_pages_reorder_seed` | `pdf_reorder_pages` | agent | pypdf | PDF页面重排 | 3 | 3 | 3 |
| `atomic__ppt_008_bullet_editing_seed` | `ppt_list_slides` | agent | python-pptx | 幻灯片读取 | 6 | 6 | 3 |
| `atomic__ppt_008_bullet_editing_seed` | `ppt_replace_text` | agent | python-pptx | 幻灯片文本编辑 | 3 | 3 | 3 |

源码映射中，`openpyxl`对应明确的`xlsx_*`接口，`python-pptx`对应`ppt_*`，`pdfplumber`对应`pdf_extract_text`，`pypdf`对应`pdf_reorder_pages/delete_pages`。Repeat-02未调用Word专用接口；`python-docx`仅作为实现参考，未计作本批使用。`soffice`/LibreOffice桌面进程没有被这些事件证明。文档格式可被Python库处理，不等于Microsoft Office/LibreOffice应用启动。

## 无法从这些来源统计的具体软件

- AgentX发布的是筛选后的请求流，不是完整工具执行日志；无法据其请求/子代理字段列真实命令或业务软件。
- Applied Compute是生产轨迹派生workload模板，不是Agent消息或真实工具操作记录；本轮复用模板数 {"agentic_coding_8k": 8192, "code_qa_8k": 8192, "office_work_8k": 8192}，模板字段不提供可确认程序名。
- Video按PUBLIC-TRACE-OPERATIONS-v3的既有限制保留为工具证据不完整；本轮没有从该来源得到可靠的具体软件/命令身份，保持unknown，不补推FFmpeg等常见工具。
- OSWorld有任务声明应用但无逐动作前台应用身份；本地P1 Coding以命令参数可读取的软件名为静态证据，不能证明进程成功启动。

## 解释边界

来源之间不共用分母；重复run不等于独立任务。静态命令头不证明进程成功启动，任务声明不证明应用被打开，API工具名不是真实服务名，源码导入不证明每个分支都运行。缺少运行版本时库版本unknown。操作类别比例也不等于软件使用时间、CPU或内存占比。
