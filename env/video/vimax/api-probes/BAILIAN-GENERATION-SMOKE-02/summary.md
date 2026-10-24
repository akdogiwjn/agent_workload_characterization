# BAILIAN-GENERATION-SMOKE-02 摘要

日期：2026-10-23。独立新授权轮次（SMOKE-01 原样保留）。前置阻断轮（0 请求）见 `verification-blocked-01.json` 快照；本文件为真实执行轮记录。

## 结果总表

| 验证项 | 模型/协议 | 结果 | 依据 |
| --- | --- | --- | --- |
| 图片生成 | qwen-image-3.0，新域名 `/images/generations` | **PASS** | HTTP 200；PNG 1024×576、376,820 B、SHA-256 `10acf903…3b261`；usage `output_image_count=1`（1k 档）；像素核对左红/右蓝/白底 0.527 全符合 |
| 图片编辑（image 扩展字段 I2I） | qwen-image-3.0，同接口 `image` 字段 | **PASS** | HTTP 200；`input_image_count=1`（参考图被接受）；PNG 1024×576、129,930 B、SHA-256 `b2c2e2bd…cf6a`；编辑生效（左红 0.408→绿 0.408/红 0.000，右蓝 0.518 保留，白底 0.534） |
| 语言/视觉 + 工具调用 | qwen3.7-plus，旧域名 Chat Completions | **PASS** | HTTP 200；`finish_reason=tool_calls`；tool id 非空、name=`report_shapes`、JSON 参数合法：`green/circle/blue/square` 四字段全对，与 B 图实际像素一致；usage 含 **image_tokens=578**（图片输入被接受的直接证据） |
| 视频生成（首帧 i2v） | wan2.6-i2v-flash，新域名原生 `video-synthesis` | **UNKNOWN**（创建 PASS，终态未观测） | 创建 HTTP 200 + task_id `ebd1a3dd-ea65-41d5-9b98-eb930eb377c9`；40 次轮询全部 401（探针漏带 Authorization 的本地 bug，见 `revision-01.json`）；任务真实状态 unknown |
| 媒体技术检查 | PIL/ffprobe | **部分执行** | A/B 图片已完整检查（解码/尺寸/格式/bytes/SHA-256/像素统计）；视频未下载故 ffprobe/抽帧未执行 |

## 计数与时长

- 发送边界计数：模型操作 **4**（A/B/C/D-create，达 4/4 上限）；创建任务 1；轮询 **40**；下载 **2**（A、B 图片）；跳转 0；发送失败 0；客户端重发 0。网关/上游内部重试不可观测（unknown）。
- 时长：A 3.96 s；B 12.22 s；C 1.92 s；D 创建响应 0.27 s；D 提交→轮询预算耗尽 408.7 s；总 wall **427.1 s**（deadline 1200 s）。
- request_id / usage：A usage `input_image_count=0 / output_image_count=1, qima_output_1k, 1024×576`；B usage `input_image_count=1, qima_input_1k / output_image_count=1`；C usage `prompt 1004（text 426 + image 578）/ completion 67 / total 1071 tokens`；D 创建 request_id `1e6623e6-7737-9c55-9d47-3e1aa61c4b59`，轮询 401 响应各带 request_id（已存 log），无任务 usage。

## 费用边界（估算与账单分列）

- 北京原价估算：A 0.18 + B 0.20 + C ≈0.003（输入 2 元/M×1004 + 输出 8 元/M×67）+ D 0.75（5 s 无声 720P，**若远端任务最终成功**，与是否下载无关）≈ **1.13 元**；若 D 任务失败/未产出则 ≈0.38 元。
- 免费额度（qwen-image-3.0 输入输出共 10 张 / wan2.6-i2v-flash 50 s / qwen3.7-plus 1M token，90 天）是否仍有余额 unknown；**实际费用以百炼账单为准，本轮无独立账单证据**。

## D 项 UNKNOWN 的根因与下一步

- 根因（已确认，本地 bug）：`poll_video()` 未传 Authorization 头；同凭据同域名创建请求刚刚成功，排除密钥/权限/余额问题。40 次轮询预算被无效 401 耗尽；按"认证失败保存证据停止、不盲目重发"规则未再发送。原始判定保留，`revision-01.json` 记录根因与重判（verdict 仍 UNKNOWN，reason 修订为 `poll_authorization_header_bug_task_status_unobserved`）。
- 代码已修复（不重发）：轮询携带 Authorization；401/403 立即停止（AUTH_ERROR）不再烧预算；错误体顶层 code/message 入 log。36 项离线测试通过（含新增 3 项）。
- **有证据的下一步（需用户授权，不自动执行）**：task_id 24 小时内可查。可授权一次"仅轮询+下载该既有 task_id"的补验（不创建新任务、无新增生成费用；若任务已成功，仅发生查询与下载流量，视频本身的 0.75 元在任务成功时已计）。命令已就绪：修复后的 `probe.py` 在下轮授权下执行（或手工单次查询）。

## 能否进入 ViMax 生成器适配

**API 层三要素中两项已获真实通过证据**：
1. ✅ **图像生成与参考图编辑**（OpenAI 兼容 `/images/generations`，T2I + I2I `image` 字段 base64 单图，新域名）——这是 ViMax 关键帧/角色图生成所需的核心能力形态；
2. ✅ **语言/视觉 + 强制工具调用**（Chat Completions + `image_url` base64 + `tool_choice` 指定函数 + `enable_thinking=false`，`image_tokens` 证据）——外层 Agent 与多候选关键帧筛选所需形态；
3. ⚠️ **视频生成未完成**：任务创建协议验证通过（200 + task_id + 首帧 base64 受理），但轮询/下载/媒体检查链路因探针 bug 未走通，任务终态与产物规格 unknown。

**结论**：可以开始 ViMax 适配中不依赖视频产物的前置部分（适配层代码、图像与 LLM 路由接线、禁网 fake 回归），但正式生成任务（八镜头视频）前必须先完成视频链路补验（上述下一步）。同时注意：一轮 smoke 只证明单图编辑与单次工具调用，多图一致性、多镜头并发、ViMax 的 OpenRouter Images/Videos 协议映射仍是后续适配工作。

## 证据清单

`plan.json`（冻结计划）、`verification.json`（真实执行原始判定，含完整脱敏 record/usage/poll log）、`counts.json`、`revision-01.json`（D 根因离线修订）、`verification-blocked-01.json` / `counts-blocked-01.json` / `manifest-blocked-01.json`（前置阻断轮快照，0 请求）、`A-generated.png`、`B-edited.png`、`d-task-id.json`、`probe.py`（含执行后轮询修复）、`test_probe_offline.py`、`manifest.json`。
未记录任何 Authorization/Cookie/密钥/签名 URL query；媒体下载不带模型 API Authorization；SMOKE-01 与历史证据未改动；未提交 Git。
