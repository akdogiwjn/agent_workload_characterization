# PUBLIC-TRACE-SOFTWARE-TOOLKITS-v2 → v3 勘误

本版只修复 SWE-bench 重新解析软件统计丢失原始 `unit_kind` 的接线；不改变软件分类、命令识别或其他来源的证据口径。

| 项目 | v2记录 | v3重算 | 解释/边界 |
|---|---:|---:|---|
| 分母/分组无效的软件明细 | 26行、18,723组件、16来源组 | 26行、18,723组件、16来源组重新关联 | v2明细存在，但统一写成`saved_operation_event`后与部分来源单位元数据不匹配；v3直接沿用解析器给出的单位，不按来源或工具名猜测。受影响软件：{"pytest": 18215, "unittest": 508} |
| Sonar pytest模块 | 13,470组件 | 13,470组件，单位=`saved_action_or_tool_call`；分母 task=2147、trajectory=2147、record=140245 | 组件频数保留，归入其实际保存单位；静态组件不代表执行成功 |
| SWE-bench静态组件总数 | 275,036 | 275,036 | +0；仅归属/分组修正 |
| 全部公开Coding静态组件总数 | 1,198,215 | 1,198,215 | +0；含其他来源对照 |
| 未受影响统计 | Solver分母 {"20240920_solver": 5037, "20240924_solver": 5246, "20241028_solver": 6037} | Solver分母一致=True；其他非SWE-bench行一致=True | Local Coding、OSWorld、DocOps、Assistant及其他Coding来源保持原统计 |

### 16个受影响来源组的摘要变化

| 来源组 | v2组摘要组件 | v3组摘要组件 | 变化 | 修正单位 |
|---|---:|---:|---:|---|
| `20240402_sweagent_claude3opus` | 1,918 | 1,953 | +35 | saved_action_or_tool_call |
| `20240402_sweagent_gpt4` | 1,365 | 1,374 | +9 | saved_action_or_tool_call |
| `20240620_sweagent_claude3.5sonnet` | 5,041 | 5,138 | +97 | saved_action_or_tool_call |
| `20240728_sweagent_gpt4o` | 4,289 | 4,578 | +289 | saved_action_or_tool_call |
| `20241007_nfactorial` | 10,496 | 10,508 | +12 | saved_shell_invocation |
| `20241125_enginelabs` | 2,602 | 2,629 | +27 | saved_action_or_tool_call |
| `20241125_marscode-agent-dev` | 2,518 | 2,525 | +7 | saved_action_or_tool_call |
| `20250110_learn_by_interact_claude3.5` | 6,033 | 6,113 | +80 | saved_action_or_tool_call |
| `20250118_codeshellagent_gemini_2.0_flash_experimental` | 1,658 | 1,685 | +27 | saved_action_or_tool_call |
| `20250203_openhands_4x_scaled` | 3,643 | 3,786 | +143 | saved_action_or_tool_call |
| `20250522_tools_claude-4-opus` | 16,821 | 18,353 | +1,532 | saved_action_or_tool_call |
| `20250616_Skywork-SWE-32B` | 3,715 | 3,818 | +103 | saved_action_or_tool_call |
| `20250623_warp` | 10,023 | 11,687 | +1,664 | saved_shell_invocation |
| `20251014_Lingxi_kimi_k2` | 9,545 | 10,735 | +1,190 | saved_action_or_tool_call |
| `20251103_SalesforceAIResearch_SAGE_OpenHands` | 22,180 | 22,215 | +35 | saved_tool_call |
| `test/20251219_sonar-foundation-agent_claude-opus-4-5` | 144,225 | 157,698 | +13,473 | saved_action_or_tool_call |

v1/v2报告、manifest及输入未改写。v2绑定分析器的精确修改前快照：`env/public-trace-software-toolkits-v3/source-before-edit/public_trace_software_toolkits.py`。v3 manifest登记该快照和本次实际输入/输出。
