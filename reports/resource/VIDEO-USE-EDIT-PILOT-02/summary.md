# VIDEO-USE-EDIT-PILOT-02 执行报告

运行 `20261021T0937Z-video-use-edit-02`，单次 attempt，n=1。计时修复在 PILOT-02 薄入口调用共享 runner 前以当前 `time.monotonic_ns()` 初始化起点；冻结文件中的准备时间不再进入运行预算。新增 timer 回归后 PILOT-02 定向测试 9 项、PILOT-01 直接受影响回归 11 项通过；mock 网络被阻断，不启动真实 Agent、ASR 或 verifier。冻结 identity SHA-256：`e1c71956167ba4d20d16021d4005a24a639d3ac44938978189a1bbc3d6d702f3`；新环境计划 SHA-256：`95f9173b81f0e856538fbaa6a3cf1df0ad3358c6e47cff5d2136b5bd526b4e1c`。

| 测量完整性 | 官方任务结果 | Agent终止 | 基础设施与归档 |
| --- | --- | --- | --- |
| 正式 attempt wall 197.72 秒（09:41:06–09:44:24 UTC）；0.5 秒目标采样 313 点，312/312 个 CPU 与 I/O 区间有效，无 gap。CPU 98.515 core-s，区间均值 0.508 core。`memory.current` 采样峰值 1,314,033,664 B；内核 peak 1,315,033,088 B，分列。cgroup I/O 读 0 B、写 1,990,656 B（有效窗 193.85 秒，写均值 10,268.9 B/s）。网络为容器共享 bridge netns 逐接口计数，eth0 RX 增 2,343,325 B、TX 增 11,311,869 B；不是 API 专属流量。准备阶段与 attempt 未共用起点计时；从最早留存的快照时间 09:36:11 到完成时间 09:44:24 为 493 秒，快照前准备起点 unknown。 | 官方 Scribe v1 转写成功，单次请求，约 6.13 秒。Agent 提交 `output.mp4` 与 `cuts.json`。隔离官方 judge 执行完成（returncode 0），reward 0.0；报告缺少 `skimage` 导致 SSIM 采样失败，且提交剪切未满足 judge 时间容差。提交视频时长 34.941 秒，judge duration 项通过。未安装依赖、未补跑、未将 verifier 反馈交回 Agent。 | Codex/Bailian Agent 阶段约 187.49 秒，returncode 0、未超时。模型请求数和 HTTP 次数在原生 rollout 中不可可靠确认（HTTP unknown）；36 次工具调用、36 次返回、0 个工具错误，含 `view_image` 视觉自检；46 条 usage 事件，累计 input 915,483（其中 cached input 707,328）、output 6,324、reasoning output 3,371、total 921,807 tokens；实际响应模型 qwen3.7-plus。截图、完整原生 rollout、转写、提交视频和 cuts 均保留。 | 镜像 `video-use-task:arm64-codex-bailian-v2`，ID `sha256:faf015927f9a71c820c82abc11d1a996037d7d684e6e149f2787908ad422c20f`，linux/arm64。输入 SHA-256 与登记一致。材料目录 2,017,306 B（不变）；Agent 工作区 0→20,581,920 B；输出目录 0→9,238,965 B，边界不重叠。Agent 容器已核验删除，镜像保留。raw manifest 登记 20 个文件，逐项 bytes/SHA 匹配，无未登记文件；manifest 不自哈希。 |

## 阶段边界

- attempt：09:41:06–09:44:24 UTC，约 197.72 秒。
- 计时修复、定向回归和重新冻结发生在 attempt 前；归档快照最早记录为 09:36:11。从该留存边界至完成为 493 秒，快照前准备起点没有独立计时记录，因此完整准备+执行 wall 保持 unknown。
- ASR：09:41:07–09:41:13 UTC；发送一次，transcript 已归档供本次 Agent 使用。
- Agent：09:41:13–09:44:21 UTC，约 187.49 秒；渲染和截图自检在此阶段内完成。
- 独立 verifier：09:44:22–09:44:24 UTC，约 1.77 秒；Agent 容器关闭并确认删除后运行。
- 资源范围为 Agent 容器及其子进程；不按工具或 API 归因。CLI 原生日志未给出的 HTTP 次数、独立模型请求边界保持 unknown。

曲线见 [resource-curves.svg](resource-curves.svg)。原始证据与 verifier 结果见 `data/raw/generated/VIDEO-USE-EDIT-PILOT-02/20261021T0937Z-video-use-edit-02/`。来源许可登记仍为 unknown；本轮按用户授权处理，登记未改写。
