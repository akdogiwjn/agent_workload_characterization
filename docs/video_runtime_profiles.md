# 视频运行配置/适配登记（v2，VIDEO-PROFILE-THREE-POINT-CLOSEOUT-01 修订）

机器可读版本：[video_runtime_profiles.json](video_runtime_profiles.json)。

## 2026-11-01：预算拒绝传播限定修订（无重跑）

OpenStoryline新增本地预算拒绝的结构化MCP错误信封，interview/assembly均恢复为终止异常；
speech_rough_cut首次拒绝即停止，不再将错误文本当JSON解析或继续原句降级并返回成功。
当前27项只读overlay包含ledger和新budget_errors helper，并进入未来冻结范围；未重建镜像。
预算、模型、逐句选择策略及其他非预算fallback语义未变，当前修复不归入历史运行代码身份。

R03-01历史计数更正：60次准入请求闭合＋32次本地发送前拒绝；第二轮开始时只剩10次预算，
先耗尽预算再产生31项伪解析失败，不是供应商31次返回坏JSON。原raw/报告/manifest保持字节不变。
本轮只完成离线修复，不代表E03已正常跑通；41句逐句重做两轮需82次内部请求，预算适配仍需另行决策。
详见[修订报告](../reports/analysis/OPENSTORYLINE-E03-BUDGET-PROPAGATION-REPAIR-01/summary.md)。

## 范围与边界

本页登记"已声明支持的任务类型/profile 内，同类新任务主要通过配置切换"；超出支持范围在付费发送前明确拒绝。
**profile登记本身不增加覆盖计数**：当前为16个历史保留的仓库×任务组合／9个输入，含两仓musicians及独立恢复；不是16次连续成功。用户现计划[9组完整流程重跑](video_full_flow_rerun_plan.md)：原8组含分阶段记录全部保留，加入video-use E03完整trace补采；**R01已执行一次失败观察（OPENSTORYLINE-E01-FULL-FLOW-R01-01，门禁/原生链到render成功但1800s截止、无提交物，不补跑），其余R02–R09尚未授权启动**。修改profile、额度探针、恢复及重跑计划都不增加不同输入或历史组合数。
**版本字段已修正**：agentic-vbench commit（b2764ed4…）只代表**任务来源**，不代表四个执行项目的程序版本。

- "native Agent / native 工具" ≠ "未经修改的上游默认系统"。记录口径为"基于开源项目、在已声明环境和执行配置下采集"。
- 当前 checkout commit 不得自动冒充历史 run 使用版本；历史 run 引用当时冻结身份，无法核实则 unknown。
- 不同版本任务不自动解释为受控性能比较；独立恢复成本单独列，不并入原 attempt 采样窗口。
- 已声明 profile 内的配置消费与拒绝边界经过离线验证；真实 Agent 完成情况、语义效果与供应商行为仍按逐 run 证据判断。

## assembly已保留成果与版本边界

- [EXECUTION-04原运行](../reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/summary.md)使用当时21项overlay，真实完成filter选K→group→plan→render；原入口误用interview完成判定而失败，无自动提交。其[冻结身份](../env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/frozen-identity.json)不改写。
- [独立恢复](../reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/recovery-COMPLETION-01/recover-report.json)逐字节复制同一render媒体、从同一timeline派生solution.json；旧10ms技术策略FAIL，新帧周期策略PASS。官方/语义未评估，reward=null；不追溯为原attempt连续成功。
- [完成判定与时间策略修复](../env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-COMPLETION-AND-RECOVERY-01/summary.md)部署为后续23项overlay版本；不能把其当前SHA或部署数量填成原运行版本。当前用户将task1列入完整流程重跑计划，以新冻结版本执行时再验证自动收尾；本轮没有启动。
- 原运行的1598点样本和CPU统计不包含恢复处理；恢复不另算一个输入、任务组合或Agent attempt。

## 程序来源 / 任务来源 / 适配身份核对

| 仓 | 执行程序来源（repo @ commit，核对方式） | 任务/故事来源 | 本地适配身份 | 适用类型/profile |
|---|---|---|---|---|
| video-use | references/repos/video-use @ `43cfc566…`（source-manifest.json `upstream_commit`） | references/repos/agentic-vbench @ `b2764ed4…` | scripts/video_use_* + 冻结身份 | repurpose（Bolt 166s/1080x1920/h264/aac 立体声 profile） |
| openstoryline | references/repos/FireRed-OpenStoryline @ `c9e94521…`（固定上游 HEAD） | references/repos/agentic-vbench @ `b2764ed4…` | entry+assembly helper+overlay + 冻结身份 | assembly（N 候选→S 段契约） |
| vimax | references/repos/ViMax @ `fd4b72e7…`（固定上游 HEAD） | references/repos/ViMax benchmark story JSON（同仓） | planning/media各自冻结身份，恢复另列 | planning_then_media；历史G01/G02/G03无声，musicians原生有声媒体＋独立AAC拼接恢复 |
| videoweaver | references/repos/VideoWeaver @ `c809392f…`（固定上游 HEAD；env/…/source 镜像 skill 仓） | ViMax故事跨仓适配（musicians case） | host_runner + 冻结身份 | generation_merge；历史silent profile，musicians显式AAC有声profile已真实跑通 |

`recursion_limit=32` 更正：为**本项目宿主/容器入口配置/默认值**（openstoryline_pilot_entry.py 的 request 构造），
**无上游依据，不称"上游默认"**；OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01 起该值为显式任务配置
执行参数（int 1..200，默认 32，进入冻结身份/请求/报告），本轮未提高正式值。

## 既有行为适配（不能被"本轮未新增"掩盖）

- OpenStoryline：任务作用域 assembly 引导文本；`register_tools.py` overlay 的 task_kind 作用域节点注册
  （understand_clips/filter_clips/group_clips 仅 assembly 下）；plan_timeline_pro/speech_rough_cut/render_video/
  task_policy/register_tools 只读 source overlay；recursion_limit=32（本地入口）。
- **assembly 可靠性版本（OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01，2026-10-31）**：截断
  stopReason 传播（maxTokens/error）+ assembly 作用域 `LLMTruncationError`；filter/group/understand
  解析失败/截断/默认全选 fail-closed；节点级 `[filter_clips]` 预算消费并受单请求上限约束；
  render_video 编码前 plan↔group 一致性门禁；recursion_limit 配置化并冻结。interview/默认行为不变。
- **assembly 选择契约（OPENSTORYLINE-ASSEMBLY-SELECTION-CONTRACT-REPAIR-01，2026-10-31）**：
  storyboard Top-K 选择模板（filter_clips_storyboard/group_clips_storyboard，zh/en）仅在
  task_kind=assembly 且存在 assembly_storyboard 契约时生效，替代通用 filter 的 >80% 保留规则与
  group 的通用叙事重排（Hook/Core/Vibe/End、场景打包、2–4 段分组）；N/K/storyboard 来自已消费的
  任务配置 + 冻结原 instruction（`## Storyboard`）；filter 选中数量必须等于 K、group 展开序列必须
  等于已选集合（不增删重）；`[filter_clips] base_max_tokens=8192, cap=8192`。通用/默认模板与
  interview 行为不变。
- ViMax：规划/媒体分阶段；固定工具allowlist与blocked tools；首帧i2v（small）；固定style；历史G01/G02/G03无声，musicians显式audio=true；故事推导镜头数＋seconds_per_shot消费。

- **ViMax 拼接恢复（VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01，2026-10-31）**：根因=13有声clip读取器线程/进程超`--pids-limit 512`；修复=读取器`-threads 1`＋显式AAC＋clip finally关闭。真实13主体恢复final，原运行3015样本与恢复49样本分别登记，不能还原单次连续端到端性能；新增为第16个历史组合，不额外计一次Agent执行。后续R08目标见重跑计划。
- **ViMax musicians 有声媒体运行（VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02，2026-10-31）**：
  唯一正式媒体 run 已执行——媒体生成/下载成功（11 图、25 视频、audio=true/AAC、0 媒体错误、无 429），
  原生 MoviePy concat 读取 shots/12 首帧失败 → final 未生成；完整采集的失败观察，不增加覆盖数，未补跑。
- **ViMax 图片流控与取消收尾（VIMAX-MUSICIANS-IMAGE-THROTTLING-AND-CLOSEOUT-REPAIR-01，2026-10-31）**：
  `image_create_policy`（单在途图片发送、显式最小发送间隔、429 有界重试、每请求 deadline）在真实
  `_post_json` 发送边界生效，首次与重试共用同一许可/间隔；任一图片失败→`image_failure_stop`
  （queued sibling 不再产生新 HTTP）；取消任务父 `image_generation` right-censored 闭合，
  entry 收尾 cancel 未完成 sibling 并有界落盘；发送 cap `image_create_sends` 与逻辑
  `image_generations` 独立；acceptance 支持 characters/portrait_views/candidate_shots
  （预算重核：9肖像＋2候选=11图、25视频、36主流程下载）。这是当时的离线修复；随后EXECUTION-02已执行，另有closeout复下载25次。
- **ViMax 四点闭合（VIMAX-IMAGE-POLICY-FOUR-POINT-FINAL-CLOSEOUT-01，2026-10-31）**：
  ① manifest 不自哈希（子先父后、cwd 无关递归回读、旧自哈希错误保留）；② 每创建绝对 deadline
  覆盖 rate-limiter/排队/pacing/退避/HTTP，超时零新增发送、发送中超时 right-censored、不伪装
  供应商 429；③ 严格有限数值校验（isfinite、拒 bool/字符串）在宿主与 adapter env 两侧一致，
  非法不静默回退默认值；④ Retry-After 正确消费（不截短、支持 HTTP-date、超剩余 deadline 停止
  并记录原因、缺失/非法走fallback）。这是当时离线状态，后续媒体运行与拼接恢复另列，不改历史身份。
- VideoWeaver：跨仓故事适配；registered-script嵌入校验；case/target路由；显式无声/有声受限720p30 profile，musicians AAC真实运行已完成。
- video-use：repurpose 专属提示映射；helper overlay/skill 注册；ElevenLabs Scribe 路线；技术验收契约。

**本轮（THREE-POINT-CLOSEOUT-01）未新增任何行为适配**：仅修复 ① VideoWeaver 字典 profile 帧率校验、
② video-use 时长/容差非有限值拒绝、③ 上述来源/版本登记。

## 帧率口径（VideoWeaver）

`silent_720p30_h264` 接受 `30/1` 与 `30000/1001` 两种**标称帧率**；二者都约为 30fps，但**不数学精确相等**。
字典 profile 显式声明的帧率必须落在该集合内（`60/1` 等明确拒绝）；未声明字段缺省为受支持值（无冲突即兼容）。

## unknown / 限制

- 供应商费用（无账单时 unknown，不宣称金额硬上限）；逐请求 HTTP 次数（协议层 unknown）。
- OpenStoryline assembly真实VLM请求受理、Top-K选择/排序及匹配timeline渲染已有EXECUTION-04实测；五字段选片语义正确性仍`not_evaluated`，官方未评分。修复后的未来自动收尾尚未真实验证，与现有独立恢复成果是否可保留分开。
- 本地资源≠远端 LLM/VLM/媒体生成计算资源；netns≠API 专属流量。
