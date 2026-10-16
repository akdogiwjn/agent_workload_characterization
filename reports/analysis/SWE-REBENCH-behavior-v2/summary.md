# SWE-rebench behavior v2

第三方 normalized Coding corpus 的流式离线行为分析；不称官方原始轨迹，不执行记录命令。

## 规模与身份
- `85` 个 shard、`9435` 条 trajectory、`111` 个 task、`17` 个 participant；每个 participant 的 run 分布从实际记录生成。
- 解析/哈希隔离错误 `0`，重复 task×participant×run 身份 `0`；source content hash 按解压 JSONL bytes 核对。

## v2 数据观察
- 原生 tool_call 总数 `598,148`；tool_result 总数 `616,980`；差额 `18,832`。关联汇总：带 ID 的 call `598,148`、带 ID 的 result `589,061`、缺 ID result `27,919`、仅有 call ID `9,087`；因此差额 = 缺 ID result − 仅有 call ID，未强行一一配对。
- 原生工具名称最高：bash_terminal=511,104, shell=16,030, Bash=15,209, grep=11,850, read=11,575.
- 保守活动分类：Read/Search=98,888, Edit/Write=17,757, Test=112, Interpreter/Execute=3,409, Other=1,392, Unknown=476,590；通用 shell 未被自动当作具体读写活动。
- 保存的 tool_call 顺序转换最高：Read/Search→Read/Search=53,726, Edit/Write→Edit/Write=8,431, Read/Search→Edit/Write=3,449, Edit/Write→Read/Search=2,014, Interpreter/Execute→Interpreter/Execute=1,305；不称实际执行顺序，不声称已检测并发。
- evaluation status：failed=4,683, resolved=4,751, skipped=1；agent_exit_status：agent/agent_proxy/inference_server/prompt_too_long=3, submit=7,212, submitted=2,220。
- `duration_ms` 仅做字段可用性计数，未解释为 CPU、完整 wall 或精确执行区间。

## 候选与边界
候选位于 `measurement_candidates.json`，角色可重叠，不构成实验授权；participant 间语义覆盖差异不用于排名。

## v1→v2
- v2 保留原生接口计数和基础 task/participant/run 覆盖；活动语义改为有限命令证据，Test 边界收紧，重复 ID/多返回/孤立返回/缺 ID 单独报告。
- v1 的“Shell 即执行活动”、Test 前缀识别、集合丢 ID、以及“已排除并发边界”的表述撤回。

## 限制
不支持 CPU/内存/I/O/热点、单工具耗时、等待/思考时间、因果解释、模型排名或 Coding 类别代表性。resolved 不等于正常 termination，usage 不等于账单。

[summary.json](summary.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [measurement_candidates.json](measurement_candidates.json) · [manifest.json](manifest.json)

- 语义覆盖率按 participant 在全部已解析 tool_call 事件上计算；各 participant 的比例与 Unknown 原因见 `summary.json`，不用于跨 participant 排名。
