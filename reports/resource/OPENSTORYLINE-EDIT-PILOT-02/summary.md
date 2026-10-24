# OPENSTORYLINE-EDIT-PILOT-02 执行与离线恢复报告

- run_id：`20261022T150133Z-openstoryline-edit-02`，唯一attempt；冻结身份 SHA-256 `441caee9a76d32d35b906ffccd62d28fb98537038d5d2fc2e031ab054d0c4f0c`。
- 正式模型：`qwen3.7-plus`，Chat Completions；逻辑请求 41 次开始、41 次结束；observed tokens 315,370；HTTP次数和账单 unknown。
- Agent实际工作 1270.80s / 1800s；本地ASR、原生工具与最终render完成。原始日志保留首次RenderVideo错误“timeline result has no video track”以及随后Agent查询history、重规划并成功渲染的恢复。
- 提交输出：854×480、25fps、H.264/yuv420p、AAC、音视频同步、非静音，完整解码通过。`output.mp4` 与最终RenderVideo artifact SHA-256一致；`cuts.json`按最终timeline源区间补集生成。
- Judge：状态 `complete`，完整性 `True`，reward `0.0`；进程返回码 `0`，wrapper返回码 `0`。
- 资源scope：Agent容器cgroup v1，2101点，目标0.5s，实测中位间隔 0.601s；netns按接口报告，不归因为API流量。Verifier资源单列。
- 清理：容器 `removed`，MCP `stopped`；镜像与模型缓存保留。原入口未能写报告，原因是宿主更新容器uid=nobody文件时PermissionError；未改写原始agent-result、消息、请求或工具日志。
- 完整attempt起点和Agent进程返回码未被原入口持久化；报告保留为unknown。目录占用初始精确du值未保存，不回填；见目录占用表。

统计表：[请求、工具与阶段](request-tool-stage-summary.csv)。图表：`resource-curves.svg`（CPU、内存、磁盘I/O、网络四面板，真实采样，缺口断开）。原始采样：raw `resource-samples.csv`；请求、工具、消息与MCP事件位于raw `workspace/output/`。
