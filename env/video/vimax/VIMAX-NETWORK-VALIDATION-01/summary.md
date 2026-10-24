# VIMAX-NETWORK-VALIDATION-01 摘要：百炼适配 + ARM64 镜像 + 禁网验证

日期：2026-10-23。范围：ViMax 百炼生成器适配、独立任务镜像构建、禁网生产链验证。不读取真实凭据、不调用付费 API、不执行正式八镜头任务。参考仓库 `references/repos/ViMax` @ `fd4b72e7731be6e5f88486206d25ea59849b0285` 原件未改。

## 1. 镜像

| 项 | 值 |
| --- | --- |
| 新镜像 | `vimax-task-bailian:arm64-v1` = `sha256:045fe9cd4ad527bfcddc3ce703a767e0623b317b3e8ad070276e199f58b27be6`，linux/arm64，约 1.03 GB |
| 基础镜像 | `video-common-base:arm64-v1` = `sha256:d414b4270fec…7a706`（构建前只读核验 ID/架构，未拉取、未覆盖） |
| 源 | `adapter-src/`（ViMax fd4b72e7 + 百炼适配补丁，见 `ADAPTATION-DIFF.md`） |
| 依赖 | uv.lock 经 `uv export --frozen` 导出（247 项，`vimax-task-image/requirements.txt`），`pip3 install -i 清华镜像` 安装；**登记偏差**：uv 直装因 files.pythonhosted.org 本机不可达而不可行，pip 镜像安装的版本仍由 lock 锁定；镜像内 `pip list --format=freeze` 已存 `image-freeze.txt`（75 顶层包：PIL 11.3.0、moviepy 2.1.2、langchain 0.3.26、aiohttp 3.12.14、pydantic 2.11.7） |
| 工具 | ffmpeg/ffprobe 7.1.5（libx264 可用）；解释器三路径核验：普通 shell 与 `bash -lc` 均为 `/usr/local/bin/python3`，ViMax 工具 shell 经 venv 优先路径一致；无 CUDA/torch 栈、无模型权重下载 |
| 构建上下文 | 白名单 `.dockerignore`（仅 adapter-src + requirements.txt 可进入）；无密钥/.env/data/其他仓库/缓存 |
| 运行用户 | uid 2000（vimax），/workspace 由宿主预先可写（chown 不可用时 chmod 777 兜底，已登记） |

**宿主网络发现（登记）**：docker bridge 网络对本机部分 HTTPS 目的地存在黑洞（TLS 挂起），构建使用 `--network host`（经典构建器）绕过；禁网验证容器 `--network none` 不受影响。

## 2. 适配差异（详见 `adapter-src/ADAPTATION-DIFF.md`）

新增 `tools/image_generator_bailian_api.py`、`tools/video_generator_bailian_api.py`；`agent_runtime/config.py` + `vimax_adapters.py` 增加 `maas.aliyuncs.com` → bailian provider 路由；**登记的行为变更**：`agents/reference_image_selector.py` 参考图上限 8→3（qwen-image-3.0 官方上限，3 处提示词 + 筛选阈值）。重试/超时统一策略显式登记（图片同步生成有界重试仅 429/5xx/传输错；**视频创建 0 重试**防双计费；轮询带鉴权、401/403 立即失败；下载无授权头、有界重试；`VIMAX_BAILIAN_EVENT_LOG` JSONL 生产账本）。

## 3. 能力契约与明确不支持项

| ViMax 生产能力 | 百炼适配状态 |
| --- | --- |
| 文生图（T2I） | ✅ `/images/generations` 无 `image` 字段 |
| 图片编辑/参考图 I2I | ✅ 同接口 `image` 字段（base64 数组），**1–3 张**；>3 张 ValueError 拒绝（不截断） |
| 文生视频（T2V，0 参考图） | ❌ **明确拒绝**（wan2.6-i2v-flash 为 i2v 模型；不静默换模型） |
| 首帧生视频（1 参考图） | ✅ `input.img_url`（SMOKE-02 实测路径） |
| **首尾帧生视频（2 参考图）** | ❌ **明确拒绝**（模型不支持；不丢弃尾帧、不伪装首帧请求、不换模型）。ViMax 中 `variation_type∈{medium,large}` 的 shot 走此路径 |
| camera transition 分支（子机位） | ✅ 1 张父 shot 首帧 → 首帧 i2v；每条 transition 额外一次视频生成（计入预算） |
| 关键帧候选/原生 VLM 选择 | 保留原生行为（num_candidates 默认 2；候选>1 时 best_image_selector 走 qwen3.7-plus 视觉，SMOKE-02 已验证该形态） |

**正式任务缓解（任务组装层，不改算法）**：user_requirement 明确要求全部 shot 为小变化（small variation）、避免剧烈机位转场，规避首尾帧路径。若 LLM 规划仍产出 medium/large，render 将明确失败并保留错误证据，不硬凑。

## 4. 禁网验证结果（`--network none`，fake 百炼边界仅在 127.0.0.1）

**34/34 检查通过，容器 rc=0，总 wall 45.4s**（验证链 41.1s）。分组结果：

| 组 | 检查项 | 结果 |
| --- | --- | --- |
| 环境 | 解释器三路径、PIL/moviepy/langchain/aiohttp/pydantic、ffmpeg/ffprobe、libx264 | 全过 |
| 适配单测（对 fake 边界） | T2I 映射、I2I image 字段、**>3 参考图拒绝**、3 参考图接受、**首帧视频端到端**（创建→轮询→下载 bytes）、**首尾帧拒绝**、**T2V 拒绝**、**401 立即失败**、坏 JSON 报错、下载失败留证、单任务单创建 | 全过 |
| 冷启动全链（真实原生入口） | 全新 session 经 `main_agent.py --jsonl --stdin-repl` 真实工具路由：narrative planning 工具结果、**规划 8 shot 契约**（storyboard.json 8 项）、render 工具结果、进程正常退出、final_video 存在 | 全过 |
| 媒体检查 | H.264、1280×720、30fps、**40.0s**、**无音轨**（audio=false）、完整解码、**8 段可识别合成片段各出现一次**（编号 [0,1,7,5,2,4,6,3]，拼接顺序由 shot idx 决定） | 全过 |
| 账本 | 8 视频任务各恰好 1 次创建、task_id 唯一 | 全过 |

生产链真实产物结构（fake 边界）：`character_portraits/{front,side,back}.png`、`shots/{0..7}/{shot_description.json, first_frame.png, first_frame_candidates/candidate_{0,1}.png+selection.json, first_frame_selector_output.json, video.mp4}`、`storyboard.json`、`camera_tree.json`、`render_events.jsonl`、`render_status.json`、`final_video.mp4`。适配账本（本轮）：image_create 成功 19 次（3 肖像 + 8 关键帧×2 候选）、video_create 8 次全部 200、每任务轮询 3 次、video_download 8 次。

**接线限制（如实登记）**：CPU boundary 缺失（容器退出后 cgroup v1 目录已删，`cpu_core_seconds=None`，原因已记录非填零）；内存有采样下界（sampled_max ≈1.39 GB）；netns 仅 lo（`--network none` 下 fake 流量 RX/TX≈1.9 MB 被观测）；blkio counters 在本宿主不可读。逻辑请求/HTTP 传输/远端 job 分列：账本按 create/poll/download 分记；供应商内部尝试数 unknown。

## 5. 轨迹与采集位置

- 原生 JSONL 事件：`workspace/validation/agent-events.jsonl`（turn/prompt_trace/status/tool_start/tool_progress/tool_result/token/done/session）
- 原生 session：`workspace/validation/agent-session/.vimax/{sessions.json,logs/*.jsonl}`、`.working_dir/<session>/`
- 百炼调用账本：`workspace/{events,validation}/bailian-events.jsonl`（create/poll/download，URL 去 query）
- 宿主编排：`run-record.json`（阶段耗时、docker argv、cgroup 采样、netns、前后目录扫描、清理）
- 采样：`ResourceSampler`（cgroup v1）+ netns 逐接口；计时用本次运行实时 monotonic（不读准备文件）

## 6. 下一次真实任务的建议预算（北京原价口径）

| 项 | 估算 |
| --- | --- |
| 图片 | 3 肖像 + 8 关键帧 × 2 候选 = 19 次生成（输出 0.18 元/张 1k 档）+ I2I 输入参考（≤3 张/次，0.02 元/张）≈ **3.7–4.0 元** |
| 视频 | 8 shot × 5s × 0.15 元/s（无声 720P）= **6.0 元**；若规划出现子机位 transition，每条 +0.75 元（建议 user_requirement 明确单机位/避免额外过渡，或将过渡预算上限定为 +6 元/8 条） |
| LLM | planning(≈11) + agent 轮(≈4) + selector(≈8) + best_image VLM(≈8) ≈ 31 次逻辑请求；token 量约 100–300K → **<1 元** |
| 合计 | ≈ **11 元**（无 transition）；免费额度（qwen-image-3.0 10 张/50s/1M token）可能大幅抵扣，余额 unknown，以账单为准 |
| 请求量级 | 模型逻辑请求 ≈ 58 次；HTTP 传输实际数以账本为准；建议 wall 预算 ≥ 90 分钟（SMOKE-02 实测单视频任务创建→成功 7–13 分钟量级，8 并发受服务限流影响） |

## 7. 是否具备进入正式执行审批的条件

**具备，附两项前置确认**：
1. 首尾帧限制已用两种方式缓解（适配层明确拒绝 + user_requirement 约束 small variation），不构成隐性失败；若正式任务被授权，render 阶段遇 medium/large shot 将显式报错而非静默降级——这是**能力边界**而非缺陷，批准时应知情。
2. 真实运行时的密钥注入（`DASHSCOPE_API_KEY` + `BAILIAN_WORKSPACE_ID` 环境变量，runtime 注入不进镜像）与 `VIMAX_LLM/IMAGE/VIDEO_*` 路由变量按 `ADAPTATION-DIFF.md` 配置。

单轮禁网验证不证明：真实模型输出质量、多参考图（2–3 张）一致性、服务限流下的并发行为、费用规模。正式八镜头任务需单独批准与预算（建议按上表 +50% 缓冲）。

## 8. 文件清单

`run-record.json`、`workspace/validation/validation-report.json`（34 检查明细）、`agent-events.jsonl`、`bailian-events.jsonl`、`agent-session/`（含 final_video.mp4 与全部中间产物）、`image-freeze.txt`、`manifest.json`；构建：`../vimax-task-image/{Dockerfile, requirements.txt}`；适配：`../adapter-src/`（ADAPTATION-DIFF.md）；验证代码：`../runner/{fake_bailian_server.py, offline_validation.py, vimax_bailian_runner.py}`。旧探针（SMOKE-01/02）与历史 raw 未触碰。
