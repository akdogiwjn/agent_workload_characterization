# P0-02 交付记录

状态：DONE（最小 IR 契约），2026-09-10；不代表 G0/M1 通过。

## 实际交付

- `src/agent_workload_characterization/ir.py`：公共模型、严格 JSON 读取、身份/引用/图/时间/证据/profile 校验。
- `schemas/trace-ir.schema.json`：由同一公共模型生成的结构 Schema。
- `metric_contracts.py`：模板长度与同钟并发区间的纯函数契约，无 adapter 或报表 pipeline。
- CLI 新增只读 `validate <JSON>`，合法返回 0、无效/不可读返回 1、参数错误返回 2；不回显原始输入值。
- 两个显式 synthetic JSON fixture 和程序内 resource/replay/关系图反例；数字示例不冒充生产采集。
- [IR 表示及迁移约定](ir_v0_1.md)，以及 README、任务状态、方法论当前进度更新。

## 依赖决定

P0-01 交付时没有第三方运行依赖。P0-02 因公共模型与 Schema 需要新增唯一运行依赖 `pydantic>=2.13,<3`，不引入 pandas/polars/pyarrow 或第二套校验框架。使用本机已有 Pydantic 2.13.4 / Python 3.11.6，没有执行下载、安装或环境升级。测试仍使用标准库 unittest；帮助/版本路径延迟加载模型依赖。

## 实际验证

从项目根执行：

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization validate tests/fixtures/ir/template_n2.json
PYTHONPATH=src python3 -B -m agent_workload_characterization validate tests/fixtures/ir/semantic_open.json
git diff --check
```

42 项测试通过（原骨架 10 项 + IR/指标/CLI 32 项），覆盖四种 profile round-trip、缺失身份、重复 ID、悬空/错误类型引用、自指/包含环/依赖环、边界与时钟、null/零/非法数值、三轴状态、未绑定请求、PID 重用、共享 scope、counter epoch、模板证据传播、N=0/N=2/缺长度/向量长度冲突、并发 work 与 union、Schema 生成一致性及只读 CLI。

N=2 手算结果：3 次 completion，上下文 `[6318, 12537, 13644]`，总输入 32499，总输出 1986；仍为 source_length 模板值，源单位待 P0-05 固定版本核实。并发样例 `[0,10]` 与 `[5,15]` 得到 work=20、busy=15、冗余 overlap=5，不把 work 当 wall time。

## 没有完成或执行的事项

- 不实现来源 adapter、catalog locator 解析、流式 ingest、跨批次去重、Parquet 存取、版本迁移器；这些仍属后续任务。
- 不转换旧 trace、不运行旧 pipeline、不搬迁数据、不修改 references 第三方内容。
- 不执行 CPU/cgroup/OS 测量、远端请求、Replay、benchmark 或 Scale。
- 不宣称 source locator 已被本轮重新全量查证，也不以 synthetic fixture 替代 P0-04/05/10 的真实小样回归。
- 不执行 pip 安装/构建或独立 JSON Schema 引擎验证；已验证源码入口和模型/Schema 一致性。
- Schema 不验证任意公式、来源真实性、覆盖率、真实资源归因或科学结论；具体约束与存储限制见 IR 文档。

下一任务为 P0-03 公共 Adapter 框架。应先实现只读发现/检查、稳定身份与新输出路径保护，再进入来源小样；本次未启动 P0-03。
