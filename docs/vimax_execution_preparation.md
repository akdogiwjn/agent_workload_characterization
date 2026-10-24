# ViMax 执行准备分析

## 当前复现入口（2026-10-24）：PILOT-04 已真实跑通

固定REPAIR-01入口已完成19图、8主体+7过渡与40秒原生拼接，技术验收33/33通过；当前无后续执行授权。完整排障、根因、验证边界与下次开跑检查见[ViMax排障与快速复现备忘](vimax_troubleshooting.md)，实际证据见[PILOT-04收尾](../env/video/vimax/VIMAX-GENERATION-PILOT-04/closeout-summary.md)。优先复用该入口和正式配置样例，不重新拼装失败PILOT中的运行器；规划与媒体生成是两个已登记阶段，不称单次不中断全流程。

以下为按当时范围保留的准备、失败与修复过程，后续新配置仍须单独身份和批准。

## 历史正式/规划结果（已收拢为历史）

以下逐轮记录（PILOT-03 握手后RC1退出、PILOT-02 本地入口TypeError、PLANNING-VALIDATE-02/01 规划契约失败、离线回调门禁/诊断、PILOT-01 达到80次LLM门禁）按当时状态保留，均已由2026-10-24的PILOT-04真实闭环取代；原文按原字节保存在 `local_archive/20261024-doc-cleanup-647394/docs/vimax_execution_preparation.md`，各自run的收尾报告、run-report、失败分析、manifest及冻结身份仍在原evidence路径，不被改写。正式attempt均已消费、不补跑。详细根因与修法见[vimax_troubleshooting.md](vimax_troubleshooting.md)的P1–P8/R1–R7行。

## 静态准备分析（保留为参考）

更新：2026-10-23。范围仅为 ViMax 固定源码快照和项目本地采集接口的静态核查；没有构建镜像、安装/下载、启动容器、读取凭据、调用 API 或运行生成任务。本页是下一轮准备方案，不是执行批准。

## 结论

- **推荐入口：** ViMax 原生 `main_agent.py` JSONL Agent Loop，先运行规划工具，检查同一 session 自动保存的规划产物，获准后再调用 render 工具。不要用 `main_script2video.py` 直接管线冒充原生 Agent 运行。
- **需做的最小适配：** 一个宿主侧薄运行器，驱动 `main_agent.py --jsonl --stdin-repl`，每轮发送一条输入、等待 `done`，保存 stdout/stderr 原始事件；检查八镜头规划后暂停，只有在批准后才向同一进程发送渲染指令。CLI 没有内置计划或渲染确认闸门。不要预写 storyboard、角色、关键帧或视频产物。
- **镜像：** 可从已登记公共基础镜像独立派生。只读 Docker inspect 确认 ID `sha256:d414b4270fec6ec2dd245982a522099d8941d8cd114ccd5ec2c6730815f3a706`、`linux/arm64`、Python `3.12.15`；与 ViMax `>=3.12` 相符。用户/工作目录为空、CMD 为 `python3`。本机没有核实其余包和动态库；不改公共标签。
- **必需远端能力：** 外层 Agent + 内部文本规划的 Chat Completions 类接口；图像生成服务；视频生成服务。多候选关键帧默认另需同一聊天模型具备视觉输入。百炼在其他项目的 Responses/Chat Completions 记录不证明 ViMax 的 LangChain、图片或视频适配兼容。
- **当前阻塞：** 尚未指定各服务供应商、模型、环境变量名和值的注入方式、请求/时间/费用预算；镜像 ARM64 wheel、最终输出规格和真实生成服务协议尚未验证。不得读取或粘贴密钥正文。
- **2026-10-23 补充——百炼生成 API smoke（[BAILIAN-GENERATION-SMOKE-01](../env/video/vimax/api-probes/BAILIAN-GENERATION-SMOKE-01/summary.md)）：** 按限额（1+1+1+1 次模型操作、无重试、失败即停）对 qwen-image-3.0 / qwen3.7-plus / wan2.6-i2v-flash 做独立 API 验证，第一步即失败：旧域名 `dashscope.aliyuncs.com/compatible-mode/v1/images/generations` 返回 404 空体（未受理、无计费），后续编辑/视觉工具调用/视频均 NOT_EXECUTED。同域名的 `/responses` 与 `/chat/completions` 此前真实可用，故图像生成/编辑需改用业务空间专属域名 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/images/generations`（需 WorkspaceId）或旧域名 DashScope 原生 `POST /api/v1/services/aigc/multimodal-generation/generation`（qwen-image-3.0 T2I/I2I 均支持，I2I 单图输入即图片编辑）。图像/视频/Chat Completions 图片+tool_choice 组合在本轮均未获得通过证据；重跑需新授权。
- **2026-10-23 追加——路由修复轮（[BAILIAN-GENERATION-SMOKE-02](../env/video/vimax/api-probes/BAILIAN-GENERATION-SMOKE-02/summary.md)），两阶段：**（1）离线修复 + 前置阻断：图片生成/编辑固定新域名 `/images/generations`（编辑走同接口 `image` 扩展字段、base64、单参考图，不用 `/images/edits`/multipart），Chat Completions 保持已验证旧域名路由，视频用新域名原生 `video-synthesis` + `/api/v1/tasks/{task_id}` 轮询；因当时登记文件无 `BAILIAN_WORKSPACE_ID` 在发送前阻断（0 请求，快照 `verification-blocked-01.json`）。（2）用户登记业务空间 ID 后真实执行：**图片生成 PASS**（PNG 1024×576、usage `output_image_count=1`、左红右蓝白底像素核对全符）、**图片编辑 PASS**（`input_image_count=1` 参考图被接受，左红→绿、右蓝保留）、**语言/视觉+强制工具调用 PASS**（qwen3.7-plus，`tool_choice` 指定函数，`image_tokens=578` 直接证据，四字段 green/circle/blue/square 全对）、**视频 UNKNOWN**（创建 200 + task_id，但 40 次轮询全部 401——探针 `poll_video` 漏带 Authorization 的本地 bug，已修复并 36 项离线回归；任务终态未观测，`revision-01.json` 保留根因；task_id 24h 内可查，若远端成功将计 0.75 元）。实际发送：4 模型操作/40 轮询/2 下载，总 wall 427 s，估算费用 ≈1.13 元（D 成功口径）。（3）[video-recovery-01 补验](../env/video/vimax/api-probes/BAILIAN-GENERATION-SMOKE-02/video-recovery-01/summary.md)（同日，仅查询+下载+本地检查授权）：原任务第 1 次查询即 **SUCCEEDED**；MP4 H.264/1280×720/30fps/5.0s/**无音轨**（audio=false 生效）/完整解码/抽帧左绿右蓝布局保持且首尾帧有动态（差异 2.72%），730,447 B（SHA-256 `a01d56f8…a359f`），usage `duration=5, SR=720, audio=false`；本轮 0 生成操作、1 查询、1 下载、总 wall 1.17 s。**结论：SMOKE-02 四项最终全部 PASS（视频为技术有效+有限语义证据）；图像与 LLM/视觉 API 层及视频创建→轮询→下载→媒体检查全链路均有真实通过证据，可进入 ViMax 生成器适配（协议映射层）与镜像依赖验证；正式八镜头任务仍需单独批准与预算，单轮 smoke 不证明多图一致性/多镜头并发/费用规模。**
- **2026-10-23 适配+镜像+禁网验证（[VIMAX-NETWORK-VALIDATION-01](../env/video/vimax/VIMAX-NETWORK-VALIDATION-01/summary.md)）：** 百炼生成器适配完成（隔离副本 `env/video/vimax/adapter-src/`，原件未动，差异登记 `ADAPTATION-DIFF.md`：图片 T2I/I2I 走新域名 `/images/generations`、`image` 字段 1–3 张（>3 拒绝）；视频原生 `video-synthesis` 首帧路径、**创建 0 重试、轮询带鉴权、401 立即失败、下载无授权头**；**首尾帧（2 参考图）与 T2V 明确拒绝不伪装**；selector 参考图上限 8→3 登记变更；重试/超时/并发策略统一显式；`VIMAX_BAILIAN_EVENT_LOG` 生产账本）。新镜像 `vimax-task-bailian:arm64-v1`（`sha256:045fe9cd4ad5…7be6`，arm64，基础镜像身份核验），依赖由 uv.lock `--frozen` 导出后 pip 清华镜像安装（uv 直装因本机 files.pythonhosted.org 不可达，登记偏差；bridge 网络黑洞改 `--network host` 构建，验证容器 `--network none` 不受影响）。**禁网验证 34/34 通过**：环境三 shell 解释器/依赖/ffmpeg；适配单测（含三种能力拒绝与 401/坏 JSON/下载失败留证）；**全新 session 经真实 `main_agent.py --jsonl --stdin-repl` 冷启动到 render、本地拼接与 `final_video.mp4` 导出**（8 shot 契约、1280×720/30fps/40.0s/无音轨、8 段可识别合成片段、8 视频任务各 1 次创建）；cgroup/netns/目录前后采集接线（CPU boundary 因容器退出时序缺失已如实登记）。**结论：具备进入正式八镜头执行审批的条件**；正式任务需知情的能力边界：medium/large variation shot（首尾帧）会被显式拒绝（缓解：user_requirement 约束 small variation），transition 子机位每条额外一次视频调用；建议预算 ≈11 元（无 transition 口径）+50% 缓冲；真实密钥（`DASHSCOPE_API_KEY`/`BAILIAN_WORKSPACE_ID`）仅运行时注入。
- **2026-10-23 审计修复轮（[VIMAX-NETWORK-VALIDATION-02](../env/video/vimax/VIMAX-NETWORK-VALIDATION-02/summary.md)）：** 新镜像 `vimax-task-bailian:arm64-v2`（`sha256:0f59ced…8a902`，从 v1 仅 COPY 代码层）。修复：①资源采集 0.5 s 目标 + 完成握手（容器存活时取最终边界）+ 逐点样本/边界/read_status/gap 全量落盘（实测 CPU 63.8 s/46.4 s wall、内核内存峰值 2.17 GB、blkio throttle 接口 IO 有据、netns 2.0 s 周期开销实测 0.082 s 登记）；②严格判定（报告缺失/损坏/必要项缺失或失败/无握手均非零；独立 finally 回收；唯一容器名+归属核验+删除只读回验；docker 命令超时）+ 宿主注入反例 10/10；③共享请求账本与发送前预算门禁（外层 Agent SDK 显式 max_retries=0、项目重试/形状补发逐次入账；内部 LangChain 回调入账；图片 429-only 重试——**撤销"同步图片重试不重复计费"错误结论**，结果不明不补发；门禁反例实测第 3 次生成被拒）；④render 前能力预检（shot 顺序/variation/相机树/transition 预算；medium 反例实测**零发送拒绝**；**撤销"user_requirement 要求 small 即可正式运行"结论**——decompose 不接收 user_requirement，保障是预检）；⑤下载器跳转计数/相对地址/协议白名单（6 类注入反例全过）；⑥严格验收（工具结果必须 ok=true、进程 rc0、30fps 显式断言、**8 段与 shot 的 SHA-256 严格映射**）。禁网验收 **42/42 必要检查全过、runner ok=true（47.0 s）**。**五维分列状态全部 READY（含登记限制）；具备进入正式八镜头执行审批条件**，尚缺：正式授权与运行时密钥注入。
- **2026-10-24 媒体入口修复轮（[VIMAX-MEDIA-ENTRY-REPAIR-01](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/FIXES.md)）：** 修复 PILOT-03 时代 4 项已确认问题（seed_session 顺序、握手捷径、日志丢失、字典切片防复发）并新发现 3 项（fake 域名未过 provider 检测；**MoviePy concat 失败根因＝宿主 256 核下 imageio-ffmpeg 每 reader ~116 线程撞 --pids-limit 512**，修复为 --cpuset-cpus 0-7 对齐配额；SIGTERM 收尾伪造 ENTRY-FAILED）。**禁网冷启动全链通过**：空 workspace、真实生产 runner/entry（同一代码，仅 API 边界 fake）、19 图 + 8 主体 + 7 过渡全映射、final 40.0s/720p/30fps/无音轨、验收 22/22、10 项异常反例全过、资源 91 点@0.5s 完整、清理零错。**本地执行接线就绪**；正式任务唯一入口 `host_runner.py run --out <dir> --config <正式配置>`（cpuset 修复对正式任务必需）。禁网接线通过不等于真实供应商生成成功。
- **2026-10-24 正式生成完成（[VIMAX-GENERATION-PILOT-04](../env/video/vimax/VIMAX-GENERATION-PILOT-04/closeout-summary.md)）：** 使用 REPAIR-01 修复版生产入口（host_runner.py + generation_entry.py，镜像 v7 未重建），真实百炼 API 完成 8 主体 + 7 过渡视频生成与原生拼接。identity `1362a4aa…40c1`。**技术验收 33/33 PASS**：19 图 + 15 视频各恰好一次创建、全 SUCCEEDED、final 40.0s/720p/30fps/无音轨/完整解码、8 段视觉签名符合故事弧线（日出暖→正午亮→蓝调→深夜霓虹）、无黑帧无重复。总 wall 1063s（17.7 分钟）；CPU 173.9 core·s（avg 0.16 cores，主要等待远端生成）；内核内存峰值 1.80GB；清理零错。**首次真实端到端 ViMax 媒体生成闭环成功。**
- 固定候选任务来自 `references/repos/ViMax/vimax_benchmark/photographer_urban_timelapses_typeA.json`。它是 ViMax 的故事定义，不是 VideoWeaver 共同官方 benchmark，也不是执行配置或评分器。

## 固定源码与入口

- ViMax commit：`fd4b72e7731be6e5f88486206d25ea59849b0285`；核查时参考仓库工作区干净。
- `main_agent.py` 提供 `--jsonl`、`--new-session`、`--session`、`--once` 和隐藏的 `--stdin-repl`；JSONL 输出 turn、tool_start/progress/result、status、error、done、session 等事件。`--once` 可做一次调用，但新建进程不会从 session 文件恢复 `AgentLoop.history`；要经过用户/runner确认后续跑，使用同一存活进程与 session。
- CLI 把 turn 异常保存为 `error` 事件后继续循环，通常仍会正常返回 0；退出码单独不足以判定任务完成，必须解析原生终态和产物状态。
- `agent_runtime.loop.build_runtime()` 构造原生 Agent、tool registry、session index 和上下文压缩器。Agent 的工具循环可执行多轮，单个对话工具轮上限为 50；没有交互审批策略。
- 另有 `main_idea2video.py`、`main_script2video.py` 直接调用 pipeline；UI/Web 调用既有 Agent Loop，需 Node/前端依赖，不作为本机资源测量的首选入口。非交互原生 JSONL CLI 最薄。
- Agent 自带的 `vimax_narrative_planning` 将 `script`/`idea`、`user_requirement`、`style` 交给原生 `Idea2VideoPipeline` 或 `Script2VideoPipeline.plan_text_artifacts()`，写出结构化 artifacts；`vimax_render_video` 检查 artifacts 后调用对应原生 pipeline，保存 render 状态与阶段事件。
- Script2Video 路径：角色抽取 → 人物正/侧/背面肖像 → 分镜/shot descriptions 与 camera tree → 关键帧生成及可选候选图像筛选 → 并发逐 shot 视频生成 → MoviePy 顺序拼接 `final_video.mp4`。内部并发通过 `asyncio.gather`；要以工具 progress 和保存产物确认实际到达阶段，不用外层退出码替代。
- 规划本身会由 LLM 生成/扩写场景和镜头；现有 pipeline 未见强制保持输入镜头数的校验。把源 JSON 的两组 scenes 和八个 shot 的 `first_frame`、`video_prompt` 按顺序转为带 `Shot 1`…`Shot 8` 的脚本文本；把人物外观/服装/相机一致、不得删镜头、16:9、每镜约5秒/约40秒、不额外加对白旁白音乐写入 `user_requirement`。`style` 单列并由任务方案冻结。JSON 的 `scene_num`、`shot_id`、`metadata` 只用于转换/审计，不直接传作内部 storyboard。
- 规划工具返回后，由薄入口检查原生输出的 shot 数量、编号顺序、地点/动作覆盖和人物描述；不符则停在规划阶段，不擅自修写内部产物。用户批准后再让 Agent 调用 render。此检查是任务契约，不修改原生规划算法。

## API 与模型准备表

| 功能 / 调用处 | 协议 / SDK | 任务必要性 | 配置变量名（不含值） | 源码证据与待验证 |
| --- | --- | --- | --- | --- |
| 外层 Agent `agent_runtime/llm.py` | `openai.AsyncOpenAI` → `chat.completions.create`，OpenAI-compatible | 必需；Agent 选择规划/render 工具 | `VIMAX_LLM_MODEL_PROVIDER`, `VIMAX_LLM_MODEL`, `VIMAX_LLM_BASE_URL`, `VIMAX_LLM_API_KEY`（别名 `VIMAX_API_KEY`） | Agent 初始化即要求 key；请求超时300秒，应用层每个 shape 尝试最多3次，shape fallback 最多3组；SDK另使用默认重试设置。usage / 实际 HTTP 交换未见持久化。提供商、工具调用格式及 usage 需现场验证。 |
| 规划及渲染内部 Chat/VLM，`vimax_adapters.py`、LangChain agents | `langchain.init_chat_model`；规划受 `max_retries=0`，request timeout 与 completion 上限由环境读取。多候选图像选择把候选图作为视觉输入 | 文本规划必需；候选数>1时视觉能力必需，设为1可跳过候选比较 | 复用 `VIMAX_LLM_*`；`VIMAX_IMAGE_NUM_CANDIDATES` 或 `configs/agent.local.yaml` 的 `image_selection.num_candidates` | Native adapter 与 Agent 可用同一模型路由；未验证百炼 LangChain tool/image payload、结构化输出和模型 usage。样例候选数为2，代码默认也是2。 |
| 关键帧/角色图生成，`tools/image_generator_*`、`agents/*generator.py` | OpenRouter Images API（`aiohttp`，`/images`）；或 Yunwu 上的 Google GenAI SDK `generate_content` | 最终视频必需；具体供应商可与语言模型分开 | `VIMAX_IMAGE_MODEL`, `VIMAX_IMAGE_BASE_URL`, `VIMAX_IMAGE_API_KEY`（回退到 LLM key） | Native adapter 只自动选择 OpenRouter/Yunwu 适配器；OpenRouter 图片请求最多重试3次。角色正/侧/背图和关键帧数量由规划/缓存/候选数影响请求量。其它 Google generator 在源码存在，当前 native adapter 未接入。具体 key 权限、参考图限制、返回 URL/下载和 ARM64 无关。 |
| 视频生成、轮询、下载，`tools/video_generator_*` | OpenRouter `/videos` + polling/content 下载，`aiohttp`；或 Yunwu Veo task/poll API，`aiohttp` | 每个 shot 通常需视频生成；实际请求数依规划输出镜头数和恢复缓存 | `VIMAX_VIDEO_MODEL`, `VIMAX_VIDEO_BASE_URL`, `VIMAX_VIDEO_API_KEY`（回退到 LLM key）；OpenRouter 另有 `VIMAX_OPENROUTER_VIDEO_DURATION/RESOLUTION/GENERATE_AUDIO` 和 timeout/poll 参数 | Native adapter 只按 OpenRouter/Yunwu base URL 自动路由；OpenRouter 默认 duration 8秒、720p，音频默认开启，poll 间隔10秒、等待上限600秒；Seedance 源码支持5/10秒及16/24fps，但 native adapter 未接入该类。5秒×8能否由被选模型真实稳定支持、最终拼接时长/音频行为均待验证。VOLCANO OpenAI-compatible URL 不等同官方接口。 |
| embedding / reranker，`_build_embedding_model`, `_build_reranker`, `novel2movie_pipeline.py` | LangChain `OpenAIEmbeddings` / SiliconFlow 风格 `/rerank` | **本任务不需要**；Novel2Video 才在规划/检索链要求 | `VIMAX_EMBEDDING_MODEL_PROVIDER/MODEL/BASE_URL/API_KEY`; `VIMAX_RERANKER_MODEL/BASE_URL/API_KEY` | Native Script2Video adapter 不初始化这两者；不要为本任务下载本地模型。 |
| 远端对象存储/媒体下载 | 生成端可能返回 URL；`ImageOutput`/`VideoOutput.save()` 与 provider 负责落盘/下载 | 生成结果转本地关键帧/片段时条件必需 | 与各生成器 key/base URL 相同，服务可能另提供签名下载 URL | 本地源码实现 URL 下载，但未确认所有 provider 的 URL 有效期、鉴权域名、图片/视频直传方式；HTTP 传输次数须实际 instrumentation，不能由逻辑生成数推算。 |
| 音频 | OpenRouter 视频生成默认 `generate_audio=true`；MoviePy concat保留素材音轨的效果需核验 | 用户没有对白/旁白/配乐要求；服务若默认带音频需如实记录 | `VIMAX_OPENROUTER_GENERATE_AUDIO` | 可以在获批配置禁用模型生成音频；其它模型音频默认/音轨拼接和编码能力待验证。 |

代码里的供应商/模型默认值只是 fallback，不是本项目已选路由或可用凭据。可评估语言/视觉继续用已登记聊天服务、图像和视频另配独立供应商；必须逐种协议分别验证。ViMax 与 VideoWeaver 能否共用图像/视频服务，尚待另一仓源码分析和接口实测，不能据此默认共用。

## 依赖和镜像方案

- ViMax `pyproject.toml` 要求 Python `>=3.12`，并提交了 `uv.lock`；基础镜像 Python `3.12.15` 满足版本声明。**建议 uv 按锁文件安装**，构建时使用 `uv sync --locked --no-dev` 并固定 uv 版本/平台；lock 与 manifest 均纳入后续镜像身份。不要裸 pip 更新，也不要用普通 `uv sync` 允许静默改锁。
- 全量运行依赖包含 `aiohttp`、LangChain/`langchain-openai`、OpenAI、Google GenAI、FAISS CPU、MoviePy、OpenCV、Pillow、PyYAML、requests、scenedetect、tenacity 等。Script2Video 实际执行用 LLM、图像/视频 clients、Pillow、MoviePy、FFmpeg；不过 native adapter 顶层也导入 Novel pipeline/图像模块，因而 FAISS、Google GenAI、OpenCV/scenedetect 目前也可能是入口导入依赖，即使该任务不调用这些服务。首版建议锁定完整 app runtime；若要精简，先做纯静态 import 边界改造并形成独立锁，不要直接漏装。
- 当前 lock 中未发现 `torch` 包；`pyproject` 虽声明仅在显式请求 torch/torchaudio 时用的 CUDA 12.8 uv index，但它们不在本项目直接依赖。不要据此安装 CUDA/PyTorch。`imageio-ffmpeg` 是 MoviePy 的依赖之一；公共基础镜像历史登记有 FFmpeg/ffprobe，当前只 inspect 到基础镜像元数据，尚未在容器内核验 binaries/编码器。
- **ARM64 兼容性待实测**：锁版本的 wheel 在目标 aarch64/Python 3.12 的可得性未由本轮联网验证；重点关注 `faiss-cpu`、`opencv-python`/numpy、Pillow 与 imageio-ffmpeg。无 wheel 时需评估编译链和体积，不能在下一轮临时升级/替换。`uv.lock` 有版本锁定不等于已验证目标架构可安装。
- 独立 ViMax 任务镜像从精确基础镜像派生；只 COPY 固定 commit 源码、锁文件、公开默认配置和薄运行入口。不要 COPY `.env`、`configs/agent.local.yaml`、宿主设置、任务输出或模型缓存。构建时不下载权重；没有源码证据表明 Script2Video 需本地大模型。
- 系统层采用基础镜像已经核验后的 ffmpeg/ffprobe 及 H.264 编码器；字体仅当服务返回媒体或工具实际需要字幕时才加入，本任务不预设字体。确认动态库/编解码器再冻结。任务 JSON/生成文件和凭据分别 runtime 挂载；输入只读，工作/输出单独可写。选非 root 固定 UID/GID，宿主输出目录预先归属该 UID，避免宿主/容器相互覆盖和收尾权限错误。`docker run` 明确 `--user`、`-w`、mount、CPU/内存、网络和环境，普通 shell 与 login shell均用绝对 venv Python；Agent 工具 shell也须验证 `sys.executable`。
- 构建草案：①只读检查固定基础镜像和源码身份；②派生新标签/摘要，建立固定路径 venv；③安装锁定依赖（平台无 wheel 立即停止）；④核验解释器、包导入、FFmpeg/编码器、只读输入和输出权限；⑤封存镜像清单及工具路由版本。不得覆盖旧标签、拉取基础镜像、安装未冻结依赖或把缓存烘焙进镜像。

## 轨迹、请求和资源采集

- 原生 session 数据位于 `.vimax/sessions.json`、`.working_dir/<session>/` 与 `.vimax/logs/{loop_history,tool_calls,revisions}.jsonl`；CLI JSONL 另可由宿主逐事件持久化。工具日志仅存参数/内容 preview（各截断500字符），turn record 在 Agent turn 结束时写入；进程中断可能失去完整turn记录。因此后续薄入口须每收到一条原生事件就原子追加 raw JSONL，保留异常与退出，不只依赖最终 session log。
- 现有外层 `OpenAICompatibleLLM` 没有把 usage、响应模型、provider request ID、每次 retry/shape fallback 的每次发送记录到 session；内部 LangChain 和 `aiohttp` 图像/视频请求也没有统一请求账本。后续需要请求边界最小 instrumentation（角色/阶段、逻辑 request ID、起止、请求模型、响应模型、usage原字段、状态、SDK retry/尝试序号、job ID、下载状态），严禁记录认证头/key。**逻辑模型请求、一次尝试、HTTP传输、远端生成job分开计数**；没有 HTTP 传输证据则次数 unknown，usage 不代表费用。
- 同一图像/视频请求的服务端重试、候选图、LLM视觉筛选、轮询和下载都可能扩大请求/费用。文本客户端最多3次重试；OpenRouter image 最多3次；Seedance 轮询最长300×2秒；OpenRouter video 轮询默认到600秒，每10秒一次；video job数通常随规划 shot 数增长。正式预算须在选定服务后按实现确认，明确 create/轮询/下载分别限时、总 deadline 与取消方式，不做无限探针。
- 复用 `src/agent_workload_characterization/collectors/resource_sampler.py` 的 `ResourceSampler(interval_s=0.5)` 和 `runners/container_runtime.py` 的 `DockerCliRuntime`/cgroup reader。已有 video-use runner演示容器内 `/proc/net/dev` 逐接口采样；网络只报容器 netns 各接口，不归因 API 字节、不跨接口重复求和。采样覆盖容器内 Agent、MCP/辅助进程（若有）、Python、MoviePy/FFmpeg 全部子进程。
- 保存 CPU 累计值和实际相邻采样区间 core、`memory.current`/可用 kernel peak、cgroup I/O累计量和有效区间速率、netns接口 RX/TX、实际采样时刻/gap/缺读。测量输入、session工作目录、宿主提交/归档目录运行前后 apparent bytes；共享缓存不归属。阶段边界使用真实 Agent/tool/progress 事件标记 planning、等待批准、图像生成、视频 create/poll/download、concat、cleanup；未观测阶段标 unknown。远端 GPU/CPU不在本机 scope。
- runner 在正式启动时采 monotonic 起点并立即持久化；Agent work 与容器/采样/归档窗口分开。deadline须能取消 Agent 与子进程，finally 独立停止采样、停止/回收进程、导出 raw 和 verify 容器删除；任务结果、Agent终止、测量完整性、基础设施清理和报告状态分列。镜像保留。

## 下一轮最小验收顺序（本轮均未执行）

| Gate | 验证范围 | 停止条件 |
| --- | --- | --- |
| A. 禁网环境 | 固定解释器（普通/login/tool shell）、锁来源和架构、FFmpeg/编码器、只读输入/可写输出、CLI JSONL、合成媒体本地 concat、deadline/子进程回收 | wheel缺失、导入缺库、路径或权限不一致即停；不下载本地模型。 |
| B. Fake 生产入口 | 新 session；驱动原生 JSONL Agent与真实工具路由、自动 artifact/log/history、fake 外部模型边界，验证8镜头合同、计划闸门和 render/concat/清理 | 仅能证明入口和数据链；不可写成真实服务兼容。不得手动保存应由生产链产生的 artifact。 |
| C. 每种必要服务一次有界兼容性验收 | 外层/内部 Chat Completions、图片 generation、视频 create/poll/download 分开；核对响应模型/usage、job状态、实际HTTP证据和媒体格式；预算上限由用户选定后冻结 | 每种协议最多一次逻辑验收（SDK retry关或逐次计入）；任一认证/协议/媒体失败即停，不反复探针。请求数与网络连接数分别记。 |
| D. 唯一正式8镜头任务 | 新预算、批准、冻结身份；先Agent规划并按合同验收、批准后同session render；采集资源/轨迹；离线检查最终视频、八段/时长/画幅/音轨；若无官方 scorer，只报告技术有效性与故事符合证据，不造 reward | 单次 attempt；deadline/调用/资源预算耗尽即停并归档，不因质量不符自动重跑。 |

## 下一步批准前需确定

下一轮可先授权准备阶段（固定源码和镜像的静态/禁网环境检查、fake 原生入口回归），再单独决定是否授权真实 API 兼容验收。正式任务另需单独预算与批准。请只确定：

1. 外层/视觉 LLM 供应商、模型及环境变量名；
2. 图像生成供应商、模型及环境变量名；
3. 视频生成供应商、模型及环境变量名（如要共用某 key，请只确认变量名/服务支持，不提供 key 文本）；
4. 准备/API兼容/正式阶段各自的逻辑请求数、wall deadline、输出 token/费用预算。

任务规格沿用本页开头的16:9、约5秒/镜、约40秒目标；生成服务自身的音频行为如实核验记录，不额外要求对白、旁白、配乐或移除音频。

密钥只在后续明确批准的运行时注入，不能进入源码、日志、镜像或报告。本轮没有运行依赖安装、真实服务调用或生成验收。
## 最新真实规划验证（2026-10-24，VALIDATE-03，已由PILOT-04采纳）

`VIMAX-PLANNING-VALIDATE-03` 已按一次授权完成，规划契约通过，未生成任何媒体。run_id：`vimax-planning-validate-03-20261024T014216Z-3d8d561a`；冻结 identity SHA-256：`7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2`；批准 SHA-256：`3804206daa1657357b07cb4687906e6b55c96aba767b9f1b5b5390792f975929`。镜像 `vimax-task-bailian:arm64-v7-capability-planning-01`（`sha256:a97ea6076…1f176f3`，89个适配源码文件与宿主哈希相同）。

结论：8项storyboard/shot descriptions与无环camera tree均通过原生schema/引用检查，variation全为`small`（适配器当前`wan2.6-i2v-flash`只接受单首帧，旧PILOT-02的不兼容项为第3镜`large`、第5/6镜`medium`）；13次逻辑请求、36,753 tokens、attempt wall 70.54秒；无媒体生成、无评分。该规划结果被`VIMAX-GENERATION-PILOT-04`采用作为媒体生成来源。证据与机器检查见[中文摘要](../env/video/vimax/VIMAX-PLANNING-VALIDATE-03/execution-01/closeout-summary.md)、[run-report](../env/video/vimax/VIMAX-PLANNING-VALIDATE-03/execution-01/run-report.json)、[plan-check.json](../env/video/vimax/VIMAX-PLANNING-VALIDATE-03/execution-01/workspace/attempt/plan-check.json)与[manifest](../env/video/vimax/VIMAX-PLANNING-VALIDATE-03/manifest.json)。后续媒体生成须另行批准；本次授权不延伸。
