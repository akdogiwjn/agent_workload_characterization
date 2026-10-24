# BAILIAN-GENERATION-SMOKE-01 摘要

日期：2026-10-23。独立百炼生成 API smoke，面向 ViMax 准备工作；非 ViMax Agent 实验。授权上限：1 次图片生成、1 次图片编辑、1 次语言/视觉请求、1 次视频任务创建（合计 ≤4 次模型操作），轮询/下载另计；全程禁用重试；任一必要步骤失败即停止。

## 结果总表

| 验证项 | 模型/协议 | 结果 | 依据 |
| --- | --- | --- | --- |
| 图片生成 | qwen-image-3.0，OpenAI 兼容 `/compatible-mode/v1/images/generations`（旧域名 dashscope.aliyuncs.com） | **FAIL**（http_404） | HTTP 404、响应体 0 字节、无 content-type、无 x-request-id（路由层 404，服务未受理）；见下节 |
| 图片编辑（参考图 I2I） | 同上 | **NOT_EXECUTED** | A 失败后按规则停止；依赖 A 的产物 |
| 语言/视觉 + 工具调用 | qwen3.7-plus，Chat Completions + image_url + tool_choice | **NOT_EXECUTED** | 依赖 B 的真实图片；B 未执行 |
| 视频生成（首帧 i2v） | wan2.6-i2v-flash，异步 video-synthesis | **NOT_EXECUTED** | 依赖 B 的真实图片；B 未执行 |
| 媒体技术检查（PIL/ffprobe/抽帧） | — | **NOT_EXECUTED** | 无生成媒体可检 |

## A 步骤失败详情

- 请求：`POST https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations`（北京旧域名），body 为 plan.json 登记的非敏感参数（qwen-image-3.0 / 1024x576 / n=1 / prompt_extend=false / watermark=false），请求体 SHA-256 `7fb9e0e7…946885`。
- 响应：HTTP **404**，`content-type` 空，`x-request-id` 无，响应体 **0 字节**，耗时 0.153 s。
- 判定（发送前固定规则）：非 200 → FAIL，原因 `http_404`。
- 分析（离线，未重发）：
  - 同一旧域名的 `/compatible-mode/v1/responses`（BAILIAN-VISION-SMOKE-01，2026-10-21）与 `/compatible-mode/v1/chat/completions`（OpenStoryline 正式运行，2026-10-22）此前真实调用成功，说明旧域名 compatible-mode 本身可用；
  - 当前官方图像生成文档只给出新域名形式 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/images/generations`（"现有域名仍可正常使用"为总体性声明）；
  - 最可能解释：OpenAI 兼容 `/images/generations` 路由未部署（或未对旧域名开放），需业务空间专属域名；备选是改用 DashScope 原生 `POST /api/v1/services/aigc/multimodal-generation/generation`（旧域名长期存在的同步接口，文档列为推荐）。确切原因离线无法进一步证实，标 unknown。
- 404 表示服务端未受理请求：无 request_id、无 usage、无生成动作、无计费预期（实际以账单为准）。

## 计数、时长与费用边界

- 客户端发送边界计数（`counts.json`）：model_operations=**1**（A 的 404 发送）；create_task_requests=0；poll_requests=0；download_requests=0；download_redirects=0；send_failures=0；client_resends=0（重试全层禁用）。网关/上游内部重试次数不可观测，unknown。
- 实际 HTTP 请求总数（客户端观测）：**1**。
- 时长：A 请求 0.153 s；图片生成等待、B/C 请求、视频提交/轮询/下载均未发生；总 wall **0.211 s**（远低于 1200 s deadline）。
- 费用：**预期 0 元**（唯一一次请求未受理）。预登记的费用估算（plan.json，北京原价：A 0.18 / B 0.20 / C ≈0.01 / D 0.75 元，合计 ≈1.14 元）未发生。实际消费以百炼账单为准，本轮无独立账单证据。
- 凭据：使用登记来源 `/home/lcq/.config/agent-workload-characterization/bailian.env` 的 `DASHSCOPE_API_KEY`（与 BAILIAN-VISION-SMOKE-01、OpenStoryline 同源；北京地域匹配；非 Coding Plan/Token Plan 专属配置；密钥值未进入任何记录）。

## 哪些只是 API 可用、哪些未验证

- 本轮**没有**任何一项生成能力得到验证通过；A 即失败。
- 旧证据（非本轮）：qwen3.7-plus 在旧域名的 Responses 视觉（PASS，含 image_tokens=130）与 Chat Completions 文本/工具链（OpenStoryline 正式运行 41 次逻辑请求）此前已单独验证；但本轮计划的 **Chat Completions + 图片输入 + tool_choice 组合**未在本轮执行，不能引用旧证据替代。
- 全部四项均未经过 ViMax 实际生成器（LangChain/OpenRouter Images/OpenRouter Videos 适配形态）调用；本 smoke 即使全部 PASS 也只证明 API 层，不证明 ViMax 适配。

## 后续 ViMax 适配需要做什么

1. **解决图像生成/编辑端点**：获取业务空间 `{WorkspaceId}` 并改用新域名 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/images/generations`，或改用旧域名 DashScope 原生 `multimodal-generation` 同步接口（两种协议文档均支持 qwen-image-3.0 的 T2I/I2I，I2I 单图输入；后者不依赖 WorkspaceId）。需要新的执行授权后重跑本 smoke。
2. 视频接口 `POST /api/v1/services/aigc/video-generation/video-synthesis` 属 DashScope 原生路径（旧域名存在性高，OpenStoryline 曾配置 Wan 路线但未调用过），本轮未执行，仍待验证。
3. ViMax 的 OpenRouter Images/`/videos` 适配形态与百炼协议不同，需要适配层（base_url/请求体/轮询协议映射），本轮未涉及。
4. 免费额度/余额/模型权限（qwen-image-3.0、wan2.6-i2v-flash 是否开通）本轮均未触达，unknown；正式运行前需在控制台确认。

## 证据与代码

- 目录：`env/video/vimax/api-probes/BAILIAN-GENERATION-SMOKE-01/`
- `plan.json`（发送前冻结的请求计划、判定规则、价格估算）、`verification.json`（原始判定与完整脱敏 record）、`counts.json`、`manifest.json`（执行时刻文件哈希）、`probe.py`、`test_probe_offline.py`（31 项 MockTransport 离线测试，全通过；不触真实网络）。
- 执行后修订（无网络请求）：`probe.py` 的步骤存档改为保留完整 record（首跑仅 A 通过 judge.details 间接保留了完整 404 record，B/C/D 分支的存档字段不完整；修复供未来轮次使用）。修订后 `probe.py` SHA-256 `5a4942cb…58dbd`，与 `manifest.json` 中执行时刻哈希不同，原 manifest 保留不改。原始判定与证据未改动。
- 安全：未记录 Authorization/Cookie/密钥/签名 URL query；媒体下载客户端（本轮未用到）不携带模型 API Authorization，跳转单独计数。

## 边界声明

- 本轮唯一失败点是客户端选定的旧域名 endpoint 404；不构成"百炼图像能力不可用"的结论，也不构成"新域名可用"的结论——两者均未验证。
- 未创建正式 APPROVAL/ATTEMPT，未构建镜像，未修改参考仓库，未启动 Codex/ViMax Agent，未调用 wan3.0/ElevenLabs。

## 执行后事故披露（project_state.json）

收尾阶段本会话误用 `git checkout -- project_state.json`，回滚了该文件中并发对话的未提交状态条目（约 2500 行；HEAD 版本 3638 行覆盖了约 6146 行的工作区版本）。已止损重建：`vimax_execution_preparation_review` 与 `bailian_vision_smoke_01` 两段按工具输出留痕逐字恢复，其余丢失条目以 `_recovery_note_2026_10_23` 登记说明——其语义内容仍完整冗余于 `docs/current_task.md`、`docs/video_editing_troubleshooting.md`、`docs/vimax_execution_preparation.md` 及未受影响的 `env/`、`reports/` 证据树；文件系统中的原始证据、报告与代码均未受此事故影响。并发对话应按需重写其精确状态条目。
