# AgentX v7 Adapter：小样语义与边界

实现位于 `adapters/agentx.py`，类 `AgentXAdapter`，版本 `agentx-v7/0.1.0`。输入为本地已登记的 `agentx_256k/traces.jsonl`，依据本地 dataset card 和实际 AX-7 / AX-SUB 记录；旧 adapter 仅参考结构，不复用其时间、turn、Tool 或 prefix 聚合错误。

默认输出 `semantic_trace / production_derived`；合成测试显式传入 `config={"trace_type": "synthetic"}`。配置不接受其他来源标签或未知选项。数据经过版本、请求规模、图片、分类调用及 256k cap 等上游筛选，不代表完整原始生产 session 或生产总体。

## 身份与结构

- run_id 来自 source_id + 源 session `id`；未知 task/attempt 不填成同一个 session ID。源 session ID 的稳定性只对当前来源命名空间成立，不自动跨来源合并。
- 主 Agent 使用明确的主 Agent 身份；子 Agent 由源 `agent_id` 标识，保存 source_agent_id/type/status。嵌套关系生成单父树，重复源 Agent ID 拒绝，不生成自指关系。
- Request ID 使用 session + 源数组 JSON pointer；这是缺少请求原生 ID 时的局部定位身份。移动文件/重复 ingest 不改变它；重新筛选或重排源数组后不能据此推导跨 snapshot 的请求等价，run 身份仍不随 snapshot 变化。
- source_request_type 原样保留 s/n，不猜测其更细的服务端执行含义；请求的 model_name 原样保留。未知请求类型拒绝，不把未知类型当 LLM 调用。
- 子 Agent 分组另有 span，保留分组 duration_ms 和状态。source_total_tokens / source_tool_use_count 仅在该 source_group scope 下保留，不加到逐请求 token 或全 run Tool 数中。
- 不创建虚构 Tool、Process、ResourceScope、causal/join 链接，也不由分组 completed 推导 run completed。

关联依据引用稳定 provenance ID + JSON pointer；provenance 自身保存实际 `line:N`。这样重复源行的行号仍可追溯，但不让位置差异被误判为运行内容冲突。

## 时间、缺失与范围

子请求的 `t` 已经是 session-relative，**不再加父 Agent 起点**。每个 session 使用独立 source_relative clock；不标成本机 monotonic，也不造 UTC anchor。源数据卡没有给出计时精度，因此 precision_ns=null / not_recorded。

将 t、api_time、ttft、think_time 的秒值归一化为整数纳秒（Decimal 字符串表示，half-even 舍入），分组 duration_ms 乘 1e6。此处仅改变表示单位，不增加精度。Interval 的 native_event 表示直接采用已发布源事件坐标，不保证其是本机真实边界；proxy 派生和上游过滤/统一偏移的限制保留在 Clock.source 与 provenance。

起点或 latency 不可用时端点为 null / not_recorded，不填零，不把缺日志擅自判为 timeout/censored。真实 latency=0、token=0 保留。start 缺失但 api_time 存在时，可累计源 API latency，不能计算区间并集。

每请求记录 input/output、API latency、源 TTFT、源 think_time、源 start 和 presence 指标。think_time 不被重新命名为 Tool latency 或 Agent 开销。所有度量附 scope、单位、源字段、证据和分母；缺失显式 unavailable。

run 汇总分别输出 `main_agent` 与 `all_agents`：

| 指标 | 定义/限制 |
| --- | --- |
| model_request_count | 保留的 s/n 请求数，不是 turn_count；重试保留源发布口径 |
| input_tokens / output_tokens | 同范围逐请求求和；有必要输入缺失时整个精确汇总为 null，不拿部分和冒充全量 |
| max_context_tokens | 同范围保留请求的最大 `in`，不是运行最初 prompt 或整个未筛选 session 的峰值 |
| model_work | 同范围 API latency 的累计和，不是服务端纯推理或本地 CPU 时间 |
| model_busy | 同范围闭合源请求区间的并集长度 |
| model_overlap | work - busy 的多重覆盖冗余量，不是 critical path |
| observed_span | 同范围已知请求首尾跨度，不是可信 run_elapsed |

并集/跨度要求所选请求的边界完整；否则 null，不静默过滤开放请求。显式空请求集合的计数/累计和为 0，最大上下文和时间跨度不可用。subagent_count 统计保留分组；总 turn_count、Tool 调用数、run_elapsed、local_cpu_time 保持 unavailable，不从缺失值推导低负载。

## Prefix 与内容边界

保留完整 hash_ids 向量、block_size、hash_id_scope。整数 hash ID 无损转为十进制字符串适配 IR；不截断，不用长度替代内容。缺向量不造空向量；存在向量但缺少必要 scope/block 元数据时拒绝该源记录。local scope 的 hash ID 不拿去跨 session 做 cache reuse 推断。

没有复制原始生产记录进测试仓库；合成 tests 使用声明过的数值例子。原始 source 保留在原位置，行号与哈希可复查。尚未实现缓存复用分析、Tool 分类、全量统计或来源覆盖报告。

## 小样复核命令

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples
```

命令通过 sources.yaml 与 sample_candidates.yaml 定位 AX-7/AX-SUB；读取至第 307 行，仅解析并规范化选中的两行，校验原 record ID、catalog 的手算请求/token 预期、完整 prefix 向量、unknown 指标和 IR round-trip。输出 JSON 到 stdout，失败返回非零，不写 batch。读取前后检查源文件 inode/size/mtime；快照只声明所选原始行的 SHA-256，未重新核验整个文件的历史 SHA。

该命令不是全量 ingest，默认 unittest 也不读取旧数据。真实检查摘要见 `reports/quality/agentx_sample_validation.json`；含具体源 locator，不应未经隐私/路径审查直接当发布数据集。
