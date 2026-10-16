# SWE-rebench behavior v1

本报告分析已保存的第三方 normalized Coding corpus，不称官方原始轨迹，不执行记录中的命令。

## 规模与完整性
- `85` 个 gzip shard，`9435` 条 trajectory，`111` 个 task，`17` 个 participant；源 manifest 声明 `9435` rows。
- 解析错误 `0`，重复身份 `0`；每个 participant 覆盖 `111` 个共同 task，每个 run index 的记录数为 111。
- 压缩文件 bytes/SHA 由 source index、获取 manifest 和本地回读核对；source content_sha256 按解压后的 JSONL bytes 核对。传输日志不完整单独保留。

## 数据支持的观察
- 工具调用总数为 `598,148`，中位数 `53`、IQR `58.0`；原生名称最高为 `bash_terminal=511,104, shell=16,030, Bash=15,209, grep=11,850, read=11,575.`
- 有限分类计数：Shell/Interpreter/Execute `536,887`，Read/Search `37,475`，Edit/Write `15,391`，Test `5,458`，Other `1,392`，Unknown `1,545`；分类分母是 tool_call 事件。
- 主要顺序转换为 `Shell/Interpreter/Execute→Shell/Interpreter/Execute=513,352, Read/Search→Read/Search=29,206, Edit/Write→Edit/Write=8,188, Shell/Interpreter/Execute→Read/Search=5,587, Edit/Write→Shell/Interpreter/Execute=5,283`；仅按保存事件顺序统计，Unknown/不明并发边界不跨越。
- evaluation status 为 `failed=4,683, resolved=4,751, skipped=1`；agent_exit_status 为 `agent/agent_proxy/inference_server/prompt_too_long=3, submit=7,212, submitted=2,220`，两者分列。
- 同 task×participant 的五次 run 用原始点、n、median、IQR 表示；候选中重复工具调用波动最大的组合见 `measurement_candidates.json`，不作因果解释。

## 后续测量候选
见 `measurement_candidates.json`。候选角色可重叠，不构成实验授权。

## 限制
可支持工具组成、调用/返回数量、有限顺序和重复波动；不支持 CPU/内存/I/O/热点、单工具耗时、等待/思考时间、因果解释、模型排行榜或类别代表性。resolved 不等于正常终止，无法确认 termination 时不从调用数推断 LimitsExceeded。

机器结果：[summary.json](summary.json)、[逐 trajectory 指标](per_trajectory.jsonl)、[候选](measurement_candidates.json)。
