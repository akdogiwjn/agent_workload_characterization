# v1 → v2 corrections

| 原问题 | 实际修复 | 影响 |
|---|---|---|
| 通用 shell 被直接归为执行类别 | 原生接口与有限活动语义分层；未支持命令保留 Unknown/Mixed | 活动计数和 Read/Test 候选收紧；原生调用总数不变 |
| Test 使用宽松 startswith | 按 executable、参数边界和 help/version 排除规则识别 | `pytest_fake`、`npm testing`、echo/grep/print 文本不再是 Test |
| ID 转 set 丢失重复 | Counter 保留重复调用/返回 ID，区分 1:1、非 1:1、孤立及缺 ID | 关联结论更细；调用/返回总计不被改写 |
| 序列实际只按保存调用顺序连接 | 明确命名为保存 tool_call 事件顺序；Unknown 打断；并发顺序 unknown | 撤回“已排除并发边界”表述 |
| 未盘点 duration_ms | 按 participant 统计 present/valid/zero/negative/invalid/missing 和 ID 关联 | 纠正“完全没有字段”，仍不开展耗时分析 |

## v1 撤回项
- 通用 shell 分类可代表具体读写/执行活动。
- Test 最高/最低比较可直接解释为测试活动密集度。
- 保存事件转换已排除不明并发边界。

## v2 仍可支持
- 111 task、17 participant、5 个 run 的实际覆盖与重复统计。
- 原生工具接口计数、保守活动类别、保存事件顺序转换、调用/返回差额和有限重复波动。
- `duration_ms` 字段存在性盘点；其语义仍 unknown。
