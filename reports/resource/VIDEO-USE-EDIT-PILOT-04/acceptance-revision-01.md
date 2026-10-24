# VIDEO-USE-EDIT-PILOT-04 验收与策略修订 01

本修订对应唯一正式 Agent attempt `20261021T1450Z-video-use-edit-04`，补充入口生成的 [`summary.md`](summary.md) 中缺少的阶段时长、逐响应 usage 汇总和检查通过/失败解释。raw 原件、官方 judge 输出、cuts、冻结身份及批准均未改写。raw manifest 的 26 个文件集合与 bytes/SHA-256 全部匹配，manifest 自身不哈希；容器删除已核验。

此前有一次本地执行入口在共享 runner 的镜像 identity 字段相等性门禁处拒绝，发生在 raw 创建、容器启动和任何网络请求之前。失败 identity 与批准保存在环境目录的 `source-snapshot/preflight-rejected-01/`、`APPROVAL-preflight-rejected.json`，事件记录为零容器、零 sampler、零 ASR/模型/verifier。修正身份字段布局、更新冻结 identity 后，仅运行了一次正式任务。正式身份 SHA-256：`0effb83dcd9d89ed58541561597284c7fc576b72db45aa0fa04685958cfb1c5e`；批准与该身份匹配。没有第二个 Agent attempt。

| 测量完整性 | 官方任务结果 | Agent终止 | 基础设施与归档 |
|---|---|---|---|
| 从 raw 记录起点到结束 monotonic 差为 258.426738301s；采样窗 239.201105413s，397 点/396 有效区间。入口 timer 从本次进程启动计预算，但入口 origin 未写入 raw，因此入口到 raw-start 的额外时长 unknown。采样目标 0.5s，实测中位 0.601334301s、最大 0.702777749s。 | judge RC 0、wrapper RC 0；评分完整，reward 0。剪切范围未通过；时长、SSIM 与音频相关性均已评估并通过。该结论不含目标时间或偏移。 | Agent RC 0、未超时；Agent 阶段 234.848889348s。工具调用/返回 32/32、协议错误 0；1 条命令非零退出（timeline 参数错误 RC 2，随后位置参数调用成功）。 | linux/arm64 v6 镜像；容器删除核验通过。共享 netns 逐接口统计，不是 API 专属流量。归档 26 项哈希完整。 |

## 提交物及独立验收

- 正式 ElevenLabs Scribe 请求一次成功，4.208506801s；无重复转写。独立 verifier 使用 `/home/lcq/.venvs/video-use-pilot03-verifier/bin/python`，环境版本记录与登记解释器一致；judge 17.221009446s，提交物预检/ffprobe/decode 0.258756193s。
- 输出为 H.264/yuv420p、854×480、25/1，AAC 单声道；与输入尺寸和帧率一致。`ffprobe`、完整 FFmpeg 解码、`cuts.json` 解析均通过。容器时长 35.784s。
- judge/wrapper 返回码均为 0，评分完整，原始 reward 0.0。cut range 0/1 通过；duration、SSIM、audio_xcorr 检查通过（SSIM 0.9852，audio_xcorr 0.9971）。与 PILOT-03 一样，cut-range 检查未通过；因此本次没有观察到评分范围改善，单次结果不作策略因果判断。

## 通用策略在执行中的表现

新策略确实在正式发给 Agent 的提示中。Agent 的 `boundary-notes.md` 将短应答判断为需要保留，把之后的重复起句和卡顿判断为剪除内容；EDL、cuts.json 与最终 render 调用共用同一计划。相比 PILOT-03 的整段重启短语删除，这次选择过程按“保留正常应答、最小必要剪切”改变了，但评分范围仍未通过。

Agent 从本地音频计算了候选区附近及渲染输出的 10ms RMS 能量，并生成 timeline 图；rollout 没有 `view_image` 打开 timeline 图的记录。它实际通过 `view_image` 查看了两张渲染后切点附近的静帧。RMS、转写和静帧都不构成听辨语义的证据。虽然策略要求没有音频理解证据时明确写“音频语义判断未验证”，Agent 的边界笔记和最终答复却声称音频能量“确认”卡顿/音频连续；这项自述证据不足，应视作策略遵循不完整，而非已验证音频理解。

第一条 timeline 命令使用了不支持的命名时间参数并以 RC 2 退出；Agent 查阅帮助后使用位置参数成功生成 timeline。该失败是参数选择错误，未发现新的通用工具缺陷。工具事件：32 calls/32 returns、0 协议错误、0 缺返回；29 `exec_command`、1 `write_stdin`、2 `view_image`。

## usage、资源与有限对照

- 原生 rollout 中 23 条 `token_usage_record` 对应 23 个不同 response_id，无重复。逐响应汇总 input 774,221、cached input 630,784、output 11,140、reasoning output 6,604、total 785,361 tokens。cached input 是 input 的子集，不另加；HTTP 传输次数和费用 unknown。响应模型 qwen3.7-plus。
- cgroup CPU 43.669572 core-s，396 有效区间平均 0.182564 core；`memory.current` 采样峰值 439,365,632 B，kernel peak 439,390,208 B；I/O read 0 B、write 1,335,296 B，write 有效区间速率 5,582.32 B/s。资源 scope 为 Agent 容器及子进程；不计独立宿主 verifier，也不归因于单个工具。
- 网络 scope 是共享 container netns 逐接口：采样窗内 `eth0` RX/TX 分别增 2,720,947/4,495,431 B，`lo` 均为 0；不是 API 专属流量。目录边界（非重叠）：materials 2,017,306→2,017,306 B，Agent workspace 0→11,072,726 B，output 0→2,774,840 B。
- 相比 PILOT-03，本次观测到 32/32 工具事件（P3 37/37）、相同的 0 协议错误和 1 条非零命令退出；Agent 分别约 234.849s/335.324s，采样窗约 239.201s/340.583s。资源点原值、有效区间和曲线见 raw run-record 与 [`resource-curves.svg`](resource-curves.svg)。采样目标相同但实际间隔和覆盖窗不等；n=1 仅作描述，不推断普遍性能或策略效果。

### 可追溯位置

- 完整原生 rollout、Agent boundary-notes、EDL、cuts、输出视频及截图：`data/raw/generated/VIDEO-USE-EDIT-PILOT-04/20261021T1450Z-video-use-edit-04/workspace/`
- 独立 verifier 与清理/资源记录：同 run 的 `verifier_private/` 和 `run-record.json`；这些材料在 Agent 容器删除之后使用，未回传给 Agent。此报告不写入官方目标边界、偏移或 oracle 内容。
- 计划、冻结 identity、最终批准、被拒 preflight 批准与事件：`env/video/video-use/VIDEO-USE-EDIT-PILOT-04/`
