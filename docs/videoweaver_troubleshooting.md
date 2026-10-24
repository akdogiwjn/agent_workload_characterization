# VideoWeaver 排障与快速复现备忘

更新：2026-10-24。范围为本项目固定版本的基础技能baseline、百炼适配与生产入口，不是上游所有版本的缺陷清单，不构成新执行授权。相关记录：[ViMax排障](vimax_troubleshooting.md)、[video-use / OpenStoryline排障](video_editing_troubleshooting.md)、[VideoWeaver准备与阶段记录](videoweaver_execution_preparation.md)。

## 先区分三个结果

| 阶段 | 实际结果与证据 | 不能怎样汇报 |
| --- | --- | --- |
| 原真实生成 `run-944af65d` | 8张首帧、8段真实视频完成，未调用merge，80次模型转发预算耗尽；原任务没有final。[原报告](../env/video/videoweaver/evidence/VIDEOWEAVER-GENERATION-PILOT-01/run-944af65d/run-report.json) | 不能把视频生成成功写成该attempt端到端成功，也不能将失败全归为模型能力不足。 |
| 独立离线恢复 | 使用原8段视频、固定venv和原生merge脚本生成40秒恢复视频。[修订与恢复记录](../env/video/videoweaver/revisions/PILOT-01-recovery-01/recovery-notes.md) | 不是Agent自主完成；不能将恢复产物、时间和资源回填原attempt。 |
| 真实Agent仅拼接 `run-5acc457e` | v2环境下Agent读取技能、调用原生merge并检查成片；无安装命令、无媒体创建/轮询/下载，输出40秒720P/30fps/H.264/无音轨。[任务级验收](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json) | 证明自主拼接及真实SSE接线，不等于修复后又完整执行过一次八镜头生成。 |

当前可报告：**媒体生成与Agent自主拼接已有真实证据，工作流分阶段覆盖；修复后单次连续生成到拼接仍未实测。** 技术规格与有限抽帧检查不代替完整语义/人物一致性评分，不编造reward。没有新执行授权，不为补齐一句“端到端成功”自动重生成8段视频。

## 复用基线，不重新拼入口

| 项目 | 当前基线 |
| --- | --- |
| 源码 | `references/repos/VideoWeaver`，commit `c809392fe6c2c8b22472049684aaefc650e31bde`；隔离适配在 `env/video/videoweaver/source/`，不改参考原件 |
| Agent与流程 | Codex CLI 0.163.0 + 原生 `AutomaticSkillOptimization/inference_CodeX/pipeline.py` + 基础技能；baseline保留基础技能，但不包括expert组合技能创建/优化 |
| 修复版镜像 | `videoweaver-task-bailian:arm64-v2`，`sha256:933363d720001f71a74bd261c14a3480595942ec4612857797f3ca1814dbb6eb`，linux/arm64；旧v1按历史保留 |
| 解释器 | `/opt/videoweaver-venv/bin/python`；v2在容器 `/etc/profile` 末尾恢复venv优先PATH，覆盖普通/login/实际Codex工具shell |
| 入口与网关 | [host_runner.py](../env/video/videoweaver/runner/host_runner.py)、[gateway.py](../env/video/videoweaver/gateway/gateway.py)；宿主/挂载文件也须绑定identity，不能只固定镜像标签 |
| 配置与任务 | [真实生成配置](../env/video/videoweaver/runner/live-config.json)、[仅拼接配置](../env/video/videoweaver/runner/merge-validate-config.json)、[仅拼接身份](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/identity.json)；新任务另存配置/目录，不原样重跑旧输出 |
| 模型 | Codex：百炼qwen3.7-plus Responses；视觉/summary按实际适配调用Chat Completions；图片qwen-image-3.0；视频wan2.6-i2v-flash单首帧 |

## 准备与能力适配中出现的问题

| 编号 | 问题与判断 | 处理及以后检查 |
| --- | --- | --- |
| V1 | 官方dataset只有占位README，被误当成本次工作流最大阻塞。 | 官方benchmark任务不能凭空复现，但支持自定义case。按category/skill_query.json/case目录契约转换同一故事，记录来源与哈希；同故事不构成严格受控比较。 |
| V2 | 宿主无codex命令，被误判为必须重新下载CLI。 | 复用video-use已保留的官方arm64 musl安装包并核对登记哈希；装入任务镜像，不改宿主。Codex使用已验证Responses，不把另一仓的Chat Completions接线直接套入。 |
| V3 | 原生媒体技能绑定Ark/火山接口；视觉工具还先上传Ark取得file_id。 | 在隔离副本适配image/video/vision及summary路由，保留技能调用契约。图片T2I/I2I按百炼接口；视频create→task_id→poll→download；视觉图片内联，视频仅显式标记sampled_frames抽帧审阅。Ark文件编号不能交给百炼；抽帧不是完整视频/音频理解。 |
| V4 | 文档声明的首尾帧、参考视频/音频、延长、T2V等不等于当前wan适配支持。 | 能力限制同时进入SKILL.md、CLI与发送前检查，不支持模式明确拒绝。当前实测仅5秒720P无音轨首帧i2v；不能静默忽略参数，也不照抄ViMax的7个过渡预算。 |
| V5 | CODEX_HOME与harness默认`~/.codex/sessions`错位，可能找不到rollout；sandbox/bypass参数堆叠也与CLI不符。 | 会话路径由专用CODEX_HOME派生；按当前CLI实际参数组合启动，保留原生rollout，ReAct只是派生结果。检查workspace配置复制不会覆盖百炼provider。 |
| V6 | Codex子进程继承外源OUTPUT_DIR，可能将媒体写入无关默认路径。 | `get-output-dir`优先使用明确VW_OUTPUT_DIR；新任务唯一新根目录，case、技能和原生pipeline导出路径逐项对齐。不能靠全盘找最新final猜来源。 |
| V7 | fake预设快速成功，未覆盖真实长命令的`Process running`与write_stdin终态；媒体读者线程还受宿主核数放大。 | 保留真实Codex、技能与FFmpeg，仅fake外部API；长任务等待须有预算、日志与终态。核对CPU affinity/quota/pids，普通配额不限制程序看到的全部核数；本机验收用0-7/4096，其他机器先检查允许集合，不照搬。 |

证据：[初次适配差异](../env/video/videoweaver/evidence/adaptation-diff.json)、[禁网冷启动报告](../env/video/videoweaver/evidence/acceptance-run-3/run-report.json)、[生产入口登记](../env/video/videoweaver/evidence/production-entry-manifest.json)。后者按其记录时版本解释，后续改动另绑身份，不能刷新旧manifest掩盖漂移。

## 生产入口与付费控制中出现的问题

| 编号 | 问题与根因 | 修复、验证与边界 |
| --- | --- | --- |
| R1 | 初版runner仅支持offline，固定fake key/config；预算只控制fake响应，并不控制真实媒体发送。 | 后续实现共用offline/live路径和限定用途网关；Codex/技能只持本地任务token，上游密钥由网关持有。发送前原子预留、记账落盘后转发，模型、创建、轮询、下载分别计数。不能用事后rollout计数或STALLED代替门禁。 |
| R2 | `reset_volume`递归清空配置目录；重用路径可能毁掉旧证据。 | 唯一新目录排他创建、存在即拒绝，拒绝宽泛路径。正式流程禁止旧reset和chmod777补救；UID/GID/挂载权限提前核对。 |
| R3 | 初版采样线程无限循环、无停止信号；仅summary，无完整逐点/netns；docker exec输出丢弃而只读docker logs。 | stop Event+有限join，容器存活时取最终边界；保存逐点resources/netns、目录边界。exec stdout/stderr实时落盘，Docker logs另存，删除前补取；采集/报告错误不跳过回收。 |
| R4 | 同目录有两次较早live启动，各模型转发一次，分别404/401，不能只数媒体生成run。 | 修订登记为上游路径双前缀、凭据值引号接线问题；本地3次启动、82次转发与80次正式转发分列。404/401不证明账单已确认为零，授权分类按保存身份说明，供应商账单仍unknown。 |
| R5 | pipeline_rc=0不代表有final；仅拼接case又曾被通用生成judge的eight_clips检查判失败。 | 任务结果、Agent终止、网关预算、日志/资源、清理分列。拼接任务不要求本次生成8段，按已批准输入和任务级验收判断；保留当时runner FAIL与另列的任务级PASS，不偷偷回写。 |

证据：[v2异常反例](../env/video/videoweaver/evidence/counterexamples-v2.json)、[原正式任务账本](../env/video/videoweaver/evidence/VIDEOWEAVER-GENERATION-PILOT-01/run-944af65d/ledger/ledger.json)、[修订总账与恢复](../env/video/videoweaver/revisions/PILOT-01-recovery-01/recovery-notes.md)、[仅拼接任务级验收](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json)。

## 真实生成后未能拼接：核心故障链

1. **v1依赖实际已装在venv，但login shell重置PATH。** 普通shell用venv，Codex的`bash -lc`却用系统python/pip。Agent早期执行一次`pip install Pillow httpx requests`，随后系统解释器能够跑图片/视频脚本；不能因8段已成功就认为解释器正确。
2. **merge技能还要求任务期安装依赖。** 8段视频生成后，Agent执行一次`pip install moviepy opencv-python`，接着等待该安装进程，未真正调用merge。安装长期未结束的具体原因没有最终输出，保持unknown；不是“反复安装”，也不是已证模型无能力。
3. **只在文档顶部加提醒不够。** 第一轮补丁后仍残留旧pip安装行和裸python示例，且image/video也会走错解释器。最终v2修复容器profile，四技能加入一致环境契约，删除merge安装矛盾行；生产挂载merge修复版并绑定身份。真实Codex工具已确认venv并成功调用原生merge，无安装命令。
4. **安装等待、正常视频等待与模型请求都消耗了会话预算。** 空命令/轮询按实际保存记录描述，不把所有低CPU或等待都归为远端生成；不能只增加LLM次数来补救错误环境。

当前实际说明：[merge技能](../env/video/videoweaver/source/skills/merge-video/SKILL.md)、[镜像Dockerfile](../env/video/videoweaver/build/Dockerfile)。普通/login shell及复制后的`.agents/skills`都要检查；构建期绝对venv导入成功不等于真实工具shell正确。不要给系统Python补装同一套包或全局覆盖系统Python。

## SSE、usage和预算为什么漏记

- 原网关对SSE字段/终态的解析没有适配真实流：80次terminal均unknown、在线usage为0。原生rollout仍保留80个唯一response_id的用量，不能把所有用量写成unknown。
- 修复支持data冒号后有/无空格、多行、CRLF、终态和按response_id去重。`[DONE]`或EOF本身不等于成功；原始上游流未留存时，协议fixture不能冒称历史原字节回放。
- 历史逐响应求和与最后累计一致：input **3,281,314**，cached_input **2,965,760**，output **16,676**，reasoning_output **2,620**，total **3,297,990**。缓存是输入子项、reasoning是输出子项，不额外相加；包含重复上下文，不是独立文本量或账单。
- 原登记500k软阈值未有效执行；回读历史第20个响应累计已到525,286。修复后不能机械沿用同一阈值期待完整八镜头一定完成，应按任务范围和实测上下文重新审批，不擅自调大。
- 真实仅拼接验证：6次Responses completed，6个response_id的93,487 tokens与rollout一致；另有1次summary Chat Completions，总模型转发7次。**93,487只代表Responses对账值，不是7次调用全部用量。**
- 历史[拼接账本](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/run-5acc457e/ledger/ledger.json)显示：summary的无response_id用量另记，未计入当时Responses total软阈值——那是修复前的记录。后续离线修复已让网关把非SSE summary的 `total_tokens` 分字段计入统一软阈值（缺ID归本地请求去重、不合并），并经定向测试验证；但该修复只作限定离线验证，尚未由新的真实大用量run复测。所有模型用量都不是账单，不能称现有阈值已覆盖全部模型费用。

证据：[用量修订](../env/video/videoweaver/revisions/PILOT-01-recovery-01/recovery-notes.md)、[SSE定向测试](../env/video/videoweaver/runner/test_sse.py)、[真实拼接验收](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json)。不为验证阈值额外花费真实请求撞上限；在线解析生效与边界反例分别记录。

## 最快的复现与排障顺序

1. **选对范围。** 生成、离线恢复、Agent仅拼接用不同case、身份、输出及资源scope。已有8段时优先复用，不自动重新付费生成；输入文件只读核验后复制到新目录。
2. **复用v2与固定入口。** 新任务用新配置/目录，核对完整镜像ID、宿主网关/runner及技能挂载哈希。v1不能被称为已含profile修复；仅拼接通过不证明新v2完整生成已实测。
3. **先查实际shell再查模型。** `bash -lc`下检查python/pip、sys.prefix和模块来源。直接调用原生脚本；任务中禁止pip/uv安装，缺依赖是环境错误。
4. **读真实技能与case路径。** 确认pipeline复制后技能是修复版，dataset挂载的是含category的根目录；MERGE验证曾因直接挂category而未发现case。原生merge把输出放首个输入目录，必须在新任务副本中写，不污染历史媒体。
5. **核对路由与门禁。** Codex走Responses，图片/视频/summary按各自路径映射，不重复拼接API前缀。凭据格式仅运行时检查，不回显/哈希；任务只持本地token，创建未知不重建。纯拼接的创建/轮询/下载额度为0。
6. **先验收真实生产冷启动，再考虑付费。** 若改入口/网关/技能，空workspace、同UID/挂载/限制，只有外部API替换；真实Codex、脚本、FFmpeg、导出和收尾都经过。fake快速成功不能覆盖真实长命令等待或用量规模。
7. **先看trace和日志。** 工具是否真的调用、正在等待哪个session、进程是venv还是系统、已运行多久，分别核对。别因无新输出就重发创建或无限write_stdin；不能把报告RC0当工具/媒体成功。
8. **保留失败与修订。** 原生成没有final保持失败；后处理及新Agent拼接各自登记。最终成片与恢复成片同哈希不足以单独证明来源，还要核对新目录、输入、原生调用及返回。删除前保存exec/Docker/gateway日志，记录资源缺口、独立停止采样和所有进程。

后续另行批准才可使用固定入口；不要原样重跑旧配置目录：

```bash
python3 -B env/video/videoweaver/runner/host_runner.py \
  --mode live --config <新任务配置JSON> --out <唯一新输出目录>
```

## 当前未验证与维护边界

- 修复后v2完整生成→拼接的一次连续真实run仍未验证；已有真实生成和自主拼接分阶段证据，不自动补跑。
- 基础技能baseline不是expert技能组合/优化全覆盖；ASR/TTS、直接视频理解、音频、多参考/首尾帧等不在当前已验范围。
- 阈值边界主要由离线反例验证；summary用量聚合已由限定离线修复纳入统一软阈值，尚未经新的真实大用量run复测。所有模型用量都不是账单；404/401也不等于已核实零费用。
- 容器cgroup覆盖本地Agent/技能/FFmpeg，不包含远端模型资源；netns不是API专属流量。峰值、采样窗和attempt wall分列，不混加不同阶段/不同scope。
- 本页是当前维护备忘，不是冻结运行证据。不修改旧manifest、ledger、rollout、批准和as-run代码来让历史“变通过”；新增结论另作修订，新配置另需授权。
