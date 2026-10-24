# VideoWeaver 执行准备分析

## 当前复现与排障入口（2026-10-24）

当前证据为“原真实生成8图/8视频但未完成merge＋独立离线恢复＋修复后真实Agent仅拼接通过”，不是修复后一次连续端到端成功。优先复用v2镜像及固定runner/gateway，完整错误与修法见[VideoWeaver排障与快速复现备忘](videoweaver_troubleshooting.md)。其中明确记录login shell PATH、运行时安装、SSE/用量软门禁、输出保护、任务验收范围及尚未合并summary到Responses total阈值的边界。本页下方按阶段保留的准备/验收结论不代表全部仍为当前状态，也不构成执行授权。

更新：2026-10-24。本页是**唯一主文档**：顶部为 2026-10-24 已完成交付的执行结果（镜像/适配/禁网全链），下方保留静态准备分析与约束；本页不是执行批准。ViMax 对应记录见[vimax_execution_preparation.md](vimax_execution_preparation.md)，剪辑仓库见[video_editing_troubleshooting.md](video_editing_troubleshooting.md)。

## 2026-10-24 执行交付（镜像＋百炼适配＋禁网冷启动全链）

本轮完成（允许的依赖下载/最小安装/镜像构建；未读凭据、未调用真实模型/媒体 API、未创建 APPROVAL/ATTEMPT）：

| 交付项 | 结果 |
| --- | --- |
| 任务镜像 | `videoweaver-task-bailian:arm64-v1`＝`sha256:60cf9b9fe2317a7b92cdba48f70cb74c77321642ddb75e3c64ccbb84e92062d8`（linux/arm64）；基础 `video-common-base:arm64-v1`；最小冻结 venv（requests/httpx/Pillow/opencv/moviepy/numpy/tqdm/PyYAML/json-repair/imageio-ffmpeg/openai）；Codex CLI 0.163.0 静态 musl（本地已核验 tar.gz 装入，不重新下载） |
| 隔离源码 | `env/video/videoweaver/source/`，8 文件差异登记见 `evidence/adaptation-diff.json` 与 `evidence/source-manifest.json`；参考仓库未改 |
| 自定义 case | `env/video/videoweaver/case/dataset/photographer_urban_timelapses/`（skill_query.json＋task.txt＋registered-script.txt），来源/转换/哈希见 `evidence/case-manifest.json` |
| 适配技能 | **image-gen**（qwen-image-3.0，T2I/I2I `/images/generations`）；**video-gen**（wan2.6-i2v-flash 单首帧，create→轮询→下载，拒绝首尾帧/参考视频/音频驱动/延长/文生视频/非 wan 模型）；**vision-understanding**（图片 base64 内联；视频**抽帧审阅 mode=sampled_frames**，直接视频理解 unsupported）；**merge-video**（moviepy 读取有界重试）；**summary_txt**（百炼路由） |
| harness 最小修复 | `args.py`（CODEX_HOME 派生会话目录）、`codex_cli_tool.py`（sandbox/bypass 不堆叠）、`get_output_dir.py`（VW_OUTPUT_DIR 优先，抵御外源 OUTPUT_DIR 污染） |
| 禁网冷启动全链 | **通过**（network=none＋add-host，真实 `pipeline.py`＋真实 Codex＋真实技能/FFmpeg，仅 fake Responses/图片/视频边界）：1 个 case、SUCCESS after 1 attempt；8 首帧图、8 视频创建/轮询/下载、1 次 merge；final.mp4 **H.264/1280×720/30fps/40.000s/无音轨**、完整解码；ReAct_process/rollout/basic_results 生成；**fake 边界 0 外部泄漏（rejected=[]）**；8 段 clip 哈希各异 |
| 生产薄入口 | `env/video/videoweaver/runner/host_runner.py`（配置化 `--config`；容器生命周期＋cgroup 采样＋删除前 logs＋清理核验＋run-report）；验收命令 `runner/acceptance_fullchain.sh`；配置模板 `runner/acceptance-config.json` |
| 证据 | `evidence/acceptance-run-3/run-report.json`（采样 72 点@0.5s、CPU 48.98 core·s、内存 kernel peak 1.69 GB、IO 写 2.05 MB、清理核验）、`evidence/acceptance-closeout/`（final/clips/run.log/ReAct/rollout/overall）、`evidence/acceptance-media-map.json`、`evidence/counterexamples-*` |
| 异常反例 | 7 项（video 尾帧/参考视频/文生视频/非 wan 模型、image max_images>1/web_search/gpt-image-2）全部**发送前拒绝**，fake 边界零请求 |

**关键接线经验（供真实执行复用）**：
- Codex 首个 Responses 请求返回纯文本会让它直接结束 turn；必须持续返回 function_call 驱动，且每个**长命令**若超过其 wall 阈值会返回 `Process running` 状态——fake 用 `--poll-interval 1` 避免；真实任务需接受 Codex 对长命令的异步 running 语义并等待终态。
- **moviepy 读取刚生成的 clip 在 256 核宿主下偶发 0 字节**（读者线程膨胀，等价 ViMax R6）：本机用 `--cpuset-cpus 0-7`＋`--pids-limit 4096` 稳定通过；**不把 0-7 写死为通用配置**，由 `acceptance-config.json` 提供。
- 输出目录必须用 `VW_OUTPUT_DIR` 显式固定：Codex 会向 exec 子进程注入非预期 OUTPUT_DIR（观察到 `/Users/bytedance/.openclaw/workspace/generate_materials`），`get_output_dir.py` 已优先读 VW_OUTPUT_DIR。
- 历史早期验收曾用容器root清空证据卷处理属主问题；此做法已弃用，不能复用于正式任务。当前必须唯一新目录、排他创建和正确UID/挂载权限，不递归删除旧证据。

## 2026-10-24 第二轮：正式生产入口、发送前预算、证据保护与完整资源采集

本轮把交付从"offline 脚本完整"提升为**同一个可配置固定入口支持 offline 与 live 分支**，并补齐真实发送前预算、唯一新目录保护、完整采集与统一结果判定。镜像 v1 未变（网关/fake/config 为宿主挂载文件，测试镜像与生产镜像一致）。未读凭据、未调用真实 API、未创建 APPROVAL/ATTEMPT。

### 交付与证据分列

| 项 | 证据 |
| --- | --- |
| **固定生产入口** `runner/host_runner.py`（v2） | `--mode offline|live` 共用 case 初始化/Codex/技能/预算/监控/导出/验收/清理；live 分支真实路由结构（网关上游=dashscope 工作空间域名、生产 CODEX_HOME config、bridge 网络），无 fake 域名/脚本/挂载；本轮用合成凭据＋fake 上游 transport 注入验证 live 分支生产代码 |
| **受控转发边界＋持久化账本** `gateway/gateway.py` | 统一处理 Codex Responses(SSE)、Chat Completions、图片创建、视频创建/轮询、媒体下载；**发送前原子 charge**（记账→fsync→才转发），budget0/账本写失败/deadline 均发送 0；`<run>/ledger/ledger.json` 计数 llm/image/video/polls/downloads＋usage 软阈值＋video_tasks 持久化（只查询原 task）；上游密钥仅网关持有，任务凭据 `VW_TASK_TOKEN` 本地化 |
| **证据保护（不重置）** | 每次 run **唯一新根目录**、排他创建、已存在即拒绝（旧文件字节不变）；拒绝仓库/data/家目录等宽泛路径；offline 测试也用独立新目录，历史 acceptance 证据未动 |
| **完整资源采集** | cgroup CPU/memory.current/内核peak/IO（ResourceSampler 逐点 `samples/resources.jsonl`）、netns 逐接口（`samples/netns.jsonl`）、run 前后目录占用（`dir_before/after`）；采样线程 stop Event＋有限 join；容器存活时取最终边界 |
| **完整日志** | docker exec stdout/stderr **实时落盘**（`logs/exec-stdout.log`/`exec-stderr.log`）；删除前补取 `logs/docker-logs.txt`；gateway/fake 日志落盘 |
| **统一结果判定** `judge()` | pipeline_rc=0 不等于成功；校验 final 规格（40s/720P/30fps/H.264/无音轨）、8 clip、账本无缺口、资源/日志完整、清理核验；关键预算/日志/采集/清理失败即整体失败 |
| **镜像身份** | 镜像 v1 不变；gateway/fake/config/runner 哈希见 `evidence/production-entry-manifest.json` |

**禁网验收（同一入口，仅替换外部 API/媒体响应）**：
- **offline 正常路径 PASS**（`evidence/fullchain-v2-094052/`）：1 case SUCCESS、账本 llm=19/image=8/video=8/polls=16/downloads=16、final 40s/720P/30fps/H.264/无音轨、8 clip、judgement 19 项全过、清理核验。
- **live 分支 PASS**（`evidence/live-v2-094230/`，`VW_LIVE_FAKE_TRANSPORT=1 VW_GATEWAY_UPSTREAM=http://127.0.0.1:8666 VW_LIVE_NETWORK=none`，合成凭据）：同一入口、真实 config 结构、只替换 upstream transport。
- **15 项异常反例** 逐项证据见 `evidence/counterexamples-v2.json`，含：live 不加载 fake（`runner/cx-live-nofake.sh` PASS）；预算0/并发争额度/重启不重置/写失败发送0（`runner/test_gateway.py` 7 项单测 PASS）；不支持模式发送0（`counterexamples.sh` 7 项）；上游失败 exec 日志保留＋清理（`evidence/cx10-*`）；deadline 发送前阻断＋回收（`evidence/cx12-*`）；缺 final 仍失败（judge 单测）。

### 生产门禁边界（诚实声明）
- "禁网生成链通过"＝真实 Codex/技能/FFmpeg/pipeline 经统一入口＋受控网关在禁网下走通，账本与媒体规格核验通过；**不是**真实供应商兼容或真实质量证明。
- "正式入口准备完成"＝offline/live 共用入口、发送前账本、目录保护、采集、日志、判定已实现并经禁网与反例验证；**真实 live 调用仍需单独授权**（注入真实上游密钥、bridge 网络、真实 WorkspaceId）。
- 网关的 usage 软阈值仅记录不阻断；代理转发次数、模型逻辑响应、工具调用、媒体任务、网关内部尝试分列；`原生cost=0` 只是占位，报告一律标实际账单 unknown。

### 下一轮真实执行（另行批准）
```bash
# live 生产（注入真实上游密钥；不添加 fake transport）
BAILIAN_WORKSPACE_ID=<ws> VW_UPSTREAM_API_KEY=<注入> \
  python3 -B env/video/videoweaver/runner/host_runner.py --mode live \
  --config env/video/videoweaver/runner/live-config.json --out <唯一新目录>
```
唯一执行命令、配置模板与身份见 `evidence/production-entry-manifest.json` 与 `runner/{live,offline}-config.json`。

## 2026-10-24 第三轮：PILOT-01 修订、修复与离线恢复成片

本轮不调真实 API、不读凭据、不运行真实 Agent、不重新生成媒体、不创建新 attempt；只做修复、历史修订与本地媒体后处理。

**失败归因更正（不再写"反复安装/空命令、纯模型能力不足"）**
- 事实：早期 Codex 执行一次 `pip install Pillow httpx requests`（系统 pip），装到系统 python（原本无 requests），使 image-gen/video-gen 得以运行；merge 前按 merge-video/SKILL.md 再执行一次 `pip install moviepy opencv-python`（系统 pip），该进程长 RUN 未结束（原因 unknown，不猜网络/冲突），Codex 轮询/空命令、从未调用 merge 脚本，80 次 LLM 预算耗尽。
- 解释器实测：普通 shell `python`→`/opt/videoweaver-venv/bin`；**login shell（bash -lc，即 Codex exec_command）`python`/`pip`→系统 `/usr/local/bin`（无 requests/moviepy）**——根因是 login shell PATH 重置。

**修复（镜像 v1 不变，经生产挂载纳入 identity）**
- `source/skills/merge-video/SKILL.md`：依赖已在固定 venv；**禁止运行时 pip/uv pip install**；缺依赖报环境错误；用 `/opt/videoweaver-venv/bin/python` 绝对路径调用；merge 前确认片段直接拼接。host_runner 挂载修复版覆盖镜像旧版（`merge_skill_fix`，纳入 source_identity）。
- `gateway/gateway.py`：SSE 解析重构（多行 data、data 后有/无空格、CRLF、`[DONE]` 不算成功终态、按 response_id 去重 usage、区分 input/cached/output/reasoning/total、缺 usage 记 `usage_missing`）；**软阈值在下一次 LLM 转发前检查**（`soft_threshold_exceeded`）；硬门禁/原子预留/持久化保留。
- 回归：`runner/test_sse.py` 7 项单测通过；最小禁网 Codex 经网关会话验证终态与 usage 落盘、软阈值到达后下一次转发为 0。

**usage 离线重算（run-944af65d 原生 rollout）**
- 80 条 `token_usage_record`、80 个唯一 response_id；逐响应求和 == 最后 turn/thread 累计：input 3,281,314 / cached_input 2,965,760 / output 16,676 / reasoning 2,620 / **total 3,297,990**。cached 是缓存上下文输入、非独立文本、非账单；**登记的 500k 软阈值原未有效执行**（在线采集失败），现已在网关层修复。

**额外 live run 核清（只读）**
- run-58dc50b4（1 次转发 404，上游路径 bug，未受理）与 run-ce40d6e0（1 次转发 401 InvalidApiKey，凭据引号 bug，未受理）为批准前预检接线失败；run-944af65d 为唯一正式 attempt（80 次受理转发）。本地启动 3 次、合计转发 82（2 未受理）。

**离线恢复成片（独立 scope）**
- 用 run-944af65d 的 8 段真实视频，固定 venv ＋ 原生 merge 脚本，禁网容器（cpuset 0-7/pids 4096/mem 4g）：`output/final-recovered.mp4` **h264/1280×720/30fps/40.000000s/无音轨/完整解码**，抽帧 8/8 非黑非纯色、色彩符合故事弧线。**定性为"原始 Agent 未完成任务后的独立离线后处理恢复"**，不并入原 attempt，不改写原 run 成功标记。
- 证据与修订：`env/video/videoweaver/revisions/PILOT-01-recovery-01/`（recovery-notes.md、recovery-manifest.json、inputs/output/logs）。

## 2026-10-24 第四轮：解释器根因修复＋真实"仅拼接"Agent 验证（MERGE-VALIDATE-01）

**解释器根因修复（不只加提醒）**
- 复用 video-use 已验证的容器内 login-shell 接线：镜像 `/etc/profile` 末尾追加 `export PATH="/opt/videoweaver-venv/bin:$PATH"`（派生 **v2 镜像** `sha256:933363d7…bb6eb`，v1 保留）。
- 实测：v2 下普通 shell 与 **bash -lc（Codex exec_command）的 `python`/`pip` 均解析到 `/opt/videoweaver-venv/bin`**；requests/PIL/moviepy/cv2/imageio-ffmpeg 全部可导入；真实 Codex 最小会话 exec_command 输出 venv python + REQ_MOVIEPY_OK。
- 技能说明统一：image-gen/video-gen/vision-understanding/merge-video 均加入"本项目环境契约"（依赖已预装、**禁止 pip/uv pip install**、固定 venv 绝对 python、缺依赖报环境错误）；删除 merge 原生前置依赖 pip install 矛盾行；merge 经生产挂载（merge_skill_fix）纳入 identity，镜像内 image/video/vision 已更新。

**真实 Agent 仅拼接验证（VIDEOWEAVER-MERGE-VALIDATE-01，一次 attempt retry=0）**
- 新 case（merge_validate_01/case-merge-01/task.txt）、新 session、唯一新输出目录；输入为 run-944af65d 的 8 段真实视频（复制，哈希与 manifest 8/8 匹配）；媒体额度全 0（image/video/polls/downloads=0，网关发送前拒绝）。
- 真实执行：**llm_calls=7**（6 Responses＋1 summary chat），**image/video/polls/downloads 全 0**，无安装命令；rollout 显示 Agent 实际调用 `/opt/videoweaver-venv/bin/python …/merge_videos.py --video_paths …`（venv 绝对路径）。
- **SSE 修复验证**：真实 Responses 终态 `sse completed=6`；网关 usage total=**93,487** 与 rollout 6 条 token_usage_record per-response 求和/最后累计**完全一致**；summary chat 的 usage 单独记录（无 response_id，不影响 total 软阈值）。
- 成片：closeout/merge-agent-output/final.mp4 **h264/1280×720/30fps/40.000000s/无音轨/完整解码**（Agent 生成，非预填；与离线恢复成片字节相同是相同输入+相同脚本的确定性结果）。
- 资源单独 scope：n_samples=265、CPU 119.1 core·s、wall 132.6s、内存内核 peak 1.70 GB；清理核验通过、无残留容器。
- host_runner 生成-judge 仅 eight_clips 一项不适用于 merge-only（已修 judge 跳过）；任务级验收按任务书 §七全过（见 `evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json`）。

**仍待验证**：真实生成任务的 v2 镜像端到端（修复后再次八镜头生成）、在线软阈值在真实大 usage 上的生效边界（由离线反例覆盖）、新身份冻结后的正式生成。

## 2026-10-24 第五至第十轮：观测/采集修复与验收经过（已收拢）

以下六轮为观测与采集的限定离线修复与验收，逐轮细节已按原字节保存在 `local_archive/20261024-doc-cleanup-647394/docs/videoweaver_execution_preparation.md`，可追溯的验收表见 `env/video/videoweaver/revisions/PILOT-01-recovery-01/observation-prep-acceptance.md`。只做采集/观测代码修复与定向离线验证，不调真实模型/API、不执行正式任务。当前结论：

- 共享采集器增加运行中JSONL流（`enable_stream`）、测量质量验收（`assess_resource_quality`）与JSONL读取器；VideoWeaver生产入口启用`resource-stream.jsonl`运行中落盘、`stages_rel_s`、受限目录扫描与`measurement_quality`/`stream_state`；ViMax补齐`dir_before`/`dir_after`。
- gateway usage修复：非SSE（summary Chat Completions）分字段提取且`total_tokens`计入统一软阈值；缺`response_id`的SSE usage归本地请求去重、不合并；经真实handler＋fake上游验证（429、硬门禁不退化）。
- judge验收补全：资源流契约校验（`validate_resource_stream`）、assess v3逐样本read状态与boundary/scope身份核对、`sample_content_digest`全字段摘要（内存==文件）、流计数守恒、零I/O状态、连续采样覆盖（`coverage_ok`）；新增 `numeric_consistent`/`scope_identity_ok` 等，短任务boundary_only贯通；旧记录只读验证源不变（含 `audit-verify-133803`）。
- 修正早期误判：**video-use 与 OpenStoryline 已具备目录边界测量**（`directory_boundaries.before/after_agent`、`boundaries_before` 等），早期"未见显式前/后测"表述已撤回；两者本轮未改，语义一致性待真实任务核对。
- 累计122项定向/回归测试通过，并完成真实 `ResourceSampler`＋`CounterSnapshot` 集成验证（内存摘要==文件摘要）。**122项离线测试通过不等于 video-use/OpenStoryline/ViMax/VideoWeaver 四个仓库的新采集口径均已由真实任务验证。**

## 结论（简短）

1. **能否复现**：工作流可以复现；官方 `dataset/` 目录只有发布占位 README，没有任何官方 `skill_query.json`、case、rubric 或参考素材（历史记录的"dataset 未发布"在本 commit 依旧成立）——**只阻塞官方 benchmark 复现，不阻塞本轮自定义故事**。本轮真实阻塞是**原生媒体技能硬编码火山 ARK SDK**（Seedance/Seedream/TTS/ASR）与 **Codex CLI 二进制需装入任务镜像**（本机无二进制，但本地已有已核验的安装包，不必重新下载）；当前已验的百炼接口不能直接替换，必须先做能力适配。
2. **用什么 Agent**：仓库原生设计是 **外层通用 Agent（Codex / Claude Code / OpenClaw）驱动基础技能库**，不内置 Agent。与本项目已验路径对齐的是 **Codex CLI（0.163.0 arm64 musl）**，经 `codex exec --json` 非交互驱动；保留原生基础技能（image-gen/video-gen/merge-video/get-output-dir/task-tracker）。
3. **同一故事任务**：`references/repos/ViMax/vimax_benchmark/photographer_urban_timelapses_typeA.json` 的故事与八镜头目标可以直接转换复用为 VideoWeaver 的自定义 case（文本输入即可，无需参考图/音频）；它不是 VideoWeaver 官方共同 benchmark，不能与 ViMax 结果做严格受控对照。
4. **百炼三模型候选**：`qwen3.7-plus`（语言/视觉、Chat Completions 或 Codex Responses）直接候选；`qwen-image-3.0`（`/images/generations` T2I/I2I）直接候选；`wan2.6-i2v-flash`（首帧 i2v，5s/720P/无音轨已验证）**部分满足**本故事的首帧路径，但 VideoWeaver 原生 video-gen 还声明首尾帧、参考视频、音频驱动、视频延长等能力，均未验证，适配器必须显式拒绝这些模式。
5. **新 API/权重/GPU/素材**：需要 **Codex CLI 装入镜像**（不联网依赖）；需要**百炼媒体适配层**（不是新增供应商）；需要**自建最小 dataset case**（故事 .txt＋skill_query.json＋可选 rubric）；不需要 GPU、不需要本地权重（本故事不触发 audio-vocal-separate 的 Demucs/torch）、不需要新增下载素材。
6. **下一步应批准的一项准备任务**：**B 阶段——构建独立 `videoweaver-task-bailian:arm64-v1` 任务镜像＋禁网冷启动全链（真实生产入口 `inference_CodeX/pipeline.py`，仅外部 API 边界 fake，全新 workspace）**。该步骤涉及镜像构建与依赖安装，需单独授权；不含正式付费调用。

## 1. 仓库与运行方式核查（源码依据）

参考仓库：`references/repos/VideoWeaver`，commit `c809392fe6c2c8b22472049684aaefc650e31bde`（2026-06-07 "Initial commit"），核查时工作区干净，参考原件未改。全仓 146 个文件、约 4.3 MB，无旧实验归档。

### 1.1 它是自带 Agent 的应用吗？

**不是。** VideoWeaver 是"基础技能库 + 三套外层 Agent 适配 harness"（README §About）：技能在 `skills/`，harness 在 `AutomaticSkillOptimization/inference_{CodeX,ClaudeCode,OpenClaw}/`。真正的"思考与规划"由外层通用 Agent（Codex/Claude/OpenClaw）完成，仓库只提供技能发现与批量运行脚本。因此**必须用外层 Agent 驱动**；本项目的选择是复用已验证的 Codex CLI＋百炼路径，不做手工拼接。

### 1.2 真正入口

推荐入口：`AutomaticSkillOptimization/inference_CodeX/pipeline.py`（`python .../pipeline.py --dataset <dir> --target_task <category> --skill_type expert|vanilla|baseline ...`，先 `--dry_run true`）。它：
- 调 `args.setup_codex_workspace()` 把 `skills/` 复制到 `_codex_workspace/.agents/skills`，并把 `configuration_files/codex/config.toml`（仅设 `OUTPUT_DIR`）写入 `_codex_workspace/.codex/config.toml`；
- 按 `dataset/<category>/skill_query.json` 生成会话名，通过 `codex_cli_tool.codex_chat()` 执行 `codex exec --skip-git-repo-check --json -C <cwd> --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox [--model <m>] "<prompt>"`；
- 解析 stdout JSONL 事件与 `~/.codex/sessions/**/rollout-*.jsonl`，产出 `ReAct_process.json/.txt`、`basic_results.json`、`run.log`，并归档 `generate_materials{,_failed,_half_stopped}`、`running_logs` 到 `<exp_id>/`。

关键文件：`inference_CodeX/pipeline.py`（698 行）、`inference_CodeX/codex_cli_tool.py`（`codex_chat` 约 L464）、`inference_CodeX/running_utils.py`、`codex_claude_pipeline_utils.py`、`args.py`、`utils.py`（`process_input` L520、`save_basic_result` L483）、`prompts.py`（`CODEX_TASK_PREFIX` L133）。

### 1.3 从用户输入到最终视频的步骤

以 `--skill_type expert`（默认，含"先让模型创建组合技能"）为例：
1. **技能创建**：对每个 category 用 `video-skill-creator` 技能让模型写一个组合技能 SKILL.md（`create_skill_task`，会话名 `create_<skill_name>`）。
2. **任务推理**：`process_input` 把 case 文件夹的 `.txt`＋参考图/视频/音频拼成任务提示（`CODEX_TASK_PREFIX` 中文指令：用 task-tracker 分步、产物进 `get-output-dir`、最终命名 `final.mp4`）。
3. **执行**：Codex 读 SKILL.md、调用基础技能脚本（image-gen→video-gen→merge-video），轮询生成任务、下载媒体。
4. **收尾**：`check_gen_done` 找 `final.mp4`、`jsonl_to_react_process` 生成轨迹、`save_basic_result` 统计。

可选 `--no_composition_skills true`：跳过第 1 步，Agent 直接只用基础技能跑 case（baseline 模式）。最小禁网验收建议用此模式先打通，再单独批准技能创建阶段。

### 1.4 本地 vs 外部

| 步骤 | 本地代码 | 外部服务 |
| --- | --- | --- |
| Agent 推理/决策 | Codex CLI（容器内二进制） | 模型 API（百炼 qwen3.7-plus，**Responses**） |
| 图片生成 | `skills/image-gen/scripts/generate.py` | **Ark SDK** `Ark.images.generate`（Seedream 5.0 / gpt-image-2）→ 需适配百炼 |
| 视频生成 | `skills/video-gen/scripts/generate.py`（含 TOS 上传、ffprobe 预处理） | **Ark SDK** `content_generation.tasks.create/get`（Seedance 2.0）→ 需适配百炼 |
| 视觉理解 | `skills/vision-understanding/scripts/vision_understanding.py` | **两步协议**：Ark SDK `files.create` 上传→`file_id`（视频抽帧）；再 OpenAI SDK `responses.create`（Ark 域名）→ 需适配百炼 qwen3.7-plus（去掉上传依赖、改内联） |
| 合并/转码 | `skills/merge-video/scripts/merge_videos.py`（moviepy＋opencv＋ffmpeg，`threads=4`） | 无 |
| ASR / TTS | `skills/automatic-speech-recognition`、`skills/text-to-speech` | 火山 OpenSpeech ASR/TTS（本故事不需要） |
| 目录/任务追踪 | `get-output-dir`、`task-tracker` | 无 |

### 1.5 浏览器 / Node / FFmpeg / GPU / 本地权重 / 额外服务

- **不需要浏览器、不需要 Node**（Codex CLI 用静态 arm64 musl 二进制）。
- **需要 FFmpeg/ffprobe**（`video-common-base` 已含 7.1.5＋libx264/aac）。
- **不需要 GPU、不需要本地模型权重**（本故事不触发 audio-vocal-separate 的 Demucs/torch、不触发 video-shot-split 之外的推理；PySceneDetect 是规则式）。
- 额外服务仅当用到对应技能才需要（TTS/ASR/音频分离）；本故事都不需要。ElevenLabs 已登记但按约束不加入新流程。

### 1.6 交互 / 后台 / 人工步骤

- 三个 harness 均为**非交互批量**：Codex 走 `codex exec --json`（`--dangerously-bypass-approvals-and-sandbox` 跳过审批，与 video-use 已验证一致）；Claude/OpenClaw 同样自动审批（`OpenClaw_Setup.md` 要求 `defaults.security=full`）。**无人工确认点**。
- 后台任务：video-gen 支持 `--background`/`--internal-worker`（子进程写 run.log），merge-video 前台阻塞；pipeline 用 asyncio 并发，默认 `--max_concurrency 5`（测试建议 1）。
- 最小非交互接线：容器内直接运行 `inference_CodeX/pipeline.py`（或宿主薄 runner 调用它），不接 OpenClaw/`session_status`。

### 1.7 原生轨迹在哪里保存？

- Codex rollout：`~/.codex/sessions/**/rollout-*.jsonl`（`args.CODEX_SESSIONS_DIR`）；pipeline 复制为 `original_ReAct.jsonl` 并派生 `ReAct_process.json`/`.txt`、`basic_results.json`、`run.log`（含生成任务状态/URL 与 `Token Used`）。
- 技能内日志：`.../videos/multi-turn-video-log.json`、`.../images/multi-turn-log.json`、`task_tracker.json`。
- **能否保存请求/工具调用/返回/阶段/usage/生成任务 ID**：**能**。rollout JSONL 含 `session_meta`（id/timestamp/cli_version/model_provider/cwd）、`response_item`（message/function_call/function_call_output）、`event_msg`（`token_count` usage、`task_complete`）；`codex_cli_tool.summarize_codex_records` 已抽取 `session_id/tool_call_count/usage/terminal_reason/returncode`。生成任务 ID 在 run.log 与下载的媒体路径中。**缺口**：`calculate_cost_from_jsonl` 明确"本地 JSONL 不暴露计费 USD，cost 恒为 0"；真实 HTTP 传输次数、账单不可从本地推算。

## 2. 测试任务与输入（沿用 ViMax 同一故事）

### 2.1 同一故事可用性

可沿用 ViMax 的 `photographer_urban_timelapses_typeA.json`（源：`references/repos/ViMax/vimax_benchmark/`；ViMax 已验收的冻结脚本文本见 `env/video/vimax/VIMAX-GENERATION-PILOT-02/preflight-01/staged-planning/registered-script.txt`，8 shot、2 scene，每镜含 `first_frame` 文本＋`video_prompt`）。ViMax 规划的正式验收记录见 `vimax_troubleshooting.md` 与 `vimax_execution_preparation.md`；**同一故事只作为行为/资源描述对照，不构成受控模型对照，也不把 ViMax 成片当作 VideoWeaver 自主产物**。

### 2.2 转换要求（保留 VideoWeaver 原生工作流）

VideoWeaver 的输入契约是 `dataset/<category>/skill_query.json`＋`<category>/<case_id>/{*.txt, 参考图/视频/音频, rubric_deterministic.json?}`（README §Dataset Format）。因此需自建：

| 必需输入 | 格式/内容 | 是否已有可复用素材 |
| --- | --- | --- |
| `skill_query.json`（每 category） | `{"skill_name":"<name>","skill_query":"组合技能创建指令"}` | 无官方样例；按八镜头摄影师故事编写（英文故事、中文指令前缀均可，README 注明当前支持中文提示） |
| case `.txt` | 把 JSON 的 8 组 `first_frame`＋`video_prompt` 转为 `Shot 1..8` 文本（可直接用已冻结 `registered-script.txt` 内容） | **有**（registered-script.txt，SHA-256 `447e4d88…2b59a`）；只读复制到 case 目录 |
| 参考图/视频/音频 | **不需要**（故事全为文本描述） | 无 |
| `rubric_deterministic.json` | 可选；官方评分器不是本仓自带的独立 verifier，而是 `output-eval`/`process-eval` 技能（LLM-as-judge），需自己按故事写 rubric | 无官方样例 |

### 2.3 复用素材会改变什么

本任务不删减原生步骤、不静默去掉音频/参考素材：故事本就没有对白/旁白/配乐要求，video-gen 原生默认"音画同出"仅在模型 prompt 明确要求声音时才发生；适配层按首帧 i2v 约束在任务提示中写明"无对白、无旁白、无配乐"，与 ViMax PILOT-04 一致。复用 `registered-script.txt` 只改变任务输入身份，不改变工作流。**唯一需要新增的是 dataset 目录结构与 skill_query.json（新增文本文件，非下载）。**

## 3. API 与模型清单

原生供应商：**火山引擎 ARK（`volcenginesdkarkruntime`）＋ TOS（`tos`）＋ OpenSpeech（ASR/TTS）**；SDK 直接写死在技能脚本 import 与 `base_url="https://ark.cn-beijing.volces.com/api/v3"`。OpenClaw 路径另需 `openclaw-sdk>=2.1.0`（Codex 路径不需要）。

| 功能 → 调用方/源码 | 协议 / SDK | 输入输出 | 必需 | 凭据变量名 | 当前可复用证据 | 未验证项 |
| --- | --- | --- | --- | --- | --- | --- |
| Agent 推理/规划 → Codex CLI（`codex_cli_tool.codex_chat`） | `codex exec --json`，**Responses**（video-use 已验证 `wire_api=responses`，不写成任选） | 文本任务 → 文本/工具调用流 | 必需 | `DASHSCOPE_API_KEY`（运行时注入；`BAILIAN_WORKSPACE_ID` 仅图片/视频域名需要） | video-use 已在容器内真实跑通 Codex CLI 0.163.0＋百炼 qwen3.7-plus（Responses、工具调用、view_image、rollout 持久化） | pipeline 期望的 stdout 事件 schema（`thread.started/item.completed/turn.completed`）与 rollout 目录（`CODEX_SESSIONS_DIR=~/.codex/sessions`）在目标容器 CODEX_HOME 下的实际对齐；**会话目录错位风险见 §5 接线**；Codex 为独立二进制，**不能套用 ViMax 进程内 SDK 的请求门禁**，须用本地 Responses 转发代理做发送前计数/记账 |
| 视觉理解 → `skills/vision-understanding/scripts/vision_understanding.py` | **两步协议**：① Ark SDK `client.files.create(purpose="user_data")` 上传媒体拿 `file_id`（视频带 `preprocess_configs.fps` 抽帧，轮询 `files.retrieve` 至非 processing，finally 再 `files.delete`）；② OpenAI SDK `client.responses.create()`（`base_url=https://ark.cn-beijing.volces.com/api/v3`），input 为 `input_image`/`input_video`（file_id）＋`input_text`。默认 `doubao-seed-2-0-pro-260215` | 图片/视频＋prompt → 文本分析 | 条件必需（image-gen/video-gen 的 SKILL.md 会引导先分析参考图；本故事无参考图时可能不触发） | 原生 `ARK_API_KEY`；适配后 `DASHSCOPE_API_KEY` | 百炼 `qwen3.7-plus` Chat Completions＋`image_url` base64 已有 `image_tokens=578` 视觉证据（BAILIAN-GENERATION-SMOKE-02）；Codex Responses 内联图片已有 video-use view_image 证据 | **适配必须去掉"Ark Files 上传→file_id"依赖**（改 base64 内联，走百炼），不能只替换图片/视频生成脚本；视频输入（`input_video`/抽帧）在百炼 Chat Completions/Responses 上未验证，适配器须先拒视频输入或单独验证；usage 上报、清理语义随适配重做 |
| 图片生成 → `skills/image-gen/scripts/generate.py` | Ark SDK `Ark.images.generate`（Seedream 5.0）/ OpenAI `images.generate`（gpt-image-2，经 tiktok 代理，`OPENAI_API_KEY`） | prompt/参考图 → 图片文件 | 必需（每镜首帧图） | 原生 `ARK_API_KEY`/`OPENAI_API_KEY`；适配后 `DASHSCOPE_API_KEY`＋业务空间域名 | 百炼 `qwen-image-3.0` `/images/generations` T2I＋I2I（`image` 字段 base64）已真实 PASS（1024×576、usage 计数、像素核对） | 适配 `resolution/ratio/max_images/seed` 参数映射；2k/4k 档与多图 `sequential_image_generation` 未验证 |
| 视频生成 → `skills/video-gen/scripts/generate.py` | Ark SDK `content_generation.tasks.create/get`；参考视频经 `tos` 上传 TOS 预签名 URL | 首帧/尾帧图、参考视频/音频、prompt、ratio/resolution/duration → mp4 | 必需（每镜 i2v） | 原生 `ARK_API_KEY`、`TOS_ACCESS_KEY`/`TOS_SECRET_KEY`；适配后 `DASHSCOPE_API_KEY`（不走 TOS） | 百炼 `wan2.6-i2v-flash` 原生 `video-synthesis` 首帧 base64 已真实闭环（创建→轮询→下载→ffprobe/抽帧）：1280×720/30fps/5.0s/无音轨（SMOKE-02＋video-recovery-01） | **首尾帧、参考视频、音频驱动、视频延长、轨道补齐均未验证，适配器必须显式拒绝**；duration 4–15s 中 >5s 未验证；1080p 档未验证；`video_url` 输入路径需走 TOS，本适配方案不使用 |
| 合并/转码 → `skills/merge-video/scripts/merge_videos.py` | 本地 moviepy＋opencv＋系统 ffmpeg | 多 mp4 → final.mp4 | 必需 | 无 | 基础镜像 FFmpeg 7.1.5＋libx264/aac 构建期已验；ViMax PILOT-04 真实 concat 已验证 moviepy 线程问题修法（`--cpuset-cpus`） | 本仓 `threads=4` 与 moviepy 读者线程在目标容器的实际表现需禁网验证 |
| 目录/任务追踪 → `get-output-dir`、`task-tracker` | 本地 Python | 路径/JSON | 必需 | 环境变量 `OUTPUT_DIR`（codex 环境用 `CODEX_THREAD_NAME/ID` 自动注入） | 纯本地脚本 | 与适配后技能的相对路径一致性 |
| ASR → `skills/automatic-speech-recognition/scripts/recognize.py` | 火山 OpenSpeech `/api/v3/auc/bigmodel/recognize/flash`（`ASR_APPID`/`ASR_TOKEN`） | 音视频 → 文本/SRT | 本故事不需要 | `ASR_APPID`、`ASR_TOKEN` | 未登记/未验证 | 不加入本流程 |
| TTS → `skills/text-to-speech/scripts/generate.py` | 火山 OpenSpeech TTS V3 `/api/v3/tts/unidirectional` | 文本 → 音频 | 本故事不需要 | `AUDIO_GEN_API_KEY`（或 `AUDIO_GEN_APPID`/`AUDIO_GEN_TOKEN`） | 未登记/未验证 | 不加入本流程 |
| 输出/过程评估 → `skills/output-eval`、`process-eval` | LLM-as-judge（Codex＋LLM） | case 目录＋rubric → 分数 | 可选（官方评分不可用，需自写 rubric） | 同 Agent | 未验证 | 仅当需要报告语义评分时才启用 |
| 音频分离 → `skills/audio-vocal-separate` | 本地 Demucs（`demucs>=4.0`＋`torch>=2.0`＋htdemucs 权重） | 音频 → vocals.wav/bgm.wav | 不需要 | 无 | 未安装 | 不加入本流程；不要因 `requirements.txt` 全量安装而引入 torch/demucs |
| 镜头分割 → `skills/video-shot-split` | PySceneDetect（scenedetect） | 视频 → 镜头片段 | 不需要 | 无 | 未验证 | 不加入本流程 |

**结论**：语言（qwen3.7-plus）、图片（qwen-image-3.0）可直接候选；**视觉理解在去掉"Ark Files 上传→file_id"依赖并改走百炼内联图后可用，属独立适配项**；视频仅首帧 i2v（wan2.6-i2v-flash）满足本故事所需形态，但**必须通过适配层把 Ark 协议映射到百炼**，并拒绝未验证模式。生成创建/轮询/下载/重试：原生脚本 `seedance_edit` 在 `max_retries=2` 内仅对 `ContentGenerationError/OutputVideoSensitiveContentDetected/InternalServiceError` 重试，轮询间隔 10s 且无总上限；pipeline 层还有 rate-limit 重试（默认 `max_retries=6`）与 `task_max_retries=3`（整任务重跑）——**这些都会放大请求/计费风险，须由宿主 runner 的预算账本与 deadline 收敛**（复用 ViMax 排障 A3/R5 的经验：SDK 重试归零、结果不明不补建、轮询带鉴权、401/403 即停、下载不带授权头）。

## 4. 独立镜像方案

从登记公共基础镜像派生独立任务镜像（只读核验通过，未构建）：

- 基础：`video-common-base:arm64-v1`＝`sha256:d414b4270fec6ec2dd245982a522099d8941d8cd114ccd5ec2c6730815f3a706`（linux/arm64，Python 3.12.15，FFmpeg/ffprobe 7.1.5，libx264/aac 构建期验证；`env/video/base/base-image.json`）。Docker endpoint 固定 `unix:///var/run/docker.sock`（server 25.0.5）。
- 建议标签 `videoweaver-task-bailian:arm64-v1`；用**最小冻结依赖**而非 `pip install -r requirements.txt`（后者含 `torch`/`demucs`，会引入数 GB ARM64 wheel 与下载超时风险，吸取 OpenStoryline O1 教训）。

| 项 | 结论/推荐 |
| --- | --- |
| Python 版本/锁/安装 | base 为 3.12.15；独立 venv（如 `/opt/videoweaver-venv`），阿里 PyPI 镜像，冻结最小集：`openai, httpx, requests, Pillow, opencv-python, moviepy, numpy, tqdm, PyYAML, json-repair`＋适配层依赖；**不装 volcenginesdkarkruntime/tos/openclaw-sdk/volcengine-python-sdk**（适配后不再需要，减少面） |
| Node 及系统工具 | 不需要 Node；base 已有 ffmpeg/ffprobe/procps |
| ARM64 wheel 与编码器 | opencv-python/moviepy/numpy 均有 aarch64 wheel；编码器 libx264/aac 已有 |
| 大体积模型/CUDA/首启下载 | 无本地权重、无 CUDA、无首启自动下载（本故事不触发 Demucs/PySceneDetect 推理；媒体全在远端 API） |
| 运行用户/工作目录/缓存/可写 | 建议非 root 固定 UID（吸取 OpenStoryline O12 宿主权限教训）；`WORKDIR` 设为仓库根（pipeline 的 `WS_ROOT` 由 `args.py` 相对文件位置计算）；`CODEX_HOME`（如 `/opt/codex-home`，含 Bailian config.toml）、`OUTPUT_DIR`、`generate_materials*`、`running_logs`、`_codex_workspace` 可写；输入 case 只读挂载 |
| 源码/配置/技能发现 | 固定 commit 的仓库 COPY 进容器；`setup_codex_workspace()` 运行时复制技能到 `_codex_workspace/.agents/skills`；codex 配置含 `[shell_environment_policy] set={OUTPUT_DIR=...}` |
| 凭据 | **仅运行时注入** `DASHSCOPE_API_KEY`（＋图片/视频业务空间域名所需 `BAILIAN_WORKSPACE_ID`），不进镜像/日志/报告 |

**Codex CLI 装入**：复用 video-use 已验证 recipe（`env/video/video-use/codex-bailian-integration-01/Dockerfile`）——GitHub release `rust-v0.163.0` 静态 arm64 musl 二进制（sha256 已登记）放到 `/usr/local/bin/codex`，`CODEX_HOME` 放显式 Bailian provider `config.toml`（`model="qwen3.7-plus"`、`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`、`env_key=DASHSCOPE_API_KEY`、`wire_api=responses`、`request_max_retries=0`、`stream_max_retries=0`）。无需下载 npm 包。

**必须验证的风险**（吸取教训）：
- **会话目录错位**：`args.CODEX_SESSIONS_DIR=~/.codex/sessions`，若 CODEX_HOME 设为 `/opt/codex-home`，rollout 会落在 `/opt/codex-home/sessions`，pipeline 将找不到 rollout → 必须让 CODEX_HOME 与 `CODEX_SESSIONS_DIR` 一致（或容器内 `~` 指向 /opt/codex-home）。
- 多线程媒体工具：moviepy/opencv 读者线程受宿主 256 核放大（ViMax R6：pids-limit 耗尽、首帧 0 字节），用 `--cpuset-cpus` 对齐配额＋`--pids-limit`，**不把 0–7 硬编码为通用配置**。
- 实际 shell/解释器路径：普通与 login shell 均用绝对 venv python，检查 `sys.executable/sys.prefix`（video-use V1）。
- `codex exec --dangerously-bypass-approvals-and-sandbox` 以容器内用户权限运行任意命令：容器隔离是唯一边界，镜像不含凭据。
- `requirements.txt` 全量安装会拉 torch/demucs：构建时**只装最小集**，禁止为"和 README 一致"引入大件。

## 5. 复用监控与执行框架（最小接线）

直接复用：
- `src/agent_workload_characterization/collectors/resource_sampler.py` 的 `ResourceSampler(interval_s=0.5)` 与 `CgroupV1FileReader`；`src/agent_workload_characterization/runners/container_runtime.py` 的 `DockerCliRuntime`（含 `mounts`、`--cpuset-cpus`、`--pids-limit`、`--pull=never`）。
- ViMax 固定生产 runner 的生命周期模式（`env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py`）：启动即 `docker logs --follow` 落盘、删除前补取日志（R4）、独立 finally（采样/netns/日志/停删容器分离）、完成握手后取最终资源边界（R7）、`--cpuset-cpus` 对齐（R6）、budget/deadline/账本发送前门禁（P3/P4）、结果不明不补建（A3）。
- 容器内原生 Agent/工具/FFmpeg 及其子进程全部纳入任务容器 cgroup；netns 逐接口采样；任务目录前后占用（apparent bytes）；attempt/阶段/请求/工具事件与 stdout/stderr、删除前 Docker logs；预算（deadline、逻辑请求上限、创建/轮询/下载计数、输出 token 软阈值）；清理与归档、容器删除核验、镜像保留。

必须新增（ViMax 任务专属项不复制）：
- 一个 **VideoWeaver 专用宿主薄入口**：读取 `inference_CodeX/pipeline.py` 的 dry-run 输出（会话清单）→ 逐 session 注入独立请求账本与 deadline；在 `codex exec` 子进程边界处挂 SDK 重试=0 与单次任务重试=1；驱动 `--no_composition_skills` baseline（**baseline 与 `expert` 技能创建流程分开登记，不冒称本轮覆盖完整技能优化实验**）；保存 rollout/ReAct/run.log/媒体映射哈希；`task_max_retries` 收敛以防重复计费。**不要复制 ViMax 的 shot/transition 预算（8+7=15）**——VideoWeaver 无相机树，创建次数由技能实际调用决定。
- **请求门禁（Codex 为独立二进制，不套用 ViMax 进程内 SDK 门禁）**：Codex 的模型请求只能在其客户端内部发生，宿主不能在其进程内插入账本；采用**限定用途的本地 Responses 转发代理**（仅代理百炼 `/responses` 上游，不成为任意 URL 代理）：在转发前原子计数、记账并检查 deadline；SSE 终态/断流/失败/usage 缺失如实记录，结果不明的请求不重试重发；分列代理实际转发次数、模型逻辑响应与网关内部尝试；不声称能观察供应商内部重试或真实账单。
- 百炼媒体适配层：`skills/image-gen/scripts/generate.py`、`skills/video-gen/scripts/generate.py`、`skills/vision-understanding/scripts/vision_understanding.py` 的 Ark→百炼替换（在容器内隔离副本改，参考仓库不改），参照 ViMax `adapter-src` 的做法登记 `ADAPTATION-DIFF.md`；**视觉理解是独立适配点**：要去掉"Ark Files 上传→file_id"依赖（改 base64 内联走百炼 Chat Completions/Responses），视频输入未验证须先拒绝或单独验证，不能只改图片/视频生成脚本；video-gen 对首尾帧/参考视频/音频驱动/延长/轨道补齐**显式拒绝**；`get-output-dir` 的 `CODEX_SESSIONS_DIR` 错位修复属接线项。

禁网验收必须：**全新 workspace＋实际生产入口 `pipeline.py`＋真实 Codex 节点/基础技能/FFmpeg，只替换外部 API 边界**（fake 百炼域名加 `--add-host` 映射回环）；不用握手通过、skip 模式或手工预填 artifact 代替完整冷启动。

## 6. 后续实施顺序（最少必要步骤）

| 步骤 | 内容 | 合并/授权 |
| --- | --- | --- |
| A | 独立依赖环境与镜像：最小冻结依赖 venv＋Codex CLI＋CODEX_HOME/Bailian config＋`videoweaver-task-bailian:arm64-v1`；禁网 shell/import/ffmpeg/技能发现核验 | 需授权（涉及依赖下载与镜像构建） |
| B | 百炼媒体适配（image-gen/video-gen/vision-understanding）＋必要接口最小兼容验证（先离线 fake，再按批准做一次有界真实兼容 smoke：图片 T2I/I2I、视频首帧创建→轮询→下载、qwen3.7-plus 视觉） | 需授权（真实调用/付费 smoke 另行批准；sdk retry=0，逐次入账） |
| C | 原生 Agent/工具、轨迹与监控接线：VideoWeaver 薄入口＋请求账本/deadline＋cgroup/netns/目录采样＋rollout 事件映射 | 可与 A/B 部分合并，但需单独身份 |
| D | 禁网连续冷启动全链与异常清理（`--no_composition_skills` baseline，fake API 边界） | 可与 A–C 合并为一次性准备（依赖与能力足够时直接进 A–D 一次性准备，不人为增加重复 smoke） |
| E | 另行批准的一个真实短任务或正式任务（本故事八镜头 case） | 需单独批准（付费调用/正式 attempt） |

## 7. 准备清单表

| 项目 | 已具备 | 缺口 | 推荐动作 | 是否涉及下载或费用 |
| --- | --- | --- | --- | --- |
| 固定源码 | commit `c809392…bde` 干净 | 无 | 冻结身份，不从历史记录改名 | 否 |
| 官方任务/dataset | 无（目录仅 README） | 自建 case＋skill_query.json | 转换已冻结 `registered-script.txt` 为 case `.txt`；新增 skill_query/rubric 文本 | 否（纯文本） |
| 外层 Agent | Codex CLI 0.163.0 recipe 与本地安装包已登记（`env/video/video-use/codex-bailian-integration-01/build/codex-aarch64-unknown-linux-musl.tar.gz`，SHA-256 `a7261e65…fffe4` 已核验一致） | 本机无独立二进制 | 从本地已核验安装包装入任务镜像，**不重新下载** | 否（复用本地包） |
| 语言/视觉模型 | qwen3.7-plus（Responses＋Chat Completions＋视觉）已验证 | 无 | 直接复用 | 运行时付费调用（另批） |
| 图片生成 | qwen-image-3.0 T2I/I2I 已验证 | Ark→百炼适配 | 改 `image-gen/scripts/generate.py` | 运行时付费调用（另批） |
| 视频生成 | wan2.6-i2v-flash 首帧 5s/720P 已验证 | >5s、1080p、首尾帧/参考视频/音频驱动未验证 | 适配并显式拒绝未验模式；任务提示约束首帧 i2v | 运行时付费调用（另批） |
| 合并/转码 | FFmpeg 7.1.5＋libx264/aac；ViMax concat 经验 | 本仓 moviepy 线程行为未实测 | 禁网验证＋cpuset 对齐 | 否 |
| 任务镜像 | `video-common-base:arm64-v1` 已登记 | 无 VideoWeaver 任务镜像 | 派生 v1（最小 venv＋Codex CLI＋Bailian config） | 依赖下载＋镜像构建（授权后） |
| 监控/收尾 | ResourceSampler/Cgroup/DockerCliRuntime、ViMax runner 模式 | VideoWeaver 专用薄入口与账本 | 派生新入口，复用框架 | 否 |
| 凭据 | `DASHSCOPE_API_KEY` 已登记（运行时注入机制） | 无 | 不读取值；仅运行时注入 | 否 |
| GPU/本地权重 | 无 | 无 | 不需要 | 否 |

## 8. 边界与未验证项汇总

- 没有官方 scorer/benchmark：VideoWeaver 评估是 LLM-as-judge 技能，非独立可执行评分器；自写 rubric 不等于官方验收。
- pipeline 层整任务重试与 rate-limit 重试会放大请求/计费，宿主账本必须收敛；真实 HTTP 次数与账单 unknown。
- 百炼已有证据只证明已测路径，不证明 VideoWeaver 客户端/技能脚本兼容；适配层与接线必须在下一轮真实兼容验收中逐项确认。
- 不修改参考仓库、不读取真实凭据、不安装/构建/下载、不调用 API、不运行 Agent；Gate、CPU-02、Replay 不变，未创建执行批准或 attempt。
