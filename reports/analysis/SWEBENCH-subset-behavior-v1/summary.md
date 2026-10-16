# SWEBENCH-subset-behavior-v1：SWE-bench 已下载轨迹代表性子集离线行为分析

生成日期：2026-10-07。离线只读，未联网、未执行轨迹、未调用模型；不改变 G2/G3-R、CPU-02、Replay。索引固定 `40f164d5b8f1d249bf95a6df8b74b577fd8e519d`。

## 选样与规模

依据增量证据（非文件数量）从已检查的 6 个 submission 中选 3 组，各按 task ID 字典序取前 30，共 90 条（selection.json 冻结于分析前，含 90 个文件 bytes/SHA-256）：

| 组 | split | 保存格式 | 选择理由 |
| --- | --- | --- | --- |
| 20240620_sweagent_claude3.5sonnet | verified | SWE-agent .traj（action/observation 步 + history 消息 + info.exit_status） | 专用编辑器接口（create/open/edit/submit）+ 轨迹内终止字段 |
| lite/20240617_moatless_gpt4o | lite | transitions 搜索流程（SearchCode/IdentifyCode/PlanToCode/EditCode/Finished） | 保存的流程结构与 duration/cost 字段；不据此断言其他语料完全没有 |
| test/20251219_sonar-foundation-agent_claude-opus-4-5 | test | 消息列表 + 显式 tool_calls + thinking blocks | Test split 最广任务集 + 显式工具调用协议；tool 结果无 tool_call_id |

排除：SuperCoder2.0（单结构）、MAYA（过程保存少）、KGCompass（自由文本无结构化调用）。已知偏差：字典序前 30 偏 astropy/django 任务；每 task 单轨迹（无 repeat 维度）；sonar 组为 partial 下载但所选 30 个文件齐全；三格式轨迹内**均无 evaluation/resolved 字段**。

## 相比 SWE-rebench v2 的新增观察（4 条）

**1. 所选两组原生轨迹提供双接口并存的直接证据。** sweagent 组 1,053 个 action 中专用编辑器命令 500 个（edit 286、open 83、create 46、goto 45、search_file 40）与 shell 命令 553 个（python 265、pip 87、ls 35 等）并存；sonar 组 2,029 个工具调用中结构化编辑工具 str_replace_based_edit_tool 481 个（view 414、str_replace 63、create 4）与 bash 1,544 个并存。SWE-rebench 的 normalized corpus 中 bash_terminal 占 85.4%；该比例不能证明其余接口中不存在编辑器。允许：保存接口结构的描述。不允许：接口占比跨语料直接比较（normalized vs 原生、任务集不同）。

**2. 显式退出字段、末条流程状态和文件结束须分开。** sweagent 组 30 条全部有显式 exit_status：submitted 24、submitted (exit_cost) 6——其中 **6 条 exit_cost 轨迹内没有 submit 命令**（Submit-marker 仅 24），即 exit_status 标"submitted"但轨迹内无提交动作，来源退出标签与显式提交动作在字段层可区分，不额外推断退出机制。moatless 组末条保存的 transition 名为：Finished 27、Rejected 2、ClarifyCodeChange 1（仅描述列表末项，不据此认证 Agent 的实际终止原因）。sonar 组 30 条均无显式终止字段（末条为 assistant 文本，终止原因 unknown）。SWE-rebench 的 agent_exit_status 另行记录；上述不同证据层级不能合并为终止协议排名。

**3. moatless 保存了转移列表和结构化参数，不能据列表形式排除底层搜索分支。** 30 条轨迹的 transitions 无 parent/children/branch 标记（branch_markers 为空），为保存的流程节点序列（典型 SearchCode→IdentifyCode→(PlanToCode→EditCode)*→Finished）；EditCode 动作保存编辑内容（content）、SearchCode 保存结构化参数（file_pattern/class_name），**所检查的保存结构中未提取到 shell 命令**，shell 活动分类不适用。轨迹内另有 duration 与 total_cost 保存字段（仅登记为保存字段，不解释为资源或账单）。本轮不对 SWE-rebench 全语料的搜索流程或 cost 字段是否存在作否定判断。

**4. 调用-返回关联协议缺失的直接证据：sonar 的 tool 结果消息全部无 tool_call_id。** 30 条轨迹共 2,029 条工具调用（均带调用 ID）与 2,029 条 tool 角色结果消息，计数一致但**结果消息无一携带 tool_call_id**，显式 ID 关联在该格式中不可用——按规则不做位置强配，只分别计数并登记协议缺失。这与 SWE-rebench 的"带 ID call/result 关联统计"形成对照：关联分析能力是格式属性，不是普遍前提。

## 与已有 Coding 结果的一致与不可比较

一致：(a) bash/shell 复合命令的 Unknown 模式——sonar 的 bash 调用 76.3% Unknown（compound_or_redirection 1,437），与 SWE-rebench 的高 Unknown 结构同源；(b) Test 仅认显式测试命令——sweagent 组 Test=11 全部来自显式 pytest 命令头，与 SWE-rebench v2 修正后的 Test 边界一致。不可比较：(a) SWE-rebench 为 17 模型统一 normalized 格式，本子集为 3 种原生格式，活动分布不在同口径；(b) 任务集不同（SWE-rebench 111 task vs 本子集三组各自的 30-task 前缀，仅部分重叠）；(c) evaluation/resolved 在三种原生格式轨迹内均不存在，本轮尚未关联独立 evaluation 配套文件，不能推断整个本地来源无法关联结果（SWE-rebench 有 evaluation_status）。组间差异无法区分任务集、格式、版本或 harness 因素，不做归因。

## 无法支持的结论

不做模型/harness 排名；不把接口占比或工具计数当活动密度；Unknown 不当"未执行"；30 条/组不推广为该 submission 全量（更不推广为 split 或 benchmark）；跨组不合并分母；无 evaluation 字段故无成功率描述；不推算 CPU/内存/I/O/耗时/等待/思考/账单（moatless 的 duration/cost 仅为保存字段）；字典序选样的 astropy/django 偏向保留在所有结论中。

## 下一步优先级判断（非已验证的边际增益结论）

本轮建议优先准备公开 Computer/Office 的最小资源测量，而不是立即扩大同格式样本。这是工作优先级判断，不是已经测得扩样边际增益递减。Computer/Office 已有 OSWorld 公开轨迹和限定行为分析，缺口是本项目该类别的自运行资源测量，并非没有公开 trace。准备与执行均未由本次修订启动或授权。

## 方法与核验

活动分类逐字复用 SWE-rebench v2 保守规则（仅作用于 shell 串；编辑器接口按接口动作分类）；Unknown 打断保存序列转换计数；分支结构只报告保存形态不扁平化为执行时间线。7 项定向测试（真实结构 fixture、缺 ID/孤立返回、Unknown 边界、shell 关键词≠测试调用、分支不扁平化、终止/结果分离、输入变化→输出变化、完整入口）全部通过；90/90 解析零错误。

## 可追溯入口

- [selection.json](selection.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [summary.json](summary.json) · [manifest.json](manifest.json)
- 输入登记：SWEBENCH-SUPPLEMENT-20261006 / SWEBENCH-CONTINUATION-20260930 / BULK-NONVIDEO-20260929；对照 [SWE-REBENCH-behavior-v2](../SWE-REBENCH-behavior-v2/summary.md)


## 2026-10-08 表述修订

收紧接口覆盖、终止原因、保存列表与执行树、结果关联可行性及下一步类别缺口的表述。生成器同步将 moatless 末条状态移到 last_saved_transition，termination 保持 unknown；不改变原始观察计数。完整入口测试输出改为临时目录，避免测试覆盖正式产物。原始数据与冻结 selection 未修改。
