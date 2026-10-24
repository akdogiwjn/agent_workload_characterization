# 当前任务与下一步

<a id="current-task"></a>

更新：2026-10-24。目标见[当前范围](current_scope.md)，成果与指标见[项目总览](project_status.md)。本页只保留当前结论和待办；详细逐轮过程、失败记录与调试经过见[历史索引](history_index.md#docs-cleanup-20261024)，不是执行批准。

## 当前结论（2026-10-24）

### VideoWeaver：真实生成、独立恢复、真实Agent仅拼接分阶段完成，修复后单次连续生成→拼接未实测

原生成run已真实完成8图和8段主体视频，但未调用merge即耗尽80次模型转发额度，原任务保持未完成（judge FAIL，缺final）；已保存片段后来独立离线恢复成片。修复login-shell的venv路径、技能安装说明和SSE解析后，`VIDEOWEAVER-MERGE-VALIDATE-01`真实Agent读取技能并调用原生merge，生成40秒720P/30fps/H.264无音轨成片，无安装命令、媒体创建/轮询/下载全0；6次Responses的93,487 tokens与rollout对账，另1次summary用量另记（其聚合已由限定离线修复纳入统一软阈值）。**修复后完整生成到拼接的单次连续运行仍未实测**；summary用量聚合、运行中采样落盘与样本摘要接线等已完成限定离线修复，122项离线测试通过，但不等于四个仓库的新采集口径均已由真实任务验证。当前没有新增执行授权。根因、修法与开跑清单见[VideoWeaver排障备忘](videoweaver_troubleshooting.md)，任务级结果见[仅拼接验收](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json)，逐轮过程见归档快照。

### ViMax：PILOT-04 真实媒体生成闭环完成

`VIMAX-GENERATION-PILOT-04` 已通过REPAIR-01固定生产入口完成19张图片、8个主体与7个过渡视频的真实生成和原生拼接；最终40秒、720P/30fps、H.264、无音轨，技术验收33/33通过，容器删除核验完成。规划来自已通过的VALIDATE-03，规划与媒体成本分阶段登记；技术验收与抽帧检查不代替全面语义评分，实际账单仍unknown。当前没有新增执行授权。正式证据见[PILOT-04收尾](../env/video/vimax/VIMAX-GENERATION-PILOT-04/closeout-summary.md)，后续优先复用[ViMax排障与快速复现备忘](vimax_troubleshooting.md)中的固定runner、配置样例及开跑清单。此前规划/启动失败记录按历史保留（见[vimax_execution_preparation.md](vimax_execution_preparation.md)与归档快照），不代表当前仍未跑通。

### video-use：核心剪辑闭环完成，暂无新执行授权

同一采访任务已有四个独立pilot记录；配置与评估完整性不同，不合并为同质重复，不以reward=0否认实际工具执行。

| 运行 | 实际到达阶段 | 结果与证据 |
| --- | --- | --- |
| PILOT-01 | ASR导入前失败，未上传音频、未启动Agent | venv存在但login shell选错Python；后续PATH已修。[原报告](../reports/resource/VIDEO-USE-EDIT-PILOT-01/summary.md) |
| PILOT-02 | 转写、Agent剪辑、自检与提交完成 | judge缺少依赖，评分不完整；分辨率及范围不达标。按[验收修订](../reports/resource/VIDEO-USE-EDIT-PILOT-02/acceptance-revision-01.md)解释，不改原reward。 |
| PILOT-03 | 核心流程与独立评分完成 | reward=0，仅剪切范围未过；规格/时长/SSIM/音频检查通过。[报告](../reports/resource/VIDEO-USE-EDIT-PILOT-03/summary.md) |
| PILOT-04 | 核心流程与独立评分完成 | reward=0，仅剪切范围未过；通用策略改变选段但未改善该项得分。[验收](../reports/resource/VIDEO-USE-EDIT-PILOT-04/acceptance-revision-01.md) |

核心路径已有真实证据：官方Scribe转写→Agent读取转写并自主选段→timeline/渲染工具→局部截图经view_image查看→输出视频及cuts→隔离官方评分。局部截图/RMS不等于听懂音频。不同配置不作为同质重复。用户当前要求保持video-use原生转写/文本/按需图像流程，不接入新音频模型或强制对齐服务；PILOT-04已结束，不创建PILOT-05。

### OpenStoryline：真实剪辑与一次官方评分完成（reward=0不等于未运行）

唯一正式attempt `20261022T150133Z-openstoryline-edit-02` 已提交并完成一次原版官方评分：reward=0.0（唯一golden cut边界未通过），其余规格/时长/SSIM/音频检查通过；Agent和渲染已完成，容器已删除，镜像/缓存保留。完整经过、ASR/MCP修复及开跑检查见[视频剪辑排障备忘](video_editing_troubleshooting.md)，正式证据见[中文摘要](../reports/resource/OPENSTORYLINE-EDIT-PILOT-02/summary.md)与[run-report](../reports/resource/OPENSTORYLINE-EDIT-PILOT-02/run-report.json)。无后续重跑授权。

## 后续方向（未开始、待用户确定）

| 方向 | 当前事实与前置工作 |
| --- | --- |
| 基础剪辑特征分析 | 已有真实调用、产物、资源曲线和完整评分样本可用；不是成功完成成本，不推广到全部视频负载。 |
| OpenStoryline剪辑 | 短任务门禁通过，唯一正式采访 attempt 已提交并完成一次官方评分；reward=0.0（唯一golden cut边界未通过）。Agent和渲染已完成，容器已删除；没有后续重跑授权。详见上方当前结论与[排障备忘](video_editing_troubleshooting.md)。 |
| ViMax / VideoWeaver生成 | ViMax PILOT-04已完成19图、8主体+7过渡、40秒原生成片及33项技术验收；旧规划/启动失败记录保留。后续复用[固定入口与排障备忘](vimax_troubleshooting.md)，新任务需独立批准。VideoWeaver已完成镜像＋百炼适配＋统一生产入口交付与分阶段真实验证（原生成、离线恢复、真实Agent仅拼接），修复后完整闭环未实测；详见[VideoWeaver排障备忘](videoweaver_troubleshooting.md)与[执行准备分析](videoweaver_execution_preparation.md)。 |
| HTML汇总 | 最后统一纳入最新三类与视频成果，不因文档整理重生成历史HTML。 |

## 暂缓待办：video-use 可选能力覆盖

<a id="video-use-optional-coverage-backlog"></a>

| 顺序 | 固定任务方向 | 拟覆盖内容 |
| --- | --- | --- |
| 先做 | 多素材口播剪辑 | 多文件转写与汇总、多素材选段、去重复、拼接、字幕；是否调用批量脚本以实际轨迹为准。 |
| 后做 | 带动态图层的介绍视频 | 动态标题或标注、图层合成、渲染及自检；只选一种上游支持的实现核验，不把静态叠图冒充动画。 |
| 可选 | 多素材观感统一 | 仅在任务要求时增加调色/亮度统一，不加到当前精确剪切任务。 |

以后先固定素材、要求、配置和验收，再决定是否重复；需同时有实际工具调用与产物效果证据。当前不安装依赖、不新增API或运行；这些待办不阻塞已有基础剪辑分析。

## 成果入口

- 公开trace：[操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)、[软件工具集v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md)。
- 三类本地：[合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)，9个固定任务各3点，错路由样本单列排除。
- 视频诊断：[PILOT-03边界分析](../reports/analysis/VIDEO-USE-EDIT-PILOT-03-boundary-review-v1/summary.md)；视频逐run数据与图表从上述pilot报告进入。
- 更早一轮整理前原文：[2026-10-21快照](../local_archive/20261021-doc-refresh-wHAJhI/docs/current_task.md)；2026-10-24整理前原文见[历史入口](#历史入口2026-10-24本轮整理)。

## 保护与授权边界

本次仅整理文档与状态，不修改代码、raw、正式报告、manifest、批准、冻结身份、源码快照、输入、环境或Docker镜像。不用git clean或整目录删除处理未跟踪成果；构建包虽可重获取，仍可能被身份/复现记录引用，未审查前保留。

local_archive被Git忽略，仅存编辑前快照和历史导航，不释放磁盘空间。许可未知不改写为已授权；旧任务的逐次外传批准不代表新API或新任务的许可。G2/G3-R未通过，CPU-02/Replay保持暂停，Gate裁定未变。

<a id="历史入口2026-10-24本轮整理"></a>

## 历史入口（2026-10-24本轮整理）

本轮整理前全文按原字节保存在 `local_archive/20261024-doc-cleanup-647394/docs/current_task.md`，逐文件SHA见该目录`manifest.json`。详细历史过程入口：

- **ViMax**：PILOT-03/02/01失败、规划验证与离线诊断经过，见[vimax_execution_preparation.md](vimax_execution_preparation.md)与[vimax_troubleshooting.md](vimax_troubleshooting.md)的历史段及归档快照。
- **VideoWeaver**：PILOT-01修订与离线恢复、十轮观测验收过程，见[videoweaver_execution_preparation.md](videoweaver_execution_preparation.md)、`env/video/videoweaver/revisions/PILOT-01-recovery-01/`及归档快照。
- **OpenStoryline**：准备、ASR诊断、MCP修复与正式attempt经过，见[video_editing_troubleshooting.md](video_editing_troubleshooting.md)及归档快照。
- **video-use早期探针**：见归档快照。

## 旧任务链接兼容

以下旧锚点保留供既有记录定位；原逐轮正文见[2026-10-21整理前原文](../local_archive/20261021-doc-refresh-wHAJhI/docs/current_task.md)与[2026-10-24整理前原文](../local_archive/20261024-doc-cleanup-647394/docs/current_task.md)，不把旧“当前任务”标题或停止条件当作现行状态。

<a id="video-use-edit-pilot-02"></a>
<a id="video-use-edit-pilot-01"></a>
<a id="video-use-codex-bailian-integration-01"></a>
<a id="bailian-vision-smoke-01"></a>
<a id="video-use-volcano-vision-01"></a>
<a id="video-use-volcano-capability-02"></a>
<a id="video-use-volcano-capability-01"></a>
<a id="video-use-api-review-01"></a>
<a id="video-use-env-01"></a>
<a id="video-four-repo-plan-01"></a>
<a id="当前任务与下一步"></a>
<a id="后续待办video-use-可选能力覆盖暂缓未授权执行"></a>
<a id="video-use-edit-pilot-02一次正式执行与验收已完成"></a>
<a id="pilot-02-验收修订历史原始评分保留"></a>
<a id="video-use-edit-pilot-03单次-attempt-与独立验收已完成"></a>
<a id="pilot-03-离线边界复核与报告修订"></a>
<a id="video-use-edit-pilot-04单次正式执行与验收已完成"></a>
<a id="当前任务video-use-edit-pilot-01一次授权-attempt-已停止未完成真实剪辑"></a>
<a id="当前任务video-use-codex-bailian-integration-01codex百炼工具看图兼容性已验证一次真实-cli-会话"></a>
<a id="素材获取agenticvbench-exp-disfluency-interview-3-task01已获取并核验用户手动上传"></a>
<a id="当前任务bailian-vision-smoke-01百炼-qwen37-plus-图片探针通过发送-11"></a>
<a id="当前任务video-use-volcano-vision-01一次图片探针完成判定-unknown发送-11"></a>
<a id="当前任务video-use-volcano-capability-02工具结果回传补验完成图片未执行发送-12"></a>
<a id="当前任务video-use-volcano-capability-01火山路由三次上限协议探针完成发送-23"></a>
<a id="当前任务video-use-api-review-01只读-api账号模型能力核查完成"></a>
<a id="外部服务清单"></a>
<a id="关键结论"></a>
<a id="需要用户决定提供只问服务模型与环境变量名不需要密钥"></a>
<a id="当前任务video-use-env-01视频环境第一闭环无模型验证完成"></a>
<a id="计划video-four-repo-plan-01可行性核查完成video-use-环境闭环已建真实执行仍未授权"></a>
<a id="四个仓库的可行性与缺口"></a>
<a id="统一记录什么"></a>
<a id="简单推进顺序"></a>
<a id="上一任务local-three-class-repeat-0112次补齐及v3合并复核完成"></a>
<a id="历史阶段v2续批后由complete-02补齐预定槽位"></a>
<a id="原批初次停止时记录保持原义"></a>
<a id="前次任务volcano-three-chain-limited-offline-characterization"></a>
<a id="已完成任务measurement-coverage-unified-01"></a>
<a id="当前任务measurement-coverage-unified-01"></a>
<a id="本轮停止点"></a>
<a id="保留事项与停止边界"></a>
<a id="video-use-edit-pilot-03"></a>
<a id="video-use-edit-pilot-04"></a>
<a id="保留事项与后续清理边界"></a>

## 已完成专项：AgentX DeepSeek客户端重复测量

[最终报告](../reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1/summary.md)：Full全量分析为393会话、98,827请求；所选5个会话各执行3次，共117个唯一源请求、351次正式客户端执行。只测客户端，未执行原始业务工具，原始长输出负载未完整复现。相关证据已做[同机独立备份](agentx_evidence_backup_20261023.md)。上述边界如实保留，不作为待补跑项。
