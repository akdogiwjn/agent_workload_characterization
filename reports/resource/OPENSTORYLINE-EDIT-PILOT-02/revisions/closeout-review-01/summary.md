# OPENSTORYLINE-EDIT-PILOT-02 收尾复核修订 01

本修订只做离线代码检查、raw字段核验和报告更正；没有启动API、模型、ASR、Agent、任务容器、渲染或verifier。原始评分与提交均未改。

## 正式结果与边界

- 正式剪辑和提交已完成；原版独立评分完整，reward **0.0** 保持不变。
- 原始 `agent-result.json` 与 `session-status.json` 仍为 `executing`，属主/权限未改。宿主 `runtime.execute` 返回码、完整attempt起点与目录初始值都没有被原入口持久化，继续标为 **unknown**；Agent工作窗口 1270.800s，cgroup采样窗口 1285.425s，两者不等于完整attempt wall。
- 收尾失败来自宿主试图写回容器属主的 `agent-result.json`（nobody，0644）；该权限错误中断了后续报告落盘。raw状态仍原样保留。MCP停止记录与容器删除核验保留于原始证据/收尾报告。

## 内存单位更正

- `memory.current`采样峰值：**6,517,669,888 bytes = 6.517669888 GB = 6.070053 GiB**。
- 内核memory peak：**6,944,976,896 bytes = 6.944976896 GB = 6.468014 GiB**。
- 此容器是cgroup v1：采样current来自 `memory.usage_in_bytes`，内核peak来自 `memory.max_usage_in_bytes`。raw bytes是基准。原四面板SVG内存轴为MiB，值按bytes/1,048,576绘制，图本身正确；无需重画。此前写成“6.52 GiB”的数值应以本修订表纠正。CPU平均0.404700 cores按有效采样区间1285.425s计算。
- 见[memory-correction.csv](memory-correction.csv)。

## 实际提交与RenderVideo来源

- 两个成功的RenderVideo候选均在session `env01-7a725fec0f2247fbae21ec08e2add618`；状态文件共同记录并指向 `render_video_1792682669.4529731`。冻结版本宿主入口按artifact `create_time` 选择最新成功产物，选中路径 `/workspace/output/.server_cache/env01-7a725fec0f2247fbae21ec08e2add618/render_video_1792682669.4529731/output_361c7a6c_1792682669473.mp4`。
- 选中媒体与提交 `output.mp4` 都为 1,887,666 bytes、SHA-256 `4cae03d385b76831d4c7e39e75b5724fc8818cba2aa315f6b4dfa2110d83f3bf`。另一个成功候选内容哈希相同，因此仅凭文件哈希无法区分副本来源；状态记录和冻结导出选择规则支持本次选择为 `render_video_1792682669.4529731`。原报告引用 `render_video_1792682621.7633991 was a recovery-script metadata-selection error; meta.json uses created_at, not create_time`；这是离线恢复脚本把`meta.json`中不存在的`create_time`当排序键造成的错误。
- `cuts.json`与同session最终PlanTimelinePro artifact `plan_timeline_pro_1792682573.151925` 的源区间补集一致；未重算剪切、渲染或评分。候选对照见[render-source-review.csv](render-source-review.csv)。

## 后续入口修复

- 后续正式入口把`agent-result.json`与`session-status.json`仅作为容器原始状态只读；宿主写入独立`host-finalization.json`、`agent-execution.json`和`run-report.json`。运行起点/预算在容器启动前原子落盘，目录前测完成即落盘，`runtime.execute`返回后立即保存返回码/timeout/终止信息。采样停止、容器删除、导出、报告及manifest分别记录；报告失败不阻断此前已执行的清理。
- render选择由Agent最终artifact ID和session状态共同确定，校验同session成功工具事件、最新时间线payload、媒体路径及源/目标SHA；恢复入口复用同一选择函数。缺路径、状态分歧或哈希不匹配时明确失败。
- 原报告、原始manifest、raw状态、提交、cuts、APPROVAL与冻结身份均未更改。冻结身份中的宿主入口hash对应改动前版本；本次修复仅适用于后续新身份，不回写历史身份。

## 交付

机器结果：[revision.json](revision.json)；输入/代码/输出清单：[input-code-output-manifest.json](input-code-output-manifest.json)。原始资源曲线保留在[原报告目录](../../)，其内存轴为MiB。
