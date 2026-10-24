# ViMax 百炼适配差异登记（adapter-src 相对参考仓库 fd4b72e7731be6e5f88486206d25ea59849b0285）

副本来源：`references/repos/ViMax` @ fd4b72e7（工作区干净，原件未改）。
副本排除：`.git/ ui/ web/ assets/ vimax_benchmark/ tests/ .working_dir/ .vimax/ __pycache__`（tests 不进镜像，适配单测在验证目录内提供）。

## 新增文件（2）

1. `tools/image_generator_bailian_api.py` — ImageGeneratorBailianAPI：
   - `POST {base_url}/images/generations`（业务空间新域名 compatible-mode/v1，BAILIAN-GENERATION-SMOKE-02 真实验证）；
   - T2I：无 `image` 字段；I2I：`image` 字段传 base64 data URL 数组（单参考图编辑已实测通过）；
   - 不使用 `/images/edits`、不使用 multipart；
   - 响应 URL 由生成器下载（无 Authorization、≤1 次跳转、20MB 上限）→ `ImageOutput(fmt="pil", ext="png")`；
   - 参考图 >3 张：`ValueError` 明确拒绝（qwen-image-3.0 官方上限 1-3 张），不截断；
   - 重试（2026-10-23 审计修订）：**撤销 V1 的"同步生成重试不会重复计费"错误说明**——生成请求超时/5xx 时服务端结果不明，默认不自动补发（账本记 right-censored）；仅明确 429（未受理）可重试且不重置单调用 deadline；401/403/其他 4xx 立即失败；
   - `VIMAX_BAILIAN_EVENT_LOG` JSONL 事件账本（create/download，URL 去 query）。
2. `tools/video_generator_bailian_api.py` — VideoGeneratorBailianAPI：
   - 原生 `POST {base}/api/v1/services/aigc/video-generation/video-synthesis`（`X-DashScope-Async: enable`）+ `GET {base}/api/v1/tasks/{task_id}`；
   - **0 张参考图：拒绝**（i2v 模型无 T2V 模式，不静默换模型）；**2 张（首尾帧）：拒绝**（wan2.6-i2v-flash 仅首帧；不丢弃尾帧、不伪装首帧请求）；>2 张拒绝；
   - 1 张 = 首帧（`input.img_url` base64，与 video-recovery-01 实测路径一致）；
   - task_id 在轮询前先落事件账本；轮询只查该 task；轮询必带 Authorization；401/403 立即失败；轮询传输错误中止（不重建付费任务）；
   - **创建 0 重试**（5xx 可能已受理，重试可能双倍计费）；下载无授权头、≤1 跳转、200MB 上限、有界重试（幂等）；
   - duration/resolution/audio/prompt_extend 从显式环境变量读取（ViMax 不经 kwargs 传）：`VIMAX_BAILIAN_VIDEO_DURATION=5`、`_RESOLUTION=720P`、`_AUDIO=false`、`_PROMPT_EXTEND=false`；
   - 返回 `VideoOutput(fmt="bytes", ext="mp4")`（生成器内完成下载）。

## 修改文件（3）

3. `agent_runtime/config.py`：`api_provider_from_base_url` 增加 `maas.aliyuncs.com` → `"bailian"`。
4. `agent_runtime/vimax_adapters.py`：`_build_image_generator` / `_build_video_generator` 增加 bailian 分支（视频 base_url 剥离 `/compatible-mode*` 后缀取裸域名）+ 两个 import。
5. `agents/reference_image_selector.py`：**行为变更（登记）**——参考图上限 8 → 3（3 处提示词 + 筛选阈值 `>= 8` → `>= 3`）。理由：qwen-image-3.0 官方参考图上限 3 张；不改则正式任务中 LLM 选 >3 张参考图会在生成器层被拒，导致关键帧全失败。此变更只约束数量，不改变选择算法与提示词其余内容。

## 重试/超时统一策略（显式登记，防三层叠加）

| 层 | 策略 |
| --- | --- |
| 百炼图片生成 | `VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS=2`（仅 429/5xx/传输错；同步无任务，不会双计费） |
| 百炼视频创建 | **0 重试**（任何失败立即抛） |
| 百炼视频轮询 | 0 重试；`VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS=10`、`VIMAX_BAILIAN_VIDEO_QUERY_TIMEOUT_SECONDS=900` |
| 百炼媒体下载 | 同图片重试策略（幂等） |
| 上游已有（未改动） | 外层 Agent `OpenAICompatibleLLM` 自建 3 次重试（429/5xx）；narrative LangChain `max_retries=0`；`utils/video.py` 下载 tenacity×3（仅 fmt="url" 的 VideoOutput 使用，百炼适配返回 bytes 不经过它） |

## 能力边界（相对 ViMax 原生行为的明确不支持项）

- **首尾帧（variation_type=medium/large 的 shot、`frame_images=[first,last]`）**：wan2.6-i2v-flash 不支持，适配层拒绝（ValueError），不静默降级。缓解（任务组装层，不改算法）：正式任务的 user_requirement 中明确要求全部 shot 使用小变化（small variation）且避免剧烈机位转场。
- **camera transition 分支**（子机位 `generate_transition_video`）：参考图为 1 张父 shot 首帧 → 属首帧 i2v，**被支持**；但每条 transition 会额外产生一次视频生成调用（预算需计入）。
- **T2V**（0 参考图）：拒绝。
- **关键帧参考图 >3**：拒绝（selector 已限 3）。


## 2026-10-23 审计修复补充（VIMAX-NETWORK-VALIDATION-02，v2 镜像）

- 新增 `agent_runtime/request_ledger.py`：共享 JSONL 请求账本（发送前 open、闭合/右删失、写入失败不静默）+ 发送前预算门禁（LLM 调用/尝试、图片、视频创建、轮询、下载、单请求输出 token、共同 deadline）；
- `agent_runtime/llm.py`：OpenAI SDK 显式 `max_retries=0`（V1 为 SDK 默认 2——旧文档"SDK 零重试"假设不成立，已纠正）；项目重试/形状补发逐次入账；usage 记录；
- `agent_runtime/vimax_adapters.py`：LangChain 账本回调（继承 BaseCallbackHandler）；`preflight_render_capability` 在 render 前校验 shot 顺序/variation/相机树/transition 预算，不兼容零发送拒绝；
- 两个生成器下载器：跳转独立计数（第 2 次失败）、相对 Location 解析、http/https 白名单、重试不重置 deadline；
- `agents/reference_image_selector.py` 的 8→3 变更维持（qwen-image-3.0 官方上限）。
