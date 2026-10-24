# ViMax 离线修复与镜像验收 02

日期：2026-10-23。范围是代码、fake 边界和禁网镜像回归；未调用模型、图片或视频 API，未读凭据、未创建 attempt、未启动生成任务。

## 修复结论

1. **预算、deadline 和取消传播：已修复并经生产入口路径验证。** `_run_planning_step` 与 narrative tool adapter 发现控制异常链时保留现有异常链并停止包装成普通可恢复错误。工具路由按异常对象/异常链及 Tenacity `RetryError.last_attempt` 判断，不用错误文本。所有 ViMax agent 的 Tenacity 装饰器统一采用 fail-fast retry predicate；脚本 pipeline 的 camera-tree 手动重试也跳过预算、deadline、取消异常。`ToolRuntimeContext.raise_if_cancelled` 现在发出 `asyncio.CancelledError`。AgentLoop 收到不可恢复 tool result 后不再发请求；请求账本既有 open/error/right-censored 记录语义未被伪造闭合。
2. **JSON 字符串无损：已修复。** 先 `json.loads` 原文；仅解析失败时由识别 JSON 字符串/转义状态的扫描器移除字符串外、紧邻闭合符的尾逗号。空/截断/缺闭合继续拒绝，finish_reason 检查与 Pydantic schema 校验保留。
3. **恢复边界：已修复。** AgentLoop 只在 narrative planning 返回 `ready_for_render=true` 时清除规划失败签名。`ready_for_render=false` 的部分 revision 不会重置同阶段失败预算；同参数同原因仍两次即停，成功的完整规划仍可继续。
4. **未来解析诊断证据：已接线。** 内部 LangChain callback 保存 request ID 与 callback run ID 关联、有限长度结构化响应、截断标记、finish_reason、usage；解析器记录 request ID、错误类型、finish_reason 和响应字符数。常见 credential 字段及签名 URL 查询参数在落盘前脱敏。响应缺失会明确标记，不伪造内容。

## 回归证据

最终在 `vimax-task-bailian:arm64-v5-offline-fixes-03` 内用 `network=none`、只读根文件系统、只读测试挂载、`--rm` 运行既有 8 项和新增 6 项测试，**14/14 通过，返回码 0**。日志：[完整测试日志](tests-v5-final-14.log)。覆盖预算与 deadline 从 planning wrapper 经真实 narrative adapter、tool registry 到 AgentLoop 的停止路径；发送前 fake transport 计数仍为 0；实际 StoryboardArtist Tenacity 遇预算或取消信号只执行一次；普通结构错误仍两次有限恢复；部分 revision 后同阶段重复失败仍停止；字符串内 `,}`/`,]`、引号/反斜杠/嵌套结构、合法尾逗号、空/截断/缺字段/schema 错误；响应关联、脱敏、截断标记。原 8 项兼容回归也一并通过。

早期测试日志保留在本目录，记录了测试夹具导入/绑定问题；最终日志只认 `tests-v5-final-14.log`。这些迭代失败不是生产模型响应或历史任务失败。

## 镜像与边界

- 新镜像：`vimax-task-bailian:arm64-v5-offline-fixes-03`
- 完整 ID：`sha256:5a17b33eac7fb18d9eea4131cea6aa2b7cafb48171539bb4930a6edd3760b193`
- 平台：`linux/arm64`；运行用户 `vimax`；只从本地登记 v4 派生，`--network=none --pull=false`，只 COPY 适配源码，没有安装/升级依赖。
- v4 原标签和原镜像均保留。最终镜像内 `/opt/vimax/src` 的 72 个 Python 源文件逐文件 SHA-256 与宿主 `adapter-src` 完全一致：[`host-source-hashes.json`](host-source-hashes.json)、[`image-source-hashes.json`](image-source-hashes.json)。
- 修改前快照包括本轮开始前保存的 7 个运行时核心文件，以及从登记 v4 镜像禁网导出的 13 个本轮机械重试导入/手动重试模块：[快照范围](pre-change-snapshot-scope.json)、[核心源码快照](snapshots/pre-change-snapshot.json)、[v4模块归档](prechange-v4-unmodified-modules.tar)。
- 定向容器均 `--rm`；最终按镜像筛选容器列表为空。新镜像保留。

## 未验证及下一步

真实模型是否稳定返回完整、符合 ViMax/Pydantic schema 的规划仍未验证。本轮也没有证明真实 SDK 的 finish_reason/usage 字段在当前服务端始终可用；缺失时账本会显式留空。HTTP 实际次数与账单仍 unknown。此次 fake 测试验证接线与停止语义，不代表生成服务兼容或真实规划质量。

下一次只需单独批准一次有硬逻辑请求上限和 wall deadline 的**有限真实规划门禁**，使用新冻结身份和该 v5 修复镜像；先到 narrative planning 并检查完整脚本模式产物，未达规划契约即停止，不进入图片/视频生成。该建议不构成本次授权。
