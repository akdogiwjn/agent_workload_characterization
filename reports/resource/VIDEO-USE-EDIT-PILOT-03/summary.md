# VIDEO-USE-EDIT-PILOT-03 执行与验收报告

run_id：`20261021T1310Z-video-use-edit-03`；单次 attempt；冻结 identity `f905501068cc15864c81948b41095e28895a81c30dc7e53fbbc0b8f4edbad33f`。以下仅描述本次 n=1。

| 测量完整性 | 官方任务结果 | Agent终止 | 基础设施与归档 |
|---|---|---|---|
| attempt wall 365.167s；采样窗口 340.583s，566 点/565 个相邻区间；目标 0.5s，实测中位 0.601359s、最大 0.801728s。原始点见 [resource-samples.csv](resource-samples.csv)，原始采样行保存在 raw run-record。 | judge RC 0、wrapper RC 0；评分 `complete` / complete `True`；原始 reward 0.0。cut_ranges=evaluated，duration=evaluated，SSIM=0.9868，audio_xcorr=0.9734；四项均已执行。未披露或回传剪切时间。 | Agent RC 0，timeout=False；Codex CLI 0.163.0，响应模型 qwen3.7-plus。协议事件 37 calls / 37 returns，协议错误 0；其中 exec_command 29、view_image 8。观察到 1 条命令非零退出（截图命令），之后同类截图调用成功。 | 转写 0，一次请求；Agent 335.324s；verifier 22.799s。镜像 v6 保留。容器删除已核验。raw manifest 86 项、bytes/SHA 全部匹配且不含自身。 |

## 输出与检查

- 输出视频：H.264/yuv420p，854×480，25/1，AAC 单声道 16000 Hz；视频流 34.920000s，容器/音频时长 34.984000s。`ffprobe` 与完整 FFmpeg 解码通过；cuts.json 可解析且含一个 hesitation cut。
- 官方结果为 reward 0：时长、SSIM 和音频相关性检查已评估，剪切范围检查未通过。评分完整，不把未执行检查当作失败。
- 视觉自检截图已归档（切点前后、输出前后及 timeline 截图）；Agent 自主生成 EDL，没有把 verifier 反馈交回。

## 资源与计量

- cgroup CPU 38.546396000000044 core-s；有效间隔平均 0.11317753940443545 core。`memory.current` 采样峰值 497999872 B；内核 memory peak 527572992 B。cgroup I/O：read 0.0 B / 0.0 B/s，write 1474560.0 B / 4329.511700761964 B/s；缺测未补零。
- 网络为容器共享 bridge netns 逐接口计数（非 API 专属）：{"lo": {"rx": 0, "tx": 0}, "eth0": {"rx": 3706018, "tx": 65839834}}。目录非重叠边界：输入 2017306→2017306 B，Agent workspace 0→43364066 B，output 0→2680433 B。
- 原生 rollout 保存 30 个不同 response_id/usage 记录；逐响应 usage 去重后的汇总：input 1012494、cached input 798080、output 14555、reasoning output 11167、total 1027049 tokens。response_id 记录不是 HTTP 传输审计；实际 HTTP 尝试次数及费用 unknown。

## 收尾说明

正式任务、verifier、raw 归档均已完成。入口最终返回码为 1，原因是冻结入口的 post-run `write_resource_report` 包装器递归调用自身，产生 `RecursionError`；它发生在 run-record 和 manifest 写入之后，不影响 Agent、judge 或容器清理。本报告与曲线由已归档证据离线生成；没有改写 raw/manifest、执行代码、评分，也没有重跑。
