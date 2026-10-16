# SWE-bench 本地对象覆盖清单

仅针对三轮获取manifest登记、并在本轮逐文件核对SHA的本地对象；不是上游全部公开提交的覆盖率。对象可能是轨迹、日志或配套产物，不直接等于轨迹数。

| submission | 登记对象 | 可提取结构化保存单位的对象 | 本轮未支持对象 |
| --- | ---: | ---: | ---: |
| 20240402_sweagent_claude3opus | 443 | 443 | 0 |
| 20240402_sweagent_gpt4 | 496 | 496 | 0 |
| 20240612_MASAI_gpt4o | 500 | 0 | 500 |
| 20240620_sweagent_claude3.5sonnet | 500 | 500 | 0 |
| 20240721_amazon-q-developer-agent-20240719-dev | 500 | 0 | 500 |
| 20240728_sweagent_gpt4o | 465 | 465 | 0 |
| 20240918_lingma-agent_lingma-swe-gpt-72b | 499 | 0 | 499 |
| 20240918_lingma-agent_lingma-swe-gpt-7b | 496 | 0 | 496 |
| 20240920_solver | 500 | 0 | 500 |
| 20240924_solver | 500 | 0 | 500 |
| 20241002_lingma-agent_lingma-swe-gpt-72b | 500 | 0 | 500 |
| 20241002_lingma-agent_lingma-swe-gpt-7b | 498 | 0 | 498 |
| 20241007_nfactorial | 478 | 0 | 478 |
| 20241028_solver | 500 | 0 | 500 |
| 20241108_devlo | 500 | 0 | 500 |
| 20241125_enginelabs | 499 | 499 | 0 |
| 20241125_marscode-agent-dev | 500 | 0 | 500 |
| 20241128_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor_20241128 | 2 | 0 | 2 |
| 20241212_epam-ai-run-claude-3-5-sonnet | 500 | 0 | 500 |
| 20241212_google_jules_gemini_2.0_flash_experimental | 1001 | 0 | 1001 |
| 20241213_devlo | 500 | 0 | 500 |
| 20250110_learn_by_interact_claude3.5 | 500 | 0 | 500 |
| 20250112_ugaiforge | 4 | 0 | 4 |
| 20250118_codeshellagent_gemini_2.0_flash_experimental | 500 | 0 | 500 |
| 20250120_Bracket | 483 | 0 | 483 |
| 20250203_openhands_4x_scaled | 500 | 389 | 111 |
| 20250214_agentless_lite_o3_mini | 501 | 0 | 501 |
| 20250306_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor | 1 | 0 | 1 |
| 20250522_tools_claude-4-opus | 500 | 0 | 500 |
| 20250615_agentless_mindlink | 366 | 0 | 366 |
| 20250616_Skywork-SWE-32B | 500 | 0 | 500 |
| 20250623_warp | 497 | 0 | 497 |
| 20250806_SWE-Exp_DeepSeek-V3 | 500 | 0 | 500 |
| 20251014_Lingxi_kimi_k2 | 500 | 0 | 500 |
| 20251103_SalesforceAIResearch_SAGE_OpenHands | 500 | 0 | 500 |
| lite/20240617_moatless_gpt4o | 300 | 300 | 0 |
| lite/20240806_SuperCoder2.0 | 300 | 0 | 300 |
| lite/20241127_globant_codefixer_agent | 300 | 0 | 300 |
| lite/20250619_KGCompass_claude-3.5-sonnet-20241022 | 300 | 0 | 300 |
| lite/20251009_MAYA_claude-sonnet-4-5-20250929 | 300 | 0 | 300 |
| test/20251219_sonar-foundation-agent_claude-opus-4-5 | 2147 | 2147 | 0 |

未支持对象包括无显式tool_calls的消息、自由文本/非JSON日志、其他结构与配套说明。不能据此说这些对象不含命令；只说明本轮没有可靠提取协议。
后续应按来源协议逐组验证，不从prompt/thought中的代码块直接猜测执行动作，也不为了降低Unknown强行归类。

实际存在但未登记的路径数：0；路径逐项见coverage.json。

[逐文件覆盖JSON](coverage.json) · [操作总结](summary.md)
