# VIDEO-USE-EDIT-PILOT-01 执行报告

- run_id: `20261021T0822Z-video-use-edit-01`；执行次数：一次。
- 时间：冻结准备至归档 80.473 秒；正式容器阶段 1.511 秒，其中 ASR 阶段 0.101 秒，独立 judge 0.055 秒。
- 输入：2017306 bytes，SHA-256 `a9bce74a50b5380d7c1aa1d9980f1d159e8633fbff00986504a363a3d18525bb`。
- 测量完整性：partial；仅保存 2 个边界样本，间隔 0.173 秒，未达到一个 0.5 秒周期采样点；缺测保持 null。
- 离线复核保留原始执行记录与判定；字段映射修正后的计数器结果见 raw `resource-summary-corrected.json`，修订原因见 `analysis-revision-01.json`。Agent 未启动，因此没有原生 rollout、工具或模型 usage 轨迹。
- CPU：0.087876 core-s；有效区间平均 0.5076200220018354 core。
- 内存：sampled current 峰值 4620288 B；kernel peak 13332480 B，分列。
- 磁盘 I/O：read 0.0 B / 0.0 B/s；write 0.0 B / 0.0 B/s。
- 官方任务结果：原版 judge 已独立执行一次，进程 returncode `1`；未生成 reward。原因是没有提交文件，judge CLI 在读取缺失的 cuts.json 时异常退出。
- Agent 终止原因：Agent 未启动。官方 transcribe.py 在导入阶段因镜像缺少 `requests` 依赖报 `ModuleNotFoundError`，故 attempt 在 ASR 阶段停止。
- ASR：ElevenLabs 请求发送数 `0`（异常发生在 `requests.post` 之前）；无音频上传、无 API 响应、无供应商费用。未安装依赖、未重试、未补跑。
- 资源 scope：Agent 容器 cgroup CPU、memory.current/kernel peak、cgroup I/O；网络为共享容器 netns 的逐接口字节，不代表 API 专属流量。
- 清理/归档：容器 `removed`；run-record 与逐文件 bytes/SHA manifest 已保存。
- 资源：CPU 0.087876 core-s，有效边界区间平均 0.50762 core；sampled current 峰值 4,620,288 B，kernel peak 13,332,480 B；观察到 cgroup 磁盘 I/O 为真实零。仅一个 0.173 秒区间可算平均值。
- 网络：容器 netns `eth0` 起止累计 RX 均 180 B，TX 均 0 B，区间增量 0；共享 bridge/netns 计数，不归因于 API。容器未连接 ASR 或模型端点。
- 模型请求、工具、返回、错误、usage、响应模型：均 `not_started`；HTTP 次数不适用/unknown，Codex 原生 rollout 不存在。
- 网络接口和时间边界详见 raw `run-record.json`；曲线：`resource-curves.svg`。
