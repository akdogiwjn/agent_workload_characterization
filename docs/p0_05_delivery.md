# P0-05 Applied Compute Adapter 与小样回归

状态：**DONE（小样范围）**，2026-09-10；G0/M1 未验收。

## 实际交付

- `adapters/applied_compute.py`：Applied Compute v1 normalize，严格输入校验（浮点/类型/溢出安全），Template + Metric IR（macro_template profile），复用 `template_lengths` 公式引擎，缺失值 `not_recorded`（非 `not_applicable`）
- `adapters/applied_checks.py` 与只读 `check-applied-samples` CLI：通过 catalog 对 AC-N2 做定位、记录哈希、逐字段校验、IR round-trip 和延迟总和核对
- `tests/test_applied_compute.py`：35 项合成回归（N=2 手算、N=0、缺失传播、零值保留、null/零区分、浮点初始拒绝、缺失键允许、超大整数溢出安全、向量/类型错误、三个来源身份不同、身份稳定、profile/trace_type、ingest round-trip/dedup/reject）
- [Applied Compute 语义文档](applied_compute_adapter.md)、[小样检查结果](../reports/quality/applied_sample_validation.json)

没有新增第三方依赖。旧 adapter 和 trie 代码只读参考，未导入或修改旧代码。

## 实际验证

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v         # 122 项通过
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples   # PASS
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples    # PASS（回归）
git diff --check                                                                    # 通过
```

实际 AC-N2 检查结果：

| 指标 | 预期 | 实际 | 状态 |
| --- | --: | --: | ---: |
| model_request_count | 3 | 3 | PASS |
| input_contexts | [6318, 12537, 13644] | 相同 | PASS |
| total_input_tokens | 32499 | 32499 | PASS |
| max_context_tokens | 13644 | 13644 | PASS |
| total_output_tokens | 1986 | 1986 | PASS |
| total_simulated_delay | 2.770s | 2.770s | PASS |

AC-N2 行 SHA-256：`33e3c44e163754576a4779ce70bc9f3a712055a7f58d892b7136947cfd0bce32`

三个 subtype 的第一行结构 smoke 均通过（agentic_coding N=11, code_qa N=7, office_work N=24）。

## 设计要点与修复

1. **缺失原因**：模板输入未知时总输入/最大 context/总输出标 `not_recorded`（不是 `not_applicable`），不因为缺少输入就声称指标不适用。
2. **浮点长度**：`6318.0` 等浮点值被严格拒绝（`type(value) is not int`），不再静默截断为整数。
3. **可选标量**：`input_prompt_length` 和 `final_assistant_response_length` 字段允许缺失，缺失时表示为 null 而非拒绝。
4. **超大整数保护**：delay 的 `float(value)` 转换被 try/except OverflowError 保护，不会中断整个批次。
5. **未知键拒绝**：六字段之外的新字段会被拒绝，暴露源格式变化。

## 边界与下一步

- 没有全量 ingest、不创建正式 normalized 批次
- 不运行 trie client、不下载模型、不发 API 请求
- 三个 subtype 首行 smoke 无独立手算期望，不标为 gold regression
- `known_issues.yaml` 中旧 adapter 的 B1/B2/B3/B7 问题仍在旧代码中，新项目已有回归修正
- 仍缺一种本地 trace 的真实小样、macro/coverage 和试点选样，因此 G0 不勾选

下一任务候选：**P0-06 SWE-bench Trajectory Adapter**，但 G0 最小闭环仍需 P0-10 本地 trace、P0-07/08/09。本次未启动。