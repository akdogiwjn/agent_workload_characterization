# Trace IR v0.1：表示、验证与迁移

历史版本说明：P0-04 已升级当前公共模型至 [v0.2](ir_v0_2.md)，保留本文的 v0.1 设计约定；当前 reader 不会静默读取/迁移 0.1 输入。

本设计实现 P0-02 的最小契约，不复制第三方或旧工程表结构。语义依据为 [trace_contract.md](trace_contract.md)；Python 公共模型名为 `agent_workload_characterization.ir.TraceDocument`，原 v0.1 结构 Schema 已归档为 [trace-ir-v0.1.schema.json](../schemas/trace-ir-v0.1.schema.json)。

## 验证入口与范围

`validate_json(str | bytes)` 先拒绝重复 JSON key、NaN/Infinity，再严格验证类型、引用和图关系。`TraceDocument.model_validate(dict)` 适合程序内已有对象；JSON 输入应使用前者。数值字符串、布尔值冒充计数/时间、未知字段和未知 Schema 版本均拒绝。

生成的 JSON Schema 采用 Pydantic 的 Draft 2020-12 表示，只覆盖结构；跨记录 ID、引用、循环、证据传播等属于 Python 语义校验。仅通过第三方 JSON Schema 校验器不等于通过 IR 验收。本轮未安装独立 JSON Schema 校验器；测试验证已提交 Schema 与模型生成结果一致。

Python 模型是解析后的可变对象，校验发生在构造/读取时；修改后须重新经过 `validate_json`，不能将原地修改的对象当作仍已验收。当前实现一次读取一个闭合 JSON 文档，不是大文件流式 ingest。

## 文档与逻辑实体

文档带 `schema_version`、`profile`、`trace_type` 和 provenance。各实体数组可以省略；省略表示没有提供记录，不表示真实数量为零。一个文档可含多个 run，也可仅有模板或未绑定请求；不能强迫模板产生 run。已知零计数须用证据明确的 Metric 表达。

| 数组/结构 | 身份及用途 |
| --- | --- |
| provenance | source_id、snapshot_id、source_record_ref、adapter_version；实体通过 provenance_id 引用 |
| tasks / attempts / runs | 任务、配置对应 attempt、运行；三个状态轴只放在 run，不互相推断 |
| agents / requests / events | Agent 树、模型请求、Tool/一般 span/phase/lifecycle；request 可保留完整 prefix hashes |
| jobs / sessions | 异步作业与持久会话，与 Tool 调用分离 |
| processes / resource_scopes | 防 PID 复用的进程身份、资源边界与包含层级 |
| metrics | 数值、单位、scope、aggregation、denominator、证据、缺失原因、字段/公式与输入指标 |
| templates | 无执行时间轴的声明长度、源长度定义和缺失原因 |
| clocks / links / replay | 时钟、带证据的多对多关联/依赖、原 trace 与 replay spec 引用 |

每个实体的 `id` 对应所属数组的语义身份，例如 `requests[].id` 即 request_id，`events[].id` 即 event_id；不重复储存别名字段。所有 ID（含 provenance、clock、metric）在文档内唯一，完全相同的重复记录也拒绝，避免隐含重复计数。

来源引用是 opaque locator，可以是文件+行号、ZIP+member、上游稳定记录键等。Schema 不访问 locator，也不保证它实际存在；catalog/adapter 负责来源查证。adapter_version 必须明确，即使手工 fixture 也使用 `manual-fixture/1`。

稳定身份规则为来源命名空间 + 稳定 source record key + 实体角色/局部身份。task 的原始键不足以唯一标识 run；必须保留可区分模型/配置/attempt 的源运行身份。绝对本机路径不能是唯一身份依据。P0-03 已实现稳定 ID 工具、批次内去重与同输入批次幂等，详见 [Adapter 框架](adapter_framework.md)；跨来源/版本的全库视图选择和冲突解决仍未实现，不能仅从文档内唯一性推导已经实现。

## 关系语义

`parent_id` 仅用于同类 Agent、Event 和 ResourceScope 的单父包含树，禁止自指、环、跨 run 和已知同钟边界越界。未知边界不推断。Request/Event 的 agent 必须属于同一个 run。不同运行的常驻服务跨 run 共享目前需在上层批次设计中另行建模，不通过绕过本版本检查实现。

`depends_on` 的 source 是后继 Event，target 是前驱 Event；resolved 链接构成 DAG。已知同钟 native 边界时，后继不能早于前驱完成；跨钟或未知边界只验证图结构，不声称已验证时序。该类型表达完成依赖；流式 start-to-start 等新语义需显式扩展类型。

`submit/poll/wait` 从 Tool Event 到 Job；`session` 从 Event 到 Session；`scope_tool` 从 ResourceScope 到 Tool Event；`scope_process` 从 ResourceScope 到 Process。每条关联带 status、method、evidence_ref。unresolved 链接只表示候选关系，不进入确定依赖图，也不能作归因依据；端点本身仍必须在文档中存在。

未匹配模型请求使用 `run_id=null`、unresolved association 和 batch_id，不制造占位 run。无法从来源获取的 agent_id 可以为空。部分树缺父节点时保留父源键的 provenance，但不能在 parent_id 填入悬空引用或推造父实体。

共享 scope 可关联多个 Tool，资源指标只记录一次并指向 scope；exclusive_scope 不允许将同一完整 scope 直接归给多个已关联 Tool。submit 返回、job 完成、scope 生命周期分别记录，不能以 Tool interval 代替全部生命周期。当前没有资源分摊、collector 或 CPU 计算器。

## 时间与指标

Interval 的起止为同一个 clock_id 下的整数纳秒；未知端点必须为 null 并记录 missing_reason。完整的零长度区间合法；完全未观测可省略 interval，表示无边界证据。Clock 保存来源、原始精度以及可选 UTC anchor、校准方法/误差和采集延迟。单位换算不提高精度。本版本不执行跨时钟换算，即使提供 anchor 也不自动作精确相减。

Metric 的 null 必须对应 unavailable + missing_reason，真实零保持非空。derived 必须引用输入 Metric，输入 unavailable 不得产生精确结果；template_parameter 和 estimated 不能升级成 measured/derived。单位是非空的来源/契约名称，不提供未经验证的自动换算；任意公式本轮不执行，也不能由 Schema 判断科学合理性。

`aggregation` 要声明 main/all-agents、single_call、run_aggregate 等范围；`denominator` 写适用对象/分母定义，不等于已实现 coverage 报告。counter 要带 counter_epoch，避免 scope 重建或计数 reset 被视为连续计数；sample_time 用 Interval 表示采样点（start=end）或观测窗。gauge、peak、counter 不互换，父 inclusive scope 不与子 scope 简单累加。这些聚合规则还需 P0-08/09 和 P1 验证，通用模型不会识别所有错误公式。

`metric_contracts.py` 仅提供两个纯函数作为手算契约：

- `template_lengths`：N+1 completion、上下文递推、输入/输出总长；返回值统一是模板参数，缺长度传播 null，源单位不擅自升级为 token。
- `interval_totals`：同钟、native、闭合区间的 work、busy union、work-busy（多重覆盖冗余时间）、observed span。后者不是可信 run elapsed；三个以上重叠时 work-busy 不等同“至少两项忙碌的时间”。空集返回不可用，跨钟/开放区间拒绝精确计算，调用方以后需明确 coverage 策略。

上述函数输出是测试用摘要，不是可直接落盘的 Metric 或完整报告；adapter/analyzer 落盘时必须补全 Metric 的 provenance、分母与缺失原因。

## Profile 与 Replay 边界

macro_template 必须有模板，不接受伪造的 clocks、run、请求或系统实体；metric 仅允许模板参数或不可用。semantic_trace 不接受进程/scope；resource_trace 至少有一个进程或 scope，但不保证逐 Tool 归因。replay_trace 必须带 original_trace_ref、spec_ref、mode，trace_type 必须保持 replay。其余 profile 可以保留 unknown trace_type，是否可进入 cohort 由后续质量门槛决定。

Replay spec 这里只是版本化外部引用，不是可执行规范；环境快照、命令、文件初态、网络替代、保真验证与 executor 均在后续任务实现。profile 合法不等于 replay 可执行或保真。

## 物理存储与版本迁移

当前 JSON envelope 是闭合调试/测试视图，不要求每个 run 都单独生成文件。批量存储将按 source_id/snapshot_id/profile/schema_version 等分区，把各实体行与 links/metrics 分开或按列存嵌套字段；选择 Parquet 后也必须保留全部身份和来源引用。run 切片必须包含依赖的 provenance/clock/task/attempt/共享实体闭包；不得因切片复制共享资源后跨 run 求和。模板和 unassigned request 属于来源/批次，不塞入假 run 分区。物理表数、分区策略和导入导出实现留给 P0-03 及后续批量验证。

IR schema_version 与 Python 包版本、adapter_version 独立。v0.1.0 尚无历史格式转换器。更改单位、身份、关系含义、必填字段或证据规则必须升级 Schema，保留旧输入并显式迁移到新输出；即使新增可选字段也须检查旧 reader 的 extra-forbid 策略，不宣称自动兼容。禁止读失败后静默降级、忽略字段或覆盖原 trace。迁移须有旧/新 fixture、血缘与重复执行测试。
