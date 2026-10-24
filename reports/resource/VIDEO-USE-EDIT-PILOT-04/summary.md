# VIDEO-USE-EDIT-PILOT-04 执行报告

| 测量完整性 | 官方任务结果 | Agent终止 | 基础设施与归档 |
|---|---|---|---|
| attempt wall 258.426738301s；采样 397 点/396 邻接间隔，采样窗 239.20110541300002s；目标 0.5s，实测中位 0.601334616s、最大 0.702777749s。CPU 43.66957199999998 core-s，平均 0.18256425665174472 core；memory.current 峰值 439365632 B，kernel peak 439390208 B；cgroup I/O read/write 0.0/1335296.0 B。 | judge RC 0；完整性 complete/True；reward 0.0；剪切范围 evaluated，时长 evaluated，SSIM evaluated，音频检查 evaluated。提交核验：{"files_present": true, "ffprobe": {"status": "pass", "video_codec": "h264", "width": 854, "height": 480, "pixel_format": "yuv420p", "frame_rate": "25/1", "video_duration_s": "35.720000", "audio_codec": "aac", "audio_channels": 1, "container_duration_s": "35.784000"}, "full_decode": {"status": "pass", "returncode": 0, "stderr": ""}, "cuts_json": {"status": "parseable", "cut_count": 1}, "ffprobe_returncode": 0, "source_video_spec": {"width": 854, "height": 480, "frame_rate": "25/1"}, "matches_source_dimensions_and_rate": true}。 | Agent RC 0，timeout False；工具调用/返回/协议错误 32/32/0；非零命令 1。原生 rollout 归档。 | 镜像 sha256:1a48c7b00da789ec99722ebb2be6e1df72aec9d37cc2a64e83c82e89ecf700c5 linux/arm64；清理 removed；网络为共享 netns 逐接口（非 API 专属）；raw manifest 见 /home/lcq/agent_workload_characterization/data/raw/generated/VIDEO-USE-EDIT-PILOT-04/20261021T1450Z-video-use-edit-04/manifest.json。HTTP 次数与费用 unknown。 |

## 单次尝试阶段

- preflight: returncode=0, duration=0.100919865s, timeout=False
- official_elevenlabs_transcribe: returncode=0, duration=unknowns, timeout=False
- agent: returncode=0, duration=unknowns, timeout=False
- export_native_rollouts: returncode=0, duration=0.101038368s, timeout=False

## 模型 usage 与网络

- Codex rollout 工具调用 32、返回 32、协议错误 0；命令非零退出单独统计。
- 保存响应 usage 事件 46；原生逐响应/累计用量见 raw，累计快照不重复相加；HTTP 请求次数 unknown。
- cgroup 覆盖容器及子进程，不归因到单工具；网络字节为共享 netns 逐接口值，不是 API 专属流量。
