# AgentX + Applied Compute macro analysis v1

仅使用本地固定版本输入；未联网、未执行轨迹或 workload。两类来源不合并统计。

## 输入与性质
- AgentX revision `8fecd2fc56694469f758f0afbbb6335ad3043740`：393 traces、68,266 model requests（主 `28,444`，subagent 内部 `39,822`），显式 subagent groups `1,697`。这是过滤后的 request-flow/proxy corpus，不是完整工具执行日志。
- Applied Compute revision `6918da7915e3ae57ce3750a375ef50e41cad2b36`：agentic_coding_8k=8,192 templates（有效 8,192）, code_qa_8k=8,192 templates（有效 8,192）, office_work_8k=8,192 templates（有效 8,192）；是 production-derived template，不是原始 Agent/Office execution trace。

## AgentX 主要观察
- 请求级 pooled input tokens median `88768.0`、output median `376.0`；trace 总 token 另按 trace 汇总，不能与 pooled 请求分布混用。
- 每 trace 请求数由实际记录决定；subagent fan-out 只依据显式 marker，未从名称或时间恢复父子关系。
- `t`/`api_time` 只在各自 source-relative scope 内形成记录区间；重叠是记录区间重叠，不是 CPU/GPU 并发。
- hash_ids 只在同一 trace 的相邻记录中检查前缀共享，不推导 cache 命中率或性能收益。

## Applied Compute 主要观察
- `agentic_coding_8k`：turn median 13.0；初始 prompt median 6448.0 token；assistant/tool/final median 分别为 112.0/162.0/416.0 token；simulated latency median 0.429 s（per-turn pooled）。
- `code_qa_8k`：turn median 9.0；初始 prompt median 1515.0 token；assistant/tool/final median 分别为 94.0/678.0/1044.0 token；simulated latency median 0.371 s（per-turn pooled）。
- `office_work_8k`：turn median 37.0；初始 prompt median 8841.0 token；assistant/tool/final median 分别为 33.0/202.0/1173.0 token；simulated latency median 0.602 s（per-turn pooled）。

## 可支持与缺口
- 可支持：请求/trace 规模、显式 subagent 结构、token 字段、有限 source-relative 区间、模板轮次/长度/模拟 delay。
- 不可支持：CPU、内存、I/O、热点、真实工具耗时、思考时间、真实 API 账单、模型排名或类别代表性。
- AgentX 与 Applied Compute 不形成共同总体；Applied 的派生 token 不能当真实 API 累计输入。

[summary.json](summary.json) · [per_trace.jsonl](per_trace.jsonl) · [per_template.jsonl](per_template.jsonl) · [manifest.json](manifest.json)
