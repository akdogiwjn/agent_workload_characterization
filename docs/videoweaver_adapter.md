# VideoWeaver 本地 Trace 组合（P0-10 小样阶段）

## 来源与输入

主样例 **VW-LONG** 由 `gen_videoweaver_traces`（bundle 目录）的三个文件组成：

| 角色 | 路径（相对 bundle） | 内容 | provenance source_id |
| --- | --- | --- | --- |
| Manifest | `manifest.json` | 运行状态、trace_id、配置、工具计数 | gen_videoweaver_traces |
| 模型遥测 | `model_telemetry/model_telemetry.jsonl` | 70 条逐请求 proxy 记录 | gen_videoweaver_traces |
| 原生 ReAct | `native_trajectory/original_ReAct.jsonl` | 88 个 toolCall↔toolResult 配对 | gen_videoweaver_traces |

辅助样例 **AUX-INCOMPLETE** 来自 `telemetry/video_weaver.jsonl`（原始 proxy 全集 491 条），选 trace_id=run-003、call_id=b6c324ad 的一条 input/output 缺失的请求，如独立未装配请求文档输出。

## 架构

`adapters/videoweaver.py` 是纯组合器，不打开文件、不执行媒体/exporter、不写批次：
- `parse_proxy_record(raw)` — 校验一条 proxy JSON 记录
- `parse_react_event(raw)` — 校验一条 ReAct JSONL event
- `interval(clock_id, start_ns, end_ns, source, missing)` — 构建 Interval
- `compose_run(manifest, telemetry, react, provenances)` — 输出一个闭合主 run TraceDocument（semantic_trace）
- `compose_unassigned_request(source_id, raw_record, provenance)` — 输出未装配请求文档

三个输入各有独立 provenance（manifest→声明、telemetry→请求指标、native→工具事件）。run ID 由 `stable_id("gen_videoweaver_traces", "run", trace_id)` 生成，不因路径/转换版本变化。请求键 `(trace_id, call_id)` 去重；工具通过 `toolCall id` 配对，孤立结果保留。

## 三轴状态

- execution：`generation_status=success` → completed（不因 pipeline_reported_status=failed 改变）
- evaluation：manifest 无声明 → unknown
- archive：仅检查所选文件 → unknown

## 指标与时间

- 时钟：UTC（proxy wall-clock），精度 unknown，不编造 monotonic 坐标
- 请求 interval：native_event（proxy 边界直接观测），API latency 另存 Metric，不强行配对
- Tool interval：log_receipt（ReAct 消息时间），结束缺失不补成 start
- 汇总：input_tokens 单独 max_input_context（max input_tokens=79937），source_context_tokens max 另名（80378，=input+output per proxy 实现）
- run_elapsed、local_cpu_time、tool_cpu_time 均 unavailable

## 检查内容

`check-videoweaver-samples` 执行：
1. VW-LONG 主运行组合、IR round-trip、请求/tool 数、token 合计、max_input/context、sidecar 对照（70 请求/88 工具均一致）
2. AUX-INCOMPLETE 独立文档、input=null、output=null、run_id=null、unresolved
3. 三轴状态、manifest wall_time、无伪造 CPU/elapsed

## 已知限制

- `context_tokens` 在 proxy = input+output，不是独立输入 context 度量
- max_input_context=79937（max input_tokens）与 sample_candidates 登记的 80378 差异源自此语义
- 非全量 ingest（仅选 70+1 条，共 491→selected）
- 无 submit/poll/wait 关联，无 provider job ID
- 远端媒体 CPU 不可测量
- 旧代码 `gen_sidecar.py` SHA：`d57fe3e11d96c4d7b1daa0761845d44ac8b9649fcb7410dfda3d56c22d2becd2`
- 旧代码 `proxy.py` SHA：`d398183a477ba8df35b40bd6191622eb66dd90730a141ae5b643dfb8b6e2fd27`