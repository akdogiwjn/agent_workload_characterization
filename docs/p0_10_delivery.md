# P0-10 VideoWeaver 本地 Trace 小样阶段

状态：**DONE（VideoWeaver 小样阶段）**，2026-09-10；其余本地来源（DocOps/AgenticVBench/WorkArena）仍未接入；G0/M1 未验收。

## 实际交付

- `adapters/videoweaver.py` — 纯组合器：manifest/proxy/ReAct 三源解析、严格校验（bool/NaN/Inf/OverflowError）、三轴状态、多 provenance、IR 0.2 semantic_trace、unassigned request 文档
- `adapters/videoweaver_checks.py` — VW-LONG（主运行）+ AUX-INCOMPLETE（辅助缺失请求）+ sidecar 对照
- `tests/test_videoweaper.py` — 15 项合成回归（round-trip、去重、空 token 保留、HTTP 200 缺 usage、unassigned、孤立结果、负值拒绝等）
- CLI `check-videoweaver-samples` — 只读检查后 JSON stdout
- `reports/quality/videoweaver_sample_validation.json` — 实际检查结果（机械生成）
- `docs/videoweaver_adapter.md` — 设计文档

## 实际验证结果

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests -v         → 137 项通过
PYTHONPATH=src python3 -B -m agent_workload_characterization check-videoweaver-samples  → PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples       → PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples      → PASS
git diff --check                                                                        → OK
```

### VW-LONG 主运行

| 指标 | 实际值 | 证据 |
|---|---|---|
| model_request_count | 70（唯一 call_id=70） | observed |
| total_input_tokens | 4,041,546 | derived |
| total_output_tokens | 28,631 | derived |
| max_input_context（max input_tokens） | 79,937 | derived |
| max_source_context_tokens（context_tokens max） | 80,378 | derived |
| total_api_latency_s | 401.421 | derived |
| tool_call_count | 88（唯一 call_id=88） | observed |
| orphan_tool_results | 0 | observed |
| manifest_reported_wall_time_s | 1,616.424 | observed |
| run_elapsed / local_cpu_time / tool_cpu_time | null（unavailable） | — |

sidecar 对照：70 请求键一致，88 工具 ID 一致，无多余/缺失。

### AUX-INCOMPLETE 辅助

trace_id=run-003, call_id=b6c324adb8dd40179883ecead5cb4262, line=326
- input_tokens: null, output_tokens: null（HTTP 200 但 usage 缺失）
- ttft=3.716896, api_latency=5.253902 — 保留
- run_id=null, association=unresolved, method=run_not_loaded_in_selection

## 边界与限制

- 只选了一个完整 bundle（VW-LONG）+ 一条辅助请求（run-003）；其余 3 bundle 未全量验证
- raw telemetry 491 条中仅 70+1 条被规范化
- 不创建 formal normalized 批次；不发 API；不改旧源
- sidecar 仅对照，不作为独立真值
- 三个 provenance 各自独立 snapshot SHA-256
- 旧读取代码 SHA：gen_sidecar.py=`d57fe3e1`, proxy.py=`d398183a`
- 其余本地来源（DocOps、AgenticVBench、WorkArena）仍未接入

下一候选：**P0-06 SWE-bench Trajectory Adapter**，但 G0 仍需 P0-07/08/09；本次未启动。