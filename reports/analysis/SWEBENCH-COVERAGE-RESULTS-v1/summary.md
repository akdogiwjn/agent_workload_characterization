# SWE-bench：下载缺口、覆盖复核与公开评价关联

本轮仅下载公开数据和离线读取，不执行Agent、工具、patch、verifier或benchmark。旧raw和报告保持原样。

- 原登记19,876对象/41组；新增147个Sonar对象，累计20,023对象。Sonar达到2294/2,294。
- 独立任务键2,506→2,594（新增88）；同一任务跨submission不算新的独立任务。
- 全部旧对象按获取清单与coverage哈希读取核验；7,367个非动作对象重查，原协议分流改变0。没有把过程节点或叙述补成调用。
- 39/41组有同split/submission的已登记results.json；缺失：20250615_agentless_mindlink, lite/20251009_MAYA_claude-sonnet-4-5-20250929。

## 三种原生格式：全组与原90条子集

| 组 | 对象数 | 独立group×instance | 已列resolved | 列其他保存字段 | 未列入保存字段 |
|---|---:|---:|---:|---:|---:|
| 20240620_sweagent_claude3.5sonnet | 500 | 500 | 168 | 14 | 318 |
| lite/20240617_moatless_gpt4o | 300 | 300 | 74 | 226 | 0 |
| test/20251219_sonar-foundation-agent_claude-opus-4-5 | 2294 | 2294 | 1207 | 19 | 1068 |

以上是发布清单成员关系，不是本项目重跑评分。未列入resolved不转为failed；no_generation/no_logs/timeout等保留来源标签。一次submission内同task的多个对象不当成多次独立attempt。

原90条选择保持冻结，只追加评价关联。关联结果：`{"20240620_sweagent_claude3.5sonnet": {"not_listed_in_saved_fields": 20, "listed_resolved": 10}, "lite/20240617_moatless_gpt4o": {"listed_other_saved_fields": 20, "listed_resolved": 10}, "test/20251219_sonar-foundation-agent_claude-opus-4-5": {"not_listed_in_saved_fields": 21, "listed_other_saved_fields": 1, "listed_resolved": 8}}`。

## 行为与结果分层

各组按saved unit_kind与保存结果标签分别给出工具/操作单位数的逐instance median/IQR，见summary.json的behavior_strata。分层只覆盖有已识别保存单位、且每instance/kind来源行唯一的实例；没有行为证据不填0，instances_without_behavior_rows另列。它们是描述性分层，任务集、保存格式及harness差异不做因果解释；同instance同kind有多个来源行时不擅自求和，排除数另列。

sweagent显式info.exit_status、轨迹submit标记、moatless末条transition、提交patch存在性和评价标签分开记录。Finished/submitted不替代任务resolved；未按末条assistant文本推断正常终止。

## 覆盖仍有哪些边界

6,054个旧部分/歧义对象中，很多是检索叙述、候选文件、请求响应日志或保存过程节点；本轮按已有冻结解析协议重查。零变化说明该协议下结果稳定，不等于所有语义已经穷尽，也不证明不存在其他可支持的协议。

此次只补已选Sonar组的147对象，没有穷尽上游所有submission。缺评价文件、未列入任何来源状态、无调用返回ID、无attempt/patch精确绑定均保持未知。没有CPU/内存/I/O/热点、可靠工具耗时或费用的新证据。

## 来源与复现

固定索引commit `40f164d5b8f1d249bf95a6df8b74b577fd8e519d`；Git中的results/metadata与S3对象保存位置分别登记。S3可变，新增内容只证明与原listing字节、当前HTTP/ETag一致，不冒称旧commit冻结了S3字节。

[逐组覆盖/评价CSV](coverage_results.csv) · [原90条关联](subset90_links.jsonl) · [逐instance](per_instance.jsonl) · [非动作复核](negative_coverage_review.jsonl) · [评价来源](evaluation_sources.json) · [manifest](manifest.json)
