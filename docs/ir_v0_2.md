# Trace IR v0.2 与显式迁移

P0-04 的实际 AgentX 接入发现两项最小模型缺口：请求模型/源类型无法表达、未知源计时精度被要求填正整数。为避免信息丢失或伪造精度，Schema 升级至 **0.2.0**，不静默改变 0.1.0 的含义。

公共模型仍为 `agent_workload_characterization.ir.TraceDocument`；当前 [结构 Schema](../schemas/trace-ir.schema.json) 只接受 0.2.0。[0.1 Schema 快照](../schemas/trace-ir-v0.1.schema.json) 保留不覆盖。Python 包版本、adapter 版本与 IR 版本独立。

## 变化

- Request 增加可空 model_name、source_request_type，不用数值 Metric 塞入字符串标签。
- Agent 增加可空 source_agent_id、source_agent_type、source_status；源状态不替代运行的三个状态轴。
- Clock.precision_ns 允许 null，并且必须附 precision_missing_reason；精度已知时不允许附缺失原因。其他校准/引用/图/证据规则保持。

其他实体、物理 JSON envelope、共享资源与聚合约定继续适用 [v0.1 设计](ir_v0_1.md) 和 [Adapter 框架](adapter_framework.md)。新增字段非必填不表示旧 reader 会自动接受；extra-forbid 仍然生效。

## 显式迁移 API

`agent_workload_characterization.migrations.upgrade_v0_1(payload)`：

1. 严格读取旧 JSON，要求 schema_version=0.1.0。
2. 拒绝旧版本不允许的新增字段，以及旧版本不允许的 null clock precision。
3. 改为 0.2.0，再执行全部共享结构与语义验证，返回新模型。

函数不写文件，不修改原字符串/字典，不改变 provenance 或实体身份；对相同旧输入重复执行得到相同结果。正常 validate 不自动升级旧输入；向迁移函数再次传入 0.2.0 也会拒绝，避免隐式多次迁移。

本轮仅在合成测试中验证迁移，无旧批次被扫描或改写。P0-03 的批次 spec 包含 schema_version，因此将来新转换自然产生不同批次；不能覆盖旧批次或合并版本后重复计算 run。
