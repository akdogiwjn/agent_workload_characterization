# OpenStoryline 完整禁网链路验收

**结果：BLOCKED，未通过正式执行门槛。** v8 镜像身份为 `sha256:aa2b4aa3e26463127639d1152f9ac7def27e480b0556c69cad84a71931c1e80e`（linux/arm64）。三次禁网容器均未访问真实模型服务；没有读取凭据，也没有创建正式 APPROVAL/ATTEMPT。

第三次验证中，实际 MCP `load_media` 和 `split_shots(mode=skip)` 通过公开 schema、生产 wrapper、真实节点及独立 session 的 ArtifactStore；相对路径按 OpenStoryline 的 path-only 契约从 `/workspace/input` 解析。`local_asr` 调用失败于模型初始化：容器内缺少已登记 ModelScope 路径下的 `configuration.json`。没有进入 ASR 推理，也没有继续粗剪、timeline、render 或导出。前两次仅因验证器误把相对媒体路径断言为绝对路径而停；断言已按 path-only 契约修正，未改生产代码。

准备期两轮修复验证额度已用完，因此按停止条件结束。未调用 fake 粗剪响应（真实 ASR 前置未通过）；旧的独立 ASR 与下游合成验证仍保留为各自证据，不并入本轮完整链路结论。下一次若继续，需先按既有模型缓存登记修正容器只读挂载，并由一次新的离线完整链验收确认，再决定是否冻结及批准正式 attempt。

完整机器可读结果见 [gate-result.json](gate-result.json)；每次测试的独立日志、ArtifactStore、输入 fixture、配置和验证脚本保留在相邻 `full-chain-01` 至 `full-chain-03` 目录。原始文件集合与 SHA-256 见 [evidence-manifest.json](evidence-manifest.json)。测试容器已自动删除，v8 镜像保留。
