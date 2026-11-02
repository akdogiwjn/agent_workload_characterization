# 开源任务代表性扩展 · 执行准备（VIDEO-OPEN-SOURCE-REPRESENTATIVE-EXPANSION-PREP-01）

> 统一表述：从开源任务集中，按工作流和本地计算操作差异选择代表性任务，在开源视频 Agent 系统中执行，
> 任务转换与环境适配单独登记。本轮仅准备，不授权执行。

## 结论速览

| 候选 | 仓库 | 来源 | 原任务/适配 | 硬要求 | 素材 | 工具表达 | 接线 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | video-use | agentic-vbench repurpose `sports_bolt_beijing_2008_100m` | 原任务 | 1080×1920 竖屏、166s、字幕烧录、角标比分、保留原声、单场 100m 决赛 | **blocked**（无外网到 HF） | partial（Codex+ffmpeg 可表达，但缺 Whisper base + VLM/audio 裁判） | pending |
| 2 | OpenStoryline | agentic-vbench assembly `task1` | 原任务 | 12 选 4、按分镜拼接、solution.mp4+json | **blocked**（无外网） | **yes**（understand_clips→filter_clips→group_clips→plan_timeline 多素材链） | pending |
| 3 | ViMax | `ViMax/vimax_benchmark/musicians_band_rehearsal_typeC.json` | 原任务（远程生成） | 3 场景 13 镜头多人排练 | N/A（远端生成；JSON 本地） | yes | pending（planning_required） |
| 4 | VideoWeaver | 上述 ViMax 故事转换 | 跨仓适配 case（非官方 dataset） | 同源故事 | N/A（远端生成） | yes | pending |

- 全部候选 `source_verified`；候选 1/2 素材 `material_blocked`（本环境无外网出口，HF 不可达）；
  候选 3/4 无需下载素材（远端生成，故事 JSON 已在 `references/repos/`）。
- 候选 1 有 `requires_scope_decision`（字幕/比分/竖屏效果与被验证的“保源禁止效果”策略冲突，且官方 verifier
  依赖 opus-vision+gemini-audio 两个外部模型裁判）。

## 一、候选 1：video-use 复合再创作（Bolt 100m）

- 来源：`references/repos/agentic-vbench@b2764ed4…`，
  `tasks/agentic_vbench_repurpose/sports-bolt-beijing-2008-100m/`。
- task.toml SHA `9e3ba977…`；instruction.md SHA `d029e0dd…`；rubric.json SHA `5f12b31d…`。
- **硬要求（原文）**：单场 100m 决赛“9.69”时刻复剪；1080×1920 竖屏（9:16）、166s（±5%）H.264+AAC 立体声；
  烧录安全区英文字幕（每句解说词）、全程角标比分组件（WR 进 9.69）、保留广播英文解说/发令枪/观众、
  不加配乐/新旁白；胸口锤击时刻至少两次不同机位；含赛前/赛时/赛后结构。
- **差异/冲突**：① 现有 video-use 验证契约是 `output.mp4`+`cuts.json` 的“保源、禁止效果”采访策略，
  与字幕烧录、竖屏重构、角标组件直接冲突；② 官方 verifier 26 项 rubric 含 `opus-vision`（Anthropic VLM）
  与 `gemini-audio`（Gemini 音频）两项外部模型裁判，当前 video-use verifier 只做 range+SSIM+audio xcorr；
  ③ 任务镜像自带 `openai-whisper base`，当前 `video-use-task:arm64-codex-bailian-v6` 未预置。
- 状态：`source_verified`；`material_blocked`；`existing_tools_expressible`=partial（Codex `exec_command`+ffmpeg
  可做竖屏/字幕/角标，但裁判与 Whisper 属新增外部依赖）；`wiring_pending`；`requires_scope_decision`。

## 二、候选 2：OpenStoryline 多素材组接（assembly task1）

- 来源：`references/repos/agentic-vbench@b2764ed4…`，`agentic_vbench_assembly/agentic-vbench-assembly-task1/`。
- task.toml SHA `6202ea52…`；instruction.md SHA `f355d25d…`。
- **硬要求（原文）**：12 段候选 clip → 按 4 个 slot 的分镜五字段（description/shot_size/camera_angle/lens_size/
  camera_movement）各选 1 段、整段各用一次、按 slot 顺序拼接；提交 `solution.mp4` + `solution.json`（4 条
  segments，half-open 区间、source/source_range、首尾连续==总时长）。
- **能力表达**：本仓原生有多素材链 `load_media → split_shots → (elementrec) → understand_clips →
  filter_clips → group_clips → plan_timeline_pro → render_video`（已核查 `register_tools`：
  understand_clips/filter_clips/group_clips 均在）。**不套用** local_asr→speech_rough_cut→cuts 采访路径；
  Agent 自主按分镜选段，宿主不预选。
- 差异：E01/E02/E03 只跑过 speech 路径；多素材理解链的 VLM 字幕与 solution.json 契约未经真实运行。
- 状态：`source_verified`；`materials_ready`；`existing_tools_expressible`=partial；`assembly_wiring_verified`+
  `offline_acceptance`（2026-10-30，`OPENSTORYLINE-ASSEMBLY-PRODUCTION-WIRING-01`：多文件输入门禁 +
  solution.mp4/solution.json 来源导出 + 结构技术验收离线接线；`semantic_selection_needs_validation`）；
  `wiring_pending`（真实多素材理解链 + 真实原生 render 待运行）。

## 三、候选 3：ViMax 多人多镜头生成

- 来源：`references/repos/ViMax@fd4b72e7…`，`vimax_benchmark/musicians_band_rehearsal_typeC.json`，
  SHA `4d52835e…`。原任务（3 场景 13 镜头多人排练故事，Type C 一致性）。
- 素材：无需下载（远端图片/视频生成；故事 JSON 已在本地）。
- 硬要求：13 shot 的 first_frame/video_prompt/person/action/sound 等原文定义跨场景一致；新规划，不能继承
  G01/G02/G03；媒体预算由未来真实 camera tree 核定（13 主体 ≠ 13 次视频请求，过渡数未定）。
- 状态：`source_verified`；`materials_ready`（N/A）；`existing_tools_expressible`=yes；`planning_required`；
  `planning_wiring_verified`+`offline_acceptance`（2026-10-30，v7 入口 `env/video/vimax/planning/`，13 镜头合成
  workspace ok=true + 反例；真实规划仍 `real_validation_pending`）；
  `wiring_pending`（media 门禁：无新规划媒体发送=0）。

## 四、候选 4：VideoWeaver 同源故事适配 case

- 来源：由候选 3 的 ViMax 故事转换为 VideoWeaver 输入（`target_task`/`case_id`/`skill_query`/`task.txt`/
  `registered-script` 真实进入 pipeline）。**非官方 VideoWeaver dataset**；固定版本 dataset 仍为占位。
- 差异：跨仓适配 case；保留来源/原文哈希/适配差异；两生成仓同源故事只描述不同执行方式，不称受控对照。
- 状态：`source_verified`；`materials_ready`（N/A）；`existing_tools_expressible`=yes；`wiring_pending`。

## 五、素材与答案隔离

- 候选 1/2 素材官方地址（公开 HF resolve URL）本轮实测**不可达**（无外网出口，`http_code=000`）→
  `material_blocked`。不读取 HF_TOKEN/ANTHROPIC/GEMINI 等新凭据；不触发模型能力接口。
- 候选 3/4 故事 JSON 已本地（`references/repos/`），仅登记哈希，无外生素材下载。
- 未执行官方 solution 脚本；未读取 golden 内容；媒体不进公开文档。

## 六、后续执行草案（未批准）

### video-use 候选 1（如授权）
- 入口 `scripts/video_use_task_entry.py`；镜像 `video-use-task:arm64-codex-bailian-v6`
  `sha256:1a48c7b0…`（现状，未含 Whisper base / VLM+audio 裁判）。
- 绑定：新 task-config（repurpose.mp4 契约）、Codex 路由、预算沿用已验证口径；elder 单独说明：
  需要在新镜像内置 whisper base、接入 opus-vision+gemini-audio 裁判（或记录裁判不支持为 block）。
- 逻辑请求 / usage / 单请求输出上限沿用已登记；输入为单 mp4（本地资源限制同 E03 量级）。
- 执行顺序建议：先解决“效果策略冲突 + 裁判依赖”后再单独授权。

### OpenStoryline 候选 2
- 入口 `openstoryline_pilot_entry.py --task-config <cfg> --launch-detached`；镜像
  `openstoryline-task:arm64-native-confirm-flow-03` `sha256:9a1e876c…`。
- 绑定：多素材 overlay（如需）、新 config（solution.mp4/solution.json 契约）、素材 SHA、edit 无关。
- 预算沿用：逻辑≤60、soft 1M、单请求 32768、agent 1800s、verifier 600s、cleanup 300s、总 2700s。
- 注意：understand_clips/filter_clips 真实字幕能力待首次真实运行确认；来源导出需支持 solution.json。

### ViMax 候选 3 / VideoWeaver 候选 4
- ViMax `vimax_task_entry`（规划→媒体分阶段授权/冻结）；媒体预算由真实 13 镜头 camera tree 核定；
  图片请求数≠PNG 数；创建/受理/轮询/下载分列。
- VideoWeaver 沿用已验证 venv；镜头数/时长/正常最低完成量与预算上限分开；不继承 8/9/10 默认。
- 建议顺序：ViMax 规划先于媒体；VideoWeaver 同源适配 case 随后。

## 七、CPU 负载代表性

- **候选 1**：新增“竖屏重构+字幕烧录+角标叠加+本地 Whisper 转写”工作流，本地操作含转写/滤镜缩放/字幕
  overlay/多机位剪辑；评审为外部 VLM/音频裁判（远端）。是真正新工具/新操作类型，值得执行（若裁判可接入）。
- **候选 2**：新增“多素材理解/筛选/分组/拼接”工作流，本地操作含 ffprobe、VLM 字幕、ffmpeg 拼接；是
  OpenStoryline 从 speech 路径过渡到 assembly 路径的代表样本，值得执行。
- **候选 3/4**：与 G01/G02/G03 同属“规划+远端生成+轮询下载”，差异主要是规模（13 镜头、多人）与同源故事；
  新增的是场景规模与跨仓适配，本地操作类型不变。B 类是否值得列入，是否替换，由用户决定（见 D 节）。

## 状态汇总（机器登记见 companion JSON）

- 候选 1：`source_verified` + `material_blocked` + `requires_scope_decision`（效果/裁判依赖）。
- 候选 2：`source_verified` + `material_blocked` + `existing_tools_expressible` + `wiring_pending`。
- 候选 3：`source_verified` + `materials_ready` + `planning_required` + `wiring_pending`。
- 候选 4：`source_verified` + `materials_ready` + `wiring_pending`。
## 口径更正（WIRING-01，2026-10-30）

1. **素材获取**：上轮“http_code=000 / 无外网”是误判（当时只试了直连，未走代理）。本轮经既有代理
   `127.0.0.1:22111`（HTTP CONNECT，与 E02/E03 相同路线）下载成功：Bolt `source.mp4`
   `1fe9e2e3…`（79,463,802 B）、assembly `materials.zip` `fa5613c8…`（14,452,898 B，12 段 clip）。
   候选 1/2 素材状态改为 `materials_ready`。
2. **video-use 能力与评估分开**：字幕/角标/竖屏是本任务要求，不是仓库不支持；“保源禁止效果”仅属采访任务
   策略。官方外部裁判（opus-vision/gemini-audio）缺失单列 `evaluation readiness=not_integrated`，
   不据此判 unsupported。执行方案可为“原要求不变 + 技术验收 + official_evaluation=not_run”。
3. **时长**：原 instruction 目标是精确 166s；`±5%`（158–175s）是评分器容差，不改写为任务允许。
4. **计数**：四项新增是 4 个“仓库×任务”观察；两生成仓同源故事只算 1 个新增故事，不是 2 个独立场景，
   不称受控对照；12 组与未来 16 组分开，准备项不计入已完成。
5. **ViMax Type C**：G03 已覆盖 Type C；本任务新增的是三人、三场景、13 镜头规模，不宣称新增一致性类型。
6. **声音能力**：musicians 故事含环境声与演奏描述，而当前已验证生成路径为无声视频。本轮不删声音要求；
   登记 `audio_capability=visual_only_adaptation`，待用户确认是否接受视觉-only 适配或另行解决音频。
   （VIDEO-MUSICIANS-AUDIO-READINESS-01，2026-10-31）已确认：两仓拼接保留音轨、payload 已有 audio 参数但当前强制 false。
   （VIDEO-MUSICIANS-NATIVE-AUDIO-INTEGRATION-AND-PROBE-01，2026-10-31）官方文档确认 wan2.6-i2v-flash 支持有声，
   两仓接线已补齐（audio 受配置贯通、有声媒体验收 profile 驱动），真实探针确认 720P/5s/audio=true 输出 AAC 非静音可解码；
   完整故事运行仍待授权。
