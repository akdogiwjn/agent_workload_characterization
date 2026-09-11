# Macro & Coverage 分析与指标契约（P0-08/09 最小集）

## 入口与接口

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization analyze-macro-pilot \
  --catalog data/catalog/sources.yaml --selection data/catalog/macro_pilot.yaml
# 默认只读；--output-dir 发布报告包到 reports/macro/<analysis_id>
```

实现：
- `analyzers/loader.py` — 共享加载：按 pilot selection 从实际原始文件经现有
  AgentX/Applied/VideoWeaver adapter/composer 生成校验后 `TraceDocument`，返回
  每样本 entity_id、文件 SHA-256、按规范聚合过滤后的 metrics。
- `analyzers/metric_registry.py` — 单一指标注册表（macro 与 coverage 共用）。
- `analyzers/macro.py` — 固定 cohort 的 min/max/mean/P50 汇总（n_valid 对齐 coverage）。
- `analyzers/coverage.py` — 每个 (definition, entity) 的分母核算。
- `analyzers/analyze.py` — 联合编排、报告发布与路径保护。

## 指标注册表

对每项记录 definition/entity_level/scope/unit/source 映射/evidence/capability。
最小支持：
- run/template 的 model_request_count、total_input_tokens、total_output_tokens、max_input_context。
- request 的 input/output tokens、input context、TTFT/API latency。
- 子 Agent 数与请求范围；可证明的 tool_call_count。
- observed_span、累计 API latency、manifest_reported_wall_time 各保留原定义。
- run_elapsed、local_cpu_time、tool_cpu_time 作为 capability-only 显式 unavailable，
  即使 IR 未发出 Metric 也输出覆盖行（缺项原因，不整项消失）。

## 分母与 missingness（固定定义）

- n_total = 该层选中实体数；run/template/request/unassigned-request/tool 各用自己分母。
- n_applicable = 指标概念适用实体数；CPU 对真实 run 适用但未采集计 missing；
  模板对 CPU 计 not_applicable。
- n_present = 适用实体中有非 null 值者；n_valid = 其中满足 unit/scope/evidence/关联者；
  n_excluded = 非 null 但不可用于统计者；n_missing = 适用但无值者。
- n_total = n_applicable + n_not_applicable；
  n_applicable = n_valid + n_missing + n_excluded；
  n_present = n_valid + n_excluded；
  coverage_ratio = n_valid / n_applicable（分母为 0 则 null 并说明）。

## 数值聚合

- 宏观只输出 n_valid 与 min/max/mean/P50；P50 为排序后线性插值 h=(n-1)*0.5。
- 对 0 个有效值全 null；1 个值允许摘要并标 singleton。
- 本次不输出 P90/P95/P99、置信区间、总体代表性排名。
- 整数计数/token 精确；浮点比较用预登记容差；JSON 输出无 NaN/Infinity。

## 时间与 phase（最小范围）

- 复用 `metric_contracts.interval_totals`；同 clock、闭合、native_event 才可用于
  work/union/overlap。
- 跨 clock、log_receipt、adjacent estimate、未闭合区间显式排除/不可用。
- 本次只保留原始 Tool/interface 标签及已观测频数；phase/operation category 标
  unsupported/unknown（完整 classifier 属 P1-06）。

## 身份与去重

- 只选择单一转换视图；重复 selector/文档明确拒绝或等价去重并记 ledger；
  同 ID 冲突必须失败。
- AUX-INCOMPLETE 为独立 unassigned 请求，不加入 VW-LONG run 分母。

## 限制

- 本最小集只覆盖 3 个真实语义 run + 1 个模板；不是生产代表性分布。
- 不做全来源总直方图、综合 score、CPU-heavy/light 标签。
- 完整 Tool/Phase classifier、P90+ 分位、置信区间、跨源去重和试点执行属后续任务。
