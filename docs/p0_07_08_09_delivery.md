# P0-07/08/09 联合交付（最小集）

> **历史记录（superseded 说明）**：本文早先各轮返修描述中，曾把 model_busy 误映射为
> observed_span、模板 CPU 误标 applicable-missing、测试数量引用过 149/162/168/170/175 等
> 中间值，并以 v1～v5 报告为当时依据；这些错误输出均已在后续轮修正，**不构成本文当前的
> 验收依据**。当前依据：`reports/macro/macro-pilot-v6/`、175 项隔离测试与显式真实小样命令；
> 本轮（P0-07 收尾）另见 [p0_07_g0_delivery.md](p0_07_g0_delivery.md)。历史报告包字节未改写。

状态：**PARTIAL（P0-07）/ DONE（最小集，待验收，P0-08/09）**。评审未通过，G0/M1 不通过。返修已按评审意见完成，需重新验收。

## 实际改动文件

**新增代码**
- `src/agent_workload_characterization/analyzers/`（loader/metric_registry/macro/coverage/analyze/__init__）
- `tests/test_macro.py`（13 项）
- `data/catalog/macro_pilot.yaml`（固定 selection）
- `workload_catalog/{coding,office,assistant,video}.yaml`
- `docs/macro_coverage.md`、`docs/benchmark_selection.md`、`docs/agent_landscape.md`
- `reports/quality/benchmark_matrix.csv`、`reports/quality/g0_review.md`

**修改**
- `src/agent_workload_characterization/cli.py`（新增 `analyze-macro-pilot` 命令）

## 实际命令与退出码

```text
PYTHONPATH=src python3 -B -m unittest discover -s tests -v        → 162 OK
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples      → PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples     → PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization check-videoweaver-samples → PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization analyze-macro-pilot       → PASS（只读）
PYTHONPATH=src python3 -B -m agent_workload_characterization analyze-macro-pilot --output-dir reports/macro/macro-pilot-0.1.0
git diff --check                                                                       → OK
```

## 固定输入及哈希

| 输入 | 路径 | SHA-256（catalog 全文） |
| --- | --- | --- |
| sources.yaml | data/catalog/sources.yaml | 97bc6dbfe708293618219cbd4d7b396ae8bff6a38eb3aa0533c8ce1c3f487150 |
| macro_pilot.yaml | data/catalog/macro_pilot.yaml | 6462a2192196868021d5cc3ff17e885abab230143afa59808a2d7beb0e9ca2d7 |

样本文件哈希见 `reports/macro/macro-pilot-0.1.0/selection_ledger.jsonl`（每样本逐文件 SHA-256）。

## 每层实体/分母核算

主 cohort：3 个真实语义 run（AX-7 / AX-SUB / VW-LONG）+ 1 个模板（AC-N2）
+ 1 个未绑定请求（AUX-INCOMPLETE，独立分母）。
已绑定实测请求数 = 7 + 21 + 70 = **98**；3 次模板 completion、1 条 unassigned 分列。

macro_summary.csv（n_valid>0 行）：
- model_request_count n_valid=4（3 run + 1 template），min=3 max=70
- total_input_tokens n_valid=2（AC 32499 + VW 4041546）
- total_output_tokens n_valid=2
- max_input_context n_valid=1（79937，VW input_tokens 口径）
- max_source_context_tokens n_valid=1（80378）
- total_api_latency_s n_valid=1（401.421469s，proxy 边界，非 CPU/E2E）
- tool_call_count n_valid=1（88，VW）
- subagent_count n_valid=2（AX-7=0, AX-SUB=1）
- observed_span n_valid=2（AX 两个 run 的 model_busy）

coverage：run_elapsed/local_cpu_time/tool_cpu_time 对所有真实 run 为 applicable 但
n_missing=1（无采集证据），对模板为 not_applicable；均显式输出，不消失。

## Gold 与负例

- P50 公式、min/max/mean、interval_totals（union/work/overlap/nested/triple/open/cross-clock/receipt）
  均有手算 fixtures（test_macro.py）。
- 真实回归：AX-7/AX-SUB 请求数 7/21、input 194368/818752、output 4097/3949；
  AC-N2 请求 3、input 32499、output 1986、max 13644、delay 2.770s；
  VW-LONG 请求 70、input 4041546、output 28631、max input 79937 / source context 80378、
  tool 88、manifest wall 1616.424s；API 累计 401.421469s。
- 负例：P50 空/singleton、区间跨 clock/open/receipt 拒绝、gold 期望缺失失败、
  malformed/缺文件、softlink 逃逸、重复身份冲突。

## 输出路径与哈希

报告包：`reports/macro/macro-pilot-0.1.0/`
- manifest.json（含各文件 SHA-256）
- macro_summary.csv、trace_coverage.csv、selection_ledger.jsonl、
  quality_checks.json、summary.md

## 不能证明什么

- 不是生产代表性分布、不是 CPU/架构结论、不是完整 quality 体系。
- 未运行 benchmark、未采集 cgroup/perf、未发 API、未创建正式 normalized 批次。
- 未做 P0-06；Tool/Phase classifier、P90+、跨源去重、试点执行属后续。

## 下一依赖

- P0-07 试点执行仍需授权（Docker + API key + 预算批准）。
- G0 五条证据见 `reports/quality/g0_review.md`（仅 READY_FOR_REVIEW）。
- 验收通过后候选 P1-00 只读可行性检查。
