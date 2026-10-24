# ViMax 排障与快速复现备忘

更新：2026-10-24。只总结本项目固定版本、百炼适配及生产入口中实际出现的问题，不是上游所有版本的缺陷清单，也不构成新执行批准。两个剪辑仓库的记录见[video-use / OpenStoryline 排障备忘](video_editing_troubleshooting.md)。

另一个生成仓库见[VideoWeaver排障与快速复现备忘](videoweaver_troubleshooting.md)，其真实生成、离线恢复和Agent仅拼接结果须分阶段解释，不能直接套用本仓的成功口径或过渡创建数。

## 当前已跑通的基线

**先复用这套入口和配置，不要重新拼一套 runner。** `VIMAX-GENERATION-PILOT-04` 已真实完成图片生成、视觉选择、8个主体视频和7个过渡视频，以及原生 FFmpeg 拼接；技术验收33/33通过。此前失败记录保留，不混入本次成功样本。

| 项目 | 固定基线与边界 |
| --- | --- |
| 参考源码 | `references/repos/ViMax`，commit `fd4b72e7731be6e5f88486206d25ea59849b0285`；项目适配在隔离副本，不改参考原件 |
| Agent | 原生 `main_agent.py` / AgentLoop；规划与媒体生成分阶段执行，不能称一次不中断会话完成全部规划和生成 |
| 已通过规划 | `VIMAX-PLANNING-VALIDATE-03`；script模式、冻结剧本、8项分镜/镜头描述、有效camera tree，当前首帧能力契约通过 |
| 镜像 | `vimax-task-bailian:arm64-v7-capability-planning-01`，`sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`，`linux/arm64` |
| 正式入口 | [REPAIR-01 host_runner.py](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py) 与 [generation_entry.py](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/generation_entry.py)；PILOT-02/03目录只作历史，不继续改写其as-run文件 |
| 模型 | 百炼 `qwen3.7-plus` + `qwen-image-3.0` + `wan2.6-i2v-flash`；语言/视觉为Chat Completions，不沿用其他仓库的Codex Responses接线 |
| 正式配置样例 | [pilot-04-formal.json](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/configs/pilot-04-formal.json)；后续另存新任务配置，不能覆盖或重新执行旧输出目录 |
| 资源限制 | 本次为8 CPU、8 GiB、`--cpuset-cpus 0-7`、`--pids-limit 512`；其他服务器先检查允许的CPU集合，不把0-7写成通用要求 |
| 输出及调用 | 19张图片（3肖像+8×2候选）；15个视频任务（8主体+7过渡）；只拼8主体，最终40秒、1280×720、30fps、H.264、无音轨 |

正式成功run：`vimax-generation-pilot-04-20261024T054343Z-c23deb8d`。生成identity SHA-256：`1362a4aad1b0d5ea7b8eb8fa827a9da15f54769aa096d69dc56c37dd494040c1`。规划身份：`7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2`。

证据：[正式收尾](../env/video/vimax/VIMAX-GENERATION-PILOT-04/closeout-summary.md)、[原始运行记录](../env/video/vimax/VIMAX-GENERATION-PILOT-04/execution-01/run-record.json)、[技术验收](../env/video/vimax/VIMAX-GENERATION-PILOT-04/execution-01/workspace/attempt/formal-acceptance.json)、[执行manifest](../env/video/vimax/VIMAX-GENERATION-PILOT-04/execution-01-manifest.json)。

## API与服务边界

| 编号 | 现象与根因 | 修法及下次检查 |
| --- | --- | --- |
| A1 | 图片请求发到旧兼容域名的 `/images/generations` 返回404；不能由此判断模型不可用。后来新业务空间域名未配置WorkspaceId，又在发送前被拒绝。 | 使用本项目已验证的业务空间路由，检查地域、模型、凭据与域名一致。图片生成/编辑走已验证接口与`image`扩展字段，不改成未经验证的`/images/edits`。不要凭模型名猜URL，也不要静默回退供应商。 |
| A2 | 视频创建成功，40次轮询却401：探针查询漏了Authorization。不是视频创建失败；远端可能早已完成并计费。 | 轮询带鉴权，401/403立即停止；已有task_id只恢复查询/下载，不新建任务。原任务后来一次补查即SUCCEEDED。下载媒体不能转发API授权头。 |
| A3 | 把同步图片超时/5xx当作未生成而重发，可能双计费；SDK默认重试也曾未显式关闭。 | SDK重试0，项目尝试逐次入账。当前图片只按登记的429策略有限重试，仍计发送次数；结果不明不补建。创建、轮询、下载、逻辑请求和实际HTTP计数分开；网关内部重试与账单不凭本地次数推算。 |

证据：[SMOKE-02与补查结论](../env/video/vimax/api-probes/BAILIAN-GENERATION-SMOKE-02/video-recovery-01/summary.md)、[生成器适配修订](../env/video/vimax/adapter-src/ADAPTATION-DIFF.md)。旧失败/UNKNOWN保留，不改成事后成功。

## 规划、解析与预算接线

| 编号 | 现象与根因 | 修法及验证边界 |
| --- | --- | --- |
| P1 | 原生session将script存成idea，省略来源续跑时切到idea扩写，造成反复规划。 | idea/script分开保存并记录planning_mode；续跑按保存模式取源。冻结剧本由文件直接初始化session，不让Agent转抄引号/换行；不同输入不覆盖旧session。后续真实规划字节一致已验证。 |
| P2 | 宽松解析可能接受截断JSON；修复尾逗号的正则又曾误改字符串内的`,}`、`,]`。 | 先严格解析原文；仅在失败后扫描字符串外尾逗号，保留转义和schema检查。空输出、缺闭合或length截断不补默认值。camera tree数量错误必须拒绝，不能凭中间一次失败判定必须填充。 |
| P3 | BudgetExceeded/DeadlineExceeded被规划包装器改成RuntimeError，再经Tenacity重试，变成可恢复错误。 | 识别异常链及RetryError中的控制异常，重试层对预算/deadline/取消/账本失败早停；partial revision未达到ready_for_render不能清空同阶段失败次数。外层与内部调用合并计数，响应usage阈值只是软阈值。 |
| P4 | 内部预算放在LangChain回调，但默认raise_error=false，异常可能只记警告；检查再计数也存在并发竞态。 | 锁定版本实际调度中验证raise_error/run_inline；账本原子检查、预留并持久化open后才允许发送。路径未配置或必需写入失败均拒绝，不能只直接调用handler证明门禁有效。 |
| P5 | ContextVar或共享“最近请求”在异步回调中不能稳定关联解析错误；单测用新解析器，但实际StoryboardArtist仍用原版解析器。 | request ID附在对应响应Generation/消息元数据上，实际分镜/拆解节点接入同一解析器；并发不串号，缺依据留null。真实节点经过SDK/fake HTTP的测试不能用单独parser实例代替。VALIDATE-02/03已记录内部解析关联。 |
| P6 | VALIDATE-01四条响应completion均4096且finish_reason=length，三条reasoning占满4096、正文为空；同配置重试没有形成分镜。 | 内部显式enable_thinking=false、输出上限8192，与入口和账本一致；核对最终请求体，不仅检查配置。保存finish_reason、实际模型、usage及有截断标志的响应。VALIDATE-02/03及后续媒体生成已验证当前配置，不推广为任意任务保证。 |
| P7 | write_json传入字符串而schema要求对象/数组；run_shell当时禁用，被误当文件权限问题。 | 保留工具契约和权限，不为消除报错启用通用shell；区分参数校验、工具禁用、进程非零退出与协议错误。不要手写规划产物凑成功。 |
| P8 | medium/large variation走独立末帧及首尾双图，但当前wan2.6适配只接单首帧。仅在外层提示small，不能保证内部拆解遵守。 | 能力声明进入实际storyboard、shot decomposition、camera tree节点，生成前硬预检。`lf_desc`文字字段本身不触发末帧，不能一律删除。当前八镜头约束为small，部分运镜简化；不是原仓全部能力复现。 |

证据：[首轮诊断](../env/video/vimax/VIMAX-GENERATION-PILOT-01-offline-diagnosis-01/diagnosis.md)、[异常与JSON修复](../env/video/vimax/VIMAX-GENERATION-PILOT-01-offline-diagnosis-02/diagnosis.md)、[真实回调调度修复](../env/video/vimax/VIMAX-GENERATION-PILOT-01-offline-diagnosis-03/diagnosis.md)、[4096截断证据](../env/video/vimax/VIMAX-PLANNING-VALIDATE-01/offline-assessment.json)、[能力不兼容审计](../env/video/vimax/VIMAX-PLANNING-VALIDATE-02/execution-01/postrun-audit.json)、[最终规划通过](../env/video/vimax/VIMAX-PLANNING-VALIDATE-03/execution-01/closeout-summary.md)。历史没保存的模型响应不补猜；合成反例不写成历史响应复现。

## 宿主、冷启动、拼接与收尾

| 编号 | 现象与根因 | 修法及下次检查 |
| --- | --- | --- |
| R1 | 原生8镜头还有7条camera父子边，各需一次过渡；只批8次视频创建，预检必拒绝。 | 按实际camera tree和运行候选数核算，不按最终视频段数估计创建次数。本任务为8+7=15；过渡用于子camera首帧连续性，不进最终concat，最终仍约40秒。其他任务重新计算，不固定套用15。 |
| R2 | PILOT-02的`record["k":"v"]`编译合法，执行时TypeError，Agent和采样尚未开始。 | 正常字典赋值；FakeOps必须驱动真实宿主生命周期，不能只编译或替换整个start_attempt。属于本项目runner错误，不是ViMax或百炼失败。 |
| R3 | PILOT-03先读sessions.json后构造SessionIndex；空workspace必现FileNotFoundError。旧握手测试ACK后返回，绕过了这段。 | 先构造再判重，同名session拒绝且不覆盖；同一生产入口从空workspace连续跑到Agent、render、导出。该缺陷后来有离线复现，但PILOT-03原stderr已丢失，不能冒称掌握了其历史完整堆栈。 |
| R4 | ACK后RC1却没有stdout/stderr；删除容器导致根因取证丢失。 | 启动即跟随Docker logs并落盘、删除前限时补取；入口最早阶段记录阶段和traceback。日志异常另记，清理照常；不能用“容器已清理”替代失败证据。 |
| R5 | 禁网fake URL用127.0.0.1时未通过provider域名识别。 | 仅验收环境使用带provider关键字的fake域名及add-host映射回环；真实配置禁止残留fake地址/挂载。不能为测试修改生产供应商判断或让合成凭据访问公网。 |
| R6 | MoviePy concat第4个左右reader读首帧失败。单开FFmpeg正常，实际是256核宿主下各reader自动开大量线程，pids-limit512耗尽；audit捕获pthread_create、RC255和0字节帧。 | 本机用cpuset0-7与8 CPU quota对齐，后续禁网及PILOT-04真实concat通过。`--cpus 8`不等于affinity只有8核。换服务器先检查允许CPU集合、线程/pids约束；不要一看到首帧失败就重下载或重新生成全部媒体。 |
| R7 | 渲染已成功，完成握手时SIGTERM触发SystemExit(0)，却被BaseException兜底写ENTRY-FAILED并变RC1。 | 区分正常SystemExit(0)、取消、真正错误和超时；成功收尾不伪造失败，非零退出仍保留。完成握手期间容器保持存活，宿主取最终资源边界后再停止。 |

详细修法、冷启动和异常反例见[REPAIR-01 FIXES](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/FIXES.md)、[同一生产runner](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py)、[异常反例](../env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/run_counterexamples.py)。该轮禁网验收22项、异常反例10项、生命周期4项属于不同检查口径，不合并冒充独立真实样本；PILOT-04才是后续真实媒体生成证据。

## 下次快速复现顺序

1. **先定位成功基线。** 核对上述镜像完整ID、runner/entry及依赖身份；复用固定入口，不从失败PILOT目录另抄一套。换任务只派生配置，代码变更另作定向回归并冻结。
2. **区分新任务与复用规划。** 原规划只读核验、复制到新workspace并回读。新剧本需重新规划和能力检查；不能把旧规划直接当新任务答案。
3. **检查真实容器环境。** UID、挂载、可写目录、CPU affinity/quota/pids、模型路由和当前网络可达性。已有服务证据可复用；不为换输出目录重复付费smoke，也不读取凭据做文档检查。
4. **按调用图批准预算。** 主体+过渡创建、图片候选、选择器模型请求、轮询和下载分列；实际HTTP及费用无证据就unknown。结果不明任务不重新创建；旧授权不延伸到新run。
5. **配置要对应实际身份。** 本次PILOT-04样例为40图片发送、15视频创建、80模型逻辑请求、每任务最多120轮询/全局1800、下载80、输出8192、returned total_tokens软阈值500k、工作5400秒+收尾300秒。不是所有后续任务的默认批准。
6. **只在入口或工具边界改变时补全链。** 正常复现做必要只读预检；若改启动/渲染代码，使用空workspace、同UID/挂载/限制、同一runner/entry，network=none，只fake外部API，真实经过Agent、session、pipeline、FFmpeg、验收与清理；不能以HANDSHAKE_ONLY或手工预填文件代替。
7. **执行中保存证据，先日志后删容器。** 新session、独立账本、实时monotonic起点和阶段记录；CPU/内存目标0.5秒、netns目标2秒，实测周期与缺口另列。保存主体/过渡/参考图/最终拼接的映射与哈希。
8. **独立判定完成。** RC0、COMPLETE、render_tool_ok、15个远端任务终态、媒体技术验收、清理与归档分别报告。抽帧颜色/签名不同不是全面语义评分，也不保证所有帧无缺陷。规划与媒体两阶段成本分开，不称同一连续attempt。

仅在另行批准后复用正式入口；以下不是立即重跑PILOT-04的命令：

```bash
python3 env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py run \
  --out <新的正式输出目录> --config <新的正式配置JSON>
```

## 报告边界与维护

- 容器cgroup包含本地Python、FFmpeg及子进程，不含远端生成模型CPU/GPU；本地低CPU不能量化远端等待原因。容器netns不是API专属流量。
- memory.current采样峰、内核peak和宿主RSS分列；bytes/GB/GiB区分。采样窗、Agent窗、attempt wall和完整收尾耗时不混用。
- 创建/下载成功、任务全部SUCCEEDED不等于无费用；PILOT-04实际账单仍unknown，仅能说没有已知在途任务。价格估算按当次登记保留，不当作永久单价。
- 失败run仍是有效的失败轨迹，不删除、不并入成功任务成本。已封存的identity、批准、raw、manifest和as-run代码不改写，新结论追加修订。
- 本备忘是当前维护文档，不是冻结执行证据；以后变更不要更新旧manifest的哈希来掩盖源码漂移。Wan3.0/VideoWeaver、新任务或新工具分支需独立适配与授权，不因本次成功默认可用。
