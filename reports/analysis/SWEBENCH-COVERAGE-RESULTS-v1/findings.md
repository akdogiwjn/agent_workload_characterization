# SWE-bench 本轮发现与缺口

[完整范围与规则](summary.md) · [逐组覆盖/评价](coverage_results.csv) · [校验](verification.json)

## 本轮实际补齐了什么

新增147个Sonar文件，39,377,587字节；与原固定下载清单逐任务及字节核对，累计2,294/2,294。新增文件评价标签：{'not_listed_in_saved_fields': 79, 'listed_resolved': 67, 'listed_other_saved_fields': 1}。

登记对象19,876→20,023；跨submission去重的任务ID为2,506→2,594，新增88个。物理对象包含轨迹、上下文、配套产物和alternate视图，不能都称为完整轨迹。

| 物理对象覆盖分类 | 数量 |
|---|---:|
| actions_extracted | 12,656 |
| process_partial_or_ambiguous | 6,054 |
| companion_artifact | 1,313 |

原7,367个非动作对象全部按冻结v3协议重解析，分类/原因/单位数均未改变。这是覆盖复核，没有增加这些文件的语义支持；本轮新增的147个文件均提取到保存动作。

## 评价关联：分母与未知项

41组中39组已有同split/submission的公开results.json，均来自本地固定Git索引；本轮实际新增的是关联分析。另2组缺失：`20250615_agentless_mindlink`、`lite/20251009_MAYA_claude-sonnet-4-5-20250929`。这只描述该索引的登记范围。

按完整原生instance ID精确连接，共19,514个group×instance键。它们不等同于已验证的独立attempt；下表也不构成模型成功率或排名。

| 保存评价关系 | group×instance数 |
|---|---:|
| 列其他保存字段 | 1,747 |
| 明确列为 resolved | 8,371 |
| 未列入保存字段 | 8,730 |
| 缺评价文件 | 666 |

未出现明确unresolved清单成员或冲突标签。8,730个未列入保存字段的键仍未知；其他字段包含generated/applied/with_logs/no_generation/no_logs等阶段标签，不能统一转成失败。`20240402_sweagent_gpt4`的no_generation清单有30项、26个唯一ID，4项重复已登记，连接按成员关系去重，不把重复项计为额外任务。

另有509个对象未按原样匹配instance ID：

| 组 | 不匹配对象数 |
|---|---:|
| 20241128_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor_20241128 | 2 |
| 20241212_google_jules_gemini_2.0_flash_experimental | 501 |
| 20250112_ugaiforge | 4 |
| 20250214_agentless_lite_o3_mini | 1 |
| 20250306_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor | 1 |

其中Google组含500个`_alternate`对象及1个README；其余为汇总/配置等文件。不擅自去掉后缀，把不同视图或汇总文件冒充已精确绑定的任务。

来源核查：37组metadata的trajs字段与预期S3命名空间字面相符；CodeShell另1组写成Git相对路径`evaluation/verified/.../trajs`，未冒称其S3字段匹配；SWE-Exp及2个缺评价组未取得对应metadata。这不妨碍按目录/ID记录发布清单关系，但不证明字节、patch或attempt一致。来源checked标签仅9组为true，29组false、3组缺失；它不是本项目独立重验。

## 三种原生格式的行为与评价分层

原90条子集不变，全部追加独立评价关系：SWE-agent 10 resolved/20未列；Moatless 10 resolved/20列其他字段；Sonar 8 resolved/1列其他字段/21未列。全组的描述统计如下：

| 组 | 保存单位 | 评价分层 | n | 单位数中位数 | Q1–Q3 |
|---|---|---|---:|---:|---:|
| SWE-agent | saved_action_or_tool_call | 列其他保存字段 | 14 | 30 | 20.5–62 |
| SWE-agent | saved_action_or_tool_call | 明确列为 resolved | 168 | 19 | 13–32.25 |
| SWE-agent | saved_action_or_tool_call | 未列入保存字段 | 318 | 33 | 19–56 |
| Moatless | saved_transition | 列其他保存字段 | 226 | 10 | 7–12 |
| Moatless | saved_transition | 明确列为 resolved | 74 | 8 | 6–10.75 |
| Sonar | saved_action_or_tool_call | 列其他保存字段 | 19 | 140 | 121.5–150 |
| Sonar | saved_action_or_tool_call | 明确列为 resolved | 1207 | 55 | 41–72 |
| Sonar | saved_action_or_tool_call | 未列入保存字段 | 1068 | 69 | 52–87 |

全41组共77个保存单位×评价分层，见[完整CSV](behavior_strata.csv)。其中6,358个group×instance没有已识别行为行，未填成零工具调用。Moatless的transition与另两组的动作/调用分母不同；其他组还包含保存过程节点等单位，不横向比较为工具效率。

SWE-agent的500条中，408条写有exit_status=submitted，84条为submitted (exit_cost)，6条exit_cost，2条缺失；仅168个任务列为resolved。Moatless末条transition有274个Finished，其中72个列为resolved、202个只列其他字段；另有2个resolved的末条保存状态分别为Rejected与PlanToCode。由此不能用最后保存状态替代公开评价，也不能反推保存记录完整。

[原生状态×评价交叉表](native_result_cross_tabs.csv)保留两类证据；Sonar没有同等原生exit_status字段，仍保留缺失。提交patch存在性与显式submit标记在逐instance中另列，未按末条文本推断正常终止。

## 仍未补齐

- 6,054个部分/歧义对象和1,313个配套产物仍不能统一恢复成完整业务工具轨迹；逐组原因见[复核表](negative_coverage_by_group.csv)。
- 没有穷尽这41组之外的公开submission；2组缺评价、未列入清单的任务及alternate对象仍有绑定缺口。
- 同一次attempt/同一份patch的精确绑定、无ID工具返回的关联、可靠工具耗时仍缺证据。
- 原始CPU、内存、I/O和业务工具资源成本无法从本轮材料恢复；固定Git索引也不冻结可变S3对象的历史字节。

## 复现与完整性

复现命令：

```bash
python3 -B -m unittest tests.test_swebench_coverage_results -v
python3 -B scripts/swebench_coverage_results.py --gap-manifest data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/manifest.json --output-dir /tmp/SWEBENCH-COVERAGE-RESULTS-reproduce
```

主分析拒绝覆盖已有目录。发现汇总由`scripts/swebench_coverage_findings.py`从冻结产物生成，执行前复核主manifest全部输入/输出、代码/测试、历史报告全部输出，以及新增下载的HTTP头/原始文件。

本轮未执行任何保存命令、Agent、模型、patch、benchmark或verifier。旧原始数据、旧报告及原90条选择保留原样。
