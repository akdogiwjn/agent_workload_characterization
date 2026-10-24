# ViMax PILOT-01 离线诊断与修复

日期：2026-10-23
范围：只读历史证据、隔离源码修复、禁网定向回归；没有 API、凭据、生成任务或新 attempt。

## 结论

PILOT-01 的直接主因是规划/session 接线和失败恢复没有边界：首次工具调用带 `script` 并进入 Script2Video；该 script 被旧版 session 解析器误存为 `idea`。后续 Agent 工具调用省略 source 时，适配器从 session 的 `idea` 字段恢复，于是切到 Idea2Video，重新扩写故事和场景。规划输出的结构问题又被节点内三次重试、camera-tree 二次尝试和最多50轮的外层工具循环放大，最终耗尽80个逻辑请求。图片和视频生成未启动。

另一个已证实的解析风险是：历史完成 usage 中，29/41 条内部响应的 `completion_tokens` 等于4096；v4 内部 LangChain 输出上限是4096，而外层 Agent 默认上限8192。部分 response usage 还保存了 reasoning token。由于历史记录没有保存响应正文和 `finish_reason`，目前只能确认上限使用和格式错误，不能确认返回被截断、content 为空或 reasoning 导致截断。

## 按时间重建

| 阶段 | 保存证据 | 结论 |
| --- | --- | --- |
| 输入与首次调用 | `task-input.txt` 为八镜头 script；第一个 `vimax_narrative_planning` 参数包含完整 `script`、session id、style 和要求 | 初始确实走 script 模式，不是 idea 模式。 |
| Script2Video 规划 | 两次调用 progress 显示 `script_pipeline_ready`、`plan_script`；第一次报 `RetryError(... OutputParserException)`；第二次曾进入 `decompose_shots`，当时报告的 shot_count 为3，camera-tree二次尝试后报 `Invalid json output:` | 至少发生结构化规划失败。早期模型原文未保存；“shot_count=3”是节点进度记录，不是当前留存 storyboard 文件。 |
| source 丢失与模式切换 | 后续工具参数只含 session id、style、user_requirement；session 文件将原始 source 存在 `idea`；适配器在 idea/script 都缺省时把 `session.idea` 当作 idea | 这是从 script 转入 Idea2Video 的直接接线原因。 |
| Idea2Video 扩写 | 保存的 `idea2video/script.json` 有8个条目；scene 0 storyboard 有4个 shot，scene 1 storyboard 有8个 shot。scene 0 另一次 camera-tree 请求报长度不符；后续调用 progress 走过 scene 0 camera tree 并进入 scene 1 | 固定八镜头要求没有在生成计划阶段强制校验；恢复路径扩大成多个 scene/额外镜头，且没有只恢复必要阶段。 |
| 后续切回 script 与文件工具恢复 | Agent 又显式带回原 script；随后尝试 `write_json` 12次、`run_shell` 5次，另有目录/缺失文件/无效 JSON 的 revision 错误 | 修复动作没有遵循文件工具 schema，也重复调用已说明失败的工具。 |
| 停止 | 80条 LLM 逻辑请求达到门禁；27条 outer、53条 inner；68条有返回、12条 inner start 未闭合；closed usage 合计933,898 tokens | 12条未闭合不代表12次 HTTP 失败。HTTP次数和费用仍 unknown。无媒体生成、无提交、未评分。 |

`project_attempt` 27条是运行器/模型调用关联记录，与80条逻辑请求重叠，不相加。旧 runner 的 `ok=true` 只表示握手完成。

## 根因分类

| 结论 | 分类 | 依据与边界 |
| --- | --- | --- |
| 外层上限8192、内部规划上限4096 | 已确认 | v4 `agent_runtime/llm.py` 默认 `VIMAX_AGENT_MAX_TOKENS=8192`；`vimax_adapters.py` 默认 `VIMAX_NARRATIVE_MAX_TOKENS=4096`；历史 progress 也记录内部4096。 |
| 29条已闭合内部请求 usage 的 completion_tokens 正好4096；41条 closed inner usage 的 reasoning_tokens 合计132,549 | 已确认 | 来自保存的 request ledger usage 字段。reasoning字段缺失的未闭合请求不补算。completion达到上限提高了截断可能性，但 ledger 没有 finish_reason。 |
| `OutputParserException`/`Invalid json output:` 的实际 content、JSON包装、空响应、finish_reason、token截断原因 | 证据缺失 | 原始 SDK response/content未写入 raw；错误摘要不能代替模型响应。不能归因为模型能力或SDK抽取错误。 |
| parser可能把截断 JSON 当成部分结果 | 已确认的代码风险；历史因果未确认 | v4 的 LangChain parser 对 `{"camera_parent_items": [` 离线会解析成空列表。历史没有该响应正文，所以不能说这是那次 got 1 的原因。 |
| camera-tree期望4是shot数还是camera数 | 已确认是camera数 | Schema要求 `camera_parent_items` 与输入 cameras 等长。该次scene 0有4条shot descriptions，`cam_idx`为0–3，故camera数为4。失败返回长度1被拒绝；之后保存的 scene 0 `camera_tree.json` 有4项，说明后续另一轮成功。scene 1 的最终规划仍因无效JSON失败。不能把中间那次长度错误描述为最终tree一直只有1项。 |
| script转idea及场景扩写 | 已确认 | v4 `_resolve_session` 把 `idea or script` 写入 session 的 `idea` 字段；后续无source时按该字段选 Idea2Video。Idea pipeline 会开发故事、拆 scene，再逐scene规划；没有八shot硬约束。 |
| `write_json` 失败 | 已确认 | 12次传入的 `path` 是 shot-description 路径，但 `data` 实际是 JSON字符串；公开schema和参数校验要求 `dict` 或 `list`，请求在文件写入前被拒。不是路径、权限或挂载错误。 |
| `run_shell` 失败 | 已确认 | 5次均试图用 `cat > ...` 写 shot JSON；工具返回 `run_shell is disabled by default`，命令没有执行。该证据不能说明文件权限。 |
| 其他修订失败 | 已确认 | 一次 revision target 指向 `shots` 目录（`Errno 21: Is a directory`）；一次目标 `shots/3/shot_description.json` 不存在；一次模型修订结果有 `Unterminated string`。不是文件系统权限根因。 |
| 为什么重复很多轮 | 已确认与证据缺失并列 | 代码允许最多50轮工具调用；规划节点有3次 tenacity重试，camera-tree另有最多2次尝试；Agent收到工具错误后继续读文件、revision、换模式和再次规划。日志未把全部53条 inner请求按每个错误阶段完整关联，故不能给每种重试精确分摊请求数。 |

## 最小修复

只改隔离副本 `env/video/vimax/adapter-src/`，参考仓库保持不变：

- `SessionIndex` 现在单独持久化 `script` 与 `planning_mode`；显式 script/idea 进新 session 时保存正确模式。后续工具省略 source 时按 session 保存的模式恢复，并在 Agent session context 显示模式。旧 session读取仍兼容，不能把历史 session 静默迁移成新模式。
- Structured output parser 先要求完整 JSON；合法 code fence 与尾逗号修复保留，空/截断/不完整 JSON 不再由宽松 partial parser 接受。若 generation metadata 明确给出 `finish_reason=length`，以可读错误拒绝。没有调整模型参数或输出预算。
- StoryboardArtist 的结构解析错误最多尝试2次；其他异常保持原来最多3次。正常规划中的 character/storyboard/decomposition/camera-tree 阶段不共用“总共两次”计数。
- AgentLoop 对同session、同规划阶段、同类结构错误，或任何工具的同参数同错误，第二次后保存错误并结束该 turn；不再发第三次模型请求。`BudgetExceeded`/`DeadlineExceeded`作为 fatal-stop 标记传过工具边界，AgentLoop收到后不再调用模型。
- `write_json` 描述明确要求 `data` 是对象/数组；`run_shell` 描述明确告知禁用时不要重试。没有扩大权限、启用 shell 或改文件工具 schema。

预算未扩大：request ledger的80逻辑请求上限、8192单请求全局配置和已登记其他预算未改。新解析并没有把4096单次内部上限调高。

## 离线验证

8项定向回归在 v4 镜像 `sha256:7c634c46a829e2d22ee901023b70a6bdb2e5bd06d7b334b0f8a8150a3daa39be` 中通过，`--network none`、`--rm`，将修复源码和测试目录只读挂载；未传入凭据。覆盖：生产 `AgentLoop` + 工具注册下脚本模式续跑和第二次同错早停；预算错误不触发后续模型请求；成功工具阶段可继续；write_json 字符串拒绝、禁用 run_shell；空/截断/finish_reason=length JSON拒绝、合法fenced+trailing-comma JSON接受；camera tree只按camera cardinality核对且不补默认值；能力预检失败返回 `image_or_video_requests_sent=0`。

其中结构化响应、截断响应和 camera tree 单项 fixture 是**合成反例**，不是历史模型响应重放。历史原文没有保存。测试代码与输出：[测试](test_offline_regressions.py)、[测试日志](offline-tests.log)。7个修改的Python源文件在同一离线镜像中编译通过。容器使用 `--rm` 自动删除，v4镜像保留。

## 下一次真实验证建议

当前只证明已知代码风险有离线回归，不证明真实模型稳定输出八镜头合格计划。后续需单独批准，并用新身份/新镜像（v4不含本轮修复）：创建全新script session，只运行原生 Agent 的规划阶段；先检查8个 storyboard shot、8份 shot descriptions、camera tree及结构一致性；不满足即停止，不进入图片/视频生成。建议最多20个逻辑请求、内部单请求4096、外层8192、最多10分钟；重复同阶段结构错误第二次即停。这个是下一轮建议预算，不是本轮更改或批准。

完整证据分类、历史校验、镜像身份与剩余未知项见[机器结果](results.json)；v4源码快照及raw校验入口见同目录文件。当前状态仍是“离线修复通过、真实规划待独立验证”。
