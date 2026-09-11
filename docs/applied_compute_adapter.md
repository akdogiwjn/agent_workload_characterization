# Applied Compute Adapter 设计

## 来源与身份

三个来源文件映射到三个独立 source_id：
| source_id | 原文件名 | 记录数 | 最少的 N |
| --- | --- | ---: | ---: |
| `applied_agentic_coding` | `agentic_coding_8k.jsonl` | 8,192 | 1 |
| `applied_code_qa` | `code_qa_8k.jsonl` | 8,192 | 1 |
| `applied_office_work` | `office_work_8k.jsonl` | 8,192 | 4 |

通过 Catalog 的 `locator` 定位，不硬编码 data_root 或复制文件。

## 身份设计

每个模板的身份使用 `stable_id(source_id, "template", source_id, "line:N")`。`line:N` 是源文件内的稳定记录位置（1-based），不包含文件系统路径、adapter 版本或 snapshot。这样文件搬家、同源重 ingest 时保持身份；同内容不同源行保留发布样本的 multiplicity。

## 输入校验

| 字段 | 类型 | 校验规则 |
| --- | --- | --- |
| `num_turns` | 非负整数（必填） | 拒绝 bool、字符串、负数、浮点 |
| `input_prompt_length` | 非负整数或 null（可选） | 拒绝 bool、负数、浮点、数值字符串；缺失或 null 视为未知 |
| `assistant_response_length` | 非负整数列表（必填） | 长度必须 == N；拒绝标量、错长度 |
| `tool_call_output_length` | 非负整数列表（必填） | 长度必须 == N；拒绝标量、错长度 |
| `tool_call_latency` | 非负有限数值列表（必填） | 长度必须 == N；拒绝 NaN/Inf、负数、bool、超大整数 |
| `final_assistant_response_length` | 非负整数或 null（可选） | 同 initial；缺失或 null 视为未知 |

未知键会立即引发错误，不静默忽略。

## IR 映射

- profile=`macro_template`；真实 trace_type=`production_derived`，合成=`synthetic`
- 只生成 provenance、Template、Metric；不生成 runs/tasks/agents/requests/events/clocks
- 长度依据 trie 固定 commit `6918da7915e3` 的 README+types.py：字段单位是 token，N 个 tool-use turns 对应 N+1 completions
- 累计公式：`I[0]=initial`；`I[i+1]=I[i]+O[i]+R[i]`；总输入 `sum(I[0:N+1])`；总输出 `sum(O)+final`；final 不再加入不存在的下一个请求
- 时延向量每个 turn 一个 Metric（`simulated_tool_delay`，`tool_turn:N` 聚合），单位 s
- 每轮 context 作为 Metric（`completion_context`，`completion:N` 聚合），单位 token
- 所有已知值标 `template_parameter`；null 对应 `unavailable` + `missing_reason=not_recorded`
- 缺一项必要输入只传播到受影响指标，不连带破坏无关指标

## 计算复用

使用 `metric_contracts.template_lengths()` 公式引擎，与 IR `Template` 模型对齐，不复制旧 adapter 或 trie client 的分歧逻辑。