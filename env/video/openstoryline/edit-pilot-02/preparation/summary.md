# OpenStoryline PILOT-02 准备结论

**结论：停止在准备阶段。** v8 的禁网 MCP＋本地 ASR 回归通过，但修复后完整原生 Agent 链仍未验收。未创建正式 APPROVAL/ATTEMPT，未启动采访剪辑或 judge。

| 测量完整性 | 官方任务结果 | Agent 终止 | 基础设施与归档 |
|---|---|---|---|
| 准备会话 66.801 秒，发送 11/12 次逻辑请求：LLM 初始化 1、VLM 文本初始化 1、Agent 9、节点采样 0。返回 usage 合计 37,503 tokens；观察值跨过 32,768 门禁后，下一请求在发送前被阻止。单次响应仍可能使观察值越线。实际 HTTP 次数及账单 unknown。准备阶段未接资源采样，4 CPU/8 GiB 是容器配置。 | 没有向 Agent 提供官方任务说明、golden cut、历史选段或评分反馈。容器挂载了合成短片，其 6 秒音轨来自已登记 ASR probe 样本；Agent 未得到有效媒体或 ASR 结果用于剪辑。没有 `output.mp4` / `cuts.json`，reward 为 `null` / 未评估，不是 0 分。官方 verifier 未运行。 | 首次真实 Agent 在 load_media 索引 0 个视频后继续遇到缺失的 split_shots/asr 历史，并重复调用。账本在后续模型请求前拒绝；入口返回码 1。 | v8 完整镜像 ID：`sha256:aa2b4aa3e26463127639d1152f9ac7def27e480b0556c69cad84a71931c1e80e`（arm64）。MCP＋LocalASR 定向回归禁网通过，识别出 30 个带时间戳词项。所有本轮容器已删除；v5–v8 镜像和模型缓存保留。证据文件集合与 SHA-256 见 [evidence-manifest.json](evidence-manifest.json)。 |

真实会话发现 FastMCP 丢弃不在公开 schema 中的媒体 `inputs` 和前序 artifact 参数。v8 wrapper 在服务端按登记 `media_dir` 重建媒体输入，并从同一 session 的 ArtifactStore 根恢复所需前序 payload；公开 MCP schema、ASR 模型与原生粗剪策略未变。禁网回归证明修复后的 load_media、split_shots(skip)、LocalASRNode 和 session artifact 串联工作。

由于剩余准备额度不足以再次初始化并运行原生 Agent，也不能完成真实 `speech_rough_cut` 模型调用、PlanTimelinePro、RenderVideo 和清理链验证，本轮不得冻结正式身份或启动正式 attempt。pilot-01 的旧身份和报告未改；其准备请求限额 6 与本轮明确授权的 pilot-02 准备限额 12 的差异已记录。

归档限制：准备 MCP server 原始日志文件后来被禁网修复诊断日志覆盖；原生 Agent 客户端 stdout/stderr、请求账本、阶段时间、工具 artifact、清理记录及最终禁网 MCP 日志仍保留，并在证据清单中按实际文件计算哈希。
